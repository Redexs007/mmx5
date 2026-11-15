#!/usr/bin/env bash
# Amplia as texturas capturadas (dumps -> replacements). Cria um venv com Pillow/NumPy na 1a vez.
set -e
D="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$D/.venv/bin/python" ]; then
  python3 -m venv "$D/.venv" && "$D/.venv/bin/pip" install -q pillow numpy
fi
exec "$D/.venv/bin/python" "$D/upscale_textures.py" "$@"
