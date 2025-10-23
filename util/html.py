from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import threading, os

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