## New

- **New look**: the overlay is now a glass panel with rounded corners, a soft shadow and sharper numbers. Settings,
  the welcome screen and the pop-ups were redesigned to match, and the tray menu follows Windows' dark mode.
- **Show only what you want**: Settings → **Overlay** has three presets (*Clock only*, *Clock and camps*,
  *Everything*), or turn each part on and off: champion and record, difference to PB, PB/target line, camps,
  verdict, rune shards, record video and footer. With only the clock, the overlay shrinks to a small panel.
- **Live preview**: size, opacity and the parts shown change on the overlay as you pick them. Opacity now fades
  only the background, so the numbers stay sharp at any setting.
- **Click the tray icon** to bring a minimized overlay back, together with Settings.

## Changed

- **Practice Tool only**: in a ranked, normal or ARAM game the overlay hides itself and times nothing, then comes
  back on its own when the game ends. Before, a laner's gold could be saved as a jungle clear. If that happened to
  you, delete those runs in Settings → **Records**.
- **Lighter on your FPS**: the overlay is redrawn only when something on it changes. Waiting for a game it uses
  about 1% of one CPU core (it was about 13%), and about 3% during a clear.
- **Sharper icon** on the desktop, the taskbar and the tray.

## Security

- Links from the community sheet are only opened when they are https links to a video site.
- Data from the game's local API is checked before use, and a damaged settings file no longer keeps the app from
  opening.
- Releases are built from dependencies pinned by hash, and the job that publishes runs no project code.

1.0.2 and later update themselves: click **Update now** in the pop-up, or **Update to version 1.1.0** in the
overlay or the tray icon. Older versions: run this installer over them once. Your PBs are kept.

---

**PT-BR:** visual novo (overlay de vidro, Configurações redesenhadas), opção de escolher o que o overlay mostra (só
o relógio, relógio e campos, ou tudo), tamanho e opacidade mudando na hora, e o app agora só funciona no Practice
Tool: em ranqueada ou normal ele se esconde e não cronometra nada. Também ficou mais leve (cerca de 1% de um núcleo
da CPU parado) e ganhou correções de segurança. Quem tem a 1.0.2 ou mais nova atualiza pelo próprio app.
