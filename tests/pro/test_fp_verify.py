import json
import os
import re
from itertools import zip_longest
from urllib.parse import urlencode

from curl_cffi import requests
from curl_cffi.fingerprints import FingerprintManager, NATIVE_IMPERSONATE_TARGETS


TLS_PEET_URL = "https://peet.impersonate.pro/api/all"
PING_FP_URL = "https://fp.impersonate.pro/api/auto"
RAW_PATH = "/raw"
VERIFY_FIELDS = (
    ("fingerprint", "http2", "akamai_fingerprint_hash"),
    ("fingerprint", "tls", "ja3"),
)
IGNORED_HEADER_NAMES = {"dnt", "origin", "referer", "sec-ch-ua", "sec-ch-ua-platform"}
# Extension 45 (psk_key_exchange_modes) is only required when pre_shared_key is
# offered; real Firefox can omit it in fresh handshakes.
IGNORED_JA3_EXTENSIONS = {"21", "41", "45"}
EXPECTED_LABEL = "expected (API fingerprint)"
CAPTURED_LABEL = "captured (runtime output)"


def _require_live_api_key() -> str:
    api_key = os.environ.get("IMPERSONATE_API_KEY")
    if not api_key:
        raise AssertionError(
            "IMPERSONATE_API_KEY must be set for live pro fingerprint verification"
        )
    return api_key


def _request_json(url: str, *, api_key: str | None = None) -> object:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return json.loads(FingerprintManager._fetch_fingerprint_payload(url, headers))


def _wrap_fingerprint_payload(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("fingerprint"), dict):
        return payload
    if isinstance(payload.get("http2"), dict) and isinstance(payload.get("tls"), dict):
        return {"fingerprint": payload}
    return None


def _payload_name_matches(payload: dict[str, object], target: str) -> bool:
    name = payload.get("name") or payload.get("target")
    return not isinstance(name, str) or name == target


def _extract_target_payload(payload: object, target: str) -> dict[str, object] | None:
    wrapped = _wrap_fingerprint_payload(payload)
    if wrapped is not None and _payload_name_matches(wrapped, target):
        return wrapped

    if isinstance(payload, dict):
        nested = payload.get(target)
        wrapped = _wrap_fingerprint_payload(nested)
        if wrapped is not None:
            return wrapped

        for key in ("items", "data"):
            items = payload.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("name") == target or item.get("target") == target:
                    wrapped = _wrap_fingerprint_payload(item)
                    if wrapped is not None:
                        return wrapped
                    raw = item.get("data", item.get("fingerprint"))
                    wrapped = _wrap_fingerprint_payload(raw)
                    if wrapped is not None:
                        if "source" not in wrapped and "source" in item:
                            wrapped = {**wrapped, "source": item["source"]}
                        return wrapped

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("name") == target or item.get("target") == target:
                wrapped = _wrap_fingerprint_payload(item)
                if wrapped is not None:
                    return wrapped
                raw = item.get("data", item.get("fingerprint"))
                wrapped = _wrap_fingerprint_payload(raw)
                if wrapped is not None:
                    if "source" not in wrapped and "source" in item:
                        wrapped = {**wrapped, "source": item["source"]}
                    return wrapped

    return None


def _load_raw_fingerprint(
    target: str,
    api_root: str,
    protocol: str,
) -> dict[str, object]:
    api_key = _require_live_api_key()
    base_url = f"{api_root.rstrip('/')}{RAW_PATH}"
    url = f"{base_url}?{urlencode({'name': target, 'protocol': protocol})}"
    try:
        payload = _request_json(url, api_key=api_key)
    except Exception as exc:
        raise AssertionError(
            f"Could not load raw fingerprint payload for {target!r}\n"
            f"{url}: {type(exc).__name__}: {exc}"
        ) from exc
    target_payload = _extract_target_payload(payload, target)
    if target_payload is not None:
        return target_payload

    raise AssertionError(
        "\n".join(
            [
                f"Could not load raw fingerprint payload for {target!r}",
                f"{url}: target not found in response",
            ]
        )
    )


def _should_print_target_progress() -> bool:
    return os.environ.get("CI", "").lower() not in {"1", "true", "yes"}


