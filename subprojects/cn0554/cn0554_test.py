import iio
import time
import sys

# --- Configuration ---
URI = "local:"
ADC_NAME = "ad7124-8"
DAC_NAME = "ltc2688"

# --- CALIBRATION CONSTANTS (Calculated from your data) ---
# The hardware shrinks the voltage. We expand it back.
CALIB_SLOPE = 12.4  
# The hardware consumes ~0.6V (diode drop/offset). We add it back.
CALIB_OFFSET = 0.6 

def get_device(ctx, name):
    dev = ctx.find_device(name)
    if not dev:
        print(f"Error: Device {name} not found!")
        sys.exit(1)
    return dev

def main():
    print(f"--- connecting to context: {URI} ---")
    try:
        ctx = iio.Context(URI)
    except:
        print("Error: Context not found.")
        return

    dac = get_device(ctx, DAC_NAME)
    adc = get_device(ctx, ADC_NAME)

    # Setup Channels
    dac_sig = dac.find_channel("voltage0", True) # Signal
    dac_ref = dac.find_channel("voltage1", True) # Virtual Ground
    adc_ch = adc.find_channel("voltage0-voltage1", False)
    adc_ch.enabled = True
    
    print("\n--- Starting Calibrated Loopback ---")
    print("Setting Output 1 to 0V (Virtual Ground)...")
    
    # FORCE OUTPUT 1 TO ZERO
    scale_ref = float(dac_ref.attrs["scale"].value)
    dac_ref.attrs["raw"].value = str(0) 

    # Loop through test voltages
    test_voltages = [1.0, 1.5, 2.0, 2.5]

    try:
        while True:
            for v_target in test_voltages:
                # 1. WRITE SIGNAL
                scale = float(dac_sig.attrs["scale"].value)
                raw_val = int(v_target / scale)
                dac_sig.attrs["raw"].value = str(raw_val)
                
                print(f"Output Set: {v_target} V")
                time.sleep(5.0) 

                # 2. READ INPUT
                raw_in = float(adc_ch.attrs["raw"].value)
                scale_in = float(adc_ch.attrs["scale"].value)
                offset_in = float(adc_ch.attrs["offset"].value)
                
                # A. Get Raw Chip Voltage (The tiny value)
                v_chip = (raw_in + offset_in) * scale_in
                if scale_in > 0.001: v_chip /= 1000.0
                
                # B. Apply Calibration (Slope + Offset)
                if v_chip < 0.001:
                    v_real = 0.0 # Clean up noise at 0V
                else:
                    v_real = (v_chip * CALIB_SLOPE) + CALIB_OFFSET

                print(f" -> Measured: {v_real:.4f} V")
                print("-" * 30)
                time.sleep(1)

    except KeyboardInterrupt:
        print("Done.")

if __name__ == "__main__":
    main()