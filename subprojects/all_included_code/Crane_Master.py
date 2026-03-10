import pigpio
import time
import threading
import os
import sys
from flask import Flask, render_template_string, jsonify, request

# ==========================================
#      CONFIGURATION
# ==========================================
ADC_SCALING_FACTOR = 2.0016
HARDWARE_OFFSET = 8388608
HARDWARE_FULL_SCALE = 13.75

# FINAL PIN MAPPING (Moved Enc 2 to Safe Zone)
ENCODER_PINS = [
    [27, 22],  # Enc 1: Pins 13 & 15
    [20, 21],  # Enc 2: Pins 38 & 40 (GPIO 20, 21) <--- MOVED TO QUIET ZONE
    [25, 26],  # Enc 3: Pins 22 & 37
    [5,  6]    # Enc 4: Pins 29 & 31
]

app = Flask(__name__)

# ==========================================
#      HARDWARE DRIVER
# ==========================================
class FastCraneHardware:
    def __init__(self):
        self.connected = False
        self.dac_files = []
        self.dac_scale = 0.000305175
        self.dac_offset = 32768
        self.adc_dev = None

        try:
            # 1. INTELLIGENT DEVICE SEARCH
            base = "/sys/bus/iio/devices"
            dac_path = None
            adc_path = None
            
            if os.path.exists(base):
                for d in os.listdir(base):
                    if "iio:device" in d:
                        try:
                            name = open(f"{base}/{d}/name").read().strip()
                            if "ltc2688" in name: dac_path = f"{base}/{d}"
                            if "ad7124" in name: adc_path = f"{base}/{d}"
                        except: pass
            
            # Fallback
            if not dac_path: dac_path = "/sys/bus/iio/devices/iio:device0"
            if not adc_path: adc_path = "/sys/bus/iio/devices/iio:device1"

            print(f"✅ DAC Found: {dac_path}")
            print(f"✅ ADC Found: {adc_path}")

            # 2. SETUP DAC FILES
            for i in range(5):
                try: 
                    with open(f"{dac_path}/out_voltage{i}_powerdown", 'w') as f: f.write("0")
                except: pass
                
                f = open(f"{dac_path}/out_voltage{i}_raw", 'w') 
                self.dac_files.append(f)

            try:
                self.dac_scale = float(open(f"{dac_path}/out_voltage0_scale").read())
                self.dac_offset = int(open(f"{dac_path}/out_voltage0_offset").read())
            except: pass

            # 3. SETUP ADC
            self.adc_dev = adc_path
            self.debug_reg = f"/sys/kernel/debug/iio/{os.path.basename(adc_path)}/direct_reg_access"
            self.connected = True

        except Exception as e:
            print(f"❌ HW INIT ERROR: {e}")

    def set_voltage_fast(self, ch, volts):
        if not self.connected or ch >= len(self.dac_files): return
        try:
            target_mv = float(volts) * 1000.0
            raw = int((target_mv / self.dac_scale) - self.dac_offset)
            raw = max(0, min(65535, raw))
            
            f = self.dac_files[ch]
            f.seek(0)
            f.write(str(raw) + "\n")
            f.flush()
        except: pass

    def read_adcs_safe(self):
        if not self.connected: return [0.0]*5
        res = []
        for i in range(5):
            try:
                # Force Bipolar
                try:
                    with open(self.debug_reg, 'w') as f: f.write(f"0x{0x19+i:X} 0x0860")
                except: pass

                # Read Value
                raw_path = f"{self.adc_dev}/in_voltage{i*2}-voltage{i*2+1}_raw"
                if not os.path.exists(raw_path):
                     raw_path = f"{self.adc_dev}/in_voltage{i}_raw"

                with open(raw_path, 'r') as f:
                    raw = int(f.read())
                
                v = ((raw - HARDWARE_OFFSET) / float(HARDWARE_OFFSET)) * HARDWARE_FULL_SCALE * ADC_SCALING_FACTOR
                res.append(round(v, 3))
            except:
                res.append(0.0)
        return res

