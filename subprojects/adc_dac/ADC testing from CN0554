import adi
import time
import numpy as np

# ==============================
# ADC (AD7124-8)
# ==============================
adc = adi.ad7124(uri="local:")
adc.sample_rate = 100  # SPS
adc.enabled_channels = [0]  # Change channel here: 0–7

# ==============================
# DAC (AD5686R)
# ==============================
dac = adi.ad5686(uri="local:")

# ------------------------------
# USER CONTROL SECTION 👇👇👇
# ------------------------------

DAC_CHANNEL = 0      # 0–3
DAC_VOLTAGE = 5.0    # Volts (0–10V supported by CN0554)

# ------------------------------
# DAC OUTPUT
# ------------------------------
print(f"Setting DAC channel {DAC_CHANNEL} to {DAC_VOLTAGE} V")
dac.channel[DAC_CHANNEL].raw = int((DAC_VOLTAGE / 10.0) * 65535)

# ------------------------------
# ADC READ
# ------------------------------
time.sleep(0.5)

data = adc.rx()
adc_voltage = np.mean(data)

print(f"ADC Channel 0 Voltage: {adc_voltage:.4f} V")
