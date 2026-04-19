; 終末地彈性物資價格追蹤器 - Inno Setup 安裝精靈
; 編譯方式：在已裝 Inno Setup 6 的電腦上雙擊 build.bat
; 需要 InnoDownloadPlugin (idp) — 放在本資料夾的 InnoDownloadPlugin/ 下

#define MyAppName "終末地彈性物資價格追蹤器"
#define MyAppShortName "終末地追蹤器"
#define MyAppVersion "2.0"
#define MyAppPublisher "eric25382772"
#define MyAppURL "https://github.com/eric25382772/endfield-price-tracker"
#define MyAppExeName "start_scanner.bat"
#define PythonVersion "3.12.7"
#define PythonInstaller "python-3.12.7-amd64.exe"

#include "InnoDownloadPlugin\idp.iss"

[Setup]
AppId={{8B3A4F2C-9D2E-4A1B-B5F6-2C7E8A9D4E1F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\EndfieldTracker
DefaultGroupName={#MyAppShortName}
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename=EndfieldTracker_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayName={#MyAppName}

[Languages]
Name: "tchinese"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 專案 Python 原始碼
Source: "..\*.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start_scanner.bat"; DestDir: "{app}"; Flags: ignoreversion
; 子資料夾（templates / static / data / ocr / tools）
Source: "..\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\data\*.py"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\data\item_images\*.png"; DestDir: "{app}\data\item_images"; Flags: ignoreversion
Source: "..\data\item_images\friend\*.png"; DestDir: "{app}\data\item_images\friend"; Flags: ignoreversion
Source: "..\ocr\*.py"; DestDir: "{app}\ocr"; Flags: ignoreversion
Source: "..\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 1. 若沒 Python，安裝 Python（idp 已下載到 {tmp}）
Filename: "{tmp}\{#PythonInstaller}"; \
  Parameters: "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0"; \
  StatusMsg: "正在安裝 Python {#PythonVersion}（約 2 分鐘，請勿關閉視窗）..."; \
  Check: NeedsPython; Flags: waituntilterminated

; 2. 升級 pip
Filename: "{cmd}"; \
  Parameters: "/C python -m pip install --upgrade pip"; \
  StatusMsg: "正在升級 pip..."; \
  Flags: runhidden waituntilterminated

; 3. 安裝 requirements.txt
Filename: "{cmd}"; \
  Parameters: "/C python -m pip install -r ""{app}\requirements.txt"""; \
  StatusMsg: "正在下載 Python 套件（約 5-10 分鐘，請耐心等待）..."; \
  Flags: runhidden waituntilterminated

; 4. 預先下載 EasyOCR 繁中模型
Filename: "{cmd}"; \
  Parameters: "/C python -c ""import easyocr; easyocr.Reader(['ch_tra','en'], gpu=False)"""; \
  StatusMsg: "正在下載 OCR 中文模型（約 300-500 MB，畫面停住是正常的）..."; \
  Flags: runhidden waituntilterminated

; 5. 把好友參考圖種子複製到 %LOCALAPPDATA%
Filename: "{cmd}"; \
  Parameters: "/C if not exist ""{localappdata}\EndfieldTracker\friend_refs"" xcopy /E /I /Y ""{app}\data\item_images\friend"" ""{localappdata}\EndfieldTracker\friend_refs"""; \
  StatusMsg: "建立使用者資料目錄..."; \
  Flags: runhidden waituntilterminated

[UninstallDelete]
; 解除安裝時不刪 %LOCALAPPDATA%\EndfieldTracker（保留使用者的 prices.db / 學到的好友圖）

[Code]
function NeedsPython(): Boolean;
var
  ResultCode: Integer;
begin
  Result := not Exec('cmd.exe', '/C python --version', '', SW_HIDE,
                     ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0);
end;

procedure InitializeWizard();
begin
  if NeedsPython() then
    idpAddFile('https://www.python.org/ftp/python/{#PythonVersion}/{#PythonInstaller}',
               ExpandConstant('{tmp}\{#PythonInstaller}'));
  idpDownloadAfter(wpReady);
end;
