"""校验更新记录格式及版本号在各入口的一致性。"""

from datetime import date
from pathlib import Path
import re
import unittest

from gear_contact import __version__


class VersionMetadataTests(unittest.TestCase):
    def test_version_metadata_matches_readme_history(self):
        root = Path(__file__).resolve().parents[1]
        project = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'^version\s*=\s*"([^"]+)"$', project, re.M), [__version__])

        histories = []
        for filename, heading in (("README.md", "更新记录"), ("README.en.md", "Changelog")):
            with self.subTest(filename=filename):
                readme = (root / filename).read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"/badge/version-([\d.]+)-", readme), [__version__])
                self.assertIn(f"- [{heading}](#{heading.lower()})", readme)
                history = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", readme, re.M | re.S)
                self.assertIsNotNone(history, "README 缺少更新记录")
                entries = [line for line in history.group(1).splitlines() if line.strip()]
                self.assertTrue(entries, "更新记录至少需要一个版本")
                versions, dates = [], []
                for entry in entries:
                    match = re.fullmatch(r"- \*\*(\d+\.\d+\.\d+) · (\d{4}-\d{2}-\d{2})\*\*：\S.*", entry)
                    self.assertIsNotNone(match, f"更新记录格式错误：{entry}")
                    version, day = match.groups()
                    versions.append(tuple(map(int, version.split("."))))
                    dates.append(date.fromisoformat(day))
                self.assertEqual(versions, sorted(set(versions), reverse=True))
                self.assertEqual(dates, sorted(dates, reverse=True))
                self.assertEqual(".".join(map(str, versions[0])), __version__)
                histories.append(entries)
        self.assertEqual(len(histories), 2)
        self.assertEqual(histories[0], histories[1], "两份 README 的更新记录必须一致")
