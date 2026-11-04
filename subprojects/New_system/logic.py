import time
import threading
import config

class TrapezoidalProfileController:
    """
    Stepper-like Trapezoidal Motion Planner:
    - Ramps up linearly from start position.
    - Cruises at flat target voltage.
    - Begins linear ramp-down when 80% of the travel is completed (20% remaining).
    - Creeps into deadband and locks to zero.
    """
    def __init__(self, axis_name):
        self.axis_name = axis_name
        self.active = False
        self.start_pos = 0
        self.target_pos = 0
        self.total_distance = 0
        self.max_voltage = 0.0
        self.direction = 1.0
        
        # Profile tuning
        self.decel_threshold = 0.20  # Decelerate when 20% distance remains (80% finished)
        self.min_creep_v = 0.35      # Minimum creep voltage to prevent motor stall before zero
        self.deadband = 4            # Snap threshold in encoder pulses

    def start_move(self, current_pos, target_pos, voltage):
        self.start_pos = current_pos
        self.target_pos = target_pos
        self.total_distance = abs(target_pos - current_pos)
        self.max_voltage = abs(float(voltage))
        self.direction = 1.0 if (target_pos >= current_pos) else -1.0
        self.active = True
        print(f"🚀 [STEPPER PROFILE] {self.axis_name.upper()} Move: {current_pos} -> {target_pos} (Dist={self.total_distance}, V={self.max_voltage})")

    def update(self, current_pos):
        """Returns (command_voltage, is_finished)."""
        if not self.active:
            return 0.0, True

        remaining_dist = abs(self.target_pos - current_pos)
        traveled_dist = self.total_distance - remaining_dist

        # 1. Target Reached: Snap & Lock
        if remaining_dist <= self.deadband or (self.direction > 0 and current_pos >= self.target_pos) or (self.direction < 0 and current_pos <= self.target_pos):
            self.active = False
            return 0.0, True

        # Edge case: Very short moves
        if self.total_distance <= (self.deadband * 2):
            return self.direction * self.min_creep_v, False

        # 2. Deceleration Phase: At or past 80% completed
        remaining_ratio = remaining_dist / float(self.total_distance)
        if remaining_ratio <= self.decel_threshold:
            # Linear ramp from max_voltage down to min_creep_v across the final 20%
            scale = remaining_ratio / self.decel_threshold
            v = self.min_creep_v + (self.max_voltage - self.min_creep_v) * scale
            return self.direction * round(v, 2), False

        # 3. Acceleration Phase: Initial 20% from start
        accel_threshold = 0.20
        traveled_ratio = max(0.0, traveled_dist) / float(self.total_distance)
        if traveled_ratio < accel_threshold:
            scale = traveled_ratio / accel_threshold
            v = self.min_creep_v + (self.max_voltage - self.min_creep_v) * scale
            return self.direction * round(v, 2), False

        # 4. Flat Cruise Phase (Between 20% and 80%)
        return self.direction * self.max_voltage, False

    def abort(self):
        self.active = False


