"""Render the gitleaks history report without secret values (NSE-003)."""

from __future__ import annotations

from typing import Any


def render_secrets_history(
    findings: list[dict[str, Any]],
    *,
    scanned_at: str,
    gitleaks: str,
) -> str:
    """Markdown of file, commit and secret type. Ignores any value fields on purpose."""
    rows = [
        {
            "file": str(item.get("file") or item.get("File") or ""),
            "commit": str(item.get("commit") or item.get("Commit") or ""),
            "rule": str(item.get("rule") or item.get("RuleID") or "unknown"),
        }
        for item in findings
    ]
    lines = [
        "# Secrets in git history",
        "",
        f"Scan: {scanned_at}. Tool: {gitleaks}.",
        "This file lists file, commit, and secret type only. Values are never recorded.",
        "Git history is not rewritten here. The owner rotates any credential below, then rewrites history.",
        "",
    ]
    if not rows:
        lines.append("No leaked secrets were found. Nothing to rotate.")
        lines.append("")
        return "\n".join(lines)
    lines.append("| File | Commit | Secret type | Action |")
    lines.append("|---|---|---|---|")
    for row in rows:
        lines.append(f"| {row['file']} | {row['commit']} | {row['rule']} | ROTATE |")
    lines.append("")
    return "\n".join(lines)
