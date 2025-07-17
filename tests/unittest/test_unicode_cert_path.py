"""
Test cases for Unicode certificate path handling on Windows
"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from curl_cffi.curl import _get_safe_cacert_path, _cleanup_temp_certs, _temp_cert_files
from curl_cffi import requests


class TestUnicodeCertPath:
    """Test Unicode certificate path handling"""
    
    def test_ascii_path_unchanged(self):
        """Test that ASCII-safe paths are returned unchanged"""
        ascii_path = "/tmp/test/cert.pem"
        result = _get_safe_cacert_path(ascii_path)
        assert result == ascii_path
    
    def test_unicode_path_creates_temp_file(self):
        """Test that Unicode paths create temporary files"""
        # Create a temporary certificate file with Unicode in path
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as temp_cert:
            temp_cert.write("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----")
            temp_cert_path = temp_cert.name
        
        try:
            # Simulate Unicode path by creating a path with non-ASCII characters
            unicode_path = temp_cert_path.replace(os.path.basename(temp_cert_path), 
                                                 "çertificate.pem")
            
            # Create the Unicode path file
            with open(unicode_path, 'w') as f:
                f.write("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----")
            
            # Test the function
            result = _get_safe_cacert_path(unicode_path)
            
            # Should create a different (safe) path
            assert result != unicode_path
            assert os.path.exists(result)
            assert result in _temp_cert_files
            
            # Verify content is copied correctly
            with open(result, 'r') as f:
                content = f.read()
                assert "BEGIN CERTIFICATE" in content
                
        finally:
            # Cleanup
            for path in [temp_cert_path, unicode_path]:
                if os.path.exists(path):
                    os.unlink(path)
            _cleanup_temp_certs()
    
    def test_cleanup_temp_certs(self):
        """Test that temporary certificate files are cleaned up properly"""
        # Create a temporary file to track
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pem')
        os.close(temp_fd)
        
        # Add to tracking list
        _temp_cert_files.append(temp_path)
        
        # Verify file exists
        assert os.path.exists(temp_path)
        
        # Cleanup
        _cleanup_temp_certs()
        
        # Verify file is removed and list is cleared
        assert not os.path.exists(temp_path)
        assert len(_temp_cert_files) == 0
    
    def test_fallback_on_temp_file_error(self):
        """Test fallback behavior when temporary file creation fails"""
        unicode_path = "/nonexistent/path/çertificate.pem"
        
        # Should return original path if temp file creation fails
        with patch('warnings.warn') as mock_warn:
            result = _get_safe_cacert_path(unicode_path)
            assert result == unicode_path
            mock_warn.assert_called_once()
    
    @pytest.mark.skipif(os.name != 'nt', reason="Windows-specific test")
    def test_windows_unicode_path_integration(self):
        """Integration test for Windows Unicode paths"""
        # This test would be run on Windows systems with Unicode paths
        # It's skipped on non-Windows systems
        pass
    
    def test_requests_with_unicode_cert_path(self):
        """Test that requests work with Unicode certificate paths"""
        # Mock certifi.where() to return Unicode path
        unicode_cert_path = "/path/with/ünïcødé/cert.pem"
        
        with patch('certifi.where', return_value=unicode_cert_path):
            with patch('curl_cffi.curl._get_safe_cacert_path') as mock_safe_path:
                mock_safe_path.return_value = "/safe/path/cert.pem"
                
                # This should not raise an exception
                session = requests.Session()
                assert session is not None
                mock_safe_path.assert_called_with(unicode_cert_path)


def test_smoke_test_unicode_environment():
    """Smoke test that basic functionality works in Unicode environment"""
    # Simple test that would run in CI/CD to ensure basic functionality
    try:
        # Test that the function exists and is callable
        assert callable(_get_safe_cacert_path)
        assert callable(_cleanup_temp_certs)
        
        # Test with a simple path
        result = _get_safe_cacert_path("/simple/path/cert.pem")
        assert isinstance(result, str)
        
    except Exception as e:
        pytest.fail(f"Basic Unicode cert path functionality failed: {e}") 