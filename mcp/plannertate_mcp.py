"""PlannerTaTe — MCP-сервер для управления планировщиком через Hermes.

Что это: набор инструментов, которые Hermes видит как обычные (mcp_plannertate_*).
Работает напрямую с graph.json (формат LiteGraph) и дёргает HTTP-API приложения для
статуса/запуска/остановки. Перед КАЖДОЙ записью делает резервную копию графа.

Важно про открытое окно: приложение держит граф в памяти браузера и сохраняет его
целиком. Если оно открыто и ты правишь граф через Hermes, то при следующем сохранении
из окна правки из Hermes затрутся. Поэтому каждая запись возвращает предупреждение —
обнови страницу (F5), чтобы окно подтянуло свежий файл.

Запуск (Hermes делает это сам, см. mcp_servers в config.yaml):
    <hermes-venv>/python.exe plannertate_mcp.py

Переопределяется переменными окружения (нужно для тестов на копии графа):
    PLANNERTATE_DIR, PLANNERTATE_GRAPH, PLANNERTATE_API
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from mcp.server import MCPServer   # mcp 2.0: класс MCPServer (прежний FastMCP переехал)

# --- Где что лежит -------------------------------------------------------------------
APP_DIR = Path(os.environ.get("PLANNERTATE_DIR", r"C:\Users\Yar\PycharmProjects\PlannerTaTe"))
GRAPH_FILE = Path(os.environ.get("PLANNERTATE_GRAPH", str(APP_DIR / "graph.json")))
API = os.environ.get("PLANNERTATE_API", "http://127.0.0.1:5001").rstrip("/")
FRONTEND_DIR = APP_DIR / "frontend"
# Скрипт снимка лежит рядом с остальными браузерными пробами: Node ищет playwright-core
# НЕ по рабочей папке, а вверх от самого скрипта — из mcp/ он его не находит (проверено 03.10.26).
SNAPSHOT_SCRIPT = FRONTEND_DIR / "workspace" / "snapshot_graph.mjs"
PYTHON312 = r"C:\Users\Yar\AppData\Local\Programs\Python\Python312\python.exe"
BACKUP_KEEP = 20

mcp = MCPServer("plannertate")


def _log(*a):
    """Логи — только в stderr: stdout занят протоколом MCP."""
    print(*a, file=sys.stderr, flush=True)


# --- Словари приложения (совпадают с frontend/src/i18n.js) ---------------------------
NODE_COLORS = {
    "белый": "#f5f5f5", "зелёный": "#7bc67b", "зеленый": "#7bc67b", "жёлтый": "#e6c34a",
    "желтый": "#e6c34a", "оранжевый": "#e08a3c", "красный": "#d95f5f", "синий": "#5b8fd9",
    "фиолетовый": "#9b7bd9", "серый": "#bdbdbd",
}
STATUSES = {
    "": "", "—": "", "нет": "", "none": "",
    "готово": "done", "done": "done", "выполнено": "done",
    "в работе": "wip", "работа": "wip", "wip": "wip", "начато": "wip",
    "ожидает": "waiting", "ожидание": "waiting", "waiting": "waiting",
    "проблема": "problem", "проблемы": "problem", "problem": "problem",
}
REPEATS = {
    "однократно": "once", "один раз": "once", "once": "once",
    "ежедневно": "daily", "каждый день": "daily", "daily": "daily",
    "еженедельно": "weekly", "каждую неделю": "weekly", "weekly": "weekly",
    "по будням": "weekdays", "будни": "weekdays", "weekdays": "weekdays",
    "ежемесячно": "monthly", "каждый месяц": "monthly", "monthly": "monthly",
}
CHANNELS = {
    "пк": "pc", "комп": "pc", "компьютер": "pc", "pc": "pc",
    "тел": "phone", "телефон": "phone", "phone": "phone",
    "тг": "telegram", "телеграм": "telegram", "телеграмм": "telegram", "telegram": "telegram",
    "макс": "vkmax", "вк": "vkmax", "vkmax": "vkmax",
}


# --- Работа с графом -----------------------------------------------------------------
def _load() -> dict:
    if not GRAPH_FILE.exists():
        raise RuntimeError(f"Нет файла графа: {GRAPH_FILE}")
    try:
        with GRAPH_FILE.open(encoding="utf-8") as f:
            g = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"graph.json повреждён: {e}")
    g.setdefault("nodes", [])
    g.setdefault("links", [])
    return g


def _backup(tag: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = GRAPH_FILE.with_name(f"{GRAPH_FILE.name}.bak_{ts}_{tag}")
    shutil.copy2(GRAPH_FILE, dest)
    old = sorted(GRAPH_FILE.parent.glob(f"{GRAPH_FILE.name}.bak_*"))
    for f in old[:-BACKUP_KEEP]:
        try:
            f.unlink()
        except OSError:
            pass
    return dest


def _app_running() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/api/load", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _save(g: dict, tag: str) -> str:
    """Записать граф атомарно, вернуть предупреждение (если окно приложения открыто)."""
    bak = _backup(tag)
    tmp = GRAPH_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
    os.replace(tmp, GRAPH_FILE)
    note = f"Записано в graph.json (бэкап: {bak.name})."
    if _app_running():
        note += (" ВНИМАНИЕ: приложение сейчас открыто — нажми F5 (обнови страницу), "
                 "иначе его следующее сохранение затрёт эти изменения.")
    return note


def _resolve(g: dict, task: str) -> dict:
    """Найти карточку по номеру (#120 / 120) или по части названия."""
    s = str(task).strip()
    m = re.fullmatch(r"#?(\d+)", s)
    if m:
        nid = int(m.group(1))
        for n in g["nodes"]:
            if n.get("id") == nid:
                return n
        raise RuntimeError(f"Карточки с номером {nid} нет.")
    low = s.lower()
    hits = [n for n in g["nodes"] if low in str(n.get("title", "")).lower()]
    if not hits:
        raise RuntimeError(f"Не нашёл карточку «{s}». Вызови list_tasks, чтобы увидеть все.")
    if len(hits) > 1:
        names = ", ".join(f"#{n['id']} {n['title']}" for n in hits[:6])
        raise RuntimeError(f"Под «{s}» подходит несколько карточек: {names}. Уточни (можно номером).")
    return hits[0]


def _line(n: dict) -> str:
    bits = [f"#{n['id']}", f"[{n.get('status') or '—'}]", str(n.get("title", ""))]
    if n.get("due"):
        bits.append(f"срок {n['due']}")
    if n.get("remindTime"):
        bits.append(f"в {n['remindTime']}")
    if n.get("repeatMode") and n["repeatMode"] != "once":
        bits.append(f"повтор {n['repeatMode']}")
    if n.get("channels"):
        bits.append("каналы " + ",".join(n["channels"]))
    if n.get("tags"):
        bits.append("теги " + ",".join(n["tags"]))
    if n.get("kind") == "notify":
        bits.insert(2, "(напоминание)")
    return " ".join(bits)


def _norm_status(v: str) -> str:
    key = str(v or "").strip().lower()
    if key not in STATUSES:
        raise RuntimeError(f"Статус «{v}» не знаю. Можно: Готово, В работе, Ожидает, Проблема или пусто.")
    return STATUSES[key]


def _norm_color(v: str) -> str:
    key = str(v or "").strip().lower()
    if not key:
        return ""
    if key in NODE_COLORS:
        return NODE_COLORS[key]
    if re.fullmatch(r"#[0-9a-fA-F]{6}", key):
        return key
    raise RuntimeError(f"Цвет «{v}» не знаю. Можно: {', '.join(NODE_COLORS)} или свой #rrggbb.")


def _norm_repeat(v: str) -> str:
    key = str(v or "").strip().lower()
    if key not in REPEATS:
        raise RuntimeError(f"Повтор «{v}» не знаю. Можно: однократно, ежедневно, еженедельно, по будням, ежемесячно.")
    return REPEATS[key]


def _norm_channels(v) -> list:
    if v is None or v == "":
        return ["pc", "phone"]
    if isinstance(v, str):
        parts = [p for p in re.split(r"[,;/]| и ", v) if p.strip()]
    else:
        parts = list(v)
    out = []
    for p in parts:
        key = str(p).strip().lower()
        if key not in CHANNELS:
            raise RuntimeError(f"Канал «{p}» не знаю. Можно: пк, телефон, телеграм, макс.")
        code = CHANNELS[key]
        if code not in out:
            out.append(code)
    return out or ["pc", "phone"]


def _free_spot(g: dict, near: str = "") -> list:
    """Куда положить новую карточку: рядом с указанной или справа от всех."""
    if near:
        anchor = _resolve(g, near)
        x, y = anchor["pos"]
        return [x + anchor.get("size", [100, 56])[0] + 60, y]
    if not g["nodes"]:
        return [300, 300]
    xs = [n["pos"][0] for n in g["nodes"]]
    ys = [n["pos"][1] for n in g["nodes"]]
    return [max(xs) + 160, min(ys)]


def _new_node(g: dict, title: str, pos, *, kind="task", status="", color="", description="",
              due="", tags=None, remind_time="", repeat="once", channels=None) -> dict:
    # Счётчик берём не только из last_node_id, но и из максимального id узлов: карточки,
    # созданные телефоном/планшетом (диапазоны 1 000 000+ / 2 000 000+), счётчик компьютера
    # НЕ поднимают (так задумано в backend.py), и без этой проверки новый id совпадал
    # с телефонным — две карточки с одним номером (проверено 08.10.26: Hh.ru #1000055).
    g["last_node_id"] = max([int(g.get("last_node_id", 0))]
                            + [int(n.get("id") or 0) for n in g["nodes"]]) + 1
    order = max([int(n.get("order", 0)) for n in g["nodes"]] or [0]) + 1
    return {
        "id": g["last_node_id"], "type": "rectnode", "pos": list(pos), "size": [100, 56],
        "flags": {}, "order": order, "mode": 0,
        "inputs": [{"color_off": "rgba(0,0,0,0)", "color_on": "rgba(0,0,0,0)", "label": "",
                    "link": None, "name": "вход", "type": "*"}],
        "outputs": [{"color_off": "rgba(0,0,0,0)", "color_on": "rgba(0,0,0,0)", "label": "",
                     "links": None, "name": "выход", "type": "*"}],
        "title": title, "properties": {}, "color": color or "#5b8fd9", "bgcolor": "rgba(0,0,0,0)",
        "status": status, "description": description, "due": due,
        "tags": tags or [], "image": "", "files": [], "dimMode": "auto",
        "kind": kind, "remindTime": remind_time, "repeatMode": repeat,
        "channels": channels if channels is not None else ["pc", "phone"],
    }


# --- Чтение --------------------------------------------------------------------------
@mcp.tool()
def list_tasks(query: str = "", status: str = "", kind: str = "") -> str:
    """Список карточек графа. query — часть названия, status — статус (в работе/готово/…),
    kind — 'task' (задача) или 'notify' (напоминание)."""
    g = _load()
    nodes = g["nodes"]
    if query:
        nodes = [n for n in nodes if query.lower() in str(n.get("title", "")).lower()]
    if status:
        nodes = [n for n in nodes if n.get("status") == _norm_status(status)]
    if kind:
        k = "notify" if kind.strip().lower() in ("notify", "напоминание") else "task"
        nodes = [n for n in nodes if (n.get("kind") or "task") == k]
    if not nodes:
        return "Ничего не нашлось."
    nodes = sorted(nodes, key=lambda n: str(n.get("title", "")).lower())
    return f"Карточек: {len(nodes)}\n" + "\n".join(_line(n) for n in nodes)


@mcp.tool()
def get_task(task: str) -> str:
    """Показать карточку целиком: task — номер (#120) или часть названия."""
    g = _load()
    n = _resolve(g, task)
    return json.dumps(n, ensure_ascii=False, indent=2)


@mcp.tool()
def summary() -> str:
    """Сводка по графу: сколько карточек, что в работе, что просрочено, напоминания."""
    g = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    by_status = {}
    for n in g["nodes"]:
        by_status[n.get("status") or "без статуса"] = by_status.get(n.get("status") or "без статуса", 0) + 1
    overdue = [n for n in g["nodes"] if n.get("due") and n["due"] < today and n.get("status") != "done"]
    todayn = [n for n in g["nodes"] if n.get("due") == today]
    rem = [n for n in g["nodes"] if n.get("kind") == "notify"]
    out = [f"Всего карточек: {len(g['nodes'])} (связей: {len(g['links'])})",
           "По статусам: " + ", ".join(f"{k} — {v}" for k, v in sorted(by_status.items())),
           f"Напоминаний: {len(rem)}", f"Со сроком сегодня ({today}): {len(todayn)}"]
    if overdue:
        out.append("ПРОСРОЧЕНО:\n" + "\n".join("  " + _line(n) for n in overdue))
    app = "запущено" if _app_running() else "не запущено"
    out.append(f"Приложение: {app}")
    return "\n".join(out)


@mcp.tool()
def list_links() -> str:
    """Список связей между карточками (кто с кем связан)."""
    g = _load()
    by_id = {n["id"]: n.get("title", "?") for n in g["nodes"]}
    if not g["links"]:
        return "Связей нет."
    rows = []
    for l in g["links"]:
        lid, src, _, dst, _, _ = (list(l) + [None] * 6)[:6]
        rows.append(f"#{lid}: {by_id.get(src, src)} → {by_id.get(dst, dst)}")
    return f"Связей: {len(rows)}\n" + "\n".join(rows)


@mcp.tool()
def list_reminders() -> str:
    """Все напоминания (карточки вида notify): когда и куда присылать."""
    g = _load()
    rem = [n for n in g["nodes"] if n.get("kind") == "notify"]
    if not rem:
        return "Напоминаний нет."
    return f"Напоминаний: {len(rem)}\n" + "\n".join(_line(n) for n in rem)


@mcp.tool()
def due_reminders() -> str:
    """Что должно сработать сегодня или уже просрочено."""
    g = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    hits = []
    for n in g["nodes"]:
        if n.get("kind") != "notify" or not n.get("due"):
            continue
        if n["due"] < today or (n["due"] == today and (n.get("remindTime") or "00:00") <= now):
            hits.append(n)
    if not hits:
        return "На сегодня ничего не ждёт."
    return f"К срабатыванию: {len(hits)}\n" + "\n".join(_line(n) for n in hits)


@mcp.tool()
def app_status() -> str:
    """Запущено ли приложение PlannerTaTe и отвечает ли его сервер."""
    g = _load()
    alive = _app_running()
    return (f"Сервер {API}: {'отвечает' if alive else 'не отвечает'}. "
            f"Карточек в графе: {len(g['nodes'])}, связей: {len(g['links'])}. Файл: {GRAPH_FILE}")


# --- Изменение -----------------------------------------------------------------------
@mcp.tool()
def add_task(title: str, description: str = "", status: str = "", color: str = "",
             due: str = "", tags: str = "", near: str = "") -> str:
    """Добавить карточку. title — название, due — срок ГГГГ-ММ-ДД, tags — через запятую,
    near — рядом с какой карточкой положить (номер или название), color — цвет словом."""
    g = _load()
    node = _new_node(g, title, _free_spot(g, near),
                     status=_norm_status(status), color=_norm_color(color),
                     description=description, due=due,
                     tags=[t.strip() for t in re.split(r"[,;]", tags) if t.strip()])
    g["nodes"].append(node)
    note = _save(g, "mcp_add")
    return f"Добавил карточку #{node['id']} «{title}». {note}"


@mcp.tool()
def edit_task(task: str, title: str = "", description: str = "", status: str = "",
              color: str = "", due: str = "", tags: str = "") -> str:
    """Изменить карточку: заполняй только то, что нужно поменять.
    Пустая строка = «не трогать»; чтобы очистить поле, передай '-'. """
    g = _load()
    n = _resolve(g, task)
    changed = []
    for field, value, norm in (("title", title, None), ("description", description, None),
                               ("status", status, _norm_status), ("color", color, _norm_color),
                               ("due", due, None)):
        if value == "":
            continue
        v = "" if value == "-" else (norm(value) if norm else value)
        n[field] = v
        changed.append(field)
    if tags != "":
        n["tags"] = [] if tags == "-" else [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
        changed.append("tags")
    if not changed:
        return "Ничего не менял — не передано ни одного поля."
    note = _save(g, "mcp_edit")
    return f"Карточка #{n['id']} «{n['title']}»: обновил {', '.join(changed)}. {note}"


@mcp.tool()
def add_reminder(task: str, when: str = "", time: str = "09:00", repeat: str = "однократно",
                 channels: str = "пк, телефон") -> str:
    """Сделать карточку напоминанием: when — дата ГГГГ-ММ-ДД, time — время ЧЧ:ММ,
    repeat — однократно/ежедневно/еженедельно/по будням/ежемесячно, channels — пк, телефон."""
    g = _load()
    n = _resolve(g, task)
    n["kind"] = "notify"
    if when:
        n["due"] = when
    n["remindTime"] = time
    n["repeatMode"] = _norm_repeat(repeat)
    n["channels"] = _norm_channels(channels)
    note = _save(g, "mcp_reminder")
    return f"Карточка #{n['id']} «{n['title']}» теперь напоминание: {n.get('due') or 'без даты'} в {time}, повтор {n['repeatMode']}, каналы {', '.join(n['channels'])}. {note}"


@mcp.tool()
def link_tasks(from_task: str, to_task: str) -> str:
    """Связать две карточки (от from_task к to_task). Между двумя карточками — только одна связь."""
    g = _load()
    a = _resolve(g, from_task)
    b = _resolve(g, to_task)
    if a["id"] == b["id"]:
        return "Это одна и та же карточка."
    for l in g["links"]:
        if (l[1] == a["id"] and l[3] == b["id"]) or (l[1] == b["id"] and l[3] == a["id"]):
            return f"Связь уже есть: {a['title']} ↔ {b['title']}."
    g["last_link_id"] = int(g.get("last_link_id", 0)) + 1
    lid = g["last_link_id"]
    g["links"].append([lid, a["id"], 0, b["id"], 0, "*"])
    # Зеркала портов. LiteGraph рисует стрелку по input.link у ПРИЁМНИКА
    # (drawConnections обходит node.inputs[].link) — раньше писали наоборот, и стрелка не появлялась.
    out = a["outputs"][0]
    if out.get("links") is None:
        out["links"] = []
    if lid not in out["links"]:
        out["links"].append(lid)
    b["inputs"][0]["link"] = lid                      # приёмник: вход занят этой связью
    if a["inputs"][0].get("link") == lid:             # источник: своё входное зеркало не трогаем
        a["inputs"][0]["link"] = None
    blinks = b["outputs"][0].get("links")
    if blinks and lid in blinks:                      # у приёмника выход свободен
        blinks.remove(lid)
    note = _save(g, "mcp_link")
    return f"Связал: {a['title']} → {b['title']} (#{lid}). {note}"


@mcp.tool()
def unlink_tasks(from_task: str, to_task: str) -> str:
    """Убрать связь между двумя карточками."""
    g = _load()
    a = _resolve(g, from_task)
    b = _resolve(g, to_task)
    ids = {(a["id"], b["id"]), (b["id"], a["id"])}
    gone = [l for l in g["links"] if (l[1], l[3]) in ids]
    if not gone:
        return f"Связи между «{a['title']}» и «{b['title']}» нет."
    g["links"] = [l for l in g["links"] if (l[1], l[3]) not in ids]
    dead = {l[0] for l in gone}
    for n in (a, b):
        out = n["outputs"][0]
        if out.get("links"):
            out["links"] = [x for x in out["links"] if x not in dead]
        if n["inputs"][0].get("link") in dead:
            n["inputs"][0]["link"] = None
    note = _save(g, "mcp_unlink")
    return f"Убрал связь {a['title']} ↔ {b['title']}. {note}"


@mcp.tool()
def delete_task(task: str) -> str:
    """Удалить карточку вместе со всеми её связями."""
    g = _load()
    n = _resolve(g, task)
    nid = n["id"]
    gone = [l[0] for l in g["links"] if l[1] == nid or l[3] == nid]
    g["links"] = [l for l in g["links"] if l[1] != nid and l[3] != nid]
    g["nodes"] = [x for x in g["nodes"] if x["id"] != nid]
    for other in g["nodes"]:
        out = (other.get("outputs") or [{}])[0]
        if out.get("links"):
            out["links"] = [x for x in out["links"] if x not in gone]
        if (other.get("inputs") or [{}])[0].get("link") in gone:
            other["inputs"][0]["link"] = None
    note = _save(g, "mcp_delete")
    return f"Удалил карточку #{nid} «{n['title']}» и её связи ({len(gone)}). {note}"


@mcp.tool()
def backup_graph() -> str:
    """Сделать резервную копию графа прямо сейчас."""
    bak = _backup("mcp_manual")
    return f"Бэкап: {bak}"


# --- Управление приложением ----------------------------------------------------------
@mcp.tool()
def start_app() -> str:
    """Запустить сервер PlannerTaTe (если он не отвечает)."""
    if _app_running():
        return f"Уже запущено: {API}"
    subprocess.Popen([PYTHON312, "backend.py"], cwd=str(APP_DIR),
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(20):
        time.sleep(0.5)
        if _app_running():
            return f"Запустил: {API} (открывай http://127.0.0.1:5001)"
    return "Запустил процесс, но сервер пока не отвечает — загляни в логи."


@mcp.tool()
def stop_app() -> str:
    """Остановить сервер PlannerTaTe."""
    if not _app_running():
        return "Сервер и так не отвечает."
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
        pids = set()
        for line in out.splitlines():
            if ":5001" in line and "LISTENING" in line.upper():
                pids.add(line.split()[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)
    except Exception as e:
        return f"Не смог остановить: {e}"
    time.sleep(1)
    return "Сервер остановлен." if not _app_running() else "Похоже, сервер ещё жив — проверь app_status."


@mcp.tool()
def snapshot() -> str:
    """Сделать снимок графа картинкой (PNG) и вернуть путь к файлу."""
    if not _app_running():
        return "Приложение не запущено — снимок сделать не получится. Вызови start_app."
    if not SNAPSHOT_SCRIPT.exists():
        return f"Нет скрипта снимка: {SNAPSHOT_SCRIPT}"
    out = APP_DIR / "mcp" / "snapshots" / f"graph_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["node", str(SNAPSHOT_SCRIPT), str(out)], cwd=str(FRONTEND_DIR),
                           capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "Снимок не получился: браузер не ответил за 3 минуты."
    if r.returncode != 0 or not out.exists():
        return f"Снимок не получился: {(r.stderr or r.stdout or '')[-400:]}"
    return f"Снимок графа: {out}"


# --- Чат «Гермес» в мобильном приложении (06.10.26, просьба Ярослава) ------------------------
# Сообщения из приложения лежат в hermes_chat.jsonl рядом с graph.json. Агент отвечает
# инструментом hermes_chat_reply — «кнопка Гермес» на телефоне получает ответ через MCP.
def _chat_file() -> Path:
    return GRAPH_FILE.parent / "hermes_chat.jsonl"


def _chat_read(limit: int = 30) -> list:
    items = []
    try:
        with open(_chat_file(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and (rec.get("text") or rec.get("file_name")):
                    items.append(rec)
    except FileNotFoundError:
        pass
    return items[-max(1, min(int(limit or 30), 200)):]


@mcp.tool()
def hermes_chat_read(limit: int = 30) -> str:
    """Прочитать последние сообщения чата с Ярославом из мобильного приложения PlannerTaTe
    (кнопка «Гермес» в приложении телефона). Сначала посмотри контекст — потом отвечай.
    """
    items = _chat_read(limit)
    if not items:
        return "Чат пока пуст."
    out = []
    for r in items:
        who = "Ярослав" if r.get("from") == "user" else "Гермес"
        line = "[%s] id=%s %s: %s" % (r.get("ts", ""), r.get("id"), who, r.get("text"))
        if r.get("file_name"):
            line += "\n[вложение: %s | %s]" % (r.get("file_name"), r.get("file_path") or "")
        out.append(line)
    return "\n".join(out)


@mcp.tool()
def hermes_chat_reply(text: str, reply_to: int = 0) -> str:
    """ОБЯЗАТЕЛЬНОЕ действие: отправить ответ Ярославу в чат мобильного приложения PlannerTaTe
    (кнопка «Гермес»). Без этого вызова он ответ не увидит!
    text — текст ответа (по-русски, коротко и по делу); reply_to можно не указывать.
    """
    text = (text or "").strip()
    if not text:
        return "Ошибка: пустой текст ответа."
    if not reply_to:
        users = [r for r in _chat_read(200) if r.get("from") == "user"]
        if users:
            reply_to = int(users[-1].get("id") or 0)
    try:
        body = json.dumps({"id": reply_to, "text": text}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(API + "/api/hermes/reply", data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("X-Plannertate-Client", "1")
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(r.read().decode("utf-8"))
        return "Ответ отправлен в чат приложения (id %s)." % res.get("id")
    except Exception as e:
        # сервер выключен — ответ не теряем: дописываем строку в чат-файл сами
        try:
            items = _chat_read(200)
            nid = max([int(i.get("id") or 0) for i in items] + [0]) + 1
            rec = {"id": nid, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "from": "hermes", "text": text, "reply_to": (reply_to or None)}
            with open(_chat_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return "Ответ записан в чат-файл напрямую (id %d; сервер не ответил: %s)." % (nid, e)
        except Exception as e2:
            return "Не получилось отправить ответ: %s" % e2


@mcp.tool()
def hermes_chat_file(path: str, limit: int = 200000) -> str:
    """Прочитать файл, который Ярослав приложил в чат мобильного приложения (файл лежит на этом
    компьютере). path — путь из строки «вложение: … | путь» в сообщении чата. Текстовый файл
    возвращается содержимым (до limit символов); для картинок и других двоичных — только сведения.
    """
    p = Path(str(path or "").strip())
    if not p.is_file():
        return "Файл не найден: %s" % p
    try:
        data = p.read_bytes()
    except Exception as e:
        return "Не получилось прочитать файл: %s" % e
    binary = b"\x00" in data[:4096]
    text = ""
    if not binary:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            binary = True
    if binary or not text.strip():
        return ("Двоичный файл: %s (%d байт). Показать содержимое я не могу — "
                "открой его на компьютере." % (p.name, len(data)))
    if len(text) > limit:
        text = text[:limit] + "\n…[обрезано, всего %d символов]" % len(text)
    return "Файл %s (%d байт):\n%s" % (p.name, len(data), text)


if __name__ == "__main__":
    _log("PlannerTaTe MCP: граф", GRAPH_FILE, "| API", API)
    mcp.run(transport="stdio")
