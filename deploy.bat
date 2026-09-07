@echo off
rem Deploy this repo's plugin files to the Krita resource directory.
set RES=D:\home\Documents\Krita\KritaResource
copy /y pykrita\custom_modular_menu.desktop "%RES%\pykrita\" >nul
xcopy /s /y /e /i pykrita\custom_modular_menu "%RES%\pykrita\custom_modular_menu" >nul
copy /y actions\custom_modular_menu.action "%RES%\actions\" >nul
echo Deployed.
