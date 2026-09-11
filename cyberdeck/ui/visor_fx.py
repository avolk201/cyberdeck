import math
import random
import time

import pygame

from ..hw.hr import hr_monitor

W, H = 128, 64
WHITE = (255, 255, 255)

_fonts = {}

def _font(size):
    f = _fonts.get(size)
    if f is None:
        if not pygame.font.get_init():
            pygame.font.init()
        f = pygame.font.Font(None, size)
        _fonts[size] = f
    return f

def _center(surf, txt, size, y=None):
    s = _font(size).render(txt, True, WHITE)
    if y is None:
        y = (H - s.get_height()) // 2
    surf.blit(s, ((W - s.get_width()) // 2, y))

# 1. RADAR
def _radar(t, l, r):
    cx, cy = 64, 32
    for rad in (10, 20, 30):
        pygame.draw.circle(l, WHITE, (cx, cy), rad, 1)
    pygame.draw.line(l, WHITE, (cx - 30, cy), (cx + 30, cy))
    pygame.draw.line(l, WHITE, (cx, cy - 30), (cx, cy + 30))
    ang = (t * 1.8) % (2 * math.pi)
    ex = cx + math.cos(ang) * 30
    ey = cy + math.sin(ang) * 30
    pygame.draw.line(l, WHITE, (cx, cy), (ex, ey), 2)
    for ba, bd in [(0.9, 22), (2.6, 14), (4.4, 26)]:
        if (ang - ba) % (2 * math.pi) < 1.6:
            bx = int(cx + math.cos(ba) * bd)
            by = int(cy + math.sin(ba) * bd)
            pygame.draw.circle(l, WHITE, (bx, by), 2)
    deg = int(math.degrees(ang))
    _center(r, "CONTACTS", 18, 4)
    _center(r, f"{deg:03d}", 36, 20)
    if int(t * 2) % 2 == 0:
        _center(r, "TRACKING", 16, 52)

# 2. SCANNER
def _scanner(t, l, r):
    for surf, phase in ((l, 0.0), (r, math.pi / 2)):
        s = math.sin(t * 3.0 + phase)
        x = int((s + 1) / 2 * (W - 10))
        direction = 1 if math.cos(t * 3.0 + phase) > 0 else -1
        for i in range(5, 0, -1):
            tx = x - direction * i * 8
            h = H - 16 - i * 8
            if h > 8 and 0 <= tx <= W - 6:
                pygame.draw.rect(surf, WHITE, (tx, (H - h) // 2, 6, h))
        pygame.draw.rect(surf, WHITE, (x, 6, 10, H - 12))

# 3. VITALS
def _vitals(t, l, r):
    wave = hr_monitor.get_waveform(W)
    if wave:
        pts = [(x, int(54 - wave[x] * 44)) for x in range(W)]
        pygame.draw.lines(l, WHITE, False, pts, 1)
    else:
        pygame.draw.line(l, WHITE, (0, 32), (W - 1, 32), 1)
        _center(l, "NO SIGNAL", 18, 6)
    bpm = hr_monitor.bpm
    _center(r, f"{bpm}" if bpm else "--", 48, 6)
    _center(r, "BPM" if bpm else "NO PULSE", 18, 48)
    if time.time() - hr_monitor.last_beat < 0.15:
        pygame.draw.circle(r, WHITE, (14, 54), 4)

_RAIN_SPEEDS = [random.Random(i).randint(18, 46) for i in range(16)]
_GLYPHS = "01<>[]{}#$%*+=/\\|"

# 4. CODE RAIN
def _code_rain(t, l, r):
    f = _font(12)
    for surf in (l, r):
        for col in range(16):
            x = col * 8
            head = int((t * _RAIN_SPEEDS[col] + col * 37) % (H + 30)) - 15
            tail = head - 26
            if head > 0 and tail < H:
                pygame.draw.line(surf, WHITE, (x + 3, max(0, tail)), (x + 3, min(H - 1, head)), 1)
            if 0 <= head < H - 10:
                g = _GLYPHS[(col * 7 + int(t * 8)) % len(_GLYPHS)]
                surf.blit(f.render(g, True, WHITE), (x, head))

# 5. GLITCH
def _glitch(t, l, r):
    for surf in (l, r):
        for _ in range(random.randint(3, 7)):
            y = random.randint(0, H - 1)
            x = random.randint(0, W - 40)
            pygame.draw.rect(surf, WHITE, (x, y, random.randint(12, 60), random.randint(1, 5)))
        if random.random() < 0.4:
            pygame.draw.rect(surf, WHITE,
                             (random.randint(0, W - 30), random.randint(0, H - 20),
                              random.randint(8, 30), random.randint(8, 20)), 1)
        if random.random() < 0.25:
            y = random.randint(0, H - 1)
            pygame.draw.line(surf, WHITE, (0, y), (W, y), 1)

# 6. TARGET
def _target(t, l, r):
    tx = 64 + math.sin(t * 0.9) * 38
    ty = 32 + math.sin(t * 1.7) * 18
    x, y = int(tx), int(ty)
    pygame.draw.circle(l, WHITE, (x, y), 10, 1)
    pygame.draw.line(l, WHITE, (x - 16, y), (x - 5, y))
    pygame.draw.line(l, WHITE, (x + 5, y), (x + 16, y))
    pygame.draw.line(l, WHITE, (x, y - 16), (x, y - 5))
    pygame.draw.line(l, WHITE, (x, y + 5), (x, y + 16))
    rng = int(120 + math.sin(t * 0.6) * 60)
    az = int(math.degrees(math.atan2(ty - 32, tx - 64))) % 360
    f = _font(18)
    r.blit(f.render(f"RNG {rng:03d}", True, WHITE), (8, 8))
    r.blit(f.render(f"AZ  {az:03d}", True, WHITE), (8, 26))
    if abs(math.sin(t * 0.9)) < 0.25 and int(t * 4) % 2 == 0:
        _center(r, "LOCK", 30, 44)

# 7. WAVEFORM
def _waveform(t, l, r):
    for surf, ph in ((l, 0.0), (r, math.pi / 3)):
        for i in range(16):
            hgt = abs(math.sin(t * 2.2 + i * 0.55 + ph)) * 0.7 + abs(math.sin(t * 5.1 + i)) * 0.3
            hpx = max(2, int(hgt * (H - 12)))
            pygame.draw.rect(surf, WHITE, (4 + i * 8, (H - hpx) // 2, 5, hpx))

# 8. COUNTDOWN
def _countdown(t, l, r):
    remaining = 60 - int(t % 60)
    _center(l, "T-MINUS", 16, 4)
    _center(l, f"{remaining:02d}", 48, 16)
    _center(r, "SEQ", 20, 6)
    frac = 1.0 - (t % 60) / 60.0
    pygame.draw.rect(r, WHITE, (10, 44, int(108 * frac), 8))
    pygame.draw.rect(r, WHITE, (10, 44, 108, 8), 1)
    if remaining <= 10 and int(t * 3) % 2 == 0:
        _center(r, "ARMED", 24, 24)

# 9. STATIC
def _static(t, l, r):
    for surf in (l, r):
        for _ in range(350):
            surf.fill(WHITE, (random.randint(0, W - 2), random.randint(0, H - 1),
                              random.randint(1, 2), 1))
        if random.random() < 0.3:
            surf.fill(WHITE, (0, random.randint(0, H - 3), W, 2))

# 10. NEURAL MESH (Rotating 3D Wireframe Mesh)
def _neural_mesh(t, l, r):
    nodes = [
        (-24, -16, 0), (24, -16, 0), (0, 20, 0),
        (-14, 0, 18), (14, 0, 18), (0, -10, -18)
    ]
    edges = [(0,1), (1,2), (2,0), (0,3), (1,4), (2,3), (2,4), (3,4), (0,5), (1,5)]
    ang = t * 1.2
    for surf, dir_mul in ((l, 1), (r, -1)):
        proj = []
        for x, y, z in nodes:
            # Rotate around Y axis
            rx = x * math.cos(ang * dir_mul) - z * math.sin(ang * dir_mul)
            rz = x * math.sin(ang * dir_mul) + z * math.cos(ang * dir_mul)
            # Perspective project
            scale = 45.0 / (rz + 60.0)
            px = int(64 + rx * scale)
            py = int(32 + y * scale)
            proj.append((px, py))
            pygame.draw.circle(surf, WHITE, (px, py), 2)
        for u, v in edges:
            pygame.draw.line(surf, WHITE, proj[u], proj[v], 1)
        _center(surf, "NEURAL SYNC", 14, 2)

# 11. COMPASS HUD (Tactical Heading Tape & Horizon)
def _compass_hud(t, l, r):
    hdg = int((t * 20.0) % 360)
    for surf in (l, r):
        # Center horizon ladder
        cy = 32 + int(math.sin(t * 1.5) * 8)
        pygame.draw.line(surf, WHITE, (32, cy), (54, cy), 1)
        pygame.draw.line(surf, WHITE, (74, cy), (96, cy), 1)
        pygame.draw.line(surf, WHITE, (54, cy), (54, cy + 4), 1)
        pygame.draw.line(surf, WHITE, (74, cy), (74, cy + 4), 1)
        pygame.draw.circle(surf, WHITE, (64, cy), 2, 1)

        # Top Heading Tape
        pygame.draw.rect(surf, WHITE, (14, 4, 100, 14), 1)
        f = _font(14)
        h_str = f"HDG {hdg:03d}"
        surf.blit(f.render(h_str, True, WHITE), (36, 6))

# 12. HEX DUMP (Scrolling Matrix Bytes)
def _hex_dump(t, l, r):
    f = _font(13)
    seed = int(t * 8)
    for surf, offset in ((l, 0), (r, 5)):
        y = 6
        for row in range(4):
            addr = f"0x{(seed + row + offset) * 16 & 0xFFFF:04X}"
            b1 = (seed * 37 + row * 19 + offset) & 0xFF
            b2 = (seed * 43 + row * 23 + offset) & 0xFF
            b3 = (seed * 59 + row * 29 + offset) & 0xFF
            line = f"{addr} {b1:02X} {b2:02X} {b3:02X}"
            surf.blit(f.render(line, True, WHITE), (6, y))
            y += 14

# 13. CROSSHAIR 3D (Precision Holographic Target)
def _crosshair_3d(t, l, r):
    cx, cy = 64, 32
    for surf in (l, r):
        # Outer dynamic square
        size = int(22 + math.sin(t * 3.0) * 4)
        pygame.draw.rect(surf, WHITE, (cx - size, cy - size, size * 2, size * 2), 1)
        # Diamond reticle
        pygame.draw.lines(surf, WHITE, True, [(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)], 1)
        # Center dot
        pygame.draw.circle(surf, WHITE, (cx, cy), 1)
        # Target lock brackets
        pygame.draw.line(surf, WHITE, (cx - size - 6, cy), (cx - size, cy), 2)
        pygame.draw.line(surf, WHITE, (cx + size + 6, cy), (cx + size, cy), 2)
        pygame.draw.line(surf, WHITE, (cx, cy - size - 6), (cx, cy - size), 2)
        pygame.draw.line(surf, WHITE, (cx, cy + size + 6), (cx, cy + size), 2)
    _center(r, "LOCK", 16, 50)

# 14. SIGNAL SPECTRUM (RF Waterfall Bars)
def _signal_spectrum(t, l, r):
    for surf, phase in ((l, 0), (r, 1.2)):
        for i in range(16):
            h_val = abs(math.sin(t * 3.5 + i * 0.4 + phase)) * 0.6 + abs(math.sin(t * 6.0 + i * 1.1)) * 0.4
            bar_h = int(h_val * 48)
            x = 8 + i * 7
            y = 56 - bar_h
            pygame.draw.rect(surf, WHITE, (x, y, 5, bar_h))
            # Peak dot
            pygame.draw.rect(surf, WHITE, (x, max(4, y - 3), 5, 1))
    _center(l, "SPECTRUM", 13, 2)
    _center(r, "2.4 GHz", 13, 2)

# 15. EYE RETICLE (Biometric Iris Lock)
def _eye_reticle(t, l, r):
    cx, cy = 64, 32
    ang = t * 2.5
    for surf in (l, r):
        # Dual counter-rotating arcs
        for r_len in (14, 22, 28):
            pygame.draw.circle(surf, WHITE, (cx, cy), r_len, 1)
        for i in range(4):
            a = ang + i * (math.pi / 2)
            px = int(cx + math.cos(a) * 28)
            py = int(cy + math.sin(a) * 28)
            pygame.draw.line(surf, WHITE, (cx, cy), (px, py), 1)
        pygame.draw.circle(surf, WHITE, (cx, cy), 5)
    _center(l, "OCULAR", 14, 4)
    _center(r, "ANALYSIS", 14, 4)

VISOR_FX = {
    "RADAR": _radar,
    "SCANNER": _scanner,
    "VITALS": _vitals,
    "CODE RAIN": _code_rain,
    "GLITCH": _glitch,
    "TARGET": _target,
    "WAVEFORM": _waveform,
    "COUNTDOWN": _countdown,
    "STATIC": _static,
    "NEURAL MESH": _neural_mesh,
    "COMPASS HUD": _compass_hud,
    "HEX DUMP": _hex_dump,
    "CROSSHAIR 3D": _crosshair_3d,
    "SIGNAL SPECTRUM": _signal_spectrum,
    "EYE RETICLE": _eye_reticle,
}
