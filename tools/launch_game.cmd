@echo off
rem Launch Okami HD through Steam (app id 587620). Steam's install path is
rem read from the registry, falling back to the default location.
set "STEAM="
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Valve\Steam" /v SteamExe 2^>nul ^| find /i "SteamExe"') do set "STEAM=%%b"
if not defined STEAM set "STEAM=C:\Program Files (x86)\Steam\steam.exe"
"%STEAM%" -applaunch 587620
