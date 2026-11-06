"""Scan git history with gitleaks and write docs/security/secrets-history.md.

The report stores file, commit and secret type only. It does not rewrite history.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.secrets_report import render_secrets_history

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "security" / "secrets-history.md"


def _gitleaks_bin() -> str:
    local = ROOT / "tools" / "gitleaks"
    if local.is_file():
        return str(local)
    return "gitleaks"


def _findings(report_path: Path) -> list[dict[str, str]]:
    if not report_path.is_file() or report_path.stat().st_size == 0:
        return []
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "file": str(item.get("File") or ""),
                "commit": str(item.get("Commit") or ""),
                "rule": str(item.get("RuleID") or "unknown"),
            }
        )
    return rows


def main() -> int:
    binary = _gitleaks_bin()
    report = Path("/tmp/nse-gitleaks-history.json")
    report.unlink(missing_ok=True)
    cmd = [
        binary,
        "detect",
        "--source",
        str(ROOT),
        "--redact",
        "--log-opts=--all",
        "--report-format",
        "json",
        "--report-path",
        str(report),
    ]
    config = ROOT / ".gitleaks.toml"
    if config.is_file():
        cmd[4:4] = ["--config", str(config)]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode not in {0, 1}:
        sys.stderr.write(completed.stderr)
        return completed.returncode or 1
    try:
        rows = _findings(report)
    finally:
        report.unlink(missing_ok=True)
    version = subprocess.run([binary, "version"], check=False, capture_output=True, text=True)
    tool = (version.stdout or version.stderr or binary).strip().splitlines()[0]
    scanned_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M IST")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render_secrets_history(rows, scanned_at=scanned_at, gitleaks=tool), encoding="utf-8")
    print(f"wrote {OUT} findings={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
