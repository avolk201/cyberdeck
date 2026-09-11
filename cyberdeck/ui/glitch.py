import pygame
import random
from ..config import State, RESOLUTION

class GlitchRenderer:
    """
    Dynamic glitch effects layered on the rendered frame: tear displacement,
    RGB split and noise. Static CRT scanlines are deliberately NOT drawn here;
    hud_effects.apply_overlay() already blits a cached scanline surface, so
    doing it again would double-darken the frame and waste a per-frame
    allocation on the Pi.
    """
    def __init__(self, surface):
        self.base_surface = surface
        self.width, self.height = RESOLUTION

    def render(self, screen_state):
        if screen_state == State.ALERT:
            self.apply_tearing(severity=10)
            self.apply_rgb_split(offset=5)
            self.apply_noise(alpha=40)
        elif screen_state == State.SCANNING:
            if random.random() < 0.1:
                self.apply_tearing(severity=3)
        elif screen_state == State.RUNNING:
            self.apply_rgb_split(offset=2)
            self.apply_noise(alpha=20)
        elif screen_state == State.IDLE:
            if random.random() < 0.02:
                self.apply_tearing(severity=2)

    def apply_tearing(self, severity):
        num_tears = random.randint(1, severity)
        for _ in range(num_tears):
            y = random.randint(0, self.height - 20)
            h = random.randint(5, 20)
            offset = random.randint(-15, 15)

            slice_rect = pygame.Rect(0, y, self.width, h)
            slice_surf = self.base_surface.subsurface(slice_rect).copy()

            pygame.draw.rect(self.base_surface, (0, 0, 0), slice_rect)
            self.base_surface.blit(slice_surf, (offset, y))

    def apply_rgb_split(self, offset):
        copy = self.base_surface.copy()
        copy.set_alpha(100)
        self.base_surface.blit(copy, (offset, 0))
        self.base_surface.blit(copy, (-offset, 0))

    def apply_noise(self, alpha):
        noise = pygame.Surface(RESOLUTION, pygame.SRCALPHA)
        for _ in range(100):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            pygame.draw.line(noise, (255, 255, 255, alpha), (x, y), (x+random.randint(1,5), y))
        self.base_surface.blit(noise, (0,0))
