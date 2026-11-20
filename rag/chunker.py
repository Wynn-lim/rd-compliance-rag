"""分层 markdown 分块器。

规则（施工规格 §3.2 / §4.2）：
  - 按 `## ` 节切块；每个 H2 前的头部（H1 标题 + 元数据表）单独成块；
  - 超长节先按 `### ` 子节切，仍超长再按空行分段，**表格整块不拆**；
  - 单个超长表格按行分组切分，并重复表头行；
  - 元数据四字段：文件名 / M 编号 / 层级 / 节标题（另加模块、状态、文号、E 编号）。
"""
import hashlib
import re

from . import metadata as md
from .config import EXCLUDED_DIRS, KNOWLEDGE_DIRS, MAX_CHUNK_CHARS, MIN_CHUNK_CHARS

H2_RE = re.compile(r"^##\s+(.*)$")
H3_RE = re.compile(r"^###\s+(.*)$")


def _is_table_line(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _table_blocks(lines):
    """把行序列切成块：连续表格行合成一个块，其余按空行分段。

    表格被空行切断后，续块会补回此前的表头行，保证每块自描述。
    """
    blocks, buf, in_table = [], [], False
    pending_header = []

    def flush():
        nonlocal buf
        if buf:
            blocks.append(buf)
            buf = []

    def remember_header(blk):
        if len(blk) > 1 and re.fullmatch(r"\|[\s:\-|]+\|", blk[1].strip()):
            return blk[:2]
        return []

    for ln in lines:
        if _is_table_line(ln):
            if not in_table and buf:
                flush()
            if not in_table and pending_header and buf == []:
                buf.extend(pending_header)
            in_table = True
            buf.append(ln)
        else:
            if in_table and ln.strip() == "":
                flush()
                in_table = False
                continue
            if in_table:
                flush()
                in_table = False
            if ln.strip() == "":
                flush()
            else:
                buf.append(ln)
    flush()

    # 记录每个表格块的表头，供后续续块使用
    out, header = [], []
    for b in blocks:
        if b and _is_table_line(b[0]):
            h = remember_header(b)
            if h:
                header = h
            elif header and b[: len(header)] != header:
                b = header + b
        out.append(b)
    return out


def _split_cell_content(content, budget):
    """把单元格文本切成 ≤ budget 的片段，优先在 ／；，、 处断，最后硬切。"""
    for sep in ("／", "；", "，", "、"):
        if content.count(sep) < 2:
            continue
        pieces, buf = [], ""
        for seg in content.split(sep):
            cand = (buf + sep + seg) if buf else seg
            if len(cand) > budget and buf:
                pieces.append(buf)
                buf = seg
            else:
                buf = cand
        if buf:
            pieces.append(buf)
        if all(len(p) <= budget for p in pieces):
            return pieces
    return _hard_split(content, budget)


def _split_long_row(row, max_chars):
    """把超长的单个表格行拆成多行，保持单元格数量不变（在最长单元格内切）。"""
    if len(row) <= max_chars:
        return [row]
    parts = row.split("|")
    if len(parts) < 3:
        return _hard_split(row, max_chars)
    inner = parts[1:-1]
    longest = max(range(len(inner)), key=lambda i: len(inner[i]))
    pieces = _split_cell_content(inner[longest], max(80, max_chars - 40))
    out = []
    for i, piece in enumerate(pieces):
        cells = list(inner)
        cells[longest] = piece if i == 0 else f"…（承上）{piece}"
        if i > 0:
            for j in range(len(cells)):
                if j != longest and j != len(cells) - 1:
                    cells[j] = "　"
        out.append("|" + "|".join(cells) + "|")
    return out


def _split_oversized_table(block):
    """把一个超长表格切成多组，每组重复表头行；组内超长行再按行内拆分。"""
    if len(block) > 1 and re.fullmatch(r"\|[\s:\-|]+\|", block[1].strip()):
        header, rows = block[:2], block[2:]
    else:
        header, rows = [], block
    header_len = sum(len(h) + 1 for h in header)
    row_budget = max(200, MAX_CHUNK_CHARS - header_len - 2)
    flat = []
    for r in rows:
        flat.extend(_split_long_row(r, row_budget))
    groups, cur, size = [], [], 0
    for r in flat:
        if size + len(r) > row_budget and cur:
            groups.append(header + cur)
            cur, size = [], 0
        cur.append(r)
        size += len(r)
    if cur:
        groups.append(header + cur)
    return groups


def _hard_split(text, max_chars):
    """兜底硬切：按行边界切，保证每片 ≤ max_chars。优先在句号/分号处断。"""
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    pieces, cur, size = [], [], 0
    for ln in lines:
        if len(ln) > max_chars:            # 单行就超长（极少见），按句号切
            if cur:
                pieces.append("\n".join(cur))
                cur, size = [], 0
            buf = ""
            for seg in re.split(r"(?<=[。；！？])", ln):
                if len(buf) + len(seg) > max_chars and buf:
                    pieces.append(buf)
                    buf = ""
                buf += seg
                while len(buf) > max_chars:
                    pieces.append(buf[:max_chars])
                    buf = buf[max_chars:]
            if buf:
                cur, size = [buf], len(buf)
            continue
        if size + len(ln) + 1 > max_chars and cur:
            pieces.append("\n".join(cur))
            cur, size = [], 0
        cur.append(ln)
        size += len(ln) + 1
    if cur:
        pieces.append("\n".join(cur))
    return [p for p in pieces if p.strip()]


def _pack_blocks(blocks, max_chars):
    """把块按顺序打包进 ≤ max_chars 的 chunk，小块并入前块。"""
    chunks, cur, size = [], [], 0

    def flush():
        nonlocal cur, size
        if cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0

    for b in blocks:
        text = "\n".join(b)
        blen = len(text)
        if blen > max_chars:
            # 单块本身就超长：表格按行组切（重复表头），其余走硬切
            flush()
            if _is_table_line(b[0]):
                chunks.extend("\n".join(g) for g in _split_oversized_table(b))
            else:
                chunks.extend(_hard_split(text, max_chars))
            continue
        if size + blen + 1 > max_chars and cur:
            flush()
        cur.append(text)
        size += blen + 1
    flush()
    return chunks


def _split_section(body_lines, heading):
    """把一个 H2 节切成若干 (子节标题, chunk 文本)。"""
    if not body_lines:
        return []
    whole = "\n".join(body_lines)
    if len(whole) <= MAX_CHUNK_CHARS:
        return [("", whole)]

    # 1) 先按 H3 子节切
    subs, cur, cur_h = [], [], ""
    for ln in body_lines:
        m = H3_RE.match(ln)
        if m:
            if cur:
                subs.append((cur_h, cur))
            cur_h, cur = m.group(1).strip(), [ln]
        else:
            cur.append(ln)
    if cur:
        subs.append((cur_h, cur))

    # 无 H3 子节时，整节按段落/表格边界打包
    if len(subs) <= 1:
        return [("", t) for t in _pack_blocks(_table_blocks(body_lines), MAX_CHUNK_CHARS)]

    out = []
    for sub_h, sub_lines in subs:
        text = "\n".join(sub_lines)
        if len(text) <= MAX_CHUNK_CHARS:
            out.append((sub_h, text))
        else:
            for packed in _pack_blocks(_table_blocks(sub_lines), MAX_CHUNK_CHARS):
                out.append((sub_h, packed))
    return out


def split_document(text):
    """返回 [(节标题, 子节标题, 正文)]，含头部块（节标题为 '__header__'）。"""
    lines = text.split("\n")
    sections, cur_head, cur_lines = [], None, []
    header_lines = []

    for ln in lines:
        m = H2_RE.match(ln)
        if m:
            if cur_head is None:
                header_lines = cur_lines
            else:
                sections.append((cur_head, cur_lines))
            cur_head, cur_lines = m.group(1).strip(), [ln]
        else:
            cur_lines.append(ln)
    if cur_head is not None:
        sections.append((cur_head, cur_lines))

    result = []
    if header_lines:
        htext = "\n".join(header_lines).strip()
        if len(htext) >= MIN_CHUNK_CHARS:
            for piece in _pack_blocks(_table_blocks(header_lines), MAX_CHUNK_CHARS):
                if len(piece.strip()) >= MIN_CHUNK_CHARS:
                    result.append(("__header__", "", piece))

    for head, body in sections:
        body_only = body[1:] if body and body[0].startswith("## ") else body
        for sub_h, chunk_text in _split_section(body_only, head):
            if len(chunk_text.strip()) >= MIN_CHUNK_CHARS:
                result.append((head, sub_h, chunk_text))
    return result


def _module_of(rel_path):
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0].startswith(("0", "1")):
        return parts[0]
    return ""


