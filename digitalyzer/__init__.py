"""DataDigititalyzer - Messwerte aus gescannten Tabellen digitalisieren und pruefen."""
import os as _os

# Die ONNX Runtime (Grundlage der Texterkennung) sendet in neueren Versionen Nutzungsdaten
# an Microsoft - auch wenn disable_telemetry_events() aufgerufen wird. Die
# Umgebungsvariable muss gesetzt sein, bevor onnxruntime geladen wird. Die Verarbeitung
# soll vollstaendig lokal bleiben.
_os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

__version__ = "0.2.0"
