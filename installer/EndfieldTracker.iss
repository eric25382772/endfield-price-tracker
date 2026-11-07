; 終末地彈性物資價格追蹤器 - Inno Setup 安裝精靈
; 編譯方式：在已裝 Inno Setup 6 的電腦上雙擊 build.bat
; 需要 InnoDownloadPlugin (idp) — 放在本資料夾的 InnoDownloadPlugin/ 下

#define MyAppName "終末地彈性物資價格追蹤器"
#define MyAppShortName "終末地追蹤器"
#define MyAppVersion "7.2"
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
; 安裝精靈本身與「新增或移除程式」清單的圖示
SetupIconFile=..\static\images\app.ico
UninstallDisplayIcon={app}\static\images\app.ico
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
; 捷徑指向 .bat，沒指定 IconFilename 的話會拿到 Windows 預設的齒輪圖示
Name: "{group}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\static\images\app.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\static\images\app.ico"

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
; 一律用 python.exe 的完整路徑，絕不退回 PATH 上的 `python`：那可能是微軟商店的「應用程式執行別名」
; （0 bytes 的假捷徑），用管理員身分執行會被 Windows 擋下，噴 CreateProcess 1920；
; 就算抓到真的，也可能是我們沒驗證過的版本，套件會裝到錯的 Python 去。
; 找不到可用的 Python 時整步跳過（HavePython），最後由 CurStepChanged 跳錯誤，不靜默假裝成功。
Filename: "{code:PyExe}"; \
  Parameters: "-m pip install --upgrade pip"; \
  StatusMsg: "正在升級 pip..."; \
  Check: HavePython; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: PipBefore; AfterInstall: PipAfter

; 3. 安裝 requirements.txt
Filename: "{code:PyExe}"; \
  Parameters: "-m pip install -r ""{app}\requirements.txt"""; \
  StatusMsg: "正在下載 Python 套件（約 5-10 分鐘，請耐心等待）..."; \
  Check: HavePython; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: ReqBefore; AfterInstall: ReqAfter

; 4. 預先下載 EasyOCR 繁中模型
; 套件沒裝成功就別浪費使用者 10 分鐘下載模型（一定也會失敗）
Filename: "{code:PyExe}"; \
  Parameters: "-c ""import easyocr; easyocr.Reader(['ch_tra','en'], gpu=False)"""; \
  StatusMsg: "正在下載 OCR 中文模型（約 300-500 MB，請稍候）..."; \
  Check: PackagesOK; \
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
// 套件是否真的裝起來了（ReqAfter 實測 import 的結果），決定要不要繼續下載 OCR 模型
var
  PkgOK: Boolean;

// 回傳 Dir 底下可用的 python.exe 完整路徑，不能用就回傳空字串。
// WindowsApps 底下的是微軟商店的「應用程式執行別名」（0 bytes 的假捷徑），
// 用管理員身分執行會被 Windows 拒絕（CreateProcess 1920），一律當作沒有。
function PyIn(const Dir: String): String;
var
  Exe: String;
