# Сторонние компоненты · Third-party components

Проверено по метаданным установленных пакетов и содержимому сборки: 29.10.2026.

## Что важно знать

- **Исходный код PlannerTaTe** распространяется под **MIT** (см. [LICENSE](LICENSE)).
- **Собранное приложение для Windows** (`PlannerTaTe.exe`, установщик `PlannerTaTe_Setup_*.exe`)
  включает **PyQt5**, распространяемый под **GNU GPL v3**. Поэтому двоичная сборка **целиком
  распространяется под GNU GPL v3**, а не под MIT. Текст лицензии — [LICENSE-GPLv3.txt](LICENSE-GPLv3.txt).
- Исходный код, соответствующий двоичной сборке, доступен в этом репозитории:
  <https://github.com/yaroslav-softcode/PlannerTaTe> — этого требует GPL v3.
- Приложение для Android (`app/PlannerTaTe.apk`) под GPL не попадает: в нём нет PyQt5,
  только Apache-2.0 компоненты (см. таблицу).

## Компоненты в сборке для Windows

| Компонент | Версия | Лицензия | Сайт |
|---|---|---|---|
| PyQt5 | 5.15.11 | **GPL v3** (или коммерческая Riverbank) | <https://riverbankcomputing.com/software/pyqt/> |
| Qt 5 (runtime) | 5.15.2 | LGPL v3 / GPL v3 (используется через PyQt5) | <https://www.qt.io/licensing/> |
| PyQt5-sip | 12.19.0 | BSD-2-Clause | <https://pypi.org/project/PyQt5-sip/> |
| Flask | 3.1.3 | BSD-3-Clause | <https://palletsprojects.com/p/flask/> |
| Werkzeug | 3.1.9 | BSD-3-Clause | <https://palletsprojects.com/p/werkzeug/> |
| Jinja2 | 3.1.6 | BSD-3-Clause | <https://palletsprojects.com/p/jinja/> |
| Click | 8.5.0 | BSD-3-Clause | <https://palletsprojects.com/p/click/> |
| itsdangerous | 2.2.0 | BSD-3-Clause | <https://palletsprojects.com/p/itsdangerous/> |
| MarkupSafe | 3.0.3 | BSD-3-Clause | <https://palletsprojects.com/p/markupsafe/> |
| blinker | 1.9.0 | MIT | <https://pypi.org/project/blinker/> |
| PyAudioWPatch | 0.2.12.9 | Apache-2.0 (обёртка над PortAudio, MIT) | <https://pypi.org/project/PyAudioWPatch/> |
| Tcl/Tk (tkinter) | 8.6 | Tcl/Tk License (BSD-подобная) | <https://www.tcl.tk/software/tcltk/license.html> |
| PyInstaller | 6.22.2 | GPL v2 **с исключением**, разрешающим собирать и распространять несвободные программы | <https://pyinstaller.org/> |

## Интерфейс (frontend/dist)

| Компонент | Версия | Лицензия |
|---|---|---|
| Vue | 3.5 | MIT |
| LiteGraph.js | 0.7.18 | MIT |
| qrcode | 1.5 | MIT |
| Vite, esbuild (только сборка) | 5.4 / 0.25 | MIT |

## Приложение для Android (app/PlannerTaTe.apk)

| Компонент | Лицензия |
|---|---|
| Kotlin stdlib | Apache-2.0 |
| AndroidX (annotation, room, constraintlayout и др.) | Apache-2.0 |

Файлы лицензий AndroidX поставляются внутри APK (`META-INF/androidx/.../LICENSE.txt`).

## Установщик

Inno Setup 6 — лицензия разрешает использование для любых целей, включая коммерческие,
и распространение собранных установщиков (см. `license.txt` в папке Inno Setup).

---

# Third-party components (English)

- **PlannerTaTe source code** is licensed under **MIT** (see [LICENSE](LICENSE)).
- **The Windows build** (`PlannerTaTe.exe`, `PlannerTaTe_Setup_*.exe`) bundles **PyQt5**, which is
  licensed under **GNU GPL v3**. The binary as a whole is therefore distributed under **GPL v3**,
  not MIT. Full text: [LICENSE-GPLv3.txt](LICENSE-GPLv3.txt). The complete corresponding source
  code of the released build is this repository (<https://github.com/yaroslav-softcode/PlannerTaTe>).
- The Android companion app contains no PyQt5 code: only Apache-2.0 components (Kotlin stdlib, AndroidX).

License texts of the individual components are available at the links in the tables above.
PyQt5 is © Riverbank Computing Limited. Qt is © The Qt Company. All other components are © their
respective authors.
