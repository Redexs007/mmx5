#!/usr/bin/env bash
# Gera dist/MegaManX5-Linux-<versao>-linux-x86_64.tar.gz com o binario, scripts, mods e documentacao.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-dev}"
OUT="$ROOT/dist"; STAGE="$OUT/MegaManX5-Linux-$VER"
rm -rf "$OUT"; mkdir -p "$STAGE"
bash "$ROOT/launcher/build_launcher.sh"
cp "$ROOT/MegaManX5-Launcher" "$ROOT/MegaManX5-Play" "$ROOT/build_linux.sh" "$ROOT/README.md" "$ROOT/LICENSE" \
   "$ROOT/THIRD_PARTY_NOTICES.md" "$ROOT/CHANGELOG.md" "$STAGE/"
cp -r "$ROOT/mods" "$ROOT/tools" "$ROOT/patches" "$ROOT/docs" "$STAGE/"
mkdir -p "$STAGE/launcher"
cp -r "$ROOT/launcher/launcher.py" "$ROOT/launcher/ui_kit.py" "$ROOT/launcher/padmap.py" "$ROOT/launcher/gpuinfo.py" \
      "$ROOT/launcher/play.c" "$ROOT/launcher/requirements.txt" "$ROOT/launcher/run_launcher.sh" \
      "$ROOT/launcher/build_launcher.sh" "$ROOT/launcher/assets" "$STAGE/launcher/"
# nada de capturas/ampliacoes de texturas no pacote
find "$STAGE/mods" \( -path '*/dumps/*' -o -path '*/replacements/*' \) -type f ! -name '.keep' -delete
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/tools/.venv" "$STAGE/tools/realesrgan"
tar -C "$OUT" -czf "$OUT/MegaManX5-Linux-$VER-linux-x86_64.tar.gz" "MegaManX5-Linux-$VER"
( cd "$OUT" && sha256sum "MegaManX5-Linux-$VER-linux-x86_64.tar.gz" > "MegaManX5-Linux-$VER-linux-x86_64.tar.gz.sha256" )
rm -rf "$STAGE"
ls -la "$OUT"
