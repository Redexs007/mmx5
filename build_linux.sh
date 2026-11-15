#!/usr/bin/env bash
# Compila Mega Man X5 Recompiled para Linux a partir do SEU disco e instala em ./game
# Uso: ./build_linux.sh --disc "/caminho/Mega Man X5 (USA).cue" [--yes] [--jobs N] [--dry-run]
#   --dry-run: so' baixa o codigo e aplica os patches (nao compila nada)
set -euo pipefail
# o launcher empacotado pode vazar libs proprias (PyInstaller) para git/cmake
if [ -n "${LD_LIBRARY_PATH_ORIG+x}" ]; then export LD_LIBRARY_PATH="$LD_LIBRARY_PATH_ORIG"; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$ROOT/project"; OUT="$ROOT/game"; WORK="$ROOT/.build-work"
# Projeto original do X5 (PolyForm Noncommercial) -- baixado do endereco oficial, nao distribuido aqui.
X5_URL="${X5_URL:-https://github.com/mstan/MegaManX5Recomp.git}"
X5_REF="${X5_REF:-c8fde08b77b8c8daae8d0955b6529de79c82d85b}"   # v0.1.0-alpha (2026-09-11)
PSXRECOMP_URL="${PSXRECOMP_URL:-https://github.com/mstan/psxrecomp.git}"
PSXRECOMP_REF="${PSXRECOMP_REF:-379565a6ffc2d399dcb53441dfb0e881ad39b043}"   # 2026-10-15 (tem o mod HD Texturas)
RECOMP_UI_URL="${RECOMP_UI_URL:-https://github.com/mstan/recomp-ui.git}"
RECOMP_UI_REF="${RECOMP_UI_REF:-0546fbcb0126bb14bf88d2128b4fe8a4229570a3}"   # 2026-10-15
DISC=""; JOBS="$(nproc 2>/dev/null || echo 4)"; YES=0; DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --disc) DISC="$2"; shift 2;; --jobs) JOBS="$2"; shift 2;; --yes) YES=1; shift;; --dry-run) DRY=1; shift;;
  -h|--help) sed -n 2,4p "$0"; exit 0;; *) echo "Opcao desconhecida: $1"; exit 2;; esac; done
