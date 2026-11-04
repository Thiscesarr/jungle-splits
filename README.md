# Jungle Splits

Cronômetro estilo F1 para full clear de jungle no Practice Tool do League of Legends, para qualquer campeão.
Fica sobreposto ao jogo e mostra, campo a campo, quanto você ganhou ou perdeu em relação ao seu PB.

- **Roxo**: melhor tempo que você já fez nesse setor (campo)
- **Verde**: mais rápido que o setor do seu PB
- **Vermelho**: mais lento que o setor do seu PB
- **Δ PB**: diferença acumulada para o PB naquele campo (verde = à frente, vermelho = atrás)
- **Embaixo do relógio**: quanto você está ganhando ou perdendo no geral para o PB, ao vivo. Ele já fica
  vermelho no meio de um campo, quando você passa do tempo que tinha no PB naquele ponto.
- **Caixa de veredito** (comparada com o seu PB, não com a meta):
  - `RESET · não bate o PB`: nem repetindo seus melhores setores dá para chegar a menos de `reset_margin`
    segundos (padrão 2) do PB. Pode resetar.
  - `ATRÁS DO PB · ainda dá`: está perdendo, mas ainda dá para recuperar
  - `À FRENTE DO PB`: no ritmo do PB você termina mais rápido que ele
  - `NO RITMO DA META` (roxo): no ritmo atual você bate a meta (`targets`, ex.: 2:50)

## Sons

Para quando você está olhando o clear e não o timer:

| Som | Quando |
|---|---|
| 3 toques + 1 longo | Contagem para os campos nascerem (0:52, 0:53, 0:54 e 0:55) |
| Duas notas subindo | Setor roxo (seu melhor tempo naquele campo) |
| Uma nota | Setor verde (mais rápido que o PB) |
| Uma nota grave | Setor vermelho (mais lento que o PB) |
| Três notas descendo | A run não bate mais o PB (o `RESET` acendeu). Toca uma vez por run |
| Quatro notas subindo | Novo PB |

Na janela de atalhos e sons (`Ctrl+Shift+,`) você escolhe:
- **Estilo**: `suave` (padrão, som de marimba), `grave` (uma oitava abaixo) ou `agudo` (bipes)
- **Volume**
- **▶ Testar sons**: toca todos os avisos em sequência

Para usar sons seus, coloque arquivos `.wav` na pasta `sons/` com os nomes listados em `sons/LEIA-ME.txt`.
Os arquivos que existirem substituem os gerados.

`Ctrl+Shift+-` liga e desliga os sons (o rodapé mostra `som off`). Em `config.json`, `sounds` liga ou desliga
cada tipo de aviso (`countdown`, `splits`, `reset_alert`).

## Como usar

1. Coloque o LoL em **Sem bordas** (Borderless). Em tela cheia exclusiva nenhum overlay aparece.
2. Rode `run.bat` (ou `python main.py`). Só precisa de Python 3.10+, sem pacotes extras.
3. Entre no Practice Tool com qualquer campeão. O overlay detecta o campeão e carrega a rota dele.
4. O timer usa o relógio do jogo e começa quando os campos nascem (0:55).
5. Para começar outra run, use **Reset Game** no Practice Tool.

### Reset Game

O Reset Game do Practice Tool volta o campeão ao início, mas **não zera o relógio do jogo**, e os campos
renascem no tempo normal. O overlay percebe o reset pelo que ele zera: o nível cai para 1, o inventário esvazia
e o ouro volta a 500. A partir daí ele conta com um relógio próprio que começa em 0:00, então os campos nascem
aos 0:55 desse relógio, como numa partida nova. O avançar tempo do Practice Tool funciona normalmente.

Se algum reset passar despercebido, `Ctrl+Shift+[` (**nova run**) zera o relógio do overlay na hora.
Também dá para usar pelo botão direito no modo mover.

### Runas

Embaixo do veredito aparecem seus fragmentos de runa (ex.: `AS/AD/HPS`) e a runa principal, lidos da API do
jogo. Ao lado aparecem os fragmentos do recorde, como a planilha anota nos detalhes. Os seus ficam verdes quando
batem com os do recorde. Siglas: AS velocidade de ataque, AD/AP força adaptativa, AH aceleração de habilidade,
MS velocidade de movimento, HPF vida fixa (+65), HPS vida que escala com o nível (10–180), T&SR tenacidade.

Quer ver antes de abrir o jogo? Rode `demo.bat`: ele simula clears em loop, cada um com uma rota sorteada do campeão (para ver a detecção), e guarda PBs separados dos reais.

## Rotas e recordes

