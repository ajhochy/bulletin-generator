#!/usr/bin/env python3
"""Repo-local AI-workflow wrapper for bulletin-generator.

The global `ai-workflow` CLI delegates here via
`python3 scripts/run_ai_workflow.py <args>` (run from the repo root, under
the *system* interpreter — keep this file 3.9-compatible).

Checks are wired to mirror `.github/workflows/ci.yml` exactly so the local
gate matches CI:
  - Python: a pinned subset under the 3.11 venv (avoids DB-dependent files).
  - JS:     `npm test` (vitest) and, at PR level, `npm run build` (vite).

The repo's supported interpreter is Python 3.11+ (auth.py uses 3.10+ syntax),
so pytest runs via .venv/bin/pytest when that venv exists.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirrors the `python` job in .github/workflows/ci.yml. Keep in sync.
CI_PYTEST_TARGETS = [
    "tests/test_server_utils.py",
    "tests/test_update.py",
    "tests/test_drive.py",
    "tests/test_propresenter_export.py",
]

MANUAL_SMOKE_DOC = "docs/testing/manual-smoke.md"


def _venv_python():
    """Return the 3.11 venv python if present, else fall back to python3."""
    candidate = REPO_ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return shutil.which("python3") or sys.executable


def _run(cmd, label):
    print("\n$ " + " ".join(cmd) + ("   # " + label if label else ""))
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def _pytest(targets):
    py = _venv_python()
    return _run([py, "-m", "pytest", "-q", *targets], "python (CI subset)")


def _npm(args, label):
    if not shutil.which("npm"):
        print("npm not found on PATH; skipping " + label)
        return 1
    return _run(["npm", *args], label)


def cmd_status(_args):
    required = [
        "AGENTS.md",
        "docs/ai/project-state.md",
        "docs/ai/repo-map.md",
        "docs/ai/architecture.md",
        "docs/ai/testing-guide.md",
        "docs/ai/current-plan.md",
        "docs/ai/decisions.md",
    ]
    missing = [p for p in required if not (REPO_ROOT / p).exists()]
    print("Repo root: " + str(REPO_ROOT))
    if missing:
        print("Missing workflow context files:")
        for p in missing:
            print("- " + p)
        return 1
    print("Workflow context files: OK")
    if not (REPO_ROOT / ".venv").exists():
        print("WARN: .venv missing — create with "
              "`python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`")
    return 0


def cmd_checks(args):
    level = args.level
    rc = 0
    # issue + smoke + pr all run the fast unit gate first.
    rc |= _pytest(CI_PYTEST_TARGETS)
    rc |= _npm(["test"], "vitest")
    if level == "pr":
        rc |= _npm(["run", "build"], "vite build")
    if level == "smoke":
        print("\n--- smoke level: run the manual checklist below ---")
        cmd_smoke_prompt(args)
    print("\n=== checks --level " + level + " => " + ("PASS" if rc == 0 else "FAIL") + " ===")
    return 1 if rc else 0


def cmd_smoke_prompt(_args):
    doc = REPO_ROOT / MANUAL_SMOKE_DOC
    print("Launch (desktop mode): .venv/bin/python server.py   # http://localhost:8080")
    print("Launch (server mode):  APP_MODE=server .venv/bin/python server.py")
    if doc.exists():
        print("\nManual smoke checklist (" + MANUAL_SMOKE_DOC + "):\n")
        print(doc.read_text())
    else:
        print("\n(no " + MANUAL_SMOKE_DOC + " yet — smoke-test-writer should create one)")
    print("\nChoose: [A] manual smoke (you click through)  "
          "[B] AI UI smoke (computer-control specialist)")
    return 0


def _gh_issue_view(number):
    if not shutil.which("gh"):
        return None
    res = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "number,title,state,milestone"],
        cwd=str(REPO_ROOT), text=True, capture_output=True,
    )
    return res.stdout.strip() if res.returncode == 0 else None


def cmd_next_issue(args):
    if not shutil.which("gh"):
        print("gh CLI required for next-issue.")
        return 1
    cmd = ["gh", "issue", "list", "--state", "open", "--limit", "60",
           "--json", "number,title,milestone"]
    if args.milestone:
        cmd += ["--milestone", args.milestone]
    return _run(cmd, "open issues")


def cmd_start_issue(args):
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(REPO_ROOT), text=True, capture_output=True,
    ).stdout.strip()
    print("Current branch: " + branch)
    info = _gh_issue_view(args.issue)
    if info:
        print(info)
    slug = "issue-" + str(args.issue)
    if not args.execute:
        print("[dry-run] would create branch off current: " + slug)
        print("Re-run with --execute to create it (run-strategy: stack on current branch).")
        return 0
    return _run(["git", "checkout", "-b", slug], "create issue branch")


def cmd_open_pr(args):
    if not shutil.which("gh"):
        print("gh CLI required for open-pr.")
        return 1
    base = "main"
    if not args.execute:
        print("[dry-run] gh pr create --base " + base + " --title " + repr(args.title) + " --draft")
        print("Re-run with --execute to open the draft PR.")
        return 0
    return _run(["gh", "pr", "create", "--base", base, "--draft",
                 "--title", args.title, "--fill"], "open draft PR")


def cmd_run(args):
    print("This repo uses the orchestrator + coding-agent flow for `run`.")
    print("Use: checks --level {issue,pr}, start-issue, open-pr, smoke-prompt.")
    if args.issue:
        print("Requested issue(s): " + args.issue)
    return 0


def main():
    p = argparse.ArgumentParser(prog="run_ai_workflow")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    c = sub.add_parser("checks")
    c.add_argument("--level", choices=["issue", "smoke", "pr"], default="issue")
    c.set_defaults(func=cmd_checks)

    sub.add_parser("smoke-prompt").set_defaults(func=cmd_smoke_prompt)

    n = sub.add_parser("next-issue")
    n.add_argument("--milestone")
    n.set_defaults(func=cmd_next_issue)

    s = sub.add_parser("start-issue")
    s.add_argument("--issue", required=True)
    s.add_argument("--execute", action="store_true")
    s.set_defaults(func=cmd_start_issue)

    o = sub.add_parser("open-pr")
    o.add_argument("--title", required=True)
    o.add_argument("--execute", action="store_true")
    o.set_defaults(func=cmd_open_pr)

    r = sub.add_parser("run")
    r.add_argument("--issue")
    r.add_argument("--execute", action="store_true")
    r.add_argument("--after")
    r.add_argument("--check-level")
    r.add_argument("--pr-title")
    r.set_defaults(func=cmd_run)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
