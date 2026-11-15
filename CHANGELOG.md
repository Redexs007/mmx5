# Changelog

## 1.0.0
Primeira versão pública.

- Launcher (JOGAR / CONFIG / MODS / INTERFACE) com tema personalizável e transições; arte neutra por padrão, arte própria opcional em `launcher_art/`.
- `build_linux.sh`: baixa o projeto do X5 (commit fixado) e o framework de 15/out/2026, aplica patches, compila e instala em `game/`; guarda o jogo anterior em `game/backup-antigo/`; `--dry-run`.
- Gráficos: resolução interna até 8K, xBR/bilinear, FMV, V-Sync, CRT; **escolha de renderizador (OpenGL / Vulkan experimental / software) e de placa de vídeo** com botões de teste.
- Controle: assistente de mapeamento para controles genéricos, teste ao vivo, seleção do Jogador 1.
- Mods: Widescreen (nova opção de proporção: 16:9, 16:10, 3:2, seguir a janela), Interpolação de quadros, Limite de FPS, HD Texturas (captura ampla + ampliação por IA), bezel, patches de bytes; pasta `mods/` funcional com exemplos.
- Diagnóstico: relatório para issues, log do último jogo, resumo da última partida, aviso de mod desligado.
- Testes automáticos (`tests/`) e `scripts/qa.sh`; workflow de release no GitHub Actions.
