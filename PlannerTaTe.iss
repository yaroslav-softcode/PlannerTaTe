; PlannerTaTe — установщик для Windows (Inno Setup 6).
; Сборка:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" PlannerTaTe.iss
; Ставится без прав администратора: в папку пользователя, ярлыки на рабочий стол и в «Пуск»,
; и (по желанию) автозапуск при входе в Windows — ярлык в «Автозагрузке» с ключом --quiet.
; Данные (граф, ключ) живут в %APPDATA%\PlannerTaTe и при удалении НЕ трогаются.

#define AppName "PlannerTaTe"
#define AppVersion "1.1"
#define AppExe "PlannerTaTe.exe"
#define AppPublisher "Ярослав Хмелев"

[Setup]
AppId={{1C8B2977-D4F0-40B8-9B4D-8A282BF6D93C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=PlannerTaTe_Setup_{#AppVersion}
SetupIconFile=PlannerTaTe.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AppMutex=PlannerTaTe_Single_Instance
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=1.1.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Установка {#AppName} — планировщика задач
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
MinVersion=10.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.autostart=Запускать при входе в Windows: %
english.autostart=Start with Windows: %
russian.tasksgroup=Дополнительно
english.tasksgroup=Additional
russian.autostarthint=Программа поднимется молча, без вкладки браузера — напоминания будут работать сразу после включения компьютера
english.autostarthint=The app will start silently, without opening a browser tab, so reminders work right after the computer is turned on

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:tasksgroup}"
Name: "autostart"; Description: "{cm:autostart}"; GroupDescription: "{cm:tasksgroup}"; Flags: checkedonce

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "app\PlannerTaTe.apk"; DestDir: "{app}\app"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--quiet"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Удаление: если программа запущена, деинсталлятор сам скажет «закройте все экземпляры приложения»
; и продолжит после этого (отметка AppMutex выше). Автоматически убивать процесс не надо: иначе
; деинсталлятор гасил бы и переносную копию, запущенную из другой папки.
