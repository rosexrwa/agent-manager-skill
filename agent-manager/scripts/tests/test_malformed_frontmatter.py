"""Tests for issue #159: agent profiles with malformed frontmatter must be
reported with an explicit warning instead of being silently skipped."""
from __future__ import annotations
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import agent_config  # noqa: E402


VALID_AGENT = """\
---
name: dev
description: Dev Agent
working_directory: /tmp
launcher: claude
---

# DEV AGENT
"""

# Frontmatter opened but never closed — the exact shape from issue #159.
UNCLOSED_AGENT = """\
---
name: cloudbank-dev
description: CloudBank Dev
working_directory: /tmp
launcher: claude
skills:
  - agent-manager

# CLOUDBANK-DEV
"""

NO_FRONTMATTER_AGENT = """\
# JUST A HEADING

body text without any frontmatter
"""


class MalformedFrontmatterTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="agent-manager-159-"))
        self.agents_dir = self.temp_root / "agents"
        self.agents_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _write(self, filename: str, content: str) -> Path:
        path = self.agents_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def _capture_stderr(self, fn, *args, **kwargs):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = fn(*args, **kwargs)
        return result, stderr.getvalue()

    def test_parse_agent_file_reports_unclosed_frontmatter(self):
        path = self._write("EMP_0015.md", UNCLOSED_AGENT)
        with self.assertRaises(ValueError) as ctx:
            agent_config.parse_agent_file(path)
        self.assertIn("never closed", str(ctx.exception))
        self.assertIn(str(path), str(ctx.exception))

    def test_parse_agent_file_reports_missing_frontmatter(self):
        path = self._write("EMP_0016.md", NO_FRONTMATTER_AGENT)
        with self.assertRaises(ValueError) as ctx:
            agent_config.parse_agent_file(path)
        self.assertIn("no YAML frontmatter", str(ctx.exception))

    def test_list_all_agents_warns_instead_of_silent_skip(self):
        self._write("EMP_0001.md", VALID_AGENT)
        broken = self._write("EMP_0015.md", UNCLOSED_AGENT)

        agents, stderr = self._capture_stderr(
            agent_config.list_all_agents, self.agents_dir
        )

        self.assertIn("EMP_0001", agents)
        self.assertNotIn("EMP_0015", agents)
        self.assertIn(str(broken), stderr)
        self.assertIn("never closed", stderr)

    def test_resolve_agent_warns_for_malformed_target(self):
        broken = self._write("EMP_0015.md", UNCLOSED_AGENT)

        config, stderr = self._capture_stderr(
            agent_config.resolve_agent, "EMP_0015", self.agents_dir
        )

        self.assertIsNone(config)
        self.assertIn(str(broken), stderr)
        self.assertIn("never closed", stderr)
        # The same file must not be warned about twice in one resolution.
        self.assertEqual(stderr.count(str(broken)), 1)

    def test_resolve_agent_by_name_still_works_with_broken_sibling(self):
        # Broken profile sorts before the valid one, so the name scan hits it
        # first: it must warn and keep going, not abort the resolution.
        self._write("EMP_0000.md", UNCLOSED_AGENT)
        self._write("EMP_0001.md", VALID_AGENT)

        config, stderr = self._capture_stderr(
            agent_config.resolve_agent, "dev", self.agents_dir
        )

        self.assertIsNotNone(config)
        self.assertEqual(config.get("name"), "dev")
        self.assertIn("EMP_0000.md", stderr)

    def test_list_malformed_profiles(self):
        self._write("EMP_0001.md", VALID_AGENT)
        broken = self._write("EMP_0015.md", UNCLOSED_AGENT)

        failures = agent_config.list_malformed_profiles(self.agents_dir)

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], broken)
        self.assertIn("never closed", failures[0][1])

    def test_valid_profiles_produce_no_warnings(self):
        self._write("EMP_0001.md", VALID_AGENT)

        agents, stderr = self._capture_stderr(
            agent_config.list_all_agents, self.agents_dir
        )

        self.assertIn("EMP_0001", agents)
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
