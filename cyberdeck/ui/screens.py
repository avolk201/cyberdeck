import pygame
import time
import math
import random
from ..config import State, RESOLUTION
from .widgets import TerminalFeed, NetMap, TelemetryGauges, EffectsWidget
from ..services import loggen

class BaseScreen:
    def __init__(self, surface):
        self.surface = surface
        pygame.font.init()
        self.font = pygame.font.SysFont("courier", 24)
        self.large_font = pygame.font.SysFont("courier", 64, bold=True)
        self.med_font = pygame.font.SysFont("courier", 40, bold=True)
    def render(self):
        self.surface.fill((0,0,0))
    def update(self):
        pass

class BootScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.start_time = time.time()
    def render(self):
        self.surface.fill((0, 0, 0))
        txt = self.large_font.render("CYBERDECK OS", True, (0, 255, 0))
        self.surface.blit(txt, (RESOLUTION[0]//2 - txt.get_width()//2, RESOLUTION[1]//2 - txt.get_height()//2))

class IdleScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.tabs = ["TERM", "NETMAP", "SYS", "FX"]
        self.active_tab_idx = 0
        
        pad = 20
        header_h = 40
        widget_rect = pygame.Rect(pad, pad + header_h, RESOLUTION[0] - pad*2, RESOLUTION[1] - pad*2 - header_h)
        
        self.terminal = TerminalFeed(widget_rect, self.font)
        self.netmap = NetMap(widget_rect)
        self.gauges = TelemetryGauges(widget_rect, self.font)
        self.fx = EffectsWidget(widget_rect, self.font)
        self.last_log = time.time()
        self.last_hostile_spawn = time.time()
        
    def update(self):
        if time.time() - self.last_log > 0.5:
            self.terminal.add_line(loggen.get_random_log())
            if self.active_tab_idx == 1:
                import random
                if random.random() < 0.2:
                    self.netmap.add_blip(force_hostile=False)
                if time.time() - self.last_hostile_spawn > random.uniform(7, 10):
                    self.netmap.add_blip(force_hostile=True)
                    self.last_hostile_spawn = time.time()
            self.last_log = time.time()
            
    def handle_tap(self, pos):
        if self.active_tab_idx == 3:
            self.fx.handle_tap(pos)
        elif self.active_tab_idx == 2:
            self.gauges.handle_tap(pos)
        elif self.active_tab_idx == 1:
            self.netmap.handle_tap(pos)
            
    def render(self):
        self.surface.fill((0, 0, 0))
        header_w = RESOLUTION[0] / len(self.tabs)
        for i, tab in enumerate(self.tabs):
            color = (0, 255, 0) if i == self.active_tab_idx else (0, 100, 0)
            txt = self.font.render(tab, True, color)
            self.surface.blit(txt, (i * header_w + (header_w/2 - txt.get_width()/2), 10))
            if i == self.active_tab_idx:
                pygame.draw.line(self.surface, color, (i*header_w, 35), ((i+1)*header_w, 35), 3)
                
        if self.active_tab_idx == 0:
            self.terminal.render(self.surface)
        elif self.active_tab_idx == 1:
            self.netmap.render(self.surface)
        elif self.active_tab_idx == 2:
            self.gauges.render(self.surface)
        elif self.active_tab_idx == 3:
            self.fx.render(self.surface)

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

class AlertScreen(BaseScreen):
    def render(self):
        self.surface.fill((150, 0, 0))
        if int(time.time() * 5) % 2 == 0:
            txt1 = self.med_font.render("! BREACH !", True, (255, 255, 255))
            txt2 = self.med_font.render("DETECTED", True, (255, 255, 255))
            self.surface.blit(txt1, (RESOLUTION[0]//2 - txt1.get_width()//2, RESOLUTION[1]//2 - txt1.get_height()))
            self.surface.blit(txt2, (RESOLUTION[0]//2 - txt2.get_width()//2, RESOLUTION[1]//2 + 10))

class BlackoutScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.font = pygame.font.SysFont("courier", 18)
        self.hex_chars = "0123456789ABCDEF"
        self.bg_text = []
        for _ in range(20):
            self.bg_text.append("".join(random.choices(self.hex_chars, k=40)))

    def update(self):
        if random.random() < 0.2:
            idx = random.randint(0, len(self.bg_text)-1)
            self.bg_text[idx] = "".join(random.choices(self.hex_chars, k=40))

    def render(self):
        self.surface.fill((0, 0, 0))
        
        y = 0
        for line in self.bg_text:
            txt = self.font.render(line, True, (0, 30, 0))
            self.surface.blit(txt, (0, y))
            y += 20
            
        box_w, box_h = 200, 100
        box_x = RESOLUTION[0]//2 - box_w//2
        box_y = RESOLUTION[1]//2 - box_h//2
        pygame.draw.rect(self.surface, (0, 0, 0), (box_x, box_y, box_w, box_h))
        pygame.draw.rect(self.surface, (0, 255, 0), (box_x, box_y, box_w, box_h), 2)
        
        txt = self.med_font.render("LOCKED", True, (0, 255, 0))
        self.surface.blit(txt, (RESOLUTION[0]//2 - txt.get_width()//2, RESOLUTION[1]//2 - txt.get_height()//2))

class TargetLockScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.button_rect = pygame.Rect(RESOLUTION[0]//2 - 150, RESOLUTION[1] - 80, 300, 50)
        
    def handle_tap(self, pos):
        if self.button_rect.collidepoint(pos):
            pygame.event.post(pygame.event.Event(pygame.USEREVENT + 3))
            
    def render(self):
        self.surface.fill((50, 0, 0)) 
        
        center_x = RESOLUTION[0]//2
        center_y = RESOLUTION[1]//2 - 40
        size = int(50 + math.sin(time.time() * 10) * 10)
        
        pygame.draw.line(self.surface, (255, 0, 0), (center_x - size, center_y), (center_x + size, center_y), 2)
        pygame.draw.line(self.surface, (255, 0, 0), (center_x, center_y - size), (center_x, center_y + size), 2)
        pygame.draw.circle(self.surface, (255, 0, 0), (center_x, center_y), size // 2, 2)
        
        txt1 = self.med_font.render("TARGET LOCKED", True, (255, 0, 0))
        self.surface.blit(txt1, (center_x - txt1.get_width()//2, center_y - size - 40))
        
        pygame.draw.rect(self.surface, (100, 0, 0), self.button_rect)
        pygame.draw.rect(self.surface, (255, 0, 0), self.button_rect, 2)
        btn_txt = self.font.render("[ COUNTER-ATTACK ]", True, (255, 0, 0))
        self.surface.blit(btn_txt, (self.button_rect.centerx - btn_txt.get_width()//2, self.button_rect.centery - btn_txt.get_height()//2))

class RunningScreen(BaseScreen):
    def __init__(self, surface):
        super().__init__(surface)
        self.progress = 0
        self.start_time = None
        self.success = None
        self.logs = []
        self.qte = None
        self.last_qte_time = 0
        
    def _spawn_qte(self):
        qte_types = ["swipe_left", "swipe_right", "swipe_down", "long_touch", "tap", "press_button"]
        qte_type = random.choice(qte_types)
        prompt = ""
        rect = None
        if qte_type == "swipe_left":
            prompt = "<<< SWIPE LEFT"
        elif qte_type == "swipe_right":
            prompt = "SWIPE RIGHT >>>"
        elif qte_type == "swipe_down":
            prompt = "vv SWIPE DOWN vv"
        elif qte_type == "long_touch":
            prompt = "[ HOLD SCREEN ]"
        elif qte_type == "tap":
            prompt = "TAP TARGET"
            rect = pygame.Rect(random.randint(50, RESOLUTION[0]-150), random.randint(50, RESOLUTION[1]-150), 100, 100)
        elif qte_type == "press_button":
            prompt = "[ PRESS BUTTON ]"
            
        self.qte = {
            "type": qte_type,
            "prompt": prompt,
            "rect": rect,
            "start": time.time()
        }

    def _resolve_qte(self, qte_type, pos=None):
        if self.qte and self.qte["type"] == qte_type:
            if qte_type == "tap":
                if self.qte["rect"].collidepoint(pos):
                    self.qte = None
                    self.last_qte_time = time.time()
            else:
                self.qte = None
                self.last_qte_time = time.time()

    def handle_swipe_left(self): self._resolve_qte("swipe_left")
    def handle_swipe_right(self): self._resolve_qte("swipe_right")
    def handle_swipe_down(self): self._resolve_qte("swipe_down")
    def handle_long_touch(self): self._resolve_qte("long_touch")
    def handle_tap(self, pos): 
        if self.progress >= 100:
            self.end_time = 0
        else:
            self._resolve_qte("tap", pos)
            
    def handle_short_press(self): 
        if self.progress >= 100:
            self.end_time = 0
        else:
            self._resolve_qte("press_button")
        
    def update(self):
        if self.start_time is None:
            self.start_time = time.time()
            self.progress = 0
            self.success = None
            self.logs = []
            self.qte = None
            self.last_qte_time = time.time()
            
        if self.progress < 100:
            if self.qte:
                if time.time() - self.qte["start"] > 2.0:
                    self.success = False
                    self.progress = 100
                    self.end_time = time.time()
            else:
                elapsed = time.time() - self.start_time
                self.progress = min(100, (elapsed / 6.0) * 100)
                
                if random.random() < 0.6:
                    self.logs.append(loggen.get_random_log())
                    if len(self.logs) > 8:
                        self.logs.pop(0)
                        
                if self.progress >= 100:
                    self.success = True
                    self.end_time = time.time()
                elif self.progress < 90 and time.time() - self.last_qte_time > 2.5:
                    if random.random() < 0.5:
                        self._spawn_qte()
                    self.last_qte_time = time.time()
        else:
            if time.time() - self.end_time > 1.5:
                evt = pygame.event.Event(pygame.USEREVENT + 4, {"success": self.success})
                pygame.event.post(evt)
                self.start_time = None 

    def render(self):
        self.surface.fill((0, 0, 0))
        
        bar_w = RESOLUTION[0] - 100
        bar_h = 30
        bar_x = 50
        bar_y = RESOLUTION[1] - 80
        
        pygame.draw.rect(self.surface, (0, 100, 0), (bar_x, bar_y, bar_w, bar_h), 2)
        if self.progress > 0:
            pygame.draw.rect(self.surface, (0, 255, 0), (bar_x, bar_y, int(bar_w * self.progress / 100), bar_h))
        
        pct_txt = self.font.render(f"{int(self.progress)}%", True, (0, 255, 0))
        self.surface.blit(pct_txt, (bar_x + bar_w/2 - pct_txt.get_width()/2, bar_y - 30))
        
        if self.progress < 100:
            y = 20
            for line in self.logs:
                txt = self.font.render(line, True, (0, 150, 0))
                self.surface.blit(txt, (50, y))
                y += 25
                
            if self.qte:
                prompt_txt = self.font.render(self.qte["prompt"], True, (255, 0, 0))
                pygame.draw.rect(self.surface, (0, 0, 0), (RESOLUTION[0]//2 - prompt_txt.get_width()//2 - 10, RESOLUTION[1]//2 - prompt_txt.get_height()//2 - 10, prompt_txt.get_width() + 20, prompt_txt.get_height() + 20))
                pygame.draw.rect(self.surface, (255, 0, 0), (RESOLUTION[0]//2 - prompt_txt.get_width()//2 - 10, RESOLUTION[1]//2 - prompt_txt.get_height()//2 - 10, prompt_txt.get_width() + 20, prompt_txt.get_height() + 20), 2)
                self.surface.blit(prompt_txt, (RESOLUTION[0]//2 - prompt_txt.get_width()//2, RESOLUTION[1]//2 - prompt_txt.get_height()//2))
                
                if self.qte["rect"]:
                    pygame.draw.rect(self.surface, (255, 0, 0), self.qte["rect"], 3)
                    pygame.draw.line(self.surface, (255, 0, 0), (self.qte["rect"].left, self.qte["rect"].top), (self.qte["rect"].right, self.qte["rect"].bottom), 2)
                    pygame.draw.line(self.surface, (255, 0, 0), (self.qte["rect"].right, self.qte["rect"].top), (self.qte["rect"].left, self.qte["rect"].bottom), 2)
        else:
            msg = "ATTACK SUCCESSFUL" if self.success else "ATTACK FAILED"
            color = (0, 255, 0) if self.success else (255, 0, 0)
            txt = self.med_font.render(msg, True, color)
            self.surface.blit(txt, (RESOLUTION[0]//2 - txt.get_width()//2, RESOLUTION[1]//2 - txt.get_height()//2 - 50))

class MessageScreen(BaseScreen):
    def __init__(self, surface, text, color=(0,255,0)):
        super().__init__(surface)
        self.text = text
        self.color = color
        
    def render(self):
        self.surface.fill((0, 0, 0))
        txt = self.large_font.render(self.text, True, self.color)
        self.surface.blit(txt, (RESOLUTION[0]//2 - txt.get_width()//2, RESOLUTION[1]//2 - txt.get_height()//2))

_screens = None
def get_screen_for_state(state, surface):
    global _screens
    if _screens is None:
        _screens = {
            State.BOOT: BootScreen(surface),
            State.IDLE: IdleScreen(surface),
            State.SCANNING: MessageScreen(surface, "SCANNING..."),
            State.RUNNING: RunningScreen(surface),
            State.ALERT: AlertScreen(surface),
            State.COOLDOWN: MessageScreen(surface, "COOLDOWN..."),
            State.BLACKOUT: BlackoutScreen(surface),
            State.TARGET_LOCK: TargetLockScreen(surface)
        }
    return _screens[state]
