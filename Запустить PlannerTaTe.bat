@echo off
setlocal
title PlannerTaTe - планировщик задач
cd /d "%~dp0"

REM  PlannerTaTe: запуск сервера и открытие страницы. Дважды щёлкните этот файл.
REM  Окно можно свернуть, но не закрывайте: в нём видно адрес для телефона.
REM  Закрыть PlannerTaTe = закрыть это окно.

set "PYEXE="
call :pick "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :pick "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
call :pick "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :pick "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PYEXE call :pickfrom python

echo PlannerTaTe запускается... Это окно можно свернуть, но не закрывайте его.
echo.
start "" /min powershell -NoProfile -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:5001'"

if not defined PYEXE goto nopython

"%PYEXE%" backend.py

echo.
echo Сервер остановлен. Нажмите любую клавишу, чтобы закрыть окно.
pause
exit /b 0

:nopython
echo.
echo Не нашёл Python с библиотекой Flask.
echo Установите Python с python.org и выполните: pip install flask
echo.
pause
exit /b 1

REM --- :pick <путь>  берём первый Python, в котором есть Flask (иначе сервер не запустится) ---
:pick
if defined PYEXE exit /b
if not exist %1 exit /b
%1 -c "import flask" >nul 2>&1
if not errorlevel 1 set "PYEXE=%~1"
exit /b

:pickfrom
if defined PYEXE exit /b
where %1 >nul 2>&1
if errorlevel 1 exit /b
%1 -c "import flask" >nul 2>&1
if not errorlevel 1 set "PYEXE=%1"
exit /b