class CraneController:
    def __init__(self, hw, encoders, mcp, is_sim=False):
        self.hw = hw
        self.encoders = encoders
        self.mcp = mcp
        self.is_sim = is_sim
        
        self.dac_raw_targets = [0.0] * config.TOTAL_DAC_CHANNELS
        self.dac_voltages    = [0.0] * config.TOTAL_DAC_CHANNELS

        # Trapezoidal Profile Planners for Spin and Trolley
        self.profiles = {
            'spin': TrapezoidalProfileController('spin'),
            'trolley': TrapezoidalProfileController('trolley')
        }

        self.joystick_enabled = True
        self.joystick_active = False
        self.running = True
        self.last_loop_time = time.time()
        self.mcp_states = {}

        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def pulse_servo_error_clear(self):
        def _pulse_thread():
            port, pin = config.PIN_MCP_SERVO_ERR_CLEAR
            print("⚡ Raising Servo Error Clear Output to HIGH (+5V)...")
            self.mcp.set_output(port, pin, True)
            time.sleep(config.SERVO_RESET_PULSE_SEC)
            self.mcp.set_output(port, pin, False)
            print("⚡ Servo Error Clear Output Returned to LOW (0V).")

        threading.Thread(target=_pulse_thread, daemon=True).start()

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
        """Called when user clicks 'MOVE TO POSITION' in GUI."""
        if axis in self.profiles:
            current = self.encoders[axis].pos
            self.profiles[axis].start_move(current, int(target_pos), float(voltage))

    def set_output_voltage(self, channel, volts):
        if 0 <= channel < len(self.dac_raw_targets):
            axis_name = config.DAC_TO_AXIS_MAP.get(channel)
            if axis_name and axis_name in self.profiles:
                self.profiles[axis_name].abort()

            self.dac_raw_targets[channel] = float(volts)
            self.dac_voltages[channel] = float(volts)
            self.hw.set_voltage(channel, float(volts))

    def stop_axis(self, channel):
        if 0 <= channel < len(self.dac_raw_targets):
            self.dac_raw_targets[channel] = 0.0
            self.dac_voltages[channel] = 0.0
            self.hw.set_voltage(channel, 0.0)

            axis_name = config.DAC_TO_AXIS_MAP.get(channel)
            if axis_name and axis_name in self.profiles:
                self.profiles[axis_name].abort()
                print(f"🛑 {axis_name.upper()} (DAC {channel}) STOPPED")

    def reset_encoder(self, axis):
        if axis in self.encoders:
            self.encoders[axis].reset()
            if axis in self.profiles:
                self.profiles[axis].abort()
            print(f"🔄 Reset Encoder {axis.upper()} to 0")

    def toggle_joystick(self, enabled):
        self.joystick_enabled = enabled
        print(f"🕹️ Joystick Auto-Control: {'ENABLED' if enabled else 'DISABLED'}")
        if not enabled:
            if not self.profiles['spin'].active:
                self.stop_axis(config.AXIS_TO_DAC_MAP['spin'])
            if not self.profiles['trolley'].active:
                self.stop_axis(config.AXIS_TO_DAC_MAP['trolley'])

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
                "spin": int(self.encoders['spin'].pos),
                "trolley": int(self.encoders['trolley'].pos)
            },
            "dac": self.dac_voltages,
            "limits": self.mcp_states
        }

    def _loop(self):
        while self.running:
            adcs = self.hw.read_adcs()
            self.mcp_states = self.mcp.read_all_inputs()

            ch_spin_dac    = config.AXIS_TO_DAC_MAP['spin']
            ch_trolley_dac = config.AXIS_TO_DAC_MAP['trolley']

            # 1. READ JOYSTICK
            if self.joystick_enabled:
                joy_v_spin = self._calc_joystick_axis(adcs[config.ADC_CH_JOYSTICK_X], config.JOYSTICK_INVERT_X)
                joy_v_trolley = self._calc_joystick_axis(adcs[config.ADC_CH_JOYSTICK_Y], config.JOYSTICK_INVERT_Y)
                joystick_is_moved = (abs(joy_v_spin) > 0.0 or abs(joy_v_trolley) > 0.0)
            else:
                joy_v_spin = 0.0
                joy_v_trolley = 0.0
                joystick_is_moved = False

            self.joystick_active = joystick_is_moved

            # 2. CONTROL ARBITRATION
            if self.joystick_active:
                # Manual stick input aborts any active trapezoidal target
                self.profiles['spin'].abort()
                self.profiles['trolley'].abort()
                self.dac_raw_targets[ch_spin_dac]    = joy_v_spin
                self.dac_raw_targets[ch_trolley_dac] = joy_v_trolley
            else:
                # 3. TRAPEZOIDAL STEPPER PROFILES (SPIN & TROLLEY)
                for axis in ['spin', 'trolley']:
                    ch = config.AXIS_TO_DAC_MAP[axis]
                    profile = self.profiles[axis]
                    
                    if profile.active:
                        current_pos = self.encoders[axis].pos
                        target_v, finished = profile.update(current_pos)
                        
                        if finished:
                            self.stop_axis(ch)
                            if self.is_sim:
                                self.encoders[axis].pos = profile.target_pos
                            print(f"🏁 [STEPPER PROFILE] {axis.upper()} Locked at Target: {self.encoders[axis].pos}")
                        else:
                            self.dac_raw_targets[ch] = target_v

            # 4. LIMIT SWITCH SAFETY CUT-OFF
            if self.mcp_states.get('spin_cw') and self.dac_raw_targets[ch_spin_dac] > 0:
                self.dac_raw_targets[ch_spin_dac] = 0.0
                self.profiles['spin'].abort()
            if self.mcp_states.get('spin_acw') and self.dac_raw_targets[ch_spin_dac] < 0:
                self.dac_raw_targets[ch_spin_dac] = 0.0
                self.profiles['spin'].abort()

            if self.mcp_states.get('trolley_front') and self.dac_raw_targets[ch_trolley_dac] > 0:
                self.dac_raw_targets[ch_trolley_dac] = 0.0
                self.profiles['trolley'].abort()
            if self.mcp_states.get('trolley_back') and self.dac_raw_targets[ch_trolley_dac] < 0:
                self.dac_raw_targets[ch_trolley_dac] = 0.0
                self.profiles['trolley'].abort()

            ch_hook_dac = config.AXIS_TO_DAC_MAP['hook']
            ch_tilt_dac = config.AXIS_TO_DAC_MAP['tilt']

            if self.mcp_states.get('hook_up') and self.dac_raw_targets[ch_hook_dac] > 0:
                self.dac_raw_targets[ch_hook_dac] = 0.0
                self.hw.set_voltage(ch_hook_dac, 0.0)
            if self.mcp_states.get('hook_down') and self.dac_raw_targets[ch_hook_dac] < 0:
                self.dac_raw_targets[ch_hook_dac] = 0.0
                self.hw.set_voltage(ch_hook_dac, 0.0)

            if self.mcp_states.get('tilt_up') and self.dac_raw_targets[ch_tilt_dac] > 0:
                self.dac_raw_targets[ch_tilt_dac] = 0.0
                self.hw.set_voltage(ch_tilt_dac, 0.0)
            if self.mcp_states.get('tilt_down') and self.dac_raw_targets[ch_tilt_dac] < 0:
                self.dac_raw_targets[ch_tilt_dac] = 0.0
                self.hw.set_voltage(ch_tilt_dac, 0.0)

            # 5. WRITE VOLTAGES TO HARDWARE
            for axis in ['spin', 'trolley']:
                ch = config.AXIS_TO_DAC_MAP[axis]
                v = self.dac_raw_targets[ch]
                self.dac_voltages[ch] = v
                self.hw.set_voltage(ch, v)

            # 6. SIMULATION PHYSICS ENGINE (Progresses encoder according to trapezoidal velocity)
            if self.is_sim:
                for axis in ['spin', 'trolley']:
                    ch = config.AXIS_TO_DAC_MAP[axis]
                    v = self.dac_voltages[ch]
                    if abs(v) > 0.05:
                        step_increment = int(v * 4)
                        if step_increment == 0:
                            step_increment = 1 if v > 0 else -1
                        self.encoders[axis].pos += step_increment

            time.sleep(0.01 if self.is_sim else 0.005)