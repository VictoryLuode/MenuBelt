@echo off
rem Deploy this repo's plugin files to the Krita resource directory.
set RES=D:\home\Documents\Krita\KritaResource
copy /y pykrita\menubelt.desktop "%RES%\pykrita\" >nul
xcopy /s /y /e /i pykrita\menubelt "%RES%\pykrita\menubelt" >nul
copy /y actions\menubelt.action "%RES%\actions\" >nul
echo Deployed.
