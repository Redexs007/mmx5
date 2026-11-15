# Problemas conhecidos (1.0.0)

## Widescreen (experimental)
O widescreen do X5 é feito por *hooks* no código gerado do jogo (alarga o fundo 2D, o HUD e a ativação de objetos).
Funciona muito bem na maior parte do jogo, mas o jogo foi desenhado para 4:3, então aparecem alguns detalhes:

| Onde | O que se vê | Explicação provável |
|---|---|---|
| Fase de introdução, no começo | faixa preta no canto esquerdo; some ao avançar | o mapa não tem nada à esquerda do ponto inicial; a visão larga mostra além do começo da fase |
| Fase do Tidal Whale | "quadrado" mais claro nas bordas esquerda e direita | algo é desenhado só dentro da área 4:3 original (camada/efeito) e não acompanha a largura nova |
| Alguns diálogos | o quadro do personagem aparece fora do lugar e dá para vê-lo entrar em cena | os retratos deslizam de fora da tela 4:3; na tela larga a entrada fica visível |

**Alternativas:** na aba MODS → Widescreen há a opção **Proporção da tela** (16:9, 16:10, 3:2 ou *seguir a janela*). Proporções
menores mostram menos das bordas e escondem parte dessas falhas. Também dá para desligar o widescreen para jogar em 4:3 original.
Esses itens vêm do mod do projeto original; correções de verdade exigem alterar os *hooks* e testar com o jogo rodando, e
devem ser reportadas também em https://github.com/mstan/MegaManX5Recomp (com fase/cena e print).

## HD Texturas
- Precisa de OpenGL e de um jogo compilado com o framework de 15/out/2026 ou mais novo (o botão *Atualizar o jogo* resolve).
- A captura só é gravada ao **fechar o jogo normalmente**. O X5 é 2D e usa sprites pequenos: o `config.yaml` do pacote
  (“captura ampla”) é necessário para que apareçam arquivos em `dumps/`.
- A ampliação por IA suaviza e melhora bordas, mas não redesenha os sprites; o resultado varia por textura.

## Vulkan
Experimental e opcional. O launcher só mostra a opção se o sistema tem loader+driver Vulkan, e o jogo só terá o backend se foi
compilado com `libvulkan-dev` e `glslc`. Se o jogo cair para OpenGL, a aba JOGAR avisa na linha "Última partida".

## Escolha de GPU
Em notebooks com duas placas, escolha a dedicada em CONFIG → Placa de vídeo e use **Testar OpenGL** para ver qual placa o
sistema usa. Com GPU integrada AMD/Intel o uso de GPU do jogo costuma ser baixo (é um jogo 2D de 60 FPS).

## Controle
O jogo usa um dispositivo por jogador (padrão do runtime: teclado). O launcher grava a escolha em `settings.toml`; o
`MegaManX5-Play` usa a última escolha gravada. Controles sem mapeamento SDL precisam do assistente *Configurar controle*.

## Outros
- O launcher e o jogo só foram testados em Linux x86_64 (X11/Wayland).
- Mods de patch de bytes exigem endereços reais; um `expected` errado faz o framework recusar o patch e o jogo pode não abrir
  (desligue o mod no launcher).
