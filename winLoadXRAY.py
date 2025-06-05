import tkinter as tk
from tkinter import messagebox, filedialog, PhotoImage
from PIL import Image, ImageTk
import base64
import requests
import json
import sys
import os
import shutil
import subprocess
from urllib.parse import urlparse, parse_qs, unquote
import winreg
import re
import socket
import ctypes

APP_NAME = "winLoadXRAY"
APP_VERS = "v0.55-beta"
xray_process = None
tun_process = None
tun_enabled = False

active_tag = None
proxy_enabled = False

base64_urls = []


CONFIGS_DIR = os.path.join(os.getenv('APPDATA'), APP_NAME, 'configs')
os.makedirs(CONFIGS_DIR, exist_ok=True)
    
#CONFIG_LIST_FILE = os.path.join(CONFIGS_DIR, "config_list.json")
LINKS_FILE = os.path.join(CONFIGS_DIR, "links.json")

STATE_FILE = os.path.join(CONFIGS_DIR, "state.json")


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
    
XRAY_EXE = resource_path("xray.exe")


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
            
            toggle_system_proxy()  # включаем системный прокси
            toggle_system_proxy()  # костыль)


        if active_tag and active_tag in configs:
            highlight_active(active_tag)
            # Автозапуск Xray
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
        btn_proxy.config(bg="SystemButtonFace")  # цвет по умолчанию на Windows

def save_base64_urls():
    global base64_urls
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(base64_urls, f, ensure_ascii=False, indent=2)

def load_base64_urls():
    # 1. Загружаем все старые конфиги из папки
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

    # 2. Загружаем подписку из LINKS_FILE (как было раньше)
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            links = json.load(f)

        if isinstance(links, list) and links:
            link = links[0]  # Берём первую ссылку
        else:
            return  # Нечего загружать

        entry.delete(0, tk.END)
        entry.insert(0, link)

        try:
            if link.startswith("vless://"):
                data = parse_vless(link)
                tag = data["tag"]
                if tag not in configs:
                    configs[tag] = data
                    listbox.insert(tk.END, tag)
                    config_json = generate_config(data)
                    with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                        f.write(config_json)

            elif link.startswith("http"):
                r = requests.get(link)
                r.raise_for_status()

                # Попытка base64 с vless
                try:
                    decoded = base64.b64decode(r.text.strip()).decode("utf-8")
                    lines = [l for l in decoded.splitlines() if l.startswith("vless://")]
                    if lines:
                        for line in lines:
                            data = parse_vless(line)
                            tag = data["tag"]
                            if tag not in configs:
                                configs[tag] = data
                                listbox.insert(tk.END, tag)
                                config_json = generate_config(data)
                                with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                                    f.write(config_json)
                        return
                except Exception:
                    pass

                # JSON без base64
                clean_content = re.sub(r'<[^>]+>', '', r.text).strip()
                config_data = json.loads(clean_content)
                tag = config_data.get("tag", "default_config")
                if tag not in configs:
                    configs[tag] = config_data
                    listbox.insert(tk.END, tag)
                    with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Ошибка при загрузке ссылки: {e}")


# --- Функция подсветки активного тега: ---
def highlight_active(tag):
    global active_tag

    # Сброс цвета у старого
    if active_tag is not None:
        try:
            idx = listbox.get(0, tk.END).index(active_tag)
            listbox.itemconfig(idx, {'bg': 'white', 'fg': 'black'})
        except ValueError:
            pass

    # Новый активный
    try:
        idx = listbox.get(0, tk.END).index(tag)
        listbox.itemconfig(idx, {'bg': 'lightgreen', 'fg': 'black'})
        active_tag = tag
        save_state()
    except ValueError:
        active_tag = None



# --- Инициализация ---
if not os.path.exists(CONFIGS_DIR):
    os.makedirs(CONFIGS_DIR)

def sanitize_filename(name):
    # Удаляем недопустимые символы для имени файла в Windows
    return re.sub(r'[<>:"/\\|?*]', '_', name)

