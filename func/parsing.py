import re
from urllib.parse import urlparse, parse_qs, unquote

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def parse_vless(url: str) -> dict:
    url = url.strip()
    parsed = urlparse(url)
    
    uuid = unquote(parsed.username or "")
    address = parsed.hostname or ""
    port = parsed.port or 443
    
    tag = unquote(parsed.fragment) if parsed.fragment else f"{address}:{port}"
    tag = sanitize_filename(tag)
    
    query = parse_qs(parsed.query)
    params = {k: v[0] for k, v in query.items() if v}
    
    return {
        "protocol": "vless",
        "uuid": uuid,
        "address": address,
        "port": port,
        "tag": tag,
        "network": params.get("type", "raw"),
        "security": params.get("security", "none"),
        "flow": params.get("flow", ""),
        "sni": params.get("sni", ""),
        "fp": params.get("fp", "chrome"),
        "pbk": params.get("pbk", ""),
        "sid": params.get("sid", ""),
        "spx": params.get("spx", "/"),
        "path": params.get("path", "/"),
        "mode": params.get("mode", "auto"),
        "extra": params.get("extra", ""),
        "headerType": params.get("headerType", "none"),
        "alpn": params.get("alpn", "")
    }

def parse_hy2(url: str) -> dict:
    url = url.strip()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    params = {k: v[0] for k, v in query.items() if v}
    
    raw_tag = unquote(parsed.fragment) if parsed.fragment else f"Hy2_{parsed.hostname}"
    tag = sanitize_filename(raw_tag)
    
    userinfo = unquote(parsed.username or "")
    if parsed.password:
        userinfo = f"{userinfo}:{unquote(parsed.password)}"

    return {
        "protocol": "hysteria",
        "network": "hysteria",
        "address": parsed.hostname or "",
        "port": parsed.port or 443,
        "auth": userinfo,
        "uuid": userinfo,
        "tag": tag,
        **params
    }

def parse_node_url(line: str) -> dict or None:
    line = line.strip()
    if line.startswith("vless://"):
        return parse_vless(line)
    elif line.startswith("hy2://") or line.startswith("hysteria2://"):
        return parse_hy2(line)
    return None