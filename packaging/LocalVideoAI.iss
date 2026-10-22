#define MyAppName "LocalVideoAI"
#define MyAppDisplay "LocalVideoAI Translator"
#define MyAppVersion "0.22.4"
#define MyAppPublisher "LocalVideoAI"
#define MyAppExeName "LocalVideoAI.exe"

[Setup]
AppId={{8F3C2A71-9B64-4D1E-9C2A-7A1B2C3D4E5F}}
AppName={#MyAppDisplay}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\LocalVideoAI
DefaultGroupName={#MyAppDisplay}
DisableProgramGroupPage=no
OutputDir=..\release
OutputBaseFilename=LocalVideoAI_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
; Users choose the install directory on the standard page.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"

[Files]
Source: "..\release\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppDisplay}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppDisplay}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplay}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 LocalVideoAI"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\install_paths.json"
Type: files; Name: "{app}\uninstall_choice.json"

[Code]
var
  DirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DirPage := CreateInputDirPage(wpSelectDir,
    '数据目录', '选择模型目录、项目目录和缓存目录。',
    '这些目录可以和安装目录分开。卸载时可以选择保留模型或项目。',
    False, '');
  DirPage.Add('模型目录');
  DirPage.Add('项目目录');
  DirPage.Add('缓存目录');
  DirPage.Values[0] := ExpandConstant('{localappdata}\LocalVideoAI\models');
  DirPage.Values[1] := ExpandConstant('{localappdata}\LocalVideoAI\projects');
  DirPage.Values[2] := ExpandConstant('{localappdata}\LocalVideoAI\cache');
end;

function CmdDir(Param, Fallback: String): String;
begin
  Result := ExpandConstant('{param:' + Param + '|' + Fallback + '}');
end;

function JsonEscape(Value: String): String;
begin
  StringChangeEx(Value, '\', '/', True);
  Result := Value;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Json: String;
  Models, Projects, Cache: String;
begin
  if CurStep = ssPostInstall then
  begin
    Models := DirPage.Values[0];
    Projects := DirPage.Values[1];
    Cache := DirPage.Values[2];
    if ExpandConstant('{param:MODELS|}') <> '' then
      Models := ExpandConstant('{param:MODELS}');
    if ExpandConstant('{param:PROJECTS|}') <> '' then
      Projects := ExpandConstant('{param:PROJECTS}');
    if ExpandConstant('{param:CACHE|}') <> '' then
      Cache := ExpandConstant('{param:CACHE}');
    if Models = '' then
      Models := ExpandConstant('{localappdata}\LocalVideoAI\models');
    if Projects = '' then
      Projects := ExpandConstant('{localappdata}\LocalVideoAI\projects');
    if Cache = '' then
      Cache := ExpandConstant('{localappdata}\LocalVideoAI\cache');
    ForceDirectories(Models);
    ForceDirectories(Projects);
    ForceDirectories(Cache);
    Json :=
      '{' + #13#10 +
      '  "models_dir": "' + JsonEscape(Models) + '",' + #13#10 +
      '  "projects_dir": "' + JsonEscape(Projects) + '",' + #13#10 +
      '  "cache_dir": "' + JsonEscape(Cache) + '"' + #13#10 +
      '}' + #13#10;
    SaveStringToFile(ExpandConstant('{app}\install_paths.json'), Json, False);
  end;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  Mode: String;
  Args: String;
begin
  Result := True;
  Mode := ExpandConstant('{param:UNINSTALLMODE|}');
  if Mode <> '' then
    Args := '--uninstall-mode ' + Mode
  else if UninstallSilent then
    Args := '--uninstall-mode program'
  else
    Args := '--uninstall';
  if Exec(ExpandConstant('{app}\{#MyAppExeName}'), Args, '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode <> 0 then
      Result := False;
  end;
end;
