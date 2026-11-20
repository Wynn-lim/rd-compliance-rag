"""分层混合检索：意图路由 → BM25 + 向量 → RRF 融合 → 重排。

对应施工规格 §3.3 的四层检索与知识库使用提示词 §2.2 的强制检索顺序。
"""
import os
import re

from .bm25 import BM25
from .config import (
    BM25_TOP_K,
    DENSE_MODEL,
    DENSE_TOP_K,
    ERRATA_MIN_SIM,
    ERRATA_TOP_K,
    ERRATA_TOP_N,
    FINAL_TOP_K,
    FUSED_TOP_K,
    RERANK_CANDIDATES,
    RRF_K,
)
from .dense import cosine_top_k, encode, get_encoder
from .metadata import extract_doc_ids, extract_e_codes, extract_m_codes
from .tokenizer import bigrams, tokenize

# ---- 意图 → 层 ----
# 纠错层（勘误/铁律/检查项）**始终参与检索**：它的职责是防止「被勘误的说法」被当成
# 结论输出。合规知识库里，漏掉它的代价远大于多召回几块的代价。
TEMPORAL_RE = re.compile(
    r"还有效|有效吗|生效|废止|废了|过期|到期|时效|现行|现在还能|最新|是否仍然|取消了|失效|延至|截止"
)
ERRATA_BOOST_RE = re.compile(
    r"对不对|真的吗|是真的|是否真实|误区|传言|听说|据说|谣传|误传|谣言|辟谣|更正|勘误|是不是错|"
    r"错在哪|铁律|怎么自查|检查项|常见错误|以讹传讹|能不能整体引用|是否已|已提高到|提至|提高到"
)
METHOD_RE = re.compile(r"五口径|五个口径|五链|方法论|怎么查库|检索顺序|怎么使用")
DOC_ID_RE = re.compile(
    r"(?:〔\s*\d{4}\s*〕\s*\d+\s*号)|(?:(?:公告|令|函)\s*\d{4}\s*年\s*第\s*\d+\s*号)"
)

LAYER_WEIGHT = {"route": 1.06, "ledger": 1.04, "errata": 1.02, "knowledge": 1.0, "method": 0.9, "log": 0.6}


def route_layers(query):
    """返回该问题应检索的层（含权重来源说明）。"""
    layers = {"route": 1.0, "knowledge": 1.0, "errata": 1.0}
    reasons = ["默认：路由层定位模块 + 知识层正文 + 纠错层（防污染，常驻）"]
    if ERRATA_BOOST_RE.search(query):
        layers["errata"] = 1.35
        reasons.append("问题像「某说法对不对」→ 纠错层加权")
    if TEMPORAL_RE.search(query):
        layers["ledger"] = 1.0
        reasons.append("涉及时效/生效判定 → 台账层")
    if METHOD_RE.search(query):
        layers["method"] = 1.0
        reasons.append("涉及方法论 → 治理层")
    if DOC_ID_RE.search(query):
        layers["ledger"] = 1.0
        reasons.append("问题含政策文号 → 台账层核时效")
    if extract_e_codes(query):
        reasons.append("问题含 E 编号 → 纠错层定向")
    if extract_m_codes(query):
        reasons.append("问题含 M 编号 → 知识层定向加权")
    return layers, reasons


DENSE_RELEVANCE_THRESHOLD = float(os.environ.get("RAG_DENSE_THRESHOLD", "0.62"))
BM25_RELEVANCE_THRESHOLD = float(os.environ.get("RAG_BM25_THRESHOLD", "12.0"))
ENTITY_COVERAGE_MIN = float(os.environ.get("RAG_COVERAGE_MIN", "0.5"))


def _distinctive_tokens(query):
    """问句里的「专有实体」候选：长度 ≥3 的词，或含拉丁字母/数字的词。"""
    out = []
    for t in tokenize(query):
        if len(t) >= 3 or re.search(r"[A-Za-z0-9]", t):
            out.append(t.lower())
    return out


