import time
import threading
import random
import math

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
#      MOCK HARDWARE DRIVER
# ==========================================
class MockHardware:
    def __init__(self):
        self.voltages = [0.0] * 5
        print("✅ MOCK Hardware Initialized (Simulation Mode)")

    def set_voltage_fast(self, ch, volts):
        if 0 <= ch < len(self.voltages):
            self.voltages[ch] = float(volts)

    def read_adcs_safe(self):
        # Returns the commanded voltages with a tiny bit of random noise (jitter) 
        # so the GUI looks like it is reading live analog sensors.
        
        # CHANGED: Now generates an independent simulated sensor wave (1.5V to 2.5V)
        current_t = time.time()
        return [round(2.0 + math.sin(current_t + i) * 0.5 + random.uniform(-0.02, 0.02), 3) for i in range(5)]

# ==========================================
#      MOCK ENCODER LOGIC
# ==========================================
class MockEncoderReader:
    def __init__(self):
        self.pos = 0

    def reset(self):
        self.pos = 0

# ==========================================
#      FIRMWARE MANAGER (SIMULATION)
# ==========================================
class CraneFirmware:
    def __init__(self):
        print("🚀 Starting Crane Firmware in SIMULATION MODE")
        self.hw = MockHardware()
        self.encoders = [MockEncoderReader() for _ in range(4)]
        self.targets = [None] * 5 
        
        # Start control loop in background
        self.running = True
        self.thread = threading.Thread(target=self.control_loop, daemon=True)
        self.thread.start()

    def control_loop(self):
        while self.running:
            for i in range(4):
                v = self.hw.voltages[i]
                
                # 1. Simulate physical movement based on voltage
                if abs(v) > 0.1:
                    # Move the encoder proportional to the voltage applied
                    step = int(v * 2) 
                    self.encoders[i].pos += step

                # 2. Check targets and stop (Original logic with dynamic margin)
                t = self.targets[i]
                if t is not None:
                    # We use a dynamic margin here so high speeds don't overshoot the check
                    margin = max(5, abs(int(v * 2))) 
                    if abs(self.encoders[i].pos - t) <= margin:
                        self.hw.set_voltage_fast(i, 0.0)
                        self.targets[i] = None
                        # Snap exactly to target for clean readouts
                        self.encoders[i].pos = t 
                        print(f"✅ STOP CH {i} @ {self.encoders[i].pos}")
                        
            time.sleep(0.01) # Slightly slower sleep to simulate mechanical lag
            
    def shutdown(self):
        self.running = False
        for i in range(5):
            self.hw.set_voltage_fast(i, 0.0)