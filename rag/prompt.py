"""系统提示词与上下文组装。

蓝本：知识库 `00_总纲/05_知识库使用提示词.md`（施工规格 Step 4）。
该文件是知识库资产，只读取、不改写。
"""
import json
from pathlib import Path

from .config import KB_ROOT, LAYER_LABEL

SYSTEM_PROMPT_FILE = KB_ROOT / "00_总纲" / "05_知识库使用提示词.md"

OUTPUT_CONTRACT = """

---

# 本轮问答的执行约束（由检索系统注入）

你上方刚刚收到了「检索到的知识库片段」。它们是**唯一可用的依据**。按以下要求作答：

## 输出格式（严格遵守）

1. **结论先行**：第一句就是判断，不许铺垫。
2. **分口径**：涉及费用、金额、比例、条件时，按「会计核算／加计扣除／高企认定／IPO 监管／R&D 统计」分开表述；未涉及的口径不要硬凑。
3. **结构化**：费用类别、范围、差异用表格；流程用分步清单；金额与比例给计算过程。
4. **每条结论后紧跟出处**，格式：
   - 条目：`（M06-15 §三）`
   - 勘误：`（E-002）`
   - 政策：`（财税〔2015〕119 号 一、2；台账核实于 2026-10-30）`
5. **区分效力层级**：规则（L-A）／解释（L-B）／判例（L-C）要写明，判例只能作演示。
6. **只用片段里出现的内容**。片段中没有的，写「库内暂无」，并说明缺什么、建议查哪里。**绝不编造条号、比例、文号、案例。**
7. 结尾若触及具体税务申报、金额认定、资质结论，加一句：「以上为方法指引与风险提示，最终以主管税务机关或专业机构意见为准。」
"""


def load_system_prompt():
    if SYSTEM_PROMPT_FILE.exists():
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    return "你是研发费用归集与税务合规助手，回答全部以研发合规知识库为唯一依据。"


def format_context(results, warnings=None):
    """把检索结果组装成带层标签的上下文块。"""
    parts = []
    for i, r in enumerate(results, start=1):
        head = (
            f"【片段 {i}】层：{LAYER_LABEL.get(r['layer'], r['layer'])}"
            f"｜文件：{r['rel_path']}"
        )
        if r.get("m_code"):
            head += f"｜M 编号：{r['m_code']}"
        if r.get("e_code"):
            head += f"｜E 编号：{r['e_code']}"
        if r.get("status"):
            head += f"｜状态：{r['status']}"
        if r.get("section"):
            head += f"｜节：{r['section']}"
        if r.get("doc_ids"):
            head += f"｜文中出现的文号：{'、'.join(r['doc_ids'][:6])}"
        parts.append(head + "\n" + r["text"])

    if warnings:
        parts.append(
            "【纠错层 · 防污染提示】以下是知识库中与本题相关的勘误记录。"
            "它们记录的是「某个常见说法是错的」。作答前必须先读，"
            "若你的结论与其中某条冲突，以勘误结论为准并说明：\n"
            + "\n\n".join(
                f"  · {w.get('e_code') or w['section']}｜{w['section']}\n{w['text']}"
                for w in warnings
            )
        )

    return "\n\n" + ("\n\n" + "=" * 60 + "\n\n").join(parts) + "\n"


def build_messages(query, results, history=None, warnings=None):
    system = load_system_prompt() + OUTPUT_CONTRACT
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-6:]:
        msgs.append(h)
    msgs.append({
        "role": "user",
        "content": format_context(results, warnings) + f"\n# 用户问题\n\n{query}\n",
    })
    return msgs


def build_prompt_text(query, results, warnings=None):
    """无 LLM 时导出完整 prompt，便于人工/任意模型直接使用。"""
    msgs = build_messages(query, results, None, warnings)
    out = []
    for m in msgs:
        out.append(f"===== {m['role'].upper()} =====")
        out.append(m["content"])
    return "\n\n".join(out)
