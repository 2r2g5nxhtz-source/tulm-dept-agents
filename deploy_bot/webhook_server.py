"""
TULM Deploy Webhook Server — слушает порт 9999, запускает деплой по секретному токену
Запускается в отдельном контейнере на Hetzner
"""
import os, subprocess, asyncio, hashlib, hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading, logging

SECRET = os.environ.get("WEBHOOK_SECRET", "tulm-deploy-2026")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("webhook")

def run_deploy():
    log.info("Запуск деплоя...")
    result = subprocess.run(
        "cd /repo && git pull origin main && "
        "docker compose -f docker-compose.prod.yml up -d --build 2>&1",
        shell=True, capture_output=True, text=True, timeout=600
    )
    log.info(f"Деплой завершён:\n{result.stdout[-2000:]}")
    return result.stdout[-2000:]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [""])[0]

        if parsed.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if parsed.path == "/deploy" and hmac.compare_digest(token, SECRET):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Deploy started")
            threading.Thread(target=run_deploy, daemon=True).start()
            return

        self.send_response(403)
        self.end_headers()
        self.wfile.write(b"Forbidden")

    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format % args}")

if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", "9999"))
    log.info(f"Webhook сервер запущен на порту {port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
