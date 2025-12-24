# QUICK REFERENCE - Custom Page Naming Feature

## ⚡ Quick Start

### Option 1: Custom Names (Recommended)
**Edit `pages.txt`:**
```
https://en.wikipedia.org/wiki/Cat|Wikipedia_Cats
https://example.com/photos|My_Photos
```

**Run:**
```bash
python3 media_extractor.py
```

**Result:**
```
output/Wikipedia_Cats/
output/My_Photos/
```

---

### Option 2: Auto-Numbered (Fallback)
**Edit `urls.txt`:**
```
https://en.wikipedia.org/wiki/Cat
https://example.com/photos
```

**Result:**
```
output/page_001/
output/page_002/
```

---

## 📋 Format Reference

### pages.txt Format
```
URL|PageName
URL|PageName
# Comments start with #
```

**Examples:**
```
https://en.wikipedia.org/wiki/Cat|Wikipedia_Cats
https://unsplash.com|Photography_Stock
https://example.com/gallery|Travel_2025
```

### Output Structure
```
output/
├── Wikipedia_Cats/
│   ├── images/        (extracted images)
│   ├── videos/        (extracted videos)
│   └── metadata.json  (extraction details)
├── Photography_Stock/
│   ├── images/
│   ├── videos/
│   └── metadata.json
└── extraction.log     (debug log)
```

---

## ✅ Checklist

- [ ] Created/edited `pages.txt` with URLs and custom names
- [ ] Each entry has format: `URL|PageName`
- [ ] Names use underscores for spaces (e.g., `My_Photos`)
- [ ] Uncommented lines are actual entries (not #comments)
- [ ] Run: `python3 media_extractor.py`
- [ ] Check: `output/` folder for custom-named directories

---

## 🔑 Key Points

| Feature | pages.txt | urls.txt |
|---------|-----------|----------|
| **Custom Names** | ✅ Yes | ❌ No |
| **Priority** | ✅ First | ⏱️ Fallback |
| **Format** | `URL\|Name` | One URL per line |
| **Output** | `Wikipedia_Cats/` | `page_001/` |
| **Recommended** | ✅ YES | For simple lists |

---

## 📝 Naming Tips

✅ **Good:**
- `Wikipedia_Cats` - Descriptive and clear
- `My_Travel_2025` - Date + content
- `Portfolio_v2` - Version indicator
- `Client_Project_1` - Context identifier

❌ **Avoid:**
- `page_001` - Not descriptive
- `test` - Too vague
- `My Page` - Use underscores, not spaces
- Special characters beyond underscore

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Still see `page_001/` | Ensure `pages.txt` has entries |
| Format error | Check for pipe `\|` separator |
| Empty folder | URL might be invalid or blocked |
| Metadata missing | Check `output/{PageName}/metadata.json` |
| URL not recognized | Remove extra spaces in `pages.txt` |

---

## 📁 File Locations

- **Configuration:** `pages.txt` (primary), `urls.txt` (fallback)
- **Script:** `media_extractor.py`
- **Output:** `output/{PageName}/`
- **Logs:** `extraction.log`
- **Examples:** `USAGE_EXAMPLES.md`

---

## 🚀 Common Commands

```bash
# Setup (one time)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run extraction with custom names
python3 media_extractor.py

# View results
ls -la output/

# See detailed logs
tail -f extraction.log

# Check metadata
cat output/Wikipedia_Cats/metadata.json
```

---

## 💡 Pro Tips

1. **Bulk Processing:** Add multiple URLs to `pages.txt` for batch extraction
2. **Organizing Collections:** Use descriptive names for easy file management
3. **Comments:** Use `#` to temporarily disable URLs without deleting them
4. **Fallback:** If `pages.txt` is empty, script automatically uses `urls.txt`
5. **Logging:** Check `extraction.log` for detailed extraction information
6. **Metadata:** Each output folder has `metadata.json` with complete extraction details

---

## Version Information

- **Python:** 3.8+
- **Dependencies:** requests 2.31.0, beautifulsoup4 4.12.2
- **Last Updated:** 2025-12-24
- **Feature Status:** ✅ Active & Tested

**Need Help?** See `README.md` or `USAGE_EXAMPLES.md` for detailed information.
