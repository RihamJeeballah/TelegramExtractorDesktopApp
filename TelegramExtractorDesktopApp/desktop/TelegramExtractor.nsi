!include "MUI2.nsh"

; ================= App Info =================
Name "Telegram Extractor"
OutFile "TelegramExtractor_Setup.exe"
InstallDir "$PROGRAMFILES64\TelegramExtractor"
InstallDirRegKey HKLM "Software\TelegramExtractor" "Install_Dir"
RequestExecutionLevel admin

; ================= Icons ====================
Icon "logo.ico"
UninstallIcon "logo.ico"

; ================= Pages ====================
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ================= Install ==================
Section "Install"

  SetOutPath "$INSTDIR"

  ; Copy entire PyInstaller folder (EXE + _internal)
  File /r "dist\TelegramExtractor\*.*"

  ; Save install path
  WriteRegStr HKLM "Software\TelegramExtractor" "Install_Dir" "$INSTDIR"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\Telegram Extractor.lnk" "$INSTDIR\TelegramExtractor.exe" "" "$INSTDIR\TelegramExtractor.exe"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\Telegram Extractor"
  CreateShortCut "$SMPROGRAMS\Telegram Extractor\Telegram Extractor.lnk" "$INSTDIR\TelegramExtractor.exe"

  ; Uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

SectionEnd

; ================= Uninstall =================
Section "Uninstall"

  Delete "$DESKTOP\Telegram Extractor.lnk"
  Delete "$SMPROGRAMS\Telegram Extractor\Telegram Extractor.lnk"
  RMDir "$SMPROGRAMS\Telegram Extractor"

  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\TelegramExtractor"

SectionEnd
