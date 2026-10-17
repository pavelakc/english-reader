"""Storage: Supabase (PostgREST over HTTPS) in production, in-memory for local tests.

Book pages and the translation cache are shared by everyone;
vocabulary, reading progress and usage are per user (user_id = Supabase auth user id).
"""
import os
from datetime import date, datetime, timezone

import requests


def now_iso():
    return datetime.now(timezone.utc).isoformat()


VOCAB_FIELDS = ("word", "lemma", "translation", "ipa", "pos", "context", "status")
SRS_FIELDS = ("ease", "interval_days", "reps", "lapses", "due_at", "status", "translation")


class SupabaseStore:
    def __init__(self, url, key):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.s = requests.Session()
        self.s.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    def _req(self, method, table, params=None, json=None, prefer=None):
        headers = {"Prefer": prefer} if prefer else {}
        r = self.s.request(method, self.base + table, params=params, json=json, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json() if r.content else None

    # --- book pages (shared) ---
    def total_pages(self, book_id, level):
        rows = self._req("GET", "reader_book_pages", params={
            "select": "page", "book_id": f"eq.{book_id}", "level": f"eq.{level}",
            "order": "page.desc", "limit": 1})
        return rows[0]["page"] + 1 if rows else 0

    def get_page(self, book_id, level, page):
        rows = self._req("GET", "reader_book_pages", params={
            "select": "page,title,text", "book_id": f"eq.{book_id}", "level": f"eq.{level}",
            "page": f"eq.{page}"})
        return rows[0] if rows else None

    def save_pages(self, book_id, level, pages):
        rows = [{"book_id": book_id, "level": level, "page": p["page"], "title": p.get("title"), "text": p["text"]}
                for p in pages]
        for i in range(0, len(rows), 200):
            self._req("POST", "reader_book_pages", params={"on_conflict": "book_id,level,page"},
                      json=rows[i:i + 200], prefer="resolution=merge-duplicates,return=minimal")

    # --- translation cache (shared) ---
    def get_translation(self, key):
        rows = self._req("GET", "reader_translations", params={"select": "data", "cache_key": f"eq.{key}"})
        return rows[0]["data"] if rows else None

    def save_translation(self, key, word, data):
        self._req("POST", "reader_translations", params={"on_conflict": "cache_key"},
                  json={"cache_key": key, "word": word, "data": data},
                  prefer="resolution=merge-duplicates,return=minimal")

    # --- usage limit (per user) ---
    def bump_usage(self, uid, limit):
        return bool(self._req("POST", "rpc/reader_bump_usage", json={"p_user": uid, "p_limit": limit}))

    # --- vocab (per user) ---
    T_VOCAB = "reader_user_vocab"

    def list_vocab(self, uid):
        return self._req("GET", self.T_VOCAB, params={"select": "*", "user_id": f"eq.{uid}", "order": "created_at.desc"})

    def get_vocab(self, uid, vid):
        rows = self._req("GET", self.T_VOCAB, params={"select": "*", "id": f"eq.{vid}", "user_id": f"eq.{uid}"})
        return rows[0] if rows else None

    def add_vocab(self, uid, item):
        row = {k: item.get(k) for k in VOCAB_FIELDS if item.get(k) is not None}
        row.update(user_id=uid, updated_at=now_iso())
        rows = self._req("POST", self.T_VOCAB, params={"on_conflict": "user_id,word"}, json=row,
                         prefer="resolution=merge-duplicates,return=representation")
        return rows[0]

    def update_vocab(self, uid, vid, fields):
        fields = dict(fields, updated_at=now_iso())
        rows = self._req("PATCH", self.T_VOCAB, params={"id": f"eq.{vid}", "user_id": f"eq.{uid}"}, json=fields,
                         prefer="return=representation")
        return rows[0] if rows else None

    def delete_vocab(self, uid, vid):
        self._req("DELETE", self.T_VOCAB, params={"id": f"eq.{vid}", "user_id": f"eq.{uid}"})

    def due_vocab(self, uid, limit):
        return self._req("GET", self.T_VOCAB, params={
            "select": "*", "user_id": f"eq.{uid}", "status": "eq.learning", "due_at": f"lte.{now_iso()}",
            "order": "due_at.asc", "limit": limit})

    # --- progress (per user) ---
    T_PROG = "reader_user_progress"

    def list_progress(self, uid):
        return self._req("GET", self.T_PROG, params={"select": "*", "user_id": f"eq.{uid}", "order": "updated_at.desc"})

    def save_progress(self, uid, book_id, level, page, total_pages):
        self._req("POST", self.T_PROG, params={"on_conflict": "user_id,book_id,level"},
                  json={"user_id": uid, "book_id": book_id, "level": level, "page": page,
                        "total_pages": total_pages, "updated_at": now_iso()},
                  prefer="resolution=merge-duplicates,return=minimal")


class MemoryStore:
    """Same interface, kept in RAM. Used when SUPABASE_URL is not set (local testing)."""

    def __init__(self):
        self.pages, self.trans, self.vocab, self.progress, self.usage = {}, {}, {}, {}, {}
        self._id = 0

    def total_pages(self, book_id, level):
        return sum(1 for (b, l, _) in self.pages if b == book_id and l == level)

    def get_page(self, book_id, level, page):
        return self.pages.get((book_id, level, page))

    def save_pages(self, book_id, level, pages):
        for p in pages:
            self.pages[(book_id, level, p["page"])] = {"page": p["page"], "title": p.get("title"), "text": p["text"]}

    def get_translation(self, key):
        return self.trans.get(key)

    def save_translation(self, key, word, data):
        self.trans[key] = data

    def bump_usage(self, uid, limit):
        k = (uid, date.today())
        if self.usage.get(k, 0) >= limit:
            return False
        self.usage[k] = self.usage.get(k, 0) + 1
        return True

    def _mine(self, uid):
        return [v for v in self.vocab.values() if v["user_id"] == uid]

    def list_vocab(self, uid):
        return sorted(self._mine(uid), key=lambda v: v["created_at"], reverse=True)

    def get_vocab(self, uid, vid):
        v = self.vocab.get(int(vid))
        return v if v and v["user_id"] == uid else None

    def add_vocab(self, uid, item):
        for v in self._mine(uid):
            if v["word"] == item["word"]:
                v.update({k: item[k] for k in VOCAB_FIELDS if item.get(k) is not None})
                return v
        self._id += 1
        v = {"id": self._id, "user_id": uid, "status": "learning", "ease": 2.5, "interval_days": 0, "reps": 0,
             "lapses": 0, "due_at": now_iso(), "created_at": now_iso()}
        v.update({k: item.get(k) for k in VOCAB_FIELDS if item.get(k) is not None})
        self.vocab[self._id] = v
        return v

    def update_vocab(self, uid, vid, fields):
        v = self.get_vocab(uid, vid)
        if v:
            v.update(fields)
        return v

    def delete_vocab(self, uid, vid):
        if self.get_vocab(uid, vid):
            self.vocab.pop(int(vid), None)

    def due_vocab(self, uid, limit):
        n = now_iso()
        due = [v for v in self._mine(uid) if v["status"] == "learning" and v["due_at"] <= n]
        return sorted(due, key=lambda v: v["due_at"])[:limit]

    def list_progress(self, uid):
        return [p for (u, _, _), p in self.progress.items() if u == uid]

    def save_progress(self, uid, book_id, level, page, total_pages):
        self.progress[(uid, book_id, level)] = {"book_id": book_id, "level": level, "page": page,
                                                "total_pages": total_pages, "updated_at": now_iso()}


def make_store():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and key:
        return SupabaseStore(url, key)
    return MemoryStore()
