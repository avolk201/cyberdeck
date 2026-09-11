import os
import signal
import sys
import time

# Synthesize mouse events from touch inputs (crucial for X11 kiosks)
os.environ.setdefault("SDL_MOUSE_TOUCH_EVENTS", "1")
os.environ.setdefault("SDL_TOUCH_MOUSE_EVENTS", "1")

# Detect if we are running without a window manager (e.g., at boot, via systemd, or SSH)
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    print("No display environment variable found. Defaulting to KMSDRM for direct rendering.")
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

import pygame
from . import runtime
from . import settings
from .stats import session_stats
from .combo import ComboDetector
from .config import RESOLUTION, FPS, STEALTH_FPS, State
from .fsm import CyberdeckFSM
from .hw.button import NavButtons
from .hw.power import PowerManager
from .hw.thermal import ThermalGuard, NORMAL, WARM, CRITICAL
from .hw.accessories import nano_accessories
from .hw.wifi_node import wifi_node
from .hw.hr import hr_monitor
from .hw.telemetry import get_power_telemetry
from .ui.screens import get_screen_for_state
from .ui.glitch import GlitchRenderer
from .ui.widgets import BREACH_EVENT, TARGET_LOCK_EVENT, RUN_COMPLETE_EVENT
from .ui.visor_fx import VISOR_FX
from .ui.hud_effects import get_hud_fx
from .ui.theme import theme_manager
from .services.audio import audio_engine
from .supervisor import touch_heartbeat, DEFAULT_HEARTBEAT_PATH

VISOR_STREAM_INTERVAL = 0.033
HEARTBEAT_INTERVAL = 1.0
SETTINGS_SAVE_INTERVAL = 2.0
# Attract mode: after this long idle + untouched, auto-cycle suit loadouts so
# the suit keeps moving at a convention. Any input resets the timer.
ATTRACT_TIMEOUT = 60.0
ATTRACT_CYCLE_INTERVAL = 8.0
# Battery warning: estimated pack percentage that triggers the banner.
LOW_BATTERY_PCT = 15
POWER_CHECK_INTERVAL = 5.0
# Wearer easter egg: six rapid LEFT clicks while idle. LEFT only cycles FX and
# never leaves IDLE, so this can never interrupt an active scan/breach; it is a
# deliberate "konami code", not something hit by accident.
CYBERPSYCHO_COMBO = ["L"] * 6
CYBERPSYCHO_COMBO_WINDOW = 3.0
fsm = None
screen = None

# Set by SIGTERM/SIGINT so the app exits cleanly (exit code 0). The
# supervisor treats a zero exit as an intentional shutdown and does not
# restart; any non-zero exit is treated as a crash and respawned.
_shutdown_requested = False


def _request_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True

class GestureRecognizer:
    def __init__(self, on_tap, on_swipe_left, on_swipe_right, on_swipe_down, on_long_press):
        self.on_tap = on_tap
        self.on_swipe_left = on_swipe_left
        self.on_swipe_right = on_swipe_right
        self.on_swipe_down = on_swipe_down
        self.on_long_press = on_long_press
        
        self.mouse_down_pos = None
        self.mouse_down_time = 0
        
    def process_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_down_pos = event.pos
            self.mouse_down_time = pygame.time.get_ticks()
        elif event.type == pygame.MOUSEBUTTONUP:
            if self.mouse_down_pos is None:
                return
            dx = event.pos[0] - self.mouse_down_pos[0]
            dy = event.pos[1] - self.mouse_down_pos[1]
            dt = pygame.time.get_ticks() - self.mouse_down_time
            
            click_pos = event.pos
            self.mouse_down_pos = None
            
            if dt > 1000 and abs(dx) < 20 and abs(dy) < 20:
                self.on_long_press()
            elif abs(dx) > 50 and abs(dx) > abs(dy):
                if dx > 0:
                    self.on_swipe_right()
                else:
                    self.on_swipe_left()
            elif dy > 50 and abs(dy) > abs(dx):
                self.on_swipe_down()
            elif abs(dx) < 10 and abs(dy) < 10:
                self.on_tap(click_pos)

