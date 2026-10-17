"""Turn a downloaded book (PDF / TXT / DOCX / ZIP) into clean paragraphs and reading pages."""
import io
import re
import zipfile

WORDS_PER_PAGE = 320


class NoTextError(Exception):
    """The file has no extractable text (e.g. a scanned PDF)."""


def extract_text(data: bytes, filename: str) -> str:
    """Detect the format by content (magic bytes), not by the URL's extension."""
    name = filename.lower()
    head = data[:1024].lstrip()
    if head[:5] == b"%PDF-" or data.find(b"%PDF-", 0, 1024) >= 0:
        try:
            return _from_pdf(data)
        except NoTextError:
            raise
        except Exception as e:  # damaged PDF
            raise NoTextError(f"Файл PDF повреждён ({type(e).__name__})") from e
    if data[:2] == b"PK":
        return _from_docx(data) if name.endswith(".docx") else _from_zip(data)
    if head[:15].lower().startswith((b"<!doctype html", b"<html")):
        raise NoTextError("Сайт вернул веб-страницу вместо файла книги")
    return _decode(data)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "ignore")


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n\n".join(pages)
    if len(re.findall(r"[A-Za-z]{2,}", text)) < 50:
        raise NoTextError("PDF без текстового слоя (скан)")
    return text


def _from_docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    return text


def _from_zip(data: bytes) -> str:
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted(n for n in z.namelist() if not n.endswith("/") and "__MACOSX" not in n)
        for n in names:
            low = n.lower()
            if low.endswith((".pdf", ".txt", ".docx")):
                try:
                    parts.append(extract_text(z.read(n), n))
                except NoTextError:
                    continue
    if not parts:
        raise NoTextError("В архиве нет читаемых файлов")
    return "\n\n".join(parts)


_PAGE_NUM = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.I)

# Browser print headers/footers that end up inside PDFs, e.g.
#   file:///C|/Users/x/Desktop/Alice%204000.txt[14/09/2012 3:06:04 p.m.]
#   https://example.com/book.html  3/45
#   14/09/2012 15:06   Alice in Wonderland
_PRINT_JUNK = [
    re.compile(r"(?:file|https?):/{2,3}\S*?(?:\[[^\]\n]{0,60}\]|(?=\s|$))(?:\s+\d{1,4}\s*/\s*\d{1,4})?", re.I),
    re.compile(r"\[\s*\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?\s*\]", re.I),
    re.compile(r"^\s*\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?\b.*$", re.I | re.M),
]


def strip_print_junk(text: str) -> str:
    for rx in _PRINT_JUNK:
        text = rx.sub(" ", text)
    return re.sub(r"[ \t]{2,}", " ", text)
_SENT_END = re.compile(r"[.!?:;\"'”’)\]]$")


def to_paragraphs(raw: str) -> list[str]:
    """Rebuild paragraphs from hard-wrapped text (PDF or TXT)."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace("­", "")
    raw = raw.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("\t", " ")
    raw = strip_print_junk(raw)
    lines = [ln.rstrip() for ln in raw.split("\n")]
    lines = [ln for ln in lines if not _PAGE_NUM.match(ln)]

    nonblank = [len(ln.strip()) for ln in lines if ln.strip()]
    if not nonblank:
        return []
    nonblank.sort()
    typical = nonblank[int(len(nonblank) * 0.8)] if len(nonblank) > 5 else max(nonblank)
    hard_wrapped = typical >= 40  # long lines everywhere means each paragraph is one line

    paras, cur = [], []

    def flush():
        if cur:
            p = " ".join(cur)
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                paras.append(p)
            cur.clear()

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            flush()
            continue
        if cur and cur[-1].endswith("-") and s[:1].islower():
            cur[-1] = cur[-1][:-1] + s  # re-join hyphenated word
            continue
        # headings ("CHAPTER 2", "Part One") stand alone
        if _is_heading(s) and not _SENT_END.search(s):
            flush()
            cur.append(s)
            flush()
            continue
        # indented line in a wrapped text usually starts a new paragraph
        if cur and hard_wrapped and ln.startswith(("   ", "　")):
            flush()
        cur.append(s)
        # short line ending a sentence → end of paragraph
        if hard_wrapped and len(s) < typical * 0.7 and _SENT_END.search(s):
            flush()
    flush()

    # merge fragments that clearly continue the previous paragraph
    merged = []
    for p in paras:
        if merged and merged[-1][-1:] not in ".!?:\"”’'" and p[:1].islower():
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def _is_heading(p: str) -> bool:
    if len(p) > 70 or len(p.split()) > 10:
        return False
    if re.match(r"^(chapter|part|book|section|story)\b", p, re.I):
        return True
    letters = [c for c in p if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def to_pages(paragraphs: list[str], words_per_page: int = WORDS_PER_PAGE) -> list[dict]:
    """Group paragraphs into pages of roughly words_per_page words; start a new page at headings."""
    pages, cur, count, heading = [], [], 0, None

    def flush():
        nonlocal cur, count
        if cur:
            pages.append({"title": heading, "text": "\n\n".join(cur)})
        cur, count = [], 0

    for p in paragraphs:
        n = len(p.split())
        if _is_heading(p):
            if count > words_per_page * 0.3:
                flush()
            heading = p.title() if p.isupper() else p
            cur.append(p)
            count += n
            continue
        if count and count + n > words_per_page * 1.25:
            flush()
        if n > words_per_page * 1.5:
            # very long paragraph: split by sentences
            sents = re.split(r"(?<=[.!?])\s+", p)
            chunk = []
            for s in sents:
                chunk.append(s)
                if sum(len(x.split()) for x in chunk) >= words_per_page:
                    cur.append(" ".join(chunk))
                    flush()
                    chunk = []
            if chunk:
                cur.append(" ".join(chunk))
                count += sum(len(x.split()) for x in chunk)
            continue
        cur.append(p)
        count += n
    flush()
    for i, pg in enumerate(pages):
        pg["page"] = i
    return pages
