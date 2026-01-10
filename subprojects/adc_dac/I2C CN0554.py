import smbus2
import time

# I2C bus (use /dev/i2c-1)
bus = smbus2.SMBus(1)

# CN0554 I2C address (default)
CN0554_ADDR = 0x48  # adjust if needed

# Example: read 2 bytes from ADC channel 0
def read_adc(channel=0):
    # CN0554 specific register read command for channel
    reg = 0x00 + channel  # example, adjust per datasheet
    data = bus.read_word_data(CN0554_ADDR, reg)
    # Convert raw data to voltage (depends on resolution)
    voltage = data * (5.0 / 65535)  # assuming 16-bit ADC, 0-5V
    return voltage

# Example: write DAC value
def write_dac(value):
    # value = 0..65535 for 16-bit DAC
    reg = 0x10  # example DAC register, check datasheet
    bus.write_word_data(CN0554_ADDR, reg, value)

# Test loop
while True:
    v = float(input("Enter DAC voltage (0-5V): "))
    dac_val = int(v / 5.0 * 65535)
    write_dac(dac_val)
    adc_val = read_adc(0)
    print(f"ADC reads: {adc_val:.3f} V")
    time.sleep(0.1)
