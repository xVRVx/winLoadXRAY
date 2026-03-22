def cmd_copy(root):
    try:
        widget = root.focus_get()
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
    except:
        pass

def cmd_paste(root, stop_xray, add_from_url):
    try:
        widget = root.focus_get()
        clipboard_text = root.clipboard_get()
        if hasattr(widget, 'delete') and hasattr(widget, 'insert'):
            try:
                widget.delete("1.0", "end")
                widget.insert("1.0", clipboard_text)
            except:
                widget.delete(0, "end")
                widget.insert(0, clipboard_text)
    except:
        pass
    stop_xray()    
    add_from_url()

def cmd_cut(root):
    try:
        widget = root.focus_get()
        selected_text = widget.selection_get()
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        if hasattr(widget, 'delete'):
            try: widget.delete("sel.first", "sel.last")
            except: pass
    except:
        pass       

def cmd_select_all(root):
    try:
        widget = root.focus_get()
        if hasattr(widget, 'tag_add'):
            widget.tag_add("sel", "1.0", "end")
        elif hasattr(widget, 'select_range'):
            widget.select_range(0, "end")
            widget.icursor("end")
    except:
        pass