def assess_relevance(results, query=""):
    """判断检索结果是否足够相关，用于「库内暂无」判定。

    三道门，全部通过才算相关：
      1. 向量余弦 ≥ 阈值（bge 系实测：库内问题 0.63+，库外 0.60 以下）；
      2. 或 BM25 关键词强命中（问句含文号/M 编号时即使语义分低也算相关）；
      3. 实体覆盖：问句里的专有实体（如「澳大利亚」「R&D Tax Incentive」）
         必须有一部分出现在检索结果里——否则说明问的是库外事物。
    """
    if not results:
        return {"relevant": False, "reason": "未检索到任何内容",
                "top_dense_sim": 0.0, "entity_coverage": 0.0}

    top = results[0]
    d, b = top["dense_sim"], top["bm25_score"]
    ctx = re.sub(r"\s+", "", " ".join(r["text"] for r in results[:3])).lower()
    toks = _distinctive_tokens(query)
    cov = (sum(1 for t in toks if t in ctx) / len(toks)) if toks else 1.0

    base = {"top_dense_sim": d, "top_bm25": b, "entity_coverage": round(cov, 3)}
    if cov < ENTITY_COVERAGE_MIN:
        return {**base, "relevant": False,
                "reason": f"问句专有实体在库内覆盖率仅 {cov:.0%}（<{ENTITY_COVERAGE_MIN:.0%}）→ 判为库内暂无"}
    if d >= DENSE_RELEVANCE_THRESHOLD:
        return {**base, "relevant": True,
                "reason": f"向量相似度 {d} ≥ {DENSE_RELEVANCE_THRESHOLD}"}
    if b >= BM25_RELEVANCE_THRESHOLD:
        return {**base, "relevant": True,
                "reason": f"BM25 得分 {b} ≥ {BM25_RELEVANCE_THRESHOLD}（关键词强命中）"}
    return {**base, "relevant": False,
            "reason": f"最高相似度 {d}、BM25 {b}，均低于阈值 → 判为库内暂无"}


