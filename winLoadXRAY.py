import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import base64
import requests
import json
import sys
import os
import shutil
import subprocess
import winreg
import re
import webbrowser
import threading
import time
import random
import concurrent.futures
import urllib.parse
from urllib.parse import urlparse, parse_qs, unquote
import socket

# Пытаемся подключить библиотеку для системного трея
try:
    import pystray
    from pystray import MenuItem as tray_item
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

sys.path.append(os.path.join(os.path.dirname(__file__), 'func'))
from parsing import parse_vless, parse_hy2, parse_node_url
from configXray import generate_config
from copyPast import cmd_copy, cmd_cut, cmd_select_all

ctk.set_appearance_mode("dark")

APP_NAME = "winLoadXRAY"
APP_VERS = "v1.20-beta"
XRAY_VERS = "v26.7.28"

xray_process = None
IS_AUTOSTART = "--autostart" in sys.argv

# --- IPC для обработки ссылок winloadxray:// и WAKEUP ---
IPC_PORT = 20810

def get_url_from_args():
    for arg in sys.argv:
        if arg.lower().startswith("winloadxray://add/"):
            return arg[18:] # Отрезаем префикс
    return None

def send_url_to_existing_instance(url):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", IPC_PORT))
            s.sendall(url.encode('utf-8'))
        return True
    except:
        return False

# Сразу перехватываем ссылку до инициализации графики
startup_url = get_url_from_args()
msg = startup_url if startup_url else "WAKEUP"
if send_url_to_existing_instance(msg):
    sys.exit(0) 

BASE_APP_DIR = os.path.join(os.getenv('APPDATA'), APP_NAME)
PROFILES_DIR = os.path.join(BASE_APP_DIR, 'profiles')
os.makedirs(PROFILES_DIR, exist_ok=True)

CONFIGS_DIR = ""
LINKS_FILE = ""
STATE_FILE = ""
active_profile = "Default"

active_tag = None
proxy_enabled = False
base64_urls = []
configs = {}

# Параметры автообновления
auto_update_interval = 0  # в часах (0 = отключено)
last_update_timestamp = 0 # Unix time последнего обновления

# --- Функция логов в GUI (вместо messagebox) ---
def log_message(text, color="#BDC3C7"):
    def _update():
        lbl_status.configure(text=f"• {text}", text_color=color)
    if threading.current_thread() is threading.main_thread():
        _update()
    else:
        root.after(0, _update)

# --- Инструменты ---
def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def safe_b64decode(s):
    s = s.strip()
    return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')

def split_flag(tag):
    if len(tag) >= 2 and '\U0001F1E6' <= tag[0] <= '\U0001F1FF' and '\U0001F1E6' <= tag[1] <= '\U0001F1FF':
        return tag[:2], tag[2:].strip()
    if len(tag) >= 1 and ord(tag[0]) > 0x2500 and not (0x4E00 <= ord(tag[0]) <= 0x9FFF):
        return tag[0], tag[1:].strip()
    return "", tag


    parsed = urlparse(url_str.strip())
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
        "address": parsed.hostname,
        "port": parsed.port or 443,
        "auth": userinfo,
        "uuid": userinfo,
        "tag": tag,
        **params
    }


# Определение типа конфига (vless raw, hysteria2, XRAY и т.д.)
def get_config_type(data):
    try:
        if "outbounds" not in data:
            proto = data.get("protocol", "").lower()
            if proto == "vless":
                net = data.get("network", "raw")
                return f"vless {net}"
            elif proto in ("hysteria", "hy2", "hysteria2"):
                return "hysteria2"
        
        outbounds = data.get("outbounds", [])
        if not outbounds: return "XRAY"
        if len(outbounds) > 4: return "XRAY"
        
        proto = outbounds[0].get("protocol", "").lower()
        if proto == "vless":
            net = outbounds[0].get("streamSettings", {}).get("network", "raw")
            return f"vless {net}"
        elif proto in ("hysteria", "hy2", "hysteria2"):
            return "hysteria2"
        else:
            return proto.upper() if proto else "XRAY"
    except:
        return "XRAY"

def get_sni_from_config(file_path: str) -> str or None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if not ("outbounds" in config and len(config['outbounds']) > 0): return None
        outbound = config['outbounds'][0]
        stream_settings = outbound.get('streamSettings', {})
        if stream_settings:
            if 'realitySettings' in stream_settings and stream_settings['realitySettings'].get('serverName'):
                return stream_settings['realitySettings']['serverName']
            if 'tlsSettings' in stream_settings and stream_settings['tlsSettings'].get('serverName'):
                return stream_settings['tlsSettings']['serverName']
        if outbound.get('settings', {}).get('address'):
            return outbound['settings']['address']
    except: return None
    return None

