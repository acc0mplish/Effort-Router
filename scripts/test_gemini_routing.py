#!/usr/bin/env python3
"""Exercise verify_gemini_install.py in an isolated GEMINI_HOME fixture."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gemini_install  # noqa: E402

VALID_SKILL_MD = """---
name: effort-router
description: Use when starting a task in Gemini, Antigravity, Claude Code, Codex, or ChatGPT that needs model and reasoning effort selected by scope, complexity, or risk — fires before implementation, planning, review, or audit work begins.
---

# Effort Router
"""


def _build_fixture(base: Path) -> tuple[Path, Path, Path]:
    fake_home = base / "fake_home"
    fake_home.mkdir()
    bin_dir = base / "bin"
    bin_dir.mkdir()

    gemini_home = base / "gemini_home"
    skill_dir = gemini_home / "config" / "skills" / "effort-router"
    (skill_dir / "platforms").mkdir(parents=True)
    (skill_dir / "scripts").mkdir(parents=True)
    (gemini_home / "config" / "rules").mkdir(parents=True)
    (gemini_home / "antigravity-cli").mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
    shutil.copy2(ROOT / "platforms" / "gemini.md", skill_dir / "platforms" / "gemini.md")
    shutil.copy2(ROOT / "scripts" / "intake_gate.py", skill_dir / "scripts" / "intake_gate.py")
    shutil.copy2(
        ROOT / "platforms" / "gemini-rules" / "effort-router.md",
        gemini_home / "config" / "rules" / "effort-router.md",
    )
    shutil.copytree(ROOT / "platforms" / "gemini-agents", gemini_home / "config" / "agents")
    (gemini_home / "antigravity-cli" / "settings.json").write_text(
        json.dumps({"model": "gemini-4-argon-medium"}) + "\n",
        encoding="utf-8",
    )
    return gemini_home, fake_home, bin_dir


def _install_agy_stub(bin_dir: Path, script_body: str) -> Path:
    stub = bin_dir / "agy"
    stub.write_text(f"#!{sys.executable}\n{script_body}\n", encoding="utf-8")
    stub.chmod(0o755)
    return stub


def _run_verifier(
    gemini_home: Path,
    fake_home: Path,
    bin_dir: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    env = dict(
        os.environ,
        GEMINI_HOME=str(gemini_home),
        HOME=str(fake_home),
        PATH=str(bin_dir),
    )
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_gemini_install.py"), *extra_args],
        env=env,
        capture_output=True,
        text=True,
    )


class GeminiRoutingTests(unittest.TestCase):
    def test_valid_install_without_agy_skips_schema_check_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            result = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS global Gemini effort-router installation", result.stdout)
            self.assertIn(
                "- custom subagents: 11/11 (agy binary not found — schema check skipped)",
                result.stdout,
            )
            self.assertNotIn("11/11 validated", result.stdout)

    def test_require_agy_fails_when_agy_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            result = _run_verifier(gemini_home, fake_home, bin_dir, "--require-agy")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("FAIL global Gemini effort-router installation", result.stdout)
            self.assertIn("agy binary not found (--require-agy specified)", result.stdout)

    def test_valid_install_with_agy_stub_and_schema_error_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            _install_agy_stub(
                bin_dir,
                """
import json, pathlib, sys
plugin_dir = pathlib.Path(sys.argv[3])
agents = list((plugin_dir / "agents").glob("*.md"))
print(json.dumps({"findings": [], "components": {"agents": len(agents)}}))
sys.exit(0)
""".strip(),
            )
            ok = _run_verifier(gemini_home, fake_home, bin_dir, "--require-agy")
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("- custom subagents: 11/11 validated", ok.stdout)

            _install_agy_stub(
                bin_dir,
                """
import json, sys
print(json.dumps({
    "findings": [{"severity": "error", "file": "agents/coder-medium.md", "message": "invalid model"}],
    "components": {"agents": 10}
}))
sys.exit(1)
""".strip(),
            )
            bad = _run_verifier(gemini_home, fake_home, bin_dir, "--require-agy")
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("agy validate error (agents/coder-medium.md): invalid model", bad.stdout)

            _install_agy_stub(
                bin_dir,
                """
