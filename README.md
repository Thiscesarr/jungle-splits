# Jungle Splits

Cronômetro estilo F1 para full clear de jungle no Practice Tool do League of Legends.
Fica sobreposto ao jogo e mostra, campo a campo, quanto você ganhou ou perdeu em relação ao seu PB.

- **Roxo**: melhor tempo que você já fez nesse setor (campo)
- **Verde**: mais rápido que o setor do seu PB
- **Vermelho**: mais lento que o setor do seu PB
- **Δ PB**: diferença acumulada para o PB naquele campo (verde = à frente, vermelho = atrás)
- **Caixa de veredito**:
  - `RESET`: nem somando seus melhores setores restantes dá para bater a meta. Pode resetar.
  - `AINDA DÁ`: só bate a meta se os próximos setores saírem melhores que o PB
  - `NO RITMO DA META`: no ritmo do PB você termina abaixo da meta

## Como usar

1. Coloque o LoL em **Sem bordas** (Borderless). Em tela cheia exclusiva nenhum overlay aparece.
2. Rode `run.bat` (ou `python main.py`). Só precisa de Python 3.10+, sem pacotes extras.
3. Entre no Practice Tool. O timer usa o relógio do jogo e começa quando os campos nascem (1:30).
4. Cada campo fecha sozinho: o app percebe o ouro dos monstros pela API oficial do jogo
   (`https://127.0.0.1:2999`, a mesma que Porofessor/Blitz usam).
5. Para começar outra run, use **Reset Game** no Practice Tool: quando o relógio volta, a run nova começa.

Quer ver antes de abrir o jogo? Rode `demo.bat`: ele simula clears em loop, com PBs separados dos reais.

## Atalhos (editáveis em `config.json`)

| Tecla | Ação |
|---|---|
| F7 | Split manual (fecha o campo atual agora) |
| F8 | Desfaz o último split (se o auto-split fechou o campo cedo demais) |
| F9 | Descarta a run atual |
| F10 | Modo mover: destrava o overlay para arrastar; aperte de novo para travar. Botão direito fecha |
| F6 | Troca de rota |
| Ctrl+Alt+F10 | Fecha o app |

Teclas aceitas: `F1`–`F24`, `NUM0`–`NUM9`, `NUMADD`, `NUMSUB`, `NUMMUL`, `NUMDIV`, letras e números,
com `ctrl+`, `alt+`, `shift+`. Essas teclas deixam de chegar ao jogo enquanto o app está aberto.

## Configuração (`config.json`)

- `target`: sua meta (`"2:50.0"`)
- `routes`: rotas e a ordem dos campos. Os nomes `Red`, `Blue`, `Gromp`, `Wolves`, `Raptors`, `Krugs` e
  `Scuttle` têm valor de ouro padrão; outros nomes funcionam, só demoram uma run a mais para calibrar.
  Mudar a ordem de uma rota zera os tempos dela (o arquivo antigo vira backup em `data/`).
- `quiet_window`: segundos sem ouro novo para considerar o campo terminado antes da calibração.
- `overlay`: posição inicial, opacidade e escala.

## Como o auto-split funciona

O ouro passivo é ~2 g/s; qualquer salto acima disso numa leitura é ouro de monstro.

- **Antes da calibração**: o campo fecha quando para de chegar ouro por `quiet_window` segundos
  (você está andando para o próximo campo). O tempo do split é o do último abate, não o do fim da espera.
- **Depois da primeira run completa**: o app aprende o ouro exato de cada campo e fecha o campo no instante
  em que esse ouro chega.

Saltos grandes (botão de ouro do Practice Tool, vender item) e compras são ignorados.
Se algo fechar errado, F8 desfaz e F7 fecha na mão.

Os dados ficam em `data/<rota>.json`: PB, melhores setores, ouro aprendido e histórico de runs completas.

## Testes

```bash
python -m unittest discover -s tests
```
