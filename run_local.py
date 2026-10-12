"""
run_local.py  --  run the whole project on your own computer (no Vercel needed).

    python run_local.py

Then open http://localhost:8000  (it opens automatically).
Serves public/index.html and the same Python API (api/route.py) that Vercel uses.
Press Ctrl+C in the terminal to stop.
"""
import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, ROOT)

import route  # api/route.py


class LocalHandler(SimpleHTTPRequestHandler):
    _send = route.handler._send  # reuse the JSON helper

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(ROOT, "public"), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/route"):
            return route.handler.do_GET(self)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/route"):
            return route.handler.do_POST(self)
        self.send_error(404)


if __name__ == "__main__":
    port = 8000
    print(f"Running at http://localhost:{port}  (Ctrl+C to stop)")
    webbrowser.open(f"http://localhost:{port}")
    HTTPServer(("127.0.0.1", port), LocalHandler).serve_forever()
