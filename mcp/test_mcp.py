"""Живой тест MCP-сервера PlannerTaTe по настоящему протоколу MCP (stdio).

Пишем НЕ в твой граф: для теста серверу подсовывается копия graph.json,
а хэш настоящего файла сверяется до и после — доказательство, что он не тронут.
Запуск: <hermes-venv>/python.exe test_mcp.py
"""
import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
SERVER = HERE / "plannertate_mcp.py"
PY = r"C:\Users\Yar\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
APP_DIR = HERE.parent
REAL = APP_DIR / "graph.json"
COPY = Path(os.environ.get("TMPDIR", r"C:\Users\Yar\AppData\Local\hermes\cache\scratch")) / "plannertate_graph_test.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


async def main() -> int:
    shutil.copy2(REAL, COPY)
    real_before, copy_before = sha(REAL), sha(COPY)
    print(f"настоящий граф: {REAL.name} sha={real_before}")
    print(f"копия для теста: {COPY} sha={copy_before}\n")

    env = dict(os.environ)
    env["PLANNERTATE_GRAPH"] = str(COPY)
    params = StdioServerParameters(command=PY, args=[str(SERVER)], env=env)

    ok = True
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            tools = (await s.list_tools()).tools
            print(f"ИНСТРУМЕНТОВ ОБНАРУЖЕНО: {len(tools)}")
            for t in tools:
                desc = (t.description or "").split("\n")[0][:95]
                print(f"  {t.name:<18} {desc}")
            print()
            one = next(t for t in tools if t.name == "edit_task")
            print("СХЕМА edit_task (что увидит модель):")
            print("  параметры:", json.dumps(one.input_schema.get("properties", {}), ensure_ascii=False)[:500])
            print("  обязательные:", one.input_schema.get("required"))
            print()

            async def call(name, **kw):
                nonlocal ok
                try:
                    r = await s.call_tool(name, kw)
                    text = r.content[0].text if r.content else ""
                    print(f"[{name}] {kw}\n  -> {text[:400]}\n")
                    return text
                except Exception as e:
                    print(f"[{name}] {kw}\n  !! ОШИБКА: {e}\n")
                    ok = False
                    return ""

            print("=== ЧТЕНИЕ ===")
            await call("summary")
            await call("list_tasks", status="в работе")
            await call("list_reminders")
            await call("list_links")
            await call("app_status")
            await call("get_task", task="Вода и краска")

            print("=== ФРИЗМЕННЫЕ ОШИБКИ (должны быть понятными) ===")
            await call("edit_task", task="Вода и краска", status="непонятный статус")
            await call("get_task", task="такой карточки точно нет")
            await call("add_task", title="Тест MCP", color="салатовый")

            print("=== ЗАПИСЬ (в копию) ===")
            before = len(json.loads(COPY.read_text(encoding="utf-8"))["nodes"])
            await call("add_task", title="Тест MCP", description="проверка сервера", due="2026-10-10",
                       tags="тест, mcp", color="зелёный", near="Вода и краска")
            await call("edit_task", task="Тест MCP", status="в работе", title="Тест MCP (изменён)")
            await call("add_reminder", task="Тест MCP (изменён)", when="2026-10-11", time="08:30",
                       repeat="ежедневно", channels="пк, телеграм")
            await call("link_tasks", from_task="Тест MCP (изменён)", to_task="Вода и краска")
            await call("link_tasks", from_task="Тест MCP (изменён)", to_task="Вода и краска")  # дубль — должен отказать
            await call("unlink_tasks", from_task="Тест MCP (изменён)", to_task="Вода и краска")
            await call("delete_task", task="Тест MCP (изменён)")

            after = len(json.loads(COPY.read_text(encoding="utf-8"))["nodes"])
            print(f"карточек в копии: было {before}, стало {after} (ожидаем то же число: создали и удалили)")

            print("=== СНИМОК ГРАФА ===")
            await call("snapshot")

    real_after, copy_after = sha(REAL), sha(COPY)
    print("=== ЦЕЛОСТНОСТЬ ===")
    print(f"настоящий граф sha: {real_before} -> {real_after} | НЕ ТРОНУТ: {real_before == real_after}")
    print(f"копия sha:          {copy_before} -> {copy_after} | менялась: {copy_before != copy_after}")
    baks = sorted(REAL.parent.glob(f"{REAL.name}.bak_*"))
    print(f"бэкапов графа в папке: {len(baks)} (последний: {baks[-1].name if baks else '—'})")
    print("ИТОГ ТЕСТА:", "OK" if ok and real_before == real_after else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
