#!/usr/bin/env python3
"""
Test script for curl_cffi Unicode certificate path fix
"""

import sys
import os
from pathlib import Path

# Add the local curl_cffi to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'curl_cffi'))

def test_unicode_cert_fix():
    """Test that the Unicode certificate path fix works"""
    print("🧪 Testing curl_cffi Unicode Certificate Path Fix")
    print("=" * 60)
    
    try:
        import curl_cffi
        print(f"✅ curl_cffi imported successfully")
        print(f"   Version: {curl_cffi.__version__}")
    except ImportError as e:
        print(f"❌ Failed to import curl_cffi: {e}")
        return False
    
    try:
        import certifi
        cert_path = certifi.where()
        print(f"📜 Original certificate path: {cert_path}")
        
        # Check if path contains non-ASCII characters
        try:
            cert_path.encode('ascii')
            print("ℹ️  Certificate path is ASCII-safe")
        except UnicodeEncodeError:
            print("⚠️  Certificate path contains non-ASCII characters")
            print("   Our fix should handle this automatically")
    except ImportError as e:
        print(f"❌ Failed to import certifi: {e}")
        return False
    
    # Test the fix
    print("\n🔧 Testing Unicode-safe certificate path function...")
    try:
        from curl_cffi.curl import _get_safe_cacert_path, DEFAULT_CACERT
        
        print(f"📁 DEFAULT_CACERT: {DEFAULT_CACERT}")
        
        # Test with original path
        safe_path = _get_safe_cacert_path(cert_path)
        print(f"🔒 Safe path: {safe_path}")
        
        if safe_path != cert_path:
            print("✅ Fix activated: Created temporary ASCII-safe certificate path")
        else:
            print("ℹ️  Fix not needed: Original path is already ASCII-safe")
            
    except Exception as e:
        print(f"❌ Error testing fix function: {e}")
        return False
    
    # Test actual HTTPS request
    print("\n🌐 Testing HTTPS Request...")
    try:
        response = curl_cffi.get("https://httpbin.org/json", timeout=10)
        print(f"✅ HTTPS request successful!")
        print(f"   Status code: {response.status_code}")
        print(f"   Response length: {len(response.content)} bytes")
        
        # Test with Google (more strict SSL)
        print("\n🔍 Testing Google HTTPS...")
        response = curl_cffi.get("https://www.google.com", timeout=10)
        print(f"✅ Google HTTPS request successful!")
        print(f"   Status code: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"❌ HTTPS request failed: {e}")
        return False

if __name__ == "__main__":
    success = test_unicode_cert_fix()
    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed! Unicode certificate path fix is working!")
        sys.exit(0)
    else:
        print("💥 Tests failed! Fix needs more work.")
        sys.exit(1) 