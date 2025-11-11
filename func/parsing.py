from urllib.parse import urlparse, parse_qs, unquote
import base64
import re

def sanitize_filename(name):
    # Удаляем недопустимые символы для имени файла в Windows
    return re.sub(r'[<>:"/\\|?*]', '_', name)

# --- Парсинг VLESS-ссылки ---
def parse_vless(url):
    parsed = urlparse(url)
    uuid = parsed.username
    address = parsed.hostname
    port = int(parsed.port)
    params = parse_qs(parsed.query)
    tag = parsed.fragment or f"{address}:{port}"
    tag = unquote(tag)  # Декодируем emoji и кириллицу
    tag = sanitize_filename(tag)

    return {
        "protocol": "vless",
        "uuid": uuid,
        "address": address,
        "port": port,
        "security": params.get("security", ["reality"])[0],
        "network": params.get("type", ["raw"])[0],
        "flow": params.get("flow", ["xtls-rprx-vision"])[0],
        "sni": params.get("sni", [""])[0],
        "pbk": params.get("pbk", [""])[0],
        "fp": params.get("fp", ["chrome"])[0],
        "sid": params.get("sid", [""])[0],
        "path": params.get("path", [""])[0],
        "spx": params.get("spx", ["/"])[0],
        "pqv": params.get("pqv", [""])[0],
        "tag": tag
    }

# --- Парсинг SS-ссылки ---
def parse_shadowsocks(url):
    assert url.startswith("ss://")
    url = url[5:]

    if "#" in url:
        url, tag = url.split("#", 1)
        tag = unquote(tag)
    else:
        tag = "ss_config"

    if "@" in url:
        base64_part, address_part = url.split("@", 1)
        padded = base64_part + '=' * (-len(base64_part) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        method, password = decoded.split(":", 1)
        server, port = address_part.split(":")
    else:
        raise ValueError("Некорректный формат Shadowsocks ссылки")

    return {
        "protocol": "shadowsocks",
        "tag": tag,
        "server": server,
        "port": int(port),
        "method": method,
        "password": password
    }