def http_ping(hostname: str, timeout: int = 3) -> (int, str):
    if not hostname: return -1, "No SNI"
    url = f"https://{hostname}"
    proxies = {"http": None, "https": None}
    try:
        start_time = time.perf_counter()
        response = requests.head(url, timeout=timeout, proxies=proxies)
        end_time = time.perf_counter()
        if 200 <= response.status_code < 400:
            return round((end_time - start_time) * 1000), "OK"
        return -1, f"HTTP {response.status_code}"
    except: return -1, "Error"

# --- Профили и Файлы ---
def setup_active_profile(profile_name):
    global CONFIGS_DIR, LINKS_FILE, STATE_FILE, active_profile, configs, base64_urls, auto_update_interval, last_update_timestamp
    active_profile = profile_name
    CONFIGS_DIR = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    LINKS_FILE = os.path.join(CONFIGS_DIR, "links.json")
    STATE_FILE = os.path.join(CONFIGS_DIR, "state.json")
    configs.clear()
    base64_urls = []
    auto_update_interval = 0
    last_update_timestamp = 0
    
    settings_path = os.path.join(BASE_APP_DIR, "settings.json")
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"active_profile": active_profile}, f)
    except: pass

def get_profiles():
    profs = [d for d in os.listdir(PROFILES_DIR) if os.path.isdir(os.path.join(PROFILES_DIR, d))]
    return profs if profs else ["Default"]

def load_initial_profile():
    settings_path = os.path.join(BASE_APP_DIR, "settings.json")
    prof = "Default"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                prof = json.load(f).get("active_profile", "Default")
        except: pass
    if not os.path.exists(os.path.join(PROFILES_DIR, prof)): prof = "Default"
    setup_active_profile(prof)

def save_state():
    state = {
        "active_tag": active_tag, 
        "proxy_enabled": proxy_enabled,
        "update_interval": auto_update_interval,
        "last_update": last_update_timestamp
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except: pass

def load_state(is_initial=False):
    global active_tag, proxy_enabled, auto_update_interval, last_update_timestamp
    if not os.path.exists(STATE_FILE): return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        active_tag = state.get("active_tag")
        proxy_enabled = state.get("proxy_enabled", False)
        auto_update_interval = state.get("update_interval", 0)
        last_update_timestamp = state.get("last_update", 0)

        if proxy_enabled:
            toggle_system_proxy()
            toggle_system_proxy()

        if active_tag and active_tag in configs:
            config_list.select(active_tag)
            if is_initial:
                config_path = os.path.join(CONFIGS_DIR, f"{active_tag}.json")
                if os.path.exists(config_path):
                    global xray_process
                    xray_process = subprocess.Popen([XRAY_EXE, "-config", config_path], creationflags=CREATE_NO_WINDOW)
                    btn_run.configure(text="Остановить конфиг", fg_color="#27AE60", hover_color="#2ECC71")
                    log_message(f"Конфиг '{active_tag}' запущен", "#2ECC71")
    except: pass

def load_base64_urls():
    configs.clear()
    config_list.clear()
    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".json") and filename not in ("links.json", "state.json"):
            try:
                with open(os.path.join(CONFIGS_DIR, filename), "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    tag = config_data.get("tag", os.path.splitext(filename)[0])
                    configs[tag] = config_data
                    ctype = get_config_type(config_data)
                    config_list.insert(tag, ctype)
            except: pass

    global base64_urls
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            links = json.load(f)
        base64_urls = links if isinstance(links, list) else []
    else:
        base64_urls = []
        
    entry.delete(0, 'end')
    if base64_urls:
        entry.insert(0, base64_urls[0])

def save_base64_urls():
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(base64_urls, f, ensure_ascii=False, indent=2)

def clear_xray_configs():
    configs.clear()
    config_list.clear()
    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".json") and filename not in ("links.json", "state.json"):
            try: os.remove(os.path.join(CONFIGS_DIR, filename))
            except: pass

# --- Основные функции ---
def toggle_system_proxy(host="127.0.0.1", port=2080):
    global proxy_enabled
    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            if not proxy_enabled:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
                proxy_enabled = True
                log_message("Системный прокси включен", "#2ECC71")
            else:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                proxy_enabled = False
                log_message("Системный прокси выключен")
        save_state()
        update_proxy_button_color()
    except Exception as e:
        log_message(f"Не удалось переключить прокси: {e}", "#E74C3C")

def stop_system_proxy(is_quitting=False):
    global proxy_enabled
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        if not is_quitting:
            proxy_enabled = False
            update_proxy_button_color()
            save_state()
    except: pass

