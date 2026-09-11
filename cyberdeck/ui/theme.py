import pygame

class CyberpunkTheme:
    def __init__(self, name, primary, secondary, accent, bg, surface_bg, text_primary, text_dim, border, danger, warning):
        self.name = name
        self.primary = primary          # Main UI line / title color
        self.secondary = secondary      # Sub-headers and active buttons
        self.accent = accent            # High-visibility alerts / reticles
        self.bg = bg                    # Screen background
        self.surface_bg = surface_bg    # Widget panel background
        self.text_primary = text_primary# High-contrast readable text
        self.text_dim = text_dim        # Subdued telemetry labels
        self.border = border            # Widget framing borders
        self.danger = danger            # Breach / intrusion red
        self.warning = warning          # Alerts / cautions

class ThemeManager:
    """
    Manages authentic Cyberpunk 2077 and Edgerunners color palettes across the OS.
    """
    def __init__(self):
        self.themes = {
            "CYBERPUNK_2077": CyberpunkTheme(
                name="CYBERPUNK 2077",
                primary=(252, 238, 9),       # Iconic Cyber Yellow
                secondary=(0, 240, 255),     # Tech Cyan
                accent=(255, 0, 60),         # Arasaka Crimson
                bg=(13, 13, 17),             # Dark Gunmetal
                surface_bg=(22, 22, 28),     # Carbon Surface
                text_primary=(252, 238, 9),  # Cyber Yellow Text
                text_dim=(160, 160, 100),    # Muted Gold
                border=(0, 240, 255),        # Cyan Border
                danger=(255, 0, 60),         # Neon Red
                warning=(255, 140, 0),       # High-vis Orange
            ),
            "ARASAKA_CORP": CyberpunkTheme(
                name="ARASAKA CORP",
                primary=(255, 26, 42),       # Arasaka Blood Red
                secondary=(255, 255, 255),   # Tactical White
                accent=(255, 200, 80),       # Amber Warning
                bg=(6, 6, 8),                # Pitch Black
                surface_bg=(32, 6, 10),      # Deep Crimson
                text_primary=(255, 60, 60),  # Red Text
                text_dim=(180, 80, 80),      # Subdued Burgundy
                border=(255, 26, 42),        # Red Border
                danger=(255, 0, 0),          # Bright Red
                warning=(255, 180, 0),       # Amber
            ),
            "TRAUMA_TEAM": CyberpunkTheme(
                name="TRAUMA TEAM",
                primary=(0, 229, 255),       # Medical Cyan
                secondary=(255, 255, 255),   # Sterile White
                accent=(255, 145, 0),        # Trauma Orange
                bg=(6, 17, 24),              # Medical Navy
                surface_bg=(14, 36, 48),     # Slate Blue
                text_primary=(0, 229, 255),  # Cyan Text
                text_dim=(80, 160, 180),     # Muted Cyan
                border=(0, 229, 255),        # Medical Cyan Border
                danger=(255, 50, 50),        # Triage Red
                warning=(255, 145, 0),       # Trauma Orange
            ),
            "MILITECH_TACTICAL": CyberpunkTheme(
                name="MILITECH TACTICAL",
                primary=(255, 179, 0),       # Militech Amber
                secondary=(255, 230, 0),     # High-vis Gold
                accent=(255, 80, 0),         # Ordnance Orange
                bg=(12, 12, 10),             # Industrial Black
                surface_bg=(28, 26, 18),     # Carbon Gold
                text_primary=(255, 179, 0),  # Amber Text
                text_dim=(160, 130, 50),     # Muted Amber
                border=(255, 179, 0),        # Amber Border
                danger=(255, 40, 40),        # Threat Red
                warning=(255, 179, 0),       # Amber Warning
            ),
            "NETRUNNER_MATRIX": CyberpunkTheme(
                name="NETRUNNER PHOSPHOR",
                primary=(0, 255, 100),       # Phosphor Green
                secondary=(50, 255, 180),    # Bright Cyan-Green
                accent=(0, 255, 255),        # Electric Cyan
                bg=(0, 10, 2),               # Terminal Black
                surface_bg=(0, 22, 8),       # Deep Phosphor
                text_primary=(0, 255, 100),  # Green Text
                text_dim=(0, 150, 60),       # Dim Green
                border=(0, 255, 100),        # Green Border
                danger=(255, 50, 50),        # Red Alert
                warning=(255, 200, 0),       # Amber Alert
            ),
            "EDGERUNNER_NEON": CyberpunkTheme(
                name="EDGERUNNER NEON",
                primary=(255, 0, 128),       # Neon Magenta / Hot Pink
                secondary=(0, 255, 255),     # Electric Cyan
                accent=(255, 240, 0),        # Cyber Yellow
                bg=(14, 5, 28),              # Deep Violet
                surface_bg=(30, 10, 50),     # Neon Purple
                text_primary=(255, 60, 160), # Magenta Text
                text_dim=(160, 80, 180),     # Muted Purple
                border=(255, 0, 128),        # Magenta Border
                danger=(255, 20, 80),        # Red Pink
                warning=(255, 240, 0),       # Acid Yellow
            ),
        }
        self.theme_keys = list(self.themes.keys())
        self.current_idx = 0
        self.current = self.themes[self.theme_keys[self.current_idx]]

    def cycle_theme(self):
        self.current_idx = (self.current_idx + 1) % len(self.theme_keys)
        self.current = self.themes[self.theme_keys[self.current_idx]]
        return self.current

    def set_theme(self, key):
        if key in self.themes:
            self.current_idx = self.theme_keys.index(key)
            self.current = self.themes[key]
        return self.current

theme_manager = ThemeManager()
