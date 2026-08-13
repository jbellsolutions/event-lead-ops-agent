from __future__ import annotations

import argparse
import signal
from pathlib import Path

from .config import canonical_source
from .profile_lock import ProfileLock

START_URLS = {
    "craigslist": "https://tampa.craigslist.org/",
    "facebook_marketplace": "https://www.facebook.com/marketplace/",
}


def default_start_url(source: str) -> str:
    return START_URLS[canonical_source(source)]


def parse_viewport(value: str) -> dict[str, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("viewport must be WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise ValueError("viewport dimensions must be positive")
    return {"width": width, "height": height}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch one lock-held persistent Chromium profile after browser-council selection"
        )
    )
    parser.add_argument("source", choices=("craigslist", "facebook", "facebook_marketplace"))
    parser.add_argument("--profile", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--start-url")
    parser.add_argument("--viewport", default="1440x900")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = canonical_source(args.source)
    start_url = args.start_url or default_start_url(source)
    if start_url != default_start_url(source):
        raise SystemExit("custom start URLs are disabled; use the certified platform root")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("install the browser extra and Chromium before launching") from exc

    with ProfileLock(Path(args.profile)), sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(Path(args.profile).resolve()),
            headless=args.headless,
            viewport=parse_viewport(args.viewport),
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(start_url, wait_until="domcontentloaded")
        stopping = False

        def stop(_signum: int, _frame: object) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        while not stopping:
            page.wait_for_timeout(1_000)
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