def update_proxy_button_color():
    if proxy_enabled:
        btn_proxy.configure(text="Выключить системный прокси", fg_color="#D35400", hover_color="#A04000")
    else:
        btn_proxy.configure(text="Включить системный прокси", fg_color=["#3B8ED0", "#1F6AA5"], hover_color=["#36719F", "#144870"])

def paste_and_add():
    try:
        clip = root.clipboard_get()
        entry.delete(0, 'end')
        entry.insert(0, clip)
        add_from_url()
    except: pass

def add_from_url(is_refresh=False):
    global base64_urls, active_profile, auto_update_interval, last_update_timestamp
    input_text = entry.get().strip()
    if not input_text: 
        log_message("Поле ввода пусто", "#F39C12")
        return

    # Запоминаем состояние работающего процесса для бесшовного перезапуска
    was_running = (xray_process is not None and xray_process.poll() is None)
    saved_tag = active_tag

    # Принудительно останавливаем процессы перед обновлением
    stop_xray()
    stop_system_proxy()

    # Обработка одиночных/нескольких VLESS или HYSTERIA2 ссылок
    SUPPORTED_SCHEMES = ("vless://", "hy2://", "hysteria2://")
    if any(input_text.startswith(s) for s in SUPPORTED_SCHEMES):
        lines = [l.strip() for l in input_text.splitlines() if any(l.strip().startswith(s) for s in SUPPORTED_SCHEMES)]
        added = 0
        for line in lines:
            try:
                data = parse_node_url(line)
                if not data: continue
                tag = data["tag"]
                configs[tag] = data
                ctype = get_config_type(data)
                config_list.insert(tag, ctype)
                with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                    f.write(generate_config(data))
                added += 1
            except: pass
        if added > 0 and not is_refresh:
            log_message(f"Добавлено конфигов в профиль: {added}", "#2ECC71")
        return

    # Обработка подписки по ссылке (HTTP/S)
    if input_text.startswith("http"):
        try:
            log_message("Загрузка подписки...")
            r = requests.get(input_text, headers={'User-Agent': f'{APP_NAME}/{APP_VERS}'}, timeout=15)
            r.raise_for_status()

            # --- Считываем интервал автообновления строго из заголовка ---
            interval_hdr = r.headers.get('profile-update-interval')
            if interval_hdr:
                match = re.search(r'\d+', str(interval_hdr))
                if match:
                    auto_update_interval = int(match.group(0))
                else:
                    auto_update_interval = 0
            else:
                auto_update_interval = 0

            last_update_timestamp = time.time()

            if not is_refresh:
                prof_name = None
                title_header = r.headers.get('profile-title')
                if title_header:
                    if title_header.startswith('base64:'):
                        try:
                            prof_name = safe_b64decode(title_header.split('base64:')[1])
                        except: pass
                    else:
                        prof_name = title_header
                
                if not prof_name:
                    prof_name = urllib.parse.urlparse(input_text).netloc
                
                prof_name = sanitize_filename(prof_name)
                if not prof_name: prof_name = "Subscription"

                base_prof_name = prof_name
                counter = 2
                while True:
                    prof_dir = os.path.join(PROFILES_DIR, prof_name)
                    links_file = os.path.join(prof_dir, "links.json")
                    if os.path.exists(prof_dir):
                        if os.path.exists(links_file):
                            try:
                                with open(links_file, "r", encoding="utf-8") as lf:
                                    existing_links = json.load(lf)
                                    if existing_links and existing_links[0] == input_text:
                                        break
                            except: pass
                        prof_name = f"{base_prof_name} ({counter})"
                        counter += 1
                    else:
                        break

                if prof_name != active_profile:
                    profs = get_profiles()
                    if prof_name not in profs:
                        profs.append(prof_name)
                        profile_dropdown.configure(values=profs)
                    setup_active_profile(prof_name)
                    profile_var.set(prof_name)

            clear_xray_configs()
            base64_urls = [input_text]
            save_base64_urls()

            added = 0
            try:
                decoded = safe_b64decode(r.text)
                # Поддержка vless://, hy2:// и hysteria2:// в подписке
                lines = [l.strip() for l in decoded.splitlines() if any(l.startswith(s) for s in SUPPORTED_SCHEMES)]
                for line in lines:
                    try:
                        data = parse_node_url(line)
                        if not data: continue
                        tag = data["tag"]
                        configs[tag] = data
                        ctype = get_config_type(data)
                        config_list.insert(tag, ctype)
                        with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                            f.write(generate_config(data))
                        added += 1
                    except: pass
            except:
                clean_content = re.sub(r'<[^>]+>', '', r.text).strip()
                try:
                    loaded_data = json.loads(clean_content)
                    items = loaded_data if isinstance(loaded_data, list) else [loaded_data]
                    for config_data in items:
                        if config_data.get("protocol") == "shadowsocks":
                            continue
                        outbounds = config_data.get("outbounds", [])
                        if outbounds and outbounds[0].get("protocol") == "shadowsocks":
                            continue

                        tag = sanitize_filename(unquote(config_data.get("remarks", config_data.get("tag", f"import_{added}"))))
                        configs[tag] = config_data
                        ctype = get_config_type(config_data)
                        config_list.insert(tag, ctype)
                        with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as cf:
                            json.dump(config_data, cf, indent=2, ensure_ascii=False)
                        added += 1
                except:
                    if not is_refresh: 
                        log_message("Не удалось распарсить подписку", "#E74C3C")
                    return

            save_state()

            # Восстанавливаем ранее активный конфиг
            if was_running and saved_tag and saved_tag in configs:
                config_list.select(saved_tag)
                run_selected()

            interval_info = f", автообновление: {auto_update_interval}ч" if auto_update_interval > 0 else ""
            log_message(f"Подписка обновлена ({added} серверов{interval_info})", "#2ECC71")
        except Exception as e:
            if not is_refresh: 
                log_message(f"Ошибка загрузки подписки: {e}", "#E74C3C")
        return
    if not is_refresh: 
        log_message("Неверный формат ссылки", "#E74C3C")

