#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 5_000_000
FORBIDDEN_TRACKED = [
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"cookie", re.I),
    re.compile(r"(^|/)(secrets?|credentials?|auth)(/|\.|$)", re.I),
    re.compile(r"\.(db|sqlite|sqlite3|pem|key)$", re.I),
    re.compile(r"(^|/)browser-profiles?(/|$)", re.I),
]
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "github_token": re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"),
    "google_api_key": re.compile(r"AIza[A-Za-z0-9_-]{30,}"),
    "aws_access_key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
}
GENERIC_ASSIGNMENT = re.compile(
    r"(?im)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b"
    r"\s*[:=]\s*(?:[\"']([^\"'\n]+)[\"']|([^\s#,;\n]+))"
)
SAFE_VALUE_MARKERS = {
    "example",
    "placeholder",
    "replace",
    "redacted",
    "intentionally",
    "omitted",
    "synthetic",
    "changeme",
}


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return result.stdout


def tracked_files() -> list[str]:
    return [line for line in run_git("ls-files").splitlines() if line]


def decode_text(data: bytes) -> str | None:
    if len(data) > MAX_TEXT_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check_forbidden_names(files: list[str]) -> list[str]:
    findings = []
    for path in files:
        if path == ".env.example":
            continue
        if any(pattern.search(path) for pattern in FORBIDDEN_TRACKED):
            findings.append(f"forbidden tracked path: {path}")
    return findings


def secret_findings(text: str, label: str) -> list[str]:
    findings = []
    for name, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{name}: {label}:{line}")
    for match in GENERIC_ASSIGNMENT.finditer(text):
        value = (match.group(1) or match.group(2) or "").strip().lower()
        if (
            len(value) < 12
            or value.startswith(("<", "${", "$", "{{"))
            or any(marker in value for marker in SAFE_VALUE_MARKERS)
        ):
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append(f"generic_assignment: {label}:{line}")
    return findings


def check_current_tree(files: list[str]) -> list[str]:
    findings = []
    for relative in files:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = decode_text(path.read_bytes())
        if text is not None:
            findings.extend(secret_findings(text, relative))
    return findings


def check_git_history() -> list[str]:
    findings = []
    seen: set[str] = set()
    for line in run_git("rev-list", "--objects", "--all").splitlines():
        object_id, _, historical_path = line.partition(" ")
        if object_id in seen:
            continue
        seen.add(object_id)
        object_type = run_git("cat-file", "-t", object_id).strip()
        if object_type != "blob":
            continue
        data = subprocess.run(
            ["git", "cat-file", "blob", object_id],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        text = decode_text(data)
        if text is None:
            continue
        label = f"history:{object_id[:12]}:{historical_path or '<unknown>'}"
        findings.extend(secret_findings(text, label))
    return findings


def check_markdown_links(files: list[str]) -> list[str]:
    findings = []
    link_re = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    for relative in files:
        if not relative.endswith(".md"):
            continue
        path = ROOT / relative
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            for target in link_re.findall(line):
                target = target.strip().split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                candidate = (path.parent / target).resolve()
                if not candidate.exists():
                    findings.append(f"broken relative link: {relative}:{line_no} -> {target}")
    return findings


def main() -> int:
    files = tracked_files()
    findings = (
        check_forbidden_names(files)
        + check_current_tree(files)
        + check_git_history()
        + check_markdown_links(files)
    )
    if findings:
        print("Repository verification FAILED:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1
    print(
        f"Repository verification passed: {len(files)} tracked files and full Git history checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
