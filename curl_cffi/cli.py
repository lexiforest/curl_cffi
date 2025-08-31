import argparse
import sys
import curl_cffi


from curl_cffi.utils import update_market_share, update_profiles, read_profiles



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
    parser.add_argument(
        "--update",
        help= "Update browser profiles and market share from impersonate.pro server"
    )
    parser.add_argument(
        "--list-profiles",
        help="List all supported browser profiles"
    )
    parser.add_argument("urls", nargs="+", help="URLs to fetch")

    args = parser.parse_args()

    if args.update:
        update_market_share()
        update_profiles()
    elif args.list_profiles:
        profiles = read_profiles()
        for profile in profiles.keys():
            print(profile)
    else:
        for url in args.urls:
            try:
                response = curl_cffi.requests.get(url, impersonate=args.impersonate)
                print(response.text)
            except Exception as e:
                print(f"Error fetching {url}: {e}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
