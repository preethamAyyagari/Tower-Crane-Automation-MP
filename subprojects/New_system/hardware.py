import os
import pigpio
import time
import math
import random
import config

try:
    from smbus2 import SMBus
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False


class MCP23017Driver:
    IODIRA = 0x00
    IODIRB = 0x01
    GPPUA  = 0x0C
    GPPUB  = 0x0D
    GPIOA  = 0x12
    GPIOB  = 0x13
    OLATA  = 0x14
    OLATB  = 0x15

    def __init__(self, bus_id=config.MCP23017_I2C_BUS, addr=config.MCP23017_I2C_ADDR):
        self.bus_id = bus_id
        self.addr = addr
        self.bus = None
        self.connected = False
        self.olat_a = 0x00
        self.olat_b = 0x00

        if SMBUS_AVAILABLE:
            try:
                self.bus = SMBus(self.bus_id)
                dir_a = 0xFF
                dir_b = 0xFF

                out_port, out_pin = config.PIN_MCP_SERVO_ERR_CLEAR
                if out_port == 'A':
                    dir_a &= ~(1 << out_pin)
                else:
                    dir_b &= ~(1 << out_pin)

                self.bus.write_byte_data(self.addr, self.IODIRA, dir_a)
                self.bus.write_byte_data(self.addr, self.IODIRB, dir_b)
                self.bus.write_byte_data(self.addr, self.GPPUA, 0x00)
                self.bus.write_byte_data(self.addr, self.GPPUB, 0x00)
                self.bus.write_byte_data(self.addr, self.OLATA, 0x00)
                self.bus.write_byte_data(self.addr, self.OLATB, 0x00)
                self.connected = True
                print(f"✅ MCP23017 connected on bus {self.bus_id} at 0x{self.addr:02X}")
            except Exception as e:
                print(f"⚠️ MCP23017 init failed: {e}")

    def read_all_inputs(self):
        states = {
            'spin_cw': False, 'spin_acw': False, 'spin_ref': False,
            'trolley_front': False, 'trolley_back': False,
            'tilt_up': False, 'tilt_down': False,
            'hook_up': False, 'hook_down': False,
            'servo_err_clear': False
        }
        if not self.connected or not self.bus:
            return states

        try:
            val_a = self.bus.read_byte_data(self.addr, self.GPIOA)
            val_b = self.bus.read_byte_data(self.addr, self.GPIOB)

            mapping = {
                'spin_cw': config.PIN_MCP_SPIN_CW_LIMIT,
                'spin_acw': config.PIN_MCP_SPIN_ACW_LIMIT,
                'spin_ref': config.PIN_MCP_SPIN_REF,
                'trolley_front': config.PIN_MCP_TROLLEY_FRONT,
                'trolley_back': config.PIN_MCP_TROLLEY_BACK,
                'tilt_up': config.PIN_MCP_TILT_UP,
                'tilt_down': config.PIN_MCP_TILT_DOWN,
                'hook_up': config.PIN_MCP_HOOK_UP,
                'hook_down': config.PIN_MCP_HOOK_DOWN
            }

            for key, (port, bit) in mapping.items():
                byte_val = val_a if port == 'A' else val_b
                is_high = bool((byte_val >> bit) & 1)
                states[key] = is_high if config.MCP_ACTIVE_HIGH else not is_high

            out_port, out_bit = config.PIN_MCP_SERVO_ERR_CLEAR
            olat = self.olat_a if out_port == 'A' else self.olat_b
            states['servo_err_clear'] = bool((olat >> out_bit) & 1)
        except Exception:
            pass
        return states

    def set_output(self, port, pin, level):
        if not self.connected or not self.bus: return
        try:
            if port == 'A':
                if level: self.olat_a |= (1 << pin)
                else: self.olat_a &= ~(1 << pin)
                self.bus.write_byte_data(self.addr, self.OLATA, self.olat_a)
            else:
                if level: self.olat_b |= (1 << pin)
                else: self.olat_b &= ~(1 << pin)
                self.bus.write_byte_data(self.addr, self.OLATB, self.olat_b)
        except Exception as e:
            print(f"❌ Output write failed: {e}")


class MockMCP23017:
    def __init__(self):
        self.states = {
            'spin_cw': False, 'spin_acw': False, 'spin_ref': False,
            'trolley_front': False, 'trolley_back': False,
            'tilt_up': False, 'tilt_down': False,
            'hook_up': False, 'hook_down': False,
            'servo_err_clear': False
        }
    def read_all_inputs(self):
        return self.states.copy()
    def set_output(self, port, pin, level):
        self.states['servo_err_clear'] = bool(level)