def update_all_subscriptions():
    if not base64_urls:
        log_message("Нет подписок для обновления в этом профиле", "#F39C12")
        return
    url = base64_urls[0]
    entry.delete(0, 'end')
    entry.insert(0, url)
    add_from_url(is_refresh=True)

# Фоновая проверка наступления времени автообновления
def check_auto_update():
    global auto_update_interval, last_update_timestamp
    try:
        if auto_update_interval > 0 and base64_urls:
            interval_seconds = auto_update_interval * 3600
            now = time.time()
            if now - last_update_timestamp >= interval_seconds:
                log_message(f"Автообновление подписки по расписанию ({auto_update_interval}ч)...")
                update_all_subscriptions()
    except Exception:
        pass
    finally:
        # Проверяем каждую минуту (60 000 мс)
        root.after(60000, check_auto_update)

def run_selected():
    global xray_process
    
    tag = config_list.selected_tag
    if not tag: 
        log_message("Конфиг не выбран", "#F39C12")
        return

    # Проверяем, запущен ли сейчас процесс
    if xray_process and xray_process.poll() is None:
        is_same_config = (active_tag == tag)
        stop_xray()
        if is_same_config:
            return

    config_path = os.path.join(CONFIGS_DIR, f"{tag}.json")
    if not os.path.exists(XRAY_EXE):
        log_message("Файл xray.exe не найден", "#E74C3C")
        return

    try:
        xray_process = subprocess.Popen([XRAY_EXE, "-config", config_path], creationflags=CREATE_NO_WINDOW)
        highlight_active(tag)
        btn_run.configure(text="Остановить конфиг", fg_color="#27AE60", hover_color="#2ECC71")
        log_message(f"Запущен конфиг: {tag}", "#2ECC71")
    except Exception as e:
        log_message(f"Не удалось запустить Xray: {e}", "#E74C3C")

def stop_xray(is_quitting=False):
    global xray_process
    if xray_process and xray_process.poll() is None:
        try:
            xray_process.terminate()
            xray_process.wait()
        except: pass
    xray_process = None
    
    if not is_quitting:
        clear_highlight()  
        btn_run.configure(text="Запустить конфиг", fg_color=["#3B8ED0", "#1F6AA5"], hover_color=["#36719F", "#144870"])
        log_message("Конфиг остановлен")

# --- Управление профилями ---
def switch_profile(new_profile):
    global active_profile
    if new_profile == active_profile: return
    stop_xray()
    stop_system_proxy()
    setup_active_profile(new_profile)
    load_base64_urls()
    load_state(is_initial=False)
    log_message(f"Профиль изменен: {new_profile}")

def add_new_profile():
    dialog = ctk.CTkInputDialog(text="Имя нового профиля:", title="Создать профиль")
    name = dialog.get_input()
    if name:
        name = sanitize_filename(name.strip())
        if name:
            setup_active_profile(name)
            profs = get_profiles()
            profile_dropdown.configure(values=profs)
            profile_var.set(name)
            load_base64_urls()
            load_state(is_initial=False)
            log_message(f"Создан профиль: {name}", "#2ECC71")

