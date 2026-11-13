"""校验更新记录格式及版本号在各入口的一致性。"""

from datetime import date
from pathlib import Path
import re
import unittest

from gear_contact import __version__


class VersionMetadataTests(unittest.TestCase):
    def test_version_metadata_matches_changelog_and_readmes(self):
        root = Path(__file__).resolve().parents[1]
        project = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'^version\s*=\s*"([^"]+)"$', project, re.M), [__version__])

        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", changelog, re.M)
        self.assertTrue(headings, "更新记录至少需要一个版本")
        versions = []
        dates = []
        for heading in headings:
            match = re.fullmatch(r"\[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})", heading)
            self.assertIsNotNone(match, f"更新记录标题格式错误：{heading}")
            version, day = match.groups()
            versions.append(tuple(map(int, version.split("."))))
            dates.append(date.fromisoformat(day))
        self.assertEqual(versions, sorted(set(versions), reverse=True))
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(".".join(map(str, versions[0])), __version__)

        for filename in ("README.md", "README.en.md"):
            with self.subTest(filename=filename):
                readme = (root / filename).read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"/badge/version-([\d.]+)-", readme), [__version__])
                self.assertIn("](CHANGELOG.md)", readme)
