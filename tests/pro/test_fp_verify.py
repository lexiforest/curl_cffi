import json
import os
import re
from itertools import zip_longest
from urllib.parse import urlencode

from curl_cffi import requests
from curl_cffi.fingerprints import FingerprintManager, NATIVE_IMPERSONATE_TARGETS


TLS_PEET_URL = "https://peet.impersonate.pro/api/all"
RAW_PATH = "/raw"
VERIFY_FIELDS = (
    ("fingerprint", "http2", "akamai_fingerprint_hash"),
    ("fingerprint", "tls", "ja3"),
)
IGNORED_HEADER_NAMES = {"dnt", "sec-ch-ua", "sec-ch-ua-platform"}
IGNORED_JA3_EXTENSIONS = {"21", "41"}


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
                    return wrapped

    return None


def _load_raw_fingerprint(target: str, api_root: str) -> dict[str, object]:
    api_key = _require_live_api_key()
    base_url = f"{api_root.rstrip('/')}{RAW_PATH}"
    url = f"{base_url}?{urlencode({'name': target})}"
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


def _format_header_lines_diff(raw_value: object, peet_value: object) -> str:
    if not isinstance(raw_value, list) or not isinstance(peet_value, list):
        return "\n".join(
            [
                "raw:",
                _format_diff_value(raw_value),
                "peet:",
                _format_diff_value(peet_value),
            ]
        )

    diff_lines = []
    for index, (raw_line, peet_line) in enumerate(
        zip_longest(raw_value, peet_value, fillvalue="<missing>")
    ):
        if raw_line == peet_line:
            continue
        diff_lines.extend(
            [
                f"line {index}:",
                f"  raw:  {raw_line}",
                f"  peet: {peet_line}",
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
    if dotted_path in {
        "$.fingerprint.http2.sent_frames[HEADERS].headers",
        "$.fingerprint.http1.headers",
    }:
        diff_body = _format_header_lines_diff(raw_value, peet_value)
    else:
        diff_body = "\n".join(
            [
                "raw:",
                _format_diff_value(raw_value),
                "peet:",
                _format_diff_value(peet_value),
            ]
        )
    mismatches.setdefault(target, []).append("\n".join([dotted_path, diff_body]))


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
        peet_payload = requests.get(TLS_PEET_URL, impersonate=target, timeout=30).json()
        raw_payload = _load_raw_fingerprint(target, api_root)
        raw_fingerprint = _get_path(raw_payload, ("fingerprint",))

        for path in VERIFY_FIELDS:
            if path == ("fingerprint", "http2", "akamai_fingerprint_hash"):
                if (
                    not isinstance(raw_fingerprint, dict)
                    or "http2" not in raw_fingerprint
                ):
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

        raw_header_path, raw_headers = _select_http_header_lines(raw_fingerprint)
        peet_header_path, peet_headers = _select_http_header_lines(peet_payload)
        raw_headers = _filter_ignored_headers(raw_headers)
        peet_headers = _filter_ignored_headers(_normalize_peet_value(peet_headers))
        if raw_header_path != peet_header_path:
            mismatches.setdefault(target, []).append(
                "\n".join(
                    [
                        "$.fingerprint.http*.headers",
                        f"raw path:  {raw_header_path}",
                        f"peet path: {peet_header_path}",
                    ]
                )
            )
            continue
        _record_mismatch(
            mismatches,
            target=target,
            dotted_path="$.fingerprint" + raw_header_path[1:],
            raw_value=raw_headers,
            peet_value=peet_headers,
        )

    if mismatches:
        formatted = []
        for target in sorted(mismatches):
            formatted.append(target)
            formatted.extend(mismatches[target])
        raise AssertionError("\n\n".join(formatted))
