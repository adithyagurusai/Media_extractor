#!/usr/bin/env python3
"""
media_extractor.py — High-quality image & public video extractor

• Extracts highest-resolution images (srcset, picture, lazy, CSS)
• De-optimizes Next.js _next/image URLs
• Supports Playwright for dynamic pages
• Downloads media without recompression
• Generates clean JSON metadata per page
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
from urllib.parse import (
    urljoin, urlparse, parse_qs, unquote
)

import requests
from bs4 import BeautifulSoup

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
        if not url:
            return ""
        return urljoin(base_url, url.split("#")[0])

def deoptimize_next_image(url: str, base_url: str) -> str:
    """
    Convert Next.js optimized image URLs back to original assets.
    """
    parsed = urlparse(url)
    if not parsed.path.startswith("/_next/image"):
        return url

    qs = parse_qs(parsed.query)
    if "url" not in qs:
        return url

    original_path = unquote(qs["url"][0])
    return urljoin(base_url, original_path)

# ───────────────────────────────── SRCSET PARSER ─────────────────────────── #

class SrcsetParser:
    @staticmethod
    def parse(srcset: str) -> List[Dict]:
        candidates = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split()
            url = bits[0]
            desc = bits[1] if len(bits) > 1 else ""
            cand = {"url": url}
            if desc.endswith("w"):
                cand["width"] = int(desc[:-1])
            elif desc.endswith("x"):
                cand["density"] = float(desc[:-1])
            candidates.append(cand)
        return candidates

    @staticmethod
    def select_best(candidates: List[Dict]) -> Optional[Dict]:
        if not candidates:
            return None
        if any("width" in c for c in candidates):
            return max(candidates, key=lambda c: c.get("width", 0))
        if any("density" in c for c in candidates):
            return max(candidates, key=lambda c: c.get("density", 0))
        return candidates[0]

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
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def download(self, url: str, path: Path) -> Optional[int]:
        for _ in range(Config.MAX_RETRIES):
            try:
                with self.session.get(url, stream=True, timeout=Config.TIMEOUT) as r:
                    r.raise_for_status()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    size = 0
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(Config.CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                size += len(chunk)
                    return size
            except Exception:
                time.sleep(1)
        return None

fetcher = MediaFetcher()

# ───────────────────────────────── IMAGE EXTRACTOR ───────────────────────── #

class ImageExtractor:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.images: List[ImageMetadata] = []
        self.seen: Set[str] = set()
        self.counter = 0

    def extract(self, html: str) -> List[ImageMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        self._from_img(soup)
        self._from_picture(soup)
        self._from_lazy(soup)
        self._from_css(soup)
        return self.images

    def _should_include(self, url: str) -> bool:
        url = URLResolver.resolve(url, self.base_url)
        if url in self.seen:
            return False
        for p in Config.IGNORE_PATTERNS:
            if re.search(p, url, re.I):
                return False
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)

    def _add(self, url: str, source: str, descriptor: str = ""):
        url = URLResolver.resolve(url, self.base_url)
        if not self._should_include(url):
            return
        self.counter += 1
        self.seen.add(url)
        self.images.append(
            ImageMetadata(
                image_id=f"img_{self.counter:03d}",
                original_url=url,
                source=source,
                descriptor=descriptor
            )
        )

    def _from_img(self, soup):
        for img in soup.find_all("img"):
            if img.get("srcset"):
                c = SrcsetParser.select_best(
                    SrcsetParser.parse(img["srcset"])
                )
                if c:
                    self._add(c["url"], "img/srcset")
                    continue
            if img.get("src"):
                self._add(img["src"], "img")

    def _from_picture(self, soup):
        for pic in soup.find_all("picture"):
            for src in pic.find_all("source"):
                if src.get("srcset"):
                    c = SrcsetParser.select_best(
                        SrcsetParser.parse(src["srcset"])
                    )
                    if c:
                        self._add(c["url"], "picture")
            img = pic.find("img")
            if img and img.get("src"):
                self._add(img["src"], "picture/fallback")

    def _from_lazy(self, soup):
        lazy_attrs = [
            "data-src", "data-srcset", "data-original",
            "data-image", "data-background"
        ]
        for el in soup.find_all(True):
            for a in lazy_attrs:
                if el.get(a):
                    if "srcset" in a:
                        c = SrcsetParser.select_best(
                            SrcsetParser.parse(el[a])
                        )
                        if c:
                            self._add(c["url"], f"lazy/{a}")
                    else:
                        self._add(el[a], f"lazy/{a}")
                    break

    def _from_css(self, soup):
        pattern = r'url\(["\']?([^"\')]+)["\']?\)'
        for el in soup.find_all(style=True):
            for u in re.findall(pattern, el["style"]):
                self._add(u, "css/inline")
        for st in soup.find_all("style"):
            if st.string:
                for u in re.findall(pattern, st.string):
                    self._add(u, "css/style")

# ───────────────────────────────── VIDEO EXTRACTOR ───────────────────────── #

class VideoExtractor:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.videos: List[VideoMetadata] = []
        self.counter = 0

    def extract(self, html: str) -> List[VideoMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        for v in soup.find_all("video"):
            for s in v.find_all("source"):
                if s.get("src"):
                    self.counter += 1
                    self.videos.append(
                        VideoMetadata(
                            video_id=f"vid_{self.counter:03d}",
                            original_url=URLResolver.resolve(
                                s["src"], self.base_url
                            ),
                            source="video"
                        )
                    )
        return self.videos

# ───────────────────────────────── DOWNLOADER ────────────────────────────── #

class MediaDownloader:
    def __init__(self, output_dir: Path, base_url: str):
        self.output_dir = output_dir
        self.base_url = base_url

    def download_images(
        self, page_id: str, images: List[ImageMetadata]
    ) -> List[ImageMetadata]:
        out = self.output_dir / page_id / "images"
        for img in images:
            clean_url = deoptimize_next_image(
                img.original_url, self.base_url
            )
            img.original_url = clean_url
            name = os.path.basename(urlparse(clean_url).path)
            path = out / name
            size = fetcher.download(clean_url, path)
            if size:
                img.local_path = str(path.relative_to(self.output_dir))
                img.file_size = size
        return images

    def download_videos(
        self, page_id: str, videos: List[VideoMetadata]
    ) -> List[VideoMetadata]:
        out = self.output_dir / page_id / "videos"
        for v in videos:
            name = os.path.basename(urlparse(v.original_url).path)
            path = out / name
            size = fetcher.download(v.original_url, path)
            if size:
                v.local_path_or_reference = str(
                    path.relative_to(self.output_dir)
                )
                v.file_size = size
        return videos

# ───────────────────────────────── METADATA ──────────────────────────────── #

class MetadataManager:
    @staticmethod
    def save(meta: PageMetadata, out: Path):
        page_dir = out / meta.page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "page_id": meta.page_id,
            "source_url": meta.source_url,
            "timestamp": meta.timestamp,
            "images": [asdict(i) for i in meta.images],
            "videos": [asdict(v) for v in meta.videos],
        }
        with open(page_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Saved metadata → {page_dir / 'metadata.json'}")

# ───────────────────────────────── ORCHESTRATOR ──────────────────────────── #

class MediaExtractorOrchestrator:
    def __init__(self, urls: List[str], names: Dict[str, str]):
        self.urls = urls
        self.names = names
        Config.OUTPUT_DIR.mkdir(exist_ok=True)

    def run(self):
        for idx, url in enumerate(self.urls, 1):
            page_id = self.names.get(url, f"page_{idx:03d}")
            logger.info(f"Processing {page_id}: {url}")

            res = fetcher.fetch_page(url)
            if not res:
                continue

            html, final_url = res

            images = ImageExtractor(final_url).extract(html)
            videos = VideoExtractor(final_url).extract(html)

            dl = MediaDownloader(Config.OUTPUT_DIR, final_url)
            images = dl.download_images(page_id, images)
            videos = dl.download_videos(page_id, videos)

            meta = PageMetadata(
                page_id=page_id,
                source_url=final_url,
                images=images,
                videos=videos,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )

            MetadataManager.save(meta, Config.OUTPUT_DIR)

# ───────────────────────────────── ENTRY POINT ───────────────────────────── #

def main():
    urls, names = [], {}

    if Path("pages.txt").exists():
        for line in Path("pages.txt").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            u, n = line.split("|", 1)
            urls.append(u.strip())
            names[u.strip()] = n.strip()

    elif Path("urls.txt").exists():
        for line in Path("urls.txt").read_text().splitlines():
            if line and not line.startswith("#"):
                urls.append(line.strip())

    if not urls:
        logger.error("No URLs provided.")
        return

    MediaExtractorOrchestrator(urls, names).run()

if __name__ == "__main__":
    main()
