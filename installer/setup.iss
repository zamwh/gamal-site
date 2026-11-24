; Gamal Almshrqi POS installer (built by GitHub Actions)
#define AppName "Gamal Almshrqi Gold"
#define AppVer GetEnv("APP_VERSION")
[Setup]
AppId={{6E2B8F3A-1C4D-4E8B-9A21-GAMALPOS0001}
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=Gamal Almshrqi Gold & Jewelry
DefaultDirName={autopf}\GamalAlmshrqi
DefaultGroupName=Gamal Almshrqi
OutputDir=..\Output
OutputBaseFilename=GamalAlmshrqi_Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\GamalAlmshrqi.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\GamalAlmshrqi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Gamal Almshrqi"; Filename: "{app}\GamalAlmshrqi.exe"
Name: "{autodesktop}\Gamal Almshrqi"; Filename: "{app}\GamalAlmshrqi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GamalAlmshrqi.exe"; Description: "Run Gamal Almshrqi"; Flags: nowait postinstall skipifsilent
