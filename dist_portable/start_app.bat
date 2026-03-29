@echo off
chcp 65001 >nul
cd /d %~dp0
for %%F in (*.exe) do (
  start "" "%%F"
  goto :eof
)
echo No executable found in current folder.