class Retriever:
    def __init__(self, chunks, tokens, embeddings=None, model_name=DENSE_MODEL,
                 use_rerank=True):
        self.chunks = chunks
        self.tokens = tokens
        self.bm25 = BM25(tokens)
        self.emb = embeddings
        self.model_name = model_name
        self._model = None
        self._reranker = None
        self.use_rerank = use_rerank
        self.layer_index = {}
        for i, c in enumerate(chunks):
            self.layer_index.setdefault(c["layer"], []).append(i)
        self._reranker_ok = self._probe_reranker()

    def _probe_reranker(self):
        """探测重排模型是否已在本地缓存（不触发下载）；没有则静默降级。"""
        if not self.use_rerank:
            return False
        try:
            from .rerank import reranker_available

            return reranker_available()
        except Exception:
            return False

    @property
    def model(self):
        if self._model is None:
            self._model = get_encoder(self.model_name)
        return self._model

    def _query_vec(self, query):
        return encode(self.model, query, normalize=True)[0]

    # ---- 融合 ----
    def _rrf(self, ranked_lists, weights=None):
        """ranked_lists: [(layer, [(idx, score), ...]), ...]"""
        scores = {}
        for layer, lst in ranked_lists:
            w = (weights or {}).get(layer, 1.0)
            for rank, (idx, _s) in enumerate(lst, start=1):
                scores[idx] = scores.get(idx, 0.0) + w * (1.0 / (RRF_K + rank))
        return scores

    def search(self, query, top_k=FINAL_TOP_K, use_dense=True, layers=None, explain=False,
               use_rerank=True):
        """返回 (主结果, 纠错层附加提示)。

        纠错层默认单独返回、不与正文抢名额——它的职责是防止「被勘误的说法」被当成
        结论输出；问题本身就在问勘误/铁律/检查项时，才并入主结果。
        """
        layers, reasons = route_layers(query)
        q_tokens = bigrams(tokenize(query))

        errata_primary = bool(re.search(r"铁律|检查项|勘误|常见错误", query)) or bool(
            extract_e_codes(query)
        )
        main_layers = {k: v for k, v in layers.items() if k != "errata"}
        if errata_primary:
            main_layers["errata"] = layers["errata"]

        cand = [i for layer, idxs in self.layer_index.items() if layer in main_layers for i in idxs]
        ranked = [("bm25", self.bm25.top_k(q_tokens, BM25_TOP_K, cand))]
        qv = None
        if use_dense and self.emb is not None:
            qv = self._query_vec(query)
            ranked.append(("dense", cosine_top_k(qv, self.emb, DENSE_TOP_K, cand)))

        raw = {}
        for name, lst in ranked:
            for idx, s in lst:
                raw.setdefault(idx, {})[name] = s

        fused = self._rrf([(l, lst) for l, lst in ranked])
        top = sorted(fused.items(), key=lambda x: -x[1])[:FUSED_TOP_K]
        route_codes = self._route_codes(top, main_layers)
        results = [self._decorate(i, s, query, main_layers, raw.get(i, {})) for i, s in top]
        results = self._rerank(results, query, route_codes)
        if use_rerank and self._reranker_ok:
            results = self._cross_rerank(query, results[:RERANK_CANDIDATES]) + results[RERANK_CANDIDATES:]
        out = results[:top_k]

        warnings = []
        if not errata_primary and "errata" in self.layer_index:
            ecand = self.layer_index["errata"]
            eranked = [("bm25", self.bm25.top_k(q_tokens, ERRATA_TOP_K, ecand))]
            if qv is not None:
                eranked.append(("dense", cosine_top_k(qv, self.emb, ERRATA_TOP_K, ecand)))
            eraw = {}
            for name, lst in eranked:
                for idx, s in lst:
                    eraw.setdefault(idx, {})[name] = s
            efused = self._rrf([(l, lst) for l, lst in eranked])
            for idx, s in sorted(efused.items(), key=lambda x: -x[1])[:ERRATA_TOP_K]:
                r = self._decorate(idx, s, query, {"errata": 1.0}, eraw.get(idx, {}))
                if r["dense_sim"] >= ERRATA_MIN_SIM or r["bm25_score"] >= BM25_RELEVANCE_THRESHOLD:
                    warnings.append(r)
            warnings = self._rerank(warnings, query, set())[:ERRATA_TOP_N]

        if explain:
            return out, warnings, {
                "layers": sorted(layers),
                "main_layers": sorted(main_layers),
                "reasons": reasons,
                "candidates": len(cand),
                "fused": len(fused),
                "route_codes": sorted(route_codes),
                "errata_primary": errata_primary,
            }
        return out, warnings

    def _route_codes(self, top, layers):
        """取融合后排名最前的路由层块，解析其中出现的 M 编号。"""
        if "route" not in layers:
            return set()
        codes = set()
        route_rank = sorted(
            ((s, i) for i, s in top if self.chunks[i]["layer"] == "route"),
            key=lambda x: -x[0],
        )
        for _s, i in route_rank[:4]:
            codes.update(extract_m_codes(self.chunks[i]["text"]))
        return codes

    def _decorate(self, idx, score, query, layers, raw=None):
        c = self.chunks[idx]
        raw = raw or {}
        return {
            "idx": idx,
            "score": round(float(score), 6),
            "bm25_score": round(float(raw.get("bm25", 0.0)), 3),
            "dense_sim": round(float(raw.get("dense", 0.0)), 4),
            "layer": c["layer"],
            "rel_path": c["rel_path"],
            "section": c["section"],
            "subsection": c["subsection"],
            "m_code": c["m_code"],
            "e_code": c["e_code"],
            "status": c["status"],
            "doc_ids": c["doc_ids"],
            "chars": c["chars"],
            "text": c["text"],
        }

    def _cross_rerank(self, query, results):
        """交叉编码器重排：与原分数加权融合（保留层权重与精确命中加成）。"""
        try:
            from .rerank import get_reranker, rerank
        except Exception:
            return results
        try:
            model = get_reranker()
            scores = rerank(model, query, [r["text"] for r in results])
        except Exception:
            return results
        if not scores:
            return results
        lo, hi = min(scores), max(scores)
        span = (hi - lo) or 1.0
        out = []
        for r, s in zip(results, scores):
            r = dict(r)
            r["cross_score"] = round(s, 4)
            # 归一化到 0~1 后与既有分数相加，避免量纲压倒层权重
            r["score"] = round(r["score"] + (s - lo) / span, 6)
            out.append(r)
        out.sort(key=lambda x: -x["score"])
        return out

    # ---- 重排：层权重 + 文号/M编号精确命中 + 状态 + 长度 ----
    def _rerank(self, results, query, route_codes=None):
        route_codes = route_codes or set()
        q_docs = set(extract_doc_ids(query))
        q_ms = set(extract_m_codes(query))
        q_es = set(extract_e_codes(query))
        out = []
        for r in results:
            bonus = 0.0
            if q_docs:
                bonus += 0.05 * len(q_docs & set(r["doc_ids"]))
            if q_ms and r["m_code"] in q_ms:
                bonus += 0.12
            if q_es and r["e_code"] in q_es:
                bonus += 0.12
            if r["m_code"] and r["m_code"] in route_codes:
                bonus += 0.05
            # 纠错层里 `## E-xxx` 块是权威勘误记录，`## 第 N 篇` 是过程笔记，
            # 前者应优先作为「这个说法已被勘误」的凭据
            if r["layer"] == "errata" and r["e_code"]:
                bonus += 0.04
            if r["status"] in ("L3", "L4"):
                bonus += 0.015
            if r["layer"] == "log":
                bonus -= 0.05
            if r["chars"] < 120:
                bonus -= 0.02
            r = dict(r)
            r["score"] = round(r["score"] * LAYER_WEIGHT.get(r["layer"], 1.0) + bonus, 6)
            out.append(r)
        out.sort(key=lambda x: -x["score"])
        return out


def build_retriever(rebuild=False, with_dense=True):
    from .store import build_or_load_chunks, build_tokens, load_embeddings, load_tokens, save_tokens

    chunks = build_or_load_chunks(rebuild=rebuild)
    try:
        tokens = load_tokens()
        if len(tokens) != len(chunks):
            raise ValueError("token 数与 chunk 数不一致，重建")
    except Exception:
        tokens = build_tokens(chunks)
        save_tokens(tokens)
    emb = None
    if with_dense:
        try:
            emb = load_embeddings()
            if len(emb) != len(chunks):
                raise ValueError("embedding 数与 chunk 数不一致，重建")
        except Exception:
            emb = None
    return Retriever(chunks, tokens, emb)
