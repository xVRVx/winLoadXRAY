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
import winreg
import re
import ctypes
import webbrowser

sys.path.append(os.path.join(os.path.dirname(__file__), 'func'))
from parsing import parse_vless, parse_shadowsocks
from configXray import generate_config
from tun2proxy import get_default_interface, patch_direct_out_interface, start_tun2proxy, stop_tun2proxy
from copyPast import cmd_copy, cmd_paste, cmd_cut, cmd_select_all

APP_NAME = "winLoadXRAY"
APP_VERS = "v0.73-beta"
XRAY_VERS = "v25.10.15"

xray_process = None
tun_enabled = False

# --- Функция для проверки последней версии на GitHub ---
def check_latest_version():
    try:
        # Получаем информацию о последнем релизе
        response = requests.get("https://api.github.com/repos/xVRVx/winLoadXRAY/releases/latest", timeout=10)
        response.raise_for_status()
        latest_release = response.json()
        latest_version = latest_release.get("tag_name", "")
        
        # Сравниваем версии
        if latest_version and latest_version != APP_VERS:
            # Показываем красную ссылку для скачивания
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
    
    update_link.pack(side="right", padx=(0, 20), pady=5)  # Добавляем отступ справа

    # Обработчик клика по ссылке
    def download_update(event):
        webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/releases/")
        # webbrowser.open_new("https://github.com/xVRVx/winLoadXRAY/releases/latest/download/winLoadXRAY.exe")
    
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
    
#CONFIG_LIST_FILE = os.path.join(CONFIGS_DIR, "config_list.json")
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
        # if listbox.size() > 0:
            # listbox.select_set(0)






# --- Инициализация ---
if not os.path.exists(CONFIGS_DIR):
    os.makedirs(CONFIGS_DIR)

configs = {}



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
    stop_xray()
    stop_system_proxy()
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
    elif input_text.startswith("ss://"):
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
            # r = requests.get(input_text)
            r.raise_for_status()

            try:
                # Попытка base64-декодирования как раньше
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

def clear_highlight():
    global active_tag
    if active_tag is not None:
        try:
            idx = listbox.get(0, tk.END).index(active_tag)
            listbox.itemconfig(idx, {'bg': 'white', 'fg': 'black'})
        except ValueError:
            pass
        active_tag = None

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
           
        start_tun2proxy(resource_path("tun2proxy/tun2proxy-bin.exe"))
        btn_tun.config(text="Выключить TUN", bg="#ffcccc")
        tun_enabled = True
    else:
        # ВЫКЛ
        stop_tun2proxy()
        btn_tun.config(text="Включить TUN", bg="SystemButtonFace")
        tun_enabled = False


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

root.title(APP_NAME+" "+APP_VERS+" "+XRAY_VERS)

root.configure(bg="#e8e8e8")



# Контейнер для поля ввода и иконки
frame = tk.Frame(root, bg="#e8e8e8")
frame.pack(padx=10, pady=5)

entry = tk.Entry(frame, width=35, bg="#fff", fg="#000", insertbackground="#ffffff", font=("Arial", 12))
entry.pack(side="left", padx=10, pady=0, ipady=3)

ToolTip(entry, "Вставьте сюда URL подписки или конфига XRAY")

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
img = Image.open(resource_path("img/ico.png"))  # путь к вашей картинке
img = img.resize((35, 35), Image.Resampling.LANCZOS)
icon = ImageTk.PhotoImage(img)

# В кнопке меняем команду:
btnBuffer = tk.Button(frame, image=icon, command=add_from_url, bg="#d1efff")
btnBuffer.pack(side="right", pady=3)

ToolTip(btnBuffer, "Обновить подписку")



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
ToolTip(btn_run, "socks5 на 2080 порту")

btn_proxy = tk.Button(frame, text="Включить системный прокси", font=("Arial", 12), command=toggle_system_proxy)
ToolTip(btn_proxy, "Запустите конфиг и выключите другие прокси расширения.\nРаботает только для браузеров.")

btn_proxy.pack(side=tk.RIGHT, pady=3)
#tk.Button(root, text="Остановить Xray", command=stop_xray, bg="#ffcccc").pack(pady=3)


        
frame = tk.Frame(root)
frame.pack(padx=10, pady=5)

startup_var = tk.BooleanVar(value=is_in_startup())
startup_check = tk.Checkbutton(frame, text="Автозапуск", font=("Arial", 12), variable=startup_var, command=toggle_startup)
startup_check.pack(side=tk.LEFT, pady=4, padx=14)


    
btn_tun = tk.Button(frame, text="Включить TUN", font=("Arial", 12), command=vrv_tun_mode_toggle)
ToolTip(btn_tun, "Только от имени Администратора! Ожидание VPN 30 сек!\nСоздается виртуальная сетевая карта.")
btn_tun.pack(side=tk.RIGHT, pady=3)


frameBot = tk.Frame(root)
frameBot.pack(padx=10, pady=2)

# Создаём "ссылку" внизу
link1 = tk.Label(
    frameBot,
    text="Наш Telegram бот",
    fg="#000",
    cursor="hand2",
    font=("Arial", 10, "underline")
)
link1.pack(side="left", pady=5)

# Привязываем обработчик
link1.bind("<Button-1>", open_link)

# Создаём "ссылку" внизу
link2 = tk.Label(
    frameBot,
    text="GitHub",
    fg="#000",
    cursor="hand2",
    font=("Arial", 10, "underline")
)
link2.pack(side="left", pady=5)

# Привязываем обработчик
link2.bind("<Button-1>", github)

# Здесь будет появляться ссылка на обновление при проверке версии


load_base64_urls()
load_state()

root.after(3000, check_latest_version)  # Проверка через 2 секунды после запуска

def on_closing():
    save_state()
    stop_xray()
    stop_system_proxy()  # Выключим прокси
    stop_tun2proxy()   # Выключим tun режим
    root.destroy()  # Закроем окно

root.protocol("WM_DELETE_WINDOW", on_closing)


root.mainloop()