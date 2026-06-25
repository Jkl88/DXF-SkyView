; Inno Setup — установщик DXF SkyView (onedir, быстрый запуск).
; Версия передаётся при сборке: iscc /DMyAppVersion=0.2.7 DXF-SkyView.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "DXF SkyView"
#define MyAppPublisher "SkyView"
#define MyAppExeName "DXF-SkyView.exe"
#define MyAppId "{{8F3C2A1B-4D5E-6F70-8A9B-0C1D2E3F4A5B}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=DXF-SkyView
SetupIconFile=..\DXF.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "associate"; Description: "Открывать файлы .dxf через DXF SkyView"; GroupDescription: "Ассоциации файлов:"; Flags: checkedonce

[Files]
Source: "..\dist\DXF-SkyView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Тип файла .dxf
Root: HKCU; Subkey: "Software\Classes\DXF-SkyView.dxf"; ValueType: string; ValueName: ""; ValueData: "DXF Drawing (SkyView)"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\DXF-SkyView.dxf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\DXFfile.ico,0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\DXF-SkyView.dxf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
; «Открыть с помощью»
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\DXFfile.ico,0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
; Расширение
Root: HKCU; Subkey: "Software\Classes\.dxf"; ValueType: string; ValueName: ""; ValueData: "DXF-SkyView.dxf"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.dxf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\DXFfile.ico,0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.dxf\OpenWithProgids"; ValueType: string; ValueName: "DXF-SkyView.dxf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.dxf\OpenWithProgids"; ValueType: string; ValueName: "Applications\{#MyAppExeName}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
; Путь установки (для приложения)
Root: HKCU; Subkey: "Software\SkyView\DXF SkyView"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall runasoriginaluser
