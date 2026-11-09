@echo off
REM PDF-Datei auf dieses Symbol ziehen (Drag and Drop) - oder: digitalisieren.bat scan.pdf
REM Wertet den Scan aus und oeffnet danach die Pruef-App im Browser.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Bitte eine PDF-Datei auf diese Datei ziehen oder als Parameter angeben.
  pause
  exit /b 1
)
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m digitalyzer "%~1"
pause
