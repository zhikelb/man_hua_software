; 漫画阅读器 - 便携版分发提示脚本
;
; 当前项目仅分发便携文件夹，不再提供安装程序。
; 保留此文件是为了给历史流程一个明确提示，避免误打包。
;
; 若运行 makensis packaging\installer.nsi，会输出一个提示程序，提醒使用 dist\漫画阅读器_便携版。

!include "MUI2.nsh"

Name "漫画阅读器（便携版）"
OutFile "..\dist\请使用便携版.exe"
RequestExecutionLevel user

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimplifiedChinese"

Section "提示"
    DetailPrint "本项目仅提供便携版分发。"
    DetailPrint "请直接使用 ..\\dist\\漫画阅读器_便携版 文件夹。"
    MessageBox MB_ICONINFORMATION|MB_OK "请直接分发并运行 ..\\dist\\漫画阅读器_便携版\\漫画阅读器.exe。$\r$\n无需安装。"
SectionEnd
