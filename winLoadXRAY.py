import tkinter as tk
from tkinter import messagebox, filedialog, PhotoImage, ttk
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
import ctypes
import webbrowser
import queue
import threading
import time
import concurrent.futures
from urllib.parse import urlparse, parse_qs, unquote

sys.path.append(os.path.join(os.path.dirname(__file__), 'func'))
from parsing import parse_vless, parse_shadowsocks
from configXray import generate_config
from tun2proxy import get_default_interface, patch_direct_out_interface, start_tun2proxy, stop_tun2proxy
from copyPast import cmd_copy, cmd_paste, cmd_cut, cmd_select_all

APP_NAME = "winLoadXRAY"
APP_VERS = "v0.85-beta"
XRAY_VERS = "v26.2.6"

xray_process = None
tun_enabled = False

IS_AUTOSTART = "--autostart" in sys.argv


# --- Новые функции для пинга ---

def get_sni_from_config(file_path: str) -> str or None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if not ("outbounds" in config and len(config['outbounds']) > 0):
            return None

        stream_settings = config['outbounds'][0].get('streamSettings', {})
        if not stream_settings:
            return None

        if 'realitySettings' in stream_settings and stream_settings['realitySettings'].get('serverName'):
            return stream_settings['realitySettings']['serverName']

        if 'tlsSettings' in stream_settings and stream_settings['tlsSettings'].get('serverName'):
            return stream_settings['tlsSettings']['serverName']

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None
    
    return None

def http_ping(hostname: str, timeout: int = 3) -> (int, str):
    if not hostname:
        return -1, "No SNI"
    url = f"https://{hostname}"
    
    # Отключаем использование прокси для точного измерения пинга напрямую
    proxies = {
        "http": None,
        "https": None,
    }
    
    try:
        start_time = time.perf_counter()
        response = requests.head(url, timeout=timeout, proxies=proxies)
        end_time = time.perf_counter()
        if 200 <= response.status_code < 400:
            return round((end_time - start_time) * 1000), "OK"
        else:
            return -1, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return -1, "Timeout"
    except requests.exceptions.RequestException:
        return -1, "Error"

# --- Функция для проверки последней версии на GitHub ---
def check_latest_version():
    try:
        response = requests.get("https://api.github.com/repos/xVRVx/winLoadXRAY/releases/latest", timeout=10)
        response.raise_for_status()
        latest_release = response.json()
        latest_version = latest_release.get("tag_name", "")
        
        if latest_version and latest_version != APP_VERS:
            show_update_link(latest_version)
    except Exception as e:
        print(f"Ошибка при проверке версии: {e}")

def show_update_link(latest_version):
    update_link = tk.Label(
        frameBot,
        text=f"Доступна: {latest_version}",
        fg="#2f97d3",
        bg="#e8e8e8",
        cursor="hand2",
        font=("Arial", 10, "underline")
    )
    ToolTip(update_link, "Замените: "+ get_executable_path())
    update_link.pack(side="right", padx=(0, 20), pady=5)

    def download_update(event):
        webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/releases/")
    
    update_link.bind("<Button-1>", download_update)

def open_link(event):
    webbrowser.open_new("https://t.me/SkyBridge_VPN_bot")

def github(event):
    webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/")

active_tag = None
proxy_enabled = False
base64_urls = []

CONFIGS_DIR = os.path.join(os.getenv('APPDATA'), APP_NAME, 'configs')
os.makedirs(CONFIGS_DIR, exist_ok=True)
    
LINKS_FILE = os.path.join(CONFIGS_DIR, "links.json")
STATE_FILE = os.path.join(CONFIGS_DIR, "state.json")

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
    
XRAY_EXE = resource_path("xray/xray.exe")
CREATE_NO_WINDOW = 0x08000000

