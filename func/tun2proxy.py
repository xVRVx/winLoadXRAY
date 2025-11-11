import subprocess
import socket
import os
import json
import time

tun_process = None

CREATE_NO_WINDOW = 0x08000000

def get_default_interface():
    ps_command = r"""
    $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
    $iface = Get-NetIPInterface | Where-Object { $_.InterfaceIndex -eq $route.InterfaceIndex }
    if ($iface -is [array]) {
        $iface[0].InterfaceAlias
    } else {
        $iface.InterfaceAlias
    }
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=CREATE_NO_WINDOW
    )
    return result.stdout.strip()
    
    
def resolve_ips_from_url(url):
    try:
        info = socket.getaddrinfo(url, None)
        return list(set(item[4][0] for item in info))
    except socket.gaierror as e:
        print(f"[!] Не удалось определить IP для {url}: {e}")
        return []    
    
def patch_direct_out_interface(config_dir, interface_name):
    for filename in os.listdir(config_dir):
        if filename.endswith(".json") and filename not in ("links.json", "state.json"):
            filepath = os.path.join(config_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    config = json.load(f)

                modified = False
                resolved_ips = []

                # Обработка outbounds — назначаем интерфейс и собираем адреса для резолва
                if isinstance(config.get("outbounds"), list):
                    for outbound in config["outbounds"]:
                        if outbound.get("tag") == "direct" and outbound.get("protocol") == "freedom":
                            outbound["streamSettings"] = {
                                "sockopt": {
                                    "interface": interface_name
                                }
                            }
                            modified = True

                        # Получаем URL из настроек, если есть
                        if "settings" in outbound and isinstance(outbound["settings"], dict):
                            vnext_list = outbound["settings"].get("vnext")
                            if isinstance(vnext_list, list):
                                for vnext in vnext_list:
                                    address = vnext.get("address")
                                    if address and not address.replace('.', '').isdigit():
                                        ips = resolve_ips_from_url(address)
                                        if ips:
                                            resolved_ips.extend(ips)
                                    print("Привет, ip получены!")

                # Удаляем дубликаты IP
                resolved_ips = list(set(resolved_ips))

                # Вставляем правило в начало routing.rules
                if resolved_ips:
                    rule = {
                        "ip": resolved_ips,
                        "outboundTag": "direct"
                    }

                    if "routing" not in config:
                        config["routing"] = {"rules": []}
                    if "rules" not in config["routing"]:
                        config["routing"]["rules"] = []

                    config["routing"]["rules"].insert(0, rule)
                    modified = True

                if modified:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    print(f"[✓] Обновлён файл: {filename}")
                else:
                    print(f"[ ] Пропущен (без изменений): {filename}")

            except Exception as e:
                print(f"[!] Ошибка в файле {filename}: {e}")
                
                
# https://github.com/tun2proxy/tun2proxy   https://one.one.one.one/help/
def start_tun2proxy(resource_path):
    global tun_process
    cmd = [
        resource_path,
        "--proxy", "socks5://127.0.0.1:2080",
        "--tun", "sbtun1",
        "--dns", "over-tcp"
    ]
    tun_process = subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW)
    time.sleep(2)

    print("\ntun_process ",tun_process)

    interface = get_default_interface()
    cmd = (
        'netsh dns add encryption server=8.8.4.4 dohtemplate=https://dns.google/dns-query autoupgrade=yes '
        '& netsh dns add encryption server=1.1.1.1 dohtemplate=https://cloudflare-dns.com/dns-query autoupgrade=yes '
        '& netsh interface ipv4 set dnsservers name="sbtun1" static 1.1.1.1 primary'
        '& netsh interface ipv4 add dnsservers name="sbtun1" 8.8.4.4 index=2'
        f'& netsh interface ipv4 set dnsservers name="{interface}" static 1.1.1.1 primary'
        f'& netsh interface ipv4 add dnsservers name="{interface}" 8.8.4.4 index=2'
    )

    result1 = subprocess.run(cmd, shell=True, check=True)
    print("\nresult1 ",result1)

    print(f"\ntun2proxy -sbtun1 запущен с PID {tun_process.pid}")


def stop_tun2proxy():
    global tun_process
    if tun_process and tun_process.poll() is None:
        interface = get_default_interface()
        cmd = (
            'netsh interface ipv4 set dnsservers name="sbtun1" source=dhcp '
            f'& netsh interface ipv4 set dnsservers name="{interface}" source=dhcp'
        )
        result2 = subprocess.run(cmd, shell=True, check=True)
        print("\nresult2 ",result2)

        tun_process.terminate()
        tun_process.wait()
        print("tun2proxy остановлен")
    tun_process = None

