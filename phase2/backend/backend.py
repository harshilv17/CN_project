#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json


class BackendHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        backend = self.server.backend_name

        if self.path == "/":
            response = {
                "backend": backend,
                "message": f"Backend {backend} is running"
            }

            self.send_json_response(200, response)
            return

        elif self.path == "/api/status":
            response = {
                "backend": backend,
                "status": "ok"
            }

            self.send_json_response(200, response)
            return

        elif self.path == "/cached":
            etag = '"team-cache-v1"'

            # Check conditional request
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return

            response = {
                "backend": backend,
                "cached": True
            }

            body = json.dumps(response).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Backend", backend)
            self.send_header("Cache-Control", "max-age=60")
            self.send_header("ETag", etag)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()

            self.wfile.write(body)
            return

        else:
            response = {
                "backend": backend,
                "error": "Not Found"
            }

            self.send_json_response(404, response)
            return

    def send_json_response(self, status_code, response):
        body = json.dumps(response).encode()

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Backend", self.server.backend_name)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.server.backend_name}] {format % args}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--backend",
        required=True,
        choices=["A", "B"]
    )

    parser.add_argument(
        "--port",
        required=True,
        type=int
    )

    args = parser.parse_args()

    server = HTTPServer(
        ("0.0.0.0", args.port),
        BackendHandler
    )

    server.backend_name = args.backend

    print(
        f"Backend {args.backend} running "
        f"on 0.0.0.0:{args.port}"
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
