# Pasta de mods

Cada **pasta** aqui dentro com um arquivo **`mod.json`** vira um mod na aba **MODS** do launcher.
Depois de mexer em qualquer arquivo, clique em **Recarregar** (na aba MODS).

```
mods/
  hd-texturas/        ← exemplo funcional: texturas (capturar → ampliar → carregar)
    mod.json
    cover.png         ← capa que aparece na lista (opcional)
    config.yaml       ← liga a "captura ampla" (necessário no X5; não apague)
    dumps/            ← o jogo grava aqui as texturas ORIGINAIS capturadas
    replacements/     ← você coloca aqui as texturas NOVAS (mesmo nome de arquivo!)
  exemplo-bezel/      ← exemplo funcional: moldura de tela
    mod.json
    bezel.png
  exemplo-patch/      ← MODELO de mod que troca bytes do jogo (não é aplicado)
    mod.json
```

Esta pasta é do **launcher** (fica ao lado do `MegaManX5-Launcher`). A pasta `game/mods/` é do jogo
(o launcher escreve lá a seleção em `state.toml`) — não precisa mexer nela.

---

## Seu primeiro mod em 5 minutos (texturas)

1. Abra a aba **MODS** → **HD Texturas**. Ligue **Capturar texturas originais**
   (isso liga o mod sozinho — confira que o quadro da lista diz *ATIVADO*).
2. Clique em **JOGAR**, jogue uns minutos e **feche o jogo normalmente** (a captura só é gravada ao sair).
3. Abra **Pasta dumps**. Os PNGs estão lá (nomes como `texupload-…png`).
4. Escolha um PNG, abra num editor de imagem (GIMP, Krita…), pinte/redesenhe e salve em
   **`replacements/` com exatamente o mesmo nome**. Pode ser maior que o original (2x, 4x…).
   Mantenha o fundo transparente onde era transparente.
5. Volte ao launcher, deixe **Carregar texturas HD** ligado e clique em **JOGAR**. Onde a textura aparece,
   você vê a sua versão.

Para ampliar muitas texturas de uma vez, use **Ampliar capturas…** (IA ou pixel art).

> Só funciona no renderizador **OpenGL**. As opções valem na próxima vez que você clicar em JOGAR.

### A captura não aparece? (confira nesta ordem)
0. **Causa mais comum: jogo compilado com framework antigo.** O mod de texturas HD só existe no framework de
   6/out/2026 em diante. Se na aba MODS → HD Texturas aparecer em vermelho que o jogo "foi compilado com uma versão
   antiga do framework", o plugin simplesmente não existe no seu jogo: clique em **Atualizar o jogo (recompilar)**
   (ou rode `./build_linux.sh --disc "…cue"`). Demora como a primeira compilação; o jogo antigo fica guardado em
   `game/backup-antigo/` e só é trocado se a compilação terminar bem.
1. **Versão do launcher:** no canto superior direito deve estar **v1.0.0** ou maior. Se aparecer uma versão menor você ainda
   está com o launcher antigo — copie o `MegaManX5-Launcher` novo por cima.
2. **O mod precisa estar LIGADO.** O sintoma clássico é: o log do jogo não tem nenhuma linha "HD textures". Isso
   acontece quando o mod está desligado no `state.toml`, mesmo com "Capturar" marcado. Na aba MODS → HD Texturas,
   a linha **"state.toml no disco"** diz se está LIGADO ou DESLIGADO. Ao clicar em JOGAR o launcher também avisa
   e oferece ligar.
3. Depois de jogar, a aba JOGAR mostra **"Última partida: texturas ATIVAS … N arquivo(s) em dumps/"**
   (o launcher agora fica aberto enquanto você joga para poder mostrar isso).
4. **`config.yaml` (captura ampla):** sem ele o runtime só salva texturas de 16x16 ou mais que passaram por um
   "upload" rastreado, e o X5 (2D, sprites pequenos) pode não gerar nada. `hd-texturas/` já vem com ele
   (chave **Captura ampla (recomendado)**). Não apague.
5. Feche o jogo normalmente (janela/menu), só no **OpenGL**.
6. Se ainda não funcionar, me mande: a linha "state.toml no disco", as linhas "HD textures" de
   **CONFIG → Ver log do último jogo** e o conteúdo de `game/mods/state.toml`.

---

## Formato do `mod.json`

Campos comuns:

| campo         | obrigatório | o que é                                                         |
|---------------|-------------|-----------------------------------------------------------------|
| `type`        | sim         | `"texture-pack"`, `"bezel"` ou `"patch"`                        |
| `name`        | não         | nome na lista (padrão: nome da pasta)                           |
| `version`     | não         | ex. `"1.0.0"`                                                   |
| `author`      | não         | seu nome                                                        |
| `description` | não         | texto que aparece nos detalhes                                  |
| `cover`       | não         | imagem da capa (padrão `cover.png`)                             |

### `type: "texture-pack"`
Usa a própria pasta do mod: `replacements/` (texturas novas) e `dumps/` (capturas). Só **um** pacote de
texturas fica ativo por vez (ligar um desliga o outro).

### `type: "bezel"`
```json
{ "type": "bezel", "name": "Minha moldura", "artwork": "bezel.png" }
```
`artwork` é uma imagem PNG/JPG (1920x1080 é bom). Ela é desenhada atrás do jogo, nas bordas que sobram quando
a tela não fica toda preenchida (ex.: jogo em 4:3 num monitor largo — desligue o mod Widescreen para ver).

### `type: "patch"` (avançado — muda bytes do jogo)
```json
{
  "type": "patch",
  "name": "Meu patch",
  "options": [
    { "id": "ativo", "label": "Ativo", "type": "boolean", "default": true },
    { "id": "modo",  "label": "Modo",  "type": "choice", "default": "a",
      "choices": [ { "value": "a", "label": "A" }, { "value": "b", "label": "B" } ] },
    { "id": "n", "label": "Número", "type": "integer", "min": 1, "max": 9, "default": 3 }
  ],
  "patches": [
    { "address": "0x80010000", "expected": "02 00 02 24", "replace": "09 00 02 24",
      "when": { "modo": "a" } }
  ]
}
```
- `address`: endereço do executável do jogo na memória (`0x80010000` a `0x801FFFFF`).
- `expected`: os bytes que **têm** que estar lá hoje. O framework confere antes de aplicar.
- `replace`: os bytes novos (mesmo tamanho de `expected`).
- `when` (opcional): só aplica se a opção tiver esse valor (`true`/`false` para boolean).
- Tipos de opção: `boolean`, `choice`, `integer` (`min`/`max`; `step` opcional).
- O launcher converte este JSON em um pacote do framework em `game/mods/installed/user.<nome>/`.
- Mod com `"template": true` é só um **modelo** (aparece mas não é aplicado). Apague essa linha quando
  tiver valores reais.

Como achar endereços/bytes: com o Ghidra (o projeto tem `seeds/ghidra_funcs.txt`) ou com códigos de
GameShark/Action Replay convertidos. É coisa de quem entende de MIPS — comece pelas texturas.

⚠ Se o `expected` não bater com o jogo, o framework **recusa** o patch e o jogo pode não abrir. Se isso
acontecer: abra o launcher, desligue o mod e jogue de novo.

---

## Criar um mod do zero
Aba MODS → **Novo mod**: escolha o tipo, dê um nome, e o launcher cria a pasta com um `mod.json` de modelo
(e abre a pasta para você).

## Erros
Um mod com `mod.json` quebrado aparece na lista com **⚠ COM ERRO** e a explicação nos detalhes
(vírgula faltando, tipo desconhecido, imagem que não existe…).
