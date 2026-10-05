# -*- mode: python ; coding: utf-8 -*-
"""Сборка PlannerTaTe.exe — один файл: сервер, сайт, значок, приложение для телефона (и планшета).

Собирать Python312 (в нём Flask и PyInstaller):
    "C:/Users/Yar/AppData/Local/Programs/Python/Python312/python.exe" -m PyInstaller PlannerTaTe.spec --noconfirm --clean

--clean обязателен: без него PyInstaller может отдать прежний exe из кэша, и внутрь не попадут
свежие правки.
"""

block_cipher = None

a = Analysis(
    ['plannertate.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend/dist'),      # собранный сайт (сам планировщик)
        ('app/PlannerTaTe.apk', 'app'),           # приложение для телефона (раздаётся по /apk)
        ('pick_file.py', '.'),                   # диалог выбора файла для карточек
        ('PlannerTaTe.ico', '.'),                 # значок для трея и окна
    ],
    hiddenimports=[
        'tkinter', 'tkinter.filedialog', 'tkinter.commondialog',   # pick_file.py подключается вручную
        'PyQt5.sip', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'PIL', 'matplotlib', 'scipy', 'pandas', 'pytest', 'setuptools', 'pip',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.Qt3DCore',
        'PyQt5.QtMultimedia', 'PyQt5.QtSql', 'PyQt5.QtDesigner', 'PyQt5.QtNetworkAuth',
        'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtSerialPort',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PlannerTaTe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                                  # окна консоли нет: всё в planermate.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['PlannerTaTe.ico'],
    version='PlannerTaTe_version.txt',
)
