#!/usr/bin/env python3
"""
Test & Validation Script for Media Extractor

Validates the media_extractor.py script and dependencies.
"""

import sys
import subprocess
from pathlib import Path


def test_imports():
    """Test if all required dependencies are installed."""
    print("=" * 70)
    print("Testing Dependencies...")
    print("=" * 70)
    
    required_modules = {
        'requests': 'HTTP library',
        'bs4': 'BeautifulSoup4 (HTML parsing)',
        'urllib': 'URL parsing (built-in)',
        're': 'Regular expressions (built-in)',
        'os': 'OS utilities (built-in)',
        'json': 'JSON handling (built-in)',
        'logging': 'Logging (built-in)',
    }
    
    all_installed = True
    
    for module, description in required_modules.items():
        try:
            __import__(module)
            print(f"✅ {module:20s} - {description}")
        except ImportError:
            print(f"❌ {module:20s} - {description} [NOT INSTALLED]")
            all_installed = False
    
    print()
    return all_installed


def test_script_syntax():
    """Test if media_extractor.py has valid syntax."""
    print("=" * 70)
    print("Testing Script Syntax...")
    print("=" * 70)
    
    try:
        result = subprocess.run(
            ['python3', '-m', 'py_compile', 'media_extractor.py'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ media_extractor.py syntax is valid")
            return True
        else:
            print(f"❌ Syntax error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error testing syntax: {e}")
        return False


def test_file_structure():
    """Test if all required files exist."""
    print("\n" + "=" * 70)
    print("Testing File Structure...")
    print("=" * 70)
    
    required_files = {
        'media_extractor.py': 'Main script',
        'requirements.txt': 'Dependencies list',
        'urls.txt': 'URLs input file',
        'README.md': 'Documentation',
    }
    
    all_exist = True
    
    for filename, description in required_files.items():
        path = Path(filename)
        if path.exists():
            size = path.stat().st_size
            print(f"✅ {filename:25s} - {description} ({size:,} bytes)")
        else:
            print(f"❌ {filename:25s} - {description} [NOT FOUND]")
            all_exist = False
    
    return all_exist


def test_imports_in_script():
    """Test if media_extractor.py imports work."""
    print("\n" + "=" * 70)
    print("Testing Script Imports...")
    print("=" * 70)
    
    try:
        # Try importing the main module
        sys.path.insert(0, str(Path.cwd()))
        from media_extractor import (
            MediaExtractorOrchestrator,
            ImageExtractor,
            VideoExtractor,
            MediaDownloader,
            SrcsetParser,
            URLResolver,
            Config,
        )
        
        print("✅ All main classes imported successfully:")
        print("   - MediaExtractorOrchestrator")
        print("   - ImageExtractor")
        print("   - VideoExtractor")
        print("   - MediaDownloader")
        print("   - SrcsetParser")
        print("   - URLResolver")
        print("   - Config")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_srcset_parser():
    """Test SrcsetParser functionality."""
    print("\n" + "=" * 70)
    print("Testing SrcsetParser...")
    print("=" * 70)
    
    try:
        from media_extractor import SrcsetParser
        
        # Test 1: Width descriptors
        srcset1 = "image-1024w.jpg 1024w, image-2560w.jpg 2560w, image-512w.jpg 512w"
        candidates = SrcsetParser.parse_srcset(srcset1)
        selected = SrcsetParser.select_highest_quality(candidates)
        
        if selected and selected.get('width') == 2560:
            print("✅ Width descriptor parsing: Correctly selected 2560w")
        else:
            print("❌ Width descriptor parsing failed")
            return False
        
        # Test 2: Density descriptors
        srcset2 = "image.jpg 1x, image-2x.jpg 2x, image-3x.jpg 3x"
        candidates = SrcsetParser.parse_srcset(srcset2)
        selected = SrcsetParser.select_highest_quality(candidates)
        
        if selected and selected.get('density') == 3.0:
            print("✅ Density descriptor parsing: Correctly selected 3x")
        else:
            print("❌ Density descriptor parsing failed")
            return False
        
        # Test 3: Empty srcset
        srcset3 = ""
        candidates = SrcsetParser.parse_srcset(srcset3)
        
        if not candidates:
            print("✅ Empty srcset handling: Correctly returns empty list")
        else:
            print("❌ Empty srcset handling failed")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_url_resolver():
    """Test URLResolver functionality."""
    print("\n" + "=" * 70)
    print("Testing URLResolver...")
    print("=" * 70)
    
    try:
        from media_extractor import URLResolver
        
        # Test 1: Relative URL resolution
        relative_url = "/images/photo.jpg"
        base_url = "https://example.com/gallery/page"
        resolved = URLResolver.resolve_url(relative_url, base_url)
        
        if "https://example.com/images/photo.jpg" in resolved:
            print("✅ Relative URL resolution: Correctly resolved to absolute URL")
        else:
            print(f"❌ Relative URL resolution failed: {resolved}")
            return False
        
        # Test 2: Fragment removal
        url_with_fragment = "https://example.com/image.jpg#anchor"
        resolved = URLResolver.resolve_url(url_with_fragment, "https://example.com")
        
        if "#" not in resolved:
            print("✅ Fragment removal: Correctly removed URL fragment")
        else:
            print(f"❌ Fragment removal failed: {resolved}")
            return False
        
        # Test 3: URL hash generation
        url = "https://example.com/image.jpg"
        url_hash = URLResolver.get_url_hash(url)
        
        if len(url_hash) == 8 and all(c in "0123456789abcdef" for c in url_hash):
            print(f"✅ URL hash generation: Correctly generated hash ({url_hash})")
        else:
            print(f"❌ URL hash generation failed: {url_hash}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_config():
    """Test Config settings."""
    print("\n" + "=" * 70)
    print("Testing Configuration...")
    print("=" * 70)
    
    try:
        from media_extractor import Config
        
        checks = [
            ('OUTPUT_DIR', Path("output")),
            ('MAX_RETRIES', 3),
            ('TIMEOUT', 30),
            ('CHUNK_SIZE', 8192),
            ('USER_AGENT', str),  # Check if it's a string
        ]
        
        all_valid = True
        for attr, expected in checks:
            value = getattr(Config, attr)
            
            if isinstance(expected, type):
                # Check type
                if isinstance(value, expected):
                    print(f"✅ Config.{attr:20s} = {str(value)[:50]}")
                else:
                    print(f"❌ Config.{attr:20s} has wrong type")
                    all_valid = False
            else:
                # Check value
                if value == expected:
                    print(f"✅ Config.{attr:20s} = {value}")
                else:
                    print(f"❌ Config.{attr:20s} = {value} (expected {expected})")
                    all_valid = False
        
        return all_valid
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_output_directory():
    """Test if output directory can be created."""
    print("\n" + "=" * 70)
    print("Testing Output Directory Creation...")
    print("=" * 70)
    
    try:
        test_dir = Path("output_test")
        test_dir.mkdir(parents=True, exist_ok=True)
        
        # Try creating a file
        test_file = test_dir / "test.txt"
        test_file.write_text("test")
        
        if test_file.exists():
            test_file.unlink()
            test_dir.rmdir()
            print("✅ Output directory can be created and written to")
            return True
        else:
            print("❌ Failed to create test file")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "MEDIA EXTRACTOR - TEST & VALIDATION" + " " * 19 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    results = []
    
    # Run tests
    results.append(("Dependencies", test_imports()))
    results.append(("Script Syntax", test_script_syntax()))
    results.append(("File Structure", test_file_structure()))
    results.append(("Script Imports", test_imports_in_script()))
    results.append(("SrcsetParser", test_srcset_parser()))
    results.append(("URLResolver", test_url_resolver()))
    results.append(("Configuration", test_config()))
    results.append(("Output Directory", test_output_directory()))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10s} - {test_name}")
    
    total_tests = len(results)
    passed_tests = sum(1 for _, p in results if p)
    
    print()
    print(f"Results: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 All tests passed! Script is ready to use.")
        print("\nNext steps:")
        print("1. Edit urls.txt with your URLs")
        print("2. Run: python3 media_extractor.py")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
