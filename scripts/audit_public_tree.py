#!/usr/bin/env python3
"""Fail fast when a public branch contains runtime data or personal identifiers."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath


FORBIDDEN_PATHS = (
    re.compile(r"(^|/)config\.json$"),
    re.compile(r"(^|/)data/profile\.json$"),
    re.compile(r"(^|/)\.env(?:\..*)?$"),
    re.compile(r"\.(?:db|sqlite|sqlite3|pdf|png|jpe?g|webp)$", re.I),
    re.compile(r"(^|/)(?:reports/(?:screenshots|evidence)|cookies|sessions|data/browser-profile(?:-|/|$))"),
)
FORBIDDEN_CONTENT = (
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"(?<!github\.com/)\bhendrixfreire\b", re.I),
    re.compile(r"\b(?:discord|telegram):-?\d{8,}\b", re.I),
    re.compile(r"\b(?:ghp|github_pat|sk-[A-Za-z0-9])[-A-Za-z0-9_]{12,}\b"),
    re.compile(r"\b(?:api[_-]?key|authorization)\s*[:=]\s*['\"]?(?!\$\{|<)[^\s'\"]+", re.I),
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.STDOUT)


def main() -> int:
    tracked = [line for line in git("ls-files").splitlines() if line]
    violations: list[str] = []

    for path in tracked:
        normalized = PurePosixPath(path).as_posix()
        if any(pattern.search(normalized) for pattern in FORBIDDEN_PATHS):
            violations.append(f"arquivo privado rastreado: {normalized}")
            continue
        try:
            content = git("show", f":{normalized}")
        except subprocess.CalledProcessError:
            violations.append(f"não foi possível auditar: {normalized}")
            continue
        for pattern in FORBIDDEN_CONTENT:
            if pattern.search(content):
                violations.append(f"conteúdo pessoal/sensível em: {normalized}")
                break

    if violations:
        print("AUDITORIA PÚBLICA FALHOU:", file=sys.stderr)
        print("\n".join(f"- {item}" for item in violations), file=sys.stderr)
        return 1
    print(f"Auditoria pública aprovada: {len(tracked)} arquivos rastreados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
