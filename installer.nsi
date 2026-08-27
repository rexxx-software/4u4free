; 4u4free Windows installer
; Build with build_installer.bat. VERSION and VERSION4 are supplied by the build script.

Unicode true
ManifestDPIAware true

!define APP_NAME "4u4free"
!define APP_PUBLISHER "rexxx"
!define APP_EXE "4u4free.exe"
!define APP_REG_KEY "Software\4u4free"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\4u4free"

!ifndef VERSION
    !define VERSION "0.5.3"
!endif
!ifndef VERSION4
    !define VERSION4 "0.5.3.0"
!endif

Name "${APP_NAME}"
OutFile "dist\4u4free-${VERSION}-Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${APP_REG_KEY}" "InstallLocation"
RequestExecutionLevel admin

SetCompressor /SOLID lzma
SetCompressorDictSize 64
CRCCheck on
ShowInstDetails show
ShowUninstDetails show
BrandingText "${APP_NAME} ${VERSION}"

VIProductVersion "${VERSION4}"
VIAddVersionKey /LANG=1033 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APP_NAME} setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright (c) ${APP_PUBLISHER}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "Sections.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "four_u_four_free\assets\4u4free.ico"
!define MUI_UNICON "four_u_four_free\assets\4u4free.ico"
!define MUI_WELCOMEPAGE_TITLE "Install ${APP_NAME} ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Setup will install ${APP_NAME} on this computer.$\r$\n$\r$\nThe default location is Program Files. You can choose a different folder on the next screen.$\r$\n$\r$\nClick Next to continue."
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_DIRECTORYPAGE_VERIFYONLEAVE

Var StartMenuFolder
!define MUI_STARTMENUPAGE_DEFAULTFOLDER "${APP_NAME}"
!define MUI_STARTMENUPAGE_REGISTRY_ROOT HKLM
!define MUI_STARTMENUPAGE_REGISTRY_KEY "${APP_REG_KEY}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "StartMenuFolder"

!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_NOREBOOTSUPPORT

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Function .onInit
    ${Unless} ${RunningX64}
        MessageBox MB_OK|MB_ICONSTOP "${APP_NAME} requires a 64-bit version of Windows."
        Abort
    ${EndUnless}
    SetRegView 64
    SetShellVarContext all
FunctionEnd

Function un.onInit
    SetRegView 64
    SetShellVarContext all
FunctionEnd

Section "4u4free (required)" SEC_APPLICATION
    SectionIn RO
    SetRegView 64
    SetShellVarContext all
    SetOutPath "$INSTDIR"

    ; settings.bin is a legacy development artifact and must never be installed.
    File /r /x "settings.bin" "dist\4u4free\*"
    File /oname=4u4free.ico "four_u_four_free\assets\4u4free.ico"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
        CreateShortcut "$SMPROGRAMS\$StartMenuFolder\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
        CreateShortcut "$SMPROGRAMS\$StartMenuFolder\Uninstall ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
    !insertmacro MUI_STARTMENU_WRITE_END

    WriteRegStr HKLM "${APP_REG_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE},0"
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoRepair" 1

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "EstimatedSize" $0
SectionEnd

Section "Desktop shortcut" SEC_DESKTOP
    SetShellVarContext all
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APPLICATION} "Install the ${APP_NAME} application and add Start menu entries."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} "Create a ${APP_NAME} shortcut on the desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    SetRegView 64
    SetShellVarContext all

    ; Close the app if it is still running so its files can be removed cleanly.
    nsExec::ExecToLog 'taskkill.exe /F /T /IM "${APP_EXE}"'

    ReadRegStr $StartMenuFolder HKLM "${APP_REG_KEY}" "StartMenuFolder"
    ${If} $StartMenuFolder != ""
        Delete "$SMPROGRAMS\$StartMenuFolder\${APP_NAME}.lnk"
        Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall ${APP_NAME}.lnk"
        RMDir "$SMPROGRAMS\$StartMenuFolder"
    ${EndIf}
    Delete "$DESKTOP\${APP_NAME}.lnk"

    DeleteRegKey HKLM "${APP_UNINSTALL_KEY}"
    DeleteRegKey HKLM "${APP_REG_KEY}"

    RMDir /r "$INSTDIR"

    IfSilent keep_user_data
    MessageBox MB_YESNO|MB_ICONQUESTION "Also remove your ${APP_NAME} settings from Local AppData?" IDNO keep_user_data
        RMDir /r "$LOCALAPPDATA\4u4free"
    keep_user_data:
SectionEnd
