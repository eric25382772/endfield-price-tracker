; 終末地彈性物資價格追蹤器 - Inno Setup 安裝精靈
; 編譯方式：在已裝 Inno Setup 6 的電腦上雙擊 build.bat
; 需要 InnoDownloadPlugin (idp) — 放在本資料夾的 InnoDownloadPlugin/ 下

#define MyAppName "終末地彈性物資價格追蹤器"
#define MyAppShortName "終末地追蹤器"
#define MyAppVersion "5.0.2"
#define MyAppPublisher "eric25382772"
#define MyAppURL "https://github.com/eric25382772/endfield-price-tracker"
#define MyAppExeName "start_scanner.bat"
#define PythonVersion "3.12.7"
#define PythonInstaller "python-3.12.7-amd64.exe"
; PyTorch 的 c10.dll 依賴 VC++ 執行庫；乾淨 Windows 沒有，缺了 easyocr/torch 會 import 崩潰（WinError 126）
#define VCRedistUrl "https://aka.ms/vs/17/release/vc_redist.x64.exe"
#define VCRedistInstaller "vc_redist.x64.exe"

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
; VC++ 執行庫裝完常回傳 3010（建議重開機）；但本程式不用重開就能用（torch 立即可載入），
; 忽略 [Run] 步驟的重開要求，避免結尾跳出多餘的「需要重新啟動電腦」
RestartIfNeededByRun=no
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
  Parameters: "/quiet /norestart InstallAllUsers=1 PrependPath=1 Include_test=0"; \
  StatusMsg: "正在安裝 Python {#PythonVersion}（約 2 分鐘，請勿關閉視窗）..."; \
  Check: NeedsPython; Flags: waituntilterminated; \
  BeforeInstall: PyBefore; AfterInstall: PyAfter

; 1.5 安裝 VC++ 執行庫（PyTorch 相依，缺了 OCR 會 import 崩潰）。已裝過會自行快速略過
Filename: "{tmp}\{#VCRedistInstaller}"; \
  Parameters: "/install /quiet /norestart"; \
  StatusMsg: "正在安裝 Visual C++ 執行庫（PyTorch 相依）..."; \
  Flags: waituntilterminated; \
  BeforeInstall: VcBefore; AfterInstall: VcAfter

; 2. 升級 pip
; 用完整路徑叫 python.exe，不靠 PATH：剛裝好的 Python 其 PATH 變更不會即時進到本安裝行程的環境，
; 全新機器上 cmd 裡的 `python` 會找不到（甚至叫出 Microsoft Store 假 python），導致這幾步靜默失敗、什麼都沒裝
Filename: "{code:PyExe}"; \
  Parameters: "-m pip install --upgrade pip"; \
  StatusMsg: "正在升級 pip..."; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: PipBefore; AfterInstall: PipAfter

; 3. 安裝 requirements.txt
Filename: "{code:PyExe}"; \
  Parameters: "-m pip install -r ""{app}\requirements.txt"""; \
  StatusMsg: "正在下載 Python 套件（約 5-10 分鐘，請耐心等待）..."; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: ReqBefore; AfterInstall: ReqAfter

; 4. 預先下載 EasyOCR 繁中模型
Filename: "{code:PyExe}"; \
  Parameters: "-c ""import easyocr; easyocr.Reader(['ch_tra','en'], gpu=False)"""; \
  StatusMsg: "正在下載 OCR 中文模型（約 300-500 MB，請稍候）..."; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: OcrBefore; AfterInstall: OcrAfter

; 5. 把好友參考圖種子複製到 %LOCALAPPDATA%
Filename: "{cmd}"; \
  Parameters: "/C if not exist ""{localappdata}\EndfieldTracker\friend_refs"" xcopy /E /I /Y ""{app}\data\item_images\friend"" ""{localappdata}\EndfieldTracker\friend_refs"""; \
  StatusMsg: "建立使用者資料目錄..."; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: CopyBefore; AfterInstall: CopyAfter

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

// 解析出可靠的 python.exe 完整路徑，供 pip / OCR 步驟使用（不靠會延遲更新的 PATH）
function PyExe(Param: String): String;
var
  RegPath: String;
begin
  // 1) 本流程 all-users 安裝的 Python 3.12 預設落點
  Result := ExpandConstant('{commonpf}\Python312\python.exe');
  if FileExists(Result) then
    exit;
  // 2) 使用者原本就裝過的 Python 3.12（登錄檔找安裝路徑）
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', RegPath) then
  begin
    Result := AddBackslash(RegPath) + 'python.exe';
    if FileExists(Result) then exit;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', RegPath) then
  begin
    Result := AddBackslash(RegPath) + 'python.exe';
    if FileExists(Result) then exit;
  end;
  // 3) 最後退回 PATH（既有安裝且已在 PATH 上時可用）
  Result := 'python';
end;

procedure InitializeWizard();
begin
  if NeedsPython() then
    idpAddFile('https://www.python.org/ftp/python/{#PythonVersion}/{#PythonInstaller}',
               ExpandConstant('{tmp}\{#PythonInstaller}'));
  // VC++ 執行庫一律下載安裝（idempotent，已裝過會快速略過），確保 torch DLL 能載入
  idpAddFile('{#VCRedistUrl}', ExpandConstant('{tmp}\{#VCRedistInstaller}'));
  idpDownloadAfter(wpReady);
end;

// 分階段實心進度條：檔案幾秒就複製完（進度條會被 Inno 填滿），之後 pip/OCR 下載才是大宗。
// 每個安裝階段開始/結束就把綠條推到對應百分比，只有真的全裝完才到 100%，不再假裝完成卡 100%。
// 各階段權重依乾淨機器上的實際耗時估算（裝套件與下載 OCR 模型最久）。
var
  GaugeReady: Boolean;

procedure GSet(V: Integer);
begin
  if not GaugeReady then
  begin
    WizardForm.ProgressGauge.Style := npbstNormal;
    WizardForm.ProgressGauge.Min := 0;
    WizardForm.ProgressGauge.Max := 100;
    GaugeReady := True;
  end;
  WizardForm.ProgressGauge.Position := V;
end;

procedure PyBefore;   begin GSet(2);   end;   // 裝 Python（約 2 分鐘）
procedure PyAfter;    begin GSet(18);  end;
procedure VcBefore;   begin GSet(18);  end;   // 裝 VC++ 執行庫
procedure VcAfter;    begin GSet(25);  end;
procedure PipBefore;  begin GSet(25);  end;   // 升級 pip
procedure PipAfter;   begin GSet(28);  end;
procedure ReqBefore;  begin GSet(30);  end;   // 下載安裝套件（torch 等，最久）
procedure ReqAfter;   begin GSet(82);  end;
procedure OcrBefore;  begin GSet(82);  end;   // 下載 OCR 中文模型（約 300-500MB）
procedure OcrAfter;   begin GSet(96);  end;
procedure CopyBefore; begin GSet(96);  end;   // 複製好友參考圖種子
procedure CopyAfter;  begin GSet(100); end;
