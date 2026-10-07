"""Moirai-owned keyword terms for Chinese and mixed text: CJK pairs, single CJK characters, Latin words.

SQLite's unicode61 tokenizer treats a whole run of Chinese characters as one
token, so events and queries are split here and stored as space-separated terms.
Pairs keep two-character words such as 龙门 matchable; single characters keep
one-character names such as 陈 matchable when the neighbouring characters
differ between a question and a memory. Both halves go to separate columns so
their weights can be tuned without re-indexing.
"""
from __future__ import annotations

TOKENIZER_ID = "cjk-pairs+chars-v1"
MAX_QUERY_TERMS = 48

_FUNCTION_CHARS = frozenset(
    "的了是在和与及或吗呢吧啊呀么什为怎样如何哪谁这那个我你他她它们就都也还又很被把对向从给让各否些所以而且但并着过得地之其"
)
_SUMMARY_MARKERS = ("[What]", "[Who]", "[How]", "[Eval]")


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def _runs(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_cjk, run) pieces; separators and punctuation are dropped."""
    runs: list[tuple[bool, str]] = []
    current: list[str] = []
    current_cjk = False
    for ch in text:
        cjk = is_cjk(ch)
        word = cjk or ch.isalnum()
        if word and current and cjk == current_cjk:
            current.append(ch)
            continue
        if current:
            runs.append((current_cjk, "".join(current)))
            current = []
        if word:
            current = [ch]
            current_cjk = cjk
    if current:
        runs.append((current_cjk, "".join(current)))
    return runs


def split_terms(text: str) -> tuple[list[str], list[str]]:
    """Return (pairs and Latin words, single CJK characters) in reading order."""
    words: list[str] = []
    chars: list[str] = []
    for cjk, run in _runs(text or ""):
        if not cjk:
            words.append(run.lower())
            continue
        chars.extend(run)
        if len(run) == 1:
            words.append(run)
        else:
            words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words, chars


def event_search_text(topic: str, tags: list[str], summary: str) -> str:
    text = " ".join([topic or "", " ".join(tags or []), summary or ""])
    for marker in _SUMMARY_MARKERS:
        text = text.replace(marker, " ")
    return text


def index_columns(topic: str, tags: list[str], summary: str) -> tuple[str, str]:
    """Values for events.search_words and events.search_chars."""
    words, chars = split_terms(event_search_text(topic, tags, summary))
    return " ".join(words), " ".join(chars)


def _is_function_only(term: str) -> bool:
    cjk = [ch for ch in term if is_cjk(ch)]
    return bool(cjk) and len(cjk) == len(term) and all(ch in _FUNCTION_CHARS for ch in cjk)


def query_terms(text: str) -> tuple[list[str], list[str]]:
    """Deduplicated query terms without function-character noise, capped at MAX_QUERY_TERMS."""
    words, chars = split_terms(text)
    kept_words = list(dict.fromkeys(t for t in words if not _is_function_only(t)))
    kept_chars = list(dict.fromkeys(t for t in chars if not _is_function_only(t)))
    kept_words = kept_words[:MAX_QUERY_TERMS]
    kept_chars = kept_chars[:max(0, MAX_QUERY_TERMS - len(kept_words))]
    return kept_words, kept_chars


def _quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def fts_match(text: str) -> str:
    """FTS5 MATCH expression over search_words and search_chars; empty when nothing is searchable."""
    words, chars = query_terms(text)
    parts = [f"search_words : {_quote(t)}" for t in words]
    parts += [f"search_chars : {_quote(t)}" for t in chars]
    return " OR ".join(parts)
