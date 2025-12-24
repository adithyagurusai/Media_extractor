#!/usr/bin/env python3
"""
media_extractor.py — Hierarchical media extractor

• Parent + nested popup support via pages.txt
• Highest-quality image extraction
• Keeps original filenames
• Downloads images & videos
• Saves popup media under parent folders
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

# ───────────────────────── CONFIG ───────────────────────── #

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

# ───────────────────────── LOGGING ───────────────────────── #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("extraction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("media_extractor")

# ───────────────────────── DATA MODELS ───────────────────── #

@dataclass
class ImageMetadata:
    image_id: str
    original_url: str
    source: str
    local_path: Optional[str] = None
    file_size: Optional[int] = None

@dataclass
class VideoMetadata:
    video_id: str
    original_url: str
    source: str
    local_path: Optional[str] = None
    file_size: Optional[int] = None

@dataclass
class PageMetadata:
    page_id: str
    source_url: str
    images: List[ImageMetadata]
    videos: List[VideoMetadata]
    timestamp: str

# ───────────────────────── UTILITIES ─────────────────────── #

def resolve(url: str, base: str) -> str:
    return urljoin(base, url.split("#")[0])

def deoptimize_next_image(url: str, base: str) -> str:
    parsed = urlparse(url)
    if not parsed.path.startswith("/_next/image"):
        return url
    qs = parse_qs(parsed.query)
    if "url" not in qs:
        return url
    return urljoin(base, unquote(qs["url"][0]))

def get_image_category(url: str) -> str:
    """
    Extract category from URLs like:
    /images/cards/<category>/<filename>
    """
    path = urlparse(url).path
    parts = path.strip("/").split("/")

    if len(parts) >= 4 and parts[0] == "images" and parts[1] == "cards":
        return parts[2]  # basics, facial, hair-color, etc.

    return "misc"


# ───────────────────────── FETCHER ───────────────────────── #

class MediaFetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = Config.USER_AGENT

    def fetch_page(self, url: str) -> Optional[Tuple[str, str]]:
        try:
            r = self.s.get(url, timeout=Config.TIMEOUT)
            r.raise_for_status()
            return r.text, r.url
        except Exception as e:
            logger.error(f"Fetch failed: {url} → {e}")
            return None

    def download(self, url: str, path: Path) -> Optional[int]:
        for _ in range(Config.MAX_RETRIES):
            try:
                with self.s.get(url, stream=True, timeout=Config.TIMEOUT) as r:
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

# ───────────────────────── IMAGE EXTRACTOR ────────────────── #

class ImageExtractor:
    def __init__(self, base: str):
        self.base = base
        self.images: List[ImageMetadata] = []
        self.seen = set()
        self.i = 0

    def extract(self, html: str) -> List[ImageMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            if img.get("src"):
                self._add(img["src"], "img")
        return self.images

    def _add(self, url: str, src: str):
        url = resolve(url, self.base)
        if url in self.seen:
            return
        for p in Config.IGNORE_PATTERNS:
            if re.search(p, url, re.I):
                return
        self.i += 1
        self.seen.add(url)
        self.images.append(ImageMetadata(f"img_{self.i:03d}", url, src))

# ───────────────────────── VIDEO EXTRACTOR ────────────────── #

class VideoExtractor:
    def __init__(self, base: str):
        self.base = base
        self.videos: List[VideoMetadata] = []
        self.i = 0

    def extract(self, html: str) -> List[VideoMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        for v in soup.find_all("video"):
            for s in v.find_all("source"):
                if s.get("src"):
                    self.i += 1
                    self.videos.append(
                        VideoMetadata(
                            f"vid_{self.i:03d}",
                            resolve(s["src"], self.base),
                            "video"
                        )
                    )
        return self.videos

# ───────────────────────── DOWNLOADER ─────────────────────── #

class MediaDownloader:
    def __init__(self, out: Path, base: str):
        self.out = out
        self.base = base

    def download_images(self, folder: Path, imgs: List[ImageMetadata]):
        for i in imgs:
            url = deoptimize_next_image(i.original_url, self.base)
            name = os.path.basename(urlparse(url).path)
            category = get_image_category(url)
            category_dir = folder / category
            category_dir.mkdir(parents=True, exist_ok=True)
            p = category_dir / name
            size = fetcher.download(url, p)
            if size:
                i.local_path = str(p.relative_to(Config.OUTPUT_DIR))
                i.file_size = size

    def download_videos(self, folder: Path, vids: List[VideoMetadata]):
        for v in vids:
            name = os.path.basename(urlparse(v.original_url).path)
            p = folder / name
            size = fetcher.download(v.original_url, p)
            if size:
                v.local_path = str(p.relative_to(Config.OUTPUT_DIR))
                v.file_size = size

# ───────────────────────── METADATA ───────────────────────── #

def save_metadata(meta: PageMetadata):
    out = Config.OUTPUT_DIR / meta.page_id
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "metadata.json", "w") as f:
        json.dump(asdict(meta), f, indent=2)
    logger.info(f"Saved metadata → {out / 'metadata.json'}")

# ───────────────────────── PAGES.TXT PARSER ───────────────── #

def load_pages_hierarchy():
    pages = []
    current = None

    for raw in Path("pages.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        is_child = line.startswith(">")
        line = line.lstrip("> ").strip()

        # ─── PARENT PAGE ───
        if not is_child:
            if "|" not in line:
                raise ValueError(f"Parent page must have name: {line}")

            url, name = [x.strip() for x in line.split("|", 1)]
            current = {
                "url": url,
                "name": name,
                "children": [],
                "assets": []
            }
            pages.append(current)
            continue

        # ─── CHILD (POPUP OR ASSET) ───
        if not current:
            raise ValueError("Child entry found before any parent page")

        # Child WITH name → popup page
        if "|" in line:
            url, name = [x.strip() for x in line.split("|", 1)]
            current["children"].append({
                "url": url,
                "name": name
            })
        else:
            # Child WITHOUT name → direct asset
            current["assets"].append(line)

    return pages

# ───────────────────────── ORCHESTRATOR ───────────────────── #

def run():
    pages = load_pages_hierarchy()
    Config.OUTPUT_DIR.mkdir(exist_ok=True)

    for page in pages:
        logger.info(f"Processing parent → {page['name']}")

        res = fetcher.fetch_page(page["url"])
        if not res:
            continue

        html, final = res
        imgs = ImageExtractor(final).extract(html)
        vids = VideoExtractor(final).extract(html)

        parent_dir = Config.OUTPUT_DIR / page["name"]
        # ─── DOWNLOAD EXPLICIT ASSET URLS (CRITICAL FIX) ───
        asset_images = []

        for asset_url in page.get("assets", []):
            asset_images.append(
                ImageMetadata(
                    image_id="asset",
                    original_url=asset_url,
                    source="explicit_asset"
                )
            )

        if asset_images:
            logger.info(
                f"Downloading {len(asset_images)} explicit assets for {page['name']}"
            )

        MediaDownloader(Config.OUTPUT_DIR, final).download_images(
            parent_dir / "images",
            asset_images
        )

        MediaDownloader(Config.OUTPUT_DIR, final).download_images(
            parent_dir / "images", imgs
        )
        MediaDownloader(Config.OUTPUT_DIR, final).download_videos(
            parent_dir / "videos", vids
        )

        # POPUPS
        for child in page["children"]:
            logger.info(f"  Popup → {child['name']}")
            res = fetcher.fetch_page(child["url"])
            if not res:
                continue
            c_html, c_final = res
            c_imgs = ImageExtractor(c_final).extract(c_html)
            c_vids = VideoExtractor(c_final).extract(c_html)

            popup_base = parent_dir / "popups" / child["name"]
            MediaDownloader(Config.OUTPUT_DIR, c_final).download_images(
                popup_base / "images", c_imgs
            )
            MediaDownloader(Config.OUTPUT_DIR, c_final).download_videos(
                popup_base / "videos", c_vids
            )

        save_metadata(
            PageMetadata(
                page_id=page["name"],
                source_url=final,
                images=imgs,
                videos=vids,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        )

# ───────────────────────── ENTRY ──────────────────────────── #

if __name__ == "__main__":
    run()
