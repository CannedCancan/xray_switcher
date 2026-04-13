import requests
import json
import time
import base64
import subprocess
import socket
import threading
import redis
import os
import traceback
from proxies import build_config

from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from basic_logger import configure_logging

logger = configure_logging(__name__)

# ---------------- CONFIG ----------------

URLS = [
    "https://import.opengate.su/sub/",
    "https://sota.ac/sub/"
]

XRAY_BIN = "/usr/local/bin/xray"
CHECK_URL = "https://github.com"

TIMEOUT = 7
MAX_WORKERS = 5
BASE_PORT = 20000

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_KEY = "alive_proxies"
REDIS_TTL = 1800

TMP_DIR = "./tmp_xray"
os.makedirs(TMP_DIR, exist_ok=True)

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# ---------------- REDIS ----------------

def save_to_redis(data):
    try:
        payload = json.dumps(data)
        redis_client.set(REDIS_KEY, payload)

        if REDIS_TTL:
            redis_client.expire(REDIS_KEY, REDIS_TTL)

        logger.info(f"saved {len(data)} configs to redis")

    except Exception as e:
        logger.error(f"redis save failed: {e}")

# ---------------- NETWORK ----------------

def wait_port(port, timeout=10):
    start = time.time()

    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except:
            time.sleep(0.2)

    return False


def fetch_with_retry(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"fetch {url} (attempt {attempt})")
            return requests.get(url, timeout=10)
        except Exception as e:
            if attempt == retries:
                logger.warning(f"fetch fail after {retries}: {e}")
                return None
            time.sleep(delay)

# ---------------- XRAY ----------------

def stream_logs(proc, port):
    for line in proc.stdout:
        logger.info(f"[XRAY {port}] {line.strip()}")

def build_outbound(uri):
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    get = lambda k, d="": params.get(k, [d])[0]

    stream = {
        "network": get("type", "tcp"),
        "security": get("security", "none"),
    }
    if stream["security"] == "tls":
        stream["tlsSettings"] = {
            "serverName": get("sni", parsed.hostname),
            "fingerprint": get("fp", "chrome")
        }

    if stream["security"] == "reality":
        stream["realitySettings"] = {
            "serverName": get("sni", ""),
            "publicKey": get("pbk", ""),
            "shortId": get("sid", ""),
            "fingerprint": get("fp", "chrome"),
            "spiderX": "/"
        }

    return {
        "protocol": "vless",
        "settings": {
            "vnext": [{
                "address": parsed.hostname,
                "port": parsed.port or 443,
                "users": [{
                    "id": parsed.username,
                    "encryption": "none"
                }]
            }]
        },
        "streamSettings": stream
    }


def run_xray(config_path, port):
    proc = subprocess.Popen(
        [XRAY_BIN, "-config", config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    threading.Thread(target=stream_logs, args=(proc, port), daemon=True).start()
    return proc

# ---------------- PARSE ----------------

def parse_subscription(text):
    try:
        decoded = base64.b64decode(text).decode()
        return [
            line.strip()
            for line in decoded.splitlines()
            if line.startswith("vless://")
        ]
    except:
        return []

# ---------------- CHECK ----------------

def check(uri, port):
    try:
        outbound = build_outbound(uri)
        logger.info(outbound)
        cfg = {
            "outbounds": [outbound]
        }

        runtime = build_config.build_runtime_config(cfg, port)

        path = os.path.join(TMP_DIR, f"xray_{port}.json")

        with open(path, "w") as f:
            json.dump(runtime, f)

        proc = run_xray(path, port)

        if not wait_port(port):
            proc.kill()
            proc.wait()
            return None

        proxy = f"socks5h://127.0.0.1:{port}"

        try:
            requests.get(
                CHECK_URL,
                timeout=TIMEOUT,
                proxies={"http": proxy, "https": proxy}
            )
            logger.info(f"OK: {uri[:60]}")
            result = build_config.build_runtime_config(cfg, 10809)
        except Exception as e:
            logger.debug(f"proxy fail: {e}")
            result = None

        proc.kill()
        proc.wait()

        try:
            os.remove(path)
        except:
            pass

        return result

    except Exception as e:
        logger.warning(f"check fail: {e}")
        return None

# ---------------- MAIN ----------------

def get_alive():
    uris = []

    for url in URLS:
        resp = fetch_with_retry(url)

        if not resp:
            continue

        logger.info(f"url ...{url[-12:]} status {resp.status_code}")
        uris.extend(parse_subscription(resp.text))

    logger.info(f"total uris: {len(uris)}")

    alive = []

    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = [
            executor.submit(check, uri, BASE_PORT + i)
            for i, uri in enumerate(uris)
        ]

        for future in as_completed(futures):
            result = future.result()
            if result:
                alive.append(result)

    logger.info(f"alive: {len(alive)}")

    save_to_redis(alive)

    return alive

# ---------------- RUN ----------------

if __name__ == "__main__":
    while True:
        try:
            get_alive()
            time.sleep(600)
        except Exception:
            logger.error(traceback.format_exc())
            exit()