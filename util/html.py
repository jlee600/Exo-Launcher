from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler, BaseHTTPRequestHandler, HTTPServer
import threading, os, json
from util.profiles import *
from util.ssh import ensure_master

# --------------------------
# Static File Server
# --------------------------
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

# --------------------------
# API Server
# --------------------------
def start_api_server(on_run, on_flex, on_stop, on_login=None, host="127.0.0.1", port=8321):
    """
    Starts a silent HTTP API server in a daemon thread.

    Control:
      POST /api/run            { "name": "<controller.py>" }
      POST /api/stop           { "name": "<controller.py>" }
      POST /api/flexible-run   { "name": "<controller.py>", "config": { ... } }

    Profiles & login:
      GET  /api/profiles                 -> { active, profiles }
      POST /api/profile/test   { name,user,host } -> { ok }
      POST /api/profile/save   { name,user,host } -> { ok }
      POST /api/login          { name }          -> { ok }
    """
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        # ---- tiny helpers ----
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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        # ---- routes ----
        def do_GET(self):
            if self.path == "/api/profiles":
                st = load_store()
                return self._json(200, {"active": st.get("active"), "profiles": st.get("profiles", {})})
            return self._json(404, {"ok": False, "message": "Not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"

            # --- Profiles: test ---
            if self.path == "/api/profile/test":
                try:
                    data = json.loads(raw)
                    name = (data.get("name") or "").strip()
                    user = (data.get("user") or "").strip()
                    host = (data.get("host") or "").strip()
                    ok, msg = validate_profile(name, user, host)
                    if not ok:
                        return self._json(400, {"ok": False, "message": msg})
                    if not ensure_master(user, host, persist="60s"):
                        return self._json(400, {"ok": False, "message": "SSH not reachable or handshake failed"})
                    return self._json(200, {"ok": True})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            # --- Profiles: save ---
            if self.path == "/api/profile/save":
                try:
                    data = json.loads(raw)
                    name = (data.get("name") or "").strip()
                    user = (data.get("user") or "").strip()
                    host = (data.get("host") or "").strip()
                    ok, msg = validate_profile(name, user, host)
                    if not ok:
                        return self._json(400, {"ok": False, "message": msg})
                    upsert_profile(name, user, host)
                    return self._json(200, {"ok": True})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            # --- Login: activate profile ---
            if self.path == "/api/login":
                try:
                    data = json.loads(raw)
                    prof_name = (data.get("name") or "").strip()
                    st = load_store()
                    prof = (st.get("profiles") or {}).get(prof_name)
                    if not prof:
                        return self._json(400, {"ok": False, "message": "Profile not found"})
                    user, host = prof["user"], prof["host"]
                    if not ensure_master(user, host, persist="5m"):
                        return self._json(400, {"ok": False, "message": "SSH not reachable"})
                    ok, msg = set_active(prof_name)
                    if not ok:
                        return self._json(400, {"ok": False, "message": msg})

                    try:
                        if on_login:
                            on_login(prof_name, user, host)
                    except Exception as e:
                        return self._json(500, {"ok": False, "message": f"Launcher hook failed: {e}"})
                    return self._json(200, {"ok": True})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            # --- Control: run ---
            if self.path == "/api/run":
                try:
                    data = json.loads(raw)
                    ctrl_name = (data.get("name") or "").strip()
                    _, user, host = get_active()
                    ok, msg = on_run(ctrl_name, user, host)
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            # --- Control: flexible run ---
            if self.path == "/api/flexible-run":
                try:
                    data = json.loads(raw)
                    ctrl_name = (data.get("name") or "").strip()
                    cfg = data.get("config")
                    _, user, host = get_active()
                    ok, msg = on_flex(ctrl_name, cfg, user, host)
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            # --- Control: stop ---
            if self.path == "/api/stop":
                try:
                    data = json.loads(raw)
                    ctrl_name = (data.get("name") or "").strip()
                    _, user, host = get_active()
                    ok, msg = on_stop(ctrl_name, user, host)
                    return self._json(200 if ok else 400, {"ok": ok, "message": msg})
                except Exception as e:
                    return self._json(500, {"ok": False, "message": f"Server error: {e}"})

            return self._json(404, {"ok": False, "message": "Not found"})

    srv = ThreadingHTTPServer((host, port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv