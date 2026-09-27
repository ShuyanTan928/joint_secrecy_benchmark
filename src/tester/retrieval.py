"""Okapi BM25 over the mailbox, for the search and expand tools. Standard library and numpy only."""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

WORD = re.compile(r"[a-z0-9]{2,}")
STOP = set(
    "a an the of to in for on with by from is are was were be been this that these those "
    "it its as at and or we you they he she his her their our your i not have has had will "
    "would can could should may might must do does did about into over under after before "
    "while which who whom whose what when where why how them then than out up down off no "
    "any all some more most other such only own same but if because so very also just we'll "
    "re fw fwd please thanks thank you let know need want get got would like".split()
)


def tokenize(text: str) -> list[str]:
    return [w for w in WORD.findall((text or "").lower()) if w not in STOP]


class BM25:
    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.doc_len = np.array([len(d) for d in docs_tokens], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if self.N else 0.0
        self.tf = [Counter(d) for d in docs_tokens]
        df: Counter = Counter()
        for d in docs_tokens:
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        s = np.zeros(self.N, dtype=float)
        denom = self.k1 * (1 - self.b + self.b * self.doc_len / (self.avgdl or 1.0))
        for t in set(query_tokens):
            idf = self.idf.get(t)
            if idf is None:
                continue
            f = np.array([tf.get(t, 0) for tf in self.tf], dtype=float)
            s += idf * (f * (self.k1 + 1)) / (f + denom)
        return s
