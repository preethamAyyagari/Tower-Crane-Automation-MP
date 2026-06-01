import pigpio
import time
import threading
import os
import sys
import random
import math
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
#      AUTO-DETECT ENVIRONMENT
# ==========================================
pi = pigpio.pi()
SIMULATION_MODE = not pi.connected

if SIMULATION_MODE:
    print("⚠️ HARDWARE NOT DETECTED: Starting in SIMULATION MODE for GUI Testing...")
else:
    print("✅ HARDWARE DETECTED: Starting in REAL HARDWARE MODE...")

# ==========================================
#      HARDWARE DRIVER (REAL)
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
#      ENCODER LOGIC (REAL WITH DIGITAL SHIELD)
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
#      MOCK CLASSES (FOR SIMULATION ONLY)
# ==========================================
class MockHardware:
    def __init__(self):
        self.voltages = [0.0] * 5
    def set_voltage_fast(self, ch, volts):
        if 0 <= ch < len(self.voltages): self.voltages[ch] = float(volts)
    def read_adcs_safe(self):
        t = time.time()
        return [round(2.0 + math.sin(t + i) * 0.5 + random.uniform(-0.02, 0.02), 3) for i in range(5)]

class MockEncoderReader:
    def __init__(self): self.pos = 0
    def reset(self): self.pos = 0

# ==========================================
#      INITIALIZATION & STATE TRACKING
# ==========================================
if SIMULATION_MODE:
    hw = MockHardware()
    encoders = [MockEncoderReader() for _ in range(4)]
else:
    hw = FastCraneHardware()
    encoders = [EncoderReader(pi, p[0], p[1]) for p in ENCODER_PINS]

targets = [None] * 5 
current_dac = [0.0] * 5  

def control_loop():
    while True:
        for i in range(4):
            # Simulation movement mechanics
            if SIMULATION_MODE:
                v = hw.voltages[i]
                if abs(v) > 0.1: encoders[i].pos += int(v * 2)

            t = targets[i]
            if t is not None:
                # Dynamic margin for simulation speed, tight margin for real hardware
                margin = max(5, abs(int(hw.voltages[i] * 2))) if SIMULATION_MODE else 5
                
                if abs(encoders[i].pos - t) <= margin:
                    hw.set_voltage_fast(i, 0.0)
                    current_dac[i] = 0.0  
                    targets[i] = None
                    if SIMULATION_MODE: encoders[i].pos = t # Snap to target for clean mock readout
                    print(f"✅ STOP CH {i} @ {encoders[i].pos}")
                    
        time.sleep(0.01 if SIMULATION_MODE else 0.005)

threading.Thread(target=control_loop, daemon=True).start()

