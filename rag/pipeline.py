"""端到端问答管线：检索 → 组装 → 生成（或导出 prompt）。"""
import json
import time

from . import llm as llm_mod
from . import prompt as prompt_mod
from .config import FINAL_TOP_K
from .retriever import assess_relevance, build_retriever, route_layers

_retriever = None


def get_retriever(with_dense=True, rebuild=False):
    global _retriever
    if _retriever is None or rebuild:
        _retriever = build_retriever(rebuild=rebuild, with_dense=with_dense)
    return _retriever


def answer(query, top_k=FINAL_TOP_K, backend=None, history=None, with_dense=True,
           export_prompt=False, rebuild=False):
    """返回结构化结果。无 LLM 时 answer 字段为空，prompt 字段可直接拿去用。"""
    r = get_retriever(with_dense=with_dense, rebuild=rebuild)
    t0 = time.time()
    results, warnings, info = r.search(query, top_k=top_k, use_dense=with_dense, explain=True)
    retrieve_ms = int((time.time() - t0) * 1000)
    relevance = assess_relevance(results, query)

    out = {
        "query": query,
        "retrieval": {
            "layers": sorted(info["layers"]),
            "main_layers": sorted(info["main_layers"]),
            "reasons": info["reasons"],
            "route_codes": info.get("route_codes", []),
            "candidates": info["candidates"],
            "fused": info["fused"],
            "latency_ms": retrieve_ms,
            "dense": bool(with_dense and r.emb is not None),
            "rerank": bool(getattr(r, "_reranker_ok", False)),
            "relevant": relevance["relevant"],
            "relevance_reason": relevance["reason"],
        },
        "sources": [
            {
                "n": i,
                "layer": x["layer"],
                "rel_path": x["rel_path"],
                "m_code": x["m_code"],
                "e_code": x["e_code"],
                "section": x["section"],
                "status": x["status"],
                "doc_ids": x["doc_ids"],
                "score": x["score"],
                "chars": x["chars"],
                "text": x["text"],
            }
            for i, x in enumerate(results, start=1)
        ],
        "errata_warnings": [
            {
                "e_code": x["e_code"],
                "rel_path": x["rel_path"],
                "section": x["section"],
                "score": x["score"],
                "chars": x["chars"],
                "text": x["text"],
            }
            for x in warnings
        ],
        "answer": None,
        "prompt": None,
        "backend": backend or "none",
    }
    # 纠错层提示一并进 context：LLM 必须知道「这个说法已被勘误」
    messages = prompt_mod.build_messages(query, results, history, warnings)
    out["prompt"] = prompt_mod.build_prompt_text(query, results, warnings)
    out["messages"] = messages

    backend = backend or "none"
    if backend != "none" and not export_prompt:
        t1 = time.time()
        out["answer"] = llm_mod.generate(messages, backend=backend)
        out["generation_ms"] = int((time.time() - t1) * 1000)
        out["backend"] = backend
    return out
