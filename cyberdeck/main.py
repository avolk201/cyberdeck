import os
import sys

# Synthesize mouse events from touch inputs (crucial for X11 kiosks)
os.environ.setdefault("SDL_MOUSE_TOUCH_EVENTS", "1")
os.environ.setdefault("SDL_TOUCH_MOUSE_EVENTS", "1")

# Detect if we are running without a window manager (e.g., at boot, via systemd, or SSH)
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    print("No display environment variable found. Defaulting to KMSDRM for direct rendering.")
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

import pygame
from .config import RESOLUTION, FPS, State
from .fsm import CyberdeckFSM
from .hw.pixels import PixelController
from .hw.button import NavButtons
from .hw.power import PowerManager
from .hw.oled import OledDisplay
from .hw.accessories import NanoAccessories
from .ui.screens import get_screen_for_state
from .ui.glitch import GlitchRenderer
from .ui.widgets import BREACH_EVENT, TARGET_LOCK_EVENT, RUN_COMPLETE_EVENT

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

def main():
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

    screen = init_display()
    pygame.display.set_caption("Cyberdeck OS")
    clock = pygame.time.Clock()

    fsm = CyberdeckFSM()
    glitch = GlitchRenderer(screen)

    pixels = PixelController()
    oled = OledDisplay()

    def on_nano_data(data):
        from . import config
        print(f"Nano data: {data}")
        if data.startswith("SW "):
            try: config.NANO_SW = int(data.split()[1])
            except: pass
        elif data.startswith("HR "):
            try: config.NANO_HR = int(data.split()[1])
            except: pass
            
        import time
        config.NANO_LAST_SEEN = time.time()

    accessories = NanoAccessories(callback=on_nano_data)
    power_manager = PowerManager()

    def on_state_change(new_state):
        pixels.set_state(new_state)
        accessories.broadcast(new_state)

    fsm.register_listener(on_state_change)
    

    def on_short_press():
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_short_press'):
            current_screen.handle_short_press()
        elif fsm.state == State.BOOT:
            fsm.boot_complete()
        elif fsm.state == State.BLACKOUT:
            fsm.wake_from_blackout()
        elif fsm.state != State.RUNNING:
            fsm.transition(State.RUNNING)

    def on_long_press():
        fsm.trigger_blackout()
        
    def on_left_press():
        from . import config
        fx_list = ["PULSE", "MATRIX", "CHASE", "STROBE", "MATRIX_SKULL", "MATRIX_RADAR"]
        current = getattr(config, "ACTIVE_FX", "PULSE")
        if current in fx_list:
            config.ACTIVE_FX = fx_list[(fx_list.index(current) + 1) % len(fx_list)]
        else:
            config.ACTIVE_FX = fx_list[0]
        
    def on_right_press():
        fsm.trigger_alert()
        
    def on_double_press():
        fsm.trigger_scan()
        
    def on_chord_press():
        fsm.transition(State.IDLE)

    nav_btns = NavButtons(on_left_press, on_right_press, on_short_press, on_long_press, on_double_press, on_chord=on_chord_press)

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
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_swipe_down'):
            current_screen.handle_swipe_down()
        elif fsm.state == State.IDLE:
            fsm.trigger_scan()
            
    def handle_long_touch():
        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'handle_long_touch'):
            current_screen.handle_long_touch()
        elif fsm.state == State.ALERT:
            on_short_press() 
        else:
            on_long_press()

    gestures = GestureRecognizer(handle_tap, handle_swipe_left, handle_swipe_right, handle_swipe_down, handle_long_touch)

    pixels.start()
    oled.start()

    running = True
    print("Cyberdeck OS started. Touchscreen gestures active!")

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    on_short_press()
                elif event.key == pygame.K_b:
                    on_long_press()
                elif event.key == pygame.K_RIGHT:
                    on_right_press()
                elif event.key == pygame.K_a:
                    on_double_press()
            elif event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP]:
                gestures.process_event(event)
            elif event.type == BREACH_EVENT:
                fsm.trigger_alert()
            elif event.type == TARGET_LOCK_EVENT:
                fsm.trigger_target_lock()
            elif event.type == pygame.USEREVENT + 3:
                fsm.launch_counter_attack()
            elif event.type == RUN_COMPLETE_EVENT:
                fsm.finish_run()
                idle_screen = get_screen_for_state(State.IDLE, screen)
                idle_screen.netmap.resolve_target(event.success)

        current_screen = get_screen_for_state(fsm.state, screen)
        if hasattr(current_screen, 'update'):
            current_screen.update()
            
        current_screen.render()
        glitch.render(fsm.state)
        
        pygame.display.flip()
        clock.tick(FPS)

    pixels.running = False
    oled.running = False
    accessories.running = False
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
