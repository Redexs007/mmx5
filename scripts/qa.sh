#!/usr/bin/env bash
# Verificacoes automaticas do projeto.  Uso: scripts/qa.sh [--online]
#   --online: tambem baixa o projeto/framework e aplica os patches (build_linux.sh --dry-run)
cd "$(dirname "$0")/.." || exit 2
ROOT="$PWD"; PY="${PYTHON:-python3}"; fail=0
ok(){ printf '  \033[32mOK\033[0m   %s\n' "$1"; }
bad(){ printf '  \033[31mFALHA\033[0m %s\n' "$1"; fail=1; }

echo "1) Python compila"
for f in launcher/*.py tools/*.py tests/*.py; do "$PY" -m py_compile "$f" 2>/dev/null && ok "$f" || bad "$f"; done
echo "2) Shell: sintaxe"
for f in build_linux.sh launcher/*.sh tools/*.sh scripts/*.sh; do bash -n "$f" 2>/dev/null && ok "$f" || bad "$f"; done
if command -v shellcheck >/dev/null; then
  shellcheck -S error build_linux.sh scripts/*.sh launcher/*.sh tools/*.sh >/dev/null 2>&1 && ok "shellcheck (erros)" || bad "shellcheck"
else echo "  (shellcheck nao instalado: pulando)"; fi
echo "3) mod.json validos"
for f in mods/*/mod.json; do "$PY" -c "import json,sys; json.load(open('$f'))" 2>/dev/null && ok "$f" || bad "$f"; done
echo "4) Sem arte de terceiros / arquivos grandes no repositorio"
big=$(find launcher/assets mods -name '*.png' -size +600k 2>/dev/null)
[ -z "$big" ] && ok "nenhuma imagem > 600 KB (arte pessoal fica em launcher_art/, fora do repositorio)" || bad "imagens grandes: $big"
[ ! -d launcher_art ] || echo "  (aviso: existe launcher_art/ local; esta no .gitignore)"
echo "5) Testes unitarios"
QT_QPA_PLATFORM=offscreen "$PY" -m unittest discover -s tests >/tmp/mmx5_ut.log 2>&1 && ok "$(tail -3 /tmp/mmx5_ut.log | head -1)" || { bad "unittest"; tail -15 /tmp/mmx5_ut.log; }
echo "6) Launcher abre e troca de aba (offscreen)"
tmp=$(mktemp -d)
QT_QPA_PLATFORM=offscreen MMX5_GAME_DIR="$tmp/g" XDG_CONFIG_HOME="$tmp/c" MMX5_SELFTEST_SHOT="$tmp/s" timeout 90 "$PY" launcher/launcher.py >/dev/null 2>&1
n=$(ls "$tmp"/s_* 2>/dev/null | wc -l); [ "$n" -ge 5 ] && ok "$n capturas de tela geradas" || bad "so $n capturas"
rm -rf "$tmp"
if [ "$1" = "--online" ]; then
  echo "7) Download do projeto + patches (build_linux.sh --dry-run)"
  d=$(mktemp -d); cp -r "$ROOT/." "$d/"; rm -rf "$d/project" "$d/.git"
  ( cd "$d" && ./build_linux.sh --dry-run >/tmp/mmx5_dry.log 2>&1 ) && ok "dry-run" || { bad "dry-run"; tail -8 /tmp/mmx5_dry.log; }
  rm -rf "$d"
fi
echo; [ $fail = 0 ] && echo "TUDO OK" || echo "HA FALHAS"; exit $fail
