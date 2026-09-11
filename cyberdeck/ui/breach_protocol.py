import pygame
import random
import time
from .theme import theme_manager
from .. import runtime
from ..services.audio import audio_engine
from ..stats import session_stats

HEX_TOKENS = ["1C", "BD", "55", "E9", "FF", "7A"]

DAEMON_POOL = [
    {"name": "BASIC DATAMINE", "desc": "+€$ 750 // COMPONENTS", "reward_credits": 750, "reward_text": "+€$ 750 & Rare Crafting Specs", "len": 2},
    {"name": "ADVANCED DATAMINE", "desc": "+€$ 1,450 // QUICKHACK", "reward_credits": 1450, "reward_text": "+€$ 1,450 & Tier-3 Quickhack", "len": 3},
    {"name": "ICEPICK.exe", "desc": "-3 RAM QUICKHACK COST", "reward_credits": 500, "reward_text": "-3 RAM Cost to all Quickhacks", "len": 3},
    {"name": "MASS VULNERABILITY", "desc": "-30% ICE RESISTANCE", "reward_credits": 600, "reward_text": "Target Network ICE Resist -30%", "len": 3},
    {"name": "OPTICS REBOOT DAEMON", "desc": "NETWORK SENSORS BLINDED", "reward_credits": 400, "reward_text": "All Security Optics Offline 60s", "len": 2},
]

