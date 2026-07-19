#!/usr/bin/env python3
"""Mantém um contexto Brave dedicado para extrair links Apply do LinkedIn.

Nunca pede, digita ou registra credenciais. A autenticação, se necessária, é
feita pelo usuário diretamente na janela Brave dedicada.
"""

from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

BRAVE = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def safe_location(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.hostname or ''}{parsed.path}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="data/browser-profile-linkedin")
    parser.add_argument("--port", type=int, default=9226)
    args = parser.parse_args()

    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    profile = Path(args.profile)
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = None
        errors: list[str] = []
        for name, executable in (("brave", BRAVE), ("chrome", CHROME), ("chromium", None)):
            if executable is not None and not executable.exists():
                continue
            kwargs = {"headless": False, "args": [f"--remote-debugging-port={args.port}"]}
            if executable is not None:
                kwargs["executable_path"] = str(executable)
            try:
                context = playwright.chromium.launch_persistent_context(str(profile), **kwargs)
                print(f"SESSION_OPEN browser={name} cdp=http://127.0.0.1:{args.port}", flush=True)
                break
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
        if context is None:
            raise RuntimeError("browser launch failed: " + "; ".join(errors))

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/jobs/", wait_until="domcontentloaded", timeout=90_000)
        print(f"LINKEDIN_OPEN location={safe_location(page.url)}", flush=True)
        while not stop:
            time.sleep(1)
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
