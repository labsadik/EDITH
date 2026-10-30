#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\EDITH"
#endif

[Setup]
AppId={{E1D17E20-B8DB-4A45-8C7A-ED17ED17ED17}
AppName=EDITH — Neuron Intelligence
AppVersion={#AppVersion}
AppVerName=EDITH — Neuron Intelligence {#AppVersion}
AppPublisher=Sadik Laskar
AppPublisherURL=https://github.com/WorkRCS/EDITH_v1
AppSupportURL=https://github.com/WorkRCS/EDITH_v1
AppUpdatesURL=https://github.com/WorkRCS/EDITH_v1/releases
DefaultDirName={autopf}\EDITH
DefaultGroupName=EDITH
DisableWelcomePage=yes
LicenseFile=..\..\LICENSE
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\..\config\assistant.ico
UninstallDisplayIcon={app}\EDITH.exe
OutputDir=..\..\dist\installer
OutputBaseFilename=EDITH-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardSizePercent=110
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany=Sadik Laskar
VersionInfoDescription=EDITH — Neuron Intelligence Setup
VersionInfoProductName=EDITH — Neuron Intelligence
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=Copyright (c) 2026 Sadik Laskar. All Rights Reserved.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\EDITH"; Filename: "{app}\EDITH.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\EDITH"; Filename: "{app}\EDITH.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\EDITH.exe"; Description: "Launch EDITH — Neuron Intelligence"; Flags: postinstall nowait skipifsilent