class FastCraneHardware:
    def __init__(self):
        self.connected = False
        self.dac_files = {}  # Dictionary mapped by channel index
        self.dac_scale = 0.000305175
        self.dac_offset = 32768
        self.adc_dev = None

        try:
            base = "/sys/bus/iio/devices"
            dac_path, adc_path = None, None
            if os.path.exists(base):
                for d in os.listdir(base):
                    if "iio:device" in d:
                        try:
                            name = open(f"{base}/{d}/name").read().strip()
                            if "ltc2688" in name: dac_path = f"{base}/{d}"
                            if "ad7124" in name: adc_path = f"{base}/{d}"
                        except Exception:
                            pass

            if not dac_path: dac_path = "/sys/bus/iio/devices/iio:device0"
            if not adc_path: adc_path = "/sys/bus/iio/devices/iio:device1"

            # Open all configured DAC channel files explicitly
            for ch in config.AXIS_TO_DAC_MAP.values():
                try:
                    with open(f"{dac_path}/out_voltage{ch}_powerdown", 'w') as f:
                        f.write("0")
                except Exception:
                    pass
                try:
                    self.dac_files[ch] = open(f"{dac_path}/out_voltage{ch}_raw", 'w')
                except Exception as e:
                    print(f"⚠️ Could not open DAC channel {ch}: {e}")

            try:
                self.dac_scale = float(open(f"{dac_path}/out_voltage0_scale").read())
                self.dac_offset = int(open(f"{dac_path}/out_voltage0_offset").read())
            except Exception:
                pass

            self.adc_dev = adc_path
            self.debug_reg = f"/sys/kernel/debug/iio/{os.path.basename(adc_path)}/direct_reg_access"
            self.connected = True
            print(f"✅ Analog Hardware: DAC={dac_path} (Active Channels: {list(self.dac_files.keys())}), ADC={adc_path}")
        except Exception as e:
            print(f"❌ HW INIT ERROR: {e}")

    def set_voltage(self, ch, volts):
        if not self.connected or ch not in self.dac_files: return
        try:
            target_mv = float(volts) * 1000.0
            raw = int((target_mv / self.dac_scale) - self.dac_offset)
            raw = max(0, min(65535, raw))
            f = self.dac_files[ch]
            f.seek(0)
            f.write(str(raw) + "\n")
            f.flush()
        except Exception:
            pass

    def read_adcs(self):
        if not self.connected: 
            return [0.0] * config.TOTAL_ADC_CHANNELS
        res = [0.0] * config.TOTAL_ADC_CHANNELS
        for i in range(config.TOTAL_ADC_CHANNELS):
            try:
                try:
                    with open(self.debug_reg, 'w') as f:
                        f.write(f"0x{0x19+i:X} 0x0860")
                except Exception:
                    pass

                raw_path = f"{self.adc_dev}/in_voltage{i*2}-voltage{i*2+1}_raw"
                if not os.path.exists(raw_path):
                    raw_path = f"{self.adc_dev}/in_voltage{i}_raw"

                if os.path.exists(raw_path):
                    with open(raw_path, 'r') as f:
                        raw = int(f.read())
                    v = ((raw - config.HARDWARE_OFFSET) / float(config.HARDWARE_OFFSET)) * config.HARDWARE_FULL_SCALE * config.ADC_SCALING_FACTOR
                    res[i] = round(v, 3)
            except Exception:
                res[i] = 0.0
        return res


class EncoderReader:
    def __init__(self, pi, gpioA, gpioB, gpioIndex=None):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.gpioIndex = gpioIndex
        self.pos = 0
        self.levA = 0
        self.levB = 0

        for pin in [gpioA, gpioB]:
            self.pi.set_mode(pin, pigpio.INPUT)
            self.pi.set_pull_up_down(pin, pigpio.PUD_UP)
            self.pi.set_glitch_filter(pin, 2000)

        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

        if gpioIndex is not None:
            self.pi.set_mode(gpioIndex, pigpio.INPUT)
            self.pi.set_pull_up_down(gpioIndex, pigpio.PUD_UP)
            self.pi.set_glitch_filter(gpioIndex, 2000)
            self.cbInd = self.pi.callback(gpioIndex, pigpio.RISING_EDGE, self._index_pulse)

    def _pulse(self, gpio, level, tick):
        if gpio == self.gpioA: self.levA = level
        else: self.levB = level

        if True: 
            if gpio == self.gpioA and level == 1:
                if self.levB == 1: self.pos += 1
                else: self.pos -= 1
            elif gpio == self.gpioB and level == 1:
                if self.levA == 1: self.pos -= 1
                else: self.pos += 1

    def _index_pulse(self, gpio, level, tick):
        pass

    def reset(self):
        self.pos = 0


class MockHardware:
    """Simulation hardware: safely reflects sparse high channel counts."""
    def __init__(self):
        self.voltages = [0.0] * config.TOTAL_DAC_CHANNELS

    def set_voltage(self, ch, volts):
        if 0 <= ch < len(self.voltages):
            self.voltages[ch] = float(volts)

    def read_adcs(self):
        t = time.time()
        readings = [0.0] * config.TOTAL_ADC_CHANNELS
        joy_channels = set(config.JOYSTICK_ADC_CHANNELS.values())

        for ch in range(config.TOTAL_ADC_CHANNELS):
            if ch in joy_channels:
                readings[ch] = 0.0  # Centered in simulation
            else:
                readings[ch] = round(math.sin(t + ch) * 2.5, 3)

        return readings

class MockEncoder:
    def __init__(self): self.pos = 0
    def reset(self): self.pos = 0