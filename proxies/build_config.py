from basic_logger import configure_logging

logger = configure_logging(__name__)

# ---------------- PATCH CONFIG ----------------
def patch_ru_direct(cfg):
    routing = cfg.setdefault("routing", {})
    rules = routing.setdefault("rules", [])

    ru_rule = {
        "type": "field",
        "domain": ["regexp:.*\\.ru$"],
        "outboundTag": "direct"
    }

    # проверяем, есть ли уже такое правило (чтобы не плодить дубликаты)
    for rule in rules:
        if (
            rule.get("outboundTag") == "direct"
            and "domain" in rule
            and any(".ru" in d for d in rule.get("domain", []))
        ):
            return cfg

    logger.info("patch: .ru → direct")

    # вставляем в начало, чтобы имело приоритет
    rules.insert(0, ru_rule)

    return cfg

def patch_udp_rules(cfg):
    routing = cfg.get("routing")
    if not routing:
        return cfg

    rules = routing.get("rules")
    if not rules:
        return cfg

    for rule in rules:
        if (
            rule.get("network") == "udp"
            and rule.get("outboundTag") == "block"
        ):
            logger.info("patch: udp block → proxy")
            rule["outboundTag"] = "proxy"

    return cfg

def patch_local_direct(cfg):
    routing = cfg.setdefault("routing", {})
    rules = routing.setdefault("rules", [])

    local_rule = {
        "type": "field",
        "ip": [
            "127.0.0.1/8",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16"
        ],
        "outboundTag": "direct"
    }

    # защита от дублей (хоть какая-то)
    for rule in rules:
        if rule.get("outboundTag") == "direct" and "ip" in rule:
            if "192.168.0.0/16" in rule.get("ip", []):
                return cfg

    logger.info("patch: local networks → direct")

    rules.insert(0, local_rule)
    return cfg
def ensure_outbounds(cfg):
    outbounds = cfg.setdefault("outbounds", [])

    tags = {o.get("tag") for o in outbounds}

    if "direct" not in tags:
        outbounds.append({
            "protocol": "freedom",
            "tag": "direct"
        })

    if "block" not in tags:
        outbounds.append({
            "protocol": "blackhole",
            "tag": "block"
        })

    # желательно иметь основной тег proxy
    for o in outbounds:
        if "tag" not in o:
            o["tag"] = "proxy"

    return cfg


def ensure_chrome(cfg):
    outbounds = cfg.get("outbounds", [])

    for outbound in outbounds:
        stream = outbound.get("streamSettings")
        if not stream:
            continue

        reality = stream.get("realitySettings")
        if not reality:
            continue

        old_fp = reality.get("fingerprint")

        if old_fp != "chrome":
            logger.info(f"patch: fingerprint {old_fp} → chrome")
            reality["fingerprint"] = "chrome"

    return cfg


def build_runtime_config(cfg, port = 10808):
    cfg = ensure_outbounds(cfg)
    cfg = ensure_chrome(cfg)   
    cfg = patch_udp_rules(cfg)
    cfg = patch_local_direct(cfg)
    cfg = patch_ru_direct(cfg)
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True}
        }],
        "outbounds": cfg.get("outbounds", []),
        "routing": cfg.get("routing", {})
    }