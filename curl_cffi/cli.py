import argparse
import sys
import curl_cffi


def main():
    parser = argparse.ArgumentParser(
        prog="curl-cffi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="A curl-like tool using curl-cffi with browser impersonation",
    )
    parser.add_argument(
        "-i",
        "--impersonate",
        default="chrome",
        help="Browser to impersonate",
    )
    parser.add_argument("urls", nargs="+", help="URLs to fetch")

    args = parser.parse_args()

    for url in args.urls:
        try:
            response = curl_cffi.requests.get(url, impersonate=args.impersonate)
            print(response.text)
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
