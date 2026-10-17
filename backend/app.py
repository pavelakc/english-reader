"""Graded Reader backend — Flask on Railway.

Env vars:
  APP_KEY               shared secret; the frontend sends it as X-App-Key
  ANTHROPIC_API_KEY     Claude API key (contextual translation)
  CLAUDE_MODEL          optional, default claude-haiku-5-5
  SUPABASE_URL          https://<ref>.supabase.co
  SUPABASE_SERVICE_KEY  service_role key (server only, never in the frontend)
  ALLOWED_ORIGINS       optional, comma-separated (default *)
"""
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

import srs
import textproc
from books import BOOKS_BY_ID, public_catalog
from store import make_store

app = Flask(__name__)
CORS(app, origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")])
store = make_store()

APP_KEY = os.environ.get("APP_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
_load_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

# Injected in tests; in production the real Claude client is used.
claude_call = None


def err(msg, code=400):
    return jsonify({"error": msg}), code


@app.before_request
def check_key():
    if request.method == "OPTIONS" or request.path in ("/", "/api/health"):
        return None
    if APP_KEY and request.headers.get("X-App-Key") != APP_KEY:
        return err("Неверный ключ приложения", 401)
    return None


@app.get("/")
@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": MODEL, "storage": type(store).__name__})


# ---------- books ----------

@app.get("/api/books")
def books():
    return jsonify(public_catalog())


def _download(url):
    r = requests.get(url, timeout=90, headers={"User-Agent": "GradedReader/1.0 (personal learning app)"})
    r.raise_for_status()
    return r.content


def ensure_book(book_id, level):
    total = store.total_pages(book_id, level)
    if total:
        return total
    key = f"{book_id}:{level}"
    with _locks_guard:
        lock = _load_locks.setdefault(key, threading.Lock())
    with lock:
        total = store.total_pages(book_id, level)
        if total:
            return total
        url = BOOKS_BY_ID[book_id]["levels"][level]
        raw = textproc.extract_text(_download(url), url)
        pages = textproc.to_pages(textproc.to_paragraphs(raw))
        if not pages:
            raise textproc.NoTextError("Не удалось извлечь текст")
        store.save_pages(book_id, level, pages)
        return len(pages)


@app.get("/api/books/<book_id>/<int:level>/page/<int:page>")
def book_page(book_id, level, page):
    book = BOOKS_BY_ID.get(book_id)
    if not book or level not in book["levels"]:
        return err("Книга не найдена", 404)
    try:
        total = ensure_book(book_id, level)
    except textproc.NoTextError as e:
        return err(f"{e}. Эту книгу пока нельзя открыть.", 422)
    except requests.RequestException:
        return err("Не удалось скачать книгу с сайта университета", 502)
    except Exception as e:  # noqa: BLE001
        app.logger.exception("book load failed: %s", e)
        return err("Не получилось подготовить книгу. Попробуй другой уровень.", 500)
    page = max(0, min(page, total - 1))
    p = store.get_page(book_id, level, page)
    return jsonify({"book_id": book_id, "level": level, "page": page, "total": total,
                    "title": p.get("title"), "text": p["text"]})


# ---------- translation ----------

WORD_PROMPT = """You help a Russian-speaking adult (A2–B1) read English books.
Translate the word as it is used in THIS sentence. Answer with JSON only, no prose:
{
 "word": the word as written,
 "lemma": dictionary form (e.g. "went" -> "go"),
 "pos": part of speech in Russian, short ("глагол", "сущ.", "прил.", "нареч."...),
 "ipa": IPA transcription of the lemma, American English, e.g. "/ɡoʊ/",
 "translation": 1–3 Russian words, the meaning in this context,
 "other": up to 3 other common Russian meanings (array, may be empty),
 "note": one short Russian sentence about usage or grammar here (e.g. tense, why this form), or "",
 "phrase": if the word is part of a phrasal verb or idiom in this sentence: {"text": "...", "translation": "..."}, else null
}"""

SENT_PROMPT = """Translate this English sentence into natural Russian for a learner.
Answer with JSON only: {"translation": "...", "note": "one short Russian note on a tricky grammar point, or empty"}"""


def _claude(system, user, max_tokens=400):
    if claude_call:
        return claude_call(system, user)
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json")
    return json.loads(m.group(0))


def _key(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


@app.post("/api/translate")
def translate():
    body = request.get_json(force=True, silent=True) or {}
    word = (body.get("word") or "").strip()
    sentence = (body.get("sentence") or "").strip()[:600]
    if not word or len(word) > 40:
        return err("Нет слова")
    key = _key("w1", word.lower(), sentence)
    cached = store.get_translation(key)
    if cached:
        return jsonify(cached)
    try:
        data = _parse_json(_claude(WORD_PROMPT, f"Word: {word}\nSentence: {sentence}"))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("translate failed: %s", e)
        return err("Перевод не получился, попробуй ещё раз", 502)
    data["word"] = word
    store.save_translation(key, word.lower(), data)
    return jsonify(data)


@app.post("/api/translate-sentence")
def translate_sentence():
    body = request.get_json(force=True, silent=True) or {}
    sentence = (body.get("sentence") or "").strip()[:800]
    if not sentence:
        return err("Нет предложения")
    key = _key("s1", sentence)
    cached = store.get_translation(key)
    if cached:
        return jsonify(cached)
    try:
        data = _parse_json(_claude(SENT_PROMPT, sentence))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("sentence failed: %s", e)
        return err("Перевод не получился, попробуй ещё раз", 502)
    store.save_translation(key, sentence[:60], data)
    return jsonify(data)


# ---------- vocabulary ----------

@app.get("/api/vocab")
def vocab_list():
    return jsonify(store.list_vocab())


@app.post("/api/vocab")
def vocab_add():
    body = request.get_json(force=True, silent=True) or {}
    word = (body.get("word") or "").strip().lower()
    if not word:
        return err("Нет слова")
    item = {k: body.get(k) for k in ("lemma", "translation", "ipa", "pos", "context", "status")}
    item["word"] = word
    if item.get("lemma"):
        item["lemma"] = item["lemma"].strip().lower()
    return jsonify(store.add_vocab(item))


@app.patch("/api/vocab/<int:vid>")
def vocab_update(vid):
    body = request.get_json(force=True, silent=True) or {}
    fields = {k: body[k] for k in ("status", "translation") if k in body}
    if fields.get("status") not in (None, "learning", "known"):
        return err("Неверный статус")
    if fields.get("status") == "learning":
        fields.update({"due_at": datetime.now(timezone.utc).isoformat()})
    v = store.update_vocab(vid, fields)
    return jsonify(v) if v else err("Не найдено", 404)


@app.delete("/api/vocab/<int:vid>")
def vocab_delete(vid):
    store.delete_vocab(vid)
    return jsonify({"ok": True})


@app.get("/api/review/due")
def review_due():
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify(store.due_vocab(limit))


@app.post("/api/review/<int:vid>")
def review_card(vid):
    body = request.get_json(force=True, silent=True) or {}
    grade = int(body.get("grade", 2))
    card = store.get_vocab(vid)
    if not card:
        return err("Не найдено", 404)
    return jsonify(store.update_vocab(vid, srs.review(card, grade)))


# ---------- reading progress ----------

@app.get("/api/progress")
def progress_list():
    return jsonify(store.list_progress())


@app.post("/api/progress")
def progress_save():
    b = request.get_json(force=True, silent=True) or {}
    if b.get("book_id") not in BOOKS_BY_ID:
        return err("Книга не найдена", 404)
    store.save_progress(b["book_id"], int(b.get("level", 0)), int(b.get("page", 0)), b.get("total_pages"))
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
