import json
import subprocess
import threading
import time
import redis
import hashlib
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from basic_logger import configure_logging

logger = configure_logging(__name__)

# ---------------- CONFIG ----------------

PORT = 2222
XRAY_BIN = "/usr/local/bin/xray"

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_KEY = "alive_proxies"

CHECK_INTERVAL = 5

TMP_PATH = "./current.json"

# ---------------- STATE ----------------

current_data = {}        # hash -> config
current_keys = []        # список ключей для переключения
current_index = 0
current_key = None

xray_proc = None
lock = threading.Lock()

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# ---------------- UTILS ----------------

def hash_cfg(cfg):
    return hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest()


# ---------------- XRAY ----------------
def stream_logs(proc, num):
    for line in proc.stdout:
        logger.info(f"[XRAY] {line.strip()}")

def restart_xray(cfg):
    global xray_proc

    try:
        if xray_proc:
            logger.info("killing previous xray")
            xray_proc.kill()
            xray_proc.wait()


        with open(TMP_PATH, "w") as f:
            json.dump(cfg, f)

        xray_proc = subprocess.Popen(
            [XRAY_BIN, "-config", TMP_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )


        threading.Thread(target=stream_logs, args=(xray_proc, 4), daemon=True).start()
        logger.info("xray restarted")

    except Exception:
        logger.exception("xray restart failed")

# ---------------- REDIS ----------------

def fetch_from_redis():
    try:
        raw = redis_client.get(REDIS_KEY)

        if not raw:
            logger.warning("redis empty")
            return {}

        data = json.loads(raw)

        # превращаем в dict
        result = {}

        for cfg in data:
            #build_config.build_runtime_config(cfg)
            h = hash_cfg(cfg)
            result[h] = cfg

        return result

    except Exception as e:
        logger.error(f"redis read failed: {e}")
        return {}

# ---------------- LOOP ----------------

def sync_loop():
    global current_data, current_keys, current_index, current_key

    while True:
        try:
            new_data = fetch_from_redis()

            if not new_data:
                time.sleep(CHECK_INTERVAL)
                continue

            with lock:
                old_key = current_key

                current_data = new_data
                current_keys = list(current_data.keys())

                if not current_keys:
                    continue

                if old_key not in current_data:
                    logger.warning("current proxy disappeared → switching")

                    current_index = 0
                    current_key = current_keys[0]

                    restart_xray(current_data[current_key])
                else:
                    current_key = old_key
                    current_index = current_keys.index(current_key)

            logger.info(f"configs loaded: {len(current_data)}")

        except Exception:
            logger.exception("sync loop error")

        time.sleep(CHECK_INTERVAL)

# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        global current_index, current_key

        if self.path == "/switch":
            with lock:
                if current_keys:
                    current_index = (current_index + 1) % len(current_keys)
                    current_key = current_keys[current_index]

                    restart_xray(current_data[current_key])

                    self.send_json({
                        "ok": True,
                        "index": current_index
                    })
                else:
                    self.send_json({"error": "empty"})

        elif self.path == "/current":
            with lock:
                self.send_json({
                    "index": current_index,
                    "config": current_data.get(current_key)
                })

        elif self.path == "/all":
            with lock:
                self.send_json([current_data[key] for key in current_data.keys()])

        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

# ---------------- MAIN ----------------

if __name__ == "__main__":
    logger.info(f"HTTP server on {PORT}")

    threading.Thread(target=sync_loop, daemon=True).start()

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()