from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler, BaseHTTPRequestHandler, HTTPServer
import threading, os, json
from config import Colors

class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

def start_static_server(root, port):
    os.chdir(root)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), SilentHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd

def start_api_server(on_run, on_flex, on_stop, host="127.0.0.1", port=8321):
    """
    Starts a HTTP server in a daemon thread.
    POST /api/run  { "name": "<controller name>" } : starts the named controller.
    POST /api/stop { "name": "<controller name>" } : stops the named controller.
    POST /api/flexible-run { "name": "<controller name>" } : starts the flexible controller.
    """
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return 
        
        def _json(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            # CORS preflight
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"
            if self.path == "/api/run":
                try:
                    data = json.loads(raw)
                    name = (data.get("name") or "").strip()
                    ok, msg = on_run(name)
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})
            elif self.path == "/api/flexible-run":
                try:
                    data = json.loads(raw)
                    name = (data.get("name") or "").strip()
                    ok, msg = on_flex(name) 
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})
            elif self.path == "/api/stop":
                try:
                    data = json.loads(raw)
                    name = (data.get("name") or "").strip()
                    ok, msg = on_stop(name) 
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})
            else:
                return self._json(404, {"ok": False, "message": "Not found"})

    srv = HTTPServer((host, port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(Colors.yellow(f"[API] listening on http://{host}:{port}"))
    return srv