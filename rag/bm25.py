"""Okapi BM25（无外部依赖）。"""
import math
from collections import Counter


class BM25:
    def __init__(self, corpus_tokens, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = corpus_tokens
        self.n = len(corpus_tokens)
        self.doc_len = [len(d) for d in corpus_tokens]
        self.avgdl = sum(self.doc_len) / self.n if self.n else 0.0
        self.tf = [Counter(d) for d in corpus_tokens]
        df = Counter()
        for d in corpus_tokens:
            for t in set(d):
                df[t] += 1
        self.idf = {
            t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()
        }

    def score(self, query_tokens, index):
        if index >= self.n:
            return 0.0
        tf = self.tf[index]
        dl = self.doc_len[index] or 1
        s = 0.0
        for t in query_tokens:
            f = tf.get(t, 0)
            if not f:
                continue
            idf = self.idf.get(t, 0.0)
            s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s

    def top_k(self, query_tokens, k, candidate_idx=None):
        q = Counter(query_tokens)
        idxs = range(self.n) if candidate_idx is None else candidate_idx
        scored = [(self.score(list(q.elements()), i), i) for i in idxs]
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(i, s) for s, i in scored[:k] if s > 0]
