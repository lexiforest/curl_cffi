from curl_cffi.fingerprints import FingerprintManager


def test_is_pro():
    assert FingerprintManager.is_pro() is False
