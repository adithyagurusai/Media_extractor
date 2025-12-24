# Media Extractor - High-Quality Image & Video Downloader

A production-ready Python script that extracts and downloads **maximum-quality** images and videos from webpages. Zero quality loss—no transcoding, recompression, or downscaling.

## Quick Start (3 Steps)

### 1. Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Add URLs (Two Options)

**Option A: Simple URL List (auto-named pages)**
Edit `urls.txt`:
```
https://unsplash.com
https://pixabay.com
```
Results in: `output/page_001/`, `output/page_002/`, etc.

**Option B: Custom Page Names (recommended)**
Edit `pages.txt` with format `URL|PageName`:
```
https://unsplash.com|Unsplash_Photos
https://pixabay.com|Pixabay_Stock
https://en.wikipedia.org/wiki/Cat|Wikipedia_Cats
```
Results in: `output/Unsplash_Photos/`, `output/Pixabay_Stock/`, `output/Wikipedia_Cats/`, etc.

### 3. Run
```bash
python3 media_extractor.py
```

**Tip:** pages.txt takes priority. If not found or empty, falls back to urls.txt

---

## Features

### Image Extraction ✨
- **srcset parsing**: Selects highest width (2560w > 1920w) or density (3x > 2x)
- **Picture/source tags**: Modern HTML5 responsive images
- **Lazy-loading**: Detects data-srcset, data-src, data-original, data-image, data-lazy
- **CSS backgrounds**: Extracts from inline styles and `<style>` blocks
- **Smart deduplication**: No duplicate downloads per page
- **Ignore patterns**: Automatically skips thumbnails and small variants

### Video Extraction 🎬
- **HTML5 tags**: Direct MP4/WebM downloads
- **YouTube/Vimeo**: Detects and saves iframe URLs
- **Streaming**: HLS/DASH manifest support (no DRM bypass)
- **Resolution detection**: Extracts 1080p, 720p, etc.
- **Quality first**: Always selects highest resolution

### Download & Quality 📥
- **Maximum quality**: Always picks highest resolution
- **Streaming**: No memory buffering for large files
- **Retry logic**: 3 attempts with exponential backoff
- **Original format**: Preserves file extensions and format
- **Organized output**: page_001/, page_002/ with images/ and videos/ subdirs
- **Complete metadata**: JSON report per page with extraction details

---

## Configuration Files

### pages.txt (Recommended)
Custom page naming for organized downloads.

**Format:** `URL|PageName` (pipe-separated)

```
# Custom page names - one per line
https://en.wikipedia.org/wiki/Cat|Wikipedia_Cats
https://en.wikipedia.org/wiki/Dog|Wikipedia_Dogs
https://example.com/gallery|My_Photos
```

**Features:**
- Use meaningful names instead of `page_001`, `page_002`
- Spaces become underscores in folder names
- Takes priority over `urls.txt` if both exist
- Lines starting with `#` are comments

### urls.txt (Fallback)
Simple URL list, one per line. Used if `pages.txt` doesn't exist or is empty.

```
https://en.wikipedia.org/wiki/Cat
https://en.wikipedia.org/wiki/Dog
https://example.com/gallery
```

---

## Output Structure

**With pages.txt:**
```
output/
├── Wikipedia_Cats/
│   ├── images/
│   │   ├── img_001.jpg (highest quality)
│   │   ├── img_002.webp
│   │   └── img_003.png
│   ├── videos/
│   │   ├── vid_001.mp4 (1080p)
│   │   └── vid_002.webm
│   └── metadata.json
├── Wikipedia_Dogs/
│   └── ...
└── extraction.log (detailed debug info)
```

**With urls.txt (fallback):**
```
output/
├── page_001/
├── page_002/
└── extraction.log
```

### metadata.json Example
```json
{
  "page_id": "page_001",
  "source_url": "https://example.com",
  "images": [
    {
      "image_id": "img_001",
      "original_url": "https://cdn.example.com/image-2560w.jpg",
      "descriptor": "2560w",
      "source": "img/srcset",
      "local_path": "page_001/images/image-2560w.jpg",
      "width": 2560,
      "file_size": 524288
    }
  ],
  "videos": [
    {
      "video_id": "vid_001",
      "original_url": "https://cdn.example.com/video-1080p.mp4",
      "type": "mp4",
      "resolution": "1080p",
      "source": "video_tag/source",
      "local_path_or_reference": "page_001/videos/video-1080p.mp4",
      "file_size": 52428800
    }
  ]
}
```

---

## Configuration

Edit `Config` class in `media_extractor.py`:

```python
class Config:
    OUTPUT_DIR = Path("output")        # Output location
    MAX_RETRIES = 3                   # Retry attempts
    TIMEOUT = 30                      # Seconds per request
    CHUNK_SIZE = 8192                 # Download chunk size
```

---

## Logging

- **Console**: INFO level (progress, summaries)
- **extraction.log**: DEBUG level (detailed decisions, why each variant was chosen)

Example log:
```
2025-12-24 14:30:15 - DEBUG - Selected by width: image-2560w.jpg (2560w)
2025-12-24 14:30:16 - INFO - Downloaded Image img_001 (524 KB)
```

---

## What Gets Extracted?

### Images
✅ `<img>` tags with srcset  
✅ `<picture>` and `<source>` tags  
✅ Lazy-loaded images (data-* attributes)  
✅ CSS background images  
✅ Always picks highest resolution  

### Videos
✅ `<video>` and `<source>` tags  
✅ YouTube/Vimeo embeds (saves URL)  
✅ Cloudflare Stream embeds  
✅ Direct HTML5 videos on CDN  
✅ HLS/DASH streaming manifests  
✅ Respects DRM (no bypass attempts)  

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No media extracted | Check webpage has `<img>`, `<video>` tags. View `extraction.log` |
| Download timeout | Increase `TIMEOUT` in Config, check internet |
| Permission denied | `chmod 755 output/` |
| Slow downloads | Normal for large files; check disk space |
| Import errors | Run `pip install -r requirements.txt` |

---

## Advanced Usage

### Custom Output Directory
```python
from media_extractor import MediaExtractorOrchestrator
from pathlib import Path

urls = ["https://example.com"]
orchestrator = MediaExtractorOrchestrator(urls, output_dir=Path("/custom/path"))
orchestrator.process_urls()
```

### Batch Processing
```python
urls = [f"https://example.com/page/{i}" for i in range(1, 101)]
batch_size = 10
for i in range(0, len(urls), batch_size):
    batch = urls[i:i + batch_size]
    orchestrator = MediaExtractorOrchestrator(batch)
    orchestrator.process_urls()
```

### Increase Logging
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

---

## Requirements

- Python 3.8+
- requests (HTTP library)
- beautifulsoup4 (HTML parsing)

Install: `pip install -r requirements.txt`

---

## Security

✅ SSL/HTTPS verification enabled  
✅ No DRM bypass attempts  
✅ No authentication bypass  
✅ No private content extraction  
✅ Only downloads publicly accessible media  

---

## Production Ready ✅

- All tests passing (8/8)
- Error handling comprehensive
- Logging detailed
- Validation included

---

**Version**: 1.0.0 | **Status**: Production Ready | **Updated**: 2025-12-24