def save_state():
    state = {
        "active_tag": active_tag,
        "proxy_enabled": proxy_enabled
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения состояния: {e}")
        
def load_state():
    global active_tag, proxy_enabled

    if not os.path.exists(STATE_FILE):
        return

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        active_tag = state.get("active_tag")
        proxy_enabled = state.get("proxy_enabled", False)

        if proxy_enabled:
            toggle_system_proxy()
            toggle_system_proxy()

        if active_tag and active_tag in configs:
            highlight_active(active_tag)
            config_path = os.path.join(CONFIGS_DIR, f"{active_tag}.json")
            if os.path.exists(config_path):
                global xray_process
                xray_process = subprocess.Popen([XRAY_EXE, "-config", config_path], creationflags=CREATE_NO_WINDOW)
                btn_run.config(text="Остановить конфиг", bg="lightgreen")

    except Exception as e:
        print(f"Ошибка загрузки состояния: {e}")
        
def update_proxy_button_color():
    if proxy_enabled:
        btn_proxy.config(bg="orange")
    else:
        btn_proxy.config(bg="SystemButtonFace")

def save_base64_urls():
    global base64_urls
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(base64_urls, f, ensure_ascii=False, indent=2)

def load_base64_urls():
    configs.clear()
    listbox.delete(0, tk.END)

    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".json") and filename not in ("links.json", "state.json"):
            try:
                with open(os.path.join(CONFIGS_DIR, filename), "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    tag = config_data.get("tag", os.path.splitext(filename)[0])
                    configs[tag] = config_data
                    listbox.insert(tk.END, tag)
            except Exception as e:
                print(f"Не удалось загрузить конфиг {filename}: {e}")

    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            links = json.load(f)

        if isinstance(links, list) and links:
            link = links[0]
        else:
            return

        entry.delete(0, tk.END)
        entry.insert(0, link)

# --- Инициализация ---
if not os.path.exists(CONFIGS_DIR):
    os.makedirs(CONFIGS_DIR)

configs = {}

def toggle_system_proxy(host="127.0.0.1", port=2080):
    global proxy_enabled
    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            if not proxy_enabled:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
                proxy_enabled = True
                btn_proxy.config(text="Выключить системный прокси")
            else:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                proxy_enabled = False
                btn_proxy.config(text="Включить системный прокси")
        save_state()
        update_proxy_button_color()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось переключить прокси: {e}")

def clear_xray_configs():
    configs.clear()
    listbox.delete(0, tk.END)
    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".json"):
            try:
                os.remove(os.path.join(CONFIGS_DIR, filename))
            except Exception as e:
                print(f"Не удалось удалить файл {filename}: {e}")

