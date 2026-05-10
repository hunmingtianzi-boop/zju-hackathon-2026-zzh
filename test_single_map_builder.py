import tempfile
import unittest
from pathlib import Path

from single_map_builder import (
    RELATION_TYPES,
    KnowledgeTriple,
    RuleBasedTripleExtractor,
    build_graph,
    build_single_book_graph,
    quality_report,
)


class SingleMapBuilderTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.book_dir = self.root / "03_生理学"
        self.book_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_chunk(self, name: str, text: str):
        path = self.book_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_rule_extractor_emits_controlled_relation_types(self):
        self.write_chunk(
            "第一章绪论_第一节___调节.md",
            "# 第一节 机体生理功能的调节\n\n"
            "### 一、神经调节\n\n"
            "### 二、体液调节\n\n"
            "心电图可用于心律失常诊断。",
        )

        triples = RuleBasedTripleExtractor().extract_book(self.book_dir)
        relations = {triple.relation for triple in triples}

        self.assertTrue(relations.issubset(set(RELATION_TYPES)))
        self.assertIn("containment", relations)
        self.assertIn("parallel", relations)
        self.assertIn("application", relations)
        self.assertTrue(all(triple.evidence for triple in triples))
        parallel_edges = [(triple.subject, triple.object) for triple in triples if triple.relation == "parallel"]
        self.assertIn(("神经调节", "体液调节"), parallel_edges)
        self.assertIn(("体液调节", "神经调节"), parallel_edges)

    def test_section_order_creates_acyclic_prerequisites(self):
        self.write_chunk("01_第一节.md", "# 第一节 A\n\n正文")
        self.write_chunk("02_第二节.md", "# 第二节 B\n\n正文")
        self.write_chunk("03_第三节.md", "# 第三节 C\n\n正文")

        triples = RuleBasedTripleExtractor().extract_book(self.book_dir)
        graph, invalid = build_graph(triples)
        report = quality_report(graph, triples, invalid, self.book_dir.name)

        self.assertEqual(report.prerequisite_cycles, [])
        self.assertGreaterEqual(report.relation_counts["prerequisite"], 2)

    def test_invalid_triples_are_rejected(self):
        triples = [
            KnowledgeTriple(
                subject="A",
                relation="unknown",
                object="B",
                evidence="bad relation",
                source_path="x.md",
                book_id="book",
                chapter="ch",
                section="sec",
            )
        ]

        graph, invalid = build_graph(triples)

        self.assertEqual(graph.number_of_edges(), 0)
        self.assertEqual(len(invalid), 1)

    def test_build_single_book_graph_writes_outputs(self):
        self.write_chunk(
            "第一章绪论_第一节___调节.md",
            "# 第一节 调节\n\n### 一、神经调节\n\n### 二、体液调节\n\n心电图可用于心律失常诊断。",
        )
        output_dir = self.root / "graphs"

        report = build_single_book_graph(self.book_dir, output_dir)

        self.assertGreater(report.nodes, 0)
        self.assertTrue((output_dir / "03_生理学.triples.json").exists())
        self.assertTrue((output_dir / "03_生理学.graph.json").exists())
        self.assertTrue((output_dir / "03_生理学.cytoscape.json").exists())
        self.assertTrue((output_dir / "03_生理学.quality.json").exists())

    def test_virtual_root_markdown_recovers_underchunked_book(self):
        vault = self.root / "vault"
        chunks = vault / "chunks"
        book_dir = chunks / "02_组织学与胚胎学"
        book_dir.mkdir(parents=True)
        (book_dir / "00_开篇.md").write_text("# 前言\n\n很短。", encoding="utf-8")
        (vault / "02_组织学与胚胎学.md").write_text(
            "# 第一章 细胞\n\n"
            "## 第一节 细胞膜\n\n细胞膜异常可导致疾病。\n\n"
            "## 第二节 细胞器\n\n线粒体异常可导致能量代谢障碍。\n\n"
            "# 第二章 上皮组织\n\n"
            "## 第一节 被覆上皮\n\n被覆上皮可用于解释临床病理改变。",
            encoding="utf-8",
        )

        triples = RuleBasedTripleExtractor().extract_book(book_dir)
        relations = [triple.relation for triple in triples]

        self.assertGreaterEqual(relations.count("prerequisite"), 2)
        self.assertIn("application", relations)

    def test_generic_fragments_are_not_application_nodes(self):
        self.write_chunk(
            "01_片段.md",
            "# 第一节 调节\n\n从而可用于临床诊断。一种异常可导致疾病。\n\n心电图可用于心律失常诊断。",
        )

        triples = RuleBasedTripleExtractor().extract_book(self.book_dir)
        labels = {triple.subject for triple in triples} | {triple.object for triple in triples}

        self.assertNotIn("从而", labels)
        self.assertNotIn("一种", labels)
        self.assertIn("心电图", labels)


if __name__ == "__main__":
    unittest.main()
