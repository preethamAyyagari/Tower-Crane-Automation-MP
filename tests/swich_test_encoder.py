import pigpio
import time

# CONNECT: Switch between Pin 11 (GPIO 17) and Pin 9 (GND)
PIN = 17 

pi = pigpio.pi()
if not pi.connected:
    print("Error: pigpiod not running")
    exit()

pi.set_mode(PIN, pigpio.INPUT)
pi.set_pull_up_down(PIN, pigpio.PUD_UP) # Enable internal 3.3V

print(f"--- Testing Pin {PIN} (Physical 11) ---")
print("Press the switch now...")

try:
    last_val = pi.read(PIN)
    while True:
        val = pi.read(PIN)
        if val != last_val:
            if val == 0:
                print("✅ SWITCH PRESSED (Low)")
            else:
                print("⭕ SWITCH RELEASED (High)")
            last_val = val
        time.sleep(0.05)
except KeyboardInterrupt:
    pi.stop()