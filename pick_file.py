# -*- coding: utf-8 -*-
"""Нативный диалог выбора файла для карточки (вызывается из backend.py).

Отдельным ПРОЦЕССОМ, а не внутри Flask: Tk нельзя поднимать в потоке сервера —
диалог должен жить в главном потоке своего процесса.

Использование:  python pick_file.py [начальное_имя_файла] [начальная_папка]
Печатает полный путь выбранного файла (пустая строка — отмена). Кириллица — в UTF-8.
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")     # иначе русские пути бьются в cp1251
except Exception:
    pass

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception as e:                            # tkinter не поставлен — молча отменяем
    sys.stderr.write("tkinter недоступен: %s\n" % e)
    sys.exit(0)

name = sys.argv[1] if len(sys.argv) > 1 else ""
folder = sys.argv[2] if len(sys.argv) > 2 else ""

root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)             # диалог поверх браузера, иначе теряется
except Exception:
    pass

kwargs = {"title": "Выберите файл для карточки"}
if name:
    kwargs["initialfile"] = name                  # после перетаскивания имя уже подставлено
if folder and os.path.isdir(folder):
    kwargs["initialdir"] = folder

try:
    path = filedialog.askopenfilename(**kwargs)
finally:
    root.destroy()

sys.stdout.write(path or "")
