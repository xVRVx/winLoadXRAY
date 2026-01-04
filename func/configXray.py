import json
# --- Генерация конфигурации XRAY ---
def generate_config(data):
    config = {
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                "https://8.8.4.4/dns-query",
                "https://8.8.8.8/dns-query",
                "https://1.1.1.1/dns-query",
                # "https://dns.google/dns-query",
                # "https://cloudflare-dns.com/dns-query",
                # "8.8.4.4",
                # "8.8.8.8",
                # "1.1.1.1",
                # "https+local://8.8.4.4/dns-query",
                # "https+local://8.8.8.8/dns-query",
                # "https+local://1.1.1.1/dns-query",
                # "localhost"
            ]
        },
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "domain": [
                        "geosite:category-ads",
                        "geosite:win-spy"
                    ],
                    "outboundTag": "block"
                },
                {
                    "protocol": [
                        "bittorrent"
                    ],
                    "outboundTag": "direct"
                },
                {
                "domain": [
                    "habr.com"
                ],
                "outboundTag": "proxy"
                },
                {
                    "domain": [
                        "geosite:private",
                        "geosite:apple",
                        "geosite:apple-pki",
                        "geosite:huawei",
                        "geosite:xiaomi",
                        "geosite:category-android-app-download",
                        "geosite:f-droid",
                        "geosite:yandex",
                        "geosite:vk",
                        "geosite:microsoft",
                        "geosite:win-update",
                        "geosite:win-extra",
                        "geosite:google-play",
                        "geosite:steam",
                        "geosite:category-ru"
                    ],
                    "outboundTag": "direct"
                },
                {
                    "ip": [
                        "geoip:private"                        
                    ],
                    "outboundTag": "direct"
                }
            ]
    },
        "inbounds": [
            {
                "tag": "socks-sb",
                "protocol": "socks",
                "listen": "127.0.0.1",
                "port": 2080,
                "settings": {
                    "udp": True
                },
                "sniffing": {
                "enabled": True,
                "destOverride": [
                    "http",
                    "tls",
                    "quic"
                ]
                }
            }
        ],
        "outbounds": []
    }

    if data["protocol"] == "shadowsocks":
        config["outbounds"].append({
            "protocol": "shadowsocks",
            "tag": "proxy",
            "settings": {
                "servers": [
                    {
                        "address": data["server"],
                        "port": data["port"],
                        "method": data["method"],
                        "password": data["password"]
                    }
                ]
            }
        })
    else:  # VLESS
        config["outbounds"].append({
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": data["address"],
                        "port": data["port"],
                        "users": [
                            {
                                "id": data["uuid"],
                                "encryption": "none",
                                "flow": data["flow"]
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": data["network"],
                "security": data["security"]
            }
        })
        if data["security"] == "reality":
            config["outbounds"][0]["streamSettings"]["realitySettings"] = {
                "fingerprint": data["fp"],
                "serverName": data["sni"],
                "password": data["pbk"],
                "shortId": data["sid"],
                "mldsa65Verify": data["pqv"],
                "spiderX": data["spx"]
            }
        if data["network"] == "xhttp":
            config["outbounds"][0]["streamSettings"]["xhttpSettings"] = {
                "host": data["host"],
                "mode": data["mode"],
                "path": data["path"],
                "scMaxConcurrentPosts": 10,
                "scMaxEachPostBytes": 1000000,
                "scMinPostsIntervalMs": 30
            }
            if data.get("extra"):
                try:
                    # Пытаемся превратить строку в объект и сразу присвоить
                    extra_obj = json.loads(data["extra"])
                    config["outbounds"][0]["streamSettings"]["xhttpSettings"]["extra"] = extra_obj
                except Exception:
                    # Если ошибка парсинга JSON — просто пропускаем, "extra" не добавится
                    pass

    # Общие outbounds
    config["outbounds"].extend([
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "block"}
    ])

    return json.dumps(config, indent=2)