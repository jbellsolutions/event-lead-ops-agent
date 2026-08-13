#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    "", ".md", ".py", ".toml", ".yaml", ".yml", ".json", ".sql", ".sh", ".txt"
}
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
    "generic_assignment": re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
        r"\s*[:=]\s*[\"'](?!example|placeholder|replace|<)[^\"']{12,}[\"']"
    ),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return [line for line in result.stdout.splitlines() if line]


def check_forbidden_names(files: list[str]) -> list[str]:
    findings = []
    for path in files:
        if path == ".env.example":
            continue
        if any(pattern.search(path) for pattern in FORBIDDEN_TRACKED):
            findings.append(f"forbidden tracked path: {path}")
    return findings


def check_secrets(files: list[str]) -> list[str]:
    findings = []
    for relative in files:
        path = ROOT / relative
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{name}: {relative}:{line}")
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
        + check_secrets(files)
        + check_markdown_links(files)
    )
    if findings:
        print("Repository verification FAILED:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"Repository verification passed: {len(files)} tracked files checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