# ==========================================
#      ENCODER LOGIC (WITH DIGITAL SHIELD)
# ==========================================
class EncoderReader:
    def __init__(self, pi, gpioA, gpioB):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.pos = 0
        self.levA = 0
        self.levB = 0
        
        # 1. Setup Inputs with Pull-ups
        self.pi.set_mode(gpioA, pigpio.INPUT)
        self.pi.set_mode(gpioB, pigpio.INPUT)
        self.pi.set_pull_up_down(gpioA, pigpio.PUD_UP)
        self.pi.set_pull_up_down(gpioB, pigpio.PUD_UP)
        
        # 2. DIGITAL SHIELD (CRITICAL STEP)
        # This tells the Pi to IGNORE pulses shorter than 2000 microseconds (2ms).
        # This blocks the SPI noise (which is nanosconds long) but sees your switch.
        self.pi.set_glitch_filter(gpioA, 2000) 
        self.pi.set_glitch_filter(gpioB, 2000)

        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

    def _pulse(self, gpio, level, tick):
        if gpio == self.gpioA: self.levA = level
        else: self.levB = level
        
        # Switch Test Logic
        if True: 
            if gpio == self.gpioA and level == 1:
                if self.levB == 1: self.pos += 1
                else: self.pos -= 1
            elif gpio == self.gpioB and level == 1:
                if self.levA == 1: self.pos -= 1
                else: self.pos += 1
    def reset(self): self.pos = 0

# ==========================================
#      MAIN LOOP
# ==========================================
pi = pigpio.pi()
if not pi.connected: exit()

hw = FastCraneHardware()
encoders = [EncoderReader(pi, p[0], p[1]) for p in ENCODER_PINS]
targets = [None] * 5 

def control_loop():
    while True:
        for i in range(4):
            t = targets[i]
            if t is not None:
                if abs(encoders[i].pos - t) <= 5:
                    hw.set_voltage_fast(i, 0.0)
                    targets[i] = None
                    print(f"✅ STOP CH {i} @ {encoders[i].pos}")
        time.sleep(0.005)

threading.Thread(target=control_loop, daemon=True).start()

# ==========================================
#      WEB UI
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Crane Final Shielded</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #222; color: #fff; text-align: center; }
        .box { display: inline-block; background: #333; margin: 10px; padding: 15px; border-radius: 8px; width: 260px; border: 1px solid #555; }
        .data { font-size: 24px; font-family: monospace; color: #0f0; margin: 10px 0; display: flex; justify-content: space-between; }
        input { font-size: 18px; width: 80px; text-align: center; padding: 5px; }
        button { font-size: 16px; padding: 10px; width: 100%; margin-top: 5px; cursor: pointer; border: none; border-radius: 4px;}
        .go { background: #27ae60; color: white; }
        .stop { background: #c0392b; color: white; font-size: 20px; font-weight: bold; }
        .rst { background: #7f8c8d; color: white; }
    </style>
    <script>
        setInterval(() => {
            fetch('/data').then(r=>r.json()).then(d=>{
                d.adc.forEach((v,i)=>document.getElementById('a'+i).innerText=v.toFixed(3)+'V');
                d.enc.forEach((v,i)=>{if(document.getElementById('e'+i))document.getElementById('e'+i).innerText=v});
            });
        }, 250);
        function post(url, data) { fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); }
    </script>
</head>
<body>
    <h1>Crane Controller (Shielded)</h1>
    {% for i in range(5) %}
    <div class="box">
        <h2 style="color:#3498db; margin:0">CH {{ i }}</h2>
        <div class="data">
            <span id="a{{ i }}">0.000V</span>
            {% if i<4 %}<span id="e{{ i }}" style="color:#f1c40f">0</span>{% else %}<span>MAN</span>{% endif %}
        </div>
        <input id="v{{ i }}" type="number" step="0.1" value="2.0">
        {% if i<4 %}<input id="t{{ i }}" type="number" step="100" value="1000">{% endif %}
        <button class="go" onclick="post('/cmd', {id:{{ i }}, v:document.getElementById('v{{ i }}').value, t:document.getElementById('t{{ i }}').value})">GO</button>
        <button class="stop" onclick="post('/stop', {id:{{ i }}})">STOP</button>
        {% if i<4 %}<button class="rst" onclick="post('/zero', {id:{{ i }}})">Zero</button>{% endif %}
    </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/data')
def data(): return jsonify(adc=hw.read_adcs_safe(), enc=[e.pos for e in encoders])

@app.route('/cmd', methods=['POST'])
def cmd():
    d = request.json
    i = int(d['id'])
    hw.set_voltage_fast(i, float(d['v']))
    if i < 4 and d.get('t'): targets[i] = int(d['t'])
    return jsonify(ok=True)

@app.route('/stop', methods=['POST'])
def stop():
    i = int(request.json['id'])
    hw.set_voltage_fast(i, 0.0)
    targets[i] = None
    return jsonify(ok=True)

@app.route('/zero', methods=['POST'])
def zero():
    encoders[int(request.json['id'])].reset()
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)