def init_display():
    pygame.font.init()
    if os.environ.get("SDL_VIDEODRIVER") == "kmsdrm":
        cards = ['/dev/dri/card0', '/dev/dri/card1', '/dev/dri/card2']
        for card in cards:
            if os.path.exists(card):
                print(f"Trying DRM card: {card}")
                os.environ["SDL_KMSDRM_DRM_CARD"] = card
                try:
                    pygame.display.init()
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    print(f"Success on {card}")
                    return screen
                except pygame.error as e:
                    print(f"Failed on {card}: {e}")
                    pygame.display.quit()
    
    # Fallback if not KMSDRM or all cards failed
    print("Falling back to default display initialization...")
    pygame.display.init()
    try:
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    except pygame.error:
        print("FULLSCREEN failed. Trying windowed mode.")
        return pygame.display.set_mode(RESOLUTION)

def render_visor_text_frame(surface, word):
    surface.fill((0, 0, 0))
    font = pygame.font.SysFont("courier", 22, bold=True)
    t_surf = font.render(word, True, (255, 255, 255))
    if t_surf.get_width() > 118:
        font = pygame.font.SysFont("courier", 15, bold=True)
        t_surf = font.render(word, True, (255, 255, 255))
    surface.blit(t_surf, ((128 - t_surf.get_width()) // 2, (64 - t_surf.get_height()) // 2))
    # Corner HUD reticle brackets
    w, h = 128, 64
    c = (255, 255, 255)
    # Top-Left
    pygame.draw.line(surface, c, (2, 2), (12, 2), 2)
    pygame.draw.line(surface, c, (2, 2), (2, 12), 2)
    # Top-Right
    pygame.draw.line(surface, c, (w - 3, 2), (w - 13, 2), 2)
    pygame.draw.line(surface, c, (w - 3, 2), (w - 3, 12), 2)
    # Bottom-Left
    pygame.draw.line(surface, c, (2, h - 3), (12, h - 3), 2)
    pygame.draw.line(surface, c, (2, h - 3), (2, h - 13), 2)
    # Bottom-Right
    pygame.draw.line(surface, c, (w - 3, h - 3), (w - 13, h - 3), 2)
    pygame.draw.line(surface, c, (w - 3, h - 3), (w - 3, h - 13), 2)

def main():
    global fsm, screen
    try:
        pygame.init()
    except pygame.error as e:
        print(f"Failed to initialize pygame: {e}")
        if os.environ.get("SDL_VIDEODRIVER") == "kmsdrm":
            print("KMSDRM failed. Falling back to X11...")
            os.environ["SDL_VIDEODRIVER"] = "x11"
            pygame.init()
        else:
            raise

    # Initialize audio engine
    audio_engine.init()

    # Restore the wearer's saved theme / loadout / stealth preference.
    settings.load()

    screen = init_display()
    runtime.screen = screen
    pygame.display.set_caption("Cyberdeck OS - Netrunner Terminal")
    
    wifi_node.start()
    
    clock = pygame.time.Clock()

    fsm = CyberdeckFSM()
    runtime.fsm = fsm
    glitch = GlitchRenderer(screen)

    power_manager = PowerManager()

    thermal = ThermalGuard()
    thermal_font = pygame.font.SysFont("courier", 20, bold=True)

    # Attract-mode bookkeeping: any input refreshes the timestamp.
    last_interaction = [time.time()]
    attract_cursor = [0]

    def mark_interaction():
        last_interaction[0] = time.time()

    def on_state_change(new_state):
        get_hud_fx(RESOLUTION).trigger_glitch(0.2)
        state_str = new_state.name if hasattr(new_state, 'name') else str(new_state)
        if state_str == "IDLE":
            import cyberdeck.config as cfg
            active_fx = getattr(cfg, "ACTIVE_MC_OLED_FX", "NETRUNNER HUD").replace(" ", "_")
            nano_accessories.broadcast(f"MC_{active_fx}")
        else:
            nano_accessories.broadcast(state_str)
        
        wifi_node.send_state(state_str)

    fsm.register_listener(on_state_change)

    def on_short_press():
        mark_interaction()
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_short_press'):
            current_screen.handle_short_press()
        elif fsm.state == State.BOOT:
            fsm.boot_complete()
        elif fsm.state == State.BLACKOUT:
            fsm.wake_from_blackout()
        elif fsm.state == State.IDLE:
            fsm.trigger_run()

    def on_long_press():
        mark_interaction()
        audio_engine.glitch_zap()
        fsm.trigger_blackout()

    # --- Vest Effect Button Multi-Gesture Implementation ---
    from . import config
    from .ui.widgets import SUIT_GLOBAL_PRESETS, apply_suit_preset
    effect_categories = ["SUIT (GLOBAL)", "VISOR OLED", "LED MATRIX", "CHEST OLED"]
    active_cat_idx = [0]
    last_saved_fx = [config.ACTIVE_FX]

    def _get_category_effects(cat):
        if cat == "VISOR OLED":
            return [f"VISOR_OLED_{name.replace(' ', '_')}" for name in VISOR_FX.keys()]
        elif cat == "SUIT (GLOBAL)":
            return [f"SUIT_{p['name'].replace(' ', '_')}" for p in SUIT_GLOBAL_PRESETS]
        elif cat == "LED MATRIX":
            return [
                "MATRIX_CYBER_SKULL", "MATRIX_RADAR_SWEEP", "MATRIX_RAIN_CASCADE",
                "MATRIX_SIGNAL_BARS", "MATRIX_HEART_PULSE", "MATRIX_CROSSHAIR",
                "MATRIX_FIREWALL_ICE", "MATRIX_HEX_DUMP", "MATRIX_SANDEVISTAN",
                "MATRIX_BIOHAZARD", "MATRIX_LIGHTNING", "MATRIX_DIAMOND_HUD",
                "MATRIX_SONAR_RING", "MATRIX_EQUALIZER", "MATRIX_CUSTOM_DRAW"
            ]
        else:
            return [
                "MC_OLED_NETRUNNER_HUD", "MC_OLED_SYSTEM_VITALS", "MC_OLED_DIAGNOSTICS",
                "MC_OLED_FREQ_TUNER", "MC_OLED_NEURAL_MESH", "MC_OLED_DATA_STREAM",
                "MC_OLED_SECURITY_ICE", "MC_OLED_BATTERY_GAUGE", "MC_OLED_OFFLINE_STATE",
                "MC_OLED_COMBAT_BIOMON", "MC_OLED_RF_SCANNER", "MC_OLED_RAM_ALLOCATOR",
                "MC_OLED_OPTICS_CAMO", "MC_OLED_CYBERWARE_LINK", "MC_OLED_BLACKWALL_LOG"
            ]

    def on_effect_single():
        mark_interaction()
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_left'):
            current_screen.handle_left()
            return
        elif fsm.state == State.ALERT:
            audio_engine.ui_blip()
            fsm.resolve_alert()
            return
        elif fsm.state == State.TARGET_LOCK:
            audio_engine.glitch_zap()
            fsm.launch_counter_attack()
            return
        elif fsm.state == State.BLACKOUT:
            audio_engine.ui_blip()
            fsm.wake_from_blackout()
            return
        elif fsm.state == State.BOOT:
            audio_engine.ui_blip()
            fsm.boot_complete()
            return

        # IDLE Vest Effect Cycling
        from .ui.widgets import SUIT_GLOBAL_PRESETS
        cat = effect_categories[active_cat_idx[0]]
        fx_list = _get_category_effects(cat)
        current = getattr(config, "ACTIVE_FX", fx_list[0])
        if current in fx_list:
            next_fx = fx_list[(fx_list.index(current) + 1) % len(fx_list)]
        else:
            next_fx = fx_list[0]
        config.ACTIVE_FX = next_fx
        last_saved_fx[0] = next_fx

        if cat == "CHEST OLED":
            clean_name = next_fx.replace("MC_OLED_", "").replace("MC_", "")
            config.ACTIVE_MC_OLED_FX = clean_name.replace("_", " ")
            nano_accessories.broadcast(f"MC_{clean_name}")
        elif cat == "SUIT (GLOBAL)":
            config.ACTIVE_SUIT_PRESET = next_fx.replace("SUIT_", "").replace("_", " ")
            nano_accessories.broadcast(next_fx)
        elif cat == "LED MATRIX":
            config.ACTIVE_MATRIX_FX = next_fx.replace("MATRIX_", "").replace("_", " ")
            nano_accessories.broadcast(next_fx)
        elif cat == "VISOR OLED":
            config.ACTIVE_VISOR_FX = next_fx.replace("VISOR_OLED_", "").replace("_", " ")

        idle_screen = get_screen_for_state(State.IDLE, screen)
        fx_display_name = next_fx.replace("VISOR_OLED_", "").replace("SUIT_", "").replace("MATRIX_", "").replace("MC_OLED_", "").replace("_", " ")
        idle_screen.terminal.add_line(f">> VEST FX: [{cat}] -> {fx_display_name}")
        print(f"[VEST BUTTON] Active FX -> [{cat}] {next_fx}")

    def on_effect_double():
        mark_interaction()
        active_cat_idx[0] = (active_cat_idx[0] + 1) % len(effect_categories)
        new_cat = effect_categories[active_cat_idx[0]]
        audio_engine.target_lock()
        fx_list = _get_category_effects(new_cat)
        next_fx = fx_list[0]
        config.ACTIVE_FX = next_fx
        last_saved_fx[0] = next_fx
        
        if new_cat == "CHEST OLED":
            clean_name = next_fx.replace("MC_OLED_", "").replace("MC_", "")
            config.ACTIVE_MC_OLED_FX = clean_name.replace("_", " ")
            nano_accessories.broadcast(f"MC_{clean_name}")
        elif new_cat in ["SUIT (GLOBAL)", "LED MATRIX"]:
            nano_accessories.broadcast(next_fx)

        idle_screen = get_screen_for_state(State.IDLE, screen)
        idle_screen.terminal.add_line(f">> VEST CATEGORY SWITCH: [{new_cat}]")
        print(f"[VEST BUTTON] Category -> {new_cat}")

    def on_effect_hold_start():
        mark_interaction()
        last_saved_fx[0] = config.ACTIVE_FX
        config.ACTIVE_FX = "VISOR_OLED_GLITCH"
        audio_engine.glitch_zap()
        nano_accessories.broadcast("ALERT")
        idle_screen = get_screen_for_state(State.IDLE, screen)
        idle_screen.terminal.add_line(">> VEST HOLD: COMBAT SURGE / GLITCH ACTIVE <<")

    def on_effect_hold_end():
        mark_interaction()
        config.ACTIVE_FX = last_saved_fx[0]
        audio_engine.ui_blip()
        if last_saved_fx[0].startswith("MC_OLED_"):
            clean_name = last_saved_fx[0].replace("MC_OLED_", "")
            nano_accessories.broadcast(f"MC_{clean_name}")
        else:
            nano_accessories.broadcast(last_saved_fx[0])

    def on_right_press():
        mark_interaction()
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_right'):
            current_screen.handle_right()
            return
        elif fsm.state == State.IDLE:
            fsm.trigger_scan()
        elif fsm.state == State.ALERT:
            fsm.resolve_alert()
        elif fsm.state == State.TARGET_LOCK:
            fsm.launch_counter_attack()
        elif fsm.state == State.COOLDOWN:
            fsm.cooldown_complete()
        elif fsm.state == State.BLACKOUT:
            fsm.wake_from_blackout()
        elif fsm.state == State.BOOT:
            fsm.boot_complete()
        else:
            fsm.trigger_scan()

    def on_double_press():
        mark_interaction()
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_double_press'):
            current_screen.handle_double_press()
        elif fsm.state == State.IDLE:
            current_screen.next_tab()
        else:
            fsm.transition(State.IDLE)

    def on_chord_press():
        mark_interaction()
        fsm.transition(State.IDLE)

    # --- Button-combo easter egg: L, L, R, R, A -> Cyberpsycho Surge ---
    combo = ComboDetector(CYBERPSYCHO_COMBO, window=CYBERPSYCHO_COMBO_WINDOW)

    def trigger_cyberpsycho_surge():
        audio_engine.glitch_zap()
        preset = next((p for p in SUIT_GLOBAL_PRESETS
                       if p["name"] == "CYBERPSYCHO SURGE"), SUIT_GLOBAL_PRESETS[0])
        apply_suit_preset(preset)
        fsm.trigger_alert()
        idle_screen = get_screen_for_state(State.IDLE, screen)
        if idle_screen and hasattr(idle_screen, "terminal"):
            idle_screen.terminal.add_line(">> !! CYBERPSYCHO SURGE DETECTED !! <<")
        print("[COMBO] Cyberpsycho Surge triggered!")

    def on_raw_button(name):
        mark_interaction()
        # Only accumulate the combo while idle so it can never interrupt a
        # scan/breach, and LEFT keeps us in IDLE so it can actually complete.
        if fsm.state == State.IDLE and combo.feed(name):
            trigger_cyberpsycho_surge()

    nav_btns = NavButtons(
        on_left_single=on_effect_single,
        on_right=on_right_press,
        on_action_short=on_short_press,
        on_action_long=on_long_press,
        on_action_double=on_double_press,
        on_chord=on_chord_press,
        on_left_double=on_effect_double,
        on_left_hold_start=on_effect_hold_start,
        on_left_hold_end=on_effect_hold_end,
        on_raw_press=on_raw_button
    )

    def handle_tap(pos):
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_tap'):
            current_screen.handle_tap(pos)
        else:
            on_short_press()
        
    def handle_swipe_left():
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_swipe_left'):
            current_screen.handle_swipe_left()
        elif fsm.state == State.IDLE:
            current_screen.next_tab()
            
    def handle_swipe_right():
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_swipe_right'):
            current_screen.handle_swipe_right()
        elif fsm.state == State.IDLE:
            current_screen.prev_tab()
            
    def handle_swipe_down():
        # Disabled: swipe down no longer triggers scan/attack
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_swipe_down'):
            current_screen.handle_swipe_down()
            
    def handle_long_touch():
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_long_touch'):
            current_screen.handle_long_touch()
        elif fsm.state == State.ALERT:
            on_short_press() 
        else:
            on_long_press()

    gestures = GestureRecognizer(handle_tap, handle_swipe_left, handle_swipe_right, handle_swipe_down, handle_long_touch)

    visor_left = pygame.Surface((128, 64))
    visor_right = pygame.Surface((128, 64))
    
    last_visor_stream = 0
    last_heartbeat = 0.0
    last_settings_save = 0.0
    last_attract_cycle = 0.0
    last_power_check = 0.0
    battery_pct = None
    start_time = time.time()
    running = True

    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    touch_heartbeat(DEFAULT_HEARTBEAT_PATH)

    print("Cyberdeck OS started. Touchscreen gestures active!")

    while running:
        now = time.time()
        if _shutdown_requested:
            running = False
            break
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            last_heartbeat = now
            touch_heartbeat(DEFAULT_HEARTBEAT_PATH)
            thermal.update()
        if now - last_power_check >= POWER_CHECK_INTERVAL:
            last_power_check = now
            try:
                battery_pct = get_power_telemetry(
                    active_fx=config.ACTIVE_FX)["battery_pct"]
            except Exception:
                pass
        if now - last_settings_save >= SETTINGS_SAVE_INTERVAL:
            last_settings_save = now
            settings.save_if_changed()
        for event in pygame.event.get():
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                mark_interaction()
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                    on_short_press()
                elif event.key == pygame.K_LEFT:
                    on_effect_single()
                elif event.key == pygame.K_RIGHT:
                    on_right_press()
                elif event.key == pygame.K_ESCAPE or event.key == pygame.K_a:
                    on_double_press()
                elif event.key == pygame.K_b:
                    on_long_press()
                # Bench / Developer Testing Shortcuts
                elif event.key == pygame.K_1:
                    fsm.transition(State.BOOT)
                elif event.key == pygame.K_2:
                    fsm.transition(State.IDLE)
                elif event.key == pygame.K_3:
                    fsm.transition(State.SCANNING)
                elif event.key == pygame.K_4:
                    fsm.transition(State.RUNNING)
                elif event.key == pygame.K_5:
                    fsm.transition(State.ALERT)
                elif event.key == pygame.K_6:
                    fsm.transition(State.COOLDOWN)
                elif event.key == pygame.K_7:
                    fsm.transition(State.BLACKOUT)
                elif event.key == pygame.K_8:
                    fsm.transition(State.TARGET_LOCK)
                elif event.key == pygame.K_TAB:
                    current_screen = get_screen_for_state(fsm.state, screen)
                    mods = pygame.key.get_mods()
                    if fsm.state == State.IDLE:
                        if mods & pygame.KMOD_SHIFT:
                            current_screen.prev_tab()
                        else:
                            current_screen.next_tab()
                elif event.key == pygame.K_q:
                    current_screen = get_screen_for_state(fsm.state, screen)
                    if fsm.state == State.IDLE:
                        current_screen.prev_tab()
                elif event.key == pygame.K_e:
                    current_screen = get_screen_for_state(fsm.state, screen)
                    if fsm.state == State.IDLE:
                        current_screen.next_tab()
                elif event.key == pygame.K_f:
                    on_effect_single()
                elif event.key == pygame.K_d:
                    on_effect_double()
                elif event.key == pygame.K_t:
                    new_th = theme_manager.cycle_theme()
                    audio_engine.target_lock()
                    idle_screen = get_screen_for_state(State.IDLE, screen)
                    idle_screen.terminal.add_line(f">> THEME SWITCHED: [{new_th.name}]")
                    nano_accessories.send_color(new_th.primary[0], new_th.primary[1], new_th.primary[2])
                    print(f"[THEME] Active Palette: {new_th.name}")
                elif event.key == pygame.K_m:
                    muted = audio_engine.toggle_mute()
                    print(f"[AUDIO] Master Audio {'MUTED' if muted else 'UNMUTED'}")
                elif event.key == pygame.K_h:
                    # Test heartbeat pulse
                    audio_engine.heartbeat()
                    hr_monitor.add_sample(750)
                elif event.key == pygame.K_w:
                    config.NANO_SW = 0 if config.NANO_SW == 1 else 1
                    print(f"[NANO] Suit sensor link toggled: {'LINKED' if config.NANO_SW == 1 else 'UNLINKED'}")
            elif event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP]:
                gestures.process_event(event)
            elif event.type == BREACH_EVENT:
                audio_engine.alert_siren()
                fsm.trigger_alert()
            elif event.type == TARGET_LOCK_EVENT:
                audio_engine.target_lock()
                fsm.trigger_target_lock()
            elif event.type == pygame.USEREVENT + 3:
                fsm.launch_counter_attack()
            elif event.type == RUN_COMPLETE_EVENT:
                fsm.finish_run()
                idle_screen = get_screen_for_state(State.IDLE, screen)
                success_val = getattr(event, 'success', False)
                credits_val = getattr(event, 'credits', 0)
                session_stats.record_run(success_val, credits_val)
                if idle_screen and hasattr(idle_screen, 'netmap'):
                    idle_screen.netmap.resolve_target(success_val)

        # Attract mode: after a long idle + untouched, auto-cycle suit loadouts
        # so the rig keeps moving at a convention. Skipped in stealth or when
        # thermally throttling. Any input resets the idle timer.
        if (fsm.state == State.IDLE and not config.STEALTH_MODE
                and not thermal.should_throttle
                and now - last_interaction[0] > ATTRACT_TIMEOUT
                and now - last_attract_cycle >= ATTRACT_CYCLE_INTERVAL):
            last_attract_cycle = now
            attract_cursor[0] = (attract_cursor[0] + 1) % len(SUIT_GLOBAL_PRESETS)
            preset = SUIT_GLOBAL_PRESETS[attract_cursor[0]]
            apply_suit_preset(preset)
            print(f"[ATTRACT] Auto-cycling loadout -> {preset['name']}")

        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'update'):
            current_screen.update()
            
        current_screen.render()

        is_stealth = config.STEALTH_MODE
        # Thermal throttling sheds load just like stealth does, independent of
        # the wearer's choice, so the deck cools itself before the Pi does.
        low_power = is_stealth or thermal.should_throttle

        if not low_power:
            glitch.render(fsm.state)

            # Apply CRT scanline & cyberpunk corner HUD reticles overlay
            get_hud_fx(RESOLUTION).apply_overlay(screen, theme_manager.current)

        # =========================================================================
        # 1. ESP32 Visor HUD Streaming (Wi-Fi UDP Broadcast)
        #    Skipped entirely in low-power mode to save CPU + radio power; the
        #    visor OLEDs are blanked once when stealth is engaged.
        # =========================================================================
        if not low_power:
            visor_mode = getattr(config, "ACTIVE_VISOR_MODE", "GRAPHIC")

            if now - last_visor_stream >= VISOR_STREAM_INTERVAL:
                last_visor_stream = now
                if visor_mode == "TEXT":
                    left_w, right_w = getattr(config, "ACTIVE_VISOR_TEXT", ("CYBER", "DECK"))
                    render_visor_text_frame(visor_left, left_w)
                    render_visor_text_frame(visor_right, right_w)
                    wifi_node.stream_image(visor_left, eye="L")
                    wifi_node.stream_image(visor_right, eye="R")
                else:
                    active_fx = getattr(config, "ACTIVE_VISOR_FX", "RADAR")
                    fx_fn = VISOR_FX.get(active_fx)
                    if fx_fn is None:
                        # Dynamic Contextual Mapping based on state
                        if fsm.state == State.SCANNING:
                            fx_fn = VISOR_FX.get("RADAR")
                        elif fsm.state == State.RUNNING:
                            fx_fn = VISOR_FX.get("TARGET")
                        elif fsm.state == State.ALERT:
                            fx_fn = VISOR_FX.get("GLITCH")
                        elif fsm.state == State.TARGET_LOCK:
                            fx_fn = VISOR_FX.get("TARGET")
                        elif fsm.state == State.COOLDOWN:
                            fx_fn = VISOR_FX.get("COUNTDOWN")
                        elif fsm.state == State.BOOT:
                            fx_fn = VISOR_FX.get("STATIC")
                        else:
                            fx_fn = VISOR_FX.get("RADAR")

                    if fx_fn:
                        visor_left.fill((0, 0, 0))
                        visor_right.fill((0, 0, 0))
                        try:
                            fx_fn(now, visor_left, visor_right)
                            wifi_node.stream_image(visor_left, eye="L")
                            wifi_node.stream_image(visor_right, eye="R")
                        except Exception as e:
                            print("Visor stream error:", e)

        # On-screen warning banner (priority: thermal > battery) so the wearer
        # knows to cool down or swap banks.
        banner = None
        if thermal.level >= CRITICAL:
            banner = (f"!! THERMAL CRITICAL {thermal.temp:.0f}C - THROTTLING !!",
                      (255, 40, 40))
        elif thermal.level >= WARM:
            banner = (f"THERMAL WARNING: {thermal.temp:.0f}C", (255, 160, 0))
        elif battery_pct is not None and battery_pct <= LOW_BATTERY_PCT:
            banner = (f"LOW BATTERY: {battery_pct}% REMAINING", (255, 200, 0))
        if banner:
            t_msg, t_col = banner
            t_surf = thermal_font.render(t_msg, True, t_col)
            t_w = t_surf.get_width() + 24
            t_x = (RESOLUTION[0] - t_w) // 2
            pygame.draw.rect(screen, (0, 0, 0), (t_x, 3, t_w, 26))
            pygame.draw.rect(screen, t_col, (t_x, 3, t_w, 26), 2)
            screen.blit(t_surf, (t_x + 12, 7))

        pygame.display.flip()
        clock.tick(STEALTH_FPS if low_power else FPS)

    nano_accessories.running = False
    wifi_node.stop()
    pygame.quit()
    print("Cyberdeck OS shut down cleanly.")
    sys.exit(0)

if __name__ == "__main__":
    main()
