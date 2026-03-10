import pigpio
import time
from flask import Flask, render_template_string, jsonify, request

# ==========================================
#      CONFIGURATION (GPIO PINS)
# ==========================================
# UPDATED MAPPING TO MATCH YOUR PHYSICAL WIRING
# Format: [Phase_A, Phase_B] using BCM Numbers
ENCODER_PINS = [
    [27, 22],  # Encoder 1: Physical Pins 13 & 15 (GPIO 27, 22)
    [20, 21],  # Encoder 2: Physical Pins 38 & 40 (GPIO 20, 21)
    [17, 25],  # Encoder 3: Physical Pins 11 & 22 (GPIO 17, 25)
    [5,  6]    # Encoder 4: Physical Pins 29 & 31 (GPIO 5, 6)
]

app = Flask(__name__)

# ==========================================
#      HIGH-SPEED ENCODER CLASS
# ==========================================
class EncoderReader:
    def __init__(self, pi, gpioA, gpioB):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.pos = 0
        self.levA = 0
        self.levB = 0
        self.lastGpio = None

        # 1. Set as Inputs
        self.pi.set_mode(gpioA, pigpio.INPUT)
        self.pi.set_mode(gpioB, pigpio.INPUT)

        # 2. ENABLE INTERNAL PULL-UP (Crucial for Open Collector)
        self.pi.set_pull_up_down(gpioA, pigpio.PUD_UP)
        self.pi.set_pull_up_down(gpioB, pigpio.PUD_UP)

        # 3. Setup Interrupts
        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

    def _pulse(self, gpio, level, tick):
        """Hardware Interrupt Callback"""
        if gpio == self.gpioA:
            self.levA = level
        else:
            self.levB = level

        # --- TESTING MODE (Switch Debounce Bypass) ---
        # Change 'True' to 'gpio != self.lastGpio' when connecting real encoders!
        if True: 
            self.lastGpio = gpio
            if gpio == self.gpioA and level == 1:
                if self.levB == 1: self.pos += 1
                else: self.pos -= 1
            elif gpio == self.gpioB and level == 1:
                if self.levA == 1: self.pos -= 1
                else: self.pos += 1
    
    def reset(self):
        self.pos = 0

# ==========================================
#      INITIALIZATION
# ==========================================
pi = pigpio.pi()
if not pi.connected:
    print("CRITICAL ERROR: 'pigpiod' is not running.")
    print("Please run: sudo systemctl start pigpiod")
    exit()

# Create list of 4 Encoder Objects
encoders = []
for pins in ENCODER_PINS:
    encoders.append(EncoderReader(pi, pins[0], pins[1]))

print(f"--- Encoder System Online (Port 5001) ---")

# ==========================================
#      WEB UI
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Encoder Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; background-color: #2c3e50; color: white; padding: 20px; }
        h1 { margin-bottom: 30px; }
        .container { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; }
        
        .card { 
            background: #34495e; padding: 20px; width: 220px; 
            border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); 
            border: 1px solid #465f75;
        }
        
        h2 { color: #3498db; margin: 0 0 10px 0; font-size: 22px; }
        
        .count { 
            font-size: 48px; font-weight: bold; color: #2ecc71; 
            font-family: monospace; margin: 15px 0; 
            text-shadow: 0 0 10px rgba(46, 204, 113, 0.2);
        }
        
        button { 
            background-color: #e67e22; color: white; border: none; 
            padding: 10px 20px; border-radius: 6px; cursor: pointer; 
            font-size: 16px; transition: background 0.2s;
        }
        button:hover { background-color: #d35400; }
    </style>
    <script>
        function updateCounts() {
            fetch('/get_positions')
                .then(res => res.json())
                .then(data => {
                    data.positions.forEach((pos, idx) => {
                        let el = document.getElementById('cnt_' + idx);
                        if(el) el.innerText = pos;
                    });
                });
        }

        function zero(idx) {
            fetch('/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: idx})
            })
            .then(updateCounts);
        }

        setInterval(updateCounts, 100); // 10 updates per second
    </script>
</head>
<body>
    <h1>📟 Position Feedback System</h1>
    
    <div class="container">
        {% for i in range(4) %}
        <div class="card">
            <h2>Encoder {{ i + 1 }}</h2>
            <div class="count" id="cnt_{{ i }}">0</div>
            <button onclick="zero({{ i }})">Zero Position</button>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/get_positions')
def handle_get():
    # Return list of current positions
    vals = [e.pos for e in encoders]
    return jsonify(positions=vals)

@app.route('/reset', methods=['POST'])
def handle_reset():
    data = request.get_json()
    idx = int(data.get('id', 0))
    if 0 <= idx < len(encoders):
        encoders[idx].reset()
    return jsonify(success=True)

if __name__ == '__main__':
    # Running on Port 5001 to avoid conflict with Crane app
    app.run(host='0.0.0.0', port=5001, debug=False)