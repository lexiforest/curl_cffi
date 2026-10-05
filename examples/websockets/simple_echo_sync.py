#!/usr/bin/env python3
from curl_cffi import Response, Session


def main() -> None:
    """Test basic echo synchronously"""
    with Session[Response]() as s:
        print("Connecting to Postman Echo...")
        with s.ws_connect("wss://ws.postman-echo.com/raw") as ws:
            message = "Hello from curl_cffi!"
            print(f">>> Sending: {message}")
            _ = ws.send_str(payload=message)

            response: str = ws.recv_str()
            print(f"<<< Received: {response}")

            assert message == response
            print("Echo test passed!")


if __name__ == "__main__":
    main()
