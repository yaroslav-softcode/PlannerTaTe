"""
PlannerTaTe — Flask backend для LiteGraph frontend.
Отдаёт статику фронтенда + HTTP API:
  GET  /api/load   -> вернуть saved graph.json
  POST /api/save   -> сохранить graph JSON
  POST /api/notify -> отправить уведомление (Telegram / VK Max)

Запуск:  python backend.py
Затем открыть в браузере: http://localhost:5001
"""
import os
import json
import sys
import hmac
import time
import secrets
import socket
import subprocess
from flask import Flask, request, jsonify, send_from_directory, Response, send_file, redirect

# --- Где что лежит (нужно для собранного PlannerTaTe.exe, 03.10.26) --------------------------
# Программа работает и из исходников (python backend.py), и как один собранный файл. Собранный
# распаковывает свой код во временную папку, поэтому:
#   * неизменяемые части (собранный сайт, диалог выбора файла) читаются ИЗ СБОРКИ — RES_DIR;
#   * записываемые файлы (граф, ключ, лицензия, состояние) лежат РЯДОМ С ПРОГРАММОЙ, а если туда
#     писать нельзя (exe положили в Program Files) — в папку пользователя (%APPDATA%\PlannerTaTe).
FROZEN = bool(getattr(sys, "frozen", False))
PROG_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES_DIR = getattr(sys, "_MEIPASS", None) or PROG_DIR


