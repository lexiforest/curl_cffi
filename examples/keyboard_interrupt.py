import time

from curl_cffi import requests


URL = "https://httpbin.org/bytes/1024"
CALLBACK_DURATION = 120


def main() -> None:
    started_at = time.monotonic()
    received = 0

    def on_chunk(chunk: bytes) -> int:
        nonlocal received
        received += len(chunk)
        print(f"Received {received} bytes and entered the callback.", flush=True)

        callback_deadline = time.monotonic() + CALLBACK_DURATION
        while time.monotonic() < callback_deadline:
            elapsed = time.monotonic() - started_at
            print(f"Still inside the callback after {elapsed:.1f}s; press Ctrl-C...")
            time.sleep(1)

        return len(chunk)

    print("Starting an httpbin download with a two-minute callback.")
    print("Press Ctrl-C after the callback starts.")
    try:
        response = requests.get(
            URL,
            content_callback=on_chunk,
            timeout=300,
        )
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt propagated cleanly; the transfer was aborted.")
        raise SystemExit(130) from None
    except requests.RequestsError as exc:
        print(f"\nUnexpected RequestsError: {exc}")
        raise
    else:
        print(f"Download completed with HTTP {response.status_code}.")


if __name__ == "__main__":
    main()
