#!/usr/bin/env python3
"""
media_extractor.py — High-quality image & public video extractor
with popup, nested-card, and manual-click fallback support

• Extracts highest-resolution images
• Keeps original filenames from URLs
• Supports internal popups & nested cards (Playwright)
• Merges manual popup captures (manual_captured_images.txt)
• Downloads media without recompression
• Generates clean JSON metadata per page
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ───────────────────────────────── CONFIG ───────────────────────────────── #

class Config:
    OUTPUT_DIR = Path("output")
    TIMEOUT = 30
    MAX_RETRIES = 3
    CHUNK_SIZE = 8192
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    IGNORE_PATTERNS = [
        r'analytics', r'pixel', r'facebook\.com/tr',
        r'google-analytics', r'icon', r'logo', r'avatar'
    ]

class PopupConfig:
    CARD_SELECTORS = [
        ".card",
        ".menu-card",
        "[data-card]",
        "[role='button']"
    ]
    POPUP_SELECTORS = [
        "[role='dialog']",
        ".modal",
        ".popup",
        ".overlay",
        ".drawer"
    ]
    MAX_CLICKS = 30

# ───────────────────────────────── LOGGING ───────────────────────────────── #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("extraction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("media_extractor")

# ───────────────────────────────── DATA MODELS ───────────────────────────── #

@dataclass
class ImageMetadata:
    image_id: str
    original_url: str
    source: str
    descriptor: Optional[str] = None
    local_path: Optional[str] = None
    file_size: Optional[int] = None

@dataclass
class VideoMetadata:
    video_id: str
    original_url: str
    source: str
    local_path_or_reference: Optional[str] = None
    file_size: Optional[int] = None

@dataclass
class PageMetadata:
    page_id: str
    source_url: str
    images: List[ImageMetadata]
    videos: List[VideoMetadata]
    timestamp: str

# ───────────────────────────────── URL UTILITIES ─────────────────────────── #

class URLResolver:
    @staticmethod
    def resolve(url: str, base_url: str) -> str:
        return urljoin(base_url, url.split("#")[0]) if url else ""

def deoptimize_next_image(url: str, base_url: str) -> str:
    parsed = urlparse(url)
    if not parsed.path.startswith("/_next/image"):
        return url
    qs = parse_qs(parsed.query)
    if "url" not in qs:
        return url
    return urljoin(base_url, unquote(qs["url"][0]))

# ───────────────────────────────── MANUAL CLICK LOADER ───────────────────── #

def load_manual_captured_images(base_url: str) -> List[ImageMetadata]:
    path = Path("output/manual_captured_images.txt")
    if not path.exists():
        logger.info("No manual_captured_images.txt found — skipping manual merge")
        return []

    images: List[ImageMetadata] = []
    seen: Set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        resolved = URLResolver.resolve(line, base_url)
        if resolved in seen:
            continue

        seen.add(resolved)
        images.append(
            ImageMetadata(
                image_id="manual",
                original_url=resolved,
                source="manual_click"
            )
        )

    logger.info(f"Loaded {len(images)} manual-captured image URLs")
    return images

# ───────────────────────────────── SRCSET PARSER ─────────────────────────── #

class SrcsetParser:
    @staticmethod
    def parse(srcset: str) -> List[Dict]:
        out = []
        for p in srcset.split(","):
            bits = p.strip().split()
            if not bits:
                continue
            c = {"url": bits[0]}
            if len(bits) > 1:
                if bits[1].endswith("w"):
                    c["width"] = int(bits[1][:-1])
                elif bits[1].endswith("x"):
                    c["density"] = float(bits[1][:-1])
            out.append(c)
        return out

    @staticmethod
    def best(cands: List[Dict]) -> Optional[Dict]:
        if not cands:
            return None
        if any("width" in c for c in cands):
            return max(cands, key=lambda x: x.get("width", 0))
        if any("density" in c for c in cands):
            return max(cands, key=lambda x: x.get("density", 0))
        return cands[0]

# ───────────────────────────────── FETCHER ───────────────────────────────── #

class MediaFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = Config.USER_AGENT

    def fetch_page(self, url: str) -> Optional[Tuple[str, str]]:
        try:
            r = self.session.get(url, timeout=Config.TIMEOUT)
            r.raise_for_status()
            return r.text, r.url
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            return None

    def download(self, url: str, path: Path) -> Optional[int]:
        for _ in range(Config.MAX_RETRIES):
            try:
                with self.session.get(url, stream=True, timeout=Config.TIMEOUT) as r:
                    r.raise_for_status()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    size = 0
                    with open(path, "wb") as f:
                        for c in r.iter_content(Config.CHUNK_SIZE):
                            if c:
                                f.write(c)
                                size += len(c)
                    return size
            except Exception:
                time.sleep(1)
        return None

fetcher = MediaFetcher()

# ───────────────────────────────── IMAGE EXTRACTOR ───────────────────────── #

class ImageExtractor:
    def __init__(self, base_url: str):
        self.base = base_url
        self.images: List[ImageMetadata] = []
        self.seen: Set[str] = set()
        self.i = 0

    def extract(self, html: str) -> List[ImageMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        self._img(soup)
        self._picture(soup)
        self._lazy(soup)
        self._css(soup)
        return self.images

    def _ok(self, url: str) -> bool:
        url = URLResolver.resolve(url, self.base)
        if url in self.seen:
            return False
        for p in Config.IGNORE_PATTERNS:
            if re.search(p, url, re.I):
                return False
        return True

    def _add(self, url: str, src: str, desc: str = ""):
        url = URLResolver.resolve(url, self.base)
        if not self._ok(url):
            return
        self.i += 1
        self.seen.add(url)
        self.images.append(ImageMetadata(f"img_{self.i:03d}", url, src, desc))

    def _img(self, soup):
        for img in soup.find_all("img"):
            if img.get("srcset"):
                c = SrcsetParser.best(SrcsetParser.parse(img["srcset"]))
                if c:
                    self._add(c["url"], "img/srcset")
                    continue
            if img.get("src"):
                self._add(img["src"], "img")

    def _picture(self, soup):
        for p in soup.find_all("picture"):
            for s in p.find_all("source"):
                if s.get("srcset"):
                    c = SrcsetParser.best(SrcsetParser.parse(s["srcset"]))
                    if c:
                        self._add(c["url"], "picture")
            if p.img and p.img.get("src"):
                self._add(p.img["src"], "picture/fallback")

    def _lazy(self, soup):
        for el in soup.find_all(True):
            for a in ["data-src", "data-srcset", "data-original", "data-image"]:
                if el.get(a):
                    if "srcset" in a:
                        c = SrcsetParser.best(SrcsetParser.parse(el[a]))
                        if c:
                            self._add(c["url"], f"lazy/{a}")
                    else:
                        self._add(el[a], f"lazy/{a}")
                    break

    def _css(self, soup):
        pat = r'url\(["\']?([^"\')]+)'
        for el in soup.find_all(style=True):
            for u in re.findall(pat, el["style"]):
                self._add(u, "css/inline")
        for s in soup.find_all("style"):
            if s.string:
                for u in re.findall(pat, s.string):
                    self._add(u, "css/style")

# ───────────────────────────── POPUP EXTRACTION ──────────────────────────── #

def find_popup(page):
    for sel in PopupConfig.POPUP_SELECTORS:
        loc = page.locator(sel)
        for i in range(loc.count()):
            if loc.nth(i).is_visible():
                return loc.nth(i)
    return None

def extract_popup_media(url: str) -> Tuple[List[ImageMetadata], List[VideoMetadata]]:
    imgs, vids = [], []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        c = b.new_context(user_agent=Config.USER_AGENT)
        page = c.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            page.goto(url, wait_until="load", timeout=60000)

        page.wait_for_timeout(1500)

        clicks = 0
        for sel in PopupConfig.CARD_SELECTORS:
            cards = page.locator(sel)
            for i in range(min(cards.count(), PopupConfig.MAX_CLICKS)):
                try:
                    card = cards.nth(i)
                    if not card.is_visible():
                        continue
                    card.scroll_into_view_if_needed()
                    card.click(timeout=2000)
                    page.wait_for_timeout(800)

                    popup = find_popup(page)
                    if popup:
                        html = popup.inner_html()
                        base = page.url
                        imgs += ImageExtractor(base).extract(html)

                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
                    clicks += 1
                    if clicks >= PopupConfig.MAX_CLICKS:
                        break
                except Exception:
                    continue

        b.close()

    return imgs, vids

# ───────────────────────────────── ORCHESTRATOR ──────────────────────────── #

class MediaExtractorOrchestrator:
    def __init__(self, urls: List[str], names: Dict[str, str]):
        self.urls = urls
        self.names = names
        Config.OUTPUT_DIR.mkdir(exist_ok=True)

    def run(self):
        for idx, url in enumerate(self.urls, 1):
            page_id = self.names.get(url, f"page_{idx:03d}")
            logger.info(f"Processing {page_id}")

            res = fetcher.fetch_page(url)
            if not res:
                continue

            html, final_url = res

            images = ImageExtractor(final_url).extract(html)
            videos = []

            popup_images, _ = extract_popup_media(final_url)

            manual_images = load_manual_captured_images(final_url)

            existing = {i.original_url for i in images}
            for src in popup_images + manual_images:
                if src.original_url not in existing:
                    images.append(src)

            dl = MediaDownloader(Config.OUTPUT_DIR, final_url)
            images = dl.download_images(page_id, images)

            meta = PageMetadata(
                page_id, final_url, images, videos,
                time.strftime("%Y-%m-%d %H:%M:%S")
            )

            MetadataManager.save(meta, Config.OUTPUT_DIR)

# ───────────────────────────────── DOWNLOADER ────────────────────────────── #

class MediaDownloader:
    def __init__(self, out: Path, base: str):
        self.out = out
        self.base = base

    def download_images(self, pid: str, imgs: List[ImageMetadata]):
        d = self.out / pid / "images"
        for i in imgs:
            url = deoptimize_next_image(i.original_url, self.base)
            name = os.path.basename(urlparse(url).path)
            p = d / name
            size = fetcher.download(url, p)
            if size:
                i.local_path = str(p.relative_to(self.out))
                i.file_size = size
        return imgs

# ───────────────────────────────── METADATA ──────────────────────────────── #

class MetadataManager:
    @staticmethod
    def save(meta: PageMetadata, out: Path):
        p = out / meta.page_id
        p.mkdir(parents=True, exist_ok=True)
        with open(p / "metadata.json", "w") as f:
            json.dump({
                "page_id": meta.page_id,
                "source_url": meta.source_url,
                "timestamp": meta.timestamp,
                "images": [asdict(i) for i in meta.images],
                "videos": [],
            }, f, indent=2)
        logger.info(f"Saved metadata → {p / 'metadata.json'}")

# ───────────────────────────────── ENTRY POINT ───────────────────────────── #

def main():
    urls, names = [], {}

    if Path("pages.txt").exists():
        for l in Path("pages.txt").read_text().splitlines():
            if l and not l.startswith("#"):
                u, n = l.split("|", 1)
                urls.append(u.strip())
                names[u.strip()] = n.strip()
    elif Path("urls.txt").exists():
        urls = [l.strip() for l in Path("urls.txt").read_text().splitlines() if l and not l.startswith("#")]

    if not urls:
        logger.error("No URLs provided.")
        return

    MediaExtractorOrchestrator(urls, names).run()

if __name__ == "__main__":
    main()
