import pygame
import math
import time
import random
from ..hw.telemetry import (
    get_temp, get_wifi_status, get_wifi_ip, get_uptime,
    get_cpu_usage, get_ram_usage, get_power_telemetry
)
from ..hw.hr import hr_monitor
from ..services.audio import audio_engine
from .. import runtime
from ..stats import session_stats
from .visor_fx import VISOR_FX
from .theme import theme_manager

BREACH_EVENT = pygame.USEREVENT + 1
TARGET_LOCK_EVENT = pygame.USEREVENT + 2
RUN_COMPLETE_EVENT = pygame.USEREVENT + 4

class TerminalFeed:
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.lines = []
        self.max_lines = (rect.height - 10) // font.get_linesize()
        self.max_w = rect.width - 10
        
    def _wrap_text(self, text):
        words = text.split(' ')
        wrapped_lines = []
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if self.font.size(test_line)[0] > self.max_w:
                if current_line:
                    wrapped_lines.append(current_line)
                current_line = word + " "
            else:
                current_line = test_line
        if current_line:
            wrapped_lines.append(current_line)
        return wrapped_lines
        
    def add_line(self, text):
        # Add netrunner timestamp if not already present
        if not text.startswith("[") and not text.startswith(">>"):
            ts = time.strftime("%H:%M:%S")
            text = f"[{ts}] {text}"
        new_lines = self._wrap_text(text)
        for line in new_lines:
            self.lines.append(line)
        while len(self.lines) > self.max_lines:
            self.lines.pop(0)
            
    def render(self, surface):
        theme = theme_manager.current
        pygame.draw.rect(surface, theme.surface_bg, self.rect)
        pygame.draw.rect(surface, theme.border, self.rect, 1)
        
        # Subtle terminal scanline grid
        for gy in range(self.rect.top + 10, self.rect.bottom, 16):
            pygame.draw.line(surface, (theme.surface_bg[0] + 8, theme.surface_bg[1] + 8, theme.surface_bg[2] + 8), (self.rect.left + 2, gy), (self.rect.right - 2, gy), 1)
            
        y = self.rect.y + 6
        for i, line in enumerate(self.lines):
            if ">>" in line or "ALERT" in line or "THEME" in line:
                c = theme.secondary
            elif "CRITICAL" in line or "FAIL" in line or "BREACH" in line or "PACKET" in line:
                c = theme.danger
            else:
                c = theme.text_primary
            txt_surf = self.font.render(line, True, c)
            surface.blit(txt_surf, (self.rect.x + 8, y))
            y += self.font.get_linesize()