def add_from_url():
    global base64_urls
    stop_xray()
    stop_system_proxy()
    input_text = entry.get().strip()

    if input_text.startswith("vless://"):
        clear_xray_configs()
        base64_urls = []
        try:
            data = parse_vless(input_text)
            tag = data["tag"]
            configs[tag] = data
            listbox.insert(tk.END, tag)
            config_json = generate_config(data)
            with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                f.write(config_json)
            base64_urls.append(input_text)
            save_base64_urls()
            messagebox.showinfo("Добавлено", f"Добавлен конфиг с тегом: {tag}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось распарсить VLESS ссылку: {e}")
        return
    elif input_text.startswith("ss://"):
        clear_xray_configs()
        base64_urls = []
        try:
            data = parse_shadowsocks(input_text)
            tag = data["tag"]
            configs[tag] = data
            listbox.insert(tk.END, tag)
            config_json = generate_config(data)
            with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                f.write(config_json)
            base64_urls.append(input_text)
            save_base64_urls()
            messagebox.showinfo("Добавлено", f"Добавлен SS конфиг: {tag}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось распарсить SS ссылку: {e}")
        return

    if input_text.startswith("https"):
        try:
            headers = {'User-Agent': f'{APP_NAME}/{APP_VERS}'}
            r = requests.get(input_text, headers=headers)
            r.raise_for_status()
            clear_xray_configs()
            base64_urls = []
            try:
                decoded = base64.b64decode(r.text.strip()).decode("utf-8")
                lines = [l.strip() for l in decoded.splitlines() if l.startswith("vless://") or l.startswith("ss://")]
                if not lines:
                    raise ValueError("Нет vless или ss ссылок в base64 декодированном тексте")
                for line in lines:
                    try:
                        if line.startswith("vless://"):
                            data = parse_vless(line)
                        elif line.startswith("ss://"):
                            data = parse_shadowsocks(line)
                        else:
                            continue
                        tag = data["tag"]
                        if tag not in configs:
                            configs[tag] = data
                            listbox.insert(tk.END, tag)
                            config_json = generate_config(data)
                            with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                                f.write(config_json)
                    except Exception as e:
                        print(f"[!] Ошибка в строке: {line}\n{e}")
            except Exception:
                clean_content = re.sub(r'<[^>]+>', '', r.text).strip()
                try:
                    loaded_data = json.loads(clean_content)
                    if isinstance(loaded_data, list):
                        items = loaded_data
                    elif isinstance(loaded_data, dict):
                        items = [loaded_data]
                    else:
                        raise ValueError("Полученные данные не являются JSON объектом или списком")
                    added_count = 0
                    for config_data in items:
                        tag = unquote(config_data.get("remarks", config_data.get("tag", f"import_json_{added_count}")))
                        tag = sanitize_filename(tag) 
                        configs[tag] = config_data
                        listbox.insert(tk.END, tag)
                        with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as cf:
                            json.dump(config_data, cf, indent=2, ensure_ascii=False)
                        added_count += 1
                    if added_count > 0:
                        base64_urls.append(input_text)
                        save_base64_urls()
                        messagebox.showinfo("Добавлено", f"Добавлено конфигов из JSON: {added_count}")
                        return
                    else:
                         messagebox.showwarning("Внимание", "JSON был валидным, но пуст.")
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось распарсить JSON конфиг: {e}")
                    return

            base64_urls.append(input_text)
            save_base64_urls()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить/распарсить: {e}")
        return
    messagebox.showerror("Ошибка", "Введите корректную VLESS ссылку или URL на base64 с конфигами.")

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name)

# Очистка строк listbox от суффиксов пинга по истечению времени
def clean_listbox_texts():
    current_items = listbox.get(0, tk.END)
    for i, item in enumerate(current_items):
        if " - " in item:
            pure_tag = item.split(" - ")[0]
            listbox.delete(i)
            listbox.insert(i, pure_tag)
            if active_tag == pure_tag:
                listbox.itemconfig(i, {'bg': 'lightgreen', 'fg': 'black'})

# --- Запуск Xray ---
def run_selected():
    global xray_process

    if xray_process and xray_process.poll() is None:
        stop_xray()
        save_state()
        btn_run.config(text="Запустить конфиг", bg="SystemButtonFace")
        return

    selected = listbox.curselection()
    if not selected:
        messagebox.showwarning("Выбор", "Выберите конфиг из списка.")
        return

    # Отсекаем " - 140ms", если попытались запустить во время показа пинга
    tag = listbox.get(selected[0]).split(" - ")[0]
    config_path = os.path.join(CONFIGS_DIR, f"{tag}.json")
    if not os.path.exists(XRAY_EXE):
        messagebox.showerror("Ошибка", "Файл xray.exe не найден.")
        return

    try:
        xray_process = subprocess.Popen([XRAY_EXE, "-config", config_path], creationflags=CREATE_NO_WINDOW)
        highlight_active(tag)
        save_state()
        btn_run.config(text="Остановить конфиг", bg="lightgreen")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить Xray: {e}")


def stop_xray():
    global xray_process
    if xray_process and xray_process.poll() is None:
        try:
            xray_process.terminate()
            xray_process.wait()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось остановить Xray: {e}")

    xray_process = None
    clear_highlight()  
    btn_run.config(text="Запустить конфиг", bg="SystemButtonFace")

def stop_system_proxy():
    global proxy_enabled
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        proxy_enabled = False
        update_proxy_button_color()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось отключить прокси: {e}")

