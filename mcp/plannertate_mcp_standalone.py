"""Автономный MCP-сервер PlannerTaTe для Codex — без Hermes и без Python на машине.

Зачем: основной `plannertate_mcp.py` требует пакет `mcp` (MCP SDK), поэтому его
запускает питон из venv Hermes. Здесь тот же набор инструментов, но SDK не нужен:
подсовываем модуль-заглушку, инструменты регистрируются как обычные функции, а
протокол MCP (JSON-RPC 2.0 построчно через stdin/stdout) обслуживается руками.
Собирается PyInstaller'ом в `plannertate_mcp.exe` — на машине пользователя не нужны
ни Hermes, ни Python.

Транспорт: stdio, одно сообщение = одна строка JSON (без Content-Length).
Методы: initialize, notifications/initialized, ping, tools/list, tools/call,
resources/list, prompts/list. Всё остальное — -32601.

Логи — ТОЛЬКО в stderr: stdout занят протоколом.
"""
import inspect
import json
import os
import sys
import types

# --- Путь приложения: exe лежит в <PlannerTaTe>/mcp/, папка данных — на уровень выше ---
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("PLANNERTATE_DIR", os.path.dirname(HERE))
sys.path.insert(0, HERE)


# --- Заглушка MCP SDK: декоратор @mcp.tool() просто запоминает функции ----------------
class _StubServer:
    def __init__(self, name):
        self.name = name
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco

    def run(self, *args, **kwargs):
        pass


_mcp_module = types.ModuleType("mcp")
_server_module = types.ModuleType("mcp.server")
_server_module.MCPServer = _StubServer
_mcp_module.server = _server_module
sys.modules.setdefault("mcp", _mcp_module)
sys.modules.setdefault("mcp.server", _server_module)

import plannertate_mcp as P  # noqa: E402  (импорт ПОСЛЕ заглушки — иначе упадёт)

TOOLS = dict(P.mcp.tools) if isinstance(getattr(P, "mcp", None), _StubServer) else {}

_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema(fn):
    """JSON-схема аргументов из сигнатуры функции (аннотации + значения по умолчанию)."""
    props, required = {}, []
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        params = []
    for p in params:
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        typ = _TYPE_MAP.get(p.annotation, "string")
        prop = {"type": typ}
        if p.default is not inspect.Parameter.empty and p.default is not None:
            prop["default"] = p.default
        props[p.name] = prop
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _tool_list():
    out = []
    for name in sorted(TOOLS):
        fn = TOOLS[name]
        out.append({"name": name,
                    "description": (inspect.getdoc(fn) or name).strip(),
                    "inputSchema": _schema(fn)})
    return out


def _call_tool(name, arguments):
    fn = TOOLS.get(name)
    if fn is None:
        return None, "Неизвестный инструмент: %s" % name
    args = arguments if isinstance(arguments, dict) else {}
    try:
        allowed = {p.name for p in inspect.signature(fn).parameters.values()
                   if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
        result = fn(**{k: v for k, v in args.items() if k in allowed})
        return ("" if result is None else str(result)), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def _send(obj):
    # Пишем БАЙТАМИ в UTF-8: sys.stdout в Windows по умолчанию cp1251/cp866, и кириллица
    # в описаниях инструментов ломала MCP-клиент (UnicodeDecodeError, проверено 23.11.26).
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _result(msg_id, result):
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id, code, message):
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def _handle(msg):
    method = msg.get("method") or ""
    msg_id = msg.get("id")
    is_notification = msg_id is None
    params = msg.get("params") or {}

    if method == "initialize":
        version = params.get("protocolVersion") or "2025-03-26"
        _result(msg_id, {"protocolVersion": version,
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "plannertate", "version": "1.12"}})
        return
    if method in ("notifications/initialized", "notifications/cancelled"):
        return                                     # уведомления без ответа
    if method == "ping":
        _result(msg_id, {})
        return
    if method == "tools/list":
        _result(msg_id, {"tools": _tool_list()})
        return
    if method == "tools/call":
        text, err = _call_tool(str(params.get("name") or ""), params.get("arguments"))
        if err:
            _result(msg_id, {"content": [{"type": "text", "text": err}], "isError": True})
        else:
            _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        return
    if method in ("resources/list", "resources/templates/list"):
        _result(msg_id, {"resources": []} if method == "resources/list" else {"resourceTemplates": []})
        return
    if method == "prompts/list":
        _result(msg_id, {"prompts": []})
        return
    if is_notification:
        return
    _error(msg_id, -32601, "Метод не поддержан: %s" % method)


def main():
    print("[plannertate-mcp] старт, инструментов: %d" % len(TOOLS), file=sys.stderr)
    sys.stderr.flush()
    # ВАЖНО: именно readline(), а не `for line in sys.stdin` — итерация по потоку
    # читает крупными блоками и на pipe висит, не дождавшись EOF (проверено 23.11.26:
    # клиент MCP ждал ответ на initialize, а сервер — ещё данных).
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            break
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except Exception as e:
            print("[plannertate-mcp] плохой JSON: %s" % e, file=sys.stderr)
            continue
        if isinstance(msg, list):                   # батч — редкий случай, обслуживаем по одному
            for one in msg:
                _handle(one)
        elif isinstance(msg, dict):
            _handle(msg)


if __name__ == "__main__":
    main()
