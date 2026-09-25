"""In-memory CJK bigram BM25 over canon events, for the two-character words trigram FTS cannot match."""

from __future__ import annotations

import math
import re
from collections import Counter

_CJK = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'.-]*")


def terms(text: str, generic: frozenset[str] = frozenset()) -> list[str]:
    """CJK bigrams plus lowercased Latin words; bigrams made only of generic characters are dropped."""
    found = []
    for part in _CJK.findall(text):
        found += [part[i:i + 2] for i in range(len(part) - 1)
                  if not (part[i] in generic and part[i + 1] in generic)]
    found += [word.lower() for word in _WORD.findall(text)]
    return found


class BigramIndex:
    def __init__(self, documents: dict[str, str], *, k1: float = 1.2, b: float = 0.75) -> None:
        self.tf = {key: Counter(terms(text)) for key, text in documents.items()}
        self.length = {key: sum(counts.values()) for key, counts in self.tf.items()}
        self.average = sum(self.length.values()) / max(1, len(self.length))
        total = len(self.tf)
        frequency = Counter(term for counts in self.tf.values() for term in counts)
        self.idf = {term: math.log(1 + (total - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}
        self.postings: dict[str, list[str]] = {}
        for key, counts in self.tf.items():
            for term in counts:
                self.postings.setdefault(term, []).append(key)
        self.k1, self.b = k1, b

    def scores(self, query_terms: list[str]) -> dict[str, float]:
        result: dict[str, float] = {}
        for term in dict.fromkeys(query_terms):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for key in self.postings[term]:
                tf = self.tf[key][term]
                norm = self.k1 * (1 - self.b + self.b * self.length[key] / self.average)
                result[key] = result.get(key, 0.0) + idf * tf * (self.k1 + 1) / (tf + norm)
        return result

    def weight(self, text: str, query_terms: list[str]) -> float:
        """Sum of idf for query terms present in a short text, used to pick a matching beat."""
        return sum(self.idf.get(term, 0.0) for term in dict.fromkeys(query_terms) if term in text)
