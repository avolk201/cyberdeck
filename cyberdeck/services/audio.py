class DummyAudioEngine:
    def __init__(self):
        self.muted = True
    
    def init(self):
        pass
        
    def toggle_mute(self):
        return True
        
    def __getattr__(self, name):
        # Return a dummy function for any missing method (like glitch_zap, target_lock, etc.)
        def dummy_method(*args, **kwargs):
            pass
        return dummy_method

audio_engine = DummyAudioEngine()
