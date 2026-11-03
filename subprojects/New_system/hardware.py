import os
import pigpio
import time
import math
import random
import config

class FastCraneHardware:
    def __init__(self):
        self.connected = False
        self.dac_files = []
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

            for i in range(4):
                try:
                    with open(f"{dac_path}/out_voltage{i}_powerdown", 'w') as f:
                        f.write("0")
                except Exception:
                    pass
                self.dac_files.append(open(f"{dac_path}/out_voltage{i}_raw", 'w'))

            try:
                self.dac_scale = float(open(f"{dac_path}/out_voltage0_scale").read())
                self.dac_offset = int(open(f"{dac_path}/out_voltage0_offset").read())
            except Exception:
                pass

            self.adc_dev = adc_path
            self.debug_reg = f"/sys/kernel/debug/iio/{os.path.basename(adc_path)}/direct_reg_access"
            self.connected = True
            print(f"✅ Hardware Bound: DAC={dac_path}, ADC={adc_path}")
        except Exception as e:
            print(f"❌ HW INIT ERROR: {e}")

    def set_voltage(self, ch, volts):
        if not self.connected or ch >= len(self.dac_files): return
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
        if not self.connected: return [0.0] * 8
        res = []
        for i in range(8):
            try:
                try:
                    with open(self.debug_reg, 'w') as f:
                        f.write(f"0x{0x19+i:X} 0x0860")
                except Exception:
                    pass

                raw_path = f"{self.adc_dev}/in_voltage{i*2}-voltage{i*2+1}_raw"
                if not os.path.exists(raw_path):
                    raw_path = f"{self.adc_dev}/in_voltage{i}_raw"

                with open(raw_path, 'r') as f:
                    raw = int(f.read())
                v = ((raw - config.HARDWARE_OFFSET) / float(config.HARDWARE_OFFSET)) * config.HARDWARE_FULL_SCALE * config.ADC_SCALING_FACTOR
                res.append(round(v, 3))
            except Exception:
                res.append(0.0)
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
    def __init__(self):
        self.voltages = [0.0] * 4

    def set_voltage(self, ch, volts):
        if 0 <= ch < 4: self.voltages[ch] = float(volts)

    def read_adcs(self):
        t = time.time()
        # In simulation: Joystick sits cleanly at 0.0V (centered) so GUI controls work.
        # Sensors provide dynamic waveforms.
        return [
            0.0,                                # CH 0: Joy X (Centered)
            0.0,                                # CH 1: Joy Y (Centered)
            round(math.sin(t) * 4.0, 3),        # CH 2: Hook Sensor
            round(math.cos(t) * 2.5, 3),        # CH 3: Tilt Sensor
            round(math.sin(t * 1.5) * 3.5, 3),  # CH 4: Alpha Swing
            round(math.cos(t * 1.5) * 3.5, 3),  # CH 5: Beta Swing
            0.0, 0.0
        ]

class MockEncoder:
    def __init__(self): self.pos = 0
    def reset(self): self.pos = 0