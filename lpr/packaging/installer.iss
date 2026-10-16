; Inno Setup 6 — LPR บ้าน (Windows 10/11 x64)
; Build: iscc /DAppVersion=1.0.0 packaging\installer.iss   (หลัง PyInstaller build และดาวน์โหลด WinSW-x64.exe มาไว้ที่ packaging\)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "LPR บ้าน"
#define AppExe "LPR.exe"

[Setup]
AppId={{3B7A6F1E-5C2D-4F9A-8E21-7D4C9B0A1F63}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LPR บ้าน
DefaultDirName={autopf}\LPR
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\Output
OutputBaseFilename=LPR-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=installer_info_th.txt
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.TaskService=ติดตั้งเป็น Windows service (แนะนำ: ทำงานเบื้องหลังตลอด เปิดเองตอนบูต)
english.TaskFirewall=อนุญาตมือถือ/แท็บเล็ตในวง LAN (เปิดพอร์ต 8765 เฉพาะเครือข่ายส่วนตัว)
english.TaskStartup=เปิดหน้าต่างโปรแกรมเมื่อเข้าสู่ระบบ Windows
english.DataTitle=โฟลเดอร์เก็บข้อมูล
english.DataDesc=ฐานข้อมูล ภาพ log และไฟล์สำรองจะเก็บที่นี่
english.DataPrompt=เลือกโฟลเดอร์เก็บข้อมูล (แนะนำไดรฟ์ที่มีพื้นที่มาก เช่น D:\LPR):

[Tasks]
Name: "service"; Description: "{cm:TaskService}"
Name: "firewall"; Description: "{cm:TaskFirewall}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "{cm:TaskStartup}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\LPR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "WinSW-x64.exe"; DestDir: "{app}"; DestName: "LPR-Service.exe"; Flags: ignoreversion
Source: "LPR-Service.xml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist

[Dirs]
Name: "{commonappdata}\LPR"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\เปิดในเบราว์เซอร์"; Filename: "{app}\{#AppExe}"; Parameters: "--browser"
Name: "{group}\คู่มือผู้ใช้"; Filename: "{app}\docs\user-manual.md"; Check: FileExists(ExpandConstant('{app}\docs\user-manual.md'))
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""LPR-ban LAN"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""LPR-ban LAN"" dir=in action=allow protocol=TCP localport=8765,8766 profile=private"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\LPR-Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopSvc"
Filename: "{app}\LPR-Service.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "DelSvc"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""LPR-ban LAN"""; Flags: runhidden; RunOnceId: "DelFw"

[Code]
var
  DataPage: TInputDirWizardPage;

function GetDriveType(lpRootPathName: string): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function DefaultHome(): string;
var
  Pointer: AnsiString;
begin
  if LoadStringFromFile(ExpandConstant('{commonappdata}\LPR\home.txt'), Pointer) and (Trim(String(Pointer)) <> '') then
    Result := Trim(String(Pointer))
  else if DirExists('D:\') and (GetDriveType('D:\') = 3) then
    Result := 'D:\LPR'
  else
    Result := ExpandConstant('{commonappdata}\LPR');
end;

function GetCommandLineHome(): string;
begin
  Result := ExpandConstant('{param:DATADIR|}');
end;

procedure InitializeWizard();
begin
  DataPage := CreateInputDirPage(wpSelectDir, CustomMessage('DataTitle'), CustomMessage('DataDesc'),
    CustomMessage('DataPrompt'), False, 'LPR');
  DataPage.Add('');
  if GetCommandLineHome() <> '' then
    DataPage.Values[0] := GetCommandLineHome()
  else
    DataPage.Values[0] := DefaultHome();
end;

procedure StopOldService();
var
  Code: Integer;
begin
  if FileExists(ExpandConstant('{app}\LPR-Service.exe')) then
  begin
    Exec(ExpandConstant('{app}\LPR-Service.exe'), 'stop', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Exec(ExpandConstant('{app}\LPR-Service.exe'), 'uninstall', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopOldService();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Home: string;
  Code: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Home := DataPage.Values[0];
    ForceDirectories(Home);
    ForceDirectories(ExpandConstant('{commonappdata}\LPR'));
    SaveStringToFile(ExpandConstant('{commonappdata}\LPR\home.txt'), Home, False);
    // ให้ผู้ใช้ทุกคนในเครื่องแก้ไขโฟลเดอร์ข้อมูลได้ (service ทำงานเป็น LocalSystem)
    Exec(ExpandConstant('{sys}\icacls.exe'), '"' + Home + '" /grant *S-1-5-32-545:(OI)(CI)M /T /C /Q', '',
      SW_HIDE, ewWaitUntilTerminated, Code);
    if WizardIsTaskSelected('service') then
    begin
      WizardForm.StatusLabel.Caption := 'กำลังติดตั้งและเริ่ม Windows service...';
      Exec(ExpandConstant('{app}\LPR-Service.exe'), 'install', '', SW_HIDE, ewWaitUntilTerminated, Code);
      Exec(ExpandConstant('{app}\LPR-Service.exe'), 'start', '', SW_HIDE, ewWaitUntilTerminated, Code);
    end;
  end;
end;