def _writable(folder):
    """Можно ли писать в папку. os.access на Windows врёт, поэтому пробуем создать файл."""
    probe = os.path.join(folder, ".plannertate_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except OSError:
        return False


def _data_dir():
    """Папка с данными (граф, ключ, лицензия).

    Из исходников — сам проект (как было всегда). У собранной программы — папка пользователя:
    иначе рядом с exe на рабочем столе появлялись бы graph.json и access_key.txt. Можно задать
    свою папку переменной PLANNERTATE_DATA (нужно для проверок рядом с рабочим приложением).
    """
    forced = os.environ.get("PLANNERTATE_DATA")
    if forced:
        os.makedirs(forced, exist_ok=True)
        return forced
    if not FROZEN and _writable(PROG_DIR):
        return PROG_DIR
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PlannerTaTe")
    os.makedirs(d, exist_ok=True)
    return d


BASE_DIR = _data_dir()
app = Flask(__name__, static_folder=os.path.join(RES_DIR, 'frontend', 'dist'), static_url_path='')
GRAPH_FILE = os.path.join(BASE_DIR, 'graph.json')
LICENSE_FILE = os.path.join(BASE_DIR, 'license.json')   # флаг «лицензия оплачена» — переживает перезапуск

# --- Тема оформления компьютера для телефона (03.10.26, просьба Ярослава) --------------------
# Тема выбирается в браузере компьютера и лежит в его localStorage — телефону её не видно.
# Поэтому компьютер сообщает выбранную тему серверу, а телефон забирает её при синхронизации
# и открывает планировщик в той же теме. Файл рядом с graph.json, как остальные настройки.
UI_FILE = os.path.join(BASE_DIR, 'ui_state.json')

# --- Ключ доступа для сети (03.10.26, просьба Ярослава) ------------------------------------
# Сервер слушает 0.0.0.0, чтобы с ним работал телефон, поэтому раньше любой в той же сети
# мог прочитать и перезаписать граф (проверено: /api/load отдавал все карточки, /api/save
# был открыт на запись). Теперь: со СВОЕГО компьютера (127.0.0.1) — свободно; из сети —
# обязателен ключ: заголовок X-Plannertate-Key, ссылка ?key=... или кука после входа по форме.
KEY_FILE = os.path.join(BASE_DIR, 'access_key.txt')
KEY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # без похожих 0/O и 1/I/L — ключ диктуют руками
KEY_LEN = 10
_bad_attempts = {}          # ip -> список времён отказов (для журнала, без блокировок)

# --- Новый пользователь: свой адрес в сети и установка приложения на телефон (03.10.26) -------
# Просьба Ярослава: у другого человека вайфай другой, поэтому адрес зашивать нельзя — компьютерная
# часть сама определяет свой адрес в сети, показывает ссылку и QR, а ключ выводит на экран.
PORT = int(os.environ.get("PLANNERTATE_PORT") or 5001)
PHONE_SEEN_FILE = os.path.join(BASE_DIR, 'phone_prompt.json')    # «Позже» в окне установки
# Приложение телефона: свежее рядом с программой (можно подменить, не пересобирая), иначе — то,
# что зашито в сборку.
APK_LOCAL = os.path.join(PROG_DIR, 'app', 'PlannerTaTe.apk')
APK_IN_BUILD = os.path.join(RES_DIR, 'app', 'PlannerTaTe.apk')
APK_DEV = os.path.join(os.path.expanduser("~"), "Projects", "PlannerTaTePhone",
                       "app", "build", "outputs", "apk", "debug", "app-debug.apk")
KEY_EXISTED = os.path.exists(KEY_FILE)     # до первого запуска ключа нет — это и есть признак


def _local_ips():
    """Все IPv4-адреса этого компьютера (включая VPN-адаптеры)."""
    ips = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith('127.'):
                ips.append(ip)
    except OSError:
        pass
    return ips


_NET_CACHE = {"at": 0.0, "data": None}


def _net_addresses():
    """Адреса компьютера с разбором: какой годится для КАБЕЛЯ (USB-модем), какой — для сети.

    Зачем (просьба Ярослава 04.10.26): у нового пользователя может не быть Wi-Fi, и тогда
    телефон подключается кабелем в режиме «USB-модем». У компьютера появляется отдельный
    адаптер (Remote NDIS / USB Ethernet) со своим адресом — именно его и надо показать в
    инструкции «Нет Wi-Fi». Разбор делаем одним вызовом PowerShell (описание адаптера иначе
    не узнать) и кэшируем на 5 секунд, чтобы не тормозить страницу.
    """
    now = time.time()
    if _NET_CACHE["data"] and now - _NET_CACHE["at"] < 5:
        return _NET_CACHE["data"]
    pairs = []
    if os.name == "nt":
        ps = ("Get-NetIPAddress -AddressFamily IPv4 | "
              "Where-Object { $_.IPAddress -notlike '127.*' } | ForEach-Object { "
              "$a = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue; "
              "'{0}|{1}' -f $_.IPAddress, ($a.InterfaceDescription) }")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=8,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if "|" in line:
                    ip, _, desc = line.partition("|")
                    ip, desc = ip.strip(), desc.strip()
                    if ip and not ip.startswith("127."):
                        pairs.append((ip, desc))
        except Exception as e:
            print("[сеть] не смог опросить адаптеры:", e, file=sys.stderr, flush=True)
    if not pairs:                                   # без PowerShell — только адреса
        pairs = [(ip, "") for ip in _local_ips()]
    cable, main, vpn = "", "", []
    for ip, desc in pairs:
        d = desc.lower()
        if ("ndis" in d) or ("usb" in d and "ethernet" in d):
            if not cable:
                cable = ip
        elif any(k in d for k in ("vpn", "wireguard", "tailscale", "zerotier", "openvpn", "tap-")):
            vpn.append(ip)
        elif not main:
            main = ip
    if not main:                                    # остались только кабель/VPN — берём любой
        for ip, _d in pairs:
            if ip != cable:
                main = ip
                break
    data = {"cable": cable, "main": main or (pairs[0][0] if pairs else "127.0.0.1"), "vpn": vpn}
    _NET_CACHE.update(at=now, data=data)
    return data


def _lan_ip():
    """Свой адрес в ДОМАШНЕЙ сети — по нему телефон находит компьютер.

    04.10.26 (нашёл Ярослав): на компьютере может быть поднят VPN (AdGuard), и тогда «адрес
    по умолчанию» — это адрес туннеля (172.16.x.x), до которого телефон в Wi-Fi не достучится.
    Поэтому сначала берём обычные домашние диапазоны: 192.168.x → 10.x → 172.16-31.x, и только
    если ничего из этого нет — адрес туннеля. Наружу ничего не уходит: UDP-сокет лишь
    «подключается», чтобы ядро показало исходящий адрес, пакет при этом не отправляется."""
    udp = None
    for probe in (('8.8.8.8', 80), ('192.168.0.1', 80), ('10.0.0.1', 80)):
        sk = None
        try:
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.settimeout(0.2)
            sk.connect(probe)
            ip = sk.getsockname()[0]
            if ip and not ip.startswith('127.'):
                udp = ip
                break
        except OSError:
            pass
        finally:
            if sk is not None:
                try:
                    sk.close()
                except OSError:
                    pass
    cands = [ip for ip in dict.fromkeys(_local_ips() + ([udp] if udp else []))
             if ip and not ip.startswith('127.')]

    def _rank(ip):
        if ip.startswith('192.168.'):
            return 0
        if ip.startswith('10.'):
            return 1
        if ip.startswith('172.'):
            try:
                if 16 <= int(ip.split('.')[1]) <= 31:
                    return 2
            except (IndexError, ValueError):
                pass
        return 3

    try:
        nets = _net_addresses()                     # домашним считаем НЕ кабельный адрес
        if nets.get("main"):
            return nets["main"]
    except Exception:
        pass
    if cands:
        return sorted(cands, key=_rank)[0]
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith('127.'):
            return ip
    except OSError:
        pass
    return '127.0.0.1'


def _apk_file():
    """Файл приложения: рядом с программой, иначе внутри сборки, иначе собранный в проекте."""
    for cand in (APK_LOCAL, APK_IN_BUILD, APK_DEV):
        if os.path.exists(cand):
            return cand
    return APK_LOCAL


def _phone_seen():
    """Показывали ли уже окно «Установить приложение на телефон»."""
    try:
        with open(PHONE_SEEN_FILE, encoding='utf-8') as f:
            return bool(json.load(f).get('seen'))
    except (OSError, ValueError):
        return False


def _access_key():
    """Ключ из access_key.txt; при первом запуске создаём и печатаем в консоль."""
    try:
        with open(KEY_FILE, encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = ''.join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_LEN))
    try:
        with open(KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(key + '\n')
        print('[key] создан ключ доступа для сети:', key, file=sys.stderr, flush=True)
    except OSError as e:
        print('[key] не смог записать access_key.txt:', e, file=sys.stderr, flush=True)
    return key


def _client_key():
    return (request.headers.get('X-Plannertate-Key')
            or request.args.get('key')
            or request.cookies.get('plannertate_key')
            or '')


def _is_local():
    return request.remote_addr in ('127.0.0.1', '::1')


def _note_bad_attempt():
    ip = request.remote_addr or '?'
    now = time.time()
    arr = [t for t in _bad_attempts.get(ip, []) if now - t < 600]
    arr.append(now)
    _bad_attempts[ip] = arr
    if len(arr) % 5 == 0:
        print(f'[key] отказ в доступе ({len(arr)} за 10 мин) с {ip}', file=sys.stderr, flush=True)


def _key_page(message=''):
    """Страница входа: ввести ключ один раз, дальше браузер носит куку."""
    nxt = request.args.get('next') or '/'
    if not nxt.startswith('/'):
        nxt = '/'
    html = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>PlannerTaTe — ключ доступа</title>
<style>body{{font-family:system-ui,Segoe UI,sans-serif;background:#16181f;color:#eef;margin:0;
display:flex;align-items:center;justify-content:center;height:100vh}}form{{background:#22242e;
padding:28px 32px;border-radius:14px;box-shadow:0 10px 30px #0008;min-width:300px}}
h1{{font-size:17px;margin:0 0 6px}}p{{color:#9aa2b5;font-size:13px;margin:0 0 14px;line-height:1.4}}
input{{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:9px;border:1px solid #3a3d4a;
background:#1b1d25;color:#eef;font-size:16px;letter-spacing:3px;text-transform:uppercase}}
button{{margin-top:12px;width:100%;padding:11px;border:0;border-radius:9px;cursor:pointer;
font-size:14px;font-weight:700;color:#fff;background:linear-gradient(180deg,#ffa53c,#f08019)}}</style>
<form method="post" action="/__key"><h1>PlannerTaTe</h1>
<p>{message or 'Введите ключ доступа. Он лежит в файле access_key.txt рядом с graph.json'}</p>
<input name="key" autofocus autocomplete="off" autocapitalize="characters" spellcheck="false">
<input type="hidden" name="next" value="{nxt}"><button>Войти</button></form></html>"""
    return Response(html, status=401, mimetype='text/html')


@app.before_request
def _net_guard():
    if _is_local():
        return None                                  # свой компьютер — как раньше, без ключа
    # Раздача приложения открыта для всех (03.10.26, просьба Ярослава): в самом APK ключа нет,
    # ключ вводится один раз в приложении, поэтому скачать установщик можно без пароля.
    if request.path in ('/apk', '/ping'):
        return None
    want = _access_key()
    got = _client_key()
    if got and hmac.compare_digest(str(got), str(want)):
        return None                                  # ключ верный (заголовок, ссылка или кука)
    if request.method == 'POST' and request.path == '/__key':
        entered = (request.form.get('key') or '').strip().upper()
        if hmac.compare_digest(entered, want):
            nxt = request.form.get('next') or '/'
            if not nxt.startswith('/'):
                nxt = '/'
            resp = redirect(nxt)
            resp.set_cookie('plannertate_key', want, httponly=True, samesite='Lax', max_age=60 * 60 * 24 * 365)
            return resp
        _note_bad_attempt()
        return _key_page('Ключ не подошёл — попробуй ещё раз.')
    _note_bad_attempt()
    return _key_page()


@app.after_request
def _remember_key(resp):
    """Ключ пришёл ссылкой ?key=... — запоминаем куку, чтобы страница работала целиком."""
    if not _is_local() and request.args.get('key'):
        want = _access_key()
        if hmac.compare_digest(str(request.args['key']), str(want)) and not request.cookies.get('plannertate_key'):
            resp.set_cookie('plannertate_key', want, httponly=True, samesite='Lax', max_age=60 * 60 * 24 * 365)
    return resp



# --- Настройки уведомлений (замените на реальные значения) ---
CONFIG = {
    "telegram": {  # Telegram Bot API
        "bot_token": os.environ.get("TG_BOT_TOKEN", ""),   # токен бота из @BotFather
        "chat_id": os.environ.get("TG_CHAT_ID", ""),        # кому отправлять
        "enabled": False,
    },
    "vkmax": {        # VK Max (dev.max.ru Bot API)
        "api_token": os.environ.get("VKMAX_API_TOKEN", ""),  # токен из dev.max.ru
        "endpoint": "https://max.ru/api/v1/messages/send",
        "enabled": False,
    },
}


def _send_telegram(text):
    cfg = CONFIG["telegram"]
    if not cfg["enabled"] or not cfg["bot_token"]:
        return ("off", f"Telegram бот не настроен (TG_BOT_TOKEN)")
    import urllib.request
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
    payload = json.dumps({"chat_id": cfg["chat_id"], "text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return ("ok", "") if data.get("ok") else ("err", data.get("description", ""))


def _send_vkmax(text):
    cfg = CONFIG["vkmax"]
    if not cfg["enabled"] or not cfg["api_token"]:
        return ("off", f"VK Max API не настроен (VKMAX_API_TOKEN)")
    import urllib.request
    req = urllib.request.Request(cfg["endpoint"], data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": cfg["api_token"]})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return ("ok", "") if data.get("status") in (True, "ok") else ("err", str(data))


# --- Напоминания: уведомление на компьютере (Windows) -------------------------------------
# Просьба Ярослава 01.10.26: напоминание с каналом «На компьютере» должно само показать
# уведомление Windows в срок. Показывает backend.py, поэтому работает и когда браузер закрыт
# (нужно, чтобы был запущен backend.py). Повторения бесконечные (решение Ярослава 01.10.26):
# у напоминания есть только время и частота, конца у серии нет; «однократно» прозвучит один раз
# и больше не напомнит — карточка при этом остаётся на холсте.
STATE_FILE = os.path.join(BASE_DIR, "notify_state.json")   # что уже прозвучало: {"<id>": "ГГГГ-ММ-ДД ЧЧ:ММ"}
TICK_SECONDS = 20          # как часто проверяем время
CATCHUP_MINUTES = 10       # если backend.py был выключен, напоминание старше этого — не догоняем

WEEKDAYS = {0, 1, 2, 3, 4}   # понедельник = 0 (datetime.weekday())

import datetime as _dt
import threading as _th
import time as _time


def _parse_date(v):
    try:
        return _dt.date.fromisoformat(str(v or "").strip())
    except Exception:
        return None


def _parse_time(v):
    txt = str(v or "").strip()
    if ":" not in txt:
        return None
    hh, _, mm = txt.partition(":")
    try:
        hh, mm = int(hh), int(mm)
    except Exception:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return _dt.time(hh, mm)


def _matches_repeat(due, repeat, day):
    """Попадает ли день `day` в серию напоминания (серия бесконечная — см. шапку блока)."""
    if day < due:
        return False
    r = (repeat or "once").lower()
    if r in ("once", "однократно"):
        return day == due
    if r == "daily":
        return True
    if r == "weekly":
        return (day - due).days % 7 == 0
    if r == "weekdays":
        return day.weekday() in WEEKDAYS
    if r == "monthly":
        # то же число месяца; если в месяце столько дней нет — последний день месяца
        last = (day.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
        return day.day == min(due.day, last.day)
    return False


def due_reminders(nodes, state, now, catchup_minutes=CATCHUP_MINUTES):
    """Кому пора показать уведомление. Чистая функция — без файлов и без показа: её и проверяем.

    Возвращает список словарей: id, когда (datetime), заголовок, описание.
    Смотрим ТОЛЬКО сегодняшний день: если backend.py был выключен сутки, старые напоминания
    не вываливаются пачкой, а тихо пропускаются.
    """
    out = []
    today = now.date()
    for n in nodes or []:
        if (n.get("kind") or "task") != "notify":
            continue
        due = _parse_date(n.get("due"))
        t = _parse_time(n.get("remindTime"))
        if not due or not t:
            continue
        if not _matches_repeat(due, n.get("repeatMode"), today):
            continue
        when = _dt.datetime.combine(today, t)
        if when > now:
            continue                                     # ещё не время
        if (now - when) > _dt.timedelta(minutes=catchup_minutes):
            continue                                     # время прошло, пока backend был выключен
        if state.get(str(n.get("id"))) == when.strftime("%Y-%m-%d %H:%M"):
            continue                                     # это срабатывание уже прозвучало
        if "pc" not in (n.get("channels") or []):
            continue                                     # канал «На компьютере» не выбран
        out.append({"id": n.get("id"), "when": when, "title": str(n.get("title") or "").strip(),
                    "description": str(n.get("description") or "").strip()})
    out.sort(key=lambda r: r["when"])
    return out


def _show_toast(title, msg):
    """Уведомление Windows. Если winotify недоступен — не падаем, а жалуемся в консоль."""
    try:
        from winotify import Notification, audio
        toast = Notification(app_id="PlannerTaTe", title=title, msg=msg, duration="long")
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return True, ""
    except Exception as e:
        return False, str(e)


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[напоминания] не смог сохранить состояние:", e)


def load_graph_nodes():
    try:
        with open(GRAPH_FILE, encoding="utf-8") as f:
            return (json.load(f) or {}).get("nodes") or []
    except Exception:
        return []


def fire_due_reminders(now=None, dry_run=False):
    """Один проход: что пора — то и показываем. Возвращает список показанного."""
    now = now or _dt.datetime.now()
    nodes = load_graph_nodes()
    state = _load_state()
    fired = []
    for r in due_reminders(nodes, state, now):
        text = r["title"] or "Напоминание"
        msg = r["when"].strftime("%H:%M")
        if r["description"]:
            msg += " · " + r["description"][:200]
        if not dry_run:
            ok, err = _show_toast("⏰ " + text, msg)
            if not ok:
                print("[напоминания] уведомление не показано:", err)
        state[str(r["id"])] = r["when"].strftime("%Y-%m-%d %H:%M")
        fired.append({"id": r["id"], "when": r["when"].strftime("%Y-%m-%d %H:%M"), "title": text})
        print(f"[напоминания] {'(проверка) ' if dry_run else ''}показано: {text} — {msg}")
    if fired and not dry_run:
        _save_state(state)
    return fired


def _reminder_loop():
    while True:
        try:
            fire_due_reminders()
        except Exception as e:
            print("[напоминания] ошибка:", e)
        _time.sleep(TICK_SECONDS)


def start_reminder_thread():
    t = _th.Thread(target=_reminder_loop, name="reminders", daemon=True)
    t.start()
    return t


# --- Routes ---
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.route("/api/load", methods=["GET"])
def api_load():
    if not os.path.exists(GRAPH_FILE):
        return jsonify({"status": "ok", "nodes": [], "links": []})
    try:
        with open(GRAPH_FILE, encoding="utf-8") as f:
            data = json.load(f)
        data, changed = _merge_phone_tasks(data)      # карточки, созданные на телефоне
        if changed:
            with open(GRAPH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/save", methods=["POST"])
def api_save():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "error": "invalid JSON"}), 400
    if not isinstance(data, dict):
        return jsonify({"status": "error", "error": "expected object"}), 400
    # Карточки, созданные на телефоне, не должны теряться, если приложение в браузере
    # сохраняет граф, не зная о них (оно держит граф в памяти).
    data, added = _merge_phone_tasks(data)
    with open(GRAPH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok"})


@app.route("/api/notify", methods=["POST"])
def api_notify():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "error": "invalid JSON"}), 400
    channel = (data.get("channel") or "").lower()
    text = data.get("text", "")
    if not text.strip():
        return jsonify({"status": "error", "error": "empty message"})
    if channel in ("telegram", "tg"):
        status, err = _send_telegram(text)
        return jsonify({"status": status if status == "ok" else "error",
                        "error": err, "channel": "telegram"})
    elif channel in ("vkmax", "vk", "max"):
        status, err = _send_vkmax(text)
        return jsonify({"status": status if status == "ok" else "error",
                        "error": err, "channel": "vkmax"})
    return jsonify({"status": "error", "error": f"unknown channel: {channel}"})


@app.route("/api/reminders/due", methods=["GET"])
def api_reminders_due():
    """Что сейчас пора показать (без показа и без записи) — для проверок и отладки."""
    now = _dt.datetime.now()
    state = _load_state()
    rows = due_reminders(load_graph_nodes(), state, now)
    return jsonify({"status": "ok", "now": now.strftime("%Y-%m-%d %H:%M"), "count": len(rows),
                    "items": [{"id": r["id"], "when": r["when"].strftime("%Y-%m-%d %H:%M"),
                               "title": r["title"]} for r in rows]})


@app.route("/api/reminders/check", methods=["POST"])
def api_reminders_check():
    """Показать всё, что пора, прямо сейчас (кнопка «проверить» / ручной запуск)."""
    fired = fire_due_reminders()
    return jsonify({"status": "ok", "fired": fired})


# Адрес, на котором слушает сервер.
# 01.10.26 по просьбе Ярослава: открыли в домашнюю сеть, чтобы смотреть приложение
# с телефона в браузере (http://192.168.0.101:5001) — раньше было только 127.0.0.1,
# то есть с телефона достучаться было нельзя. Если доступ с телефона не нужен или
# мешает, запусти с PLANNERTATE_HOST=127.0.0.1. Внимание: с 0.0.0.0 приложение доступно
# любому в этой Wi-Fi (у API нет пароля) — поэтому в брандмауэре правило открыто
# только для локальной подсети.
BIND_HOST = os.environ.get("PLANNERTATE_HOST", "0.0.0.0")


@app.route("/api/reminders/export", methods=["GET"])
def api_reminders_export():
    """Расписание срабатываний для телефона (см. reminder_schedule)."""
    try:
        return jsonify(reminder_schedule())
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/task/add", methods=["POST"])
def api_task_add():
    """Принять задачу, созданную на телефоне, и положить карточку в свободное место."""
    data = request.get_json(silent=True) or {}
    try:
        nid, pos = _add_phone_task(data)
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    return jsonify({"status": "ok", "id": nid, "x": pos[0], "y": pos[1]})

@app.route("/ping", methods=["GET"])
def ping():
    """Опознание: приложение на телефоне прощупывает сеть и по этому ответу понимает,
    что нашло именно PlannerTaTe, а не чужой сервер на том же порту. Ключ не требуется."""
    return jsonify({"app": "plannertate", "name": "PlannerTaTe", "port": PORT})


# --- Страница установки приложения на телефон/планшет (04.10.26, просьба Ярослава) ----------
# Ссылка со ключом (?key=...&device=...) ведёт сюда: сначала скачать APK, потом — когда приложение
# уже стоит — одной кнопкой открыть его с готовым адресом компьютера, ключом и типом устройства.
# Так ключ не надо диктовать руками: он приезжает в QR-коде, а приложение подставляет его само.
INSTALL_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlannerTaTe — установка</title>
<style>
body{font-family:system-ui,Segoe UI,sans-serif;background:#16181f;color:#eef;margin:0;padding:24px;line-height:1.5}
.box{max-width:460px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#9aa2b5;font-size:14px;margin:0 0 18px}
.btn{display:block;text-align:center;text-decoration:none;margin:10px 0;padding:14px;border-radius:12px;
font-size:16px;font-weight:700;color:#fff;background:linear-gradient(180deg,#ffa53c,#f08019)}
.btn.ghost{background:#22242e;border:1px solid #3a3d4a;color:#eef;font-weight:600}
ol{color:#c7ccda;font-size:14px;padding-left:20px}
.key{margin-top:16px;padding:12px;border-radius:10px;background:#22242e;border:1px solid #3a3d4a;font-size:14px;color:#9aa2b5}
.key b{color:#fff;font-size:20px;letter-spacing:.14em;font-family:ui-monospace,Consolas,monospace}
.warn{color:#d9822b;font-size:14px}
.foot{margin-top:16px;color:#8b93a6;font-size:12px}
</style></head><body><div class="box">
<h1>PlannerTaTe</h1>
<p class="sub">Установка на {DEV}. Компьютер в сети: <b>{HOST}</b></p>
<ol>
<li>Скачайте приложение и установите его (разрешите установку из этого источника).</li>
<li>Вернитесь сюда и нажмите «Открыть и заполнить» — адрес и ключ подставятся сами.</li>
</ol>
{DL}
<a class="btn ghost" href="{INTENT}">Открыть и заполнить (адрес и ключ)</a>
<div class="key">Ключ доступа: <b>{KEY}</b></div>
<p class="foot">{DEV} должен быть в той же сети Wi-Fi, что и компьютер.</p>
</div></body></html>"""


def _install_page(has_apk):
    from urllib.parse import quote
    device = 'tablet' if (request.args.get('device') or '').strip().lower() == 'tablet' else 'phone'
    key = (request.args.get('key') or '').strip() or _access_key()
    ip = _lan_ip()
    host_port = "%s:%d" % (ip, PORT)
    dev_ru = 'планшет' if device == 'tablet' else 'телефон'
    fallback = "http://%s/apk?raw=1" % host_port
    intent = ("intent://setup?host=%s&port=%d&key=%s&device=%s"
              "#Intent;scheme=plannertate;package=com.plannertate.phone;"
              "S.browser_fallback_url=%s;end" % (ip, PORT, key, device, quote(fallback, safe='')))
    dl = ('<a class="btn" href="/apk?raw=1">Скачать приложение (APK)</a>' if has_apk
          else '<div class="warn">Файл приложения ещё не положен рядом с программой (папка app).</div>')
    html = INSTALL_HTML
    for a, b in (('{DEV}', dev_ru), ('{KEY}', key), ('{HOST}', host_port),
                 ('{DL}', dl), ('{INTENT}', intent.replace('&', '&amp;'))):
        html = html.replace(a, b)
    return Response(html, mimetype='text/html')


@app.route("/apk", methods=["GET"])
def apk_download():
    path = _apk_file()
    has = os.path.exists(path)
    # ?raw=1 или заход без параметров — отдаём сам файл, как раньше.
    if request.args.get("raw") or not (request.args.get("device") or request.args.get("key")):
        if not has:
            return jsonify({"status": "error", "error": "APK ещё не собран"}), 404
        return send_file(path, as_attachment=True, download_name="PlannerTaTe.apk")
    return _install_page(has)


@app.route("/api/phone/state", methods=["GET"])
def phone_state():
    """Что показать на экране установки: свой адрес в сети, ссылку, ключ и признак первого запуска."""
    ip = _lan_ip()
    path = _apk_file()
    key = _access_key()
    return jsonify({
        "firstRun": not KEY_EXISTED,
        "promptSeen": _phone_seen(),
        "lanIp": ip,
        "port": PORT,
        "link": f"http://{ip}:{PORT}/apk",
        # Ссылки установки со ключом и типом устройства (04.10.26): QR ведёт на страницу установки,
        # откуда приложение ставится, а уже установленное — открывается с готовым адресом и ключом.
        "installPhone": f"http://{ip}:{PORT}/apk?key={key}&device=phone",
        "installTablet": f"http://{ip}:{PORT}/apk?key={key}&device=tablet",
        # Кабельный путь (кнопка «Нет Wi-Fi»): адрес адаптера USB-модема, если он поднят (04.10.26)
        "cableIp": _net_addresses().get("cable", ""),
        "cableLink": (f"http://{_net_addresses()['cable']}:{PORT}/apk"
                      if _net_addresses().get("cable") else ""),
        "installPhoneCable": (f"http://{_net_addresses()['cable']}:{PORT}/apk?key={key}&device=phone"
                              if _net_addresses().get("cable") else ""),
        "installTabletCable": (f"http://{_net_addresses()['cable']}:{PORT}/apk?key={key}&device=tablet"
                               if _net_addresses().get("cable") else ""),
        "key": key,
        "apkReady": os.path.exists(path),
        "apkSize": os.path.getsize(path) if os.path.exists(path) else 0,
    })


@app.route("/api/phone/prompt_seen", methods=["POST"])
def phone_prompt_seen():
    """Запомнить, что окно «Установить приложение на телефон?» уже показано (нажали «Позже»)."""
    try:
        with open(PHONE_SEEN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"seen": True, "at": time.strftime('%Y-%m-%d %H:%M')}, f, ensure_ascii=False)
    except OSError as e:
        print('[phone] не смог записать phone_prompt.json:', e, file=sys.stderr, flush=True)
    return jsonify({"status": "ok"})


# --- Резервная копия графа (кнопка-значок в сайдбаре, 04.10.26) ----------------------------
# Раньше копию делал только MCP-сервер перед записью. Теперь её можно сделать и вручную из
# приложения: рядом с graph.json кладём graph.json.bak_<дата>_<время>_manual и держим 20 свежих.
BACKUP_KEEP = 20


@app.route("/api/backup", methods=["POST"])
def api_backup():
    bad = _api_guard()
    if bad:
        return bad
    if not os.path.exists(GRAPH_FILE):
        return jsonify({"status": "error", "error": "графа ещё нет"}), 404
    try:
        import shutil
        name = "graph.json.bak_%s_manual" % time.strftime("%Y-%m-%d_%H%M%S")
        shutil.copy2(GRAPH_FILE, os.path.join(BASE_DIR, name))
        baks = sorted(f for f in os.listdir(BASE_DIR) if f.startswith("graph.json.bak_"))
        for old in baks[:-BACKUP_KEEP]:
            try:
                os.remove(os.path.join(BASE_DIR, old))
            except OSError:
                pass
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    print("[бэкап] создана резервная копия:", name)
    return jsonify({"status": "ok", "file": name})


# --- Восстановление графа из резервной копии (кнопка-значок рядом с «создать копию», 04.10.26) ---
# Список копий и подмена графа. Перед подменой текущий граф тоже сохраняется копией, поэтому
# неверное восстановление можно отменить. Доступ — только со своего компьютера (как у бэкапа).
_BACKUP_NAME_RE = r"^graph\.json\.bak_[A-Za-z0-9_.\-]+$"


@app.route("/api/backups", methods=["GET"])
def api_backups():
    bad = _api_guard()
    if bad:
        return bad
    items = []
    try:
        for fn in os.listdir(BASE_DIR):
            if not (fn.startswith("graph.json.bak_") or fn == "graph.json.pretest"):
                continue
            try:
                st = os.stat(os.path.join(BASE_DIR, fn))
            except OSError:
                continue
            items.append({"file": fn, "size": st.st_size,
                          "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    except OSError as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    items.sort(key=lambda r: r["file"], reverse=True)     # в имени дата → новые сверху
    return jsonify({"status": "ok", "items": items[:60]})


@app.route("/api/restore", methods=["POST"])
def api_restore():
    bad = _api_guard()
    if bad:
        return bad
    import re as _re
    import shutil
    data = request.get_json(silent=True) or {}
    name = os.path.basename(str(data.get("file") or "").strip())
    if not _re.match(_BACKUP_NAME_RE, name):
        return jsonify({"status": "error", "error": "неверное имя копии"}), 400
    src = os.path.join(BASE_DIR, name)
    if not os.path.exists(src):
        return jsonify({"status": "error", "error": "копия не найдена"}), 404
    try:
        with open(src, encoding="utf-8") as f:
            json.load(f)                                  # копия должна быть валидным графом
        safety = ""
        if os.path.exists(GRAPH_FILE):
            safety = "graph.json.bak_%s_before_restore" % time.strftime("%Y-%m-%d_%H%M%S")
            shutil.copy2(GRAPH_FILE, os.path.join(BASE_DIR, safety))
        tmp = GRAPH_FILE + ".tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, GRAPH_FILE)                       # подмена одним движением
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    print("[восстановление] граф заменён копией:", name, "| прежний сохранён как:", safety or "(нет)")
    return jsonify({"status": "ok", "file": name, "safety": safety})

# --- Обмен с телефоном (приложение PlannerTaTe для Android) --------------------------------
# Ярослав 01.10.26: приложение на телефоне скачивает копию страницы и данные, ставит свои
# будильники по готовому расписанию и умеет СОЗДАВАТЬ задачи. Правок существующего с телефона
# не бывает — поэтому и разбора конфликтов не нужно.
PHONE_TASKS_FILE = os.path.join(BASE_DIR, "phone_tasks.json")


def _phone_tasks_load():
    if not os.path.exists(PHONE_TASKS_FILE):
        return {}
    try:
        with open(PHONE_TASKS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _phone_tasks_save(d):
    try:
        with open(PHONE_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[телефон] не смог сохранить список задач: " + str(e))


def _merge_phone_tasks(graph):
    """Вставить карточки с телефона (и их связи), которых нет в графе.

    Нужно потому, что приложение в браузере держит граф в памяти и сохраняет его целиком:
    без этой вставки карточка, созданная на телефоне, пропала бы при первом же сохранении
    с компьютера. Когда браузер присылает граф, в котором карточка уже есть, она считается
    «усвоенной» и убирается из списка. Связь едет вместе с карточкой — иначе напоминание,
    созданное на телефоне, осталось бы без привязки к задаче (Ярослав 02.10.26).
    """
    pending = _phone_tasks_load()
    if not pending:
        return graph, False
    nodes = graph.get("nodes") or []
    have = {n.get("id") for n in nodes}
    links = graph.get("links")
    if isinstance(links, dict):
        links = list(links.values())
    if not isinstance(links, list):
        links = []
    have_link = {l[0] for l in links if isinstance(l, list) and l}
    changed = False
    left = {}
    for key, rec in pending.items():
        node = rec.get("node") if isinstance(rec, dict) and "node" in rec else rec
        if not isinstance(node, dict):
            continue
        extra = rec.get("links") if isinstance(rec, dict) else None
        fresh = False
        if node.get("id") not in have:
            nodes.append(node)
            have.add(node.get("id"))
            fresh = True
        for l in extra or []:
            if isinstance(l, list) and l and l[0] not in have_link:
                links.append(l)
                have_link.add(l[0])
                fresh = True
        if fresh:
            changed = True
            left[key] = rec                      # ещё не усвоено — держим дальше
    if changed:
        graph["nodes"] = nodes
        graph["links"] = links
        graph["last_node_id"] = max([int(graph.get("last_node_id") or 0)] + [int(n.get("id") or 0) for n in nodes])
        if have_link:
            graph["last_link_id"] = max([int(graph.get("last_link_id") or 0)] + [int(v) for v in have_link])
    if left != pending:
        _phone_tasks_save(left)
    return graph, changed


# Цвет карточки-напоминания — тот же, что в приложении (App.vue, NOTIFY_COLOR).
NOTIFY_COLOR = "#9b7bd9"


def _find_free_pos_beside(nodes, x, y, w=100, h=56, pad=18, step=26):
    """Место для карточки, ПРИВЯЗАННОЙ к другой: сразу справа от неё, а если занято — ниже.

    Так же ставит напоминание и приложение (кнопка «+⏰»): родитель → напоминание справа.
    Без этого напоминание улетало бы в общий «свободный» угол и связь тянулась бы через холст.
    """
    rects = []
    for n in nodes:
        p = n.get("pos") or [0, 0]
        s = n.get("size") or [100, 56]
        rects.append((p[0], p[1], p[0] + s[0], p[1] + s[1]))
    for _ in range(200):
        clash = False
        for (l, tp, r, b) in rects:
            if not (x + w + pad <= l or r + pad <= x or y + h + pad <= tp or b + pad <= y):
                clash = True
                break
        if not clash:
            break
        y += h + step
    return [int(round(x)), int(round(y))]


def _phone_size_for(title, base=(100, 56)):
    """Размер карточки под название — как fitCard в приложении: ширина 100…200."""
    w, h = int(base[0] or 100), int(base[1] or 56)
    extra = len(title) - 14
    if extra > 0:
        w = min(200, w + extra * 6)
    return [w, h]


def _phone_card(tpl, nid, pos, size, title, kind):
    """Карточка ровно того же вида, как живые карточки в graph.json.

    Форму входов/выходов берём у живой карточки, но ССЫЛКИ НА СВЯЗИ не переносим:
    у новой карточки связей ещё нет, а унаследованный номер связи сделал бы вход
    «занятым» и связь задачи с напоминанием не нарисовалась бы.
    """
    def _ports(src, is_input):
        out = []
        for p in src or []:
            q = dict(p) if isinstance(p, dict) else {}
            if is_input:
                q["link"] = None
            else:
                q["links"] = []
            out.append(q)
        return out
    t = tpl or {}
    return {
        "id": nid, "type": "rectnode", "pos": pos, "size": size,
        "flags": {}, "order": 0, "mode": 0,
        "inputs": _ports(t.get("inputs"), True),
        "outputs": _ports(t.get("outputs"), False),
        "title": title, "properties": {},
        "color": t.get("color") or "#5b8fd9",
        "bgcolor": "rgba(0,0,0,0)",
        "status": "", "description": "", "due": "",
        "tags": [], "image": "", "file": "", "dimMode": "auto", "kind": kind,
    }


def _find_free_pos(nodes, w=100, h=56, pad=18):
    """Свободное место для новой карточки: правее всех существующих, а если там занято — ниже."""
    rects = []
    for n in nodes:
        p = n.get("pos") or [0, 0]
        s = n.get("size") or [100, 56]
        rects.append((p[0], p[1], p[0] + s[0], p[1] + s[1]))
    if not rects:
        return [60, 60]
    x = max(r[2] for r in rects) + 60
    y = min(r[1] for r in rects)
    for _ in range(400):
        clash = False
        for (l, t, r, b) in rects:
            if not (x + w + pad <= l or r + pad <= x or y + h + pad <= t or b + pad <= y):
                clash = True
                break
        if not clash:
            return [int(round(x)), int(round(y))]
        y += h + 26
    return [int(round(x)), int(round(y))]


def _add_phone_task(data):
    """Создать карточки из данных телефона. Возвращает (id, pos) или бросает ValueError.

    Галочка «Напоминание» на телефоне даёт ДВЕ карточки: саму задачу и привязанное к ней
    напоминание — ровно так, как это делает кнопка «+⏰» в панели задачи (родитель →
    напоминание). Раньше в этом случае появлялась одна карточка, и это было напоминание:
    самой задачи не возникало (замечание Ярослава 02.10.26).
    """
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("нет названия")
    with open(GRAPH_FILE, encoding="utf-8") as f:
        graph = json.load(f)
    nodes = graph.get("nodes") or []
    links = graph.get("links")
    if isinstance(links, dict):
        links = list(links.values())
    if not isinstance(links, list):
        links = []
    template = next((n for n in nodes if (n.get("kind") or "task") == "task"), None)
    notify_tpl = next((n for n in nodes if (n.get("kind") or "task") == "notify"), None)
    # Статусы — ровно те же пять, что в панели карточки на компьютере (замечание Ярослава 03.10.26):
    # none («—», статус не заполнен), done, wip, waiting, problem. Русские и английские подписи
    # принимаем от прежних сборок телефона и переводим в ключи.
    status = str(data.get("status") or "waiting").strip()
    status = {"—": "none", "Готово": "done", "В работе": "wip", "Ожидает": "waiting",
              "Проблема": "problem", "Done": "done", "In progress": "wip",
              "Waiting": "waiting", "Problem": "problem"}.get(status, status)
    if status not in ("none", "done", "wip", "waiting", "problem"):
        status = "waiting"
    due = (data.get("due") or "").strip()
    # С телефона можно создать и просто задачу, и задачу с напоминанием (галочка «Напоминание»).
    want_notify = data.get("kind") == "notify"
    remind = "09:00"
    rem_due = due
    repeat = "once"
    chans = ["phone"]
    if want_notify:
        import re as _re
        # У напоминания может быть своя дата (поле «Дата напоминания» на телефоне); если её нет —
        # берём срок задачи, как было. Без даты напоминание бессмысленно: компьютер не знает, когда звонить.
        rem_due = (str(data.get("remindDate") or "").strip() or due)
        if not rem_due:
            raise ValueError("напоминанию нужен срок (дата)")
        raw = str(data.get("remindTime") or "").strip().replace(".", ":")
        m = _re.match(r"^(\d{1,2}):(\d{2})$", raw)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("неверное время напоминания")
        remind = "%02d:%s" % (int(m.group(1)), m.group(2))
        # Повторение и каналы — ровно те значения, что понимает панель карточки:
        # once | daily | weekly | weekdays | monthly и pc (Windows) | phone (телефон).
        repeat = str(data.get("repeatMode") or "once").strip().lower()
        if repeat not in ("once", "daily", "weekly", "weekdays", "monthly"):
            repeat = "once"
        raw_ch = data.get("channels")
        if isinstance(raw_ch, str):
            raw_ch = raw_ch.replace(";", ",").split(",")
        chans = [str(c).strip().lower() for c in (raw_ch or [])]
        chans = [c for c in chans if c in ("pc", "phone", "tablet", "telegram", "vkmax")]
        if not chans:
            chans = ["phone"]        # по умолчанию — на телефоне: напоминание и создали на нём
    order0 = max([int(n.get("order") or 0) for n in nodes] + [0])
    nid = int(graph.get("last_node_id") or 0) + 1
    size = list(template.get("size")) if template and template.get("size") else [100, 56]
    # Родитель (необязательно): с телефона можно создать и ПОДЗАДАЧУ — тогда карточка встаёт
    # рядом с родителем и связывается с ним (как двойной клик по карточке в приложении).
    parent = None
    if data.get("parent") not in (None, "", 0, "0"):
        try:
            pid = int(data.get("parent"))
        except Exception:
            pid = 0
        parent = next((n for n in nodes if int(n.get("id") or 0) == pid), None)
        if parent is None:
            print("[телефон] родитель id " + str(pid) + " не найден — создаю обычную задачу")
    if parent is not None:
        ppos = parent.get("pos") or [0, 0]
        psize = parent.get("size") or [100, 56]
        pos = _find_free_pos_beside(nodes, int(ppos[0]) + int(psize[0]) + 60, int(ppos[1]),
                                    int(size[0] or 100), int(size[1] or 56))
    else:
        pos = _find_free_pos(nodes, int(size[0] or 100), int(size[1] or 56))
    node = _phone_card(template, nid, pos, size, title, "task")
    node["order"] = order0 + 1
    node["status"] = status
    node["description"] = (data.get("description") or "").strip()
    node["due"] = due
    nodes.append(node)
    # Подзадачи: каждая строка поля «Подзадачи» с телефона — ОТДЕЛЬНАЯ карточка,
    # привязанная к задаче. То же самое делает поле «Подзадачи» в панели карточки.
    raw_subs = data.get("subtasks")
    if isinstance(raw_subs, str):
        raw_subs = raw_subs.replace("\r", "\n").split("\n")
    sub_titles = []
    for s in (raw_subs or []):
        s = str(s).strip()
        if s:
            sub_titles.append(s)
    kept = []                     # (карточка, её входящая связь) — для переноса в браузер
    new_links = []
    next_lid = int(graph.get("last_link_id") or 0)
    if parent is not None:
        next_lid += 1
        new_links.append([next_lid, int(parent["id"]), 0, nid, 0, "*"])   # родитель → задача
        if node.get("inputs"):
            node["inputs"][0]["link"] = next_lid
        pouts = parent.get("outputs") or []
        if pouts:
            cur = pouts[0].get("links")
            pouts[0]["links"] = (list(cur) if isinstance(cur, list) else []) + [next_lid]
    if want_notify:
        # Напоминание — отдельная карточка, привязанная к задаче (выход задачи → вход напоминания).
        rid = nid + 1
        rsize = list(notify_tpl.get("size")) if notify_tpl and notify_tpl.get("size") else list(size)
        rpos = _find_free_pos_beside(nodes, int(pos[0]) + int(size[0]) + 60, int(pos[1]),
                                     int(rsize[0] or 100), int(rsize[1] or 56))
        rem = _phone_card(notify_tpl or template, rid, rpos, rsize, title, "notify")
        rem["order"] = order0 + 2
        rem["status"] = ""
        rem["description"] = node["description"]     # снимок с задачи — как делает панель «+⏰»
        rem["due"] = rem_due
        rem["color"] = NOTIFY_COLOR
        rem["remindTime"] = remind
        rem["repeatMode"] = repeat
        # Куда придёт — выбор Ярослава на экране телефона: «На телефоне» (будильник телефона)
        # и/или «На компьютере» (уведомление Windows). Компьютер сам читает каналы:
        # телефон получает в расписании только «phone», тост Windows — только «pc».
        rem["channels"] = chans
        next_lid += 1
        new_links.append([next_lid, nid, 0, rid, 0, "*"])
        if node.get("outputs"):
            outs = node["outputs"][0]
            cur = outs.get("links")
            outs["links"] = (list(cur) if isinstance(cur, list) else []) + [next_lid]
        if rem.get("inputs"):
            rem["inputs"][0]["link"] = next_lid
        nodes.append(rem)
        kept.append((rem, [[next_lid, nid, 0, rid, 0, "*"]]))
    for k, stitle in enumerate(sub_titles):
        sid = nid + 1 + (1 if want_notify else 0) + k
        ssize = _phone_size_for(stitle, size)
        spos = _find_free_pos_beside(nodes, int(pos[0]) + int(size[0]) + 60, int(pos[1]),
                                     int(ssize[0]), int(ssize[1]))
        sub = _phone_card(template, sid, spos, ssize, stitle, "task")
        sub["order"] = order0 + 3 + k
        sub["status"] = "waiting"
        nodes.append(sub)
        next_lid += 1
        link = [next_lid, nid, 0, sid, 0, "*"]                      # задача → подзадача
        new_links.append(link)
        if sub.get("inputs"):
            sub["inputs"][0]["link"] = next_lid
        outs = node.get("outputs") or []
        if outs:
            cur = outs[0].get("links")
            outs[0]["links"] = (list(cur) if isinstance(cur, list) else []) + [next_lid]
        kept.append((sub, [link]))
    if next_lid > int(graph.get("last_link_id") or 0):
        graph["last_link_id"] = next_lid
    links = links + new_links
    graph["nodes"] = nodes
    graph["links"] = links
    graph["last_node_id"] = max([int(graph.get("last_node_id") or 0)] + [int(n.get("id") or 0) for n in nodes])
    with open(GRAPH_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    pending = _phone_tasks_load()
    # Держим карточки (и их связи) до тех пор, пока браузер не пришлёт граф, где они уже есть.
    pending[str(nid)] = {"node": node, "links": [l for l in new_links if l[3] == nid]}
    for card, lks in kept:
        pending[str(card["id"])] = {"node": card, "links": lks}
    _phone_tasks_save(pending)
    extra = (" + напоминание id " + str(nid + 1)) if want_notify else ""
    if sub_titles:
        extra += " + подзадач: " + str(len(sub_titles))
    print("[телефон] принята задача id " + str(nid) + extra + ": " + title)
    return nid, pos


def reminder_schedule(days=30, limit_per_item=60):
    """Расписание срабатываний для телефона: компьютер считает сам, телефон только ставит будильники."""
    import datetime as _dt          # модуль datetime в этом файле импортируется внутри функций
    now = _dt.datetime.now()
    today = now.date()
    out = []
    for n in load_graph_nodes():
        if (n.get("kind") or "task") != "notify":
            continue
        # Отдаём то, что должно звонить на телефоне ИЛИ на планшете (04.10.26): каналов стало три,
        # а устройств — два. Кто из них поставит будильник, решает САМ телефон/планшет по своему
        # типу (канал «phone» или «tablet») — компьютер лишь отдаёт расписание с каналами.
        _chans = n.get("channels") or []
        if not ("phone" in _chans or "tablet" in _chans):
            continue
        due = _parse_date(n.get("due"))
        t = _parse_time(n.get("remindTime"))
        if not due or not t:
            continue
        repeat = n.get("repeatMode") or "once"
        firings = []
        for shift in range(0, days + 1):
            day = today + _dt.timedelta(days=shift)
            if not _matches_repeat(due, repeat, day):
                continue
            when = _dt.datetime.combine(day, t)
            if when <= now:
                continue
            firings.append(when.strftime("%Y-%m-%d %H:%M"))
            if len(firings) >= limit_per_item:
                break
        if not firings:
            continue
        out.append({
            "id": n.get("id"),
            "title": n.get("title") or "",
            "description": (n.get("description") or "").strip()[:300],
            "channels": n.get("channels") or [],
            "firings": firings,
        })
    return {"status": "ok", "now": now.strftime("%Y-%m-%d %H:%M"), "days": days, "items": out}



# --- Файлы-ссылки на карточках: выбрать и открыть системной программой --------------
# Ярослав 03.10.26: «пусть в карточке остаётся ссылка на файл в системе, а по клику он
# открывается стандартной программой; копировать файлы в папку приложения не нужно».
# Файлы НЕ копируются — хранится только путь.
#
# ЗАЩИТА. Сервер слушает 0.0.0.0 (с ним работает телефон), поэтому «открыть файл» разрешено
# ТОЛЬКО с самого этого компьютера. Плюс требуем свой заголовок X-Plannertate-Client: чужой сайт в
# браузере не сможет дёрнуть эндпоинт без CORS-preflight, а мы его не разрешаем.
def _api_guard():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"status": "error", "error": "только с этого компьютера"}), 403
    if request.headers.get("X-Plannertate-Client") != "1":
        return jsonify({"status": "error", "error": "нет заголовка клиента"}), 403
    return None


@app.route("/api/pick_file", methods=["POST"])
def api_pick_file():
    """Нативный диалог выбора файла ЛЮБОГО типа. Путь берём у Windows, а не у браузера:
    браузер путь выбранного или перетащенного файла не отдаёт (приватность), а сервер
    работает на том же компьютере и видит файловую систему как обычная программа."""
    bad = _api_guard()
    if bad:
        return bad
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    folder = str(data.get("folder") or "").strip()
    script = os.path.join(RES_DIR, "pick_file.py")
    if FROZEN:
        # Собранный exe — не интерпретатор Python: запускаем его же в режиме диалога.
        cmd = [sys.executable, "--pick-file", name, folder]
    elif os.path.exists(script):
        cmd = [sys.executable, script, name, folder]
    else:
        return jsonify({"status": "error", "error": "нет pick_file.py"}), 500
    try:
        r = subprocess.run(cmd,
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
    except Exception as e:
        return jsonify({"status": "error", "error": "диалог не открылся: %s" % e}), 500
    path = (r.stdout or "").strip()
    if not path:
        return jsonify({"status": "cancel"})          # пользователь закрыл диалог
    return jsonify({"status": "ok", "path": os.path.normpath(path)})


@app.route("/api/open_file", methods=["POST"])
def api_open_file():
    """Открыть файл-ссылку стандартной программой системы (Windows: os.startfile)."""
    bad = _api_guard()
    if bad:
        return bad
    data = request.get_json(silent=True) or {}
    path = str(data.get("path") or "").strip().strip('"')
    if not path or not os.path.isabs(path):
        return jsonify({"status": "error", "error": "нужен полный путь к файлу"}), 400
    if not os.path.isfile(path):
        return jsonify({"status": "error", "error": "файл не найден"}), 404
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)                        # Windows: ассоциация системы (Блокнот, плеер и т.п.)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
    except Exception as e:
        return jsonify({"status": "error", "error": "не удалось открыть: %s" % e}), 500
    return jsonify({"status": "ok"})


# --- Лицензия / поддержка автора (03.10.26, просьба Ярослава) ------------------------------
# Флаг «человек нажал Оплатить» лежит отдельным файлом рядом с graph.json: перезапуск сервера
# его не сбрасывает, поэтому кнопка «Лицензия» больше не показывается никогда.
@app.route("/api/license", methods=["GET"])
def api_license():
    done = False
    try:
        with open(LICENSE_FILE, encoding="utf-8") as f:
            done = bool((json.load(f) or {}).get("done"))
    except Exception:
        done = False                                    # файла нет — лицензию ещё не оплачивали
    return jsonify({"status": "ok", "done": done})


@app.route("/api/license_done", methods=["POST"])
def api_license_done():
    bad = _api_guard()
    if bad:
        return bad
    data = request.get_json(silent=True) or {}
    rec = {
        "done": True,
        "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "amount": data.get("amount"),                   # сумма в рублях, которую выбрал человек
        "currency": "RUB",
        "usd": data.get("usd"),
        "row": data.get("text"),                        # строка оценки, которую он выбрал
    }
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    return jsonify({"status": "ok"})


def _owner_machine():
    """Запрос пришёл с самого компьютера хозяина: сам computer — это 127.0.0.1 или его адрес
    в сети. Нужно, чтобы тему не перебил чужой браузер в сети (он ходит с другого адреса).
    Проверка именно здесь, а не в браузере: браузер не отличает «свой» адрес от «гостевого» —
    у хозяина страница может быть открыта и по сетевому адресу (03.10.26, разбор бага)."""
    addr = (request.remote_addr or "").strip()
    if addr in ("127.0.0.1", "::1"):
        return True
    try:
        return addr == _lan_ip()
    except Exception:
        return False


@app.route("/api/ui_state", methods=["GET", "POST"])
def api_ui_state():
    """Тема оформления компьютера: телефон читает её при синхронизации, компьютер пишет свою."""
    if request.method == "GET":
        state = {}
        try:
            with open(UI_FILE, encoding="utf-8") as f:
                state = json.load(f) or {}
        except Exception:
            state = {}
        return jsonify({"theme": state.get("theme") or "", "custom": state.get("custom") or {}})
    data = request.get_json(silent=True) or {}
    theme = str(data.get("theme") or "").strip()
    state = {}
    try:
        with open(UI_FILE, encoding="utf-8") as f:
            state = json.load(f) or {}
    except Exception:
        state = {}
    if not _owner_machine():
        print("[тема] отказ: попытка задать тему с адреса", request.remote_addr)
        return jsonify({"status": "ignored", "reason": "not the owner machine"})
    state["theme"] = theme
    # Настройки «Своей» темы (палитра, шрифт, жирность, заглавные): без них телефон показывал
    # «свою» тему пустой, с базовой палитрой и своим шрифтом (нашёл Ярослав 03.10.26).
    # Значение приходит из сети, поэтому берём только известные поля и приводим их к типу.
    custom = data.get("custom")
    if isinstance(custom, dict):
        clean = {"base": str(custom.get("base") or "")[:20], "font": str(custom.get("font") or "")[:60]}
        try:
            w = int(custom.get("weight") or 400)
        except Exception:
            w = 400
        clean["weight"] = w if 100 <= w <= 900 else 400
        clean["caps"] = bool(custom.get("caps"))
        if clean["base"]:
            state["custom"] = clean
    state["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        tmp = UI_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, UI_FILE)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    print("[тема] компьютер сообщил:", theme or "(пусто)", "| настройки:",
          state.get("custom") or "нет")
    return jsonify({"status": "ok", "theme": theme})


@app.route("/api/open_url", methods=["POST"])
def api_open_url():
    """Открыть ссылку в браузере СИСТЕМЫ (страница поддержки): окно приложения может быть
    без вкладок, а сервер работает на этом же компьютере и умеет позвать браузер."""
    bad = _api_guard()
    if bad:
        return bad
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return jsonify({"status": "error", "error": "нужна http(s)-ссылка"}), 400
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception as e:
        return jsonify({"status": "error", "error": "не удалось открыть: %s" % e}), 500
    return jsonify({"status": "ok"})




if __name__ == "__main__":
    _access_key()      # создаём/печатаем ключ доступа сразу при запуске
    import sys as _sys
    if "--test-toast" in _sys.argv:
        # показать пробное уведомление Windows (проверить, что тосты доходят)
        ok, err = _show_toast("⏰ PlannerTaTe", "Проверка уведомления — всё работает")
        print("пробное уведомление:", "показано" if ok else "НЕ показано: " + err)
        _sys.exit(0 if ok else 1)
    if "--reminders" in _sys.argv:
        # разовый проход по напоминаниям (ручная проверка, без запуска сервера)
        fired = fire_due_reminders()
        print("показано напоминаний:", len(fired))
        _sys.exit(0)
    print("PlannerTaTe backend на http://localhost:%d  (Ctrl+C для остановки)" % PORT)
    print("Папка с данными: %s" % BASE_DIR)
    print("Установка на телефон: боковая панель → «Установить приложение на телефон»")
    print("Ссылка на приложение для телефона: http://%s:%d/apk" % (_lan_ip(), PORT))
    start_reminder_thread()      # напоминания «на компьютере» — даже если браузер закрыт
    print("Напоминания включены: проверяю каждые", TICK_SECONDS, "с")
    app.run(host=BIND_HOST, port=PORT, debug=False)