def delete_current_profile():
    if len(get_profiles()) <= 1:
        log_message("Нельзя удалить единственный профиль", "#F39C12")
        return
    deleted_name = active_profile
    stop_xray()
    stop_system_proxy()
    try: shutil.rmtree(CONFIGS_DIR)
    except: pass
    profs = get_profiles()
    if not profs: profs = ["Default"]
    new_prof = profs[0]
    profile_dropdown.configure(values=profs)
    profile_var.set(new_prof)
    switch_profile(new_prof)
    log_message(f"Профиль '{deleted_name}' удален", "#F39C12")

# --- Рандомный автовыбор ---
def on_auto_select_click():
    tags = config_list.get_all_tags()
    if not tags: 
        log_message("Список серверов пуст", "#F39C12")
        return
    btn_auto.configure(state="disabled", text="Ищем...")
    log_message("Проверка доступности серверов...")

    def ping_all_task():
        def check_tag(t):
            config_path = os.path.join(CONFIGS_DIR, f"{t}.json")
            sni = get_sni_from_config(config_path)
            if sni:
                ms, _ = http_ping(sni, timeout=2)
                return t, ms
            return t, -1

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(check_tag, tags))

        valid_results = [r for r in results if r[1] >= 0]
        best_tag = random.choice(valid_results)[0] if valid_results else None

        def update_ui():
            for original_tag in tags:
                ms = next((r[1] for r in results if r[0] == original_tag), -1)
                res_str = f"{ms} ms" if ms >= 0 else "Ошибка"
                config_list.update_ping(original_tag, res_str)

            if best_tag:
                config_list.select(best_tag)
                if xray_process and xray_process.poll() is None: stop_xray()
                run_selected()
                log_message(f"Выбран случайный рабочий сервер: {best_tag}", "#2ECC71")
            else:
                log_message("Не найдено доступных серверов", "#E74C3C")

            def finish():
                btn_auto.configure(state="normal", text="Автовыбор")
                for original_tag in tags:
                    config_list.update_ping(original_tag, "")

            root.after(2000, finish)
        root.after(0, update_ui)
    threading.Thread(target=ping_all_task, daemon=True).start()

# --- Контекстное меню ---
def on_context_ping_click():
    tag = config_list.selected_tag
    if not tag: return
    config_path = os.path.join(CONFIGS_DIR, f"{tag}.json")
    sni = get_sni_from_config(config_path)

    def ping_task():
        ms, status = http_ping(sni, timeout=2) if sni else (-1, "No SNI")
        res_str = f"{ms} ms" if ms >= 0 else ("Ошибка" if sni else "No SNI")
        def update_ui():
            config_list.update_ping(tag, res_str)
            log_message(f"Пинг {tag}: {res_str}")
            root.after(2000, lambda: config_list.update_ping(tag, ""))
        root.after(0, update_ui)
    threading.Thread(target=ping_task, daemon=True).start()

def on_context_delete_config():
    tag = config_list.selected_tag
    if not tag: return
    if active_tag == tag:
        stop_xray()
        stop_system_proxy()
    try: os.remove(os.path.join(CONFIGS_DIR, f"{tag}.json"))
    except: pass
    config_list.delete(tag)
    if tag in configs: del configs[tag]
    log_message(f"Конфиг '{tag}' удален", "#F39C12")

def show_context_menu(event, tag):
    context_menu.tk_popup(event.x_root, event.y_root)

# --- Доп функции (Update, Autostart) ---
def check_latest_version():
    try:
        response = requests.get("https://api.github.com/repos/xVRVx/winLoadXRAY/releases/latest", timeout=10)
        response.raise_for_status()
        latest_version = response.json().get("tag_name", "")
        if latest_version and latest_version != APP_VERS:
            update_link = ctk.CTkLabel(frame_links, text=f"Доступна: {latest_version}", text_color="#F1C40F", cursor="hand2", font=("Arial", 12, "underline"))
            ToolTip(update_link, "Замените: "+ get_executable_path())
            update_link.pack(side="right", padx=0)
            update_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/releases/"))
    except: pass

# --- Остальные утилиты ---
def highlight_active(tag):
    global active_tag
    active_tag = tag
    save_state()
    config_list.update_colors()

def clear_highlight():
    global active_tag
    active_tag = None
    save_state()
    config_list.update_colors()

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) 
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'): return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
    
XRAY_EXE = resource_path("xray/xray.exe")
CREATE_NO_WINDOW = 0x08000000

def get_executable_path():
    return sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)

def is_in_startup(app_name=APP_NAME):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, app_name)
        exe_path = get_executable_path().lower()
        return exe_path in value.lower()
    except Exception:
        return False

def add_to_startup(app_name=APP_NAME, path=None):
    if path is None:
        path = get_executable_path()
    path = f'"{path}" --autostart'
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_ALL_ACCESS
        )
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, path)
        winreg.CloseKey(key)
        log_message("Автозапуск включен", "#2ECC71")
    except Exception as e:
        log_message(f"Ошибка автозапуска: {e}", "#E74C3C")

