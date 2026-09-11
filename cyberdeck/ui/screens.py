import pygame
import time
import math
import random
from ..config import State, RESOLUTION
from .. import runtime
from ..stats import session_stats
from ..hw.telemetry import get_power_telemetry
from .widgets import TerminalFeed, NetMap, TelemetryGauges, EffectsWidget
from .breach_protocol import HexBreachProtocol
from .theme import theme_manager
from ..services import loggen
from ..services.audio import audio_engine

class BaseScreen:
    def __init__(self, surface):
        self.surface = surface
        pygame.font.init()
        self.font = pygame.font.SysFont("courier", 22)
        self.small_font = pygame.font.SysFont("courier", 16)
        self.large_font = pygame.font.SysFont("courier", 60, bold=True)
        self.med_font = pygame.font.SysFont("courier", 36, bold=True)
    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
    def update(self):
        pass

class BootScreen(BaseScreen):
    """
    Military-spec netrunner hardware initialization sequence with memory check,
    subsystem verification, cyberdeck ASCII logo, and animated progress bar.
    """
    def __init__(self, surface):
        super().__init__(surface)
        self.start_time = time.time()
        self.progress = 0
        self.diagnostics = [
            ("CORE BIOS v4.81-ARM", 0.15),
            ("POWER RAIL 5V: NOMINAL", 0.35),
            ("NANO ACCESSORY NODE: LINKED", 0.55),
            ("VISOR SOFT-AP (192.168.4.1): READY", 0.75),
            ("NEURAL INTERFACE BUS: MOUNTED", 0.90),
            ("CYBERDECK OS v1.0 ONLINE", 1.00),
        ]
        self._played_boot_snd = False

    def update(self):
        if not self._played_boot_snd:
            audio_engine.boot_drone()
            self._played_boot_snd = True
            
        elapsed = time.time() - self.start_time
        self.progress = min(1.0, elapsed / 2.8)
        if self.progress >= 1.0 and elapsed > 3.2:
            # Auto-advance to IDLE
            fsm = runtime.fsm
            if fsm and fsm.state == State.BOOT:
                audio_engine.ui_blip()
                fsm.boot_complete()

    def handle_tap(self, pos):
        # Quick skip on tap
        fsm = runtime.fsm
        if fsm and fsm.state == State.BOOT:
            audio_engine.ui_blip()
            fsm.boot_complete()

    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        w, h = RESOLUTION
        
        # Cyberdeck Header Box
        header_box = pygame.Rect(30, 25, w - 60, 90)
        pygame.draw.rect(self.surface, theme.surface_bg, header_box)
        pygame.draw.rect(self.surface, theme.border, header_box, 2)
        
        title = self.large_font.render("CYBERDECK OS", True, theme.primary)
        self.surface.blit(title, (header_box.centerx - title.get_width() // 2, header_box.y + 8))
        
        sub = self.small_font.render(f"[ MIL-SPEC NETRUNNER ARCHITECTURE // PALETTE: {theme.name} ]", True, theme.secondary)
        self.surface.blit(sub, (header_box.centerx - sub.get_width() // 2, header_box.y + 64))
        
        # Diagnostic Log Lines
        y = 135
        for text, threshold in self.diagnostics:
            if self.progress >= threshold:
                status_color = theme.primary
                status_txt = "[ OK ]"
            else:
                status_color = theme.text_dim
                status_txt = "[....]"
                
            line = f"{text:<42} {status_txt}"
            txt = self.font.render(line, True, status_color)
            self.surface.blit(txt, (45, y))
            y += 28

        # Persisted netrunner career summary
        if session_stats.runs > 0:
            career = (f"NETRUNNER CAREER // {session_stats.runs} RUNS | "
                      f"{session_stats.solved} BREACHED | "
                      f"{session_stats.success_rate}% SUCCESS | "
                      f"BEST STREAK {session_stats.best_streak} | "
                      f"€$ {session_stats.credits} EXTRACTED")
            career_surf = self.small_font.render(career, True, theme.secondary)
            self.surface.blit(career_surf, (45, y + 8))

        # Progress Bar
        bar_w = w - 90
        bar_h = 24
        bar_x = 45
        bar_y = h - 60
        
        pygame.draw.rect(self.surface, theme.surface_bg, (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(self.surface, theme.border, (bar_x, bar_y, bar_w, bar_h), 2)
        
        fill_w = int(bar_w * self.progress)
        if fill_w > 0:
            pygame.draw.rect(self.surface, theme.primary, (bar_x + 2, bar_y + 2, fill_w - 4, bar_h - 4))
            
        pct_lbl = self.small_font.render(f"SYSTEM INIT: {int(self.progress * 100)}% (TAP TO SKIP)", True, theme.primary)
        self.surface.blit(pct_lbl, (w // 2 - pct_lbl.get_width() // 2, bar_y - 22))

class IdleScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.tabs = ["TERM", "NETMAP", "SYS", "FX"]
        self.active_tab_idx = 0
        
        pad = 20
        header_h = 40
        widget_rect = pygame.Rect(pad, pad + header_h, RESOLUTION[0] - pad * 2, RESOLUTION[1] - pad * 2 - header_h)
        
        self.terminal = TerminalFeed(widget_rect, self.font)
        self.netmap = NetMap(widget_rect)
        self.gauges = TelemetryGauges(widget_rect, self.font)
        self.fx = EffectsWidget(widget_rect, self.font)
        self.last_log = time.time()
        self.last_hostile_spawn = time.time()
        # Clock + battery readout refresh (once per second, not per frame).
        self.last_status_refresh = 0.0
        self.battery_pct = None

        # One-time controls reference so the wearer sees the button map on first
        # idle. It scrolls away as the feed fills, which is intentional.
        self.terminal.add_line(">> CYBERDECK OS ONLINE // CONTROLS:")
        self.terminal.add_line(">> [L] CYCLE FX   [R] SCAN   [A] RUN/CONFIRM")
        self.terminal.add_line(">> HOLD [A] = BLACKOUT    [L]+[R] = HOME")
        self.terminal.add_line(">> 6x [L] QUICK = CYBERPSYCHO SURGE")
        
    def update(self):
        now = time.time()
        if now - self.last_log > 0.5:
            self.terminal.add_line(loggen.get_random_log())
            if self.active_tab_idx == 1:
                if random.random() < 0.2:
                    self.netmap.add_blip(force_hostile=False)
                if now - self.last_hostile_spawn > random.uniform(7, 10):
                    self.netmap.add_blip(force_hostile=True)
                    self.last_hostile_spawn = now
            self.last_log = now

        # Refresh battery estimate once per second — in update(), not render(),
        # because get_power_telemetry() may shell out to vcgencmd.
        if now - self.last_status_refresh >= 1.0:
            self.last_status_refresh = now
            try:
                from .. import config
                self.battery_pct = get_power_telemetry(
                    active_fx=config.ACTIVE_FX)["battery_pct"]
            except Exception:
                pass
            
    def handle_tap(self, pos):
        # Header tab click detection
        header_w = RESOLUTION[0] / len(self.tabs)
        if pos[1] < 45:
            tab_clicked = int(pos[0] // header_w)
            if 0 <= tab_clicked < len(self.tabs) and tab_clicked != self.active_tab_idx:
                self.active_tab_idx = tab_clicked
                self.netmap.reset()
                if self.active_tab_idx == 1:
                    self.netmap.on_show()
                return True
                
        if self.active_tab_idx == 3:
            self.fx.handle_tap(pos)
        elif self.active_tab_idx == 2:
            self.gauges.handle_tap(pos)
        elif self.active_tab_idx == 1:
            self.netmap.handle_tap(pos)
            
    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        header_w = RESOLUTION[0] / len(self.tabs)
        for i, tab in enumerate(self.tabs):
            is_active = (i == self.active_tab_idx)
            color = theme.primary if is_active else theme.text_dim
            
            # Tab button background highlight
            tab_rect = pygame.Rect(int(i * header_w) + 2, 4, int(header_w) - 4, 34)
            if is_active:
                pygame.draw.rect(self.surface, theme.surface_bg, tab_rect)
            pygame.draw.rect(self.surface, theme.border if is_active else (50, 50, 50), tab_rect, 1)
            
            txt = self.font.render(tab, True, color)
            self.surface.blit(txt, (i * header_w + (header_w / 2 - txt.get_width() / 2), 10))
            if is_active:
                pygame.draw.line(self.surface, theme.primary, (i * header_w + 4, 36), ((i + 1) * header_w - 4, 36), 3)
                
        if self.active_tab_idx == 0:
            self.terminal.render(self.surface)
        elif self.active_tab_idx == 1:
            self.netmap.render(self.surface)
        elif self.active_tab_idx == 2:
            self.gauges.render(self.surface)
        elif self.active_tab_idx == 3:
            self.fx.render(self.surface)

        # HUD Status Badges at bottom
        from .. import config

        # Live clock + estimated pack charge for the wearer (the audio badge was
        # always "MUTED" on this speakerless rig, so it carried no information).
        status_txt = time.strftime("%H:%M:%S")
        if self.battery_pct is not None:
            status_txt += f"  |  BAT {self.battery_pct}%"
        status_color = theme.warning if (self.battery_pct is not None
                                          and self.battery_pct <= 15) else theme.secondary
        status_surf = self.small_font.render(status_txt, True, status_color)
        self.surface.blit(status_surf, (RESOLUTION[0] - status_surf.get_width() - 25, RESOLUTION[1] - 22))

        theme_badge = self.small_font.render(f"[THEME: {theme.name}]", True, theme.primary)
        self.surface.blit(theme_badge, (RESOLUTION[0] // 2 - theme_badge.get_width() // 2, RESOLUTION[1] - 22))

        cur_fx = getattr(config, "ACTIVE_FX", "").replace("VISOR_OLED_", "").replace("SUIT_", "").replace("MATRIX_", "").replace("MC_OLED_", "").replace("_", " ")
        if cur_fx:
            fx_surf = self.small_font.render(f"FX: {cur_fx}", True, theme.secondary)
            self.surface.blit(fx_surf, (25, RESOLUTION[1] - 22))

    def next_tab(self):
        self.active_tab_idx = (self.active_tab_idx + 1) % len(self.tabs)
        self.netmap.reset()
        if self.active_tab_idx == 1:
            self.netmap.on_show()
        
    def prev_tab(self):
        self.active_tab_idx = (self.active_tab_idx - 1) % len(self.tabs)
        self.netmap.reset()
        if self.active_tab_idx == 1:
            self.netmap.on_show()

class ScanningScreen(BaseScreen):
    """
    Dedicated RF/Wi-Fi Spectrum & Node Discovery Screen with frequency oscilloscope,
    channel spectrum waterfall, signal acquisition meters, and probe triggers.
    """
    def __init__(self, surface):
        super().__init__(surface)
        self.probe_btn = pygame.Rect(RESOLUTION[0] - 220, RESOLUTION[1] - 70, 190, 45)
        self.abort_btn = pygame.Rect(30, RESOLUTION[1] - 70, 160, 45)
        self.last_ping = 0
        self.detected_nodes = [
            {"ssid": "CORP-NET_5G", "ch": 36, "pwr": -48, "sec": "WPA3"},
            {"ssid": "ARASAKA_SUBNET", "ch": 6, "pwr": -62, "sec": "ENTERPRISE"},
            {"ssid": "VISOR_LINK (AP)", "ch": 1, "pwr": -28, "sec": "WPA2"},
            {"ssid": "MILITECH_ICE_NODE", "ch": 11, "pwr": -75, "sec": "HARDENED"},
        ]

    def update(self):
        now = time.time()
        if now - self.last_ping > 1.2:
            audio_engine.radar_ping()
            self.last_ping = now

    def handle_tap(self, pos):
        fsm = runtime.fsm
        if self.abort_btn.collidepoint(pos):
            audio_engine.ui_blip()
            if fsm:
                fsm.transition(State.IDLE)
            return True
        elif self.probe_btn.collidepoint(pos):
            audio_engine.target_lock()
            if fsm:
                fsm.trigger_run()
            return True
        return False

    def handle_left(self):
        # Cycle through detected nodes
        if self.detected_nodes:
            self.detected_nodes.append(self.detected_nodes.pop(0))

    def handle_right(self):
        # Deep Probe / Launch Breach on top node
        fsm = runtime.fsm
        if fsm:
            fsm.trigger_run()

    def handle_short_press(self):
        # Launch ICE breach on selected node
        fsm = runtime.fsm
        if fsm:
            fsm.trigger_run()

    def handle_double_press(self):
        # Abort scan back to IDLE
        fsm = runtime.fsm
        if fsm:
            fsm.transition(State.IDLE)

    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        w, h = RESOLUTION
        now = time.time()
        
        # Header
        hdr = self.med_font.render(">> RF SPECTRUM SCANNER <<", True, theme.primary)
        self.surface.blit(hdr, (w // 2 - hdr.get_width() // 2, 15))
        pygame.draw.line(self.surface, theme.border, (30, 52), (w - 30, 52), 2)
        
        # Oscilloscope Waveform Box
        osc_rect = pygame.Rect(30, 65, w - 60, 110)
        pygame.draw.rect(self.surface, theme.surface_bg, osc_rect)
        pygame.draw.rect(self.surface, theme.border, osc_rect, 1)
        
        # Grid lines inside oscilloscope
        for gy in range(osc_rect.top + 20, osc_rect.bottom, 25):
            pygame.draw.line(self.surface, (30, 30, 30), (osc_rect.left, gy), (osc_rect.right, gy), 1)
            
        pts = []
        for x in range(osc_rect.left, osc_rect.right, 4):
            dx = (x - osc_rect.left) * 0.04
            y_val = math.sin(dx + now * 6.0) * 22 + math.sin(dx * 2.5 - now * 3.0) * 12 + math.sin(now * 15.0) * 6
            pts.append((x, osc_rect.centery + int(y_val)))
        if len(pts) > 1:
            pygame.draw.lines(self.surface, theme.secondary, False, pts, 2)
            
        freq_lbl = self.small_font.render(f"FREQ: 2.412 GHz - 5.825 GHz | NOISE FLOOR: -94 dBm", True, theme.text_dim)
        self.surface.blit(freq_lbl, (osc_rect.left + 8, osc_rect.top + 6))
        
        # Detected Nodes Table
        table_y = 190
        col_hdr = self.small_font.render("TARGET AP             CH   PWR      SECURITY      STATUS", True, theme.secondary)
        self.surface.blit(col_hdr, (40, table_y))
        pygame.draw.line(self.surface, (60, 60, 60), (35, table_y + 18), (w - 35, table_y + 18), 1)
        
        y = table_y + 24
        for i, node in enumerate(self.detected_nodes):
            color = theme.primary if i == 0 else theme.text_dim
            status = "LOCKED" if i == 0 else "IDENTIFIED"
            row_str = f"{node['ssid']:<21} {node['ch']:<4} {node['pwr']}dBm  {node['sec']:<13} {status}"
            txt = self.small_font.render(row_str, True, color)
            self.surface.blit(txt, (40, y))
            y += 22
            
        # Buttons
        pygame.draw.rect(self.surface, (50, 0, 0), self.abort_btn)
        pygame.draw.rect(self.surface, theme.danger, self.abort_btn, 2)
        ab_txt = self.font.render("[ CANCEL ]", True, theme.danger)
        self.surface.blit(ab_txt, (self.abort_btn.centerx - ab_txt.get_width() // 2, self.abort_btn.centery - ab_txt.get_height() // 2))

        pygame.draw.rect(self.surface, theme.surface_bg, self.probe_btn)
        pygame.draw.rect(self.surface, theme.primary, self.probe_btn, 2)
        pr_txt = self.font.render("[ DEEP PROBE ]", True, theme.primary)
        self.surface.blit(pr_txt, (self.probe_btn.centerx - pr_txt.get_width() // 2, self.probe_btn.centery - pr_txt.get_height() // 2))

class CooldownScreen(BaseScreen):
    """
    Thermal Dissipation & Memory Buffer Purge Screen after execution.
    """
    def __init__(self, surface):
        super().__init__(surface)
        self.start_time = None
        self.duration = 4.0

    def update(self):
        if self.start_time is None:
            self.start_time = time.time()
            
        elapsed = time.time() - self.start_time
        if elapsed >= self.duration:
            fsm = runtime.fsm
            if fsm and fsm.state == State.COOLDOWN:
                audio_engine.ui_blip()
                fsm.cooldown_complete()

    def handle_tap(self, pos):
        fsm = runtime.fsm
        if fsm and fsm.state == State.COOLDOWN:
            audio_engine.ui_blip()
            fsm.cooldown_complete()

    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        w, h = RESOLUTION
        elapsed = time.time() - (self.start_time or time.time())
        rem = max(0.0, self.duration - elapsed)
        progress = min(1.0, elapsed / self.duration)
        
        # Radiator Vents Animation
        vent_w = 40
        vent_gap = 15
        start_x = w // 2 - (6 * (vent_w + vent_gap)) // 2
        for i in range(6):
            vent_rect = pygame.Rect(start_x + i * (vent_w + vent_gap), 90, vent_w, 140)
            glow = int(max(0, 255 * (1.0 - progress) + math.sin(time.time() * 8.0 + i) * 30))
            glow = min(255, max(0, glow))
            pygame.draw.rect(self.surface, (glow // 4, glow // 2, glow), vent_rect)
            pygame.draw.rect(self.surface, theme.border, vent_rect, 2)
            
        title = self.med_font.render(">> THERMAL PURGE ACTIVE <<", True, theme.secondary)
        self.surface.blit(title, (w // 2 - title.get_width() // 2, 35))
        
        status = self.font.render(f"FLUSHING ICE BUFFERS... {rem:.1f}s (TAP TO BYPASS)", True, theme.primary)
        self.surface.blit(status, (w // 2 - status.get_width() // 2, 260))
        
        # Progress Bar
        bar_rect = pygame.Rect(w // 2 - 200, 310, 400, 20)
        pygame.draw.rect(self.surface, theme.surface_bg, bar_rect)
        pygame.draw.rect(self.surface, theme.border, bar_rect, 2)
        if progress > 0:
            pygame.draw.rect(self.surface, theme.primary, (bar_rect.x + 2, bar_rect.y + 2, int((bar_rect.width - 4) * progress), bar_rect.height - 4))

class AlertScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.purge_btn = pygame.Rect(RESOLUTION[0] // 2 - 260, RESOLUTION[1] - 80, 240, 50)
        self.blackout_btn = pygame.Rect(RESOLUTION[0] // 2 + 20, RESOLUTION[1] - 80, 240, 50)
        self.last_alarm = 0

    def update(self):
        now = time.time()
        if now - self.last_alarm > 0.6:
            audio_engine.alert_siren()
            self.last_alarm = now

    def handle_tap(self, pos):
        fsm = runtime.fsm
        if self.purge_btn.collidepoint(pos):
            audio_engine.ui_blip()
            if fsm:
                fsm.resolve_alert()
            return True
        elif self.blackout_btn.collidepoint(pos):
            audio_engine.glitch_zap()
            if fsm:
                fsm.trigger_blackout()
            return True
        return False

    def render(self):
        theme = theme_manager.current
        self.surface.fill((80, 0, 15))
        w, h = RESOLUTION
        now = time.time()
        
        # Animated Hazard Chevrons
        stripe_offset = int((now * 40) % 60)
        for x in range(-60, w + 60, 60):
            pts = [(x + stripe_offset, 0), (x + 30 + stripe_offset, 0), (x - 10 + stripe_offset, h), (x - 40 + stripe_offset, h)]
            pygame.draw.polygon(self.surface, (60, 0, 10), pts)
            
        # Warning Banner Box
        box = pygame.Rect(60, 45, w - 120, 160)
        pygame.draw.rect(self.surface, (0, 0, 0), box)
        pygame.draw.rect(self.surface, theme.danger, box, 4)
        
        if int(now * 4) % 2 == 0:
            txt1 = self.large_font.render("! INTRUSION DETECTED !", True, (255, 255, 255))
            txt2 = self.med_font.render("SECURITY GRID COMPROMISED", True, theme.danger)
            self.surface.blit(txt1, (w // 2 - txt1.get_width() // 2, box.y + 25))
            self.surface.blit(txt2, (w // 2 - txt2.get_width() // 2, box.y + 95))
            
        # Interactive Response Buttons
        pygame.draw.rect(self.surface, theme.surface_bg, self.purge_btn)
        pygame.draw.rect(self.surface, theme.primary, self.purge_btn, 2)
        txt_p = self.font.render("[ PURGE THREAT ]", True, theme.primary)
        self.surface.blit(txt_p, (self.purge_btn.centerx - txt_p.get_width() // 2, self.purge_btn.centery - txt_p.get_height() // 2))

        pygame.draw.rect(self.surface, (40, 0, 0), self.blackout_btn)
        pygame.draw.rect(self.surface, theme.warning, self.blackout_btn, 2)
        txt_b = self.font.render("[ EMERGENCY LOCK ]", True, theme.warning)
        self.surface.blit(txt_b, (self.blackout_btn.centerx - txt_b.get_width() // 2, self.blackout_btn.centery - txt_b.get_height() // 2))

class BlackoutScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.font = pygame.font.SysFont("courier", 18)
        self.hex_chars = "0123456789ABCDEF"
        self.bg_text = []
        for _ in range(24):
            self.bg_text.append("".join(random.choices(self.hex_chars, k=48)))

    def update(self):
        if random.random() < 0.2:
            idx = random.randint(0, len(self.bg_text) - 1)
            self.bg_text[idx] = "".join(random.choices(self.hex_chars, k=48))

    def handle_tap(self, pos):
        fsm = runtime.fsm
        if fsm and fsm.state == State.BLACKOUT:
            audio_engine.ui_blip()
            fsm.wake_from_blackout()

    def render(self):
        self.surface.fill((0, 0, 0))
        theme = theme_manager.current
        
        y = 0
        for line in self.bg_text:
            txt = self.font.render(line, True, (20, 20, 20))
            self.surface.blit(txt, (0, y))
            y += 20
            
        box_w, box_h = 320, 110
        box_x = RESOLUTION[0] // 2 - box_w // 2
        box_y = RESOLUTION[1] // 2 - box_h // 2
        pygame.draw.rect(self.surface, (0, 0, 0), (box_x, box_y, box_w, box_h))
        pygame.draw.rect(self.surface, theme.border, (box_x, box_y, box_w, box_h), 2)
        
        txt = self.med_font.render("TERMINAL LOCKED", True, theme.primary)
        self.surface.blit(txt, (RESOLUTION[0] // 2 - txt.get_width() // 2, box_y + 20))
        
        hint = self.small_font.render("[ TAP SCREEN TO RE-AUTHENTICATE ]", True, theme.secondary)
        self.surface.blit(hint, (RESOLUTION[0] // 2 - hint.get_width() // 2, box_y + 70))

class TargetLockScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.button_rect = pygame.Rect(RESOLUTION[0] // 2 - 150, RESOLUTION[1] - 95, 300, 42)
        self.abort_btn = pygame.Rect(RESOLUTION[0] // 2 - 150, RESOLUTION[1] - 45, 300, 32)
        self._played_lock_snd = False
        
    def update(self):
        if not self._played_lock_snd:
            audio_engine.target_lock()
            self._played_lock_snd = True

    def handle_tap(self, pos):
        if self.button_rect.collidepoint(pos):
            audio_engine.glitch_zap()
            self._played_lock_snd = False
            pygame.event.post(pygame.event.Event(pygame.USEREVENT + 3))
            return True
        elif self.abort_btn.collidepoint(pos):
            audio_engine.ui_blip()
            self._played_lock_snd = False
            import cyberdeck.runtime as _rt
            if _rt.fsm:
                _rt.fsm.transition(State.IDLE)
            return True

    def handle_short_press(self):
        audio_engine.glitch_zap()
        self._played_lock_snd = False
        pygame.event.post(pygame.event.Event(pygame.USEREVENT + 3))

    def handle_double_press(self):
        audio_engine.ui_blip()
        self._played_lock_snd = False
        import cyberdeck.runtime as _rt
        if _rt.fsm:
            _rt.fsm.transition(State.IDLE)
            
    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        
        center_x = RESOLUTION[0] // 2
        center_y = RESOLUTION[1] // 2 - 50
        size = int(50 + math.sin(time.time() * 10) * 10)
        
        pygame.draw.line(self.surface, theme.danger, (center_x - size, center_y), (center_x + size, center_y), 2)
        pygame.draw.line(self.surface, theme.danger, (center_x, center_y - size), (center_x, center_y + size), 2)
        pygame.draw.circle(self.surface, theme.danger, (center_x, center_y), size // 2, 2)
        
        txt1 = self.med_font.render("TARGET LOCKED", True, theme.danger)
        self.surface.blit(txt1, (center_x - txt1.get_width() // 2, center_y - size - 36))
        
        pygame.draw.rect(self.surface, theme.surface_bg, self.button_rect)
        pygame.draw.rect(self.surface, theme.danger, self.button_rect, 2)
        btn_txt = self.font.render("[ COUNTER-ATTACK ]", True, theme.danger)
        self.surface.blit(btn_txt, (self.button_rect.centerx - btn_txt.get_width() // 2, self.button_rect.centery - btn_txt.get_height() // 2))

        pygame.draw.rect(self.surface, theme.surface_bg, self.abort_btn)
        pygame.draw.rect(self.surface, theme.border, self.abort_btn, 1)
        abt_txt = self.small_font.render("[ ABORT / DISENGAGE ]", True, theme.text_dim)
        self.surface.blit(abt_txt, (self.abort_btn.centerx - abt_txt.get_width() // 2, self.abort_btn.centery - abt_txt.get_height() // 2))

class RunningScreen(BaseScreen):
    """
    Breach execution screen featuring the authentic Cyberpunk 2077 Hex Memory Buffer Minigame.
    Supports full hardware button navigation:
      - Left Button: Step cursor backward across selectable cells
      - Right Button: Step cursor forward across selectable cells
      - Action Button (Short): Confirm / Select cursor cell
      - Action Button (Double): Abort / Disconnect breach
      - Touchscreen: Direct cell tap & button tap
    """
    def __init__(self, surface):
        super().__init__(surface)
        rect = pygame.Rect(15, 15, RESOLUTION[0] - 30, RESOLUTION[1] - 30)
        self.breach = HexBreachProtocol(rect, self.font)
        self.end_time = 0

    def handle_tap(self, pos):
        return self.breach.handle_tap(pos)

    def handle_left(self):
        if not self.breach.solved and not self.breach.failed:
            self.breach.move_cursor(-1)

    def handle_right(self):
        if not self.breach.solved and not self.breach.failed:
            self.breach.move_cursor(1)

    def handle_short_press(self):
        if self.breach.solved or self.breach.failed:
            fsm = runtime.fsm
            if fsm:
                fsm.finish_run()
            return
        self.breach.commit_cursor_selection()

    def handle_double_press(self):
        # Emergency Abort breach
        fsm = runtime.fsm
        if fsm:
            fsm.transition(State.IDLE)

    def update(self):
        self.breach.update()
        if self.breach.solved or self.breach.failed:
            if self.end_time == 0:
                self.end_time = time.time()
            elif time.time() - self.end_time > 4.5:
                # Auto-return after victory/fail modal timeout
                evt = pygame.event.Event(pygame.USEREVENT + 4, {
                    "success": self.breach.solved,
                    "credits": self.breach.total_credits_earned,
                })
                pygame.event.post(evt)
                self.end_time = 0
                self.breach.reset()

    def render(self):
        theme = theme_manager.current
        self.surface.fill(theme.bg)
        self.breach.render(self.surface)

_screens = None
def get_screen_for_state(state, surface):
    global _screens
    # Callers that only need to reach an already-built screen (e.g. to append a
    # terminal line) pass surface=None; fall back to the live display surface
    # so a cold call can never construct screens around a None surface.
    if surface is None:
        surface = runtime.screen
    if _screens is None:
        _screens = {
            State.BOOT: BootScreen(surface),
            State.IDLE: IdleScreen(surface),
            State.SCANNING: ScanningScreen(surface),
            State.RUNNING: RunningScreen(surface),
            State.ALERT: AlertScreen(surface),
            State.COOLDOWN: CooldownScreen(surface),
            State.BLACKOUT: BlackoutScreen(surface),
            State.TARGET_LOCK: TargetLockScreen(surface)
        }
    return _screens[state]
