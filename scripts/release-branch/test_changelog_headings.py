"""Tests for the CHANGELOG headings the cut and the GA prep write.

    python3 -m unittest discover -s scripts/release-branch -p 'test_*.py'

main and the release branch must end up with the same `## 0.42.0 (date)`
heading: the cut writes main's as `## 0.42.0 (unreleased)`, the GA prep dates
the release branch's and main's with one date.
"""

import datetime
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from release_lib import close_unreleased, date_heading, pending_heading, release_heading

HERE = pathlib.Path(__file__).resolve().parent

MAIN_BEFORE_CUT = """# Changelog

## Unreleased

- feat: shipped in 0.42

## 0.41.0 (2026-10-01)

- fix: old
"""


class Headings(unittest.TestCase):
    def test_close_unreleased_writes_pending_heading(self):
        self.assertEqual(
            close_unreleased(MAIN_BEFORE_CUT, "0.42.0"),
            """# Changelog

## Unreleased

## 0.42.0 (unreleased)

- feat: shipped in 0.42

## 0.41.0 (2026-10-01)

- fix: old
""",
        )

    def test_close_unreleased_without_section(self):
        self.assertIsNone(close_unreleased("# Changelog\n\n## 0.41.0 (2026-10-01)\n", "0.42.0"))

    def test_date_heading_dates_every_form(self):
        for heading in (
            pending_heading("0.42.0"),
            "## 0.42.0 (release/0.42)",  # written by cuts before the pending form
            "## 0.42.0 (2026-11-01)",  # dated by hand, or by an earlier GA prep run
            "## 0.42.0",
            "## [0.42.0] - 2026-11-01",
        ):
            with self.subTest(heading=heading):
                text = f"## Unreleased\n\n{heading}\n\n- feat: x\n\n## 0.41.0 (2026-10-01)\n"
                self.assertEqual(
                    date_heading(text, "0.42.0", "2026-11-16"),
                    "## Unreleased\n\n## 0.42.0 (2026-11-16)\n\n- feat: x\n\n## 0.41.0 (2026-10-01)\n",
                )

    def test_date_heading_leaves_other_versions(self):
        text = "## Unreleased\n\n## 0.42.0 (unreleased)\n\n## 0.41.0 (release/0.41)\n\n## 0.4.0 (release/0.4)\n"
        dated = date_heading(text, "0.4.0", "2026-11-16")
        self.assertEqual(dated, text.replace("## 0.4.0 (release/0.4)", "## 0.4.0 (2026-11-16)"))
        self.assertIsNone(date_heading("## Unreleased\n\n## 0.42.10 (unreleased)\n", "0.42.1", "2026-11-16"))

    def test_date_heading_is_idempotent(self):
        text = "## Unreleased\n\n## 0.42.0 (2026-11-16)\n"
        self.assertEqual(date_heading(text, "0.42.0", "2026-11-16"), text)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class CutThenGa(unittest.TestCase):
    """The cut's main heading and the GA prep's release heading converge."""

    def test_ga_prep_dates_both_sides_alike(self):
        with tempfile.TemporaryDirectory() as tmp:
            rel = pathlib.Path(tmp) / "release"
            rel.mkdir()
            (rel / "Cargo.toml").write_text('[workspace]\nmembers = []\n\n[workspace.package]\nversion = "0.42.0"\n')
            (rel / "RELEASE").write_text("0.42.0-rc.1\n")
            (rel / "CHANGELOG.md").write_text(MAIN_BEFORE_CUT)
            git(rel, "init", "-q", "-b", "release/0.42")
            git(rel, "add", "-A")
            git(rel, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "cut")

            main_log = pathlib.Path(tmp) / "main-CHANGELOG.md"
            cut = close_unreleased(MAIN_BEFORE_CUT, "0.42.0")
            assert cut is not None
            main_log.write_text("## Unreleased\n\n- feat: after the cut\n\n" + cut.split("## Unreleased\n\n", 1)[1])

            env = {**os.environ, "RELEASE_ROOT": str(rel)}
            subprocess.run(
                [sys.executable, str(HERE / "prepare-release.py"), "--kind", "ga", "--main-changelog", str(main_log)],
                cwd=rel,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            heading = release_heading("0.42.0", datetime.date.today().isoformat())
            self.assertIn(f"\n{heading}\n", (rel / "CHANGELOG.md").read_text())
            self.assertIn(f"\n{heading}\n", main_log.read_text())
            self.assertNotIn("(unreleased)", main_log.read_text())
            self.assertEqual((rel / "RELEASE").read_text(), "0.42.0\n")


if __name__ == "__main__":
    unittest.main()