def remove_from_startup(app_name=APP_NAME):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_ALL_ACCESS
        )
        winreg.DeleteValue(key, app_name)
        winreg.CloseKey(key)
        log_message("Автозапуск выключен")
    except FileNotFoundError:
        pass
    except Exception as e:
        log_message(f"Ошибка удаления автозапуска: {e}", "#E74C3C")

def toggle_startup():
    if startup_var.get():
        add_to_startup()
    else:
        remove_from_startup()

def open_link(event): webbrowser.open_new("https://t.me/SkyBridge_VPN_bot")
def github(event): webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/")

# --- Обработка ссылки (Протокол Реестра) ---
def register_url_protocol():
    if sys.platform != "win32": return
    try:
        exe_path = get_executable_path()
        if exe_path.endswith('.py'):
            command = f'"{sys.executable}" "{exe_path}" "%1"'
        else:
            command = f'"{exe_path}" "%1"'

        key_path = r"Software\Classes\winloadxray"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:winLoadXRAY Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        cmd_path = key_path + r"\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    except Exception:
        pass

def _restore_window():
    root.deiconify()
    root.wm_state('normal')
    root.attributes('-topmost', True)
    root.attributes('-topmost', False)
    root.focus_force()

def process_incoming_url(url):
    try:
        _restore_window()
    except: pass
    
    if url and url != "WAKEUP":
        entry.delete(0, 'end')
        entry.insert(0, url)
        add_from_url()

def start_ipc_server():
    def _server():
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(("127.0.0.1", IPC_PORT))
            server.listen()
            while True:
                conn, addr = server.accept()
                data = conn.recv(4096)
                if data:
                    url = data.decode('utf-8').strip()
                    if url:
                        root.after(0, lambda u=url: process_incoming_url(u))
        except Exception:
            pass
    threading.Thread(target=_server, daemon=True).start()


# ==========================================
# ====== НАСТРОЙКА ЦВЕТОВ ПРОГРАММЫ ========
# ==========================================
MAIN_BG_COLOR = "#102236"  # Основной цвет программы (темно-синий)
LIST_BG_COLOR = "#1a1a1a"  # Цвет поля со списком конфигов (темный/графит)
# ==========================================


class ConfigList(ctk.CTkScrollableFrame):
    def __init__(self, master, command=None, right_click_command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.command = command
        self.right_click_command = right_click_command
        self.rows = {}
        self.selected_tag = None
        self.emoji_font = ctk.CTkFont(family="Segoe UI Emoji", size=16)

    def insert(self, tag, config_type="XRAY"):
        if tag in self.rows: return
        
        row_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, border_width=0)
        row_frame.pack(fill="x", padx=2, pady=1)
        
        flag, name = split_flag(tag)
        
        lbl_flag = ctk.CTkLabel(row_frame, text=flag, width=30, font=self.emoji_font, anchor="center", text_color="white")
        lbl_flag.pack(side="left", padx=(5,0))
        
        lbl_name = ctk.CTkLabel(row_frame, text=name, anchor="w", text_color="white")
        lbl_name.pack(side="left", fill="x", expand=True, padx=5)
        
        # --- Правый блок ---
        lbl_ping = ctk.CTkLabel(row_frame, text="", width=55, anchor="e", text_color="white")
        lbl_ping.pack(side="right", padx=(0,10))
        
        lbl_type = ctk.CTkLabel(row_frame, text=config_type, width=90, anchor="w", text_color="gray")
        lbl_type.pack(side="right", padx=(5, 5))
        
        for w in (row_frame, lbl_flag, lbl_name, lbl_ping, lbl_type):
            w.bind("<Button-1>", lambda e, t=tag: self.select(t))
            w.bind("<Button-3>", lambda e, t=tag: self.right_click(e, t))
            w.bind("<Double-Button-1>", lambda e, t=tag: self.double_click(t))
            w.configure(cursor="hand2")

        self.rows[tag] = {
            "frame": row_frame,
            "lbl_name": lbl_name,
            "lbl_ping": lbl_ping,
            "lbl_type": lbl_type,
            "lbl_flag": lbl_flag
        }

    def update_colors(self):
        for t, widgets in self.rows.items():
            if t == active_tag:
                bg_color = "#2ECC71"
                widgets["frame"].configure(fg_color=bg_color)
                widgets["lbl_name"].configure(text_color="black", fg_color=bg_color)
                widgets["lbl_ping"].configure(text_color="black", fg_color=bg_color)
                widgets["lbl_type"].configure(text_color="#1E5631", fg_color=bg_color) 
                widgets["lbl_flag"].configure(text_color="black", fg_color=bg_color)
            elif t == self.selected_tag:
                bg_color = "#3498DB"
                widgets["frame"].configure(fg_color=bg_color)
                widgets["lbl_name"].configure(text_color="white", fg_color=bg_color)
                widgets["lbl_ping"].configure(text_color="white", fg_color=bg_color)
                widgets["lbl_type"].configure(text_color="#D5D8DC", fg_color=bg_color) 
                widgets["lbl_flag"].configure(text_color="white", fg_color=bg_color)
            else:
                widgets["frame"].configure(fg_color="transparent")
                widgets["lbl_name"].configure(text_color=["white", "gray90"], fg_color="transparent")
                widgets["lbl_ping"].configure(text_color=["white", "gray90"], fg_color="transparent")
                widgets["lbl_type"].configure(text_color="gray", fg_color="transparent")
                widgets["lbl_flag"].configure(text_color=["white", "gray90"], fg_color="transparent")

    def update_ping(self, tag, ping_text):
        if tag in self.rows:
            self.rows[tag]["lbl_ping"].configure(text=ping_text)

    def delete(self, tag):
        if tag in self.rows:
            self.rows[tag]["frame"].destroy()
            del self.rows[tag]
            if self.selected_tag == tag: self.selected_tag = None

    def clear(self):
        for w in self.rows.values(): w["frame"].destroy()
        self.rows.clear()
        self.selected_tag = None

    def select(self, tag):
        self.selected_tag = tag
        self.update_colors()
        if self.command: self.command(tag)

    def right_click(self, event, tag):
        self.select(tag)
        if self.right_click_command: self.right_click_command(event, tag)

    def double_click(self, tag):
        self.select(tag)
        run_selected()

    def get_all_tags(self): return list(self.rows.keys())


