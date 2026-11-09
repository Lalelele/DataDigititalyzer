@echo off
REM Installiert die benoetigten Pakete (einmalig, braucht Internet).
setlocal
cd /d "%~dp0"
set PY=
for %%V in (3.12 3.11 3.13) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set PY=py -%%V
  )
)
if not defined PY (
  echo.
  echo Keine passende Python-Version gefunden ^(benoetigt: 64-Bit Python 3.11, 3.12 oder 3.13^).
  echo Bitte Python 3.12 ^(64-Bit^) von https://www.python.org/downloads/ installieren
  echo oder - falls der Python-Installationsmanager vorhanden ist - eingeben:  py install 3.12
  pause
  exit /b 1
)
echo Verwende: %PY%
%PY% -c "import struct,sys; print('Python', sys.version.split()[0], struct.calcsize('P')*8, 'Bit')"
%PY% -m pip install -r requirements.txt
pause