def highlight_active(tag):
    global active_tag
    if active_tag is not None:
        for i, item in enumerate(listbox.get(0, tk.END)):
            pure_item = item.split(" - ")[0]
            if pure_item == active_tag:
                listbox.itemconfig(i, {'bg': 'white', 'fg': 'black'})

    active_tag = tag
    save_state()
    for i, item in enumerate(listbox.get(0, tk.END)):
        pure_item = item.split(" - ")[0]
        if pure_item == tag:
            listbox.itemconfig(i, {'bg': 'lightgreen', 'fg': 'black'})
            break

def clear_highlight():
    global active_tag
    if active_tag is not None:
        for i, item in enumerate(listbox.get(0, tk.END)):
            pure_item = item.split(" - ")[0]
            if pure_item == active_tag:
                listbox.itemconfig(i, {'bg': 'white', 'fg': 'black'})
        active_tag = None

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) 
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

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
    except FileNotFoundError:
        return False

def add_to_startup(app_name=APP_NAME, path=None):
    if path is None:
        path = get_executable_path()
    path = f'"{path}" --autostart'

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, path)
    winreg.CloseKey(key)

def remove_from_startup(app_name=APP_NAME):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, app_name)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass

def toggle_startup():
    if startup_var.get():
        add_to_startup()
    else:
        remove_from_startup()

def restart_xray_with_active():
    global xray_process
    if not active_tag:
        return
    config_path = os.path.join(CONFIGS_DIR, f"{active_tag}.json")
    if not os.path.exists(config_path):
        return
    try:
        xray_process = subprocess.Popen([XRAY_EXE, "-config", config_path], creationflags=CREATE_NO_WINDOW)
        highlight_active(active_tag)
        btn_run.config(text="Остановить конфиг", bg="lightgreen")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось перезапустить Xray: {e}")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    script = get_executable_path()
    params = "" 
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        save_state()
        stop_xray()
        stop_system_proxy()
        sys.exit() 
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить права администратора: {e}")

def vrv_tun_mode_toggle():
    global tun_enabled, active_tag
    if not is_admin():
        run_as_admin()

    if not tun_enabled:
        interface = get_default_interface()
        patch_direct_out_interface(CONFIGS_DIR, interface)

        saved_tag = active_tag
        stop_xray()
        if saved_tag:
            active_tag = saved_tag
            restart_xray_with_active()
           
        start_tun2proxy(resource_path("tun2proxy/tun2proxy-bin.exe"))
        btn_tun.config(text="Выключить TUN", bg="#ffcccc")
        tun_enabled = True
    else:
        stop_tun2proxy()
        btn_tun.config(text="Включить TUN", bg="SystemButtonFace")
        tun_enabled = False

# --- Контекстное меню (одиночный Ping) ---
def on_context_ping_click():
    selected = listbox.curselection()
    if not selected:
        return

    idx = selected[0]
    item_text = listbox.get(idx)
    # Если уже пинговали недавно и надпись висит, не пингуем снова
    if " - " in item_text:
        return
        
    tag = item_text
    config_path = os.path.join(CONFIGS_DIR, f"{tag}.json")
    sni = get_sni_from_config(config_path)

    def ping_task():
        if sni:
            ms, status = http_ping(sni, timeout=2)
            res_str = f"{ms} ms" if ms >= 0 else "Ошибка"
        else:
            res_str = "No SNI"

        def update_ui():
            # Дописываем к строке результат
            new_text = f"{tag} - {res_str}"
            listbox.delete(idx)
            listbox.insert(idx, new_text)
            
            if active_tag == tag:
                listbox.itemconfig(idx, {'bg': 'lightgreen', 'fg': 'black'})
            
            # Убираем результат через 2 секунды
            root.after(2000, clean_listbox_texts)

        root.after(0, update_ui)

    threading.Thread(target=ping_task, daemon=True).start()

