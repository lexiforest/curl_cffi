import curl_cffi

# OKHTTP impersonatation examples
# credits: https://github.com/bogdanfinn/tls-client/blob/master/profiles/contributed_custom_profiles.go

url = "https://tls.browserleaks.com/json"

okhttp4_android10_ja3 = ",".join(
    [
        "771",
        "4865-4866-4867-49195-49196-52393-49199-49200-52392-49171-49172-156-157-47-53",
        "0-23-65281-10-11-35-16-5-13-51-45-43-21",
        "29-23-24",
        "0",
    ]
)

okhttp4_android10_akamai = "4:16777216|16711681|0|m,p,a,s"

extra_fp = {
    "tls_signature_algorithms": [
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
    # other options:
    # tls_min_version: int = CurlSslVersion.TLSv1_2
    # tls_grease: bool = False
    # tls_permute_extensions: bool = False
    # tls_cert_compression: Literal["zlib", "brotli"] = "brotli"
    # tls_signature_algorithms: Optional[List[str]] = None
    # http2_stream_weight: int = 256
    # http2_stream_exclusive: int = 1
    # See requests/impersonate.py and tests/unittest/test_impersonate.py for more
    # examples
}


r = curl_cffi.get(
    url, ja3=okhttp4_android10_ja3, akamai=okhttp4_android10_akamai, extra_fp=extra_fp
)

print(r.json())


# Special firefox extension


# ruff: noqa: E501
extra_fp = {
    "tls_delegated_credential": "ecdsa_secp256r1_sha256:ecdsa_secp384r1_sha384:ecdsa_secp521r1_sha512:ecdsa_sha1",
    "tls_record_size_limit": 4001,
}

# Note that the ja3 string also includes extensiion: 28 and 34
# ruff: noqa: E501
ja3 = "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-34-18-51-43-13-45-28-27-65037,4588-29-23-24-25-256-257,0"

r = curl_cffi.get(url, ja3=ja3, extra_fp=extra_fp)
print(r.json())
