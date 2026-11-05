## Fixed

- **Camps that never closed** ([#1](https://github.com/Thiscesarr/jungle-splits/issues/1)): the wolves pay 85 gold,
  not the 105 the app expected, so they never closed and every later split shifted by one camp (Master Yi's
  wolves never recorded; Cho'Gath's Krugs only registered after another camp). Every camp's gold is now measured
  monster by monster from real clears: Blue/Red 90, Gromp 80, Wolves 85, Raptors 75, Krugs 109.
- **The jungle pet's bonus treat** (20 gold, once a minute from about 2:31) no longer counts as camp gold. It could
  make Red look like Krugs and swap them in route detection.
- **Clicks pass through the overlay again** (broken since the opacity setting in 1.0.1).

## New

- **Splits show instantly**: a camp closes the moment its last monster dies, not 2–5 s later.
- **Records tab** in Settings: delete a route's PB and attempts, for example after a clear with teleports or extra
  smites.
- **Minimize**: in move mode, the – button next to the ✕ hides the overlay; the move hotkey or the tray icon brings
  it back.

1.0.2 updates itself: click **Update to version 1.0.3** in the overlay or the tray icon. Older versions: run this
installer over them once. Your PBs are kept.

---

**PT-BR:** lobos e outros camps que não fechavam (#1) corrigidos com o ouro exato de cada camp; o petisco do pet não
conta mais como ouro de camp; os cliques voltam a atravessar o overlay; os splits aparecem na hora; nova aba
Recordes para apagar PBs; botão de minimizar no modo mover. Quem tem a 1.0.2 atualiza pelo próprio app.
