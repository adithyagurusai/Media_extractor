#!/bin/bash
# Quick Start Guide - Copy & Paste Ready Commands

# 1. Navigate to project
cd /Users/kothavamsi/Git/TRIMIX_Images

# 2. Activate virtual environment
source venv/bin/activate

# 3. Run validation (optional - verify setup)
python3 test_validator.py

# 4. Edit URLs - Add your target websites
# Edit urls.txt and add URLs like:
# https://en.wikipedia.org/wiki/Cat
# https://en.wikipedia.org/wiki/Dog

# 5. Run the extractor
python3 media_extractor.py

# 6. Check results
ls -la output/page_001/
cat output/page_001/metadata.json

# 7. View detailed log
tail -f extraction.log
