; Inno Setup Script for Scrcpy Master
; Use Inno Setup Compiler to build this into a Setup.exe

[Setup]
AppName=Scrcpy Master
AppVersion=2.0.0
DefaultDirName={autopf}\ScrcpyMaster
DefaultGroupName=Scrcpy Master
UninstallDisplayIcon={app}\ScrcpyMaster.exe
Compression=lzma2
SolidCompression=yes
OutputDir=Output
OutputBaseFilename=ScrcpyMaster_v2.0.0_Setup
SetupIconFile=scrcpy_master.ico

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The main application folder from PyInstaller
Source: "dist\ScrcpyMaster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Include tools folder specifically if it exists in the root
Source: "tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Scrcpy Master"; Filename: "{app}\ScrcpyMaster.exe"
Name: "{autodesktop}\Scrcpy Master"; Filename: "{app}\ScrcpyMaster.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ScrcpyMaster.exe"; Description: "{cm:LaunchProgram,Scrcpy Master}"; Flags: nowait postinstall skipifsilent
