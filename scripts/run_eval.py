"""评测：四指标（交接文档 §6.4 的建议方案）。

    检索命中率 / 出处正确率 / 口径不混与抗污染 / 拒答准确率

用法：
    python -I scripts/run_eval.py
    RAG_DENSE_MODEL=BAAI/bge-small-zh-v1.5 python -I scripts/run_eval.py --top-k 6
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag.pipeline import get_retriever  # noqa: E402
from rag.retriever import assess_relevance  # noqa: E402

# ---- 基线 10 题（逐字摘自 05_评测/基线题库_10题.md）----
BASELINE = [
    {"id": "Q1", "q": "研发费用加计扣除现在的比例是多少？未形成无形资产、形成无形资产分别怎么处理？",
     "expect_m": ["M07-01", "M07-01-01"], "expect_doc": ["2023 年第 7 号"],
     "must_contain": ["100%", "200%"]},
    {"id": "Q2", "q": "集成电路和工业母机企业的加计扣除比例是多少？到什么时候？",
     "expect_m": ["M07-01", "M07-01-01"], "expect_doc": ["2023 年第 44 号"],
     "must_contain": ["120%", "220%", "2027-12-31"]},
    {"id": "Q3", "q": "委托境内研发的加计基数是多少？委托境外呢？",
     "expect_m": ["M06-14", "M06-13", "M06-05-01"], "expect_doc": ["〔2018〕64"],
     "must_contain": ["80%"]},
    {"id": "Q4", "q": "高企认定研发费用占销售收入比例分几档？",
     "expect_m": ["M07-02", "M07-08"], "expect_doc": ["〔2016〕32"],
     "must_contain": ["5%", "4%", "3%"]},
    {"id": "Q5", "q": "高企科技人员占比和工时的要求？",
     "expect_m": ["M07-02", "M02-01", "M05-02", "M06-03"], "expect_doc": [],
     "must_contain": ["10%", "183"]},
    {"id": "Q6", "q": "研发支出资本化的五个条件是什么？",
     "expect_m": ["M06-07", "M06-07-01"], "expect_doc": [],
     "must_contain": ["技术可行", "意图", "资源", "计量"]},
    {"id": "Q7", "q": "委托研发的「知识产权归属」是不是加计扣除的门槛？",
     "expect_m": ["M06-14"], "expect_doc": [],
     "must_contain": ["假闸", "不是"]},
    {"id": "Q8", "q": "研发费用加计扣除有没有「金额门槛」？",
     "expect_m": ["M07-11", "M07-01", "M10-07"], "expect_doc": [],
     "must_contain": ["没有"]},
    {"id": "Q9", "q": "「集中研发」的加计条文在哪里？",
     "expect_m": ["M06-12"], "expect_doc": ["〔2015〕119"],
     "must_contain": ["119"]},
    {"id": "Q10", "q": "加计扣除的行业负面清单有哪些？",
     "expect_m": ["M04-02"], "expect_doc": ["〔2015〕119"],
     "must_contain": ["烟草", "住宿餐饮", "批发零售"]},
]

# ---- badcase 5 例（反向检测）----
BADCASE = [
    {"id": "BC-01", "q": "2026 年制造业企业研发费用加计扣除比例是不是已提高到 120%？",
     "expect_e": "E-002", "wrong_tokens": ["制造业", "120%"],
     "must_contain": ["无文号", "100%"]},
    {"id": "BC-02", "q": "新版《高新技术企业认定管理办法》是否已发布？发明专利权重是否提到 45%～50%？",
     "expect_e": "E-003", "wrong_tokens": ["45%", "50%"],
     "must_contain": ["未印发", "32"]},
    {"id": "BC-03", "q": "国家税务总局公告 2015 年第 97 号现在还有效吗？能不能整体引用？",
     "expect_e": "E-004", "wrong_tokens": [],
     "must_contain": ["部分有效"]},
    {"id": "BC-04", "q": "研发费用监管有哪几个口径？",
     "expect_e": "E-005", "wrong_tokens": [],
     "must_contain": ["统计"]},
    {"id": "BC-05", "q": "2026 年度高企申报现在还能报吗？",
     "expect_e": "E-806", "wrong_tokens": [],
     "must_contain": ["贵州", "厦门"]},
]

# ---- 拒答测试：库内确定没有的内容 ----
OOD = [
    "澳大利亚研发税收激励 R&D Tax Incentive 的可返还比例是多少？",
    "美国 IRS Section 41 研发税收抵免的抵免率怎么算？",
    "日本研究開發税制的税額控除率是多少？",
]


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def run(top_k=6, use_dense=True, verbose=True):
    r = get_retriever(with_dense=use_dense)
    report = {"top_k": top_k, "dense": bool(use_dense and r.emb is not None), "model": r.model_name}

    # 1) 检索命中率 + 2) 出处正确率
    hits, src_ok = [], []
    for item in BASELINE:
        res, warns, info = r.search(item["q"], top_k=top_k, use_dense=use_dense, explain=True)
        codes = [x["m_code"] for x in res if x["m_code"]]
        hit = any(e in codes for e in item["expect_m"])
        hits.append(hit)
        ctx = _norm(" ".join(x["text"] for x in res))
        missing = [t for t in item["must_contain"] if _norm(t) not in ctx]
        doc_ok = True
        if item["expect_doc"]:
            doc_ok = any(_norm(d) in ctx for d in item["expect_doc"])
        src_ok.append(not missing and doc_ok)
        if verbose:
            print(f"  {item['id']} 检索{'✓' if hit else '✗'} 出处{'✓' if (not missing and doc_ok) else '✗'}"
                  f" 层={sorted(info['layers'])}")
            if missing:
                print(f"       缺关键内容: {missing}")
            print(f"       命中条目: {[c for c in codes[:5]]}")
    report["retrieval_hit_rate"] = f"{sum(hits)}/{len(hits)}"
    report["source_correct_rate"] = f"{sum(src_ok)}/{len(src_ok)}"

    # 3) 抗污染：纠错层是否被检索到
    anti = []
    for item in BADCASE:
        res, warns, info = r.search(item["q"], top_k=top_k, use_dense=use_dense, explain=True)
        e_codes = [x["e_code"] for x in (res + warns) if x["e_code"]]
        got = item["expect_e"] in e_codes
        # 纠错层的结论就在 warns 里，内容检查必须把它算进去
        ctx = _norm(" ".join(x["text"] for x in (res + warns)))
        missing = [t for t in item["must_contain"] if _norm(t) not in ctx]
        anti.append(got and not missing)
        if verbose:
            print(f"  {item['id']} 纠错层{'✓' if got else '✗'} 内容{'✓' if not missing else '✗'}"
                  f" 层={sorted(info['layers'])}")
            if not got:
                print(f"       未命中 {item['expect_e']}，实际 E 编号: {[c for c in e_codes if c][:5]}")
            if missing:
                print(f"       缺关键内容: {missing}")
    report["errata_recall"] = f"{sum(anti)}/{len(anti)}"

    # 4) 拒答准确率：库外问题，最高分应显著低于基线
    ood_judged = []
    for q in OOD:
        res, _w, _i = r.search(q, top_k=top_k, use_dense=use_dense, explain=True)
        j = assess_relevance(res, q)
        ood_judged.append(j["relevant"])
        if verbose:
            print(f"  库外题：相关={j['relevant']}｜{j['reason']}")
    report["ood_rejection"] = f"{sum(1 for x in ood_judged if not x)}/{len(ood_judged)}"
    report["rejection_ok"] = all(not x for x in ood_judged)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    rep = run(top_k=args.top_k, use_dense=not args.no_dense)
    rep["elapsed_s"] = round(time.time() - t0, 1)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("\n=== 汇总 ===")
        for k, v in rep.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
