# ==============================================================================
#                      CRANE SYSTEM HARDWARE CONFIGURATION
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. PIGPIO ENCODER PIN DEFINITIONS (BCM GPIO Numbering, NOT Physical Board Pins)
# ------------------------------------------------------------------------------
PIN_SPIN_ENC_A     = 21
PIN_SPIN_ENC_B     = 19
PIN_SPIN_ENC_INDEX = 20

PIN_TROLLEY_ENC_A     = 6
PIN_TROLLEY_ENC_B     = 5
PIN_TROLLEY_ENC_INDEX = 13


# ------------------------------------------------------------------------------
# 2. DAC CHANNELS (Analog Voltage Output: 0 to 3)
# ------------------------------------------------------------------------------
DAC_CH_SPIN    = 0   # Output voltage to Spin Motor Driver
DAC_CH_TROLLEY = 1   # Output voltage to Trolley Motor Driver
DAC_CH_HOOK    = 2   # Output voltage to Hook Motor Driver
DAC_CH_TILT    = 3   # Output voltage to Tilt Motor Driver


# ------------------------------------------------------------------------------
# 3. ADC CHANNELS ON CN0554 (Analog Voltage Input: 0 to 7)
# ------------------------------------------------------------------------------
ADC_CH_JOYSTICK_X = 0   # Joystick X-Axis (-12V to +12V) -> Controls SPIN
ADC_CH_JOYSTICK_Y = 1   # Joystick Y-Axis (-12V to +12V) -> Controls TROLLEY
ADC_CH_HOOK_SENSOR = 2  # Hook sensor
ADC_CH_TILT_SENSOR = 3  # Tilt sensor
ADC_CH_SWING_ALPHA = 4  # Alpha Axis Swing Angle
ADC_CH_SWING_BETA  = 5  # Beta Axis Swing Angle


# ------------------------------------------------------------------------------
# 4. BIPOLAR (+/- 12V) JOYSTICK CALIBRATION & BEHAVIOR
# ------------------------------------------------------------------------------
JOYSTICK_CENTER_V = 0.0
JOYSTICK_DEADBAND_V = 0.50
JOYSTICK_MAX_DEFLECTION_V = 12.0
JOYSTICK_MAX_OUTPUT_V = 10.0
JOYSTICK_INVERT_X = False
JOYSTICK_INVERT_Y = False


# ------------------------------------------------------------------------------
# 5. HARDWARE CHIP PARAMETERS (AD7124 / LTC2688)
# ------------------------------------------------------------------------------
ADC_SCALING_FACTOR  = 2.0016
HARDWARE_OFFSET     = 8388608
HARDWARE_FULL_SCALE = 13.75


# ------------------------------------------------------------------------------
# 6. S-CURVE ACCELERATION & RAMPING CONFIGURATION
# ------------------------------------------------------------------------------
MAX_ACCEL_V_PER_SEC = 12.0
MAX_JERK_V_PER_SEC2 = 30.0
RAMP_GUI_COMMANDS = True

# Tuning Recommendations
# Problem                                                       Cause                                                            Adjustment
# Crane feels sluggish:                           Acceleration limit too conservative                            Increase MAX_ACCEL_V_PER_SEC (e.g., from 12.0 to 20.0)
# Crane "thuds" on sudden reversals               Jerk transition too steep                                      Lower MAX_JERK_V_PER_SEC2 (e.g., from 30.0 to 15.0)
# Payload starts swinging when stick released     Deceleration slope excites natural frequency                   Lower MAX_ACCEL_V_PER_SEC to match crane pendulation period

# ------------------------------------------------------------------------------
# 7. SQLITE LOGGING CONFIGURATION
# ------------------------------------------------------------------------------
# Sampling interval in seconds (e.g., 0.1 for 10 Hz, 0.05 for 20 Hz, 0.01 for 100 Hz)
LOGGING_INTERVAL_SEC = 0.1

# Folder path: 2 folders above current script directory ('../../logs')
LOGS_DIR_RELATIVE = "../../logs"
