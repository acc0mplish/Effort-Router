#!/usr/bin/env python3
"""Verify the global Gemini / Antigravity Effort Router installation without mutating it."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

EXPECTED_ROLES: dict[str, tuple[str, str, bool]] = {
    "coder-medium": ("gemini-4-carbon-high", "inherit", False),
    "implement-med": ("gemini-4-carbon-high", "inherit", False),
    "implement-xhigh": ("gemini-4-carbon-high", "inherit", False),
    "core-xhigh": ("gemini-4-carbon-high", "inherit", False),
    "ops-supervisor": ("gemini-4-carbon-high", "inherit", False),
    "plan-high": ("gemini-4-hydrogen-xhigh", "pro", False),
    "plan-xhigh": ("gemini-4-hydrogen-xhigh", "pro", False),
    "plan-adversary-xhigh": ("gemini-4-hydrogen-xhigh", "pro", True),
    "review-pr-high": ("gemini-4-carbon-low", "flash", True),
    "review-pr-xhigh": ("gemini-4-hydrogen-xhigh", "pro", True),
    "security-audit": ("gemini-4-hydrogen-xhigh", "pro", True),
}

READONLY_TOOLS = frozenset({"read_file", "run_command", "manage_task", "search_web"})
WRITABLE_TOOLS = frozenset(
    {"read_file", "edit_file", "write_file", "run_command", "manage_task", "search_web"}
)


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}
    result: dict[str, str] = {}
    current_key: str | None = None
    for line in lines[1:end_idx]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() and current_key is not None:
            result[current_key] = f"{result[current_key]} {line.strip()}".strip()
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            current_key = k.strip()
            result[current_key] = v.strip()
    return result


def parse_tools_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    inner = stripped[1:-1].strip()
    if not inner:
        return []
    items = [item.strip().strip("'\"") for item in inner.split(",")]
    if any(not item for item in items):
        return None
    return items


def check_file_exists(path: Path, failures: list[str], label: str = "missing") -> bool:
    try:
        exists = path.is_file()
    except OSError as err:
        failures.append(f"cannot access {path}: {err}")
        return False
    if not exists:
        failures.append(f"{label} {path}")
        return False
    return True


def safe_is_dir(path: Path, failures: list[str]) -> bool:
    try:
        return path.is_dir()
    except OSError as err:
        failures.append(f"cannot access directory {path}: {err}")
        return False


def safe_read_text(path: Path, failures: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        failures.append(f"cannot read {path}: {err}")
        return None


def resolve_agy_bin(failures: list[str]) -> Path | None:
    which_agy = shutil.which("agy")
    candidates: list[Path] = []
    if which_agy:
        candidates.append(Path(which_agy))
    else:
        try:
            candidates.append(Path.home() / ".local" / "bin" / "agy")
        except (OSError, RuntimeError):
            return None
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        except OSError as err:
            failures.append(f"cannot access agy binary {candidate}: {err}")
            return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the global Gemini / Antigravity Effort Router installation."
    )
    parser.add_argument(
        "--require-agy",
        action="store_true",
        help="Fail if the agy CLI binary is not available for plugin schema validation.",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []
    try:
        gemini_env = os.environ.get("GEMINI_HOME")
        gemini_root = (
            Path(gemini_env).expanduser() if gemini_env else (Path.home() / ".gemini")
        )
    except (OSError, RuntimeError) as err:
        print("FAIL global Gemini effort-router installation")
        print(f"- cannot resolve GEMINI_HOME: {err}")
        return 1

    config_root = gemini_root / "config"
    cli_settings_path = gemini_root / "antigravity-cli" / "settings.json"

    skill_dir = config_root / "skills" / "effort-router"
    skill_md_exists = False
    for rel in ("SKILL.md", "platforms/gemini.md", "scripts/intake_gate.py"):
        exists = check_file_exists(skill_dir / rel, failures)
        if rel == "SKILL.md":
            skill_md_exists = exists

    if skill_md_exists:
        skill_text = safe_read_text(skill_dir / "SKILL.md", failures)
        if skill_text is not None:
            skill_fm = parse_frontmatter(skill_text)
            description = skill_fm.get("description", "")
            if "Gemini" not in description or "Antigravity" not in description:
                failures.append(
                    "SKILL.md frontmatter description missing Gemini / Antigravity trigger"
                )

    if check_file_exists(cli_settings_path, failures):
        raw_settings = safe_read_text(cli_settings_path, failures)
        if raw_settings is not None:
            try:
                settings = json.loads(raw_settings)
            except json.JSONDecodeError as err:
                failures.append(f"invalid {cli_settings_path}: {err}")
                settings = {}
            if not isinstance(settings, dict) or settings.get("model") != "gemini-4-carbon-high":
                got_model = settings.get("model") if isinstance(settings, dict) else settings
                failures.append(
                    f"settings.json model expected gemini-4-carbon-high, got {got_model!r}"
                )

    rule_path = config_root / "rules" / "effort-router.md"
    rule_ready = False
    if check_file_exists(rule_path, failures):
        rule_text = safe_read_text(rule_path, failures)
        if rule_text is not None:
            rule_ready = True
            for marker in (
                "trigger: always_on",
                "gemini-4-carbon-high",
                "gemini-4-hydrogen-xhigh",
                "gemini-4-carbon-low",
                "intake_gate.py",
                "실패 기반 영구 예방 규칙",
            ):
                if marker not in rule_text:
                    failures.append(f"rules/effort-router.md missing marker: {marker}")

    agents_dir = config_root / "agents"
    all_agents_readable = True
    for role, (_slug, tier, read_only) in EXPECTED_ROLES.items():
        agent_path = agents_dir / f"{role}.md"
        if not check_file_exists(agent_path, failures, label="missing agent"):
            all_agents_readable = False
            continue
        agent_text = safe_read_text(agent_path, failures)
        if agent_text is None:
            all_agents_readable = False
            continue
        fm = parse_frontmatter(agent_text)
        if fm.get("name") != role:
            failures.append(f"agent {role} name mismatch: {fm.get('name')!r}")
        if fm.get("model") != tier:
            failures.append(
                f"agent {role} expected model tier {tier!r}, got {fm.get('model')!r}"
            )
        if fm.get("subagent") != "true" or fm.get("mainAgent") != "false":
            failures.append(f"agent {role} must set subagent: true and mainAgent: false")
        if fm.get("inheritCustomizations") != "false":
            failures.append(
                f"agent {role} must set inheritCustomizations: false, got {fm.get('inheritCustomizations')!r}"
            )
        expected_tools = READONLY_TOOLS if read_only else WRITABLE_TOOLS
        parsed_tools = parse_tools_list(fm.get("tools"))
        if (
            parsed_tools is None
            or len(parsed_tools) != len(set(parsed_tools))
            or frozenset(parsed_tools) != expected_tools
        ):
            failures.append(
                f"agent {role} tools mismatch: expected {sorted(expected_tools)}, got {fm.get('tools')!r}"
            )

    agy_bin = resolve_agy_bin(failures)
    agy_validated = False
    if agy_bin is None:
        if args.require_agy:
            failures.append("agy binary not found (--require-agy specified)")
    elif safe_is_dir(agents_dir, failures) and rule_ready and all_agents_readable:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                (tmp_path / "plugin.json").write_text(
                    json.dumps(
                        {
                            "name": "effort-router-verify",
                            "description": "Verification harness",
                            "version": "1.0.0",
                        }
                    ),
                    encoding="utf-8",
                )
                (tmp_path / "agents").mkdir()
                for role in EXPECTED_ROLES:
                    shutil.copy2(agents_dir / f"{role}.md", tmp_path / "agents" / f"{role}.md")
                (tmp_path / "rules").mkdir()
                shutil.copy2(rule_path, tmp_path / "rules" / "effort-router.md")
                proc = subprocess.run(
                    [str(agy_bin), "plugin", "validate", str(tmp_path), "--json"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
        except subprocess.TimeoutExpired:
            failures.append("agy plugin validate timed out after 15s")
        except (OSError, shutil.Error) as err:
            failures.append(f"agy plugin validate execution failed: {err}")
        else:
            try:
                report = json.loads(proc.stdout) if proc.stdout.strip() else None
            except json.JSONDecodeError:
                report = None

            if not isinstance(report, dict):
                detail = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
                failures.append(
                    f"agy plugin validate failed to parse output (rc={proc.returncode}): {detail}"
                )
            else:
                raw_findings = report.get("findings")
                findings_list = raw_findings if isinstance(raw_findings, list) else []
                errors = [
                    finding
                    for finding in findings_list
                    if isinstance(finding, dict) and finding.get("severity") == "error"
                ]
                for err_item in errors:
                    failures.append(
                        f"agy validate error ({err_item.get('file')}): {err_item.get('message')}"
                    )
                raw_components = report.get("components")
                components_map = raw_components if isinstance(raw_components, dict) else {}
                agent_count = components_map.get("agents")
                if agent_count != len(EXPECTED_ROLES):
                    failures.append(
                        f"agy validate loaded {agent_count} agents, expected {len(EXPECTED_ROLES)}"
                    )
                if proc.returncode != 0 and not errors:
                    detail = (proc.stderr or proc.stdout).strip()
                    failures.append(
                        f"agy plugin validate exited with code {proc.returncode}: {detail}"
                    )
                if not failures:
                    agy_validated = True

    if failures:
        print("FAIL global Gemini effort-router installation")
        for item in failures:
            print(f"- {item}")
        return 1

    print("PASS global Gemini effort-router installation")
    print(f"- GEMINI_CONFIG: {config_root}")
    print("- default session model: gemini-4-carbon-high")
    print("- planning/adversary/deep-review/audit: gemini-4-hydrogen-xhigh (pro tier)")
    print("- light S/M review: gemini-4-carbon-low (flash tier)")
    if agy_validated:
        print(f"- custom subagents: {len(EXPECTED_ROLES)}/{len(EXPECTED_ROLES)} validated")
    else:
        print(
            f"- custom subagents: {len(EXPECTED_ROLES)}/{len(EXPECTED_ROLES)} "
            "(agy binary not found — schema check skipped)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
