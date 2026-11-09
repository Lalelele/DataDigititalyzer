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
REM Bevorzugt eine Python-Version, fuer die alle Pakete verfuegbar sind (3.12, 3.11, 3.13)
set PY=
for %%V in (3.12 3.11 3.13) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set PY=py -%%V
  )
)
if not defined PY (
  where py >nul 2>nul && (set PY=py) || (set PY=python)
)
echo Verwende: %PY%
%PY% -m digitalyzer "%~1"
pause
