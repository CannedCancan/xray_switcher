# Xray Proxy Checker & Runtime Switcher

A lightweight system for validating VLESS proxies and dynamically switching between working configurations using Xray.

The project consists of two independent components:

* **checker** — fetches proxy subscriptions, validates them, and stores working configurations in Redis
* **switcher** — loads working configs from Redis and manages Xray runtime with live switching via HTTP API

---

## ⚙️ Architecture

```
Subscriptions (base64)
        ↓
     checker
        ↓
  alive configs (Redis)
        ↓
     switcher
        ↓
       Xray
        ↓
 SOCKS5 proxy (127.0.0.1:10808)
```

---

## 🚀 Features

* Parse VLESS URIs from base64 subscriptions
* Build Xray outbound configurations dynamically
* Parallel proxy validation using local SOCKS5 instances
* Store only working proxies in Redis
* Hot-reload Xray without restarting the service
* HTTP API for runtime proxy switching
* Automatic patching of routing rules (UDP block → proxy)

---

## 📦 Requirements

* Python 3.9+
* Redis
* Xray

Install dependencies:

```
pip install requests[socks] redis
```

---

## 🧩 Components

### 1. Checker

File: `checker.py`

Responsibilities:

* Fetch subscription URLs
* Decode base64 content
* Extract `vless://` URIs
* Build outbound configurations
* Validate proxies via Xray
* Store **only working configs** in Redis

Run:

```
python checker.py
```

Defaults:

* Runs every 10 minutes
* Redis TTL: 30 minutes

---

### 2. Switcher

File: `switcher.py`

Responsibilities:

* Load configs from Redis
* Maintain active proxy state
* Restart Xray on config switch
* Provide HTTP API

Run:

```
python switcher.py
```

---

## 🌐 HTTP API

### Get current config

```
GET /current
```

Response:

```json
{
  "index": 0,
  "config": {...}
}
```

---

### Switch to next proxy

```
GET /switch
```

Response:

```json
{
  "ok": true,
  "index": 1
}
```

---

### Get all configs

```
GET /all
```

---

## 🧠 Implementation Details

* Configurations are stored in Redis as JSON (not raw URIs)
* Hashing is used to detect config changes
* Checker and Switcher are decoupled and can run independently
* Xray is managed as a subprocess and restarted on demand
* SOCKS5 proxy uses remote DNS (`socks5h`)

---

## ⚠️ Limitations

* No automatic fallback between protocols
* No built-in health-check in switcher
* No load balancing (manual switching only)
* Sequential port allocation during validation

---

## 🛠️ Possible Improvements

* Automatic failover when proxy dies
* Latency-based ranking
* Support for additional protocols (VMess, Trojan)
* Async implementation (asyncio)
* Web UI instead of raw HTTP endpoints

---

## 📌 Motivation

This project solves a common problem:

> From a large list of proxies, identify the ones that actually work
> and switch between them quickly without manual config editing

---

## 📄 License

MIT (or any other, depending on how serious you want to look)
