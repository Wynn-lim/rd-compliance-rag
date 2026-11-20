"""分块与检索的不变量测试。运行：python -I -m pytest tests/ -q  或  python -I tests/test_rag.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag.chunker import _is_table_line, _table_blocks, build_chunks, split_document  # noqa: E402
from rag.config import EXCLUDED_DIRS, GOVERNANCE_FILES, KB_ROOT, KNOWLEDGE_DIRS, MAX_CHUNK_CHARS  # noqa: E402
from rag.metadata import extract_doc_ids, extract_e_codes, extract_m_codes  # noqa: E402
from rag.tokenizer import tokenize  # noqa: E402


class TestChunker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = build_chunks(KB_ROOT, GOVERNANCE_FILES, KNOWLEDGE_DIRS, EXCLUDED_DIRS)

    def test_chunk_count(self):
        self.assertGreater(len(self.chunks), 3000)

    def test_all_chunks_have_layer(self):
        for c in self.chunks:
            self.assertIn(c["layer"], {"route", "knowledge", "errata", "ledger", "method", "log"})

    def test_knowledge_chunks_have_m_code(self):
        for c in self.chunks:
            if c["layer"] == "knowledge":
                self.assertTrue(c["m_code"], f"{c['rel_path']} 缺 M 编号")

    def test_no_oversized_chunk(self):
        bad = [(c["rel_path"], c["section"], c["chars"]) for c in self.chunks if c["chars"] > 1600]
        self.assertEqual(bad, [], f"{len(bad)} 个块超过 1600 字")

    def test_no_empty_chunk(self):
        for c in self.chunks:
            self.assertGreater(len(c["text"].strip()), 50)

    def test_table_blocks_keep_tables_together(self):
        lines = ["| a | b |", "|---|---|", "| 1 | 2 |", "", "正文", "", "| c | d |", "|---|---|", "| 3 | 4 |"]
        blocks = _table_blocks(lines)
        for b in blocks:
            if b and _is_table_line(b[0]):
                self.assertTrue(all(_is_table_line(x) for x in b), "表格块被非表格行打断")

    def test_table_continuation_gets_header(self):
        lines = ["| a | b |", "|---|---|", "| 1 | 2 |", "", "| 3 | 4 |", "| 5 | 6 |"]
        blocks = _table_blocks(lines)
        table_blocks = [b for b in blocks if b and _is_table_line(b[0])]
        self.assertGreaterEqual(len(table_blocks), 1)
        for b in table_blocks[1:]:
            self.assertEqual(b[0], "| a | b |", "续块未补回表头")

    def test_metadata_extraction(self):
        text = "依据财税〔2015〕119 号 二、3，见 M06-15；已被 E-004 勘误；财政部 税务总局公告 2023 年第 7 号"
        self.assertIn("〔2015〕119", extract_doc_ids(text))
        self.assertIn("2023年第7号", extract_doc_ids(text))
        self.assertIn("M06-15", extract_m_codes(text))
        self.assertIn("E-004", extract_e_codes(text))

    def test_long_row_split_keeps_cell_count(self):
        from rag.chunker import _split_long_row

        row = "| a | " + "／".join(["内容" * 100] * 60) + " | b |"
        out = _split_long_row(row, 1100)
        self.assertGreater(len(out), 1)
        for r in out:
            self.assertEqual(r.count("|"), row.count("|"), "拆分后单元格数变了")


class TestTokenizer(unittest.TestCase):
    def test_doc_number_not_split(self):
        toks = tokenize("财税〔2015〕119 号怎么规定")
        self.assertTrue(any("〔2015〕119" in t for t in toks), toks)

    def test_m_and_e_codes_preserved(self):
        toks = tokenize("M06-15 和 E-002")
        self.assertIn("m06-15", toks)
        self.assertIn("e-002", toks)

    def test_stopwords_removed(self):
        toks = tokenize("这个的是什么")
        self.assertNotIn("的", toks)
        self.assertNotIn("是", toks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
