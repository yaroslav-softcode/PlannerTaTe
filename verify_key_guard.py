"""Проверка защиты ключом: свой компьютер свободен, сеть требует ключ, чужие точки закрыты."""
import json, pathlib, urllib.request, urllib.error

APP = pathlib.Path(r"C:\Users\Yar\PycharmProjects\PlannerTaTe")
LAN = "http://192.168.0.101:5001"
LOCAL = "http://127.0.0.1:5001"

# прогреваем: первый сетевой запрос заставляет сервер создать ключ
import urllib.request as _u
try:
    _u.urlopen(f"{LAN}/api/load", timeout=8)
except Exception:
    pass
_KEYFILE = APP / "access_key.txt"
KEY = _KEYFILE.read_text(encoding="utf-8").strip() if _KEYFILE.exists() else ""
mask = (KEY[:2] + "…" + KEY[-2:]) if len(KEY) > 4 else "(нет)"
print(f"файл ключа: {_KEYFILE.name}, есть: {_KEYFILE.exists()}, ключ: {mask}, длина {len(KEY)}\n")

def get(url, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, len(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, 0, dict(e.headers)
    except Exception as e:
        return 0, 0, {"err": str(e)[:60]}

checks = [
    ("свой компьютер, без ключа      ", get(f"{LOCAL}/api/load"), 200),
    ("сеть, без ключа  (было открыто)", get(f"{LAN}/api/load"), 401),
    ("сеть, страница без ключа       ", get(f"{LAN}/"), 401),
    ("сеть, ключ в ссылке            ", get(f"{LAN}/api/load?key={KEY}"), 200),
    ("сеть, ключ в заголовке         ", get(f"{LAN}/api/load", {"X-Plannertate-Key": KEY}), 200),
    ("сеть, страница с ключом        ", get(f"{LAN}/?key={KEY}"), 200),
    ("сеть, чужой ключ               ", get(f"{LAN}/api/load?key=ZZZZZZZZZZ"), 401),
    ("сеть, раздача APK без ключа    ", get(f"{LAN}/apk"), 200),
    ("сеть, раздача APK с ключом     ", get(f"{LAN}/apk?key={KEY}"), 200),
    ("сеть + ключ, но открытие файла ", get(f"{LAN}/api/open_url", {"X-Plannertate-Key": KEY}, "POST"), 403),
    ("сеть + ключ, экспорт напоминаний", get(f"{LAN}/api/reminders/export", {"X-Plannertate-Key": KEY}), 200),
]
ok = True
for name, (code, size, hdrs), want in checks:
    good = code == want
    ok = ok and good
    extra = ""
    if "Set-Cookie" in hdrs:
        extra = " + кука"
    if size:
        extra += f" ({size} байт)"
    print(f"  {'OK  ' if good else 'ПЛОХО'} {name} http={code} (ждали {want}){extra}")
print("\nИТОГ:", "всё как задумано" if ok else "ЕСТЬ ОТКЛОНЕНИЯ")
