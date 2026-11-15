#!/usr/bin/env bash
# Roda o launcher direto do codigo-fonte (alternativa ao binario). Cria um venv na primeira vez.
set -e
D="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$D/.venv/bin/python" ]; then python3 -m venv "$D/.venv"; "$D/.venv/bin/pip" install PySide6-Essentials; fi
exec "$D/.venv/bin/python" "$D/launcher.py" "$@"
