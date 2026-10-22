#define MyAppName "LocalVideoAI"
#define MyAppDisplay "LocalVideoAI Translator"
#define MyAppVersion "0.22.4"
#define MyAppExeName "LocalVideoAI.exe"

[Setup]
AppName={#MyAppDisplay} Portable
AppVersion={#MyAppVersion}
DefaultDirName={src}\LocalVideoAI
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=LocalVideoAI_Portable
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=no
CreateUninstallRegKey=no
UpdateUninstallLogAppName=no
UsePreviousAppDir=no
DirExistsWarning=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\release\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\packaging\PORTABLE_README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SaveStringToFile(ExpandConstant('{app}\portable.flag'), '1' + #13#10, False);
  end;
end;
