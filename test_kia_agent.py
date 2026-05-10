import tempfile
import unittest
from pathlib import Path

from kia_agent import AgentPaths, KIAAgent


class KIAAgentTest(unittest.TestCase):
    def test_strict_essence_respects_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            essence_dir = root / "essence"
            essence_dir.mkdir()
            (essence_dir / "essence_report.json").write_text(
                '{"original_chars": 1000, "compressed_chars": 900, "compression_ratio": 0.9, "tier_distribution": {"1": 1}}',
                encoding="utf-8",
            )
            (essence_dir / "essence.md").write_text(
                "# Title\n\n### 1. A\n\n**摘要**: Alpha\n\n<details>very long raw text</details>\n\n"
                + "\n".join(f"### {i}. Node\n\n**摘要**: Summary {i}" for i in range(80)),
                encoding="utf-8",
            )
            paths = AgentPaths(
                chunks_dir=root / "chunks",
                graphs_dir=root / "graphs",
                merged_dir=root / "merged",
                essence_dir=essence_dir,
                frontend_data=root / "agentData.json",
            )

            report = KIAAgent(paths).write_strict_essence(target_ratio=0.3)

            self.assertLessEqual(report["compression_ratio"], 0.3)
            self.assertTrue((essence_dir / "essence_strict.md").exists())
            self.assertNotIn("<details>", (essence_dir / "essence_strict.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