begin
  Result := '';
  if Dir = '' then
    exit;
  Exe := AddBackslash(Dir) + 'python.exe';
  if (Pos('\windowsapps\', Lowercase(Exe)) = 0) and FileExists(Exe) then
    Result := Exe;
end;

// 裝在非預設位置的 Python，從登錄檔問出安裝路徑
function PyInReg(RootKey: Integer; const Ver: String): String;
var
  Dir: String;
begin
  Result := '';
  if RegQueryStringValue(RootKey, 'SOFTWARE\Python\PythonCore\' + Ver + '\InstallPath', '', Dir) then
    Result := PyIn(Dir);
end;

// 找出一個「真的存在、而且套件裝得起來」的 python.exe；找不到回傳空字串。
// 絕不回傳 'python' 這種靠 PATH 解析的名字——那正是 1920 的來源。
// 只認 3.11~3.14：torch 2.15 最低到 3.11、opencv-python 5.0 最高到 3.14，範圍外裝不起來。
// 不用 `python --version` 問，問到的可能是假捷徑或我們不支援的版本，會騙我們跳過安裝 Python。
function FindPython(): String;
var
  Vers: array[0..3] of String;
  Dirs: array[0..3] of String;
  I: Integer;
begin
  // 本安裝程式自帶 3.12，優先採用；其次才是使用者原本就有的其他可用版本
  Vers[0] := '3.12'; Dirs[0] := 'Python312';
  Vers[1] := '3.13'; Dirs[1] := 'Python313';
  Vers[2] := '3.11'; Dirs[2] := 'Python311';
  Vers[3] := '3.14'; Dirs[3] := 'Python314';
  for I := 0 to 3 do
  begin
    // all-users 安裝的預設落點（本流程用 InstallAllUsers=1 就會落在這）
    Result := PyIn(ExpandConstant('{commonpf}') + '\' + Dirs[I]);
    if Result <> '' then exit;
    // 使用者自己裝的 per-user 預設落點
    Result := PyIn(ExpandConstant('{localappdata}') + '\Programs\Python\' + Dirs[I]);
    if Result <> '' then exit;
    // 裝在別的地方
    Result := PyInReg(HKLM, Vers[I]);
    if Result <> '' then exit;
    Result := PyInReg(HKCU, Vers[I]);
    if Result <> '' then exit;
  end;
  Result := '';
end;

function NeedsPython(): Boolean;
begin
  Result := FindPython() = '';
end;

function HavePython(): Boolean;
begin
  Result := FindPython() <> '';
end;

function PackagesOK(): Boolean;
begin
  Result := HavePython() and PkgOK;
end;

// 供 [Run] 的 Filename 使用。正常情況搭配 Check: HavePython，走不到找不到的分支；
// 真走到了也要給一個「一看就知道是什麼事」的假路徑，絕不能回傳 'python' 讓 Windows 自由發揮
function PyExe(Param: String): String;
begin
  Result := FindPython();
  if Result = '' then
    Result := ExpandConstant('{app}\PYTHON-NOT-FOUND.exe');
end;

procedure InitializeWizard();
begin
  PkgOK := True;
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

// 不看 pip 的回傳值，直接驗真正要的結果：套件 import 得起來嗎。
// pip 中途失敗（斷網、防毒擋、版本沒輪子）在 [Run] 裡是靜默的，Inno 不會理回傳值，
// 以前會一路跑到「安裝完成」，使用者雙擊捷徑才發現沒反應，而且查不出原因。
procedure ReqAfter;
var
  Py: String;
  Code: Integer;
begin
  GSet(82);
  Py := FindPython();
  PkgOK := (Py <> '') and
           Exec(Py, '-c "import easyocr, cv2, flask"', '', SW_HIDE,
                ewWaitUntilTerminated, Code) and (Code = 0);
end;
procedure OcrBefore;  begin GSet(82);  end;   // 下載 OCR 中文模型（約 300-500MB）
procedure OcrAfter;   begin GSet(96);  end;
procedure CopyBefore; begin GSet(96);  end;   // 複製好友參考圖種子
procedure CopyAfter;  begin GSet(100); end;

// 裝壞了就明講。以前不管中間失敗幾次都照樣顯示「安裝完成」，使用者只會覺得程式是壞的
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    exit;
  if not HavePython() then
    MsgBox('Python 沒有安裝成功，所以套件也沒有裝，程式還不能用。' + #13#10#13#10 +
           '請先關閉防毒軟體，再重新執行一次安裝程式。', mbError, MB_OK)
  else if not PkgOK then
    MsgBox('Python 套件沒有裝完整，程式還不能用。' + #13#10#13#10 +
           '通常是安裝過程中網路中斷。請確認網路後，重新執行一次安裝程式。', mbError, MB_OK);
end;
