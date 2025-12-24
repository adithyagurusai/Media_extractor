"""
Run this script to open a visible Chromium window; interact with the page
(manually click the "EXPLORE SERVICES" buttons). The script records any
image network responses and writes the discovered URLs to
`output/manual_captured_images.txt`.

Usage:
  python3 tools/manual_click_capture.py

Requirements:
  - Playwright installed in your Python env: `pip install playwright`
  - Install browsers: `playwright install`

When the browser opens, click the site as you normally would. Return to the
terminal and press Enter to stop capture and save results.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import json

URL = "https://www.trimx.in/menu"
OUT = Path('output') / 'manual_captured_images.txt'
OUT.parent.mkdir(parents=True, exist_ok=True)

images = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    def on_response(response):
        try:
            url = response.url
            headers = response.headers
            ct = headers.get('content-type', '')
            # treat as image by content-type or resource type or file extension
            if 'image' in ct or response.request.resource_type == 'image' or url.lower().split('?')[0].endswith(('.jpg','.jpeg','.png','.webp','.gif','.svg','.avif')):
                images.add(url)
        except Exception:
            pass

    page.on('response', on_response)

    print('Opening browser — interact with the page window that appears.')
    page.goto(URL, wait_until='networkidle')
    print('Page loaded. Now click EXPLORE/Service buttons in the opened browser.')
    print('When finished interacting, return here and press Enter to stop capture.')
    input()

    # give network a moment
    page.wait_for_timeout(500)

    # Save results
    with OUT.open('w', encoding='utf-8') as f:
        for u in sorted(images):
            f.write(u + '\n')

    print(f'Saved {len(images)} image URLs to {OUT}')

    browser.close()
