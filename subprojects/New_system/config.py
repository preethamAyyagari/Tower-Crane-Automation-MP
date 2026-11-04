# ==============================================================================
#                      CRANE SYSTEM HARDWARE CONFIGURATION
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. PIGPIO ENCODER PIN DEFINITIONS (BCM GPIO Numbering)
# ------------------------------------------------------------------------------
# Spin Encoder
PIN_SPIN_ENC_A     = 21  # Physical pin 40
PIN_SPIN_ENC_B     = 19  # Physical pin 35
PIN_SPIN_ENC_INDEX = 20  # Physical pin 38

# Trolley Encoder
PIN_TROLLEY_ENC_A     = 6   # gpio 6, Physical pin 31
PIN_TROLLEY_ENC_B     = 5   # gpio 5, Physical pin 29
PIN_TROLLEY_ENC_INDEX = 13  # gpio 13, Physical pin 33


# ------------------------------------------------------------------------------
# 2. DAC CHANNELS (Analog Voltage Output - LTC2688)
# ------------------------------------------------------------------------------
DAC_CH_SPIN    = 6   # Output voltage to Spin Motor Driver
DAC_CH_TROLLEY = 2   # Output voltage to Trolley Motor Driver
DAC_CH_HOOK    = 4   # Output voltage to Hook Motor Driver
DAC_CH_TILT    = 0   # Output voltage to Tilt Motor Driver

# Total allocated DAC size in memory (must be > max(DAC_CH_*))
TOTAL_DAC_CHANNELS = 16


# ------------------------------------------------------------------------------
# 3. ADC CHANNELS ON CN0554 (Analog Voltage Input - AD7124)
# ------------------------------------------------------------------------------
ADC_CH_SWING_ALPHA = 0   # Alpha Axis Swing Angle
ADC_CH_SWING_BETA  = 2   # Beta Axis Swing Angle
ADC_CH_JOYSTICK_X  = 4   # Joystick X-Axis (-12V to +12V) -> Controls SPIN
ADC_CH_JOYSTICK_Y  = 6   # Joystick Y-Axis (-12V to +12V) -> Controls TROLLEY
ADC_CH_HOOK_SENSOR = 8   # Hook sensor
ADC_CH_TILT_SENSOR = 10  # Tilt sensor

# Total allocated ADC size in memory (must be > max(ADC_CH_*))
TOTAL_ADC_CHANNELS = 16


# ------------------------------------------------------------------------------
# 4. BIPOLAR (+/- 12V) JOYSTICK CALIBRATION & BEHAVIOR
# ------------------------------------------------------------------------------
JOYSTICK_CENTER_V         = 0.0
JOYSTICK_DEADBAND_V       = 0.50
JOYSTICK_MAX_DEFLECTION_V = 12.0
JOYSTICK_MAX_OUTPUT_V     = 10.0
JOYSTICK_INVERT_X         = False
JOYSTICK_INVERT_Y         = False


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
RAMP_GUI_COMMANDS   = True


# ------------------------------------------------------------------------------
# 7. SQLITE LOGGING CONFIGURATION
# ------------------------------------------------------------------------------
LOGGING_INTERVAL_SEC = 0.1
LOGS_DIR_RELATIVE    = "../../logs"


# ------------------------------------------------------------------------------
# 8. MCP23017 WAVESHARE I2C EXPANDER (5V Logic)
# ------------------------------------------------------------------------------
MCP23017_I2C_BUS  = 1
MCP23017_I2C_ADDR = 0x27
MCP_ACTIVE_HIGH   = True

PIN_MCP_SPIN_CW_LIMIT   = ('B', 1)
PIN_MCP_SPIN_ACW_LIMIT  = ('B', 3)
PIN_MCP_SPIN_REF        = ('A', 0)
PIN_MCP_TROLLEY_FRONT   = ('B', 5)
PIN_MCP_TROLLEY_BACK    = ('B', 7)
PIN_MCP_TILT_UP         = ('B', 6)
PIN_MCP_TILT_DOWN       = ('B', 4)
PIN_MCP_HOOK_UP         = ('B', 2)
PIN_MCP_HOOK_DOWN       = ('B', 0)
PIN_MCP_SERVO_ERR_CLEAR = ('A', 7)
SERVO_RESET_PULSE_SEC   = 1.0


# ------------------------------------------------------------------------------
# 9. DYNAMIC LOOKUP TABLES
# ------------------------------------------------------------------------------
AXIS_TO_DAC_MAP = {
    'spin': DAC_CH_SPIN,
    'trolley': DAC_CH_TROLLEY,
    'hook': DAC_CH_HOOK,
    'tilt': DAC_CH_TILT
}

DAC_TO_AXIS_MAP = {v: k for k, v in AXIS_TO_DAC_MAP.items()}

JOYSTICK_ADC_CHANNELS = {
    'spin': ADC_CH_JOYSTICK_X,
    'trolley': ADC_CH_JOYSTICK_Y
}