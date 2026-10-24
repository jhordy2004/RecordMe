; Script de Inno Setup 6 para RecordMe
; Genera el instalador profesional ejecutable para RecordMe con versión dinámica

#ifndef MyAppName
  #define MyAppName "RecordMe"
#endif

#ifndef MyAppVersion
  #define MyAppVersion "0.1.1"
#endif

#ifndef MyAppPublisher
  #define MyAppPublisher "RecordMe Team"
#endif

#ifndef MyAppExeName
  #define MyAppExeName "RecordMe.exe"
#endif

#ifndef MyAppIcon
  #define MyAppIcon "src\recordme\resources\ico\icono_256.ico"
#endif

#ifndef OutputBaseFilename
  #define OutputBaseFilename "RecordMe_Setup_v" + MyAppVersion
#endif

[Setup]
AppId={{5D9A9C8E-2B6F-4C2E-8E28-6623FA2D58A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Release
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#MyAppIcon}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=force
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\RecordMe_dir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyAppIcon}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
