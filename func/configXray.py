import json
# --- Генерация конфигурации XRAY ---
def generate_config(data):
    config = {
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
        "log": {"loglevel": "warning"},
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
                },
                {
                    "ip": [
                        "geoip:!ru"
                    ],
                    "outboundTag": "proxy"
                },
                {
                    "domain": [
                        "geosite:discord",
                        "geosite:youtube",
                        "geosite:tiktok",
                        "geosite:twitch",
                        "geosite:signal"

                    ],
                    "outboundTag": "proxy"
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
                                "flow": data["flow"],
                                "level": 0
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
            config["outbounds"][0]["streamSettings"]["xhttpSettings"] = {"mode": "auto"}

    # Общие outbounds
    config["outbounds"].extend([
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "block"}
    ])

    return json.dumps(config, indent=2)