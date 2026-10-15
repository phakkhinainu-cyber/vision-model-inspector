; Inno Setup 6 script — Vision Model Inspector (CPU package, Windows x64)
; Build: iscc /DAppVersion=0.1.0 packaging\installer.iss   (after PyInstaller onedir build)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Vision Model Inspector"
#define AppExe "VisionModelInspector.exe"

[Setup]
AppId={{6C6F7B0E-3C2A-4E0B-9A54-4D1F5E8B7A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} (CPU)
AppPublisher=Vision Model Inspector
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; per-user install by default (no admin needed); user may choose all users
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\Output
OutputBaseFilename=VisionModelInspector-{#AppVersion}-cpu-setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=installer_info_th.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\VisionModelInspector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\คู่มือการใช้งาน_Vision_Model_Inspector.pdf"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\คู่มือการใช้งาน (PDF)"; Filename: "{app}\docs\คู่มือการใช้งาน_Vision_Model_Inspector.pdf"; Check: ManualExists
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function ManualExists(): Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\docs\คู่มือการใช้งาน_Vision_Model_Inspector.pdf'));
end;
