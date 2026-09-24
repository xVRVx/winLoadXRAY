import json
from urllib.parse import urlparse, parse_qs, unquote

def parse_url(url_str: str) -> dict:
    """Автоматически парсит vless://, hy2://, hysteria2:// в словарь параметров"""
    parsed = urlparse(url_str.strip())
    scheme = parsed.scheme.lower()
    query = parse_qs(parsed.query)
    params = {k: v[0] for k, v in query.items() if v}
    
    tag = unquote(parsed.fragment) if parsed.fragment else "proxy"
    userinfo = unquote(parsed.username or "")
    if parsed.password:
        userinfo = f"{userinfo}:{unquote(parsed.password)}"

    data = {
        "protocol": scheme,
        "address": parsed.hostname,
        "port": parsed.port or 443,
        "tag": tag,
        **params
    }

    if scheme in ("hy2", "hysteria2"):
        data["auth"] = userinfo
        data["uuid"] = userinfo
    else:
        data["uuid"] = userinfo

    return data


def generate_config(data):
    # Если передана готовая ссылка строкой — парсим её
    if isinstance(data, str):
        data = parse_url(data)

    config = {
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                {
                    "address": "https+local://77.88.8.8/dns-query",
                    "domains": [
                        "geosite:category-ru",
                        "geosite:yandex",
                        "geosite:vk",
                        "domain:ru",
                        "domain:su",
                        "domain:xn--p1ai"
                    ],
                    "skipFallback": True
                },
                "https://8.8.4.4/dns-query",
                "https://8.8.8.8/dns-query",
                "https://1.1.1.1/dns-query"
            ],
            "queryStrategy": "UseIPv4"
        },
        "routing": {
            "domainMatcher": "hybrid",
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
                        "habr.com",
                        "apkmirror.com"
                    ],
                    "outboundTag": "proxy"
                },
                {
                    "domain": [
                        "geosite:private",
                        "ifconfig.me",
                        "checkip.amazonaws.com",
                        "pify.org",
                        "domain:ru",
                        "domain:su",
                        "domain:xn--p1ai",
                        "geosite:category-ip-geo-detect",
                        "geosite:apple",
                        "geosite:apple-pki",
                        "geosite:yandex",
                        "geosite:vk",
                        "geosite:category-ru"
                    ],
                    "outboundTag": "direct"
                },
                {
                    "ip": [
                        "geoip:ru",
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
                    "destOverride": ["http", "tls", "quic"]
                }
            }
        ],
        "outbounds": []
    }

    protocol = data.get("protocol", "vless").lower()
    raw_net = data.get("network", "").lower()

    # =========================================================================
    # 1. ОБРАБОТКА HYSTERIA 2 (hy2 / hysteria2)
    # =========================================================================
    if protocol in ("hy2", "hysteria2", "hysteria") or raw_net == "hysteria":
        auth = data.get("auth") or data.get("password") or data.get("uuid") or ""
        sni = data.get("sni") or data.get("host") or data.get("address")
        fp = data.get("fp") or "firefox"

        alpn = data.get("alpn") or ["h3"]
        if isinstance(alpn, str):
            alpn = [a.strip() for a in alpn.split(",") if a.strip()]

        # Скорость Brutal (по умолчанию надежные 70 mbps)
        up = data.get("up") or data.get("up_mbps") or "70 mbps"
        down = data.get("down") or data.get("down_mbps") or "70 mbps"
        up_val = f"{up} mbps" if not str(up).endswith("bps") else str(up)
        down_val = f"{down} mbps" if not str(down).endswith("bps") else str(down)

        finalmask = {
            "quicParams": {
                "congestion": data.get("congestion", "brutal"),
                "brutalUp": up_val,
                "brutalDown": down_val
            }
        }

        # Если передана обфускация salamander
        obfs = data.get("obfs") or data.get("obfs_type")
        obfs_pass = data.get("obfs-password") or data.get("obfs_password") or auth
        if obfs:
            finalmask["udp"] = [{"type": obfs, "password": obfs_pass}]

        proxy_outbound = {
            "tag": "proxy",
            "protocol": "hysteria",
            "settings": {
                "address": data["address"],
                "port": int(data.get("port", 443)),
                "version": 2
            },
            "streamSettings": {
                "network": "hysteria",
                "security": "tls",
                "tlsSettings": {
                    "serverName": sni,
                    "alpn": alpn,
                    "allowInsecure": str(data.get("insecure", "0")).lower() in ("1", "true")
                },
                "fingerprint": fp,
                "hysteriaSettings": {
                    "version": 2,
                    "auth": auth
                },
                "finalmask": finalmask
            }
        }

    # =========================================================================
    # 2. ОБРАБОТКА VLESS (RAW VISION и XHTTP)
    # =========================================================================
    else:
        if raw_net in ("splithttp", "xhttp"):
            network = "xhttp"
        else:
            network = "raw"

        security = data.get("security", "tls").lower()

        user_entry = {
            "id": data["uuid"],
            "encryption": data.get("encryption", "none")
        }

        # Vision доступен только для raw + tls/reality
        flow = data.get("flow", "")
        if flow and network == "raw" and security in ("tls", "reality"):
            user_entry["flow"] = flow

        proxy_outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": data["address"],
                        "port": int(data.get("port", 443)),
                        "users": [user_entry]
                    }
                ]
            },
            "streamSettings": {
                "network": network,
                "security": security
            }
        }

        # TLS (основной для наших серверов)
        if security == "tls":
            sni = data.get("sni") or data.get("host") or data.get("address")
            tls_settings = {
                "serverName": sni,
                "fingerprint": data.get("fp") or "chrome",
                "allowInsecure": False
            }
            alpn = data.get("alpn")
            if alpn:
                alpn_list = [a.strip() for a in alpn.split(",")] if isinstance(alpn, str) else list(alpn)
                if alpn_list:
                    tls_settings["alpn"] = alpn_list

            proxy_outbound["streamSettings"]["tlsSettings"] = tls_settings

        # Reality (оставлен на случай сторонних конфигов)
        elif security == "reality":
            pbk = data.get("pbk", "")
            proxy_outbound["streamSettings"]["realitySettings"] = {
                "show": False,
                "fingerprint": data.get("fp") or "chrome",
                "serverName": data.get("sni", ""),
                "publicKey": pbk,
                "password": pbk,
                "shortId": data.get("sid", ""),
                "spiderX": data.get("spx") or "/"
            }
            if data.get("pqv"):
                proxy_outbound["streamSettings"]["realitySettings"]["mldsa65Verify"] = data["pqv"]

        # XHTTP транспорт
        if network == "xhttp":
            proxy_outbound["streamSettings"]["xhttpSettings"] = {
                "host": data.get("host", ""),
                "mode": data.get("mode", "auto"),
                "path": data.get("path", "/"),
                "scMaxConcurrentPosts": 10,
                "scMaxEachPostBytes": 1000000,
                "scMinPostsIntervalMs": 30
            }
            if data.get("extra"):
                try:
                    if isinstance(data["extra"], dict):
                        proxy_outbound["streamSettings"]["xhttpSettings"]["extra"] = data["extra"]
                    else:
                        proxy_outbound["streamSettings"]["xhttpSettings"]["extra"] = json.loads(data["extra"])
                except Exception:
                    pass

    config["outbounds"].append(proxy_outbound)

    # Стандартные исходящие
    config["outbounds"].extend([
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "block"}
    ])

    return json.dumps(config, indent=2, ensure_ascii=False)