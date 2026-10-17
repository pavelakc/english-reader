"""Graded Reader backend — Flask on Railway.

Users sign in with an email code (Supabase Auth). The browser never sees any Supabase or
Anthropic key: sign-in goes through /api/auth/*, and every personal endpoint checks the
user's access token with Supabase.

Env vars:
  ANTHROPIC_API_KEY     Claude API key (contextual translation)
  CLAUDE_MODEL          optional, default claude-haiku-5-5
  SUPABASE_URL          https://<ref>.supabase.co
  SUPABASE_SERVICE_KEY  service_role key (server only)
  ALLOWED_ORIGINS       optional, comma-separated (default *)
  DAILY_LIMIT           optional, new (uncached) translations per user per day, default 300
  SITE_URL              optional, where email links send people back (the reader page)
"""
import functools
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, g, jsonify, request
from flask_cors import CORS

import srs
import textproc
from books import BOOKS_BY_ID, public_catalog
from store import make_store

app = Flask(__name__)
CORS(app, origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")])
store = make_store()

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", 300))
SUPA_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPA_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SITE_URL = os.environ.get("SITE_URL", "https://pavelakc.github.io/english-reader/")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_load_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

# Injected in tests; in production the real services are used.
claude_call = None
token_check = None  # fn(token) -> {"id":..., "email":...} or None

_token_cache: dict[str, tuple[float, dict]] = {}


MSG = {
    "uk": {
        "Слишком много попыток. Подожди минуту и попробуй снова.": "Забагато спроб. Зачекай хвилину й спробуй знову.",
        "Почта пока не может отправить письмо на этот адрес. Владелец приложения должен подключить отправку писем.": "Поки не вдається надіслати лист на цю адресу.",
        "Код неверный или устарел. Запроси новый.": "Код неправильний або застарів. Запроси новий.",
        "Не удалось отправить письмо": "Не вдалося надіслати лист",
        "Проверь адрес почты": "Перевір адресу пошти",
        "Введи код из письма": "Введи код із листа",
        "Код не подошёл": "Код не підійшов",
        "Нет сессии": "Немає сесії",
        "Сессия истекла, войди снова": "Сесія завершилася, увійди знову",
        "Нужно войти": "Потрібно увійти",
        "Книга не найдена": "Книжку не знайдено",
        "Эту книгу пока нельзя открыть.": "Цю книжку поки не можна відкрити.",
        "Не удалось скачать книгу с сайта университета": "Не вдалося завантажити книжку із сайту університету",
        "Не получилось подготовить книгу. Попробуй другой уровень.": "Не вдалося підготувати книжку. Спробуй інший рівень.",
        "Нет слова": "Немає слова",
        "Нет предложения": "Немає речення",
        "Перевод не получился, попробуй ещё раз": "Переклад не вдався, спробуй ще раз",
        "Неверный статус": "Неправильний статус",
        "Не найдено": "Не знайдено",
        "На сегодня лимит новых переводов исчерпан. Уже переведённые слова доступны, новые — завтра.": "Ліміт нових перекладів на сьогодні вичерпано. Уже перекладені слова доступні, нові — завтра.",
    },
    "en": {
        "Слишком много попыток. Подожди минуту и попробуй снова.": "Too many attempts. Wait a minute and try again.",
        "Почта пока не может отправить письмо на этот адрес. Владелец приложения должен подключить отправку писем.": "We can't send email to this address yet.",
        "Код неверный или устарел. Запроси новый.": "The code is wrong or expired. Request a new one.",
        "Не удалось отправить письмо": "Couldn't send the email",
        "Проверь адрес почты": "Check the email address",
        "Введи код из письма": "Enter the code from the email",
        "Код не подошёл": "That code didn't work",
        "Нет сессии": "Not signed in",
        "Сессия истекла, войди снова": "Your session expired, sign in again",
        "Нужно войти": "Please sign in",
        "Книга не найдена": "Book not found",
        "Эту книгу пока нельзя открыть.": "This book can't be opened yet.",
        "Не удалось скачать книгу с сайта университета": "Couldn't download the book from the university site",
        "Не получилось подготовить книгу. Попробуй другой уровень.": "Couldn't prepare the book. Try another level.",
        "Нет слова": "No word",
        "Нет предложения": "No sentence",
        "Перевод не получился, попробуй ещё раз": "Translation failed, please try again",
        "Неверный статус": "Invalid status",
        "Не найдено": "Not found",
        "На сегодня лимит новых переводов исчерпан. Уже переведённые слова доступны, новые — завтра.": "You've reached today's limit for new translations. Words already translated still work; new ones tomorrow.",
    },
}

TR_LANGS = {"ru": "Russian", "uk": "Ukrainian", "es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German",
            "pl": "Polish", "tr": "Turkish", "zh": "Simplified Chinese", "ja": "Japanese", "ko": "Korean",
            "vi": "Vietnamese", "tl": "Tagalog", "hi": "Hindi", "ar": "Arabic", "fa": "Persian", "it": "Italian",
            "ro": "Romanian", "kk": "Kazakh"}


def _ui_lang():
    lang = (request.headers.get("X-Lang") or "ru")[:2].lower()
    return lang if lang in MSG else "ru"


def tr(msg):
    table = MSG.get(_ui_lang(), {})
    if msg in table:
        return table[msg]
    # messages like "<reason>. Эту книгу пока нельзя открыть."
    for k, v in table.items():
        if k in msg:
            return msg.replace(k, v)
    return msg


def err(msg, code=400):
    return jsonify({"error": tr(msg)}), code


@app.get("/")
@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": MODEL, "storage": type(store).__name__})


# ---------- auth (proxied to Supabase Auth) ----------

def _supa_auth(method, path, **kw):
    headers = {"apikey": SUPA_KEY, "Content-Type": "application/json"}
    headers.update(kw.pop("headers", {}))
    return requests.request(method, f"{SUPA_URL}/auth/v1/{path}", headers=headers, timeout=20, **kw)


def _session_out(d):
    user = d.get("user") or {}
    return {"access_token": d.get("access_token"), "refresh_token": d.get("refresh_token"),
            "expires_at": d.get("expires_at") or int(time.time()) + int(d.get("expires_in", 3600)),
            "email": user.get("email")}


def _auth_error(r, default):
    try:
        d = r.json()
    except ValueError:
        d = {}
    msg = (d.get("msg") or d.get("error_description") or d.get("message") or "").lower()
    if r.status_code == 429 or "rate" in msg:
        return err("Слишком много попыток. Подожди минуту и попробуй снова.", 429)
    if "not authorized" in msg:
        return err("Почта пока не может отправить письмо на этот адрес. Владелец приложения должен подключить отправку писем.", 403)
    if "expired" in msg or "invalid" in msg:
        return err("Код неверный или устарел. Запроси новый.", 400)
    app.logger.warning("auth error %s: %s", r.status_code, d)
    return err(default, 400)


@app.post("/api/auth/send")
def auth_send():
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return err("Проверь адрес почты")
    r = _supa_auth("POST", "otp", params={"redirect_to": SITE_URL},
                   json={"email": email, "create_user": True})
    if r.status_code >= 400:
        return _auth_error(r, "Не удалось отправить письмо")
    return jsonify({"ok": True})


@app.post("/api/auth/verify")
def auth_verify():
    b = request.get_json(silent=True) or {}
    email = (b.get("email") or "").strip().lower()
    code = re.sub(r"\D", "", b.get("code") or "")
    if not EMAIL_RE.match(email) or not 6 <= len(code) <= 10:
        return err("Введи код из письма")
    r = _supa_auth("POST", "verify", json={"type": "email", "email": email, "token": code})
    if r.status_code >= 400:
        return _auth_error(r, "Код не подошёл")
    return jsonify(_session_out(r.json()))


@app.post("/api/auth/refresh")
def auth_refresh():
    rt = (request.get_json(silent=True) or {}).get("refresh_token") or ""
    if not rt:
        return err("Нет сессии", 401)
    r = _supa_auth("POST", "token", params={"grant_type": "refresh_token"}, json={"refresh_token": rt})
    if r.status_code >= 400:
        return err("Сессия истекла, войди снова", 401)
    return jsonify(_session_out(r.json()))


def _check_token(token):
    if token_check:
        return token_check(token)
    k = hashlib.sha256(token.encode()).hexdigest()
    hit = _token_cache.get(k)
    if hit and hit[0] > time.time():
        return hit[1]
    r = _supa_auth("GET", "user", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        return None
    u = r.json()
    user = {"id": u["id"], "email": u.get("email")}
    if len(_token_cache) > 5000:
        _token_cache.clear()
    _token_cache[k] = (time.time() + 300, user)
    return user


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        h = request.headers.get("Authorization", "")
        token = h[7:] if h.startswith("Bearer ") else ""
        user = _check_token(token) if token else None
        if not user:
            return err("Нужно войти", 401)
        g.uid = user["id"]
        return fn(*a, **kw)
    return wrapper


# ---------- books (public) ----------

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
    # also cleans pages cached before the print-header filter existed
    text = "\n\n".join(x.strip() for x in textproc.strip_print_junk(p["text"]).split("\n\n") if x.strip())
    return jsonify({"book_id": book_id, "level": level, "page": page, "total": total,
                    "title": p.get("title"), "text": text})


# ---------- translation (signed-in users, daily limit on new translations) ----------

WORD_PROMPT = """You help an adult learner (A2–B1) whose native language is {L} read English books.
Translate the word as it is used in THIS sentence. Answer with JSON only, no prose:
{{
 "word": the word as written,
 "lemma": dictionary form (e.g. "went" -> "go"),
 "pos": part of speech written in {L}, short,
 "ipa": IPA transcription of the lemma, American English, e.g. "/ɡoʊ/",
 "translation": 1–3 words in {L}, the meaning in this context,
 "other": up to 3 other common meanings in {L} (array, may be empty),
 "note": one short sentence in {L} about usage or grammar here (e.g. tense, why this form), or "",
 "phrase": if the word is part of a phrasal verb or idiom in this sentence: {{"text": "...", "translation": "... in {L}"}}, else null
}}"""

SENT_PROMPT = """Translate this English sentence into natural {L} for a learner.
Answer with JSON only: {{"translation": "...", "note": "one short note in {L} on a tricky grammar point, or empty"}}"""


def _tr_lang(body):
    lang = (body.get("lang") or "ru").lower()
    return lang if lang in TR_LANGS else "ru"

LIMIT_MSG = "На сегодня лимит новых переводов исчерпан. Уже переведённые слова доступны, новые — завтра."


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
@login_required
def translate():
    body = request.get_json(force=True, silent=True) or {}
    word = (body.get("word") or "").strip()
    sentence = (body.get("sentence") or "").strip()[:600]
    if not word or len(word) > 40:
        return err("Нет слова")
    lang = _tr_lang(body)
    key = _key("w1", word.lower(), sentence) if lang == "ru" else _key("w1", lang, word.lower(), sentence)
    cached = store.get_translation(key)
    if cached:
        return jsonify(cached)
    if not store.bump_usage(g.uid, DAILY_LIMIT):
        return err(LIMIT_MSG, 429)
    try:
        data = _parse_json(_claude(WORD_PROMPT.format(L=TR_LANGS[lang]), f"Word: {word}\nSentence: {sentence}"))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("translate failed: %s", e)
        return err("Перевод не получился, попробуй ещё раз", 502)
    data["word"] = word
    store.save_translation(key, word.lower(), data)
    return jsonify(data)


@app.post("/api/translate-sentence")
@login_required
def translate_sentence():
    body = request.get_json(force=True, silent=True) or {}
    sentence = (body.get("sentence") or "").strip()[:800]
    if not sentence:
        return err("Нет предложения")
    lang = _tr_lang(body)
    key = _key("s1", sentence) if lang == "ru" else _key("s1", lang, sentence)
    cached = store.get_translation(key)
    if cached:
        return jsonify(cached)
    if not store.bump_usage(g.uid, DAILY_LIMIT):
        return err(LIMIT_MSG, 429)
    try:
        data = _parse_json(_claude(SENT_PROMPT.format(L=TR_LANGS[lang]), sentence))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("sentence failed: %s", e)
        return err("Перевод не получился, попробуй ещё раз", 502)
    store.save_translation(key, sentence[:60], data)
    return jsonify(data)


# ---------- vocabulary (per user) ----------

@app.get("/api/vocab")
@login_required
def vocab_list():
    return jsonify(store.list_vocab(g.uid))


@app.post("/api/vocab")
@login_required
def vocab_add():
    body = request.get_json(force=True, silent=True) or {}
    word = (body.get("word") or "").strip().lower()
    if not word or len(word) > 40:
        return err("Нет слова")
    item = {k: body.get(k) for k in ("lemma", "translation", "ipa", "pos", "context", "status")}
    item["word"] = word
    if item.get("lemma"):
        item["lemma"] = item["lemma"].strip().lower()
    if item.get("context"):
        item["context"] = item["context"][:600]
    if item.get("status") not in (None, "learning", "known"):
        item["status"] = "learning"
    return jsonify(store.add_vocab(g.uid, item))


@app.patch("/api/vocab/<int:vid>")
@login_required
def vocab_update(vid):
    body = request.get_json(force=True, silent=True) or {}
    fields = {k: body[k] for k in ("status", "translation") if k in body}
    if fields.get("status") not in (None, "learning", "known"):
        return err("Неверный статус")
    if fields.get("status") == "learning":
        fields.update({"due_at": datetime.now(timezone.utc).isoformat()})
    v = store.update_vocab(g.uid, vid, fields)
    return jsonify(v) if v else err("Не найдено", 404)


@app.delete("/api/vocab/<int:vid>")
@login_required
def vocab_delete(vid):
    store.delete_vocab(g.uid, vid)
    return jsonify({"ok": True})


@app.get("/api/review/due")
@login_required
def review_due():
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify(store.due_vocab(g.uid, limit))


@app.post("/api/review/<int:vid>")
@login_required
def review_card(vid):
    body = request.get_json(force=True, silent=True) or {}
    grade = max(0, min(3, int(body.get("grade", 2))))
    card = store.get_vocab(g.uid, vid)
    if not card:
        return err("Не найдено", 404)
    return jsonify(store.update_vocab(g.uid, vid, srs.review(card, grade)))


# ---------- reading progress (per user) ----------

@app.get("/api/progress")
@login_required
def progress_list():
    return jsonify(store.list_progress(g.uid))


@app.post("/api/progress")
@login_required
def progress_save():
    b = request.get_json(force=True, silent=True) or {}
    if b.get("book_id") not in BOOKS_BY_ID:
        return err("Книга не найдена", 404)
    store.save_progress(g.uid, b["book_id"], int(b.get("level", 0)), int(b.get("page", 0)), b.get("total_pages"))
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
