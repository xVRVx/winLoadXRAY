import tkinter as tk
from tkinter import Text, Entry

def cmd_copy(root):
    widget = root.focus_get()
    try:
        # Копируем выделенный текст в буфер обмена
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
    except:
        pass  # Нет выделения, ничего не делаем


def cmd_paste(root, stop_xray, add_from_url):
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

def cmd_cut(root):
    widget = root.focus_get()
    try:
        # Вырезаем выделенный текст: копируем и удаляем из виджета
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        widget.delete("sel.first", "sel.last")
    except:
        pass  # Нет выделения, ничего не делаем         

def cmd_select_all(root):
    widget = root.focus_get()
    # Для Text
    if isinstance(widget, Text):
        widget.tag_add("sel", "1.0", "end")
    # Для Entry
    elif isinstance(widget, Entry):
        widget.select_range(0, "end")
        widget.icursor("end")