import pygame
import random
import time

class HUDEffects:
    """
    Visual-only CRT scanlines, vignette framing, and tactical netrunner HUD reticles.
    Designed for speakerless, high-immersion display output.
    """
    def __init__(self, resolution):
        self.res = resolution
        self.scanline_surface = pygame.Surface(resolution, pygame.SRCALPHA)
        self._build_scanlines()
        self._glitch_until = 0.0

    def _build_scanlines(self):
        self.scanline_surface.fill((0, 0, 0, 0))
        for y in range(0, self.res[1], 3):
            pygame.draw.line(self.scanline_surface, (0, 0, 0, 35), (0, y), (self.res[0], y), 1)

    def trigger_glitch(self, duration=0.18):
        self._glitch_until = time.time() + duration

    def apply_overlay(self, surface, theme):
        # 1. Apply CRT scanlines
        surface.blit(self.scanline_surface, (0, 0))

        # 2. Cyberpunk corner framing reticles
        w, h = self.res
        line_len = 16

        # Top-Left
        pygame.draw.line(surface, theme.border, (6, 6), (6 + line_len, 6), 2)
        pygame.draw.line(surface, theme.border, (6, 6), (6, 6 + line_len), 2)
        # Top-Right
        pygame.draw.line(surface, theme.border, (w - 7, 6), (w - 7 - line_len, 6), 2)
        pygame.draw.line(surface, theme.border, (w - 7, 6), (w - 7, 6 + line_len), 2)
        # Bottom-Left
        pygame.draw.line(surface, theme.border, (6, h - 7), (6 + line_len, h - 7), 2)
        pygame.draw.line(surface, theme.border, (6, h - 7), (6, h - 7 - line_len), 2)
        # Bottom-Right
        pygame.draw.line(surface, theme.border, (w - 7, h - 7), (w - 7 - line_len, h - 7), 2)
        pygame.draw.line(surface, theme.border, (w - 7, h - 7), (w - 7, h - 7 - line_len), 2)

        # 3. State-transition glitch displacement tearing
        if time.time() < self._glitch_until:
            for _ in range(4):
                gy = random.randint(10, h - 30)
                gh = random.randint(4, 16)
                shift = random.randint(-15, 15)
                sub_rect = pygame.Rect(0, gy, w, gh)
                sub_surf = surface.subsurface(sub_rect).copy()
                surface.blit(sub_surf, (shift, gy))
                pygame.draw.rect(surface, theme.primary, (0, gy, w, 2))

hud_fx = None
def get_hud_fx(resolution):
    global hud_fx
    if hud_fx is None:
        hud_fx = HUDEffects(resolution)
    return hud_fx