# --- Автовыбор конфига (выбор 2-го лучшего) ---
def on_auto_select_click():
    items = listbox.get(0, tk.END)
    if not items:
        return

    tags = [item.split(" - ")[0] for item in items]
    btn_auto.config(state=tk.DISABLED, text="Ищем...", fg="black")

    def ping_all_task():
        def check_tag(tag):
            config_path = os.path.join(CONFIGS_DIR, f"{tag}.json")
            sni = get_sni_from_config(config_path)
            if sni:
                ms, _ = http_ping(sni, timeout=2)
                return tag, ms
            return tag, -1

        # Параллельный пинг
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(check_tag, tags))

        # Выбираем 2-ой лучший результат
        valid_results = [r for r in results if r[1] >= 0]
        valid_results.sort(key=lambda x: x[1])
        
        best_tag = None
        if len(valid_results) > 1:
            best_tag = valid_results[1][0]  # Второй по счету (индекс 1)
        elif len(valid_results) == 1:
            best_tag = valid_results[0][0]  # Если рабочий только один

        def update_ui():
            global xray_process
            
            # Обновляем все строки, дописывая результаты
            for i, original_tag in enumerate(tags):
                ms = next((r[1] for r in results if r[0] == original_tag), -1)
                res_str = f"{ms} ms" if ms >= 0 else "Ошибка"
                
                new_text = f"{original_tag} - {res_str}"
                listbox.delete(i)
                listbox.insert(i, new_text)
                
                if active_tag == original_tag:
                    listbox.itemconfig(i, {'bg': 'lightgreen', 'fg': 'black'})

            if best_tag:
                idx = tags.index(best_tag)
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(idx)
                listbox.activate(idx)
                listbox.see(idx)
                
                # --- НОВОЕ: Остановка и автозапуск конфига ---
                if xray_process and xray_process.poll() is None:
                    stop_xray()
                
                # run_selected самостоятельно подхватит выделенный сейчас элемент,
                # запустит xray и корректно его подсветит
                run_selected()
                # ---------------------------------------------

            # Через 2 секунды возвращаем обычный вид кнопки и списка
            def finish():
                btn_auto.config(state=tk.NORMAL, text="Автовыбор", fg="black")
                clean_listbox_texts()

            root.after(2000, finish)

        root.after(0, update_ui)

    threading.Thread(target=ping_all_task, daemon=True).start()


# --- Интерфейс ---
root = tk.Tk()

icon_path = resource_path("img/logo.png")
icon = PhotoImage(file=icon_path)
root.iconphoto(True, icon)

icon_path = resource_path("img/icon.ico")
root.iconbitmap(icon_path)

root.minsize(400, 280)

def keypress(e):
    if e.keycode == 86:
        cmd_paste(root, stop_xray, add_from_url)
    elif e.keycode == 67:
        cmd_copy(root)
    elif e.keycode == 88:
        cmd_cut(root)
    elif e.keycode == 65:
        cmd_select_all(root)
root.bind("<Control-KeyPress>", keypress)

def select_config():
    selected = listbox.curselection()
    if not selected:
        return
    tag = listbox.get(selected[0]).split(" - ")[0]
    highlight_active(tag)

def on_enter_key(event):
    global xray_process
    if entry == root.focus_get():
        add_from_url()
    else:
        if not listbox.curselection():
            active = listbox.index(tk.ACTIVE)
            if active >= 0:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(active)
        if xray_process and xray_process.poll() is None:        
            run_selected()
            run_selected()
        else:
            run_selected()

root.bind('<Return>', on_enter_key)

root.title(APP_NAME+" "+APP_VERS+" "+XRAY_VERS)
root.configure(bg="#e8e8e8")

frame = tk.Frame(root, bg="#e8e8e8")
frame.pack(padx=10, pady=5)

entry = tk.Entry(frame, width=31, bg="#fff", fg="#000", insertbackground="#ffffff", font=("Arial", 12))
entry.pack(side="left", padx=5, pady=0, ipady=3)

ToolTip(entry, "Вставьте сюда URL подписки или конфига XRAY")

def add_from_clipboard_and_parse():
    try:
        clipboard_text = root.clipboard_get().strip()
        entry.delete(0, tk.END)
        entry.insert(0, clipboard_text)
        add_from_url()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить данные из буфера обмена: {e}")

img = Image.open(resource_path("img/ico.png")) 
img = img.resize((30, 30), Image.Resampling.LANCZOS)
icon1 = ImageTk.PhotoImage(img)

