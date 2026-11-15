# Avisos de terceiros

Este repositório **não contém** o jogo, a BIOS de console retail, imagens de disco nem o código-fonte dos projetos
abaixo. O `build_linux.sh` baixa o código dos repositórios originais na máquina de quem compila.

## Projetos baixados na hora do build (licença própria)

| Projeto | Origem | Licença |
|---|---|---|
| MegaManX5Recomp (projeto do X5) | https://github.com/mstan/MegaManX5Recomp (commit fixado no `build_linux.sh`) | PolyForm Noncommercial 1.0.0 — © 2026 Matthew Stanley |
| psxrecomp (framework) | https://github.com/mstan/psxrecomp | PolyForm Noncommercial 1.0.0 |
| recomp-ui | https://github.com/mstan/recomp-ui | PolyForm Noncommercial 1.0.0 |
| recomp-net, retcomm-rbengine, SDL3, libchdr … | submódulos / dependências do framework | licenças próprias (veja cada repositório) |

Consequência prática: **o uso do jogo compilado é restrito a fins não comerciais**, conforme essas licenças
(https://polyformproject.org/licenses/noncommercial/1.0.0). Este repositório adiciona um patch pequeno
(`patches/0001-widescreen-aspect-option.patch`) sobre o projeto do X5; ele só é aplicado localmente, na pasta do build.

## Incluído neste repositório

| Componente | Licença |
|---|---|
| Fontes Chakra Petch, Share Tech Mono, Silkscreen (`launcher/assets/fonts/`) | SIL Open Font License 1.1 (arquivos `OFL-*.txt` ao lado das fontes) |
| Arte neutra do launcher, capas dos mods, ícone | criados para este projeto (MIT, como o resto do repositório) |

## Dependências do launcher

| Componente | Licença (conforme publicada pelos autores) |
|---|---|
| PySide6 / Qt for Python | LGPLv3 / GPLv3 / comercial |
| PyInstaller (usado só para gerar o binário) | GPLv2 com exceção para o bootloader |
| Pillow, NumPy (ferramenta de ampliação de texturas) | HPND / BSD |
| Real-ESRGAN ncnn Vulkan (baixado sob demanda pela ferramenta de texturas) | BSD-3-Clause |

O binário do launcher é gerado com PyInstaller a partir do código-fonte desta pasta (`launcher/`); quem preferir pode
rodar `launcher/run_launcher.sh`, que usa o PySide6 instalado pelo `pip` em vez do binário.
Confira as licenças atuais em cada projeto: este arquivo é informativo e não é aconselhamento jurídico.

## Marcas e arte

Mega Man e Mega Man X são marcas e propriedade da Capcom. Este projeto é **não oficial** e não é afiliado nem
endossado pela Capcom. **Nenhuma arte, som ou dado do jogo é distribuído aqui.** O launcher vem com arte neutra; se
você quiser usar imagens suas, coloque-as em `launcher_art/` (veja o README) — elas ficam só na sua máquina.
