#!/usr/bin/env python3
"""Static file server for the playground/site with **no-cache** headers.

`python -m http.server` lets the browser cache JS/CSS/HTML, which during rapid frontend
iteration serves stale files (a control looks like it "does nothing" because old JS is running).
This server tells the browser never to cache, so every reload gets the current files.

Usage: python scripts/serve.py [PORT]   (serves the current working directory; run from repo root)
"""

from __future__ import annotations

import http.server
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8092


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), NoCacheHandler) as httpd:
        print(f"serving (no-cache) on http://localhost:{PORT}")
        httpd.serve_forever()
