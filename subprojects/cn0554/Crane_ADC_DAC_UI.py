import iio
import sys
import time
import subprocess
from flask import Flask, render_template_string, request, jsonify

# ==========================================
#      CALIBRATION (The "Magic Numbers")
# ==========================================
# We found that raw math gives -1.25V for a -2.5V input.
# So we simply multiply by 2.0 to correct it.
SCALING_FACTOR = 2.0 
HARDWARE_OFFSET = 8388608  # The midpoint (0V) for 24-bit ADC
HARDWARE_FULL_SCALE = 13.75 # The physical max voltage of the range

URI = "local:"
ADC_NAME = "ad7124-8"
DAC_NAME = "ltc2688"

app = Flask(__name__)

# ==========================================
#      HARDWARE DRIVER (Custom Bipolar)
# ==========================================
class CraneHardware:
    def __init__(self):
        self.connected = False
        try:
            self.ctx = iio.Context(URI)
            self.dac = self.ctx.find_device(DAC_NAME)
            self.adc = self.ctx.find_device(ADC_NAME)
            
            if not self.dac or not self.adc:
                print("Error: Hardware not found.")
                return

            # --- DAC SETUP ---
            self.dac_sig = self.dac.find_channel("voltage0", True)
            self.dac_ref = self.dac.find_channel("voltage1", True)
            
            # Wake up
            if "powerdown" in self.dac_sig.attrs: self.dac_sig.attrs["powerdown"].value = "0"
            if "powerdown" in self.dac_ref.attrs: self.dac_ref.attrs["powerdown"].value = "0"

            # DAC Constants
            self.dac_scale = float(self.dac_sig.attrs["scale"].value)
            try:
                self.dac_offset = int(self.dac_sig.attrs["offset"].value)
            except:
                self.dac_offset = -32768

            # Zero the Reference
            raw_zero = int((0.0 / self.dac_scale) - self.dac_offset)
            self.dac_ref.attrs["raw"].value = str(raw_zero)

            # --- ADC SETUP ---
            self.adc_ch = self.adc.find_channel("voltage0-voltage1", False)
            self.adc_ch.enabled = True
            
            self.connected = True
            print("--- Crane System Online (Custom Bipolar Driver) ---")

        except Exception as e:
            print(f"HARDWARE ERROR: {e}")

    def set_dac_voltage(self, voltage):
        """ Sets Servo Voltage (-10 to +10) """
        if not self.connected: return False
        try:
            target_mv = float(voltage) * 1000.0
            raw_val = int((target_mv / self.dac_scale) - self.dac_offset)
            raw_val = max(0, min(65535, raw_val)) 
            self.dac_sig.attrs["raw"].value = str(raw_val)
            return True
        except Exception as e:
            print(f"DAC Error: {e}")
            return False

    def read_adc_voltage(self):
        """ Reads Boom Angle using Brute Force Bipolar Fix """
        if not self.connected: return 0.0
        try:
            # 1. FORCE BIPOLAR MODE (Register 0x19 -> 0x0860)
            # This fixes the "0V" clipping issue on Linux drivers
            subprocess.call("iio_reg iio:device1 0x19 0x0860 > /dev/null", shell=True)
            
            # 2. READ RAW DIRECTLY
            raw_str = self.adc_ch.attrs["raw"].value
            raw = int(raw_str)
            
            # 3. MANUAL MATH
            # Subtract the 0V offset (8,388,608)
            code_diff = raw - HARDWARE_OFFSET
            
            # Convert to Volts (Base Span)
            base_volts = (code_diff / float(HARDWARE_OFFSET)) * HARDWARE_FULL_SCALE
            
            # 4. APPLY FINAL SCALING (The x2.0 Fix)
            final_volts = base_volts * SCALING_FACTOR
            
            return round(final_volts, 4)
            
        except Exception as e:
            print(f"ADC Read Error: {e}")
            return 0.0

crane = CraneHardware()

# ==========================================
#      WEB UI
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Tower Crane Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; background-color: #eef2f5; padding: 20px; }
        .card { background: white; padding: 30px; width: 300px; margin: 10px; border-radius: 12px; display: inline-block; vertical-align: top; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; }
        h2 { color: #555; font-size: 18px; }
        input { font-size: 20px; padding: 8px; width: 100px; text-align: center; border: 1px solid #ccc; border-radius: 4px; }
        button { font-size: 18px; padding: 8px 20px; background-color: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: 10px; }
        .reading { font-size: 42px; font-weight: bold; color: #27ae60; margin: 15px 0; font-family: monospace; }
    </style>
    <script>
        function updateADC() {
            fetch('/get_adc')
                .then(res => res.json())
                .then(data => {
                    let val = data.voltage;
                    let el = document.getElementById('adc_val');
                    el.innerText = val;
                    el.style.color = (val < 0) ? "#e74c3c" : "#27ae60"; 
                });
        }
        function setDAC() {
            let val = document.getElementById('dac_input').value;
            fetch('/set_dac', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({voltage: val})
            });
        }
        setInterval(updateADC, 500); // Refresh every 0.5s
    </script>
</head>
<body>
    <h1>🏗️ Crane Control (±10V)</h1>
    
    <div class="card">
        <h2>Servo Motor (DAC)</h2>
        <input type="number" id="dac_input" step="0.1" value="0.0" min="-10" max="10">
        <br><button onclick="setDAC()">Set Voltage</button>
    </div>

    <div class="card">
        <h2>Boom Angle (ADC)</h2>
        <div class="reading"><span id="adc_val">---</span> V</div>
    </div>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/set_dac', methods=['POST'])
def handle_dac():
    data = request.get_json()
    crane.set_dac_voltage(data.get('voltage', 0))
    return jsonify(success=True)

@app.route('/get_adc')
def handle_adc():
    return jsonify(voltage=crane.read_adc_voltage())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)