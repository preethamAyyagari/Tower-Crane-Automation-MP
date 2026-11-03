import time
import threading
import config

class SCurveRamp:
    def __init__(self, max_accel, max_jerk):
        self.current_val = 0.0
        self.current_rate = 0.0
        self.max_accel = max_accel
        self.max_jerk = max_jerk

    def update(self, target, dt):
        error = target - self.current_val

        desired_rate = error / max(dt, 0.001)
        desired_rate = max(-self.max_accel, min(self.max_accel, desired_rate))

        rate_error = desired_rate - self.current_rate
        max_rate_delta = self.max_jerk * dt
        rate_change = max(-max_rate_delta, min(max_rate_delta, rate_error))
        
        self.current_rate += rate_change
        self.current_rate = max(-self.max_accel, min(self.max_accel, self.current_rate))

        val_delta = self.current_rate * dt
        self.current_val += val_delta

        if abs(target - self.current_val) < 0.05 and abs(self.current_rate) < 0.1:
            self.current_val = target
            self.current_rate = 0.0

        return round(self.current_val, 3)

    def hard_reset(self, val=0.0):
        self.current_val = val
        self.current_rate = 0.0


class CraneController:
    def __init__(self, hw, encoders, is_sim=False):
        self.hw = hw
        self.encoders = encoders
        self.is_sim = is_sim
        
        self.targets = {'spin': None, 'trolley': None}
        self.target_voltages = {'spin': 0.0, 'trolley': 0.0}
        self.dac_raw_targets = [0.0] * 4
        self.dac_voltages = [0.0] * 4
        
        self.ramps = {
            'spin': SCurveRamp(config.MAX_ACCEL_V_PER_SEC, config.MAX_JERK_V_PER_SEC2),
            'trolley': SCurveRamp(config.MAX_ACCEL_V_PER_SEC, config.MAX_JERK_V_PER_SEC2)
        }

        self.joystick_enabled = True
        self.joystick_active = False
        self.running = True
        self.last_loop_time = time.time()

        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def _calc_joystick_axis(self, raw_voltage, invert=False):
        delta = raw_voltage - config.JOYSTICK_CENTER_V
        if abs(delta) < config.JOYSTICK_DEADBAND_V:
            return 0.0

        sign = 1.0 if delta > 0 else -1.0
        effective_delta = delta - (sign * config.JOYSTICK_DEADBAND_V)
        max_travel = config.JOYSTICK_MAX_DEFLECTION_V - config.JOYSTICK_DEADBAND_V
        
        normalized = effective_delta / max_travel
        normalized = max(-1.0, min(1.0, normalized))
        if invert:
            normalized = -normalized

        return round(normalized * config.JOYSTICK_MAX_OUTPUT_V, 2)

    def set_target(self, axis, target_pos, voltage):
        """Sets closed-loop encoder target from GUI."""
        if axis in self.targets:
            self.targets[axis] = target_pos
            self.target_voltages[axis] = abs(float(voltage))

    def set_output_voltage(self, channel, volts):
        """Sets direct target voltage (Hook, Tilt, or Manual)."""
        if 0 <= channel < 4:
            # If manually commanding spin/trolley, cancel closed-loop positioning target
            if channel == config.DAC_CH_SPIN: self.targets['spin'] = None
            if channel == config.DAC_CH_TROLLEY: self.targets['trolley'] = None

            self.dac_raw_targets[channel] = float(volts)
            if channel in [config.DAC_CH_HOOK, config.DAC_CH_TILT]:
                self.dac_voltages[channel] = float(volts)
                self.hw.set_voltage(channel, float(volts))

    def stop_axis(self, channel):
        """Immediate hard stop: clears targets, ramps, and physical DAC output."""
        self.dac_raw_targets[channel] = 0.0
        self.dac_voltages[channel] = 0.0
        self.hw.set_voltage(channel, 0.0)

        if channel == config.DAC_CH_SPIN:
            self.targets['spin'] = None
            self.ramps['spin'].hard_reset(0.0)
        elif channel == config.DAC_CH_TROLLEY:
            self.targets['trolley'] = None
            self.ramps['trolley'].hard_reset(0.0)

    def reset_encoder(self, axis):
        if axis in self.encoders:
            self.encoders[axis].reset()

    def toggle_joystick(self, enabled):
        self.joystick_enabled = enabled
        if not enabled:
            self.stop_axis(config.DAC_CH_SPIN)
            self.stop_axis(config.DAC_CH_TROLLEY)

    def get_status(self):
        raw_adcs = self.hw.read_adcs()
        return {
            "adc": raw_adcs,
            "joy": {
                "x_raw": raw_adcs[config.ADC_CH_JOYSTICK_X],
                "y_raw": raw_adcs[config.ADC_CH_JOYSTICK_Y],
                "enabled": self.joystick_enabled,
                "in_use": self.joystick_active
            },
            "enc": {
                "spin": self.encoders['spin'].pos,
                "trolley": self.encoders['trolley'].pos
            },
            "dac": self.dac_voltages
        }

    def _loop(self):
        while self.running:
            now = time.time()
            dt = max(0.001, now - self.last_loop_time)
            self.last_loop_time = now

            adcs = self.hw.read_adcs()

            # 1. READ JOYSTICK
            joy_v_spin = self._calc_joystick_axis(adcs[config.ADC_CH_JOYSTICK_X], config.JOYSTICK_INVERT_X)
            joy_v_trolley = self._calc_joystick_axis(adcs[config.ADC_CH_JOYSTICK_Y], config.JOYSTICK_INVERT_Y)

            joystick_is_moved = (abs(joy_v_spin) > 0.0 or abs(joy_v_trolley) > 0.0)
            self.joystick_active = joystick_is_moved and self.joystick_enabled

            # 2. CONTROL ARBITRATION
            if self.joystick_enabled and joystick_is_moved:
                # Joystick overrides active targets
                self.targets['spin'] = None
                self.targets['trolley'] = None
                self.dac_raw_targets[config.DAC_CH_SPIN] = joy_v_spin
                self.dac_raw_targets[config.DAC_CH_TROLLEY] = joy_v_trolley

          # 3. CLOSED-LOOP POSITIONING (Smooth Deceleration Profile)
            for axis, ch in [('spin', config.DAC_CH_SPIN), ('trolley', config.DAC_CH_TROLLEY)]:
                target_pos = self.targets[axis]
                if target_pos is not None:
                    pos_error = target_pos - self.encoders[axis].pos
                    deadband_margin = 4       # Snapping threshold in encoder counts
                    slowdown_zone = 80         # Start deceleration 80 counts before target
                    min_creep_v = 0.4          # Minimum voltage to overcome real mechanical stiction

                    if abs(pos_error) <= deadband_margin:
                        # Target reached: hard stop and lock
                        self.stop_axis(ch)
                        if self.is_sim: 
                            self.encoders[axis].pos = target_pos
                    else:
                        direction = 1.0 if pos_error > 0 else -1.0
                        distance = abs(pos_error)

                        if distance > slowdown_zone:
                            # Cruise at full commanded speed
                            cmd_v = self.target_voltages[axis]
                        else:
                            # Smooth proportional ramp down to avoid overshoot
                            ratio = distance / float(slowdown_zone)
                            cmd_v = max(min_creep_v, self.target_voltages[axis] * ratio)

                        self.dac_raw_targets[ch] = direction * cmd_v

            # 4. S-CURVE SMOOTHING & OUTPUT TO HARDWARE
            for axis, ch in [('spin', config.DAC_CH_SPIN), ('trolley', config.DAC_CH_TROLLEY)]:
                # Skip ramp if target is already achieved and stopped
                if self.targets[axis] is None and self.dac_raw_targets[ch] == 0.0 and abs(self.dac_voltages[ch]) < 0.05:
                    self.dac_voltages[ch] = 0.0
                    self.hw.set_voltage(ch, 0.0)
                else:
                    ramped_v = self.ramps[axis].update(self.dac_raw_targets[ch], dt)
                    self.dac_voltages[ch] = ramped_v
                    self.hw.set_voltage(ch, ramped_v)

            # 5. SIMULATION PHYSICS FEEDBACK
            if self.is_sim:
                for idx, axis in enumerate(['spin', 'trolley']):
                    v = self.dac_voltages[idx]
                    if abs(v) > 0.05:
                        self.encoders[axis].pos += int(v * 4)

            time.sleep(0.01 if self.is_sim else 0.005)