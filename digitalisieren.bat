@echo off
REM Doppelklick: startet die App im Browser (Dokumente auswaehlen, Einstellungen, Scan, Pruefung).
REM PDF-Datei auf dieses Symbol ziehen: wertet sie direkt aus und oeffnet die Pruefung.
setlocal
cd /d "%~dp0"
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
if "%~1"=="" (
  echo Die App oeffnet sich im Browser. Dieses Fenster offen lassen - schliessen beendet die App.
  %PY% -m digitalyzer
) else (
  %PY% -m digitalyzer "%~1"
)
pause
