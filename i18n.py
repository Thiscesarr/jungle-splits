"""Interface strings in Portuguese and English."""
from __future__ import annotations

import ctypes

LANGUAGES = {"pt": "Português (Brasil)", "en": "English"}

STRINGS: dict[str, dict[str, str]] = {
    # Overlay
    "record_line": {"pt": "RECORDE {time} · {player} · {patch}", "en": "RECORD {time} · {player} · {patch}"},
    "custom_route": {"pt": "ROTA PERSONALIZADA", "en": "CUSTOM ROUTE"},
    "smite_tag": {"pt": "{n} SMITE", "en": "{n} SMITE"},
    "info_line": {"pt": "PB {pb}    META {target}", "en": "PB {pb}    TARGET {target}"},
    "sum_of_best": {"pt": "    SOMA MELHORES {time}", "en": "    SUM OF BEST {time}"},
    "col_camp": {"pt": "CAMPO", "en": "CAMP"},
    "col_time": {"pt": "TEMPO", "en": "TIME"},
    "col_delta": {"pt": "Δ PB", "en": "Δ PB"},
    "col_sector": {"pt": "SETOR", "en": "SECTOR"},
    "waiting_game": {"pt": "Aguardando o Practice Tool", "en": "Waiting for the Practice Tool"},
    "spawn_in": {"pt": "Campos nascem em {time}", "en": "Camps spawn in {time}"},
    "abandoned": {"pt": "Run descartada · Reset Game para outra", "en": "Run discarded · Reset Game for another"},
    "new_pb": {"pt": "NOVO PB!  {time}", "en": "NEW PB!  {time}"},
    "target_hit": {"pt": "META BATIDA  {time}", "en": "TARGET BEATEN  {time}"},
    "final": {"pt": "FINAL {time}  ({delta} PB)", "en": "FINAL {time}  ({delta} PB)"},
    "v_reset": {"pt": "RESET · não bate o PB (melhor possível {time})",
                "en": "RESET · can't beat the PB (best possible {time})"},
    "v_on_target": {"pt": "NO RITMO DA META · projeção {time}", "en": "ON TARGET PACE · projected {time}"},
    "v_ahead": {"pt": "À FRENTE DO PB · projeção {time}", "en": "AHEAD OF PB · projected {time}"},
    "v_behind": {"pt": "ATRÁS DO PB · ainda dá{best}", "en": "BEHIND PB · still possible{best}"},
    "best_suffix": {"pt": " · melhor possível {time}", "en": " · best possible {time}"},
    "first_run_route": {"pt": "Primeira run da rota · gravando referência",
                        "en": "First run on this route · recording reference"},
    "runes": {"pt": "RUNAS {runes}", "en": "RUNES {runes}"},
    "record_shards": {"pt": "recorde {shards}", "en": "record {shards}"},
    "video": {"pt": "▶ Vídeo do recorde · {player}", "en": "▶ Record video · {player}"},
    "video_click": {"pt": "▶ Clique para abrir o vídeo de {player}", "en": "▶ Click to open {player}'s video"},
    "footer_stats": {"pt": "Tentativas {attempts} · Completas {completed} · fecha por {mode}",
                     "en": "Attempts {attempts} · Finished {completed} · splits by {mode}"},
    "mode_cs": {"pt": "CS", "en": "CS"},
    "mode_gold": {"pt": "ouro", "en": "gold"},
    "mode_both": {"pt": "CS/ouro", "en": "CS/gold"},
    "sound_off_tag": {"pt": " · som off", "en": " · sound off"},
    "footer_offline": {"pt": "Configurações: {key} ou o ícone na bandeja", "en": "Settings: {key} or the tray icon"},
    "move_bar": {"pt": "ARRASTE PARA MOVER", "en": "DRAG TO MOVE"},
    "move_footer": {"pt": "Botão direito: menu · – minimiza ({key} mostra) · ✕ fecha",
                    "en": "Right-click: menu · – minimizes ({key} shows it) · ✕ quits"},
    "notice_route": {"pt": "ROTA DETECTADA: {path}", "en": "ROUTE DETECTED: {path}"},
    "notice_sound_on": {"pt": "SOM LIGADO", "en": "SOUND ON"},
    "notice_sound_off": {"pt": "SOM DESLIGADO", "en": "SOUND OFF"},
    "notice_smites": {"pt": "MODO {n} SMITE · {champion}", "en": "{n} SMITE MODE · {champion}"},
    # Menus (right-click and tray)
    "menu_route": {"pt": "Rota ({champion})", "en": "Route ({champion})"},
    "menu_smites": {"pt": "Smites ({champion})", "en": "Smites ({champion})"},
    "menu_smite_n": {"pt": "{n} smite", "en": "{n} smite"},
    "menu_new_run": {"pt": "Nova run (zera o relógio agora)", "en": "New run (restart the clock now)"},
    "menu_video": {"pt": "Abrir vídeo do recorde", "en": "Open record video"},
    "menu_settings": {"pt": "Configurações…", "en": "Settings…"},
    "menu_move": {"pt": "Mover overlay", "en": "Move overlay"},
    "menu_lock": {"pt": "Travar posição", "en": "Lock position"},
    "menu_show": {"pt": "Mostrar overlay", "en": "Show overlay"},
    "menu_sound": {"pt": "Sons", "en": "Sounds"},
    "menu_quit": {"pt": "Fechar Jungle Splits", "en": "Quit Jungle Splits"},
    "already_running": {"pt": "O Jungle Splits já está aberto (veja o ícone na bandeja, perto do relógio).",
                        "en": "Jungle Splits is already running (look for its icon in the tray, by the clock)."},
    # Hotkey actions
    "act_split": {"pt": "Fechar campo na mão", "en": "Close camp manually"},
    "act_undo": {"pt": "Desfazer último campo", "en": "Undo last camp"},
    "act_reset": {"pt": "Nova run (zera o relógio)", "en": "New run (restart the clock)"},
    "act_next_route": {"pt": "Próxima rota do campeão", "en": "Next route for the champion"},
    "act_smites": {"pt": "Alternar 1 / 2 smites", "en": "Toggle 1 / 2 smites"},
    "act_move": {"pt": "Mover overlay (liga/desliga)", "en": "Move overlay (on/off)"},
    "act_settings": {"pt": "Abrir configurações", "en": "Open settings"},
    "act_mute": {"pt": "Ligar/desligar sons", "en": "Sound on/off"},
    "act_quit": {"pt": "Fechar o app", "en": "Quit the app"},
    # Settings window
    "settings_title": {"pt": "Jungle Splits · Configurações", "en": "Jungle Splits · Settings"},
    "tab_general": {"pt": "Geral", "en": "General"},
    "tab_hotkeys": {"pt": "Atalhos", "en": "Hotkeys"},
    "tab_sounds": {"pt": "Sons", "en": "Sounds"},
    "tab_about": {"pt": "Sobre", "en": "About"},
    "language": {"pt": "Idioma", "en": "Language"},
    "target_for": {"pt": "Meta para {champion}", "en": "Target for {champion}"},
    "target_hint": {"pt": "Formato m:ss (ex.: 2:50). Vazio = recorde da rota + 5 s.",
                    "en": "Format m:ss (e.g. 2:50). Empty = route record + 5 s."},
    "target_invalid": {"pt": "Meta inválida: use m:ss, por exemplo 2:50.", "en": "Invalid target: use m:ss, e.g. 2:50."},
    "smites_for": {"pt": "Smites de {champion}", "en": "Smites for {champion}"},
    "smites_hint": {"pt": "Fica salvo para este campeão. Os PBs de 1 e 2 smites são separados.",
                    "en": "Saved for this champion. 1- and 2-smite PBs are kept apart."},
    "overlay_size": {"pt": "Tamanho do overlay", "en": "Overlay size"},
    "overlay_opacity": {"pt": "Opacidade do overlay", "en": "Overlay opacity"},
    "opacity_hint": {"pt": "Menos = mais transparente. Muda na hora, enquanto você arrasta.",
                     "en": "Lower = more see-through. Changes live as you drag."},
    "hotkeys_hint": {"pt": "Clique em um atalho e aperte a nova combinação (Esc cancela).",
                     "en": "Click a hotkey and press the new combination (Esc cancels)."},
    "press_keys": {"pt": "aperte as teclas…", "en": "press the keys…"},
    "none": {"pt": "(nenhum)", "en": "(none)"},
    "hotkey_moved": {"pt": "{key} saiu de \"{action}\".", "en": "{key} was removed from \"{action}\"."},
    "hotkey_no_modifier": {"pt": "Sem Ctrl/Alt/Shift, toda vez que você apertar {key} jogando o atalho também dispara.",
                           "en": "Without Ctrl/Alt/Shift, {key} also fires every time you press it while playing."},
    "sound_style": {"pt": "Estilo", "en": "Style"},
    "sound_volume": {"pt": "Volume", "en": "Volume"},
    "sound_test": {"pt": "▶ Testar sons", "en": "▶ Test sounds"},
    "sound_custom": {"pt": "Para usar sons seus, coloque WAVs na pasta de sons (botão abaixo).",
                     "en": "To use your own sounds, put WAV files in the sounds folder (button below)."},
    "open_sounds_folder": {"pt": "Abrir pasta de sons", "en": "Open sounds folder"},
    "theme_suave": {"pt": "Suave", "en": "Soft"},
    "theme_grave": {"pt": "Grave", "en": "Deep"},
    "theme_agudo": {"pt": "Agudo", "en": "Sharp"},
    "restore": {"pt": "Restaurar padrão", "en": "Restore defaults"},
    "cancel": {"pt": "Cancelar", "en": "Cancel"},
    "save": {"pt": "Salvar", "en": "Save"},
    "about_text": {
        "pt": "Cronômetro estilo F1 para full clears de jungle no Practice Tool.\n"
              "Rotas e recordes: planilha Jungle Clear Compilation, da comunidade.",
        "en": "F1-style split timer for jungle full clears in the Practice Tool.\n"
              "Routes and records: the community Jungle Clear Compilation sheet.",
    },
    "disclaimer": {
        "pt": "Jungle Splits não é endossado pela Riot Games e não reflete as opiniões da Riot Games ou de qualquer "
              "pessoa envolvida na produção ou gerenciamento das propriedades da Riot Games. Riot Games e todas as "
              "propriedades associadas são marcas registradas da Riot Games, Inc.",
        "en": "Jungle Splits isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or "
              "anyone officially involved in producing or managing Riot Games properties. Riot Games, and all "
              "associated properties are trademarks or registered trademarks of Riot Games, Inc.",
    },
    "open_github": {"pt": "Página do projeto", "en": "Project page"},
    "update_available": {"pt": "⬆ Versão {version} disponível · atualize pelo ícone da bandeja",
                         "en": "⬆ Version {version} available · update from the tray icon"},
    "update_click": {"pt": "⬆ Clique para atualizar para a versão {version}",
                     "en": "⬆ Click to update to version {version}"},
    "updating": {"pt": "⬇ Baixando a versão {version}…", "en": "⬇ Downloading version {version}…"},
    "update_failed": {"pt": "Não deu para atualizar: abrindo a página de download",
                      "en": "Couldn't update: opening the download page"},
    "menu_update": {"pt": "Atualizar para a versão {version}", "en": "Update to version {version}"},
    "open_logs": {"pt": "Abrir logs de depuração", "en": "Open debug logs"},
    "logs_hint": {"pt": "Algum clear saiu estranho? Mande o arquivo daquela run para o desenvolvedor no GitHub.",
                  "en": "A clear looked wrong? Send that run's file to the developer on GitHub."},
    "open_sheet": {"pt": "Planilha de clears", "en": "Clear sheet"},
    "version": {"pt": "Versão {version}", "en": "Version {version}"},
    # Welcome screen
    "welcome_title": {"pt": "Bem-vindo ao Jungle Splits", "en": "Welcome to Jungle Splits"},
    "welcome_subtitle": {"pt": "Cronômetro estilo F1 para o seu full clear", "en": "F1-style timer for your full clear"},
    "welcome_steps": {
        "pt": "1.  Deixe o LoL em modo Sem bordas (Borderless).\n"
              "2.  Abra o Practice Tool com qualquer campeão.\n"
              "3.  Faça o clear: cada campo fecha sozinho, a rota é detectada sozinha.\n"
              "4.  Reset Game no Practice Tool começa a próxima tentativa.",
        "en": "1.  Set LoL to Borderless window mode.\n"
              "2.  Open the Practice Tool with any champion.\n"
              "3.  Clear the jungle: camps close and the route is detected on their own.\n"
              "4.  Reset Game in the Practice Tool starts the next attempt.",
    },
    "welcome_colors": {
        "pt": "Roxo = seu melhor setor   ·   Verde = mais rápido que o PB   ·   Vermelho = mais lento",
        "en": "Purple = your best sector   ·   Green = faster than PB   ·   Red = slower",
    },
    "welcome_keys": {"pt": "Configurações: {settings}   ·   Mover overlay: {move}   ·   ou o ícone na bandeja",
                     "en": "Settings: {settings}   ·   Move overlay: {move}   ·   or the tray icon"},
    "welcome_start": {"pt": "Começar", "en": "Let's go"},
}

_language = "en"


def system_language() -> str:
    """'pt' when Windows is in Portuguese, 'en' otherwise."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return "pt" if lang_id & 0x3FF == 0x16 else "en"  # 0x16 = LANG_PORTUGUESE


def set_language(language: str) -> None:
    global _language
    _language = language if language in LANGUAGES else "en"


def language() -> str:
    return _language


def t(name: str, /, **values) -> str:
    text = STRINGS[name].get(_language) or STRINGS[name]["en"]
    return text.format(**values) if values else text
