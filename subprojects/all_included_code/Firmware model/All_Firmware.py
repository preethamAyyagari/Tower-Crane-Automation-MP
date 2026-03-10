import pigpio
import time
import threading
import os
import sys

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
#      FIRMWARE MANAGER (For GUI Access)
# ==========================================
class CraneFirmware:
    def __init__(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpiod is not running. Please start it.")

        self.hw = FastCraneHardware()
        self.encoders = [EncoderReader(self.pi, p[0], p[1]) for p in ENCODER_PINS]
        self.targets = [None] * 5 
        
        # Start control loop in background
        self.running = True
        self.thread = threading.Thread(target=self.control_loop, daemon=True)
        self.thread.start()

    def control_loop(self):
        while self.running:
            for i in range(4):
                t = self.targets[i]
                if t is not None:
                    if abs(self.encoders[i].pos - t) <= 5:
                        self.hw.set_voltage_fast(i, 0.0)
                        self.targets[i] = None
                        print(f"✅ STOP CH {i} @ {self.encoders[i].pos}")
            time.sleep(0.005)
            
    def shutdown(self):
        self.running = False
        for i in range(5):
            self.hw.set_voltage_fast(i, 0.0)