: "$YES"   # --yes e aceito por compatibilidade (o launcher passa)
log(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die(){ printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$DRY" = 1 ] || { [ -n "$DISC" ] && [ -f "$DISC" ]; } || die "Informe o disco: --disc \"/caminho/arquivo.cue\""
missing=(); for c in git python3 cmake ninja gcc g++ pkg-config; do command -v "$c" >/dev/null || missing+=("$c"); done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Faltam ferramentas: ${missing[*]}"
  echo "Debian/Ubuntu: sudo apt install build-essential git python3 cmake ninja-build pkg-config libgl1-mesa-dev libx11-dev libxext-dev libxcursor-dev libxi-dev libxrandr-dev libxss-dev libwayland-dev libxkbcommon-dev libasound2-dev libpulse-dev libudev-dev libdbus-1-dev"
  echo "Fedora: sudo dnf install gcc-c++ git python3 cmake ninja-build pkgconf-pkg-config mesa-libGL-devel libX11-devel libXext-devel libXcursor-devel libXi-devel libXrandr-devel wayland-devel libxkbcommon-devel alsa-lib-devel pulseaudio-libs-devel systemd-devel"
  exit 1
fi
mkdir -p "$WORK"

# Vulkan (opcional): precisa dos cabecalhos e do glslc SO na compilacao; o jogo carrega o driver sozinho.
HAVE_VK=0
if command -v glslc >/dev/null 2>&1 && { [ -f /usr/include/vulkan/vulkan.h ] || [ -n "${VULKAN_SDK:-}" ]; }; then HAVE_VK=1; fi
if [ "$HAVE_VK" = 0 ]; then
  echo "AVISO: sem glslc/cabecalhos do Vulkan -> o jogo sera compilado SEM Vulkan (OpenGL funciona normalmente)."
  echo "  Para ter Vulkan: Debian/Ubuntu: sudo apt install libvulkan-dev glslc   |   Fedora: sudo dnf install vulkan-headers vulkan-loader-devel glslc"
fi

fetch(){ # dir url ref  -- baixa OU atualiza para o commit pedido
  local d="$1" u="$2" r="$3"
  mkdir -p "$d"
  [ -d "$d/.git" ] || { git -C "$d" init -q; git -C "$d" remote add origin "$u"; }
  [ "$(git -C "$d" rev-parse HEAD 2>/dev/null || true)" = "$r" ] && return 0
  echo "Baixando $u @ ${r:0:8}"
  if git -C "$d" fetch -q --depth 1 origin "$r" 2>/dev/null; then git -C "$d" checkout -q -f FETCH_HEAD
  else echo "AVISO: commit $r indisponivel; usando master de $u"; git -C "$d" fetch -q --depth 1 origin master; git -C "$d" checkout -q -f FETCH_HEAD; fi
}
log "1/7 Baixando o projeto do X5, o framework (psxrecomp + recomp-ui) e aplicando os patches"
fetch "$PROJECT" "$X5_URL" "$X5_REF"
for p in "$ROOT"/patches/*.patch; do
  [ -f "$p" ] || continue
  if git -C "$PROJECT" apply --check -R "$p" >/dev/null 2>&1; then echo "patch ja aplicado: $(basename "$p")"
  elif git -C "$PROJECT" apply --whitespace=nowarn "$p"; then echo "patch aplicado: $(basename "$p")"
  else die "Nao consegui aplicar o patch $(basename "$p") (o projeto original mudou?). Use X5_REF=<commit> ou abra um problema."; fi
done
fetch "$PROJECT/psxrecomp-v4" "$PSXRECOMP_URL" "$PSXRECOMP_REF"
fetch "$PROJECT/recomp-ui" "$RECOMP_UI_URL" "$RECOMP_UI_REF"
FW="$PROJECT/psxrecomp-v4"
NEWREF="$(git -C "$PROJECT" rev-parse HEAD)/$(git -C "$FW" rev-parse HEAD)/$(git -C "$PROJECT/recomp-ui" rev-parse HEAD)"
if [ "$(cat "$PROJECT/.framework-ref" 2>/dev/null || true)" != "$NEWREF" ]; then
  log "Framework mudou: limpando compilacoes antigas (isso e' normal, so' desta vez)"
  rm -rf "$PROJECT/build" "$FW/recompiler/build" "$PROJECT/generated"
  echo "$NEWREF" > "$PROJECT/.framework-ref"
fi
# submodulos do framework (recomp-net e retcomm-rbengine): o runtime precisa dos dois
git -C "$FW" submodule update --init --recursive --depth 1 || git -C "$FW" submodule update --init --recursive

if [ "$DRY" = 1 ]; then
  log "dry-run: codigo baixado e patches aplicados (X5 ${X5_REF:0:8}, framework ${PSXRECOMP_REF:0:8}). Nada foi compilado."
  exit 0
fi

log "2/7 Compilando o recompilador"
cmake -S "$FW/recompiler" -B "$FW/recompiler/build" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$FW/recompiler/build" -j"$JOBS" --target psxrecomp-game
REC="$(find "$FW/recompiler/build" -maxdepth 2 -type f -name psxrecomp-game | head -1)"
[ -x "$REC" ] || die "psxrecomp-game nao foi gerado"

log "3/7 Regenerando a OpenBIOS"
( cd "$FW" && bash tools/regen_bios.sh --config bios/OpenBIOS.toml ) || echo "AVISO: regen_bios falhou; usando a OpenBIOS ja incluida no framework"

log "4/7 Extraindo o executavel do jogo do seu disco"
CUE="$DISC"
case "${DISC,,}" in *.bin|*.iso)
  CUE="$WORK/disc.cue"; printf 'FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' "$DISC" > "$CUE";; esac
mkdir -p "$PROJECT/mmx5"
python3 "$FW/tools/new_project_layout/probe_disc.py" "$CUE" --write-boot-exe "$PROJECT/mmx5" --json-out "$WORK/probe.json"
[ -f "$PROJECT/mmx5/SLUS_013.34" ] || die "Nao achei SLUS_013.34 no disco. E' mesmo Mega Man X5 (USA)?"

log "5/7 Gerando o codigo nativo do jogo"
sed 's#psxrecomp-v4/bios/SCPH1001.toml#psxrecomp-v4/bios/OpenBIOS.toml#' "$PROJECT/game.toml" > "$PROJECT/game.linux.toml"
( cd "$PROJECT" && "$REC" --config game.linux.toml )

log "6/7 Compilando o runtime"
cmake -S "$PROJECT" -B "$PROJECT/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DPSX_NETPLAY=ON
cmake --build "$PROJECT/build" -j"$JOBS"
EXE="$(find "$PROJECT/build" -type f -name mmx5-runtime | head -1)"
[ -x "$EXE" ] || die "mmx5-runtime nao foi gerado"

log "7/7 Instalando em $OUT"
mkdir -p "$OUT"; EXED="$(dirname "$EXE")"
if [ -f "$OUT/mmx5-runtime" ]; then   # guarda a versao antiga, por seguranca
  BK="$OUT/backup-antigo"; mkdir -p "$BK/mods"; cp -f "$OUT/mmx5-runtime" "$BK/mmx5-runtime"
  for c in bundled packages; do [ -d "$OUT/mods/$c" ] && { rm -rf "$BK/mods/$c"; mv "$OUT/mods/$c" "$BK/mods/$c"; }; done
fi
cp -f "$EXE" "$OUT/mmx5-runtime"
for d in mods bios assets licenses overlay_toolchain; do [ -d "$EXED/$d" ] && cp -a "$EXED/$d" "$OUT/" || true; done
[ -d "$OUT/bios" ] || { [ -d "$FW/bios" ] && cp -a "$FW/bios" "$OUT/bios"; } || true
# game.toml para Linux (py -3 -> python3, sem .exe) + ferramentas do auto-compilador de overlays
sed -e 's#py -3#python3#' -e 's#psxrecomp-game\.exe#psxrecomp-game#' -e 's#psxrecomp-v4/bios/SCPH1001.toml#psxrecomp-v4/bios/OpenBIOS.toml#' "$PROJECT/game.toml" > "$OUT/game.toml"
mkdir -p "$OUT/psxrecomp-v4/tools" "$OUT/psxrecomp-v4/recompiler/build" "$OUT/psxrecomp-v4/runtime"
cp -a "$FW/tools/compile_overlays.py" "$OUT/psxrecomp-v4/tools/" 2>/dev/null || true
cp -a "$REC" "$OUT/psxrecomp-v4/recompiler/build/" ; cp -a "$FW/runtime/include" "$OUT/psxrecomp-v4/runtime/" 2>/dev/null || true
if [ "$HAVE_VK" = 1 ] && ! grep -q '^offer_vulkan' "$OUT/game.toml"; then   # mostra o Vulkan no launcher
  awk '{print} /^\[video\]/ && !d {print "offer_vulkan = true"; d=1}' "$OUT/game.toml" > "$OUT/game.toml.tmp" && mv "$OUT/game.toml.tmp" "$OUT/game.toml"
fi
cp -an "$PROJECT/packaging/release/input.ini" "$OUT/input.ini" 2>/dev/null || true
cp -a "$PROJECT/mmx5" "$OUT/mmx5" 2>/dev/null || true
chmod +x "$OUT/mmx5-runtime"
# grava o disco em settings.toml se ainda nao houver
if ! grep -q '^\[disc\]' "$OUT/settings.toml" 2>/dev/null; then printf '\n[disc]\npath = "%s"\n' "$DISC" >> "$OUT/settings.toml"; fi
mkdir -p "$ROOT/mods"
[ "$HAVE_VK" = 1 ] && echo "Vulkan: incluido nesta compilacao." || echo "Vulkan: NAO incluido (veja o aviso no inicio)."
log "Pronto! Abra ./MegaManX5-Launcher (ou ./MegaManX5-Play para jogar direto)."
