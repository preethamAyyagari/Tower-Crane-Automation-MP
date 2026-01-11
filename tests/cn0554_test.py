import iio
import time
import sys

# --- Configuration ---
URI = "local:"
ADC_NAME = "ad7124-8"
DAC_NAME = "ltc2688"

# --- ADC CALIBRATION CONSTANTS ---
# Kept from your previous good data
CALIB_SLOPE = 0.01135 
CALIB_OFFSET = 0.0

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
    
    print("\n--- Starting Bipolar Calibrated Test ---")
    
    # 1. WAKE UP DAC (Disable Power Down)
    # The attributes might be named 'powerdown' or similar. 
    # We try to write "0" to them to ensure they are ON.
    if "powerdown" in dac_sig.attrs:
        dac_sig.attrs["powerdown"].value = "0"
    if "powerdown" in dac_ref.attrs:
        dac_ref.attrs["powerdown"].value = "0"

    # 2. GET DAC SCALING INFO
    # Scale is in mV. Offset is in Raw Steps.
    # Formula: Raw = (Target_mV / Scale) - Offset
    dac_scale = float(dac_sig.attrs["scale"].value)
    
    try:
        dac_offset = int(dac_sig.attrs["offset"].value)
    except:
        # If the driver doesn't report offset, we assume -32768 for +/-15V mode
        # based on your manual test (54613 = 10V).
        print("Warning: Could not read DAC offset. Assuming -32768 (Bipolar Mode).")
        dac_offset = -32768

    print(f"DAC Config -> Scale: {dac_scale:.4f} mV/bit | Offset: {dac_offset}")

    # 3. SET VIRTUAL GROUND (Output 1) TO 0V
    # To output 0V, we need: (0 / Scale) - Offset
    raw_zero = int((0.0 / dac_scale) - dac_offset)
    dac_ref.attrs["raw"].value = str(raw_zero)
    print(f"Setting Virtual Ground (0V) -> Raw Code: {raw_zero}")

    test_voltages = [1.0, 1.5, 2.0, 2.5]

    try:
        while True:
            for v_target in test_voltages:
                # 4. WRITE SIGNAL (Convert Volts to mV first)
                target_mv = v_target * 1000.0
                
                # The Golden Formula for Bipolar DACs
                raw_val = int((target_mv / dac_scale) - dac_offset)
                
                dac_sig.attrs["raw"].value = str(raw_val)
                
                print(f"Output Set: {v_target} V (Raw: {raw_val})")
                time.sleep(3.0) 

                # 5. READ INPUT
                raw_in = float(adc_ch.attrs["raw"].value)
                scale_in = float(adc_ch.attrs["scale"].value)
                offset_in = float(adc_ch.attrs["offset"].value)
                
                v_chip = (raw_in + offset_in) * scale_in
                if scale_in > 0.001: v_chip /= 1000.0
                
                if v_chip < 0.001:
                    v_real = 0.0
                else:
                    v_real = (v_chip * CALIB_SLOPE) + CALIB_OFFSET

                print(f" -> Measured: {v_real:.4f} V")
                print("-" * 30)

    except KeyboardInterrupt:
        print("Done.")

if __name__ == "__main__":
    main()