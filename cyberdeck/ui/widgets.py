import pygame
import math
import time
import random
from ..hw.telemetry import get_temp

BREACH_EVENT = pygame.USEREVENT + 1
TARGET_LOCK_EVENT = pygame.USEREVENT + 2
RUN_COMPLETE_EVENT = pygame.USEREVENT + 4

class TerminalFeed:
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.lines = []
        self.max_lines = (rect.height - 10) // font.get_linesize()
        self.color = (0, 255, 0)
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
        new_lines = self._wrap_text(text)
        for line in new_lines:
            self.lines.append(line)
        while len(self.lines) > self.max_lines:
            self.lines.pop(0)
            
    def render(self, surface):
        pygame.draw.rect(surface, (0, 20, 0), self.rect)
        pygame.draw.rect(surface, self.color, self.rect, 1)
        y = self.rect.y + 5
        for line in self.lines:
            txt_surf = self.font.render(line, True, self.color)
            surface.blit(txt_surf, (self.rect.x + 5, y))
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
            dist = self.radius - 1  # Spawn just inside the boundary
            dr = random.uniform(-0.1, 0)
            
        dtheta = random.uniform(-0.005, 0.005)
            
        if force_hostile is not None:
            is_hostile = force_hostile
        else:
            is_hostile = False if initial else (random.randint(1, 10) == 1)
        if is_hostile:
            dr = random.uniform(-0.05, -0.1)
            
        alpha = 0 if not initial else random.randint(50, 255)
        self.blips.append({
            "angle": angle, "dist": dist, 
            "rendered_angle": angle, "rendered_dist": dist,
            "dr": dr, "dtheta": dtheta,
            "alpha": alpha, "hostile": is_hostile
        })
        
    def on_show(self):
        if not self.has_been_shown:
            self.has_been_shown = True
            import random
            slices = random.randint(6, 8)
            slice_angle = (2 * math.pi) / slices
            for i in range(slices):
                offset = random.uniform(-slice_angle/4, slice_angle/4)
                self.add_blip(initial=True, force_angle=(i * slice_angle) + offset)
                
    def handle_tap(self, pos):
        for blip in self.blips:
            if blip["hostile"] and blip["alpha"] > 0:
                bx = self.center[0] + blip["rendered_dist"] * math.cos(blip["rendered_angle"])
                by = self.center[1] + blip["rendered_dist"] * math.sin(blip["rendered_angle"])
                dist = math.hypot(pos[0] - bx, pos[1] - by)
                if dist < 25:
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
        
    def render(self, surface):
        import random
        pygame.draw.rect(surface, (0, 10, 0), self.rect)
        pygame.draw.rect(surface, (0, 255, 0), self.rect, 1)
        
        inner_ring = self.radius // 4
        
        pygame.draw.circle(surface, (0, 100, 0), self.center, self.radius, 1)
        pygame.draw.circle(surface, (0, 100, 0), self.center, self.radius // 2, 1)
        pygame.draw.circle(surface, (150, 0, 0), self.center, inner_ring, 1)
        
        old_angle = self.angle
        self.angle += 0.05
        if self.angle >= 2 * math.pi:
            self.angle -= 2 * math.pi
            
        end_x = self.center[0] + self.radius * math.cos(self.angle)
        end_y = self.center[1] + self.radius * math.sin(self.angle)
        pygame.draw.line(surface, (0, 255, 0), self.center, (end_x, end_y), 2)
        
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
                blip["dr"] += random.uniform(-0.005, 0.005)
                blip["dtheta"] += random.uniform(-0.001, 0.001)
                blip["dr"] = max(-0.05, min(-0.01, blip["dr"]))
                blip["dtheta"] = max(-0.001, min(0.001, blip["dtheta"]))
                    
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
                
                color = (blip["alpha"], 0, 0) if blip["hostile"] else (0, blip["alpha"], 0)
                if blip["hostile"] and int(time.time() * 10) % 2 == 0:
                    color = (255, 0, 0) if blip["alpha"] > 100 else color
                    
                pygame.draw.circle(surface, color, (int(bx), int(by)), 5 if blip["hostile"] else 4)
                
            active_blips.append(blip)
            
        self.blips = active_blips

class TelemetryGauges:
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.cpu_load = 0.5
        self.target_load = 0.5
        self.last_update = 0
        
    def render(self, surface):
        pygame.draw.rect(surface, (0, 15, 0), self.rect)
        pygame.draw.rect(surface, (0, 255, 0), self.rect, 1)
        
        temp = get_temp()
        
        y = self.rect.y + 10
        txt = self.font.render(f"SYS TEMP: {temp}C", True, (0, 255, 0))
        surface.blit(txt, (self.rect.x + 10, y))
        y += 40
        
        now = time.time()
        if now - self.last_update > 0.5:
            self.target_load = random.uniform(0.1, 0.9)
            self.last_update = now
            
        self.cpu_load += (self.target_load - self.cpu_load) * 0.1
        
        pygame.draw.rect(surface, (0, 100, 0), (self.rect.x + 10, y, self.rect.width - 20, 20))
        pygame.draw.rect(surface, (0, 255, 0), (self.rect.x + 10, y, int((self.rect.width - 20) * self.cpu_load), 20))
        
        txt2 = self.font.render(f"CPU LOAD: {int(self.cpu_load*100)}%", True, (0, 255, 0))
        surface.blit(txt2, (self.rect.x + 10, y + 25))

class EffectsWidget:
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.main_effects = ["PULSE", "MATRIX", "CHASE", "STROBE"]
        self.matrix_effects = ["SKULL", "SMILE", "RADAR", "BACK"]
        
        self.in_matrix_menu = False
        self.active_main_idx = 0
        self.active_matrix_idx = 0
        
        self.btn_w = (rect.width - 30) // 2
        self.btn_h = (rect.height - 30) // 2
        self.buttons = []
        for i in range(4):
            x = rect.x + 10 + (i % 2) * (self.btn_w + 10)
            y = rect.y + 10 + (i // 2) * (self.btn_h + 10)
            self.buttons.append(pygame.Rect(x, y, self.btn_w, self.btn_h))
            
    def handle_tap(self, pos):
        for i, btn in enumerate(self.buttons):
            if btn.collidepoint(pos):
                if not self.in_matrix_menu:
                    self.active_main_idx = i
                    if self.main_effects[i] == "MATRIX":
                        self.in_matrix_menu = True
                    else:
                        from .. import config
                        config.ACTIVE_FX = self.main_effects[i]
                else:
                    if self.matrix_effects[i] == "BACK":
                        self.in_matrix_menu = False
                    else:
                        self.active_matrix_idx = i
                        from .. import config
                        config.ACTIVE_FX = f"MATRIX_{self.matrix_effects[i]}"
                return True
        return False
        
    def render(self, surface):
        pygame.draw.rect(surface, (0, 15, 0), self.rect)
        pygame.draw.rect(surface, (0, 255, 0), self.rect, 1)
        
        labels = self.matrix_effects if self.in_matrix_menu else self.main_effects
        active = self.active_matrix_idx if self.in_matrix_menu else self.active_main_idx
        if self.in_matrix_menu and labels[active] == "BACK":
            active = -1 
            
        for i, (fx, btn) in enumerate(zip(labels, self.buttons)):
            color = (0, 255, 0) if i == active else (0, 100, 0)
            pygame.draw.rect(surface, color, btn, 2 if i != active else 0)
            
            txt_color = (0, 0, 0) if i == active else (0, 255, 0)
            txt = self.font.render(fx, True, txt_color)
            surface.blit(txt, (btn.centerx - txt.get_width()//2, btn.centery - txt.get_height()//2))
