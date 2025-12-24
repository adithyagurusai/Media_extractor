#!/usr/bin/env python3
"""
High-Quality Media Extractor for Webpages

Extracts and downloads the highest-quality images and publicly available videos
from given webpage URLs. Preserves original quality without transcoding or recompression.

Author: Backend Engineer
Date: 2025-12-24
"""

import os
import json
import logging
import re
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, asdict
import requests
from bs4 import BeautifulSoup
import time

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

def setup_logging(log_file: str = "extraction.log") -> logging.Logger:
    """Configure logging with file and console handlers."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

logger = setup_logging()

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ImageMetadata:
    """Image metadata container."""
    image_id: str
    original_url: str
    descriptor: str
    source: str  # img/srcset, picture, css, lazy
    local_path: Optional[str] = None
    width: Optional[int] = None
    pixel_density: Optional[float] = None
    file_size: Optional[int] = None

@dataclass
class VideoMetadata:
    """Video metadata container."""
    video_id: str
    original_url: str
    video_type: str  # mp4, webm, hls, dash, youtube, vimeo
    resolution: Optional[str] = None
    bitrate: Optional[str] = None
    source: str = "unknown"  # video_tag, iframe, embed
    local_path_or_reference: Optional[str] = None
    file_size: Optional[int] = None

@dataclass
class PageMetadata:
    """Page metadata container."""
    page_id: str
    source_url: str
    images: List[ImageMetadata]
    videos: List[VideoMetadata]
    extraction_timestamp: str
    total_images: int = 0
    total_videos: int = 0

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Global configuration."""
    OUTPUT_DIR = Path("output")
    MAX_RETRIES = 3
    TIMEOUT = 30
    CHUNK_SIZE = 8192
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Video platform patterns
    YOUTUBE_PATTERNS = [
        r'(?:youtube\.com|youtu\.be)',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    VIMEO_PATTERNS = [
        r'vimeo\.com/(\d+)',
        r'player\.vimeo\.com/video/(\d+)',
    ]
    CLOUDFLARE_PATTERNS = [
        r'cloudflarestream\.com',
        r'cdn-cgi/video',
    ]
    
    # Image ignore patterns (thumbnails, small variants)
    IGNORE_PATTERNS = [
        r'thumb', r'thumbnail', r'small', r'tiny',
        r'\d{1,3}x\d{1,3}',  # 100x100, 300x300
        r'(icon|logo|avatar)',
        r'-sm\b', r'-xs\b', r'-mini\b',
        # Tracker pixels and analytics
        r'(facebook\.com/tr|google-analytics|doubleclick|pixel\.gif)',
        r'(tracking|beacon|analytics)',
    ]

# ============================================================================
# FETCH UTILITIES
# ============================================================================

class MediaFetcher:
    """Handles HTTP requests with retry logic and quality preservation."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': Config.USER_AGENT})
        self.session.verify = True
    
    def fetch_page(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Fetch webpage HTML with retry logic.
        
        Returns:
            Tuple of (html_content, final_url) or None on failure.
        """
        logger.info(f"Fetching webpage: {url}")
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    timeout=Config.TIMEOUT,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                # Ensure UTF-8 decoding
                response.encoding = response.apparent_encoding or 'utf-8'
                
                logger.info(f"Successfully fetched {url} (Status: {response.status_code})")
                return response.text, response.url
                
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{Config.MAX_RETRIES} failed: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(f"Failed to fetch {url} after {Config.MAX_RETRIES} attempts")
        return None
    
    def download_media(
        self, url: str, file_path: Path, description: str = "Media"
    ) -> tuple:
        """
        Download media with streaming (no memory buffering).
        
        Returns:
            Tuple of (file_size in bytes, final_file_path) or (None, None) on failure.
        """
        logger.info(f"Downloading {description}: {url}")
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    timeout=Config.TIMEOUT,
                    stream=True,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                # Detect proper extension from Content-Type header or URL
                proper_ext = self._detect_extension_from_content_type(response, url)
                
                # Update file path with proper extension if needed
                if proper_ext and proper_ext != file_path.suffix:
                    final_path = file_path.with_suffix(proper_ext)
                else:
                    final_path = file_path
                
                # Ensure parent directory exists
                final_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Stream download
                total_size = 0
                with open(final_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=Config.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                
                logger.info(f"Successfully downloaded {description} ({total_size} bytes)")
                return (total_size, final_path)
                
            except requests.RequestException as e:
                logger.warning(f"Download attempt {attempt + 1}/{Config.MAX_RETRIES} failed: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        
        logger.error(f"Failed to download {description} after {Config.MAX_RETRIES} attempts")
        return (None, None)
    
    def _detect_extension_from_content_type(self, response: requests.Response, url: str) -> str:
        """
        Detect file extension from Content-Type header or URL.
        
        Args:
            response: HTTP response object
            url: Original URL for fallback detection
        
        Returns:
            File extension (e.g., '.jpg', '.webp', '.bin')
        """
        # First try Content-Type header
        content_type = response.headers.get('Content-Type', '').lower()
        
        mime_to_ext = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/avif': '.avif',
            'image/svg+xml': '.svg',
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
            'application/json': '.json',
        }
        
        # Check for exact Content-Type match
        for mime_type, ext in mime_to_ext.items():
            if mime_type in content_type:
                logger.debug(f"Detected {ext} from Content-Type: {content_type}")
                return ext
        
        # Fallback to URL-based detection
        path = urlparse(url).path
        
        # Try common extensions
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.svg', '.mp4', '.webm', '.mov']:
            if path.lower().endswith(ext):
                return ext
        
        # Default
        return '.bin'

fetcher = MediaFetcher()

# ============================================================================
# URL UTILITIES
# ============================================================================

class URLResolver:
    """Handles URL normalization and resolution."""
    
    @staticmethod
    def resolve_url(url: str, base_url: str) -> str:
        """
        Convert relative URL to absolute URL.
        
        Args:
            url: URL to resolve (may be relative)
            base_url: Base URL for relative resolution
        
        Returns:
            Absolute URL with normalized query string.
        """
        if not url:
            return ""
        
        # Remove URL fragments
        url = url.split('#')[0]
        
        # Join relative URLs
        absolute_url = urljoin(base_url, url)
        
        # Normalize URL (remove duplicate query params)
        absolute_url = URLResolver._normalize_query_string(absolute_url)
        
        return absolute_url
    
    @staticmethod
    def _normalize_query_string(url: str) -> str:
        """Remove duplicate query parameters."""
        parts = urlparse(url)
        if not parts.query:
            return url
        
        # Parse and deduplicate query params
        params = parse_qs(parts.query, keep_blank_values=True)
        normalized_query = urlencode(
            {k: v[0] for k, v in params.items()},
            doseq=False
        )
        
        return url.split('?')[0] + ('?' + normalized_query if normalized_query else '')
    
    @staticmethod
    def get_url_hash(url: str) -> str:
        """Generate hash for URL deduplication."""
        return hashlib.md5(url.encode()).hexdigest()[:8]

# ============================================================================
# IMAGE EXTRACTION
# ============================================================================

class SrcsetParser:
    """Parse srcset attributes and select highest-quality variant."""
    
    @staticmethod
    def parse_srcset(srcset: str) -> List[Dict[str, any]]:
        """
        Parse srcset string into list of candidates.
        
        Returns:
            List of dicts with 'url', 'width', and 'density' keys.
        """
        candidates = []
        
        if not srcset:
            return candidates
        
        for descriptor in srcset.split(','):
            descriptor = descriptor.strip()
            if not descriptor:
                continue
            
            # Parse URL and descriptor
            parts = descriptor.rsplit(None, 1)
            if len(parts) == 2:
                url, spec = parts
                candidate = {'url': url.strip()}
                
                # Parse width descriptor (e.g., "2560w")
                if spec.endswith('w'):
                    try:
                        candidate['width'] = int(spec[:-1])
                    except ValueError:
                        logger.warning(f"Invalid width descriptor: {spec}")
                
                # Parse pixel density (e.g., "2x")
                elif spec.endswith('x'):
                    try:
                        candidate['density'] = float(spec[:-1])
                    except ValueError:
                        logger.warning(f"Invalid density descriptor: {spec}")
                
                candidates.append(candidate)
        
        return candidates
    
    @staticmethod
    def select_highest_quality(candidates: List[Dict]) -> Optional[Dict]:
        """
        Select highest-quality candidate from parsed srcset.
        
        Priority:
        1. Highest width (width descriptor)
        2. Highest pixel density (density descriptor)
        """
        if not candidates:
            return None
        
        # Separate by descriptor type
        width_candidates = [c for c in candidates if 'width' in c]
        density_candidates = [c for c in candidates if 'density' in c]
        
        selected = None
        descriptor_type = None
        
        # Prefer width descriptors (more reliable for high-quality)
        if width_candidates:
            selected = max(width_candidates, key=lambda c: c['width'])
            descriptor_type = f"{selected['width']}w"
            logger.debug(f"Selected by width: {selected['url']} ({descriptor_type})")
        
        # Fallback to density descriptors
        elif density_candidates:
            selected = max(density_candidates, key=lambda c: c['density'])
            descriptor_type = f"{selected['density']}x"
            logger.debug(f"Selected by density: {selected['url']} ({descriptor_type})")
        
        # Last resort: first candidate
        else:
            selected = candidates[0]
            logger.debug(f"No descriptors found, using first candidate: {selected['url']}")
        
        selected['descriptor'] = descriptor_type
        return selected

# ============================================================================
# IMAGE EXTRACTOR
# ============================================================================

class ImageExtractor:
    """Extract high-quality images from webpage HTML."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.extracted_urls: Set[str] = set()  # Deduplication
        self.images: List[ImageMetadata] = []
        self.image_counter = 0
    
    def extract(self, html: str) -> List[ImageMetadata]:
        """Extract all image variants from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract from <img> tags
        self._extract_from_img_tags(soup)
        
        # Extract from <picture> and <source> tags
        self._extract_from_picture_tags(soup)
        
        # Extract lazy-loaded images
        self._extract_lazy_loaded(soup)
        
        # Extract CSS background images
        self._extract_css_images(soup)
        
        logger.info(f"Extracted {len(self.images)} images from page")
        return self.images
    
    def _extract_from_img_tags(self, soup: BeautifulSoup) -> None:
        """Extract images from <img> tags."""
        for img in soup.find_all('img'):
            # Try srcset first
            srcset = img.get('srcset')
            if srcset:
                candidates = SrcsetParser.parse_srcset(srcset)
                selected = SrcsetParser.select_highest_quality(candidates)
                
                if selected:
                    url = URLResolver.resolve_url(selected['url'], self.base_url)
                    if self._should_include_url(url):
                        img_metadata = ImageMetadata(
                            image_id=self._next_image_id(),
                            original_url=url,
                            descriptor=selected.get('descriptor', 'unknown'),
                            source='img/srcset',
                            width=selected.get('width'),
                            pixel_density=selected.get('density'),
                        )
                        self.images.append(img_metadata)
                        self.extracted_urls.add(url)
                        logger.debug(f"[img/srcset] {url} ({selected.get('descriptor', 'unknown')})")
                        continue
            
            # Fallback to src
            src = img.get('src')
            if src:
                url = URLResolver.resolve_url(src, self.base_url)
                if self._should_include_url(url):
                    img_metadata = ImageMetadata(
                        image_id=self._next_image_id(),
                        original_url=url,
                        descriptor='fallback_src',
                        source='img/src',
                    )
                    self.images.append(img_metadata)
                    self.extracted_urls.add(url)
                    logger.debug(f"[img/src] {url}")
    
    def _extract_from_picture_tags(self, soup: BeautifulSoup) -> None:
        """Extract images from <picture> and <source> tags."""
        for picture in soup.find_all('picture'):
            sources = picture.find_all('source')
            
            for source in sources:
                srcset = source.get('srcset')
                media_type = source.get('type', '')
                
                if srcset:
                    candidates = SrcsetParser.parse_srcset(srcset)
                    selected = SrcsetParser.select_highest_quality(candidates)
                    
                    if selected:
                        url = URLResolver.resolve_url(selected['url'], self.base_url)
                        if self._should_include_url(url):
                            # Prefer modern formats only if higher resolution
                            img_metadata = ImageMetadata(
                                image_id=self._next_image_id(),
                                original_url=url,
                                descriptor=selected.get('descriptor', 'unknown'),
                                source=f'picture/{media_type or "srcset"}',
                                width=selected.get('width'),
                                pixel_density=selected.get('density'),
                            )
                            self.images.append(img_metadata)
                            self.extracted_urls.add(url)
                            logger.debug(
                                f"[picture/{media_type}] {url} ({selected.get('descriptor', 'unknown')})"
                            )
            
            # Fallback to <img> inside <picture>
            img = picture.find('img')
            if img:
                src = img.get('src')
                if src:
                    url = URLResolver.resolve_url(src, self.base_url)
                    if self._should_include_url(url):
                        img_metadata = ImageMetadata(
                            image_id=self._next_image_id(),
                            original_url=url,
                            descriptor='picture_fallback',
                            source='picture/img',
                        )
                        self.images.append(img_metadata)
                        self.extracted_urls.add(url)
                        logger.debug(f"[picture/img] {url}")
    
    def _extract_lazy_loaded(self, soup: BeautifulSoup) -> None:
        """Extract lazy-loaded images from data attributes."""
        lazy_attributes = ['data-srcset', 'data-src', 'data-original', 'data-image', 'data-lazy']
        
        for img in soup.find_all(['img', 'div', 'span']):
            for attr in lazy_attributes:
                value = img.get(attr)
                if not value:
                    continue
                
                # Handle srcset format in data attributes
                if attr == 'data-srcset':
                    candidates = SrcsetParser.parse_srcset(value)
                    selected = SrcsetParser.select_highest_quality(candidates)
                    
                    if selected:
                        url = URLResolver.resolve_url(selected['url'], self.base_url)
                        if self._should_include_url(url):
                            img_metadata = ImageMetadata(
                                image_id=self._next_image_id(),
                                original_url=url,
                                descriptor=selected.get('descriptor', 'unknown'),
                                source=f'lazy/{attr}',
                                width=selected.get('width'),
                                pixel_density=selected.get('density'),
                            )
                            self.images.append(img_metadata)
                            self.extracted_urls.add(url)
                            logger.debug(f"[lazy/{attr}] {url} ({selected.get('descriptor', 'unknown')})")
                else:
                    url = URLResolver.resolve_url(value, self.base_url)
                    if self._should_include_url(url):
                        img_metadata = ImageMetadata(
                            image_id=self._next_image_id(),
                            original_url=url,
                            descriptor='lazy_attribute',
                            source=f'lazy/{attr}',
                        )
                        self.images.append(img_metadata)
                        self.extracted_urls.add(url)
                        logger.debug(f"[lazy/{attr}] {url}")
                
                break  # Use first matching attribute
    
    def _extract_css_images(self, soup: BeautifulSoup) -> None:
        """Extract background images from CSS."""
        # Inline styles
        for elem in soup.find_all(style=True):
            style = elem.get('style', '')
            urls = self._extract_urls_from_css(style)
            for url in urls:
                if self._should_include_url(url):
                    resolved_url = URLResolver.resolve_url(url, self.base_url)
                    img_metadata = ImageMetadata(
                        image_id=self._next_image_id(),
                        original_url=resolved_url,
                        descriptor='css_inline',
                        source='css/inline',
                    )
                    self.images.append(img_metadata)
                    self.extracted_urls.add(resolved_url)
                    logger.debug(f"[css/inline] {resolved_url}")
        
        # <style> blocks
        for style_tag in soup.find_all('style'):
            style_content = style_tag.string or ''
            urls = self._extract_urls_from_css(style_content)
            for url in urls:
                if self._should_include_url(url):
                    resolved_url = URLResolver.resolve_url(url, self.base_url)
                    img_metadata = ImageMetadata(
                        image_id=self._next_image_id(),
                        original_url=resolved_url,
                        descriptor='css_style_tag',
                        source='css/style',
                    )
                    self.images.append(img_metadata)
                    self.extracted_urls.add(resolved_url)
                    logger.debug(f"[css/style] {resolved_url}")
    
    def _extract_urls_from_css(self, css: str) -> List[str]:
        """Extract URLs from CSS (url() patterns)."""
        pattern = r'url\(["\']?([^"\'()]+)["\']?\)'
        return re.findall(pattern, css)
    
    def _should_include_url(self, url: str) -> bool:
        """Check if URL should be included (dedup + ignore patterns)."""
        # Check deduplication
        if url in self.extracted_urls:
            return False
        
        # Check ignore patterns
        for pattern in Config.IGNORE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                logger.debug(f"Ignoring URL (matches pattern '{pattern}'): {url}")
                return False
        
        # Check if URL is valid
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            logger.debug(f"Ignoring invalid URL: {url}")
            return False
        
        return True
    
    def _next_image_id(self) -> str:
        """Generate next image ID."""
        self.image_counter += 1
        return f"img_{self.image_counter:03d}"

# ============================================================================
# VIDEO EXTRACTOR
# ============================================================================

class VideoExtractor:
    """Extract public videos from webpage HTML."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.extracted_urls: Set[str] = set()
        self.videos: List[VideoMetadata] = []
        self.video_counter = 0
    
    def extract(self, html: str) -> List[VideoMetadata]:
        """Extract all videos from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract from <video> tags
        self._extract_from_video_tags(soup)
        
        # Extract from embedded iframes
        self._extract_from_iframes(soup)
        
        logger.info(f"Extracted {len(self.videos)} videos from page")
        return self.videos
    
    def _extract_from_video_tags(self, soup: BeautifulSoup) -> None:
        """Extract videos from <video> tags."""
        for video in soup.find_all('video'):
            # Try <source> tags first
            sources = video.find_all('source')
            best_source = None
            best_resolution = None
            
            for source in sources:
                src = source.get('src')
                src_type = source.get('type', '')
                
                if not src:
                    continue
                
                url = URLResolver.resolve_url(src, self.base_url)
                if self._should_include_url(url):
                    # Prefer MP4 > WebM > others
                    priority = self._get_video_priority(src_type, url)
                    if best_source is None or priority > best_source[1]:
                        best_source = (url, priority, src_type)
            
            if best_source:
                url, priority, src_type = best_source
                video_type = self._detect_video_type(url, src_type)
                resolution = self._extract_resolution_from_url(url)
                
                video_metadata = VideoMetadata(
                    video_id=self._next_video_id(),
                    original_url=url,
                    video_type=video_type,
                    resolution=resolution,
                    source='video_tag/source',
                )
                self.videos.append(video_metadata)
                self.extracted_urls.add(url)
                logger.debug(f"[video/source] {url} (type: {video_type})")
            else:
                # Fallback to video src attribute
                src = video.get('src')
                if src:
                    url = URLResolver.resolve_url(src, self.base_url)
                    if self._should_include_url(url):
                        video_type = self._detect_video_type(url, '')
                        resolution = self._extract_resolution_from_url(url)
                        
                        video_metadata = VideoMetadata(
                            video_id=self._next_video_id(),
                            original_url=url,
                            video_type=video_type,
                            resolution=resolution,
                            source='video_tag/src',
                        )
                        self.videos.append(video_metadata)
                        self.extracted_urls.add(url)
                        logger.debug(f"[video/src] {url} (type: {video_type})")
    
    def _extract_from_iframes(self, soup: BeautifulSoup) -> None:
        """Extract videos from iframe embeds."""
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if not src:
                continue
            
            url = URLResolver.resolve_url(src, self.base_url)
            
            # Detect platform
            platform = None
            video_id = None
            
            # YouTube
            for pattern in Config.YOUTUBE_PATTERNS:
                match = re.search(pattern, url)
                if match:
                    if len(match.groups()) > 0:
                        video_id = match.group(1)
                    platform = 'youtube'
                    break
            
            # Vimeo
            if not platform:
                for pattern in Config.VIMEO_PATTERNS:
                    match = re.search(pattern, url)
                    if match:
                        if len(match.groups()) > 0:
                            video_id = match.group(1)
                        platform = 'vimeo'
                        break
            
            # Cloudflare Stream
            if not platform:
                for pattern in Config.CLOUDFLARE_PATTERNS:
                    if re.search(pattern, url):
                        platform = 'cloudflare_stream'
                        break
            
            # Generic MP4/WebM
            if not platform:
                if re.search(r'\.(mp4|webm|m3u8|mpd)$', url, re.IGNORECASE):
                    platform = 'html5_cdn'
            
            if platform and self._should_include_url(url):
                video_type = platform
                resolution = self._extract_resolution_from_url(url)
                
                video_metadata = VideoMetadata(
                    video_id=self._next_video_id(),
                    original_url=url,
                    video_type=video_type,
                    resolution=resolution,
                    source='iframe',
                )
                self.videos.append(video_metadata)
                self.extracted_urls.add(url)
                logger.debug(f"[iframe/{platform}] {url}")
    
    def _detect_video_type(self, url: str, mime_type: str) -> str:
        """Detect video type from URL or MIME type."""
        # From MIME type
        if 'mp4' in mime_type.lower():
            return 'mp4'
        elif 'webm' in mime_type.lower():
            return 'webm'
        elif 'ogg' in mime_type.lower() or 'ogv' in mime_type.lower():
            return 'ogv'
        
        # From URL extension
        if url.lower().endswith('.mp4'):
            return 'mp4'
        elif url.lower().endswith('.webm'):
            return 'webm'
        elif url.lower().endswith('.ogv') or url.lower().endswith('.ogg'):
            return 'ogv'
        elif url.lower().endswith('.m3u8'):
            return 'hls'
        elif url.lower().endswith('.mpd'):
            return 'dash'
        
        return 'unknown'
    
    def _get_video_priority(self, mime_type: str, url: str) -> int:
        """Assign priority to video format (higher = better)."""
        priority = 0
        
        # Prefer MP4 > WebM > others
        if 'mp4' in mime_type.lower() or url.lower().endswith('.mp4'):
            priority = 10
        elif 'webm' in mime_type.lower() or url.lower().endswith('.webm'):
            priority = 5
        else:
            priority = 1
        
        return priority
    
    def _extract_resolution_from_url(self, url: str) -> Optional[str]:
        """Extract resolution from URL if available."""
        # Patterns: 1080p, 720p, 4k, etc.
        pattern = r'([0-9]{3,4}p|[0-9]k)'
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None
    
    def _should_include_url(self, url: str) -> bool:
        """Check if URL should be included."""
        # Deduplication
        if url in self.extracted_urls:
            return False
        
        # Valid URL check
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            logger.debug(f"Ignoring invalid video URL: {url}")
            return False
        
        return True
    
    def _next_video_id(self) -> str:
        """Generate next video ID."""
        self.video_counter += 1
        return f"vid_{self.video_counter:03d}"

# ============================================================================
# MEDIA DOWNLOADER
# ============================================================================

class MediaDownloader:
    """Download extracted media files."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
    
    def download_images(
        self, page_id: str, images: List[ImageMetadata]
    ) -> List[ImageMetadata]:
        """Download images and update metadata."""
        images_dir = self.output_dir / page_id / "images"
        valid_images = []
        
        for img in images:
            # Generate filename from URL
            parsed = urlparse(img.original_url)
            original_filename = os.path.basename(parsed.path)
            
            # Fallback to extension detection
            if not original_filename or '.' not in original_filename:
                extension = self._detect_extension_from_url(img.original_url)
                original_filename = f"{img.image_id}{extension}"
            
            file_path = images_dir / original_filename
            
            # Skip if already downloaded
            if file_path.exists():
                # Check if file is empty or has unknown extension
                file_size = file_path.stat().st_size
                if file_size == 0 or file_path.suffix == '.bin':
                    logger.warning(f"Skipping empty/invalid file: {file_path}")
                    continue
                
                logger.info(f"Skipping existing file: {file_path}")
                img.local_path = str(file_path.relative_to(self.output_dir))
                img.file_size = file_size
                valid_images.append(img)
                continue
            
            # Download (returns tuple of (file_size, final_path))
            file_size, final_path = fetcher.download_media(
                img.original_url,
                file_path,
                f"Image {img.image_id}"
            )
            
            if file_size is not None and final_path is not None:
                # Skip empty files (tracker pixels, 1x1 images, etc.)
                if file_size == 0:
                    logger.warning(f"Skipping empty file (likely tracker pixel): {final_path}")
                    final_path.unlink()  # Delete the empty file
                    continue
                
                # Skip files with unknown/invalid extensions
                if final_path.suffix == '.bin':
                    logger.warning(f"Skipping file with unknown extension: {final_path}")
                    final_path.unlink()  # Delete the file
                    continue
                
                img.local_path = str(final_path.relative_to(self.output_dir))
                img.file_size = file_size
                logger.info(f"Downloaded {img.image_id} -> {img.local_path}")
                valid_images.append(img)
            else:
                logger.error(f"Failed to download {img.image_id}")
        
        return valid_images
    
    def download_videos(
        self, page_id: str, videos: List[VideoMetadata]
    ) -> List[VideoMetadata]:
        """Download videos (or save manifest URLs)."""
        videos_dir = self.output_dir / page_id / "videos"
        valid_videos = []
        
        for vid in videos:
            # For streaming manifests, save URL only
            if vid.video_type in ['hls', 'dash', 'youtube', 'vimeo', 'cloudflare_stream']:
                logger.info(
                    f"Saving manifest/reference URL for {vid.video_id}: {vid.original_url}"
                )
                vid.local_path_or_reference = vid.original_url
                valid_videos.append(vid)
                continue
            
            # For direct files, download
            parsed = urlparse(vid.original_url)
            original_filename = os.path.basename(parsed.path)
            
            if not original_filename or '.' not in original_filename:
                extension = self._detect_extension_from_url(vid.original_url)
                original_filename = f"{vid.video_id}{extension}"
            
            file_path = videos_dir / original_filename
            
            # Skip if already downloaded
            if file_path.exists():
                file_size = file_path.stat().st_size
                if file_size == 0 or file_path.suffix == '.bin':
                    logger.warning(f"Skipping empty/invalid video file: {file_path}")
                    continue
                
                logger.info(f"Skipping existing file: {file_path}")
                vid.local_path_or_reference = str(file_path.relative_to(self.output_dir))
                vid.file_size = file_size
                valid_videos.append(vid)
                continue
            
            # Download (returns tuple of (file_size, final_path))
            file_size, final_path = fetcher.download_media(
                vid.original_url,
                file_path,
                f"Video {vid.video_id}"
            )
            
            if file_size is not None and final_path is not None:
                # Skip empty files
                if file_size == 0:
                    logger.warning(f"Skipping empty video file: {final_path}")
                    final_path.unlink()
                    continue
                
                # Skip files with unknown/invalid extensions
                if final_path.suffix == '.bin':
                    logger.warning(f"Skipping video file with unknown extension: {final_path}")
                    final_path.unlink()
                    continue
                
                vid.local_path_or_reference = str(final_path.relative_to(self.output_dir))
                vid.file_size = file_size
                logger.info(f"Downloaded {vid.video_id} -> {vid.local_path_or_reference}")
                valid_videos.append(vid)
            else:
                logger.error(f"Failed to download {vid.video_id}")
        
        return valid_videos
    
    def _detect_extension_from_url(self, url: str) -> str:
        """Detect file extension from URL."""
        # Remove query parameters
        path = urlparse(url).path
        
        # Try common extensions
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.mp4', '.webm', '.mov']:
            if path.lower().endswith(ext):
                return ext
        
        # Default
        return '.bin'

# ============================================================================
# METADATA MANAGEMENT
# ============================================================================

class MetadataManager:
    """Save and manage metadata."""
    
    @staticmethod
    def save_metadata(metadata: PageMetadata, output_dir: Path) -> None:
        """Save page metadata to JSON."""
        page_dir = output_dir / metadata.page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        
        metadata_file = page_dir / "metadata.json"
        
        # Serialize metadata
        data = {
            'page_id': metadata.page_id,
            'source_url': metadata.source_url,
            'extraction_timestamp': metadata.extraction_timestamp,
            'images': [
                {
                    'image_id': img.image_id,
                    'original_url': img.original_url,
                    'descriptor': img.descriptor,
                    'source': img.source,
                    'local_path': img.local_path,
                    'width': img.width,
                    'pixel_density': img.pixel_density,
                    'file_size': img.file_size,
                } for img in metadata.images
            ],
            'videos': [
                {
                    'video_id': vid.video_id,
                    'original_url': vid.original_url,
                    'type': vid.video_type,
                    'resolution': vid.resolution,
                    'bitrate': vid.bitrate,
                    'source': vid.source,
                    'local_path_or_reference': vid.local_path_or_reference,
                    'file_size': vid.file_size,
                } for vid in metadata.videos
            ],
            'summary': {
                'total_images': len(metadata.images),
                'total_videos': len(metadata.videos),
            }
        }
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved metadata to {metadata_file}")

# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class MediaExtractorOrchestrator:
    """Orchestrate the entire extraction and download process."""
    
    def __init__(self, urls: List[str] = None, output_dir: Path = Config.OUTPUT_DIR, 
                 page_names: Dict[str, str] = None):
        self.urls = urls or []
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.page_counter = 0
        self.page_names = page_names or {}  # Map URL to custom page name
    
    def process_urls(self) -> None:
        """Process all URLs and extract/download media."""
        logger.info(f"Starting media extraction for {len(self.urls)} URLs")
        
        for url in self.urls:
            self._process_single_url(url)
        
        logger.info("Extraction completed!")
    
    def _process_single_url(self, url: str) -> None:
        """Process a single URL."""
        self.page_counter += 1
        
        # Use custom page name if provided, otherwise auto-generate
        if url in self.page_names:
            page_id = self.page_names[url]
        else:
            page_id = f"page_{self.page_counter:03d}"
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Processing {page_id}: {url}")
        logger.info(f"{'='*70}")
        
        # Fetch page
        result = fetcher.fetch_page(url)
        if not result:
            logger.error(f"Failed to fetch {url}, skipping...")
            return
        
        html, final_url = result
        
        # Extract images
        image_extractor = ImageExtractor(final_url)
        images = image_extractor.extract(html)
        
        # Extract videos
        video_extractor = VideoExtractor(final_url)
        videos = video_extractor.extract(html)
        
        # Download media
        downloader = MediaDownloader(self.output_dir)
        images = downloader.download_images(page_id, images)
        videos = downloader.download_videos(page_id, videos)
        
        # Save metadata
        metadata = PageMetadata(
            page_id=page_id,
            source_url=final_url,
            images=images,
            videos=videos,
            extraction_timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            total_images=len(images),
            total_videos=len(videos),
        )
        MetadataManager.save_metadata(metadata, self.output_dir)
        
        # Summary
        logger.info(f"\n{page_id} Summary:")
        logger.info(f"  Images: {len(images)}")
        logger.info(f"  Videos: {len(videos)}")
        logger.info(f"  Output directory: {self.output_dir / page_id}")

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    # Try to read from pages.txt first (URL|PageName format)
    page_names = {}
    urls = []
    
    pages_file = Path("pages.txt")
    if pages_file.exists():
        with open(pages_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '|' in line:
                        url, page_name = line.split('|', 1)
                        url = url.strip()
                        page_name = page_name.strip()
                        urls.append(url)
                        page_names[url] = page_name
                        logger.info(f"Mapped URL to page: {page_name}")
    
    # Fallback to urls.txt if pages.txt doesn't exist or is empty
    if not urls:
        urls_file = Path("urls.txt")
        if urls_file.exists():
            with open(urls_file, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    if not urls:
        logger.error("No URLs provided. Please create pages.txt (URL|PageName format) or urls.txt")
        return
    
    orchestrator = MediaExtractorOrchestrator(urls, page_names=page_names)
    orchestrator.process_urls()

if __name__ == "__main__":
    main()