import sys
sys.stderr.write("fatal crash\\n")
sys.exit(2)
""".strip(),
            )
            crashed = _run_verifier(gemini_home, fake_home, bin_dir, "--require-agy")
            self.assertEqual(crashed.returncode, 1, crashed.stdout + crashed.stderr)
            self.assertIn("agy plugin validate failed to parse output (rc=2)", crashed.stdout)

    def test_missing_files_rules_and_frontmatter_description_trigger_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            skill_md = (
                gemini_home / "config" / "skills" / "effort-router" / "SKILL.md"
            )
            # Body mentions Gemini and Antigravity, but frontmatter description does not.
            skill_md.write_text(
                "---\nname: effort-router\ndescription: Claude Code and Codex only.\n---\n"
                "Gemini and Antigravity appear only in body text.\n",
                encoding="utf-8",
            )
            res = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn(
                "SKILL.md frontmatter description missing Gemini / Antigravity trigger",
                res.stdout,
            )

            # Restore SKILL.md, remove rule marker / required file.
            skill_md.write_text(VALID_SKILL_MD, encoding="utf-8")
            rule_path = gemini_home / "config" / "rules" / "effort-router.md"
            rule_path.unlink()
            res_missing_rule = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(res_missing_rule.returncode, 1)
            self.assertIn(f"missing {rule_path}", res_missing_rule.stdout)

    def test_readonly_agent_edit_file_injection_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            ro_agent = gemini_home / "config" / "agents" / "review-pr-high.md"
            original = ro_agent.read_text(encoding="utf-8")
            ro_agent.write_text(
                original.replace(
                    "tools: [read_file, run_command, manage_task, search_web]",
                    "tools: [read_file, edit_file, run_command, manage_task, search_web]",
                    1,
                ),
                encoding="utf-8",
            )
            result = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("agent review-pr-high tools mismatch", result.stdout)

    def test_inherit_customizations_true_and_direct_slug_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            agent = gemini_home / "config" / "agents" / "coder-medium.md"
            original = agent.read_text(encoding="utf-8")

            agent.write_text(
                original.replace(
                    "inheritCustomizations: false", "inheritCustomizations: true", 1
                ),
                encoding="utf-8",
            )
            res_inherit = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(res_inherit.returncode, 1, res_inherit.stdout + res_inherit.stderr)
            self.assertIn(
                "agent coder-medium must set inheritCustomizations: false",
                res_inherit.stdout,
            )

            agent.write_text(
                original.replace("model: pro", "model: gemini-4-hydrogen-high", 1),
                encoding="utf-8",
            )
            res_slug = _run_verifier(gemini_home, fake_home, bin_dir)
            self.assertEqual(res_slug.returncode, 1, res_slug.stdout + res_slug.stderr)
            self.assertIn(
                "agent coder-medium expected model tier 'pro', got 'gemini-4-hydrogen-high'",
                res_slug.stdout,
            )

    def test_oserror_permission_error_exits_1_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home, fake_home, bin_dir = _build_fixture(Path(tmp))
            # 1) Deterministic PermissionError / TimeoutExpired mocks
            with mock.patch.dict(
                os.environ,
                {"GEMINI_HOME": str(gemini_home), "HOME": str(fake_home), "PATH": str(bin_dir)},
            ):
                out_is_file, err_is_file = io.StringIO(), io.StringIO()
                with (
                    mock.patch.object(
                        Path, "is_file", side_effect=PermissionError("sandbox denied")
                    ),
                    contextlib.redirect_stdout(out_is_file),
                    contextlib.redirect_stderr(err_is_file),
                ):
                    rc = verify_gemini_install.main([])
                self.assertEqual(rc, 1)
                self.assertIn("FAIL global Gemini effort-router installation", out_is_file.getvalue())
                self.assertIn("sandbox denied", out_is_file.getvalue())
                self.assertNotIn("Traceback", err_is_file.getvalue())

                out_read, err_read = io.StringIO(), io.StringIO()
                with (
                    mock.patch.object(
                        Path, "read_text", side_effect=PermissionError("read denied")
                    ),
                    contextlib.redirect_stdout(out_read),
                    contextlib.redirect_stderr(err_read),
                ):
                    rc_read = verify_gemini_install.main([])
                self.assertEqual(rc_read, 1)
                self.assertIn("read denied", out_read.getvalue())
                self.assertNotIn("Traceback", err_read.getvalue())

                _install_agy_stub(bin_dir, "import sys\nsys.exit(0)")
                out_timeout, err_timeout = io.StringIO(), io.StringIO()
                with (
                    mock.patch.object(
                        subprocess,
                        "run",
                        side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=15),
                    ),
                    contextlib.redirect_stdout(out_timeout),
                    contextlib.redirect_stderr(err_timeout),
                ):
                    rc_timeout = verify_gemini_install.main(["--require-agy"])
                self.assertEqual(rc_timeout, 1)
                self.assertIn("agy plugin validate timed out after 15s", out_timeout.getvalue())
                self.assertNotIn("Traceback", err_timeout.getvalue())

            # 2) Subprocess run with 0o000 file/dir permissions (when not root)
            rm_agy = bin_dir / "agy"
            if rm_agy.exists():
                rm_agy.unlink()
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                locked_rule = gemini_home / "config" / "rules" / "effort-router.md"
                locked_dir = gemini_home / "config" / "agents"
                try:
                    locked_rule.chmod(0o000)
                    locked_dir.chmod(0o000)
                    proc = _run_verifier(gemini_home, fake_home, bin_dir)
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertIn("FAIL global Gemini effort-router installation", proc.stdout)
                    self.assertNotIn("Traceback", proc.stderr)
                    self.assertNotIn("Traceback", proc.stdout)
                finally:
                    locked_dir.chmod(0o755)
                    locked_rule.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
