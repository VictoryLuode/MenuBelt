@echo off
rem 把本仓库的插件文件部署到 Krita 资源目录
set RES=D:\home\Documents\Krita\KritaResource
copy /y pykrita\quick_list_menu.desktop "%RES%\pykrita\" >nul
xcopy /s /y /e /i pykrita\quick_list_menu "%RES%\pykrita\quick_list_menu" >nul
copy /y actions\quick_list_menu.action "%RES%\actions\" >nul
echo Deployed.