# ==========================================
#      WEB UI (UPDATED CUSTOM CHANNELS)
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Crane Advanced Interface</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #1e272e; color: #d2dae2; text-align: center; margin: 0; padding: 20px;}
        
        .top-bar { display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; }
        .top-btn { padding: 12px 24px; font-size: 16px; font-weight: bold; cursor: pointer; border: none; border-radius: 6px; color: white; transition: 0.2s;}
        #pauseBtn { background: #f39c12; }
        #snapBtn { background: #8e44ad; }
        
        h1 { margin: 0 0 10px 0; color: #ecf0f1; }
        .section-title { text-align: left; padding-left: 20px; color: #0fb9b1; border-bottom: 2px solid #34495e; margin-top: 20px; padding-bottom: 5px; }
        
        .grid-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; margin-bottom: 30px; }
        .box { background: #2c3e50; padding: 15px; border-radius: 8px; width: 320px; border: 1px solid #485460; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        
        h3 { color: #3498db; margin: 0 0 10px 0; text-align: left; border-bottom: 1px solid #485460; padding-bottom: 5px;}
        
        .data { font-size: 24px; font-family: monospace; font-weight: bold; margin: 10px 0; display: flex; justify-content: space-between; align-items: center;}
        .adc-val { color: #2ecc71; }
        .enc-val { color: #f1c40f; }
        
        .chart-container { height: 140px; width: 100%; margin-bottom: 10px; background: #1e272e; border-radius: 4px; padding: 5px; box-sizing: border-box;}
        canvas { width: 100% !important; height: 100% !important; }
        
        .chart-tools { display: flex; justify-content: space-between; margin-bottom: 15px; }
        .tool-btn { background: #485460; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-size: 12px; cursor: pointer; }
        .tool-btn:hover { background: #576574; }
        .active-scale { background: #0fb9b1 !important; color: white !important; font-weight: bold; }
        
        .inputs { display: flex; justify-content: space-between; gap: 8px; margin-top: 10px; }
        input { font-size: 16px; width: 45%; text-align: center; padding: 8px; border-radius: 4px; border: 1px solid #485460; background: #d2dae2; color: #1e272e; font-weight: bold;}
        
        button { font-size: 16px; font-weight: bold; padding: 10px; width: 100%; margin-top: 8px; cursor: pointer; border: none; border-radius: 4px;}
        .go { background: #20bf6b; color: white; }
        .stop { background: #eb3b5a; color: white; }
        .rst { background: #778ca3; color: white; }
    </style>
</head>
<body id="main-body">
    
    <h1>Crane Control Dashboard</h1>
    
    <div class="top-bar" data-html2canvas-ignore>
        <button id="pauseBtn" class="top-btn" onclick="togglePause()">⏸ Pause Plotting</button>
        <button id="snapBtn" class="top-btn" onclick="takeFullScreenshot()">📸 Save Entire Window</button>
    </div>

    <h2 class="section-title">📡 Analog IN (Sensors)</h2>
    <div class="grid-container">
        {% for ch, name in adc_channels %}
        <div class="box" id="adcBox_{{ ch }}">
            <h3>CH {{ ch }} - {{ name }}</h3>
            <div class="data">
                <span>Signal:</span>
                <span id="a{{ ch }}" class="adc-val">0.000V</span>
            </div>
            <div class="chart-container"><canvas id="adcChart_{{ ch }}"></canvas></div>
            <div class="chart-tools" data-html2canvas-ignore>
                <button class="tool-btn" onclick="toggleAutoScale('adc', {{ ch }}, this)">↕ Auto-Scale: OFF</button>
                <button class="tool-btn" onclick="saveSingleBox('adcBox_{{ ch }}', '{{ name }}_Graph')">💾 Save Graph</button>
            </div>
        </div>
        {% endfor %}
    </div>

    <h2 class="section-title">⚙️ Analog OUT (Motors & Control)</h2>
    <div class="grid-container">
        {% for ch, name in dac_channels %}
        <div class="box" id="dacBox_{{ ch }}">
            <h3>CH {{ ch }} - {{ name }}</h3>
            <div class="data">
                <span style="color:#eb3b5a">Voltage Out</span>
                <span id="e{{ ch }}" class="enc-val">Pos: 0</span>
            </div>
            
            <div class="chart-container"><canvas id="dacChart_{{ ch }}"></canvas></div>
            
            <div class="chart-tools" data-html2canvas-ignore>
                <button class="tool-btn" onclick="toggleAutoScale('dac', {{ ch }}, this)">↕ Auto-Scale: OFF</button>
                <button class="tool-btn" onclick="saveSingleBox('dacBox_{{ ch }}', '{{ name }}_Graph')">💾 Save Graph</button>
            </div>
            
            <div class="inputs" data-html2canvas-ignore>
                <input id="v{{ ch }}" type="number" step="0.1" value="2.0" title="Voltage (V)">
                <input id="t{{ ch }}" type="number" step="100" value="1000" title="Target Steps">
            </div>
            
            <button class="go" data-html2canvas-ignore onclick="post('/cmd', {id:{{ ch }}, v:document.getElementById('v{{ ch }}').value, t:document.getElementById('t{{ ch }}').value})">GO</button>
            <button class="stop" data-html2canvas-ignore onclick="post('/stop', {id:{{ ch }}})">STOP</button>
            <button class="rst" data-html2canvas-ignore onclick="post('/zero', {id:{{ ch }}})">Zero Encoder</button>
        </div>
        {% endfor %}
    </div>

    <script>
        let isPaused = false;
        const MAX_POINTS = 40; 
        const charts = { adc: {}, dac: {} }; // Using objects for specific ID tracking
        const startTime = Date.now(); 

        function getChartConfig(colorCode) {
            return {
                type: 'line',
                data: { labels: Array(MAX_POINTS).fill(''), datasets: [{ data: Array(MAX_POINTS).fill(null), borderColor: colorCode }] },
                options: {
                    responsive: true, maintainAspectRatio: false, animation: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    scales: { 
                        x: { 
                            display: true, 
                            title: { display: true, text: 'Time (s)', color: '#aaa', font: {size: 10} },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' },
                            ticks: { color: '#aaa', maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }
                        }, 
                        y: { 
                            min: -10.5, max: 10.5, 
                            grid: { color: 'rgba(255, 255, 255, 0.1)' },
                            ticks: { color: '#aaa', stepSize: 5 } 
                        } 
                    },
                    elements: { point: { radius: 0 }, line: { borderWidth: 2, tension: 0.1 } }
                }
            };
        }

        // Only initialize charts if the DOM elements exist
        [0, 1, 2, 3, 4].forEach(i => {
            let ctxA = document.getElementById('adcChart_' + i);
            if (ctxA) charts.adc[i] = new Chart(ctxA.getContext('2d'), getChartConfig('#2ecc71'));

            let ctxD = document.getElementById('dacChart_' + i);
            if (ctxD) charts.dac[i] = new Chart(ctxD.getContext('2d'), getChartConfig('#eb3b5a'));
        });

        // --- BUTTON ACTIONS ---
        function toggleAutoScale(type, index, btnElement) {
            let targetChart = charts[type][index];
            if (!targetChart) return;
            
            let scales = targetChart.options.scales.y;
            if (scales.min !== undefined) {
                delete scales.min; delete scales.max;
                btnElement.innerText = "↕ Auto-Scale: ON";
                btnElement.classList.add("active-scale");
            } else {
                scales.min = -10.5; scales.max = 10.5;
                btnElement.innerText = "↕ Auto-Scale: OFF";
                btnElement.classList.remove("active-scale");
            }
            targetChart.update();
        }

        function togglePause() {
            isPaused = !isPaused;
            let btn = document.getElementById('pauseBtn');
            if (isPaused) {
                btn.innerText = "▶ Resume Plotting"; btn.style.background = "#20bf6b";
            } else {
                btn.innerText = "⏸ Pause Plotting"; btn.style.background = "#f39c12";
            }
        }

        function takeFullScreenshot() {
            html2canvas(document.body, { backgroundColor: '#1e272e' }).then(canvas => {
                let a = document.createElement('a');
                a.href = canvas.toDataURL("image/png");
                a.download = "crane_full_dashboard.png";
                a.click();
            });
        }

        function saveSingleBox(boxId, fileName) {
            let boxElement = document.getElementById(boxId);
            html2canvas(boxElement, { backgroundColor: '#2c3e50', scale: 2 }).then(canvas => {
                let a = document.createElement('a');
                a.href = canvas.toDataURL("image/png");
                a.download = fileName + ".png";
                a.click();
            });
        }

        function post(url, data) { fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); }

        // --- FETCH & UPDATE LOOP ---
        setInterval(() => {
            fetch('/data').then(r=>r.json()).then(d=>{
                let elapsedSecs = ((Date.now() - startTime) / 1000).toFixed(1);

                d.adc.forEach((v, i) => {
                    // Only update DOM elements that actually exist
                    let adcLabel = document.getElementById('a'+i);
                    if (adcLabel) adcLabel.innerText = v.toFixed(3) + 'V';
                    
                    let encLabel = document.getElementById('e'+i);
                    if (encLabel && d.enc[i] !== undefined) encLabel.innerText = "Pos: " + d.enc[i];
                    
                    if (!isPaused) {
                        if (charts.adc[i]) {
                            charts.adc[i].data.labels.shift();
                            charts.adc[i].data.labels.push(elapsedSecs);
                            charts.adc[i].data.datasets[0].data.shift();
                            charts.adc[i].data.datasets[0].data.push(v);
                            charts.adc[i].update();
                        }
                        
                        if (charts.dac[i]) {
                            charts.dac[i].data.labels.shift();
                            charts.dac[i].data.labels.push(elapsedSecs);
                            charts.dac[i].data.datasets[0].data.shift();
                            charts.dac[i].data.datasets[0].data.push(d.dac[i]);
                            charts.dac[i].update();
                        }
                    }
                });
            }).catch(e => console.log("Connection Error..."));
        }, 250);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # Pass the custom mapping to Jinja
    adc_mapping = [(0, 'Sensor Alpha'), (1, 'Sensor Beta'), (2, 'Sensor Hook'), (4, 'Tilt')]
    dac_mapping = [(0, 'Spin Control'), (1, 'Trolley'), (2, 'Hook'), (3, 'Tilt')]
    return render_template_string(HTML_PAGE, adc_channels=adc_mapping, dac_channels=dac_mapping)

@app.route('/data')
def data(): return jsonify(adc=hw.read_adcs_safe(), enc=[e.pos for e in encoders], dac=current_dac)

@app.route('/cmd', methods=['POST'])
def cmd():
    d = request.json
    i = int(d['id'])
    v = float(d['v'])
    hw.set_voltage_fast(i, v)
    current_dac[i] = v  
    if i < 4 and d.get('t'): targets[i] = int(d['t'])
    return jsonify(ok=True)

@app.route('/stop', methods=['POST'])
def stop():
    i = int(request.json['id'])
    hw.set_voltage_fast(i, 0.0)
    current_dac[i] = 0.0 
    targets[i] = None
    return jsonify(ok=True)

@app.route('/zero', methods=['POST'])
def zero():
    encoders[int(request.json['id'])].reset()
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)