configs = {}

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
        "uuid": uuid,
        "address": address,
        "port": port,
        "security": params.get("security", ["tls"])[0],
        "network": params.get("type", ["tcp"])[0],
        "flow": params.get("flow", [""])[0],
        "sni": params.get("sni", [""])[0],
        "pbk": params.get("pbk", [""])[0],
        "sid": params.get("sid", [""])[0],
        "path": params.get("path", [""])[0],
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
        "tag": tag,
        "protocol": "shadowsocks",
        "server": server,
        "port": int(port),
        "method": method,
        "password": password
    }

# --- Генерация конфигурации XRAY ---
def generate_config(data):
    config = {
        "dns": {
            "servers": [
                "8.8.4.4",
                "8.8.8.8",
                "1.1.1.1",
                "localhost"
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
                        "geosite:twitch",
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
                        "geoip:private",
                        "geoip:ru",
                        "geoip:by",
                        "geoip:kz"
                        
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
        "outbounds": [
            {
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
            },
            {
                "protocol": "freedom",
                "tag": "direct"
            },
            {
                "protocol": "blackhole",
                "tag": "block"
            }
        ]
    }

    if data["security"] == "reality":
        config["outbounds"][0]["streamSettings"]["realitySettings"] = {
            "serverName": data["sni"],
            "publicKey": data["pbk"],
            "shortId": data["sid"],
            "fingerprint": "chrome"
        }

    if data["network"] == "xhttp":
        config["outbounds"][0]["streamSettings"]["xhttpSettings"] = {"mode": "auto"}

    return json.dumps(config, indent=2)


# --- Системный прокси ---
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


def add_from_url():
    global base64_urls

    input_text = entry.get().strip()

    # Очистка старых данных
    configs.clear()
    listbox.delete(0, tk.END)
    base64_urls = []

    # Удаляем все json-файлы из папки CONFIGS_DIR
    for filename in os.listdir(CONFIGS_DIR):
        if filename.endswith(".json"):
            try:
                os.remove(os.path.join(CONFIGS_DIR, filename))
            except Exception as e:
                print(f"Не удалось удалить файл {filename}: {e}")

    if input_text.startswith("vless://"):
        # Добавляем одну прямую VLESS ссылку
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

    if input_text.startswith("https"):
        try:
            r = requests.get(input_text)
            r.raise_for_status()

            try:
                # Попытка base64-декодирования как раньше
                decoded = base64.b64decode(r.text.strip()).decode("utf-8")
                lines = [l for l in decoded.splitlines() if l.startswith("vless://")]
                if not lines:
                    raise ValueError("Нет vless ссылок в base64 декодированном тексте")
            except Exception:
                # Если base64 не прокатил — пытаемся загрузить как чистый JSON (с очисткой html)
                import re
                clean_content = re.sub(r'<[^>]+>', '', r.text).strip()
                try:
                    config_data = json.loads(clean_content)
                    tag = config_data.get("tag", "default_config")
                    configs[tag] = config_data
                    listbox.insert(tk.END, tag)
                    with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as cf:
                        json.dump(config_data, cf, indent=2, ensure_ascii=False)
                    base64_urls.append(input_text)
                    save_base64_urls()
                    messagebox.showinfo("Добавлено", "Добавлен конфиг из JSON.")
                    return
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось распарсить JSON конфиг: {e}")
                    return

            # Если base64 с vless ссылками успешно распарсились
            for line in lines:
                data = parse_vless(line)
                tag = data["tag"]
                configs[tag] = data
                listbox.insert(tk.END, tag)
                config_json = generate_config(data)
                with open(os.path.join(CONFIGS_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
                    f.write(config_json)

            base64_urls.append(input_text)
            save_base64_urls()
            #messagebox.showinfo("Добавлено", f"Добавлено {len(lines)} конфигов.")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить/распарсить: {e}")
        return

    messagebox.showerror("Ошибка", "Введите корректную VLESS ссылку или URL на base64 с конфигами.")



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

    tag = listbox.get(selected[0])
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


def clear_highlight():
    global active_tag
    if active_tag is not None:
        try:
            idx = listbox.get(0, tk.END).index(active_tag)
            listbox.itemconfig(idx, {'bg': 'white', 'fg': 'black'})
        except ValueError:
            pass
        active_tag = None


# --- кнопка стоп
def stop_xray():
    global xray_process

    if xray_process and xray_process.poll() is None:
        try:
            xray_process.terminate()
            xray_process.wait()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось остановить Xray: {e}")

    xray_process = None
    clear_highlight()  # <--- убираем подсветку активного конфига
    btn_run.config(text="Запустить конфиг", bg="SystemButtonFace")


def stop_system_proxy():
    global proxy_enabled

    # Отключаем системный прокси
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        proxy_enabled = False
        update_proxy_button_color()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось отключить прокси: {e}")

#подсказка при наведении
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
        tw.wm_overrideredirect(True)  # Без рамок окна
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

def cmd_copy():
    widget = root.focus_get()
    try:
        # Копируем выделенный текст в буфер обмена
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
    except:
        pass  # Нет выделения, ничего не делаем


def cmd_paste():
    widget = root.focus_get()
    try:
        clipboard_text = root.clipboard_get()
        # Очистить поле (для Entry и Text по-разному)
        if isinstance(widget, tk.Entry) or isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END) if isinstance(widget, tk.Text) else widget.delete(0, tk.END)
            widget.insert("1.0" if isinstance(widget, tk.Text) else 0, clipboard_text)
    except:
        pass
    stop_xray()    
    add_from_url()

def cmd_cut():
    widget = root.focus_get()
    try:
        # Вырезаем выделенный текст: копируем и удаляем из виджета
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        widget.delete("sel.first", "sel.last")
    except:
        pass  # Нет выделения, ничего не делаем         

def cmd_select_all():
    widget = root.focus_get()
    # Для Text
    if isinstance(widget, Text):
        widget.tag_add("sel", "1.0", "end")
    # Для Entry
    elif isinstance(widget, Entry):
        widget.select_range(0, "end")
        widget.icursor("end")
            

# --- Интерфейс ---
root = tk.Tk()

icon_path = resource_path("logo.png")
icon = PhotoImage(file=icon_path)
root.iconphoto(True, icon)

icon_path = resource_path("icon.ico")
root.iconbitmap(icon_path)

root.minsize(400, 280)

def keypress(e):
    if e.keycode == 86:
        cmd_paste()
    elif e.keycode == 67:
        cmd_copy()
    elif e.keycode == 88:
        cmd_cut()
    elif e.keycode == 65:
        cmd_select_all()
root.bind("<Control-KeyPress>", keypress)

def select_config():
    selected = listbox.curselection()
    if not selected:
        return
    tag = listbox.get(selected[0])
    highlight_active(tag)

def on_enter_key(event):
    global xray_process
    if entry == root.focus_get():
        add_from_url()
    else:
        # Устанавливаем активный элемент как выбранный, если нет выделения
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

root.title(APP_NAME+" "+APP_VERS)

root.configure(bg="#e8e8e8")



# Контейнер для поля ввода и иконки
frame = tk.Frame(root, bg="#e8e8e8")
frame.pack(padx=10, pady=5)

entry = tk.Entry(frame, width=35, bg="#fff", fg="#000", insertbackground="#ffffff", font=("Arial", 12))
entry.pack(side="left", padx=10, pady=0, ipady=3)

tooltip = ToolTip(entry, "Вставьте сюда URL подписки или конфиг XRAY")

# вставка из буфера обмена
# def add_from_clipboard_and_parse():
    # try:
        # clipboard_text = root.clipboard_get().strip()
        # entry.delete(0, tk.END)
        # entry.insert(0, clipboard_text)
        # add_from_url()
    # except Exception as e:
        # messagebox.showerror("Ошибка", f"Не удалось получить данные из буфера обмена: {e}")


# Загрузка изображения (иконки)
img = Image.open(resource_path("ico.png"))  # путь к вашей картинке
img = img.resize((35, 35), Image.Resampling.LANCZOS)
icon = ImageTk.PhotoImage(img)

# В кнопке меняем команду:
btnBuffer = tk.Button(frame, image=icon, command=add_from_url, bg="#d1efff")
btnBuffer.pack(side="right", pady=3)

tooltip = ToolTip(btnBuffer, "Обновить")



frame = tk.Frame(root)
frame.pack(padx=10, pady=5)

listbox = tk.Listbox(frame, width=38, height=8, bg="#fff", font=("Arial", 12))
listbox.pack(side=tk.LEFT, fill=tk.BOTH)
# Создаём вертикальную полосу прокрутки
scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

# Связываем Listbox и Scrollbar
listbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=listbox.yview)



frame = tk.Frame(root)
frame.pack(padx=10, pady=5)
btn_run = tk.Button(frame, text="Запустить конфиг", font=("Arial", 12), command=run_selected)
btn_run.pack(side=tk.LEFT, pady=3)
tooltip = ToolTip(btn_run, "socks5 на 2080 порту")

btn_proxy = tk.Button(frame, text="Включить системный прокси", font=("Arial", 12), command=toggle_system_proxy)
tooltip = ToolTip(btn_proxy, "Запустите конфиг и выключите другие прокси расширения.")

btn_proxy.pack(side=tk.RIGHT, pady=3)
#tk.Button(root, text="Остановить Xray", command=stop_xray, bg="#ffcccc").pack(pady=3)


def get_executable_path():
    return sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)

def is_in_startup(app_name=APP_NAME):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return os.path.abspath(value) == get_executable_path()
    except FileNotFoundError:
        return False

def add_to_startup(app_name=APP_NAME, path=None):
    if path is None:
        path = get_executable_path()
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

# ---- Tkinter UI ----
def toggle_startup():
    if startup_var.get():
        add_to_startup()
    else:
        remove_from_startup()
        
frame = tk.Frame(root)
frame.pack(padx=10, pady=5)

startup_var = tk.BooleanVar(value=is_in_startup())
startup_check = tk.Checkbutton(frame, text="Автозапуск", font=("Arial", 12), variable=startup_var, command=toggle_startup)
startup_check.pack(side=tk.LEFT, pady=4, padx=14)

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
        ["powershell", "-NoProfile", "-Command", ps_command],
        capture_output=True,
        text=True,
        encoding="utf-8"
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
                
                

def start_tun2proxy():
    global tun_process
    cmd = [
        resource_path("tun2proxy/tun2proxy-bin.exe"),
        "--proxy", "socks5://127.0.0.1:2080"
    ]
    tun_process = subprocess.Popen(cmd)
    print(f"tun2proxy запущен с PID {tun_process.pid}")


def stop_tun2proxy():
    global tun_process
    if tun_process and tun_process.poll() is None:
        tun_process.terminate()
        tun_process.wait()
        print("tun2proxy остановлен")
    tun_process = None

 
def restart_xray_with_active():
    global xray_process
    if not active_tag:
        print("Нет активного тега для перезапуска.")
        return

    config_path = os.path.join(CONFIGS_DIR, f"{active_tag}.json")
    if not os.path.exists(config_path):
        print(f"Конфиг не найден: {config_path}")
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
    params = ""  # можно передать аргументы, если нужно
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", script, params, None, 1
        )
        save_state()
        stop_xray()
        stop_system_proxy()
        sys.exit()  # завершить текущий процесс
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить права администратора: {e}")

 
def vrv_tun_mode_toggle():
    global tun_enabled, active_tag

    if not is_admin():
        # answer = messagebox.askyesno("Требуются права", "Нужно запустить с правами администратора. Перезапустить?")
        # if answer:
            run_as_admin()
        # return

    if not tun_enabled:
        # ВКЛ
        interface = get_default_interface()
        patch_direct_out_interface(CONFIGS_DIR, interface)

        saved_tag = active_tag
        stop_xray()
        if saved_tag:
            active_tag = saved_tag
            restart_xray_with_active()
           
        start_tun2proxy()
        btn_tun.config(text="Выключить TUN", bg="#ffcccc")
        tun_enabled = True
    else:
        # ВЫКЛ
        stop_tun2proxy()
        btn_tun.config(text="Включить TUN", bg="SystemButtonFace")
        tun_enabled = False




    
btn_tun = tk.Button(frame, text="Включить TUN", font=("Arial", 12), command=vrv_tun_mode_toggle)
tooltip = ToolTip(btn_tun, "Только от имени Администратора! Ожидание 30 сек.")
btn_tun.pack(side=tk.RIGHT, pady=3)

load_base64_urls()
load_state()


def on_closing():
    save_state()
    stop_xray()
    stop_system_proxy()  # Выключим прокси
    stop_tun2proxy()   # Выключим tun режим
    root.destroy()  # Закроем окно

root.protocol("WM_DELETE_WINDOW", on_closing)


root.mainloop()