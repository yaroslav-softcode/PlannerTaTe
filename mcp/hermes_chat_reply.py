# -*- coding: utf-8 -*-
"""Записать ответ Гермеса в чат мобильного приложения PlannerTaTe («кнопка Гермес»).

Вызывается агентом Hermes (вебхук-мост):
    python hermes_chat_reply.py --id 12 --text "текст ответа"
или текст из stdin:   python hermes_chat_reply.py --id 12 --text -

Основной путь — локальный сервер приложения (POST /api/hermes/reply): так чат остаётся
с одним писателем, и id не конфликтуют. Если сервер выключен — пишем строку прямо в
hermes_chat.jsonl рядом с graph.json: сообщение не теряется.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request


def chat_file():
    base = (os.environ.get("PLANNERTATE_DATA")
            or os.path.join(os.environ.get("APPDATA", ""), "PlannerTaTe"))
    return os.path.join(base, "hermes_chat.jsonl")


def via_server(text, mid):
    port = os.environ.get("PLANNERTATE_PORT", "5001")
    body = json.dumps({"id": mid, "text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%s/api/hermes/reply" % port,
                                 data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("X-Plannertate-Client", "1")
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read().decode("utf-8")


def via_file(text, mid):
    path = chat_file()
    items = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        items.append(rec)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    nid = max([int(i.get("id") or 0) for i in items] + [0]) + 1
    rec = {"id": nid, "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "from": "hermes", "text": text, "reply_to": (mid or None)}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return json.dumps({"status": "ok", "id": nid, "via": "file"}, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="")
    ap.add_argument("--text", required=True)
    a = ap.parse_args()
    text = sys.stdin.read() if a.text == "-" else a.text
    text = (text or "").strip()
    if not text:
        print(json.dumps({"status": "error", "error": "пустой текст"}, ensure_ascii=False))
        sys.exit(2)
    try:
        print(via_server(text, a.id))
    except Exception as e:
        print(json.dumps({"status": "warn", "server": str(e), "fallback": "file"},
                         ensure_ascii=False))
        print(via_file(text, a.id))


if __name__ == "__main__":
    main()
