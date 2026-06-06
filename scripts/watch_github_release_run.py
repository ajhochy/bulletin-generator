#!/usr/bin/env python3
"""Watch a GitHub Actions release run until it passes or fails.

Requires the GitHub CLI (`gh`) to be authenticated for this repository.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any


TERMINAL_STATES = {"completed"}
SUCCESS_CONCLUSION = "success"


def run_gh(args: list[str]) -> Any:
    proc = subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    text = proc.stdout.strip()
    return json.loads(text) if text else None


def notify(title: str, message: str) -> None:
    print("\a", end="", flush=True)
    if sys.platform == "darwin":
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_message}" with title "{safe_title}"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def find_run(workflow: str, tag: str) -> dict[str, Any] | None:
    fields = "databaseId,status,conclusion,displayTitle,headBranch,headSha,url,createdAt,updatedAt,event,workflowName"
    try:
        data = run_gh(
            [
                "run",
                "list",
                "--workflow",
                workflow,
                "--branch",
                tag,
                "--limit",
                "10",
                "--json",
                fields,
            ]
        )
    except RuntimeError:
        data = run_gh(
            [
                "run",
                "list",
                "--branch",
                tag,
                "--limit",
                "25",
                "--json",
                fields,
            ]
        )
    for run in data:
        workflow_name = run.get("workflowName") or ""
        workflow_file_match = workflow in workflow_name
        electron_release_match = workflow_name == "Release (Electron)"
        if run.get("headBranch") == tag and (workflow_file_match or electron_release_match):
            return run
    return None


def get_run(run_id: int) -> dict[str, Any]:
    return run_gh(
        [
            "run",
            "view",
            str(run_id),
            "--json",
            "databaseId,status,conclusion,name,displayTitle,headBranch,headSha,url,jobs,createdAt,updatedAt,event",
        ]
    )


def summarize_jobs(run: dict[str, Any]) -> str:
    jobs = run.get("jobs") or []
    parts = []
    for job in jobs:
        name = job.get("name", "unknown")
        status = job.get("status", "unknown")
        conclusion = job.get("conclusion")
        label = conclusion or status
        parts.append(f"{name}: {label}")
    return " | ".join(parts) if parts else "jobs unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default="release-electron.yml")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=60 * 60)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    run: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        try:
            run = find_run(args.workflow, args.tag)
        except Exception as exc:
            print(f"Waiting for workflow run lookup: {exc}", flush=True)
            time.sleep(args.interval)
            continue

        if run:
            break
        print(f"Waiting for {args.workflow} run on {args.tag}...", flush=True)
        time.sleep(args.interval)

    if not run:
        notify("GitHub release watcher", f"No run found for {args.tag}")
        print(f"No run found for workflow={args.workflow} tag={args.tag}", file=sys.stderr)
        return 2

    run_id = int(run["databaseId"])
    last_line = ""
    while time.monotonic() < deadline:
        run = get_run(run_id)
        status = run.get("status")
        conclusion = run.get("conclusion")
        line = (
            f"run={run_id} status={status}"
            f" conclusion={conclusion or '-'} jobs=[{summarize_jobs(run)}]"
            f" url={run.get('url')}"
        )
        if line != last_line:
            print(line, flush=True)
            last_line = line

        if status in TERMINAL_STATES:
            if conclusion == SUCCESS_CONCLUSION:
                notify("GitHub release passed", f"{args.workflow} passed for {args.tag}")
                return 0
            notify("GitHub release failed", f"{args.workflow} {conclusion} for {args.tag}")
            return 1

        time.sleep(args.interval)

    notify("GitHub release watcher", f"Timed out watching {args.tag}")
    print(f"Timed out watching run {run_id}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
