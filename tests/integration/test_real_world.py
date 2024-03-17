from curl_cffi import requests


def test_post_with_no_body():
    r = requests.post("https://shopee.co.id/api/v2/authentication/get_active_login_page")
    assert r.status_code == 200
