import iio
import sys
import time
import os
from flask import Flask, render_template_string, request, jsonify

# ==========================================
#      CALIBRATION (Fixed)
# ==========================================
# Removed the 0.002 offset because it was causing your overshoot.
SCALING_FACTOR = 2.0016  
CALIB_OFFSET = 0.0       

# Hardware Constants
HARDWARE_OFFSET = 8388608
HARDWARE_FULL_SCALE = 13.75

URI = "local:"
ADC_NAME = "ad7124-8"
DAC_NAME = "ltc2688"
# Direct Register Access Path (Much faster than iio_reg command)
DEBUG_REG_PATH = "/sys/kernel/debug/iio/iio:device1/direct_reg_access"

app = Flask(__name__)

# ==========================================
#      HARDWARE DRIVER (High Speed)
# ==========================================
class CraneHardware:
    def __init__(self):
        self.connected = False
        self.dacs = []
        self.adcs = []
        self.dac_scale = 0.0
        self.dac_offset = 0

        try:
            self.ctx = iio.Context(URI)
            dev_dac = self.ctx.find_device(DAC_NAME)
            dev_adc = self.ctx.find_device(ADC_NAME)
            
            if not dev_dac or not dev_adc:
                print("Error: Hardware not found.")
                return

            # --- SETUP 5 DAC CHANNELS ---
            for i in range(5):
                ch = dev_dac.find_channel(f"voltage{i}", True)
                if "powerdown" in ch.attrs: ch.attrs["powerdown"].value = "0"
                self.dacs.append(ch)

            self.dac_scale = float(self.dacs[0].attrs["scale"].value)
            try:
                self.dac_offset = int(self.dacs[0].attrs["offset"].value)
            except:
                self.dac_offset = -32768

            # --- SETUP 5 ADC CHANNELS ---
            # Mapping: Ch0=v0-v1, Ch1=v2-v3, Ch2=v4-v5, etc.
            for i in range(5):
                pos, neg = i * 2, (i * 2) + 1
                ch_id = f"voltage{pos}-voltage{neg}"
                ch = dev_adc.find_channel(ch_id, False)
                if ch:
                    ch.enabled = True
                    self.adcs.append(ch)

            self.connected = True
            print(f"--- Crane System Online (High Speed Mode) ---")

        except Exception as e:
            print(f"HARDWARE ERROR: {e}")

    def fast_force_bipolar(self, channel_idx):
        """ Writes directly to debugfs file (No shell overhead) """
        try:
            # Register 0x19 is Config_0. Setup 1 is 0x1A, etc.
            reg_addr = 0x19 + channel_idx
            # Format: "Address Value" (e.g., "0x19 0x0860")
            cmd = f"0x{reg_addr:X} 0x0860"
            
            with open(DEBUG_REG_PATH, 'w') as f:
                f.write(cmd)
        except Exception as e:
            # Fail silently to keep speed up, log only on first fail if needed
            pass

    def set_dac_voltage(self, channel_idx, voltage):
        if not self.connected or channel_idx >= len(self.dacs): return False
        try:
            target_mv = float(voltage) * 1000.0
            raw_val = int((target_mv / self.dac_scale) - self.dac_offset)
            raw_val = max(0, min(65535, raw_val)) 
            self.dacs[channel_idx].attrs["raw"].value = str(raw_val)
            return True
        except:
            return False

    def read_all_adcs(self):
        if not self.connected: return [0.0]*5
        results = []
        for i, ch in enumerate(self.adcs):
            try:
                # 1. FAST FORCE BIPOLAR
                self.fast_force_bipolar(i)
                
                # 2. READ RAW
                raw = int(ch.attrs["raw"].value)
                
                # 3. MANUAL MATH
                code_diff = raw - HARDWARE_OFFSET
                base_volts = (code_diff / float(HARDWARE_OFFSET)) * HARDWARE_FULL_SCALE
                final_volts = (base_volts * SCALING_FACTOR) + CALIB_OFFSET
                
                results.append(round(final_volts, 4))
            except:
                results.append(0.0)
        return results

crane = CraneHardware()

# ==========================================
#      WEB UI
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>5-Channel Crane Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; background-color: #eef2f5; padding: 10px; }
        .container { display: flex; flex-wrap: wrap; justify-content: center; gap: 15px; }
        .channel-group { background: white; padding: 15px; width: 200px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        h3 { margin: 5px 0 10px 0; color: #444; border-bottom: 2px solid #eee; }
        input { font-size: 18px; padding: 5px; width: 80px; text-align: center; margin-bottom: 5px; }
        .btn-set { background-color: #3498db; color: white; border: none; padding: 8px; border-radius: 4px; cursor: pointer; width: 100%; margin-bottom: 5px; }
        .btn-zero { background-color: #e74c3c; color: white; border: none; padding: 8px; border-radius: 4px; cursor: pointer; width: 100%; font-weight: bold; }
        .reading { font-size: 26px; font-weight: bold; color: #27ae60; margin-top: 10px; font-family: monospace; }
    </style>
    <script>
        function updateADCs() {
            fetch('/get_adcs')
                .then(res => res.json())
                .then(data => {
                    data.voltages.forEach((val, idx) => {
                        let el = document.getElementById('adc_' + idx);
                        if(el) {
                            el.innerText = val.toFixed(4);
                            el.style.color = (val < 0) ? "#e74c3c" : "#27ae60";
                        }
                    });
                });
        }
        function setDAC(idx) {
            let val = document.getElementById('dac_in_' + idx).value;
            postDAC(idx, val);
        }
        function setZero(idx) {
            document.getElementById('dac_in_' + idx).value = "0.0";
            postDAC(idx, 0.0);
        }
        function postDAC(idx, val) {
            fetch('/set_dac', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel: idx, voltage: val})
            });
        }
        setInterval(updateADCs, 200); // Fast 200ms updates
    </script>
</head>
<body>
    <h1>🏗️ 5-Channel Crane Control</h1>
    <div class="container">
        {% for i in range(5) %}
        <div class="channel-group">
            <h3>CH {{ i }}</h3>
            <input type="number" id="dac_in_{{ i }}" step="0.1" value="0.0" min="-10" max="10">
            <button class="btn-set" onclick="setDAC({{ i }})">Set Voltage</button>
            <button class="btn-zero" onclick="setZero({{ i }})">STOP (0V)</button>
            <div class="reading"><span id="adc_{{ i }}">---</span> V</div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/set_dac', methods=['POST'])
def handle_dac():
    data = request.get_json()
    crane.set_dac_voltage(int(data.get('channel', 0)), data.get('voltage', 0))
    return jsonify(success=True)

@app.route('/get_adcs')
def handle_adcs():
    return jsonify(voltages=crane.read_all_adcs())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)