root = ctk.CTk()
root.title(f"{APP_NAME} {APP_VERS} {XRAY_VERS}")
root.geometry("500x480") 
root.minsize(500, 480)
root.iconbitmap(resource_path("img/icon.ico"))

root.configure(fg_color=MAIN_BG_COLOR)

def keypress(e):
    if e.keycode == 86: paste_and_add() # Ctrl+V
    elif e.keycode == 67: cmd_copy(root)
    elif e.keycode == 88: cmd_cut(root)
    elif e.keycode == 65: cmd_select_all(root)
root.bind("<Control-KeyPress>", keypress)
root.bind('<Return>', lambda e: add_from_url() if entry == root.focus_get() else run_selected())

bg_frame = ctk.CTkFrame(root, fg_color="transparent")
bg_frame.pack(fill="both", expand=True)

content_frame = ctk.CTkFrame(bg_frame, fg_color="transparent")
content_frame.pack(fill="both", expand=True, padx=15, pady=15)

# Меню профилей
frame_prof = ctk.CTkFrame(content_frame, fg_color="transparent")
frame_prof.pack(fill="x", pady=(0, 10))
ctk.CTkLabel(frame_prof, text="Профиль:", text_color="white").pack(side="left", padx=(0,5))
profile_var = ctk.StringVar(value="Default")
profile_dropdown = ctk.CTkOptionMenu(frame_prof, variable=profile_var, command=switch_profile)
profile_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5))
ctk.CTkButton(frame_prof, text="+", width=30, command=add_new_profile).pack(side="left", padx=(0, 5))
ctk.CTkButton(frame_prof, text="-", width=30, fg_color="#E74C3C", hover_color="#C0392B", command=delete_current_profile).pack(side="left")

# Строка ввода
frame_entry = ctk.CTkFrame(content_frame, fg_color="transparent")
frame_entry.pack(fill="x", pady=(0, 10))
entry = ctk.CTkEntry(frame_entry, placeholder_text="URL подписки, vless или hy2 конфиг...")
entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
ToolTip(entry, "Вставьте сюда URL подписки или конфиг (vless://, hy2://)")

img_paste = ctk.CTkImage(Image.open(resource_path("img/ref.png")), size=(20, 20))
btn_paste = ctk.CTkButton(frame_entry, image=img_paste, text="", width=30, command=paste_and_add)
btn_paste.pack(side="left", padx=(0, 5))
ToolTip(btn_paste, "Вставить из буфера обмена")

img_update = ctk.CTkImage(Image.open(resource_path("img/ico.png")), size=(20, 20))
btn_refresh = ctk.CTkButton(frame_entry, image=img_update, text="", width=30, command=update_all_subscriptions)
btn_refresh.pack(side="left")
ToolTip(btn_refresh, "Обновить подписку")