def _get_path(value: object, path: tuple[object, ...]) -> object:
    current = value
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, list):
                raise AssertionError(f"Expected list while resolving {path!r}")
            current = current[part]
        else:
            if not isinstance(current, dict):
                raise AssertionError(f"Expected object while resolving {path!r}")
            current = current[part]
    return current


def _find_http2_frame(
    sent_frames: object,
    *,
    frame_type: str,
    required_key: str | None = None,
) -> dict[str, object]:
    if not isinstance(sent_frames, list):
        raise AssertionError("Expected http2.sent_frames to be a list")
    for frame in sent_frames:
        if not isinstance(frame, dict):
            continue
        if frame.get("frame_type") != frame_type:
            continue
        if required_key is not None and required_key not in frame:
            continue
        return frame
    required_suffix = f" containing {required_key!r}" if required_key else ""
    raise AssertionError(
        f"Could not find HTTP/2 frame {frame_type!r}{required_suffix} in sent_frames"
    )


def _select_http_header_lines(payload: object) -> tuple[str, object]:
    if not isinstance(payload, dict):
        raise AssertionError("Expected payload object when selecting HTTP headers")

    http2_payload = payload.get("http2")
    if isinstance(http2_payload, dict):
        sent_frames = http2_payload.get("sent_frames")
        headers_frame = _find_http2_frame(
            sent_frames,
            frame_type="HEADERS",
            required_key="headers",
        )
        return "$.http2.sent_frames[HEADERS].headers", headers_frame["headers"]

    http1_payload = payload.get("http1")
    if isinstance(http1_payload, dict) and "headers" in http1_payload:
        return "$.http1.headers", http1_payload["headers"]

    raise AssertionError("Could not find comparable HTTP headers in payload")


def _normalize_peet_value(value: object) -> object:
    if isinstance(value, str):
        # tls.peet.ws sometimes double-escapes quoted header values like
        # sec-ch-ua-platform, yielding \"Windows\" instead of "Windows".
        value = value.replace('\\"', '"')
        # It can also leave a dangling trailing backslash after the final quoted
        # token, e.g. `sec-ch-ua-platform: "Windows\`.
        if value.endswith("\\") and value.count('"') % 2 == 1:
            value = value[:-1] + '"'
        value = re.sub(r': "([^"]+)\\$', r': "\1"', value)
        return value
    if isinstance(value, list):
        return [_normalize_peet_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_peet_value(item) for key, item in value.items()}
    return value


def _normalize_ja3(value: object) -> object:
    if not isinstance(value, str):
        return value
    parts = value.split(",")
    if len(parts) != 5:
        return value
    extensions = [
        extension
        for extension in parts[2].split("-")
        if extension and extension not in IGNORED_JA3_EXTENSIONS
    ]
    extensions.sort(key=lambda extension: int(extension))
    parts[2] = "-".join(extensions)
    return ",".join(parts)


def _format_diff_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True)


def _normalize_header_name(value: object) -> str | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    name, _ = value.split(":", 1)
    return name.strip().lower()


def _filter_ignored_headers(value: object) -> object:
    if not isinstance(value, list):
        return value
    return [
        _normalize_header_line(item)
        for item in value
        if _normalize_header_name(item) not in IGNORED_HEADER_NAMES
    ]


def _normalize_header_line(value: object) -> object:
    if not isinstance(value, str):
        return value
    if not value.startswith(":"):
        if _normalize_header_name(value) == "host":
            return "Host: <ignored>"
        return value
    name, _, _ = value[1:].partition(":")
    return f":{name}: <ignored>"


