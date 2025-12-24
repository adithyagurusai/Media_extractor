#!/usr/bin/env python3
"""
Manual popup media capture helper

• Opens visible Chromium
• You manually click cards / popups
• Captures image network responses
• Saves URLs to output/manual_captured_images.txt
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

# URL = "https://www.trimx.in/menu"
URL = "https://www.trimx.in/branches"
OUT = Path("output") / "manual_captured_images.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)

images = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    def on_response(response):
        try:
            url = response.url
            ct = response.headers.get("content-type", "")
            if (
                "image" in ct
                or response.request.resource_type == "image"
                or url.lower().split("?")[0].endswith(
                    (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg")
                )
            ):
                images.add(url)
        except Exception:
            pass

    page.on("response", on_response)

    print("Opening browser — interact with the page window that appears.")

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        print("Retrying with wait_until=load")
        page.goto(URL, wait_until="load", timeout=60000)

    page.wait_for_timeout(2000)

    print("Page loaded.")
    print("Now click EXPLORE / service cards / nested popups.")
    print("When finished, return here and press Enter.")
    input()

    # Allow final network responses
    page.wait_for_timeout(800)

    with OUT.open("w", encoding="utf-8") as f:
        for u in sorted(images):
            f.write(u + "\n")

    print(f"Saved {len(images)} image URLs to {OUT}")

    browser.close()
