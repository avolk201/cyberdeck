from .config import State

class CyberdeckFSM:
    def __init__(self):
        self.state = State.BOOT
        self.listeners = []

    def register_listener(self, callback):
        self.listeners.append(callback)

    def transition(self, new_state):
        if new_state != self.state:
            print(f"FSM Transition: {self.state} -> {new_state}")
            self.state = new_state
            self.notify()

    def notify(self):
        for listener in self.listeners:
            listener(self.state)

    # State specific triggers
    def boot_complete(self):
        if self.state == State.BOOT:
            self.transition(State.IDLE)
    
    def trigger_scan(self):
        if self.state in [State.IDLE, State.RUNNING]:
            self.transition(State.SCANNING)
            
    def trigger_run(self):
        if self.state in [State.IDLE, State.SCANNING]:
            self.transition(State.RUNNING)
            
    def trigger_alert(self):
        self.transition(State.ALERT)
        
    def resolve_alert(self):
        if self.state == State.ALERT:
            self.transition(State.COOLDOWN)
            
    def cooldown_complete(self):
        if self.state == State.COOLDOWN:
            self.transition(State.IDLE)
            
    def trigger_blackout(self):
        self.transition(State.BLACKOUT)
        
    def wake_from_blackout(self):
        if self.state == State.BLACKOUT:
            self.transition(State.BOOT)

    def trigger_target_lock(self):
        if self.state == State.IDLE:
            self.transition(State.TARGET_LOCK)
            
    def launch_counter_attack(self):
        if self.state == State.TARGET_LOCK:
            self.transition(State.RUNNING)
            
    def finish_run(self):
        if self.state == State.RUNNING:
            self.transition(State.IDLE)