class HexBreachProtocol:
    """
    Authentic Cyberpunk 2077 Breach Protocol / ICE Breaker Minigame.
    Features:
      - 5x5 Code Matrix with guaranteed solvable random-walk paths.
      - Alternating row/column selection mechanics.
      - Authentic per-daemon sequence step matching.
      - Pre-breach planning: Timer does NOT count down until first byte is selected!
      - Interactive Cursor for physical buttons (Left/Right step, Action commit) + Touchscreen.
      - Crosshair projection & target sequence token matching highlights.
      - Cyberpunk 2077 Victory / Failure readout modal with extracted rewards.
    """
    def __init__(self, rect, font):
        self.rect = rect
        self.font = font
        self.small_font = pygame.font.SysFont("courier", 15)
        self.large_font = pygame.font.SysFont("courier", 24, bold=True)
        self.mono_bold = pygame.font.SysFont("courier", 18, bold=True)
        self.grid_size = 5
        self.buffer_size = 6
        # Adaptive difficulty: consecutive successful breaches (the wearer's
        # streak) tighten the clock, up to MAX_THREAT. A failure resets it.
        self.base_time = 25.0
        self.min_time = 13.0
        self.time_step = 2.0
        self.max_threat = 6
        self.time_limit = self.base_time
        self.reset()

    def threat_level(self):
        return max(0, min(session_stats.streak, self.max_threat))

    def _adaptive_time(self):
        return max(self.min_time,
                   self.base_time - self.time_step * self.threat_level())

    def reset(self):
        # 1. Generate 5x5 Code Matrix
        self.grid = [[random.choice(HEX_TOKENS) for _ in range(self.grid_size)] for _ in range(self.grid_size)]

        # 2. Pick 3 distinct daemons
        selected_templates = random.sample(DAEMON_POOL, 3)

        # 3. Embed guaranteed solvable sequences via random walk from Row 0
        walk_r = 0
        walk_c = random.randint(0, self.grid_size - 1)
        walk_is_row = True
        walk_path = [(walk_r, walk_c)]

        for _ in range(self.buffer_size + 1):
            if walk_is_row:
                # Next move along column (vertical)
                next_r = random.choice([r for r in range(self.grid_size) if r != walk_r])
                walk_path.append((next_r, walk_c))
                walk_r = next_r
                walk_is_row = False
            else:
                # Next move along row (horizontal)
                next_c = random.choice([c for c in range(self.grid_size) if c != walk_c])
                walk_path.append((walk_r, next_c))
                walk_c = next_c
                walk_is_row = True

        walk_tokens = [self.grid[r][c] for (r, c) in walk_path]

        self.daemons = []
        for i, t in enumerate(selected_templates):
            req_len = t["len"]
            # Slice feasible overlapping sequence from the walk path
            start_idx = min(i, max(0, len(walk_tokens) - req_len))
            daemon_seq = walk_tokens[start_idx : start_idx + req_len]
            if len(daemon_seq) < req_len:
                daemon_seq = [random.choice(HEX_TOKENS) for _ in range(req_len)]

            self.daemons.append({
                "name": t["name"],
                "desc": t["desc"],
                "reward_credits": t["reward_credits"],
                "reward_text": t["reward_text"],
                "seq": daemon_seq,
                "matched_index": 0,
                "uploaded": False
            })

        self.buffer = []
        self.is_row_selection = True
        self.active_index = 0  # Initial selection is along Row 0
        self.cursor_idx = 0   # Index among valid selectable cells
        self.selected_coords = []
        self.timer_started = False
        self.start_time = 0.0
        self.time_remaining = self.time_limit
        self.solved = False
        self.failed = False
        self.total_credits_earned = 0
        self.cell_rects = {}
        self.hover_token = None
        self.modal_dismiss_btn = pygame.Rect(self.rect.centerx - 120, self.rect.bottom - 60, 240, 42)

    def _get_selectable_coords(self):
        """Returns list of (r, c) tuples currently selectable along the active axis."""
        selectable = []
        if self.is_row_selection:
            r = self.active_index
            for c in range(self.grid_size):
                if (r, c) not in self.selected_coords:
                    selectable.append((r, c))
        else:
            c = self.active_index
            for r in range(self.grid_size):
                if (r, c) not in self.selected_coords:
                    selectable.append((r, c))
        return selectable

    def get_current_cursor_coord(self):
        selectable = self._get_selectable_coords()
        if not selectable:
            return None
        self.cursor_idx = max(0, min(self.cursor_idx, len(selectable) - 1))
        return selectable[self.cursor_idx]

    def move_cursor(self, delta):
        """Moves cursor across selectable cells in current active axis (Left/Right buttons)."""
        selectable = self._get_selectable_coords()
        if not selectable:
            return
        self.cursor_idx = (self.cursor_idx + delta) % len(selectable)
        cur = selectable[self.cursor_idx]
        self.hover_token = self.grid[cur[0]][cur[1]]

    def commit_cursor_selection(self):
        """Commits the move at the current cursor position (Action button short click)."""
        coord = self.get_current_cursor_coord()
        if coord:
            return self._commit_move(coord[0], coord[1])
        return False

    def handle_tap(self, pos):
        if self.solved or self.failed:
            if self.modal_dismiss_btn.collidepoint(pos):
                fsm = runtime.fsm
                if fsm:
                    fsm.finish_run()
                return True
            return False

        # Direct cell tap on code matrix
        for (r, c), cell_rect in self.cell_rects.items():
            if cell_rect.collidepoint(pos):
                if (r, c) in self.selected_coords:
                    continue

                # Check valid move along active axis
                if self.is_row_selection and r == self.active_index:
                    return self._commit_move(r, c)
                elif not self.is_row_selection and c == self.active_index:
                    return self._commit_move(r, c)
        return False

    def _commit_move(self, r, c):
        if self.solved or self.failed:
            return False

        # Start timer on first move if not already started (Authentic Cyberpunk 2077 rule!)
        if not self.timer_started:
            self.timer_started = True
            self.start_time = time.time()

        val = self.grid[r][c]
        self.buffer.append(val)
        self.selected_coords.append((r, c))
        self.hover_token = val
        audio_engine.ui_blip()

        # Update per-daemon sequential matching (Cyberpunk 2077 logic)
        newly_uploaded = False
        for d in self.daemons:
            if not d["uploaded"]:
                target_token = d["seq"][d["matched_index"]]
                if val == target_token:
                    d["matched_index"] += 1
                    if d["matched_index"] >= len(d["seq"]):
                        d["uploaded"] = True
                        newly_uploaded = True
                        self.total_credits_earned += d["reward_credits"]
                else:
                    # Check if token matches start of sequence
                    if val == d["seq"][0]:
                        d["matched_index"] = 1
                    else:
                        d["matched_index"] = 0

        if newly_uploaded:
            audio_engine.target_lock()
            # Flash Nano LEDs green on daemon upload
            try:
                from ..hw.accessories import nano_accessories
                if nano_accessories:
                    nano_accessories.send_color(0, 255, 120)
            except:
                pass

        # Switch Axis
        if self.is_row_selection:
            self.is_row_selection = False
            self.active_index = c
        else:
            self.is_row_selection = True
            self.active_index = r

        self.cursor_idx = 0

        # Check Win/Loss conditions
        all_uploaded = all(d["uploaded"] for d in self.daemons)
        buffer_full = len(self.buffer) >= self.buffer_size
        any_uploaded = any(d["uploaded"] for d in self.daemons)

        if all_uploaded:
            self.solved = True
        elif buffer_full:
            if any_uploaded:
                self.solved = True
            else:
                self.failed = True
                audio_engine.glitch_zap()

        return True

    def update(self):
        if not self.solved and not self.failed:
            if self.timer_started:
                elapsed = time.time() - self.start_time
                self.time_remaining = max(0.0, self.time_limit - elapsed)
                if self.time_remaining <= 0.0:
                    if any(d["uploaded"] for d in self.daemons):
                        self.solved = True
                    else:
                        self.failed = True
                        audio_engine.glitch_zap()
            else:
                # Pre-breach: keep the clock in sync with the wearer's current
                # streak. record_run() updates the streak before a new run can
                # start, so this always reflects the latest result.
                self.time_limit = self._adaptive_time()
                self.time_remaining = self.time_limit

        # Update hover token from current cursor
        coord = self.get_current_cursor_coord()
        if coord:
            self.hover_token = self.grid[coord[0]][coord[1]]

    def render(self, surface):
        theme = theme_manager.current
        pygame.draw.rect(surface, theme.surface_bg, self.rect)
        pygame.draw.rect(surface, theme.border, self.rect, 2)

        now = time.time()

        # ----------------------------------------------------
        # 1. Header Bar: Cyberpunk Breadcrumb & Timer
        # ----------------------------------------------------
        title_surf = self.large_font.render(">> ACCESS POINT // BREACH PROTOCOL <<", True, theme.primary)
        surface.blit(title_surf, (self.rect.x + 20, self.rect.y + 12))

        # Threat level (from the wearer's win streak) ramps the difficulty.
        threat = self.threat_level()
        threat_col = theme.danger if threat >= 4 else (theme.warning if threat >= 2 else theme.text_dim)
        threat_surf = self.small_font.render(f"THREAT LVL {threat} // STREAK {session_stats.streak}", True, threat_col)
        surface.blit(threat_surf, (self.rect.x + 20, self.rect.y + 40))

        if not self.timer_started:
            timer_str = f"BREACH TIME: {self.time_limit:.1f}s [STANDBY]"
            timer_col = theme.secondary
        else:
            timer_str = f"BREACH TIME: {self.time_remaining:.1f}s"
            timer_col = theme.danger if self.time_remaining < 7.0 and int(now * 4) % 2 == 0 else (theme.danger if self.time_remaining < 7.0 else theme.secondary)

        timer_txt = self.font.render(timer_str, True, timer_col)
        surface.blit(timer_txt, (self.rect.right - timer_txt.get_width() - 25, self.rect.y + 16))

        # ----------------------------------------------------
        # 2. Memory Buffer Display (Top Left)
        # ----------------------------------------------------
        buf_y = self.rect.y + 50
        buf_lbl = self.small_font.render("MEMORY BUFFER:", True, theme.text_dim)
        surface.blit(buf_lbl, (self.rect.x + 20, buf_y + 8))

        slot_w, slot_h = 44, 32
        for i in range(self.buffer_size):
            bx = self.rect.x + 160 + i * (slot_w + 8)
            slot_rect = pygame.Rect(bx, buf_y, slot_w, slot_h)
            is_filled = i < len(self.buffer)
            is_next = i == len(self.buffer) and not (self.solved or self.failed)

            pygame.draw.rect(surface, theme.bg, slot_rect)
            border_c = theme.primary if is_filled else (theme.secondary if is_next else theme.border)
            pygame.draw.rect(surface, border_c, slot_rect, 2 if (is_filled or is_next) else 1)

            if is_filled:
                t_val = self.mono_bold.render(self.buffer[i], True, theme.primary)
                surface.blit(t_val, (slot_rect.centerx - t_val.get_width() // 2, slot_rect.centery - t_val.get_height() // 2))
            elif is_next:
                # Pulsing cursor in empty slot
                if int(now * 3) % 2 == 0:
                    pygame.draw.rect(surface, (theme.secondary[0]//3, theme.secondary[1]//3, theme.secondary[2]//3), slot_rect.inflate(-6, -6))

        # Status text below buffer
        if not self.timer_started:
            status_prompt = "SELECT INITIAL VECTOR FROM TOP ROW (ROW 0)"
            pr_col = theme.secondary
        elif self.is_row_selection:
            status_prompt = f"ACTIVE AXIS: ROW {self.active_index + 1} (HORIZONTAL)"
            pr_col = theme.primary
        else:
            status_prompt = f"ACTIVE AXIS: COLUMN {self.active_index + 1} (VERTICAL)"
            pr_col = theme.primary
        p_surf = self.small_font.render(status_prompt, True, pr_col)
        surface.blit(p_surf, (self.rect.x + 20, buf_y + 40))

        # ----------------------------------------------------
        # 3. 5x5 Code Matrix (Left Panel)
        # ----------------------------------------------------
        grid_start_x = self.rect.x + 25
        grid_start_y = self.rect.y + 115
        cell_size = 52
        cell_gap = 8
        self.cell_rects = {}

        cur_coord = self.get_current_cursor_coord()

        # Render Active Guide Bar (Authentic Cyberpunk 2077 row/col highlighting)
        if not (self.solved or self.failed):
            if self.is_row_selection:
                guide_y = grid_start_y + self.active_index * (cell_size + cell_gap) - 4
                guide_w = self.grid_size * (cell_size + cell_gap) - cell_gap + 8
                pygame.draw.rect(surface, (theme.secondary[0] // 5, theme.secondary[1] // 5, theme.secondary[2] // 5), (grid_start_x - 4, guide_y, guide_w, cell_size + 8))
                pygame.draw.rect(surface, theme.secondary, (grid_start_x - 4, guide_y, guide_w, cell_size + 8), 1)
            else:
                guide_x = grid_start_x + self.active_index * (cell_size + cell_gap) - 4
                guide_h = self.grid_size * (cell_size + cell_gap) - cell_gap + 8
                pygame.draw.rect(surface, (theme.secondary[0] // 5, theme.secondary[1] // 5, theme.secondary[2] // 5), (guide_x, grid_start_y - 4, cell_size + 8, guide_h))
                pygame.draw.rect(surface, theme.secondary, (guide_x, grid_start_y - 4, cell_size + 8, guide_h), 1)

            # Projected Next Axis Crosshair Preview from current cursor
            if cur_coord:
                cr, cc = cur_coord
                if self.is_row_selection:
                    # Next move will be along column cc
                    proj_x = grid_start_x + cc * (cell_size + cell_gap) - 2
                    proj_h = self.grid_size * (cell_size + cell_gap) - cell_gap + 4
                    pygame.draw.rect(surface, (40, 40, 40), (proj_x, grid_start_y - 2, cell_size + 4, proj_h), 1)
                else:
                    # Next move will be along row cr
                    proj_y = grid_start_y + cr * (cell_size + cell_gap) - 2
                    proj_w = self.grid_size * (cell_size + cell_gap) - cell_gap + 4
                    pygame.draw.rect(surface, (40, 40, 40), (grid_start_x - 2, proj_y, proj_w, cell_size + 4), 1)

        # Render Grid Cells
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                cx = grid_start_x + c * (cell_size + cell_gap)
                cy = grid_start_y + r * (cell_size + cell_gap)
                c_rect = pygame.Rect(cx, cy, cell_size, cell_size)
                self.cell_rects[(r, c)] = c_rect

                is_selected = (r, c) in self.selected_coords
                is_selectable = (self.is_row_selection and r == self.active_index) or (not self.is_row_selection and c == self.active_index)
                is_cursor = (cur_coord == (r, c)) and not (self.solved or self.failed)

                if is_selected:
                    pygame.draw.rect(surface, (15, 15, 15), c_rect)
                    val_txt = self.small_font.render("[--]", True, (70, 70, 70))
                elif is_cursor:
                    # Bright Cursor Highlight (Cyberpunk yellow / primary)
                    pygame.draw.rect(surface, (theme.primary[0]//2, theme.primary[1]//2, theme.primary[2]//2), c_rect)
                    pygame.draw.rect(surface, (255, 255, 255), c_rect, 3)
                    val_txt = self.mono_bold.render(self.grid[r][c], True, (255, 255, 255))
                elif is_selectable:
                    bg_col = (30, 30, 15) if not (self.solved or self.failed) else theme.bg
                    pygame.draw.rect(surface, bg_col, c_rect)
                    pygame.draw.rect(surface, theme.primary, c_rect, 2)
                    val_txt = self.font.render(self.grid[r][c], True, theme.primary)
                else:
                    pygame.draw.rect(surface, theme.bg, c_rect)
                    pygame.draw.rect(surface, (50, 50, 50), c_rect, 1)
                    val_txt = self.font.render(self.grid[r][c], True, theme.text_dim)

                surface.blit(val_txt, (c_rect.centerx - val_txt.get_width() // 2, c_rect.centery - val_txt.get_height() // 2))

        # ----------------------------------------------------
        # 4. Target Daemons Sequence Panel (Right Panel)
        # ----------------------------------------------------
        panel_x = grid_start_x + self.grid_size * (cell_size + cell_gap) + 25
        panel_w = self.rect.right - panel_x - 20
        panel_h = self.grid_size * (cell_size + cell_gap) - cell_gap + 8
        panel_rect = pygame.Rect(panel_x, grid_start_y - 4, panel_w, panel_h)
        pygame.draw.rect(surface, theme.bg, panel_rect)
        pygame.draw.rect(surface, theme.border, panel_rect, 1)

        p_title = self.small_font.render("TARGET DAEMONS // SEQUENCES", True, theme.secondary)
        surface.blit(p_title, (panel_x + 12, grid_start_y + 4))

        dy = grid_start_y + 30
        for d in self.daemons:
            is_up = d["uploaded"]
            d_box = pygame.Rect(panel_x + 8, dy, panel_w - 16, 74)
            box_border = (0, 255, 120) if is_up else theme.border
            box_bg = (10, 35, 20) if is_up else theme.surface_bg
            pygame.draw.rect(surface, box_bg, d_box)
            pygame.draw.rect(surface, box_border, d_box, 1)

            # Daemon Name & Status
            status_str = "[ UPLOADED ✓ ]" if is_up else f"[ MATCH: {d['matched_index']}/{len(d['seq'])} ]"
            status_col = (0, 255, 120) if is_up else theme.text_dim
            d_name = self.small_font.render(f"{d['name']:<18} {status_str}", True, status_col)
            surface.blit(d_name, (d_box.x + 8, d_box.y + 6))

            # Sequence Tokens with Token Highlighting (Cyberpunk 2077 matching highlight)
            seq_x = d_box.x + 10
            for idx, token in enumerate(d["seq"]):
                tok_box = pygame.Rect(seq_x, d_box.y + 28, 38, 26)
                is_token_matched = idx < d["matched_index"] or is_up
                is_token_hovered = (self.hover_token == token) and not is_up

                if is_token_matched:
                    pygame.draw.rect(surface, (0, 80, 40), tok_box)
                    pygame.draw.rect(surface, (0, 255, 120), tok_box, 1)
                    t_col = (0, 255, 120)
                elif is_token_hovered:
                    # Hover match glowing highlight!
                    pygame.draw.rect(surface, (100, 80, 0), tok_box)
                    pygame.draw.rect(surface, (255, 230, 0), tok_box, 2)
                    t_col = (255, 230, 0)
                else:
                    pygame.draw.rect(surface, theme.bg, tok_box)
                    pygame.draw.rect(surface, (70, 70, 70), tok_box, 1)
                    t_col = theme.text_primary

                t_surf = self.mono_bold.render(token, True, t_col)
                surface.blit(t_surf, (tok_box.centerx - t_surf.get_width() // 2, tok_box.centery - t_surf.get_height() // 2))

                # Arrow separator between tokens
                if idx < len(d["seq"]) - 1:
                    arr_surf = self.small_font.render(">", True, (100, 100, 100))
                    surface.blit(arr_surf, (tok_box.right + 2, tok_box.centery - arr_surf.get_height() // 2))
                    seq_x = tok_box.right + 12
                else:
                    seq_x = tok_box.right + 8

            # Reward summary text on bottom
            desc_surf = self.small_font.render(d["desc"], True, (0, 255, 120) if is_up else theme.text_dim)
            surface.blit(desc_surf, (d_box.x + 8, d_box.y + 56))

            dy += 82

        # ----------------------------------------------------
        # 5. Cyberpunk Victory / Failure Result Modal Overlay
        # ----------------------------------------------------
        if self.solved or self.failed:
            modal_w = 540
            modal_h = 320
            modal_rect = pygame.Rect(self.rect.centerx - modal_w // 2, self.rect.centery - modal_h // 2, modal_w, modal_h)

            # Dark translucent backing
            s_overlay = pygame.Surface((modal_w, modal_h))
            s_overlay.set_alpha(245)
            s_overlay.fill((10, 10, 15))
            surface.blit(s_overlay, modal_rect)

            border_c = (0, 255, 120) if self.solved else theme.danger
            pygame.draw.rect(surface, border_c, modal_rect, 2)

            # Header Banner
            b_text = ">> BREACH PROTOCOL // ACCESS GRANTED <<" if self.solved else ">> BREACH PROTOCOL // ACCESS DENIED <<"
            m_title = self.large_font.render(b_text, True, border_c)
            surface.blit(m_title, (modal_rect.centerx - m_title.get_width() // 2, modal_rect.y + 18))

            sub_txt = f"TOTAL CREDITS EXTRACTED: €$ {self.total_credits_earned}" if self.solved else "ICE DEFENSES TRIGGERED - CONNECTION TERMINATED"
            m_sub = self.font.render(sub_txt, True, theme.primary if self.solved else theme.danger)
            surface.blit(m_sub, (modal_rect.centerx - m_sub.get_width() // 2, modal_rect.y + 52))

            # Installed Daemons List
            my = modal_rect.y + 90
            for d in self.daemons:
                is_up = d["uploaded"]
                icon = "[✓]" if is_up else "[✗]"
                col = (0, 255, 120) if is_up else (140, 140, 140)
                d_line = self.small_font.render(f"{icon} {d['name']:<18} : {d['reward_text']}", True, col)
                surface.blit(d_line, (modal_rect.x + 25, my))
                my += 28

            # Dismiss Button
            self.modal_dismiss_btn = pygame.Rect(modal_rect.centerx - 130, modal_rect.bottom - 54, 260, 38)
            pygame.draw.rect(surface, (20, 20, 20), self.modal_dismiss_btn)
            pygame.draw.rect(surface, border_c, self.modal_dismiss_btn, 2)
            btn_txt = self.font.render("[ DISCONNECT & RETURN ]", True, border_c)
            surface.blit(btn_txt, (self.modal_dismiss_btn.centerx - btn_txt.get_width() // 2, self.modal_dismiss_btn.centery - btn_txt.get_height() // 2))