class NetMap:
    def __init__(self, rect):
        self.rect = rect
        self.center = (rect.x + rect.width // 2, rect.y + rect.height // 2)
        self.radius = min(rect.width, rect.height) // 2 - 5
        self.angle = 0
        self.blips = [] 
        self.max_blips = 20
        self.has_been_shown = False
        self.ping_waves = [] # [(start_time, cx, cy)]
        self.inspected_node = None # Node inspection popup
        self.small_font = pygame.font.SysFont("courier", 15)
        
    def add_blip(self, initial=False, force_angle=None, force_hostile=None):
        if len(self.blips) >= self.max_blips:
            normal_blips = [b for b in self.blips if not b["hostile"]]
            if normal_blips:
                self.blips.remove(normal_blips[0])
            else:
                return
            
        import random
        angle = force_angle if force_angle is not None else random.uniform(0, 2 * math.pi)
        if initial:
            dist = random.uniform(20, self.radius)
            dr = random.uniform(-0.1, 0.1)
        else:
            dist = self.radius - 1
            dr = random.uniform(-0.1, 0)
            
        dtheta = random.uniform(-0.005, 0.005)
            
        if force_hostile is not None:
            is_hostile = force_hostile
        else:
            is_hostile = False if initial else (random.randint(1, 10) == 1)
        if is_hostile:
            dr = random.uniform(-0.25, -0.5)
            
        corp_prefixes = ["ARASAKA", "MILITECH", "KANG-TAO", "TRAUMA", "CORPO", "NETWATCH"]
        node_name = f"{random.choice(corp_prefixes)}-ICE-{random.randint(10, 99)}" if is_hostile else f"SUBNET-{random.randint(100, 999)}"
        
        self.blips.append({
            "angle": angle,
            "dist": dist,
            "dr": dr,
            "dtheta": dtheta,
            "hostile": is_hostile,
            "alpha": 0,
            "rendered_angle": angle,
            "rendered_dist": dist,
            "targeted": False,
            "node_name": node_name,
            "security": "WPA3-ENTERPRISE" if is_hostile else "OPEN MESH",
            "pwr": random.randint(-78, -35)
        })
        
    def on_show(self):
        if not self.has_been_shown:
            self.has_been_shown = True
            slices = random.randint(6, 8)
            slice_angle = (2 * math.pi) / slices
            for i in range(slices):
                offset = random.uniform(-slice_angle/4, slice_angle/4)
                self.add_blip(initial=True, force_angle=(i * slice_angle) + offset)
                
    def handle_tap(self, pos):
        # Handle Inspected Node Popup clicks
        if self.inspected_node:
            if getattr(self, 'popup_close_btn', None) and self.popup_close_btn.collidepoint(pos):
                self.inspected_node = None
                return True
            if getattr(self, 'popup_ping_btn', None) and self.popup_ping_btn.collidepoint(pos):
                self.ping_waves.append((time.time(), self.center[0], self.center[1]))
                from ..services.audio import audio_engine
                from .screens import get_screen_for_state
                from ..config import State
                audio_engine.radar_ping()
                try:
                    idle = get_screen_for_state(State.IDLE, None)
                    if idle and hasattr(idle, 'terminal'):
                        idle.terminal.add_line(f">> [PING SENT: {self.inspected_node['node_name']}] -> 14ms (ACK)")
                except Exception:
                    pass
                self.inspected_node = None
                return True
            if getattr(self, 'popup_sniff_btn', None) and self.popup_sniff_btn.collidepoint(pos):
                from ..services.audio import audio_engine
                from .screens import get_screen_for_state
                from ..config import State
                audio_engine.ui_blip()
                try:
                    idle = get_screen_for_state(State.IDLE, None)
                    if idle and hasattr(idle, 'terminal'):
                        hex_dump = " ".join([f"{random.randint(0, 255):02X}" for _ in range(8)])
                        idle.terminal.add_line(f">> [SNIFF: {self.inspected_node['node_name']}] -> {hex_dump}")
                except Exception:
                    pass
                self.inspected_node = None
                return True
            if getattr(self, 'popup_breach_btn', None) and self.popup_breach_btn.collidepoint(pos):
                if runtime.fsm:
                    runtime.fsm.trigger_run()
                self.inspected_node = None
                return True

        # Trigger PING ripple on tap
        self.ping_waves.append((time.time(), pos[0], pos[1]))

        for blip in self.blips:
            bx = self.center[0] + blip["rendered_dist"] * math.cos(blip["rendered_angle"])
            by = self.center[1] + blip["rendered_dist"] * math.sin(blip["rendered_angle"])
            dist = math.hypot(pos[0] - bx, pos[1] - by)
            if dist < 28:
                blip["alpha"] = 255
                self.inspected_node = blip
                if blip["hostile"]:
                    blip["targeted"] = True
                    pygame.event.post(pygame.event.Event(TARGET_LOCK_EVENT))
                return True
        return False
        
    def resolve_target(self, success):
        to_remove = []
        for blip in self.blips:
            if blip.get("targeted"):
                if success:
                    to_remove.append(blip)
                else:
                    blip["targeted"] = False
        for b in to_remove:
            if b in self.blips:
                self.blips.remove(b)
                
    def reset(self):
        self.blips = []
        self.has_been_shown = False
        self.ping_waves = []
        self.inspected_node = None
        
    def render(self, surface):
        theme = theme_manager.current
        pygame.draw.rect(surface, theme.surface_bg, self.rect)
        pygame.draw.rect(surface, theme.border, self.rect, 1)
        
        inner_ring = self.radius // 4
        
        pygame.draw.circle(surface, (theme.border[0] // 3, theme.border[1] // 3, theme.border[2] // 3), self.center, self.radius, 1)
        pygame.draw.circle(surface, (theme.border[0] // 3, theme.border[1] // 3, theme.border[2] // 3), self.center, self.radius // 2, 1)
        pygame.draw.circle(surface, theme.danger, self.center, inner_ring, 1)
        
        old_angle = self.angle
        self.angle += 0.05
        if self.angle >= 2 * math.pi:
            self.angle -= 2 * math.pi
            
        end_x = self.center[0] + self.radius * math.cos(self.angle)
        end_y = self.center[1] + self.radius * math.sin(self.angle)
        pygame.draw.line(surface, theme.primary, self.center, (end_x, end_y), 2)
        
        # Compass markings
        surface.blit(self.small_font.render("N", True, theme.primary), (self.center[0] - 4, self.center[1] - self.radius - 2))
        surface.blit(self.small_font.render("S", True, theme.primary), (self.center[0] - 4, self.center[1] + self.radius - 12))
        surface.blit(self.small_font.render("E", True, theme.primary), (self.center[0] + self.radius - 12, self.center[1] - 6))
        surface.blit(self.small_font.render("W", True, theme.primary), (self.center[0] - self.radius + 2, self.center[1] - 6))
        
        # Render PING quickhack expanding waves
        now = time.time()
        active_pings = []
        for (p_time, px, py) in self.ping_waves:
            p_age = now - p_time
            if p_age < 1.2:
                p_rad = int(p_age * 120)
                pygame.draw.circle(surface, theme.secondary, (px, py), p_rad, 1)
                active_pings.append((p_time, px, py))
        self.ping_waves = active_pings

        active_blips = []
        for blip in self.blips:
            passed = False
            if old_angle < self.angle:
                if old_angle <= blip["angle"] < self.angle:
                    passed = True
            else: 
                if old_angle <= blip["angle"] or blip["angle"] < self.angle:
                    passed = True
                    
            if passed:
                blip["alpha"] = 255
                blip["rendered_angle"] = blip["angle"]
                blip["rendered_dist"] = blip["dist"]
                
            if blip["hostile"]:
                blip["dr"] += random.uniform(-0.025, 0.025)
                blip["dtheta"] += random.uniform(-0.005, 0.005)
                blip["dr"] = max(-0.25, min(-0.05, blip["dr"]))
                blip["dtheta"] = max(-0.005, min(0.005, blip["dtheta"]))
                    
                blip["dist"] += blip["dr"]
                blip["angle"] = (blip["angle"] + blip["dtheta"]) % (2 * math.pi)
                
                if blip["dist"] <= inner_ring:
                    pygame.event.post(pygame.event.Event(BREACH_EVENT))
                    continue 
            else:
                blip["dr"] += random.uniform(-0.01, 0.01)
                blip["dtheta"] += random.uniform(-0.001, 0.001)
                blip["dr"] = max(-0.05, min(0.05, blip["dr"]))
                blip["dtheta"] = max(-0.001, min(0.001, blip["dtheta"]))
                blip["dist"] += blip["dr"]
                blip["angle"] = (blip["angle"] + blip["dtheta"]) % (2 * math.pi)
                
                if blip["dist"] >= self.radius or blip["dist"] < 5:
                    continue
            
            blip["alpha"] = max(0, blip["alpha"] - 2)
            
            if blip["alpha"] > 0:
                bx = self.center[0] + blip["rendered_dist"] * math.cos(blip["rendered_angle"])
                by = self.center[1] + blip["rendered_dist"] * math.sin(blip["rendered_angle"])
                
                color = theme.danger if blip["hostile"] else theme.primary
                if blip["hostile"] and int(time.time() * 10) % 2 == 0:
                    color = (255, 255, 255)
                    
                pygame.draw.circle(surface, color, (int(bx), int(by)), 5 if blip["hostile"] else 4)

                # Target lock HUD reticle if targeted
                if blip.get("targeted"):
                    rad = int(8 + math.sin(time.time() * 12) * 3)
                    pygame.draw.circle(surface, theme.danger, (int(bx), int(by)), rad, 1)
                    pygame.draw.line(surface, theme.danger, (int(bx) - rad - 3, int(by)), (int(bx) + rad + 3, int(by)), 1)
                
            active_blips.append(blip)
            
        self.blips = active_blips

        # --- Tactical Node Inspection Modal Popup ---
        if self.inspected_node:
            p_w, p_h = 320, 180
            p_x = self.rect.centerx - p_w // 2
            p_y = self.rect.centery - p_h // 2
            popup_box = pygame.Rect(p_x, p_y, p_w, p_h)
            pygame.draw.rect(surface, theme.bg, popup_box)
            pygame.draw.rect(surface, theme.border, popup_box, 2)

            # Node Title & Close [X]
            t_hdr = self.small_font.render(f">> NODE: {self.inspected_node['node_name']}", True, theme.primary)
            surface.blit(t_hdr, (p_x + 12, p_y + 10))
            self.popup_close_btn = pygame.Rect(p_x + p_w - 32, p_y + 8, 24, 24)
            pygame.draw.rect(surface, theme.danger, self.popup_close_btn, 1)
            x_txt = self.small_font.render("X", True, theme.danger)
            surface.blit(x_txt, (self.popup_close_btn.centerx - x_txt.get_width()//2, self.popup_close_btn.centery - x_txt.get_height()//2))

            # Telemetry Info
            dist_m = int(self.inspected_node["rendered_dist"] * 0.8)
            az_deg = int(math.degrees(self.inspected_node["rendered_angle"]) % 360)
            sec_txt = self.small_font.render(f"RANGE: {dist_m}m  AZ: {az_deg}°  PWR: {self.inspected_node['pwr']}dBm", True, theme.text_dim)
            surface.blit(sec_txt, (p_x + 12, p_y + 36))
            ice_txt = self.small_font.render(f"ICE: {self.inspected_node['security']}", True, theme.secondary)
            surface.blit(ice_txt, (p_x + 12, p_y + 58))

            # Tactical Action Buttons
            btn_h = 32
            self.popup_sniff_btn = pygame.Rect(p_x + 10, p_y + 90, 145, btn_h)
            pygame.draw.rect(surface, theme.surface_bg, self.popup_sniff_btn)
            pygame.draw.rect(surface, theme.secondary, self.popup_sniff_btn, 1)
            b1_txt = self.small_font.render("[ SNIFF PKTS ]", True, theme.secondary)
            surface.blit(b1_txt, (self.popup_sniff_btn.centerx - b1_txt.get_width()//2, self.popup_sniff_btn.centery - b1_txt.get_height()//2))

            self.popup_breach_btn = pygame.Rect(p_x + 165, p_y + 90, 145, btn_h)
            pygame.draw.rect(surface, theme.surface_bg, self.popup_breach_btn)
            pygame.draw.rect(surface, theme.primary, self.popup_breach_btn, 1)
            b2_txt = self.small_font.render("[ BREACH ICE ]", True, theme.primary)
            surface.blit(b2_txt, (self.popup_breach_btn.centerx - b2_txt.get_width()//2, self.popup_breach_btn.centery - b2_txt.get_height()//2))

            self.popup_ping_btn = pygame.Rect(p_x + 10, p_y + 130, p_w - 20, btn_h)
            pygame.draw.rect(surface, theme.surface_bg, self.popup_ping_btn)
            pygame.draw.rect(surface, theme.border, self.popup_ping_btn, 1)
            b3_txt = self.small_font.render("[ SEND PING QUICKHACK ]", True, theme.text_primary)
            surface.blit(b3_txt, (self.popup_ping_btn.centerx - b3_txt.get_width()//2, self.popup_ping_btn.centery - b3_txt.get_height()//2))

class TelemetryGauges:
    """
    System Diagnostics, Real-Time Hardware Telemetry & 20Ah Power Monitor.
    Displays:
      1. Core System & Network: Temp, Uptime, Wi-Fi link, dedicated IP row, real CPU usage & RAM.
      2. 20Ah Power & Energy Telemetry: Total Watts/Amps, 20Ah battery life estimation, and
         per-subsystem breakdown (Raspberry Pi + 120-LED NeoPixels + 5m EL Wire 4W + OLEDs).
      3. Live Bio-Wave EKG oscilloscope.
      4. System Halt, Theme Palette, and Wi-Fi Manager buttons.
    """
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.small_font = pygame.font.SysFont("courier", 13, bold=True)
        self.micro_font = pygame.font.SysFont("courier", 11)
        self.mono_bold = pygame.font.SysFont("courier", 15, bold=True)
        
        # Dual-Panel Symmetrical Layout
        panel_w = (rect.width - 30) // 2
        panel_h = 230
        self.panel_left = pygame.Rect(rect.x + 10, rect.y + 8, panel_w, panel_h)
        self.panel_right = pygame.Rect(self.panel_left.right + 10, rect.y + 8, panel_w, panel_h)
        
        # Bio-Wave Scope
        self.scope_rect = pygame.Rect(rect.x + 10, self.panel_left.bottom + 8, rect.width - 20, 68)
        
        # Bottom Control Buttons (4 Symmetrical Buttons)
        btn_y = self.rect.bottom - 46
        btn_h = 38
        b_w = (rect.width - 50) // 4
        self.stealth_btn = pygame.Rect(rect.x + 10, btn_y, b_w, btn_h)
        self.theme_btn = pygame.Rect(self.stealth_btn.right + 10, btn_y, b_w, btn_h)
        self.wifi_btn = pygame.Rect(self.theme_btn.right + 10, btn_y, b_w, btn_h)
        self.shutdown_btn = pygame.Rect(self.wifi_btn.right + 10, btn_y, b_w, btn_h)
        
        self.confirm_shutdown = False
        self.confirm_time = 0
        
        self.show_wifi_menu = False
        self.wifi_networks = []
        self.last_wifi_scan = 0
        self.wifi_rect = None
        self.wifi_item_rects = []
        
        # Modal buttons pre-initialized
        overlay_rect = pygame.Rect(rect.x + 20, rect.y + 15, rect.width - 40, rect.height - 30)
        btn_w = (overlay_rect.width - 60) // 3
        btn_y_modal = overlay_rect.y + 56
        self.visor_btn = pygame.Rect(overlay_rect.x + 15, btn_y_modal, btn_w, 32)
        self.disconnect_btn = pygame.Rect(self.visor_btn.right + 15, btn_y_modal, btn_w, 32)
        self.close_wifi_btn = pygame.Rect(self.disconnect_btn.right + 15, btn_y_modal, btn_w, 32)
        
    def handle_tap(self, pos):
        from .. import config
        if getattr(self, 'show_wifi_menu', False):
            if getattr(self, 'close_wifi_btn', None) and self.close_wifi_btn.collidepoint(pos):
                self.show_wifi_menu = False
                return True

            if getattr(self, 'visor_btn', None) and self.visor_btn.collidepoint(pos):
                from ..services.wifi import connect_wifi
                connect_wifi("VISOR_LINK")
                return True

            if getattr(self, 'disconnect_btn', None) and self.disconnect_btn.collidepoint(pos):
                from ..services.wifi import connect_wifi
                connect_wifi("DISCONNECT")
                return True

            for rect, ssid in getattr(self, 'wifi_item_rects', []):
                if rect.collidepoint(pos):
                    from ..services.wifi import connect_wifi
                    connect_wifi(ssid)
                    return True
            self.show_wifi_menu = False
            return True

        # Stealth Mode Toggle Tap
        if self.stealth_btn.collidepoint(pos):
            config.STEALTH_MODE = not config.STEALTH_MODE
            from ..hw.accessories import nano_accessories
            from ..hw.wifi_node import wifi_node
            theme = theme_manager.current

            if config.STEALTH_MODE:
                if nano_accessories:
                    nano_accessories.send_brightness(0)
                    nano_accessories.send_color(0, 0, 0)
                # Blank the visor OLEDs. Black = every OLED pixel off, which is
                # the display's lowest-power state; the main loop then stops
                # streaming so the radio quiets down too.
                blank = pygame.Surface((128, 64))
                blank.fill((0, 0, 0))
                wifi_node.stream_image(blank, eye="L")
                wifi_node.stream_image(blank, eye="R")
                print("[POWER] STEALTH MODE ENGAGED (LEDs + visor dark, low-FPS)")
            else:
                if nano_accessories:
                    nano_accessories.send_brightness(255)
                    nano_accessories.send_color(*theme.primary)
                wifi_node.send_text(config.ACTIVE_VISOR_TEXT[0], config.ACTIVE_VISOR_TEXT[1])
                print("[POWER] STEALTH MODE DISENGAGED (COMBAT POWER RESTORED)")
            return True

        # Wi-Fi Manager Button or IP Chip Tap
        if self.wifi_btn.collidepoint(pos) or (getattr(self, 'wifi_rect', None) and self.wifi_rect.collidepoint(pos)):
            self.show_wifi_menu = True
            self.last_wifi_scan = 0
            return True

        # Theme Switcher Button Tap
        if self.theme_btn.collidepoint(pos):
            new_theme = theme_manager.cycle_theme()
            from ..hw.accessories import nano_accessories
            if nano_accessories and not config.STEALTH_MODE:
                nano_accessories.send_color(new_theme.primary[0], new_theme.primary[1], new_theme.primary[2])
            return True

        # Safe System Halt Tap
        if self.shutdown_btn.collidepoint(pos):
            if not self.confirm_shutdown:
                self.confirm_shutdown = True
                self.confirm_time = time.time()
            else:
                if time.time() - self.confirm_time < 5.0:
                    import os
                    os.system("sudo shutdown -h now")
                self.confirm_shutdown = False
            return True

        return False
        
    def render(self, surface):
        theme = theme_manager.current
        pygame.draw.rect(surface, theme.surface_bg, self.rect)
        pygame.draw.rect(surface, theme.border, self.rect, 1)
        
        from .. import config
        temp = get_temp()
        hr = hr_monitor.bpm
        nano_last = config.NANO_LAST_SEEN
        is_nano_online = time.time() - nano_last < 5.0
        uptime_str = get_uptime()
        
        # Get Live System & Power Telemetry
        pwr = get_power_telemetry(active_fx=config.ACTIVE_FX)
        ram_used, ram_total, ram_pct = get_ram_usage()

        # =========================================================================
        # 1. LEFT PANEL: CORE SYSTEM & NETWORK TELEMETRY
        # =========================================================================
        p1 = self.panel_left
        pygame.draw.rect(surface, theme.bg, p1)
        pygame.draw.rect(surface, theme.border, p1, 1)
        pygame.draw.rect(surface, theme.primary, (p1.x, p1.y, 4, p1.height)) # Left Notch
        
        hdr1 = self.small_font.render(">> CORE SYSTEM & NETWORK <<", True, theme.primary)
        surface.blit(hdr1, (p1.x + 12, p1.y + 8))
        
        # Row 1: Nano Node & Temp
        y1 = p1.y + 30
        txt_nano = self.micro_font.render(f"NANO: {'ONLINE' if is_nano_online else 'OFFLINE'}", True, (0, 255, 120) if is_nano_online else theme.danger)
        surface.blit(txt_nano, (p1.x + 12, y1))
        
        temp_color = theme.primary if temp < 60.0 else (theme.warning if temp < 72.0 else theme.danger)
        txt_temp = self.micro_font.render(f"CORE TEMP: {temp}C", True, temp_color)
        surface.blit(txt_temp, (p1.x + 190, y1))
        
        # Row 2: Wi-Fi Link & Uptime
        y1 += 24
        wifi_status = get_wifi_status()
        is_wifi_online = "OFFLINE" not in wifi_status
        txt_wifi_st = self.micro_font.render(f"WIFI: {wifi_status}", True, theme.primary if is_wifi_online else theme.danger)
        surface.blit(txt_wifi_st, (p1.x + 12, y1))
        
        txt_upt = self.micro_font.render(f"UP: {uptime_str}", True, theme.secondary)
        surface.blit(txt_upt, (p1.x + 190, y1))
        
        # Row 3: Dedicated IP Address (Completely isolated row, never covered!)
        y1 += 24
        ip = get_wifi_ip()
        ip_str = ip if ip else "NO IP // OFFLINE"
        self.wifi_rect = pygame.Rect(p1.x + 10, y1, p1.width - 20, 22)
        pygame.draw.rect(surface, (theme.primary[0]//5, theme.primary[1]//5, theme.primary[2]//5), self.wifi_rect)
        pygame.draw.rect(surface, theme.primary if ip else theme.border, self.wifi_rect, 1)
        
        txt_ip_lbl = self.micro_font.render(f"IPV4 ADDR: {ip_str}", True, theme.primary if ip else theme.text_dim)
        surface.blit(txt_ip_lbl, (self.wifi_rect.x + 8, self.wifi_rect.y + 4))
        
        # Row 4: Real CPU Usage (%)
        y1 += 30
        cpu_val = pwr["cpu_pct"]
        txt_cpu = self.micro_font.render(f"REAL CPU LOAD: {cpu_val:.1f}%", True, theme.primary)
        surface.blit(txt_cpu, (p1.x + 12, y1))
        
        bar_w = p1.width - 24
        bar_h = 10
        y1 += 16
        pygame.draw.rect(surface, (25, 25, 25), (p1.x + 12, y1, bar_w, bar_h))
        pygame.draw.rect(surface, theme.primary, (p1.x + 12, y1, int(bar_w * (cpu_val / 100.0)), bar_h))
        
        # Row 5: RAM Usage
        y1 += 18
        txt_ram = self.micro_font.render(f"RAM MEMORY: {ram_used}MB / {ram_total}MB ({ram_pct}%)", True, theme.secondary)
        surface.blit(txt_ram, (p1.x + 12, y1))
        
        y1 += 16
        pygame.draw.rect(surface, (25, 25, 25), (p1.x + 12, y1, bar_w, bar_h))
        pygame.draw.rect(surface, theme.secondary, (p1.x + 12, y1, int(bar_w * (ram_pct / 100.0)), bar_h))
        
        # Row 6: Bio Heart Rate Status
        y1 += 18
        txt_bio = self.micro_font.render(f"BIOMONITOR: {hr if hr else '--'} BPM [{'SYNCED' if hr else 'OFFLINE'}]", True, (0, 255, 120) if hr else theme.text_dim)
        surface.blit(txt_bio, (p1.x + 12, y1))

        # Row 7: Netrunner Career Stats (persisted across power cycles)
        y1 += 18
        career_str = (f"CAREER: {session_stats.runs} RUNS | "
                      f"{session_stats.solved} BREACHED | "
                      f"STREAK {session_stats.streak} (BEST {session_stats.best_streak}) | "
                      f"€$ {session_stats.credits}")
        txt_career = self.micro_font.render(career_str, True, theme.warning)
        surface.blit(txt_career, (p1.x + 12, y1))

        # =========================================================================
        # 2. RIGHT PANEL: 20Ah POWER & ENERGY TELEMETRY
        # =========================================================================
        p2 = self.panel_right
        pygame.draw.rect(surface, theme.bg, p2)
        pygame.draw.rect(surface, theme.border, p2, 1)
        p_notch_col = (255, 170, 0) if pwr['is_stealth'] else theme.secondary
        pygame.draw.rect(surface, p_notch_col, (p2.x, p2.y, 4, p2.height)) # Right Notch
        
        hdr_txt = ">> 20Ah STEALTH POWER MONITOR <<" if pwr['is_stealth'] else ">> 20Ah POWER & ENERGY TELEMETRY <<"
        hdr2 = self.small_font.render(hdr_txt, True, p_notch_col)
        surface.blit(hdr2, (p2.x + 12, p2.y + 8))
        
        # Row 1: Total Power Draw & Current @ 5V
        y2 = p2.y + 30
        pwr_col = (255, 180, 0) if pwr['is_stealth'] else theme.primary
        txt_pwr = self.mono_bold.render(f"TOTAL: {pwr['total_watts']} W  ({pwr['current_amps']} A @ 5.0V)", True, pwr_col)
        surface.blit(txt_pwr, (p2.x + 12, y2))
        
        # Row 2: 20Ah Battery Runtime & Battery Gauge
        y2 += 24
        bat_pct = pwr["battery_pct"]
        txt_bat = self.micro_font.render(f"20Ah PACK: {bat_pct}% [ {pwr['runtime_str']} REMAINING ]", True, (0, 255, 120) if bat_pct > 30 else theme.warning)
        surface.blit(txt_bat, (p2.x + 12, y2))
        
        y2 += 16
        bat_bar_col = (0, 255, 120) if bat_pct > 50 else ((255, 200, 0) if bat_pct > 20 else theme.danger)
        pygame.draw.rect(surface, (25, 25, 25), (p2.x + 12, y2, bar_w, bar_h))
        pygame.draw.rect(surface, bat_bar_col, (p2.x + 12, y2, int(bar_w * (bat_pct / 100.0)), bar_h))
        
        # Power Consumption Breakdown Lines
        y2 += 20
        breakdown = [
            (f"• RASPBERRY PI  : {pwr['pi_watts']} W (COMPUTE LOAD)", theme.text_primary),
            (f"• 120-LED STRIP  : {pwr['led_strip_watts']} W ({'OFF // STEALTH' if pwr['is_stealth'] else 'SUIT NEOPIXELS'})", (255, 170, 0) if pwr['is_stealth'] else theme.primary),
            (f"• 5M EL WIRE     : {pwr['el_wire_watts']} W [{pwr['el_status_str']}]", theme.secondary if pwr['nano_sw_on'] else theme.text_dim),
            (f"• OLEDs & MATRIX : {round(pwr['matrix_watts'] + pwr['oled_watts'], 1)} W (DISPLAYS)", theme.text_primary),
        ]
        for line_txt, col in breakdown:
            s_line = self.micro_font.render(line_txt, True, col)
            surface.blit(s_line, (p2.x + 12, y2))
            y2 += 17
            
        # Sub-footer: Battery Pack Nominal Specs
        y2 += 2
        txt_spec = self.micro_font.render("ENERGY CAPACITY: 74.0 Wh (20,000 mAh @ 3.7V)", True, theme.text_dim)
        surface.blit(txt_spec, (p2.x + 12, y2))

        # =========================================================================
        # 3. BOTTOM: BIO-WAVE SCOPE & HARDWARE BUTTONS
        # =========================================================================
        scope = self.scope_rect
        pygame.draw.rect(surface, theme.bg, scope)
        pygame.draw.rect(surface, theme.border, scope, 1)
        
        # Grid lines inside scope
        for gx in range(scope.x + 40, scope.right, 50):
            pygame.draw.line(surface, (20, 20, 20), (gx, scope.y + 16), (gx, scope.bottom - 4), 1)
        pygame.draw.line(surface, (25, 25, 25), (scope.x + 5, scope.centery + 8), (scope.right - 5, scope.centery + 8), 1)
        
        wave = hr_monitor.get_waveform(scope.width - 10)
        wave_top = scope.y + 16
        wave_h = scope.height - 22
        if wave:
            pts = [(scope.x + 5 + i, scope.bottom - 4 - int(v * wave_h)) for i, v in enumerate(wave)]
            pygame.draw.lines(surface, theme.primary, False, pts, 2)
        else:
            pygame.draw.line(surface, theme.text_dim, (scope.x + 5, wave_top + wave_h // 2),
                             (scope.right - 5, wave_top + wave_h // 2), 1)
        hr_label = f"REAL-TIME NEURAL BIO-WAVE OSCILLOSCOPE // HR: {hr} BPM" if hr else "BIO-WAVE: STANDBY"
        lbl = self.micro_font.render(hr_label, True, theme.primary if hr else theme.text_dim)
        surface.blit(lbl, (scope.x + 8, scope.y + 3))

        # 1. Stealth Mode Toggle Button
        is_st = pwr['is_stealth']
        st_bg = (40, 25, 0) if is_st else theme.bg
        st_border = (255, 170, 0) if is_st else theme.border
        st_txt_col = (255, 170, 0) if is_st else theme.text_primary
        pygame.draw.rect(surface, st_bg, self.stealth_btn)
        pygame.draw.rect(surface, st_border, self.stealth_btn, 2 if is_st else 1)
        st_title = "[ ⚡ STEALTH: ON ]" if is_st else "[ ⚡ STEALTH: OFF ]"
        txt_st = self.small_font.render(st_title, True, st_txt_col)
        surface.blit(txt_st, (self.stealth_btn.centerx - txt_st.get_width()//2, self.stealth_btn.centery - txt_st.get_height()//2))

        # 2. Theme Switcher Button
        pygame.draw.rect(surface, theme.bg, self.theme_btn)
        pygame.draw.rect(surface, theme.primary, self.theme_btn, 1)
        th_txt = self.small_font.render(f"[ PALETTE ]", True, theme.primary)
        surface.blit(th_txt, (self.theme_btn.centerx - th_txt.get_width()//2, self.theme_btn.centery - th_txt.get_height()//2))

        # 3. Wi-Fi Manager Button
        pygame.draw.rect(surface, theme.bg, self.wifi_btn)
        pygame.draw.rect(surface, theme.secondary, self.wifi_btn, 1)
        wf_txt = self.small_font.render("[ WI-FI / VISOR ]", True, theme.secondary)
        surface.blit(wf_txt, (self.wifi_btn.centerx - wf_txt.get_width()//2, self.wifi_btn.centery - wf_txt.get_height()//2))

        # 4. Shutdown Button
        if self.confirm_shutdown and time.time() - self.confirm_time > 5.0:
            self.confirm_shutdown = False
            
        color = theme.danger if self.confirm_shutdown else (150, 0, 0)
        pygame.draw.rect(surface, (50, 0, 0), self.shutdown_btn)
        pygame.draw.rect(surface, color, self.shutdown_btn, 2 if self.confirm_shutdown else 1)
        btn_text = "CONFIRM?" if self.confirm_shutdown else "[ HALT SYS ]"
        txt3 = self.small_font.render(btn_text, True, color)
        surface.blit(txt3, (self.shutdown_btn.centerx - txt3.get_width()//2, self.shutdown_btn.centery - txt3.get_height()//2))

        if getattr(self, 'show_wifi_menu', False):
            self._render_wifi_menu(surface)

    def _render_wifi_menu(self, surface):
        from ..services.wifi import scan_wifi, get_wifi_status_msg
        theme = theme_manager.current

        self.wifi_networks = scan_wifi()

        overlay_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 15, self.rect.width - 40, self.rect.height - 30)
        pygame.draw.rect(surface, theme.bg, overlay_rect)
        pygame.draw.rect(surface, theme.border, overlay_rect, 2)

        txt = self.font.render(">> WI-FI NETWORKS // ADAPTER MANAGER <<", True, theme.primary)
        surface.blit(txt, (overlay_rect.centerx - txt.get_width()//2, overlay_rect.y + 10))

        # Status Line
        status_msg = get_wifi_status_msg()
        st_color = theme.secondary if "LINKED" in status_msg else (theme.danger if "FAILED" in status_msg or "TIMEOUT" in status_msg else theme.text_dim)
        st_surf = self.small_font.render(f"STATUS: {status_msg}", True, st_color)
        surface.blit(st_surf, (overlay_rect.x + 20, overlay_rect.y + 36))

        # Action Buttons Row
        btn_w = (overlay_rect.width - 60) // 3
        btn_y = overlay_rect.y + 56

        self.visor_btn = pygame.Rect(overlay_rect.x + 15, btn_y, btn_w, 32)
        pygame.draw.rect(surface, theme.surface_bg, self.visor_btn)
        pygame.draw.rect(surface, theme.primary, self.visor_btn, 1)
        txt_v = self.small_font.render("[ LINK VISOR ]", True, theme.primary)
        surface.blit(txt_v, (self.visor_btn.centerx - txt_v.get_width()//2, self.visor_btn.centery - txt_v.get_height()//2))

        self.disconnect_btn = pygame.Rect(self.visor_btn.right + 15, btn_y, btn_w, 32)
        pygame.draw.rect(surface, (40, 10, 10), self.disconnect_btn)
        pygame.draw.rect(surface, theme.danger, self.disconnect_btn, 1)
        txt_d = self.small_font.render("[ DISCONNECT ]", True, theme.danger)
        surface.blit(txt_d, (self.disconnect_btn.centerx - txt_d.get_width()//2, self.disconnect_btn.centery - txt_d.get_height()//2))

        self.close_wifi_btn = pygame.Rect(self.disconnect_btn.right + 15, btn_y, btn_w, 32)
        pygame.draw.rect(surface, theme.surface_bg, self.close_wifi_btn)
        pygame.draw.rect(surface, theme.secondary, self.close_wifi_btn, 1)
        txt_c = self.small_font.render("[ CLOSE MENU ]", True, theme.secondary)
        surface.blit(txt_c, (self.close_wifi_btn.centerx - txt_c.get_width()//2, self.close_wifi_btn.centery - txt_c.get_height()//2))

        # Scanned Networks List
        self.wifi_item_rects = []
        y = overlay_rect.y + 100
        for net in self.wifi_networks:
            color = (0, 255, 120) if net["in_use"] else theme.text_primary
            prefix = "[* ACTIVE]" if net["in_use"] else "[  JOIN  ]"
            sig_bars = "■" * max(1, net["signal"] // 25)
            txt_net = self.small_font.render(f"{prefix} {net['ssid']:<22} ({net['signal']}%) {sig_bars}", True, color)
            rect = pygame.Rect(overlay_rect.x + 20, y, overlay_rect.width - 40, 26)
            if rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surface, (theme.primary[0]//4, theme.primary[1]//4, theme.primary[2]//4), rect)
            surface.blit(txt_net, (rect.x + 8, rect.y + 4))
            self.wifi_item_rects.append((rect, net["ssid"]))
            y += 28
            if y > overlay_rect.bottom - 32:
                break


# ----------------------------------------------------
# VISOR 2-WORD PHRASE LIBRARY (One Word Per Eye - 15 Items for 3x5 Grid)
# ----------------------------------------------------
VISOR_PHRASES = [
    ("TARGET", "LOCKED"),
    ("ICE", "BREACH"),
    ("NEURAL", "SYNC"),
    ("SANDEVISTAN", "ACTIVE"),
    ("OPTICS", "OFFLINE"),
    ("SYSTEM", "OVERHEAT"),
    ("COMBAT", "MODE"),
    ("CYBER", "PUNK"),
    ("BLACK", "WALL"),
    ("DATA", "MINING"),
    ("OVER", "CLOCK"),
    ("KILL", "SWITCH"),
    ("FUCK", "AI"),
    ("NET", "RUNNER"),
    ("TRAUMA", "ALERT")
]

# ----------------------------------------------------
# GLOBAL SUIT / SANDEVISTAN PRESETS (15 Loadouts for 3x5 Grid)
# ----------------------------------------------------
SUIT_GLOBAL_PRESETS = [
    {
        "name": "SANDEVISTAN APEX",
        "desc": "CYAN AFTERIMAGE // SANDY SPEED",
        "theme": "CYBERPUNK_2077",
        "text": ("SANDEVISTAN", "ACTIVE"),
        "matrix": "CROSSHAIR",
        "mc": "NETRUNNER HUD",
        "rgb": (0, 240, 255)
    },
    {
        "name": "CYBERPSYCHO SURGE",
        "desc": "RED STROBE // OVERHEAT CASCADE",
        "theme": "ARASAKA_CORP",
        "text": ("SYSTEM", "OVERHEAT"),
        "matrix": "CYBER SKULL",
        "mc": "SYSTEM VITALS",
        "rgb": (255, 20, 20)
    },
    {
        "name": "NETRUNNER DIVE",
        "desc": "PURPLE DATA STREAM // ICE BREAKER",
        "theme": "EDGERUNNER_NEON",
        "text": ("ICE", "BREACH"),
        "matrix": "HEX DUMP",
        "mc": "DATA STREAM",
        "rgb": (180, 0, 255)
    },
    {
        "name": "STEALTH GHOST",
        "desc": "AMBER RADAR // OPTICS CAMO",
        "theme": "MILITECH_TACTICAL",
        "text": ("OPTICS", "OFFLINE"),
        "matrix": "SIGNAL BARS",
        "mc": "SECURITY ICE",
        "rgb": (255, 170, 0)
    },
    {
        "name": "ARASAKA SPEC-OPS",
        "desc": "CRIMSON TARGET // FIREWALL ICE",
        "theme": "ARASAKA_CORP",
        "text": ("TARGET", "LOCKED"),
        "matrix": "FIREWALL ICE",
        "mc": "SECURITY ICE",
        "rgb": (255, 0, 50)
    },
    {
        "name": "MILITECH BRAWLER",
        "desc": "MILITARY GOLD // HARDENED OVERCLOCK",
        "theme": "MILITECH_TACTICAL",
        "text": ("COMBAT", "MODE"),
        "matrix": "RADAR SWEEP",
        "mc": "DIAGNOSTICS",
        "rgb": (255, 200, 0)
    },
    {
        "name": "OVERCLOCK SURGE",
        "desc": "HIGH-FREQ STROBE // RECLOCK BURST",
        "theme": "EDGERUNNER_NEON",
        "text": ("OVER", "CLOCK"),
        "matrix": "RAIN CASCADE",
        "mc": "FREQ TUNER",
        "rgb": (0, 255, 200)
    },
    {
        "name": "NEURAL HARMONY",
        "desc": "RHYTHMIC BIOMON // NEURAL MESH",
        "theme": "EDGERUNNER_NEON",
        "text": ("NEURAL", "SYNC"),
        "matrix": "HEART PULSE",
        "mc": "NEURAL MESH",
        "rgb": (140, 40, 255)
    },
    {
        "name": "BLACKWALL PROTOCOL",
        "desc": "CORRUPTED DATA // VOID INTRUSION",
        "theme": "ARASAKA_CORP",
        "text": ("BLACK", "WALL"),
        "matrix": "HEX DUMP",
        "mc": "OFFLINE STATE",
        "rgb": (255, 0, 0)
    },
    {
        "name": "TRAUMA TEAM MED",
        "desc": "EMERGENCY GREEN // LIFE SUPPORT",
        "theme": "NETRUNNER_MATRIX",
        "text": ("TRAUMA", "ALERT"),
        "matrix": "HEART PULSE",
        "mc": "SYSTEM VITALS",
        "rgb": (0, 255, 120)
    },
    {
        "name": "KANG TAO SMART",
        "desc": "TACTICAL ORANGE // SMART TARGET",
        "theme": "MILITECH_TACTICAL",
        "text": ("TARGET", "LOCKED"),
        "matrix": "CROSSHAIR",
        "mc": "NETRUNNER HUD",
        "rgb": (255, 120, 0)
    },
    {
        "name": "MAELSTROM CHAOS",
        "desc": "CYBERNETIC FRENZY // RED CHAOS",
        "theme": "ARASAKA_CORP",
        "text": ("KILL", "SWITCH"),
        "matrix": "CYBER SKULL",
        "mc": "DIAGNOSTICS",
        "rgb": (255, 0, 100)
    },
    {
        "name": "TYGER CLAWS NEON",
        "desc": "ELECTRIC MAGENTA // DRIFT GLOW",
        "theme": "EDGERUNNER_NEON",
        "text": ("CYBER", "PUNK"),
        "matrix": "RAIN CASCADE",
        "mc": "DATA STREAM",
        "rgb": (255, 0, 220)
    },
    {
        "name": "VALENTINOS GOLD",
        "desc": "HOLY GOLD SHIMMER // SANTA MUERTE",
        "theme": "MILITECH_TACTICAL",
        "text": ("DATA", "MINING"),
        "matrix": "DIAMOND HUD",
        "mc": "FREQ TUNER",
        "rgb": (255, 215, 0)
    },
    {
        "name": "MOXES RIOT",
        "desc": "CHROME PINK // RIOT PROTECTION",
        "theme": "EDGERUNNER_NEON",
        "text": ("FUCK", "AI"),
        "matrix": "BIOHAZARD",
        "mc": "NETRUNNER HUD",
        "rgb": (255, 40, 160)
    }
]


def apply_suit_preset(preset):
    """Apply a global suit loadout (theme + strip + matrix + visor text).

    Shared by the FX widget (manual selection) and attract mode (auto-cycle),
    so both paths stay in lock-step.
    """
    from .. import config
    from ..hw.accessories import nano_accessories
    from ..hw.wifi_node import wifi_node

    fx_id = f"SUIT_{preset['name'].replace(' ', '_')}"
    config.ACTIVE_SUIT_PRESET = preset["name"]
    config.ACTIVE_VISOR_MODE = "TEXT"
    config.ACTIVE_VISOR_TEXT = preset["text"]
    config.ACTIVE_MATRIX_FX = preset["matrix"]
    config.ACTIVE_MC_OLED_FX = preset["mc"]
    config.ACTIVE_FX = fx_id

    theme_manager.set_theme(preset["theme"])
    if nano_accessories:
        nano_accessories.broadcast(fx_id)
        nano_accessories.send_color(*preset["rgb"])
    wifi_node.send_text(preset["text"][0], preset["text"][1])
    return fx_id


class EffectsWidget:
    """
    Multi-Device Cyberware Effects & Loadout Coordinator.
    Provides 4 clean top-level categories in a 2x2 layout:
      1. SUIT (GLOBAL): 15 Master Sandevistan Presets (3x5 Grid).
      2. VISOR OLED: Contains Sub-tabs for [ HUD GRAPHICS ] (15 Presets) and [ 2-WORD TEXT ] (15 Phrases).
      3. LED MATRIX: 15 8x8 LED Matrix Tactical Patterns (3x5 Grid) & Custom Drawing Canvas.
      4. CHEST OLED: 15 Micro-OLED Status Modes (3x5 Grid).
    """
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.small_font = pygame.font.SysFont("courier", 13, bold=True)
        self.mono_bold = pygame.font.SysFont("courier", 16, bold=True)
        self.categories = ["SUIT (GLOBAL)", "VISOR OLED", "LED MATRIX", "CHEST OLED"]

        self.effects = {
            "SUIT (GLOBAL)": [p["name"] for p in SUIT_GLOBAL_PRESETS],
            "VISOR GRAPHICS": list(VISOR_FX.keys()),
            "VISOR TEXT": [f"{p[0]} / {p[1]}" for p in VISOR_PHRASES],
            "LED MATRIX": [
                "CYBER SKULL", "RADAR SWEEP", "RAIN CASCADE",
                "SIGNAL BARS", "HEART PULSE", "CROSSHAIR",
                "FIREWALL ICE", "HEX DUMP", "SANDEVISTAN",
                "BIOHAZARD", "LIGHTNING", "DIAMOND HUD",
                "SONAR RING", "EQUALIZER", "CUSTOM DRAW"
            ],
            "CHEST OLED": [
                "NETRUNNER HUD", "SYSTEM VITALS", "DIAGNOSTICS",
                "FREQ TUNER", "NEURAL MESH", "DATA STREAM",
                "SECURITY ICE", "BATTERY GAUGE", "OFFLINE STATE",
                "COMBAT BIOMON", "RF SCANNER", "RAM ALLOCATOR",
                "OPTICS CAMO", "CYBERWARE LINK", "BLACKWALL LOG"
            ]
        }

        self.active_category = None
        self.selected_fx = {cat: 0 for cat in self.effects}
        self.visor_subtab = 0 # 0: Graphics, 1: 2-Word Text

        self.drawing_matrix = False
        self.glitch_enabled = False
        self.matrix_canvas = [0] * 64
        self.canvas_rects = []

        # 2x2 Symmetrical Grid for Top-Level Categories (Fills full vertical space)
        self.cat_buttons = []
        cat_w = (rect.width - 30) // 2
        cat_h = (rect.height - 56) // 2

        for i in range(4):
            x = rect.x + 10 + (i % 2) * (cat_w + 10)
            y = rect.y + 38 + (i // 2) * (cat_h + 10)
            self.cat_buttons.append(pygame.Rect(x, y, cat_w, cat_h))

        self.back_btn = pygame.Rect(rect.x + 10, rect.y + 6, rect.width - 20, 32)
        self.draw_back_btn = pygame.Rect(rect.x + 10, rect.y + 6, (rect.width - 30) // 2, 32)
        self.draw_glitch_btn = pygame.Rect(self.draw_back_btn.right + 10, rect.y + 6, (rect.width - 30) // 2, 32)

        # Visor Subtab Switcher Buttons
        tab_w = (rect.width - 30) // 2
        self.visor_tab_gfx = pygame.Rect(rect.x + 10, rect.y + 42, tab_w, 32)
        self.visor_tab_txt = pygame.Rect(self.visor_tab_gfx.right + 10, rect.y + 42, tab_w, 32)

        # 3x5 Grid geometry for submenus (15 buttons: 3 columns x 5 rows - Maximized Vertical Height)
        self.grid_y_normal = rect.y + 46
        self.grid_y_visor = rect.y + 80
        self.fx_btn_w = (rect.width - 40) // 3
        self.fx_btn_h_normal = 64
        self.fx_btn_h_visor = 58

        # Preset Stamp Button Rectangles (Scaled to fill right pane)
        cell_s = 38
        stamp_x = rect.x + 20 + 8 * cell_s + 20
        stamp_w = rect.right - stamp_x - 15
        s_y = rect.y + 50
        stamp_h = 58
        self.preset_skull_btn = pygame.Rect(stamp_x, s_y, stamp_w, stamp_h)
        self.preset_heart_btn = pygame.Rect(stamp_x, s_y + stamp_h + 10, stamp_w, stamp_h)
        self.preset_inv_btn = pygame.Rect(stamp_x, s_y + 2 * (stamp_h + 10), stamp_w, stamp_h)
        self.preset_clear_btn = pygame.Rect(stamp_x, s_y + 3 * (stamp_h + 10), stamp_w, stamp_h)

    def handle_tap(self, pos):
        from .. import config
        from ..hw.wifi_node import wifi_node
        from ..hw.accessories import nano_accessories

        if self.drawing_matrix:
            if self.draw_back_btn.collidepoint(pos):
                self.drawing_matrix = False
                return True

            if self.draw_glitch_btn.collidepoint(pos):
                self.glitch_enabled = not self.glitch_enabled
                if nano_accessories:
                    msg = f"G {'1' if self.glitch_enabled else '0'}\n".encode('ascii')
                    with nano_accessories.lock:
                        for node in nano_accessories.nodes:
                            try:
                                node.write(msg)
                            except Exception:
                                pass
                return True

            # Check Preset Stamp buttons
            if getattr(self, 'preset_clear_btn', None) and self.preset_clear_btn.collidepoint(pos):
                self.matrix_canvas = [0] * 64
                self._broadcast_matrix()
                return True
            if getattr(self, 'preset_skull_btn', None) and self.preset_skull_btn.collidepoint(pos):
                skull = [
                    0,1,1,1,1,1,1,0,
                    1,1,1,1,1,1,1,1,
                    1,0,1,1,1,1,0,1,
                    1,0,1,1,1,1,0,1,
                    1,1,1,0,0,1,1,1,
                    0,1,1,1,1,1,1,0,
                    0,0,1,0,0,1,0,0,
                    0,0,1,1,1,1,0,0
                ]
                self.matrix_canvas = skull
                self._broadcast_matrix()
                return True
            if getattr(self, 'preset_heart_btn', None) and self.preset_heart_btn.collidepoint(pos):
                heart = [
                    0,1,1,0,0,1,1,0,
                    1,1,1,1,1,1,1,1,
                    1,1,1,1,1,1,1,1,
                    1,1,1,1,1,1,1,1,
                    0,1,1,1,1,1,1,0,
                    0,0,1,1,1,1,0,0,
                    0,0,0,1,1,0,0,0,
                    0,0,0,0,0,0,0,0
                ]
                self.matrix_canvas = heart
                self._broadcast_matrix()
                return True
            if getattr(self, 'preset_inv_btn', None) and self.preset_inv_btn.collidepoint(pos):
                self.matrix_canvas = [1 if b == 0 else 0 for b in self.matrix_canvas]
                self._broadcast_matrix()
                return True

            for i, rect in enumerate(self.canvas_rects):
                if rect.collidepoint(pos):
                    self.matrix_canvas[i] = 1 if self.matrix_canvas[i] == 0 else 0
                    self._broadcast_matrix()
                    return True
            return False

        if self.active_category is None:
            for i, btn in enumerate(self.cat_buttons):
                if btn.collidepoint(pos):
                    self.active_category = self.categories[i]
                    return True
        else:
            if self.back_btn.collidepoint(pos):
                self.active_category = None
                return True

            cat = self.active_category

            # ----------------------------------------------------
            # 1. VISOR OLED (With GFX and 2-Word Text Sub-Tabs)
            # ----------------------------------------------------
            if cat == "VISOR OLED":
                if self.visor_tab_gfx.collidepoint(pos):
                    self.visor_subtab = 0
                    return True
                elif self.visor_tab_txt.collidepoint(pos):
                    self.visor_subtab = 1
                    return True

                if self.visor_subtab == 0:
                    # GFX Subtab
                    effects_list = self.effects["VISOR GRAPHICS"]
                    for i, (fx_name, btn) in enumerate(zip(effects_list, self._get_fx_buttons(self.grid_y_visor, is_visor=True))):
                        if btn.collidepoint(pos):
                            self.selected_fx["VISOR GRAPHICS"] = i
                            config.ACTIVE_VISOR_MODE = "GRAPHIC"
                            config.ACTIVE_VISOR_FX = fx_name
                            config.ACTIVE_FX = f"VISOR_OLED_{fx_name.replace(' ', '_')}"
                            print(f"[VISOR GRAPHIC] Set -> {fx_name}")
                            return True
                else:
                    # 2-Word Text Subtab
                    effects_list = self.effects["VISOR TEXT"]
                    for i, (phrase_name, btn) in enumerate(zip(effects_list, self._get_fx_buttons(self.grid_y_visor, is_visor=True))):
                        if btn.collidepoint(pos):
                            self.selected_fx["VISOR TEXT"] = i
                            phrase = VISOR_PHRASES[i]
                            config.ACTIVE_VISOR_MODE = "TEXT"
                            config.ACTIVE_VISOR_TEXT = phrase
                            config.ACTIVE_FX = f"VISOR_TEXT_{phrase[0]}_{phrase[1]}"
                            wifi_node.send_text(phrase[0], phrase[1])
                            print(f"[VISOR TEXT] Sent 2-word phrase -> L: {phrase[0]} | R: {phrase[1]}")
                            return True

            # ----------------------------------------------------
            # 2. GLOBAL SUIT / SANDEVISTAN PRESET
            # ----------------------------------------------------
            elif cat == "SUIT (GLOBAL)":
                effects_list = self.effects["SUIT (GLOBAL)"]
                for i, (p_name, btn) in enumerate(zip(effects_list, self._get_fx_buttons(self.grid_y_normal, is_visor=False))):
                    if btn.collidepoint(pos):
                        self.selected_fx["SUIT (GLOBAL)"] = i
                        preset = SUIT_GLOBAL_PRESETS[i]
                        apply_suit_preset(preset)
                        print(f"[GLOBAL PRESET] Applied loadout -> {preset['name']}")
                        return True

            # ----------------------------------------------------
            # 3. LED MATRIX
            # ----------------------------------------------------
            elif cat == "LED MATRIX":
                effects_list = self.effects["LED MATRIX"]
                for i, (fx_name, btn) in enumerate(zip(effects_list, self._get_fx_buttons(self.grid_y_normal, is_visor=False))):
                    if btn.collidepoint(pos):
                        if fx_name == "CUSTOM DRAW":
                            self.drawing_matrix = True
                            config.ACTIVE_MATRIX_FX = "CUSTOM DRAW"
                            self.matrix_canvas = [0] * 64
                        else:
                            self.selected_fx["LED MATRIX"] = i
                            config.ACTIVE_MATRIX_FX = fx_name
                            config.ACTIVE_FX = f"MATRIX_{fx_name.replace(' ', '_')}"
                            if nano_accessories:
                                nano_accessories.broadcast(f"MATRIX_{fx_name.replace(' ', '_')}")
                            print(f"[MATRIX] Set -> {fx_name}")
                        return True

            # ----------------------------------------------------
            # 4. CHEST OLED
            # ----------------------------------------------------
            elif cat == "CHEST OLED":
                effects_list = self.effects["CHEST OLED"]
                for i, (fx_name, btn) in enumerate(zip(effects_list, self._get_fx_buttons(self.grid_y_normal, is_visor=False))):
                    if btn.collidepoint(pos):
                        self.selected_fx["CHEST OLED"] = i
                        config.ACTIVE_MC_OLED_FX = fx_name
                        config.ACTIVE_FX = f"MC_OLED_{fx_name.replace(' ', '_')}"
                        if nano_accessories:
                            nano_accessories.broadcast(f"MC_{fx_name.replace(' ', '_')}")
                        print(f"[CHEST OLED] Set -> {fx_name}")
                        return True

        return False

    def _get_fx_buttons(self, start_y, is_visor=False):
        btns = []
        btn_h = self.fx_btn_h_visor if is_visor else self.fx_btn_h_normal
        spacing_y = 6 if is_visor else 8
        for i in range(15):
            x = self.rect.x + 10 + (i % 3) * (self.fx_btn_w + 10)
            y = start_y + 2 + (i // 3) * (btn_h + spacing_y)
            btns.append(pygame.Rect(x, y, self.fx_btn_w, btn_h))
        return btns

    def _broadcast_matrix(self):
        hex_str = ""
        for chunk in range(16):
            val = 0
            for bit in range(4):
                if self.matrix_canvas[chunk*4 + bit]:
                    val |= (1 << (3 - bit))
            hex_str += f"{val:X}"
        from ..hw.accessories import nano_accessories
        if nano_accessories:
            nano_accessories.send_matrix(hex_str)

    def render(self, surface):
        theme = theme_manager.current
        pygame.draw.rect(surface, theme.surface_bg, self.rect)
        pygame.draw.rect(surface, theme.border, self.rect, 1)

        # ----------------------------------------------------
        # 1. Symmetrical 2x2 Top-Level Category Grid
        # ----------------------------------------------------
        if self.active_category is None:
            # Header Title
            hdr = self.font.render(">> CYBERWARE // HARDWARE LOADOUT CONTROLLER <<", True, theme.primary)
            surface.blit(hdr, (self.rect.x + 15, self.rect.y + 10))

            icons = ["[ GLOBAL LOADOUTS ]", "[ VISOR OLED HUD ]", "[ 8x8 LED MATRIX ]", "[ CHEST MICRO-OLED ]"]
            descs = [
                "Sync Sandevistan strip, visor & theme",
                "Targeting graphics & 2-word text phrases",
                "Tactical animations & custom drawing canvas",
                "Biomonitor telemetry & diagnostic vitals"
            ]

            for i, (cat, btn, icon, desc) in enumerate(zip(self.categories, self.cat_buttons, icons, descs)):
                pygame.draw.rect(surface, theme.bg, btn)
                border_c = theme.primary if i == 0 else theme.border
                pygame.draw.rect(surface, border_c, btn, 2 if i == 0 else 1)

                # Accent left stripe
                stripe_col = theme.secondary if i == 0 else theme.primary
                pygame.draw.rect(surface, stripe_col, (btn.x, btn.y, 6, btn.height))

                txt = self.mono_bold.render(icon, True, theme.primary)
                surface.blit(txt, (btn.x + 18, btn.y + 24))

                d_surf = self.small_font.render(desc, True, theme.text_dim)
                surface.blit(d_surf, (btn.x + 18, btn.y + 60))

        # ----------------------------------------------------
        # 2. Sub-Category Menus
        # ----------------------------------------------------
        else:
            if self.drawing_matrix:
                pygame.draw.rect(surface, (50, 0, 0), self.draw_back_btn)
                pygame.draw.rect(surface, theme.danger, self.draw_back_btn, 2)
                txt = self.font.render(f"[ BACK ]", True, theme.danger)
                surface.blit(txt, (self.draw_back_btn.centerx - txt.get_width()//2, self.draw_back_btn.centery - txt.get_height()//2))

                glitch_color = theme.secondary if self.glitch_enabled else theme.text_dim
                pygame.draw.rect(surface, theme.bg, self.draw_glitch_btn)
                pygame.draw.rect(surface, glitch_color, self.draw_glitch_btn, 2)
                g_txt = self.font.render(f"GLITCH: {'ON' if self.glitch_enabled else 'OFF'}", True, glitch_color)
                surface.blit(g_txt, (self.draw_glitch_btn.centerx - g_txt.get_width()//2, self.draw_glitch_btn.centery - g_txt.get_height()//2))

                # 8x8 Canvas (Scaled to fill height)
                grid_y = self.rect.y + 50
                cell_s = 38
                grid_x = self.rect.x + 20

                self.canvas_rects = []
                for i in range(64):
                    r_x = grid_x + (i % 8) * cell_s
                    r_y = grid_y + (i // 8) * cell_s
                    rect = pygame.Rect(r_x, r_y, cell_s - 3, cell_s - 3)
                    self.canvas_rects.append(rect)

                    if self.matrix_canvas[i]:
                        pygame.draw.rect(surface, theme.primary, rect)
                    else:
                        pygame.draw.rect(surface, (25, 25, 25), rect, 1)

                # Preset Stamp Buttons
                stamp_x = grid_x + 8 * cell_s + 20
                stamp_w = self.rect.right - stamp_x - 15
                s_y = grid_y
                stamp_h = 58

                self.preset_skull_btn = pygame.Rect(stamp_x, s_y, stamp_w, stamp_h)
                pygame.draw.rect(surface, theme.bg, self.preset_skull_btn)
                pygame.draw.rect(surface, theme.primary, self.preset_skull_btn, 1)
                surface.blit(self.small_font.render("[ STAMP: SKULL ]", True, theme.primary), (stamp_x + 16, s_y + 20))

                s_y += stamp_h + 10
                self.preset_heart_btn = pygame.Rect(stamp_x, s_y, stamp_w, stamp_h)
                pygame.draw.rect(surface, theme.bg, self.preset_heart_btn)
                pygame.draw.rect(surface, theme.secondary, self.preset_heart_btn, 1)
                surface.blit(self.small_font.render("[ STAMP: HEART ]", True, theme.secondary), (stamp_x + 16, s_y + 20))

                s_y += stamp_h + 10
                self.preset_inv_btn = pygame.Rect(stamp_x, s_y, stamp_w, stamp_h)
                pygame.draw.rect(surface, theme.bg, self.preset_inv_btn)
                pygame.draw.rect(surface, theme.border, self.preset_inv_btn, 1)
                surface.blit(self.small_font.render("[ INVERT PIXELS ]", True, theme.text_primary), (stamp_x + 16, s_y + 20))

                s_y += stamp_h + 10
                self.preset_clear_btn = pygame.Rect(stamp_x, s_y, stamp_w, stamp_h)
                pygame.draw.rect(surface, (40, 0, 0), self.preset_clear_btn)
                pygame.draw.rect(surface, theme.danger, self.preset_clear_btn, 1)
                surface.blit(self.small_font.render("[ CLEAR MATRIX ]", True, theme.danger), (stamp_x + 16, s_y + 20))

            else:
                # Back button
                pygame.draw.rect(surface, (40, 10, 10), self.back_btn)
                pygame.draw.rect(surface, theme.danger, self.back_btn, 1)
                b_title = f"< RETURN // [{self.active_category}]"
                txt = self.small_font.render(b_title, True, theme.danger)
                surface.blit(txt, (self.back_btn.centerx - txt.get_width()//2, self.back_btn.centery - txt.get_height()//2))

                cat = self.active_category

                # Render Visor Sub-Tab Header if in VISOR OLED
                if cat == "VISOR OLED":
                    # GFX Tab Button
                    is_gfx = (self.visor_subtab == 0)
                    pygame.draw.rect(surface, (theme.primary[0]//4, theme.primary[1]//4, theme.primary[2]//4) if is_gfx else theme.surface_bg, self.visor_tab_gfx)
                    pygame.draw.rect(surface, theme.primary if is_gfx else theme.border, self.visor_tab_gfx, 2 if is_gfx else 1)
                    txt_g = self.small_font.render("[ 1. HUD GRAPHICS ]", True, theme.primary if is_gfx else theme.text_dim)
                    surface.blit(txt_g, (self.visor_tab_gfx.centerx - txt_g.get_width()//2, self.visor_tab_gfx.centery - txt_g.get_height()//2))

                    # 2-Word Text Tab Button
                    is_txt = (self.visor_subtab == 1)
                    pygame.draw.rect(surface, (theme.primary[0]//4, theme.primary[1]//4, theme.primary[2]//4) if is_txt else theme.surface_bg, self.visor_tab_txt)
                    pygame.draw.rect(surface, theme.primary if is_txt else theme.border, self.visor_tab_txt, 2 if is_txt else 1)
                    txt_t = self.small_font.render("[ 2. 2-WORD PHRASES ]", True, theme.primary if is_txt else theme.text_dim)
                    surface.blit(txt_t, (self.visor_tab_txt.centerx - txt_t.get_width()//2, self.visor_tab_txt.centery - txt_t.get_height()//2))

                    effects_list = self.effects["VISOR GRAPHICS"] if is_gfx else self.effects["VISOR TEXT"]
                    active_key = "VISOR GRAPHICS" if is_gfx else "VISOR TEXT"
                    active_idx = self.selected_fx[active_key]
                    btns = self._get_fx_buttons(self.grid_y_visor, is_visor=True)
                else:
                    effects_list = self.effects[cat]
                    active_idx = self.selected_fx[cat]
                    btns = self._get_fx_buttons(self.grid_y_normal, is_visor=False)

                for i, (fx_name, btn) in enumerate(zip(effects_list, btns[:len(effects_list)])):
                    is_active = (i == active_idx)
                    pygame.draw.rect(surface, (theme.primary[0]//3, theme.primary[1]//3, theme.primary[2]//3) if is_active else theme.surface_bg, btn)
                    border_c = theme.primary if is_active else theme.border
                    pygame.draw.rect(surface, border_c, btn, 2 if is_active else 1)

                    # For SUIT (GLOBAL), render 2 lines (Preset Name + Descriptor)
                    if cat == "SUIT (GLOBAL)" and i < len(SUIT_GLOBAL_PRESETS):
                        p = SUIT_GLOBAL_PRESETS[i]
                        txt_color = theme.primary if is_active else theme.text_primary
                        txt_title = self.small_font.render(p["name"], True, txt_color)
                        txt_desc = pygame.font.SysFont("courier", 11).render(p["desc"][:26], True, theme.secondary if is_active else theme.text_dim)
                        surface.blit(txt_title, (btn.centerx - txt_title.get_width()//2, btn.y + 12))
                        surface.blit(txt_desc, (btn.centerx - txt_desc.get_width()//2, btn.y + 36))
                    else:
                        txt_color = theme.primary if is_active else theme.text_primary
                        txt = self.small_font.render(fx_name, True, txt_color)
                        surface.blit(txt, (btn.centerx - txt.get_width()//2, btn.centery - txt.get_height()//2))