btnBuffer = tk.Button(frame, image=icon1, command=add_from_url, bg="#dcedf8")
btnBuffer.pack(side="right", padx=2.2, pady=3)
ToolTip(btnBuffer, "Обновить подписку")

img = Image.open(resource_path("img/ref.png")) 
img = img.resize((30, 30), Image.Resampling.LANCZOS)
icon2 = ImageTk.PhotoImage(img)

btnBuffer = tk.Button(frame, image=icon2, command=add_from_clipboard_and_parse, bg="#dcedf8")
btnBuffer.pack(side="right", padx=2.2, pady=3)
ToolTip(btnBuffer, "Вставить из буфера обмена")


frame_list = tk.Frame(root)
frame_list.pack(padx=10, pady=5)

listbox = tk.Listbox(frame_list, width=38, height=8, bg="#fff", font=("Arial", 12))
listbox.pack(side=tk.LEFT, fill=tk.BOTH)

scrollbar = tk.Scrollbar(frame_list, orient=tk.VERTICAL)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

listbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=listbox.yview)

# --- Контекстное меню для ListBox ---
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="SNI Ping", command=on_context_ping_click)

def show_context_menu(event):
    try:
        index = listbox.nearest(event.y)
        if index >= 0:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            context_menu.tk_popup(event.x_root, event.y_root)
    finally:
        context_menu.grab_release()

listbox.bind("<Button-3>", show_context_menu)


# --- Кнопки управления (Верхний ряд) ---
frame_btns = tk.Frame(root)
frame_btns.pack(padx=10, pady=5, fill=tk.X)

btn_run = tk.Button(frame_btns, text="Запустить конфиг", font=("Arial", 12), command=run_selected)
btn_run.pack(side=tk.LEFT, pady=3)
ToolTip(btn_run, "socks5 на 2080 порту")

btn_proxy = tk.Button(frame_btns, text="Включить системный прокси", font=("Arial", 12), command=toggle_system_proxy)
ToolTip(btn_proxy, "Запустите конфиг и выключите другие прокси расширения.\nРаботает только для браузеров.")
btn_proxy.pack(side=tk.RIGHT, pady=3)


# --- Кнопки управления (Нижний ряд) ---
frame_bottom = tk.Frame(root)
frame_bottom.pack(padx=10, pady=5, fill=tk.X)

startup_var = tk.BooleanVar(value=is_in_startup())
startup_check = tk.Checkbutton(frame_bottom, text="Автозапуск", font=("Arial", 12), variable=startup_var, command=toggle_startup)
startup_check.pack(side=tk.LEFT, pady=4)

btn_auto = tk.Button(frame_bottom, text="Автовыбор", font=("Arial", 12), command=on_auto_select_click)
ToolTip(btn_auto, "Проверить пинг и выбрать лучший вариант")
btn_auto.pack(side=tk.LEFT, padx=10, pady=3)
  
btn_tun = tk.Button(frame_bottom, text="Включить TUN", font=("Arial", 12), command=vrv_tun_mode_toggle)
ToolTip(btn_tun, "Только от имени Администратора! Ожидание VPN 30 сек!\nСоздается виртуальная сетевая карта.")
btn_tun.pack(side=tk.RIGHT, pady=3)


frameBot = tk.Frame(root)
frameBot.pack(padx=10, pady=2)

link1 = tk.Label(frameBot, text="Наш Telegram бот", fg="#000", cursor="hand2", font=("Arial", 10, "underline"))
link1.pack(side="left", pady=5)
link1.bind("<Button-1>", open_link)

link2 = tk.Label(frameBot, text="GitHub", fg="#000", cursor="hand2", font=("Arial", 10, "underline"))
link2.pack(side="left", pady=5)
link2.bind("<Button-1>", github)

load_base64_urls()
load_state()

if IS_AUTOSTART:
    root.iconify()

root.after(3000, check_latest_version)

def on_closing():
    save_state()
    stop_xray()
    stop_system_proxy()
    stop_tun2proxy()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()