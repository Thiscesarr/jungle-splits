; Inno Setup script for the Jungle Splits installer.
; Built by tools/build.py (or the release workflow): iscc /DAppVersion=1.0.0 packaging\installer.iss
; Installs per user (no administrator prompt) and remembers the language picked here for the app.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3C2A51-7B1E-4C55-9E2A-4D6B1F0A9C21}
AppName=Jungle Splits
AppVersion={#AppVersion}
AppVerName=Jungle Splits {#AppVersion}
AppPublisher=Jungle Splits
AppPublisherURL=https://github.com/Thiscesarr/jungle-splits
AppSupportURL=https://github.com/Thiscesarr/jungle-splits/issues
DefaultDirName={localappdata}\Programs\Jungle Splits
DefaultGroupName=Jungle Splits
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=JungleSplits-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\JungleSplits.exe
UninstallDisplayName=Jungle Splits
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Jungle Splits installer

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\JungleSplits\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[INI]
; The app reads this on first start to open in the language chosen in the installer.
Filename: "{app}\install.ini"; Section: "app"; Key: "language"; String: "{language}"

[Icons]
Name: "{autoprograms}\Jungle Splits"; Filename: "{app}\JungleSplits.exe"
Name: "{autodesktop}\Jungle Splits"; Filename: "{app}\JungleSplits.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\JungleSplits.exe"; Description: "{cm:LaunchProgram,Jungle Splits}"; Flags: nowait postinstall skipifsilent
