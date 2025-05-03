import json

class Config:
    def __init__(self, filename='config.json'):
        self.filename = filename
        self.config = self.load_config()
    
    def load_config(self):
        try:
            with open(self.filename) as f:
                return json.load(f)
        except OSError:
            # Return default config if file doesn't exist
            return {
                "osc_ip": "10.81.95.148",
                "osc_port": 53000,
                "pins": list(range(2, 10)),
                "addresses": ["/cue/1/go", "/cue/2/go", "/cue/3/go", "/cue/4/go", "/cue/5/go", "/cue/6/go", "/cue/7/go", "/cue/8/go"]
            }
    
    def save_config(self):
        with open(self.filename, 'w') as f:
            json.dump(self.config, f)