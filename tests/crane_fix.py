import iio
import time
import os
import subprocess

# ==========================================
#      FORCE BIPOLAR & READ
# ==========================================
DAC_NAME = "ltc2688"
ADC_NAME = "ad7124-8"
URI = "local:"

def set_dac_negative(ctx):
    # Set DAC to approx -2.5V to prove the system works
    # Scale ~0.45mV. Offset ~ -32768. 
    # Target -2500mV.
    # Raw = (-2500 / 0.457) - (-32768) = -5464 + 32768 = 27304
    print("Setting DAC to -2.5V...")
    dac = ctx.find_device(DAC_NAME)
    phy = dac.find_channel("voltage0", True)
    phy.attrs["raw"].value = "27304" 
    
    # Ensure Ground reference is 0V
    ref = dac.find_channel("voltage1", True)
    ref.attrs["raw"].value = "32768"

def force_bipolar_reg():
    # Uses system call to write Register 0x19 to 0x0860 (Bipolar Bit = 1)
    # We suppress output to keep the terminal clean
    subprocess.call("iio_reg iio:device1 0x19 0x0860 > /dev/null", shell=True)

def main():
    ctx = iio.Context(URI)
    adc = ctx.find_device(ADC_NAME)
    ch = adc.find_channel("voltage0-voltage1", False)
    ch.enabled = True
    
    set_dac_negative(ctx)
    
    print("\n--- FORCING BIPOLAR MODE LOOP ---")
    print("Expected Voltage: ~ -2.5 V")
    print("Expected Raw: ~ 6,700,000")
    print("-" * 30)
    
    while True:
        try:
            # 1. FORCE THE REGISTER (The "Brute Force" Fix)
            force_bipolar_reg()
            
            # 2. READ IMMEDIATELY
            raw_str = ch.attrs["raw"].value
            raw = int(raw_str)
            
            # 3. CALCULATE VOLTAGE (Manual Bipolar Math)
            # Offset Binary: 8,388,608 is 0V.
            hardware_offset = 8388608
            code_diff = raw - hardware_offset
            
            # Full Span is +/- 13.75V over 8,388,608 codes
            voltage = (code_diff / 8388608.0) * 13.75
            
            print(f"Raw: {raw:<10} | Voltage: {voltage:.4f} V")
            
        except Exception as e:
            print(f"Error: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()