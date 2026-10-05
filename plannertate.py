# -*- coding: utf-8 -*-
"""PlannerTaTe — запуск приложения на компьютере (собранный PlannerTaTe.exe).

Что делает при запуске:
  1) поднимает сервер (тот же backend.py, что и в исходниках) в фоновом потоке;
  2) ставит значок в области уведомлений: открыть планировщик, адрес и ключ для телефона, выход;
  3) открывает страницу в браузере.

Повторный запуск, когда приложение уже работает, просто открывает страницу: второй сервер
поднимать нельзя, порт занят.

Отдельный режим `--pick-file ИМЯ ПАПКА` — нативный диалог выбора файла для карточки. Он нужен
потому, что в собранном exe нет отдельного python для pick_file.py: сервер запускает этот же exe.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser

APP_TITLE = "PlannerTaTe"
PAGE_URL = "http://127.0.0.1:%d"
MUTEX_NAME = "PlannerTaTe_Single_Instance"     # по нему установщик понимает, что программа запущена
STARTUP_LNK = os.path.join(os.environ.get("APPDATA") or "",
                           "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "PlannerTaTe.lnk")


def _base_dir():
    """Папка со сборкой (в собранном виде — временная распаковка, рядом лежат pick_file.py и .ico)."""
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))


def _redirect_output(data_dir):
    """В собранном виде консоли нет: весь вывод (свой и сервера) — в файл журнала."""
    try:
        f = open(os.path.join(data_dir, "plannertate.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
        print("\n--- запуск %s, %s ---" % (APP_TITLE, time.strftime("%d.%m.%Y %H:%M:%S")))
    except OSError:
        pass


def _shortcut(lnk, arguments=""):
    """Ярлык на программу. Строки PowerShell держим ASCII: кириллица в них бьётся."""
    exe = os.path.abspath(sys.executable)
    try:
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
              "$s.TargetPath='%s';$s.WorkingDirectory='%s';$s.IconLocation='%s';$s.Arguments='%s';"
              "$s.Description='PlannerTaTe';$s.Save()") % (lnk, exe, os.path.dirname(exe), exe, arguments)
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=90)
    except Exception as e:
        print("ярлык не получился (%s): %r" % (lnk, e))
    return os.path.exists(lnk)


def _autostart_on():
    """Включён ли запуск при входе в Windows (ярлык в папке «Автозагрузка»)."""
    return os.path.exists(STARTUP_LNK)


def _autostart_set(on):
    """Включить/выключить запуск при входе в Windows.

    В автозапуске ярлык с ключом --quiet: программа поднимется молча, без окна браузера —
    иначе при каждом включении компьютера вылезала бы вкладка.
    """
    if not getattr(sys, "frozen", False):
        return False                     # из исходников автозапуск не ставим
    if not on:
        try:
            os.remove(STARTUP_LNK)
        except OSError:
            pass
        return not _autostart_on()
    return _shortcut(STARTUP_LNK, arguments="--quiet")


def _make_shortcuts():
    """Ярлыки на рабочем столе и в меню «Пуск» — чтобы программу не искали по папкам.

    Делается один раз: если ярлык уже есть, ничего не трогаем. Только для собранной программы.
    """
    if not getattr(sys, "frozen", False) or os.environ.get("PLANNERTATE_NO_SHORTCUT"):
        return 0
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    targets = [
        os.path.join(home, "Desktop", "PlannerTaTe.lnk"),
        os.path.join(os.environ.get("APPDATA") or "", "Microsoft", "Windows", "Start Menu", "Programs", "PlannerTaTe.lnk"),
    ]
    made = sum(1 for lnk in targets if lnk and not os.path.exists(lnk) and _shortcut(lnk))
    print("ярлыков создано:", made)
    return made


def _single_instance():
    """Отметка «программа работает» для установщика (он по ней предлагает закрыть приложение).

    Ручку не закрываем: она живёт, пока живёт процесс.
    """
    try:
        import ctypes
        return ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    except Exception:
        return None


def _pick_file_mode():
    """Диалог выбора файла в своём процессе. Вывод идёт родителю в поток, а не в журнал."""
    try:
        sys.stdout = open(1, "w", encoding="utf-8", closefd=False)
        sys.stderr = open(2, "w", encoding="utf-8", closefd=False, errors="replace")
    except OSError:
        pass
    import runpy
    sys.argv = ["pick_file.py"] + list(sys.argv[2:])
    runpy.run_path(os.path.join(_base_dir(), "pick_file.py"), run_name="__main__")
    return 0


def _port_busy(port):
    import socket
    s = socket.socket()
    try:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--pick-file":
        return _pick_file_mode()

    import backend                     # папку данных считает сервер, чтобы не было двух правд
    _redirect_output(backend.BASE_DIR)
    _mutex = _single_instance()

    port = backend.PORT
    page = PAGE_URL % port
    # Тихий запуск: при входе в Windows (ярлык автозапуска) и при проверках — без вкладки браузера.
    quiet = bool(os.environ.get("PLANNERTATE_NO_BROWSER")) or "--quiet" in sys.argv

    def open_page(*_):
        if not quiet:
            webbrowser.open(page)

    if _port_busy(port):
        print("[%s] уже запущен на порту %d — открываю страницу" % (APP_TITLE, port))
        open_page()
        return 0

    _make_shortcuts()

    backend._access_key()          # ключ создаётся при первом запуске и печатается в журнал

    def serve():
        try:
            backend.start_reminder_thread()
            backend.app.run(host=backend.BIND_HOST, port=port, debug=False,
                            threaded=True, use_reloader=False)
        except Exception as e:                     # порт заняли между проверкой и запуском
            print("сервер остановился: %r" % e)

    threading.Thread(target=serve, daemon=True).start()

    try:
        from PyQt5 import QtWidgets, QtGui, QtCore
    except Exception as e:
        # Значка не будет, но приложение обязано работать: сервер уже поднят.
        print("нет Qt для значка в трее: %r" % e)
        open_page()
        while True:
            time.sleep(1)

    qt = QtWidgets.QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)

    ico = os.path.join(_base_dir(), "PlannerTaTe.ico")
    icon = (QtGui.QIcon(ico) if os.path.exists(ico)
            else qt.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon))

    def show_info(*_):
        """Адрес и ключ для телефона — то же, что показывает страница при первом запуске."""
        key = backend._access_key()
        ip = backend._lan_ip()
        box = QtWidgets.QMessageBox()
        box.setWindowTitle("PlannerTaTe на телефон")
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(
            "<b>Планер уже работает на этом компьютере.</b><br><br>"
            "Чтобы поставить приложение на телефон, откройте на нём адрес:<br>"
            "<b>http://%s:%d</b><br><br>"
            "Ключ доступа (вводится на телефоне один раз):<br>"
            "<b style='font-size:15px'>%s</b><br><br>"
            "Телефон и компьютер должны быть в одной сети Wi-Fi.<br>"
            "Если Windows спросит про доступ к сети — разрешите." % (ip, port, key))
        box.exec_()

    tray = QtWidgets.QSystemTrayIcon(icon)
    menu = QtWidgets.QMenu()
    menu.addAction("Открыть PlannerTaTe", open_page)
    menu.addAction("Адрес и ключ для телефона", show_info)

    def toggle_autostart(on):
        """Автозапуск при входе в Windows: галочка в меню трея."""
        ok = _autostart_set(on)
        act_auto.setChecked(_autostart_on())
        print("автозапуск:", "включён" if act_auto.isChecked() else "выключен", "| получилось:", ok)

    menu.addSeparator()
    act_auto = menu.addAction("Запускать при входе в Windows")
    act_auto.setCheckable(True)
    act_auto.setChecked(_autostart_on())
    act_auto.triggered.connect(toggle_autostart)
    menu.addSeparator()
    menu.addAction("Выход", qt.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("%s — планировщик задач (работает)" % APP_TITLE)
    tray.activated.connect(lambda reason: open_page() if reason == QtWidgets.QSystemTrayIcon.DoubleClick else None)
    tray.show()

    print("значок в трее поставлен, страница: %s" % page)
    QtCore.QTimer.singleShot(1200, open_page)
    if not quiet:
        QtCore.QTimer.singleShot(2000, lambda: tray.showMessage(
            APP_TITLE, "Приложение работает. Планера — в трее, рядом с часами.",
            QtWidgets.QSystemTrayIcon.Information, 6000))
    return qt.exec_()


if __name__ == "__main__":
    sys.exit(main())
