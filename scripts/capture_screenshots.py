"""Capture screenshots of the running Proteoscope app.

Run against a live server on 127.0.0.1:8013. Drives the real UI — fills the
sequence, clicks Analyze, waits for the canvases to paint, then shoots.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
OUT = "screenshots"

LYSOZYME = (
    ">sp|P00698|LYSC_CHICK Lysozyme C\n"
    "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])

        # --- desktop ---
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)

        # 01 — the input view, before analysis.
        page.screenshot(path=f"{OUT}/01-analyze.png")
        print("shot 01-analyze")

        # Run a prediction.
        page.fill("#sequence", LYSOZYME)
        page.fill("#label", "Lysozyme C")
        page.click("#run")
        page.wait_for_selector("#results:not([hidden])", timeout=30000)
        page.wait_for_timeout(1800)  # let the canvases paint

        # 02 — the 3D trace.
        page.locator("#viewer").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/02-structure.png")
        print("shot 02-structure")

        # 03 — the contact map.
        page.locator("#contactmap").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/03-contacts.png")
        print("shot 03-contacts")

        # 04 — the properties + table.
        page.locator("#props").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/04-properties.png")
        print("shot 04-properties")

        # 05 — the About view.
        page.click("#nav-about")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/05-about.png")
        print("shot 05-about")

        # --- mobile ---
        mobile = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True
        )
        mobile.goto(BASE, wait_until="networkidle")
        mobile.wait_for_timeout(600)
        mobile.fill("#sequence", LYSOZYME)
        mobile.click("#run")
        mobile.wait_for_selector("#results:not([hidden])", timeout=30000)
        mobile.wait_for_timeout(1800)
        mobile.screenshot(path=f"{OUT}/06-mobile.png")
        print("shot 06-mobile")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
