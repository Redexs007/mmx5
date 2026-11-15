#!/usr/bin/env bash
# Gera na raiz do repositorio: MegaManX5-Launcher (binario unico, PyInstaller) e MegaManX5-Play (executavel direto).
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$D/.." && pwd)"
PY="${PYTHON:-python3}"
if ! "$PY" -c "import PySide6, PyInstaller" 2>/dev/null; then
  "$PY" -m venv "$D/.venv"
  "$D/.venv/bin/pip" install -q -r "$D/requirements.txt"
  PY="$D/.venv/bin/python"
fi
T="${TMPDIR:-/tmp}/mmx5-pyi"
"$PY" -m PyInstaller --onefile --name MegaManX5-Launcher --add-data "$D/assets:assets" \
  --exclude-module PySide6.QtNetwork --distpath "$ROOT" --workpath "$T" --specpath "$T" "$D/launcher.py"
gcc -O2 -static -o "$ROOT/MegaManX5-Play" "$D/play.c"
echo "Pronto: $ROOT/MegaManX5-Launcher e $ROOT/MegaManX5-Play"