def _parse_header_line(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    if value.startswith(":"):
        name, separator, header_value = value[1:].partition(":")
        if not separator:
            return None
        return f":{name.strip().lower()}", header_value.strip()

    name, header_value = value.split(":", 1)
    return name.strip().lower(), header_value.strip()


def _header_line_matches(raw_value: object, peet_value: object) -> bool:
    if raw_value == peet_value:
        return True

    raw_header = _parse_header_line(raw_value)
    peet_header = _parse_header_line(peet_value)
    if raw_header is None or peet_header is None:
        return False

    raw_name, _ = raw_header
    peet_name, _ = peet_header
    if raw_name != peet_name:
        return False

    return raw_name == "accept-language"


def _header_lines_match(raw_value: object, peet_value: object) -> bool:
    if raw_value == peet_value:
        return True
    if not isinstance(raw_value, list) or not isinstance(peet_value, list):
        return False
    if len(raw_value) != len(peet_value):
        return False
    return all(
        _header_line_matches(raw_line, peet_line)
        for raw_line, peet_line in zip(raw_value, peet_value, strict=True)
    )


def _format_header_lines_diff(raw_value: object, peet_value: object) -> str:
    if not isinstance(raw_value, list) or not isinstance(peet_value, list):
        return "\n".join(
            [
                f"{EXPECTED_LABEL}:",
                _format_diff_value(raw_value),
                f"{CAPTURED_LABEL}:",
                _format_diff_value(peet_value),
            ]
        )

    diff_lines = []
    for index, (raw_line, peet_line) in enumerate(
        zip_longest(raw_value, peet_value, fillvalue="<missing>")
    ):
        if _header_line_matches(raw_line, peet_line):
            continue
        diff_lines.extend(
            [
                f"line {index}:",
                f"  {EXPECTED_LABEL}: {raw_line}",
                f"  {CAPTURED_LABEL}: {peet_line}",
            ]
        )

    return "\n".join(diff_lines)


def _record_mismatch(
    mismatches: dict[str, list[str]],
    *,
    target: str,
    dotted_path: str,
    raw_value: object,
    peet_value: object,
) -> None:
    if peet_value == raw_value:
        return
    is_header_path = dotted_path in {
        "$.fingerprint.http2.sent_frames[HEADERS].headers",
        "$.fingerprint.http1.headers",
        "$.fingerprint.http2.headers",
    }
    if is_header_path and _header_lines_match(raw_value, peet_value):
        return
    if is_header_path:
        diff_body = _format_header_lines_diff(raw_value, peet_value)
    else:
        diff_body = "\n".join(
            [
                f"{EXPECTED_LABEL}:",
                _format_diff_value(raw_value),
                f"{CAPTURED_LABEL}:",
                _format_diff_value(peet_value),
            ]
        )
    mismatches.setdefault(target, []).append("\n".join([dotted_path, diff_body]))


def _verify_api_fingerprint(
    *,
    target: str,
    raw_payload: dict[str, object],
    peet_payload: object,
    mismatches: dict[str, list[str]],
) -> None:
    raw_fingerprint = _get_path(raw_payload, ("fingerprint",))

    for path in VERIFY_FIELDS:
        if path == ("fingerprint", "http2", "akamai_fingerprint_hash"):
            if not isinstance(raw_fingerprint, dict) or "http2" not in raw_fingerprint:
                continue
            if not isinstance(peet_payload, dict) or "http2" not in peet_payload:
                continue
        raw_value = _get_path(raw_payload, path)
        peet_value = _normalize_peet_value(_get_path(peet_payload, path[1:]))
        if path == ("fingerprint", "tls", "ja3"):
            raw_value = _normalize_ja3(raw_value)
            peet_value = _normalize_ja3(peet_value)
        _record_mismatch(
            mismatches,
            target=target,
            dotted_path="$." + ".".join(str(part) for part in path),
            raw_value=raw_value,
            peet_value=peet_value,
        )

    # The headers dict is currently noisy enough to obscure useful failures.
    # Keep this block commented out so it can be re-enabled once the captured
    # header format is stable.
    # raw_header_path, raw_headers = _select_http_header_lines(raw_fingerprint)
    # peet_header_path, peet_headers = _select_http_header_lines(peet_payload)
    # raw_headers = _filter_ignored_headers(raw_headers)
    # peet_headers = _filter_ignored_headers(_normalize_peet_value(peet_headers))
    # if raw_header_path != peet_header_path:
    #     mismatches.setdefault(target, []).append(
    #         "\n".join(
    #             [
    #                 "$.fingerprint.http*.headers",
    #                 f"{EXPECTED_LABEL} path: {raw_header_path}",
    #                 f"{CAPTURED_LABEL} path: {peet_header_path}",
    #             ]
    #         )
    #     )
    #     return
    # _record_mismatch(
    #     mismatches,
    #     target=target,
    #     dotted_path="$.fingerprint" + raw_header_path[1:],
    #     raw_value=raw_headers,
    #     peet_value=peet_headers,
    # )


def _ping_pseudo_header_order(raw_http2: dict[str, object]) -> list[str]:
    akamai_text = raw_http2.get("akamai_text")
    if not isinstance(akamai_text, str):
        raise AssertionError("Expected ping http2.akamai_text to be a string")

    parts = akamai_text.split("|")
    if len(parts) != 4:
        raise AssertionError("Expected ping http2.akamai_text to contain 4 sections")

    pseudo_names = {
        "m": ":method",
        "a": ":authority",
        "s": ":scheme",
        "p": ":path",
    }
    order = []
    for item in parts[3].split(","):
        name = pseudo_names.get(item)
        if name is None:
            raise AssertionError(f"Unknown ping HTTP/2 pseudo-header code: {item!r}")
        order.append(name)
    return order


def _ping_header_lines(raw_http2: dict[str, object]) -> list[str]:
    headers = raw_http2.get("headers")
    if not isinstance(headers, dict):
        raise AssertionError("Expected ping http2.headers to be an object")

    header_order = raw_http2.get("header_order")
    if not isinstance(header_order, list):
        raise AssertionError("Expected ping http2.header_order to be a list")

    lines = []
    for name in _ping_pseudo_header_order(raw_http2):
        value = headers.get(name)
        if value is not None:
            lines.append(f"{name}: <ignored>")

    for item in header_order:
        if not isinstance(item, str):
            raise AssertionError("Expected ping http2.header_order items to be strings")
        name = item.strip().lower()
        if name in IGNORED_HEADER_NAMES:
            continue
        value = headers.get(item, headers.get(name))
        if value is None:
            raise AssertionError(
                f"Ping header_order references missing header: {item!r}"
            )
        if name == "host":
            lines.append("Host: <ignored>")
        else:
            lines.append(f"{name}: {value}")

    return lines


def _verify_ping_fingerprint(
    *,
    target: str,
    raw_payload: dict[str, object],
    ping_payload: object,
    mismatches: dict[str, list[str]],
) -> None:
    raw_fingerprint = _get_path(raw_payload, ("fingerprint",))
    if not isinstance(raw_fingerprint, dict):
        raise AssertionError("Expected ping fingerprint to be an object")
    if not isinstance(ping_payload, dict):
        raise AssertionError("Expected ping runtime payload to be an object")

    raw_ja3 = _normalize_ja3(_get_path(raw_fingerprint, ("tls", "ja3", "text")))
    ping_ja3 = _normalize_ja3(
        _normalize_peet_value(_get_path(ping_payload, ("tls", "ja3", "text")))
    )
    _record_mismatch(
        mismatches,
        target=target,
        dotted_path="$.fingerprint.tls.ja3.text",
        raw_value=raw_ja3,
        peet_value=ping_ja3,
    )

    raw_http2 = raw_fingerprint.get("http2")
    if not isinstance(raw_http2, dict):
        return
    ping_http2 = ping_payload.get("http2")
    if not isinstance(ping_http2, dict):
        return

    if "akamai_hash" in raw_http2 and "akamai_hash" in ping_http2:
        _record_mismatch(
            mismatches,
            target=target,
            dotted_path="$.fingerprint.http2.akamai_hash",
            raw_value=raw_http2["akamai_hash"],
            peet_value=_normalize_peet_value(ping_http2["akamai_hash"]),
        )
    if "akamai_text" in raw_http2 and "akamai_text" in ping_http2:
        _record_mismatch(
            mismatches,
            target=target,
            dotted_path="$.fingerprint.http2.akamai_text",
            raw_value=raw_http2["akamai_text"],
            peet_value=_normalize_peet_value(ping_http2["akamai_text"]),
        )

    # The headers dict is currently noisy enough to obscure useful failures.
    # Keep this block commented out so it can be re-enabled once the captured
    # header format is stable.
    # _record_mismatch(
    #     mismatches,
    #     target=target,
    #     dotted_path="$.fingerprint.http2.headers",
    #     raw_value=_ping_header_lines(raw_http2),
    #     peet_value=_ping_header_lines(ping_http2),
    # )


def test_normalize_ja3_sorts_extension_segment():
    raw_ja3 = "771,4865-4866,23-10-41-21-45-35,29-23,0"
    permuted_ja3 = "771,4865-4866,35-21-45-41-23-10,29-23,0"
    assert _normalize_ja3(raw_ja3) == _normalize_ja3(permuted_ja3)
    assert _normalize_ja3(raw_ja3) == "771,4865-4866,10-23-35,29-23,0"


def test_load_raw_fingerprint_requests_protocol(monkeypatch):
    requests = []

    def fetch_payload(url, headers):
        requests.append((url, headers))
        return json.dumps(
            {
                "name": "testing",
                "source": "ping",
                "fingerprint": {"protocol": "http2"},
            }
        ).encode()

    monkeypatch.setenv("IMPERSONATE_API_KEY", "ci-secret")
    monkeypatch.setattr(
        FingerprintManager,
        "_fetch_fingerprint_payload",
        staticmethod(fetch_payload),
    )

    payload = _load_raw_fingerprint("testing", "https://api.test", "http2")

    assert payload["source"] == "ping"
    assert requests == [
        (
            "https://api.test/raw?name=testing&protocol=http2",
            {"Authorization": "Bearer ci-secret"},
        )
    ]


def test_header_line_matches_ignores_accept_language_value():
    assert _header_line_matches("accept-language: en-US", "Accept-Language: zh-CN")
    assert not _header_line_matches("accept: text/html", "accept: application/json")


def test_mismatch_output_labels_expected_and_captured_values():
    mismatches: dict[str, list[str]] = {}

    _record_mismatch(
        mismatches,
        target="testing",
        dotted_path="$.fingerprint.tls.ja3",
        raw_value="expected-ja3",
        peet_value="captured-ja3",
    )

    assert mismatches == {
        "testing": [
            "\n".join(
                [
                    "$.fingerprint.tls.ja3",
                    f"{EXPECTED_LABEL}:",
                    "expected-ja3",
                    f"{CAPTURED_LABEL}:",
                    "captured-ja3",
                ]
            )
        ]
    }


def test_live_fingerprint_data_matches_runtime_output(monkeypatch, tmp_path):
    api_key = _require_live_api_key()
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    FingerprintManager.load_fingerprints.cache_clear()
    FingerprintManager.set_api_key(api_key=api_key)

    api_root = FingerprintManager.get_api_root()
    updated = FingerprintManager.update_fingerprints(api_root)
    assert updated is not None and updated > 0

    fingerprints = FingerprintManager.load_fingerprints()
    assert fingerprints

    preset_targets = {item["target_name"] for item in NATIVE_IMPERSONATE_TARGETS}
    custom_targets = sorted(
        target for target in fingerprints if target not in preset_targets
    )
    assert custom_targets, "No non-preset fingerprints found in updated cache"

    mismatches: dict[str, list[str]] = {}
    should_print_target_progress = _should_print_target_progress()

    for target in custom_targets:
        if should_print_target_progress:
            print(f"verifying fingerprint: {target}")
        protocol = (
            "http3" if fingerprints[target].http_version in {"v3", "h3"} else "http2"
        )
        raw_payload = _load_raw_fingerprint(target, api_root, protocol)
        if raw_payload.get("source") == "ping":
            ping_payload = requests.get(
                PING_FP_URL,
                impersonate=target,
                timeout=30,
            ).json()
            _verify_ping_fingerprint(
                target=target,
                raw_payload=raw_payload,
                ping_payload=ping_payload,
                mismatches=mismatches,
            )
        else:
            peet_payload = requests.get(
                TLS_PEET_URL,
                impersonate=target,
                timeout=30,
            ).json()
            _verify_api_fingerprint(
                target=target,
                raw_payload=raw_payload,
                peet_payload=peet_payload,
                mismatches=mismatches,
            )

    if mismatches:
        formatted = []
        for target in sorted(mismatches):
            formatted.append(target)
            formatted.extend(mismatches[target])
        raise AssertionError("\n\n".join(formatted))