def _m_code_from_name(rel_path):
    import os
    base = os.path.basename(rel_path)
    m = re.match(r"(M\d{2}(?:-\d{2})*)", base)
    return m.group(1) if m else None


def _e_code_from_heading(heading):
    m = re.match(r"(E-\d{3})", heading)
    return m.group(1) if m else None


def build_chunks(kb_root, governance_files, knowledge_dirs, excluded_dirs):
    """遍历知识库，产出 chunk 字典列表。"""
    chunks = []
    for layer, paths in governance_files.items():
        for p in paths:
            if not p.exists():
                continue
            rel = f"00_总纲/{p.name}"
            text = p.read_text(encoding="utf-8")
            for i, (head, sub, body) in enumerate(split_document(text)):
                chunks.append(_make_chunk(
                    layer=layer, rel_path=rel, file_name=p.name, idx=i,
                    head=head, sub=sub, body=body, module="00_总纲",
                ))

    for d in knowledge_dirs:
        dir_path = kb_root / d
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.rglob("*.md")):
            if any(x in f.parts for x in excluded_dirs):
                continue
            rel = f"{d}/{f.name}"
            text = f.read_text(encoding="utf-8")
            for i, (head, sub, body) in enumerate(split_document(text)):
                chunks.append(_make_chunk(
                    layer="knowledge", rel_path=rel, file_name=f.name, idx=i,
                    head=head, sub=sub, body=body, module=d,
                ))
    for i, c in enumerate(chunks):
        c["chunk_id"] = f"{i:05d}"
    return chunks


def _make_chunk(layer, rel_path, file_name, idx, head, sub, body, module):
    e_code = _e_code_from_heading(head)
    m_code = _m_code_from_name(rel_path)
    title = ""
    first = body.strip().split("\n")[0]
    if first.startswith("# "):
        title = first[2:].strip()
    full = body
    return {
        "layer": layer,
        "module": module,
        "rel_path": rel_path,
        "file": file_name,
        "m_code": m_code,
        "e_code": e_code,
        "section": head if head != "__header__" else "文件头部（标题与元数据）",
        "subsection": sub,
        "title": title,
        "status": md.extract_status(full),
        "doc_ids": md.extract_doc_ids(full),
        "m_refs": md.extract_m_codes(full),
        "e_refs": md.extract_e_codes(full),
        "dates": md.extract_dates(full),
        "chars": len(full),
        "sha1": hashlib.sha1(full.encode("utf-8")).hexdigest()[:12],
        "text": full,
        "_idx": idx,
    }