# Список конфигов
context_menu = tk.Menu(root, tearoff=0, bg="#2b2b2b", fg="white", activebackground="#3498db")
context_menu.add_command(label="SNI Ping", command=on_context_ping_click)
context_menu.add_command(label="Удалить конфиг", command=on_context_delete_config)

config_list = ConfigList(content_frame, fg_color=LIST_BG_COLOR, right_click_command=show_context_menu, width=400, height=150)
config_list.pack(fill="both", expand=True, pady=(0, 5))

# Кнопки управления
frame_btns1 = ctk.CTkFrame(content_frame, fg_color="transparent")
frame_btns1.pack(fill="x", pady=(15, 10))
btn_run = ctk.CTkButton(frame_btns1, text="Запустить конфиг", command=run_selected)
btn_run.pack(side="left", fill="x", expand=True, padx=(0, 5))
ToolTip(btn_run, "socks5 на 2080 порту")

btn_proxy = ctk.CTkButton(frame_btns1, text="Включить системный прокси", command=toggle_system_proxy)
btn_proxy.pack(side="right", fill="x", expand=True)
ToolTip(btn_proxy, "Запустите конфиг и выключите другие прокси расширения.\nРаботает только для браузеров.")

frame_btns2 = ctk.CTkFrame(content_frame, fg_color="transparent")
frame_btns2.pack(fill="x", pady=(5, 5))
startup_var = ctk.BooleanVar(value=is_in_startup())
ctk.CTkCheckBox(frame_btns2, text="Автозапуск", variable=startup_var, command=toggle_startup, text_color="white").pack(side="left")
btn_auto = ctk.CTkButton(frame_btns2, text="Автовыбор", width=100, command=on_auto_select_click)
btn_auto.pack(side="left", padx=(15, 5))
ToolTip(btn_auto, "Случайный выбор")

# --- СТРОКА СТАТУСА / ЛОГОВ ---
lbl_status = ctk.CTkLabel(content_frame, text="• Программа готова к работе", anchor="w", text_color="#BDC3C7", font=("Arial", 11))
lbl_status.pack(fill="x", pady=(6, 2))

# Ссылки 
frame_links = ctk.CTkFrame(content_frame, fg_color="transparent")
frame_links.pack(fill="x", pady=(5, 0))
lbl_tg = ctk.CTkLabel(frame_links, text="Наш Telegram бот", cursor="hand2", text_color="#3498db")
lbl_tg.pack(side="left", padx=(0, 10))
lbl_tg.bind("<Button-1>", open_link)
lbl_gh = ctk.CTkLabel(frame_links, text="GitHub", cursor="hand2", text_color="#3498db")
lbl_gh.pack(side="left")
lbl_gh.bind("<Button-1>", github)

# ==========================================
# ===== ЛОГИКА СИСТЕМНОГО ТРЕЯ И ВЫХОДА ====
# ==========================================

def actual_quit():
    stop_xray(is_quitting=True)
    stop_system_proxy(is_quitting=True)
    root.destroy()
    os._exit(0)

def on_closing():
    if HAS_TRAY:
        root.withdraw()
    else:
        actual_quit()

def show_window_from_tray(icon=None, item=None):
    root.after(0, _restore_window)

def quit_from_tray(icon=None, item=None):
    if icon:
        icon.stop()
    root.after(0, actual_quit)

if HAS_TRAY:
    def setup_tray():
        try:
            image = Image.open(resource_path("img/icon.ico"))
            menu = pystray.Menu(
                tray_item('Развернуть', show_window_from_tray, default=True),
                tray_item('Выход', quit_from_tray)
            )
            tray_icon = pystray.Icon("winLoadXRAY", image, "winLoadXRAY", menu)
            threading.Thread(target=tray_icon.run, daemon=True).start()
        except:
            pass
    setup_tray()

try:
    import win32api
    import win32con

    def _windows_shutdown_handler(ctrl_type):
        if ctrl_type in (win32con.CTRL_SHUTDOWN_EVENT, win32con.CTRL_LOGOFF_EVENT):
            actual_quit() 
            return True
        return False

    win32api.SetConsoleCtrlHandler(_windows_shutdown_handler, True)
except ImportError:
    pass 


# --- Инициализация перед запуском ---
register_url_protocol()
start_ipc_server()

# Запуск
load_initial_profile()
profile_var.set(active_profile)
profile_dropdown.configure(values=get_profiles())
load_base64_urls()
load_state(is_initial=True)

if startup_url:
    root.after(200, lambda: process_incoming_url(startup_url))

if IS_AUTOSTART:
    if HAS_TRAY:
        root.withdraw()
    else:
        root.iconify()

root.after(3000, check_latest_version)

# Запуск таймера проверки автообновления подписки
root.after(10000, check_auto_update)

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()