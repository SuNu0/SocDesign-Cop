"""Open the self-contained timing demo through a loopback-only web server."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import threading
import time
from urllib.request import urlopen
import webbrowser


FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parent if (FOLDER.parent / 'sv_ffn_accel').is_dir() else FOLDER
ROUTE = '/output/timing_fixed.html' if ROOT != FOLDER else '/timing_fixed.html'
HEALTH = json.dumps({'app': 'ffn-timing-r2', 'root': str(ROOT)}).encode('utf-8')
last_request = time.monotonic()


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        global last_request
        last_request = time.monotonic()
        if self.path == '/__timing_health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(HEALTH)))
            self.end_headers()
            self.wfile.write(HEALTH)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *_):
        pass


def main():
    no_open = '--no-open' in sys.argv
    base = 'http://127.0.0.1:8765'
    try:
        with urlopen(base + '/__timing_health', timeout=1) as response:
            existing = json.loads(response.read())
        if existing.get('app') == 'ffn-timing-r2' and existing.get('root') == str(ROOT):
            if not no_open:
                webbrowser.open(base + ROUTE)
            return
    except Exception:
        pass
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8765), partial(Handler, directory=str(ROOT)))
    except OSError:
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    url = f'http://127.0.0.1:{server.server_port}{ROUTE}'
    (FOLDER / 'timing_local_url.txt').write_text(url, encoding='utf-8')

    def close_when_idle():
        while True:
            time.sleep(30)
            if time.monotonic() - last_request > 1800:
                server.shutdown()
                return

    threading.Thread(target=close_when_idle, daemon=True).start()
    if not no_open:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (FOLDER / 'timing_open_error.txt').write_text(str(error), encoding='utf-8')
        raise