As rotas e tempos vêm da planilha da comunidade
[Jungle Clear Compilation](https://docs.google.com/spreadsheets/d/1jE8bnlnIJnmWv9pnVW9veMKRXJNaaJf5tneQB3xUkbI).
O app baixa a versão online no máximo a cada 12 h (cache em `data/clears.csv`). Se estiver sem internet, usa a
cópia `clears_fallback.csv`. Para cada campeão aparece uma rota por caminho, com o tempo mais rápido da planilha.

- Escolha da rota: entre no modo mover (`Ctrl+Shift+.`), clique com o botão direito no overlay → **Rota**,
  ou use `Ctrl+Shift+]` para passar para a próxima. A escolha fica salva por campeão.
- `preferred_routes` no `config.json` define a rota padrão de cada campeão. Também serve para adicionar uma rota
  que não está na planilha.
- **Detecção automática**: não precisa escolher a rota. Se você fizer um caminho diferente do selecionado, o app
  percebe e troca no meio da run, refazendo os tempos na rota certa. A rota errada não ganha tentativa nem PB.
  O rodapé mostra `ROTA DETECTADA` quando isso acontece, e a rota fica salva para as próximas runs.
  Como funciona: o jogo não diz qual campo morreu, mas cada campo tem uma assinatura:
  - Red, Blue e Gromp são um monstro só, então o ouro entra de uma vez.
  - Wolves, Raptors e Krugs têm vários monstros, então o ouro entra aos poucos.
  - Recall aparece como uma compra na loja.
  - O ouro de cada campo é diferente. O app aprende esses valores a cada run completa (`data/camp_gold.json`).

  O app compara isso com as rotas do campeão na planilha. Por isso a troca acontece no campo em que as rotas se
  separam: Raptors × Red/Blue start no 1º campo, Red × Blue start no 2º (Krugs × Gromp).
  Só são reconhecidas rotas da planilha ou de `preferred_routes`. Escolher a rota na mão no meio da run desliga a
  detecção até o fim dela, e `"auto_detect_route": false` desliga sempre. Red e Blue dão o mesmo ouro, então rotas
  que só diferem por trocar Red e Blue de lugar não dá para separar.
- **Recall** é uma etapa da rota: ela fecha na primeira compra na loja. Se você for direto para o próximo campo
  sem comprar, ela fecha quando o primeiro monstro morrer.

Cada campeão e rota tem PB e melhores setores próprios, em `data/<campeão>/<rota>.json`.

## Atalhos

Abra a janela de atalhos com `Ctrl+Shift+,`, ou com `binds.bat`, ou pelo botão direito no modo mover.
Clique no atalho e aperte a nova combinação.

Os padrões usam Ctrl+Shift com as teclas de símbolo. Elas existem no teclado 60%, o LoL não usa, e quase nenhum
programa usa como atalho global. As teclas abaixo são as de um teclado ABNT2. Num teclado americano, a mesma
tecla física mostra outro símbolo, e o atalho continua funcionando.

| Padrão | Ação |
|---|---|
| Ctrl+Shift+Ç | Fecha o campo atual na mão |
| Ctrl+Shift+; | Desfaz o último campo fechado |
| Ctrl+Shift+[ | Nova run: zera o relógio do overlay agora |
| Ctrl+Shift+] | Próxima rota do campeão |
| Ctrl+Shift+. | Modo mover: arraste o overlay. Aparece um **X** no canto para fechar o app, e o botão direito abre o menu. Aperte de novo para travar |
| Ctrl+Shift+, | Janela de atalhos |
| Ctrl+Shift+- | Liga/desliga os sons |

Os atalhos funcionam com o jogo em foco porque o app lê o estado do teclado direto. Um atalho registrado no
Windows não funcionaria, porque o LoL desliga esse tipo de atalho enquanto está em foco. Em compensação, a tecla
também chega aos outros programas: se alguma combinação já fizer algo no seu PC (como o `Ctrl+Shift+M` do
Discord), troque na janela de atalhos.

## Como um campo é fechado

Cada campo dá **4 CS** (`cs_per_camp`). O app lê o CS do placar (TAB) pela API oficial do jogo
(`https://127.0.0.1:2999`, a mesma que Porofessor/Blitz usam) e fecha o campo no instante em que o 4º CS entra.
Pausas no meio do campo (krugs se dividindo) não fecham nada antes da hora.

Se o jogo não informar o CS um a um (por exemplo, só de 10 em 10), o app percebe sozinho e passa a usar o ouro:

- **Antes da calibração**: o campo fecha quando o ouro dos monstros para de entrar por `quiet_window` segundos.
  O tempo do split é o do último abate.
- **Depois da primeira run completa**: o app aprende o ouro exato de cada campo e fecha no instante em que ele chega.

O rodapé mostra qual modo está ativo (`fecha por CS` ou `fecha por ouro`). Saltos de ouro do Practice Tool e
compras são ignorados. Se algo fechar errado, desfaça e feche na mão.

## Configuração (`config.json`)

- `camp_spawn`: quando os campos nascem (`"0:55"`)
- `targets`: meta por campeão (`{"Lee Sin": "2:50.0"}`). Sem meta, usa o recorde da planilha + `default_target_margin` segundos.
- `preferred_routes`, `fallback_routes` (usada para campeões fora da planilha)
- `cs_per_camp`, `quiet_window`, `auto_update_sheet`
- `hotkeys`: atalhos padrão (os que você muda na janela ficam em `data/ui_state.json`). Teclas de símbolo pela
  posição: `OEM1` (Ç), `OEM2` (;), `OEM5` (]), `OEM6` ([), `COMMA`, `PERIOD`, `MINUS`, `PLUS`
- `reset_margin`: quantos segundos acima do PB o melhor possível pode ficar antes de o veredito pedir reset
- `sounds`: `enabled`, `theme` e `volume` padrão (o que você escolhe na janela fica em `data/ui_state.json`),
  `countdown`, `splits`, `reset_alert`
- `overlay`: posição inicial, opacidade e escala

## Testes

```bash
python -m unittest discover -s tests
```
