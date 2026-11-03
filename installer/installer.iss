; Inno Setup 6 安装包定义 —— CineSort
; 先运行 tools\build_exe.ps1 生成 dist\CineSort\（onedir 全目录），再运行 tools\build_installer.ps1
; 版本号由构建脚本经 /Dversion 注入（对齐 SubTrans 的 ISCC /Dversion 模式）

#ifndef version
  #define version "0.5.0"
#endif

[Setup]
AppName=CineSort 影片归类器
AppVersion={#version}
AppPublisher=CineSort
DefaultDirName={autopf}\CineSort
DefaultGroupName=CineSort
OutputBaseFilename=CineSort-setup-{#version}
OutputDir=Output
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\CineSort.exe
; 配置默认写入 %APPDATA%\CineSort（exe 检测到 Program Files 不可写时自动回退）

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "..\dist\CineSort\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config.example.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\CineSort 影片归类器"; Filename: "{app}\CineSort.exe"
Name: "{group}\卸载 CineSort"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CineSort 影片归类器"; Filename: "{app}\CineSort.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CineSort.exe"; Description: "启动 CineSort"; Flags: postinstall nowait skipifsilent
