from curl_cffi import requests
from curl_cffi.requests.impersonate import ExtraFingerprints

# OKHTTP impersonatation examples
# credits: https://github.com/bogdanfinn/tls-client/blob/master/profiles/contributed_custom_profiles.go

url = "https://tls.browserleaks.com/json"

okhttp4_android10_ja3 = ",".join(
    [
        "771",
        "4865-4866-4867-49195-49196-52393-49199-49200-52392-49171-49172-156-157-47-53",
        "0-23-65281-10-11-35-16-5-13-51-45-43-18-21",  # FIXME: 18 should not be here.
        "29-23-24",
        "0",
    ]
)

okhttp4_android10_akamai = "4:16777216|16711681|0|m,p,a,s"

extra_fp = ExtraFingerprints(
    tls_signature_algorithms=[
        "ecdsa_secp256r1_sha256",
        "rsa_pss_rsae_sha256",
        "rsa_pkcs1_sha256",
        "ecdsa_secp384r1_sha384",
        "rsa_pss_rsae_sha384",
        "rsa_pkcs1_sha384",
        "rsa_pss_rsae_sha512",
        "rsa_pkcs1_sha512",
        "rsa_pkcs1_sha1",
    ]
)


r = requests.get(
    url, ja3=okhttp4_android10_ja3, akamai=okhttp4_android10_akamai, extra_fp=extra_fp
)
print(r.json())
