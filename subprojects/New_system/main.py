import pigpio
import config
from hardware import (
    FastCraneHardware, 
    EncoderReader, 
    MCP23017Driver, 
    MockHardware, 
    MockEncoder, 
    MockMCP23017
)
from logic import CraneController
from logger import CraneDataLogger
from gui import create_app

def main():
    pi = pigpio.pi()
    is_sim = not pi.connected

    if is_sim:
        print("⚠️ HARDWARE NOT DETECTED: Running in Simulation Mode.")
        hw = MockHardware()
        encoders = {
            'spin': MockEncoder(),
            'trolley': MockEncoder()
        }
        mcp = MockMCP23017()
    else:
        print("✅ HARDWARE DETECTED: Initializing CM4 GPIO, IIO bus, Encoders, and MCP23017...")
        hw = FastCraneHardware()
        encoders = {
            'spin': EncoderReader(
                pi, 
                gpioA=config.PIN_SPIN_ENC_A, 
                gpioB=config.PIN_SPIN_ENC_B, 
                gpioIndex=config.PIN_SPIN_ENC_INDEX
            ),
            'trolley': EncoderReader(
                pi, 
                gpioA=config.PIN_TROLLEY_ENC_A, 
                gpioB=config.PIN_TROLLEY_ENC_B, 
                gpioIndex=config.PIN_TROLLEY_ENC_INDEX
            )
        }
        
        # Instantiate MCP23017 with configured address, fallback to 0x20 if 0x27 fails
        mcp = MCP23017Driver(bus_id=config.MCP23017_I2C_BUS, addr=config.MCP23017_I2C_ADDR)
        if not mcp.connected:
            fallback_addr = 0x20 if config.MCP23017_I2C_ADDR == 0x27 else 0x27
            print(f" Trying alternate I2C address: 0x{fallback_addr:02X}...")
            mcp = MCP23017Driver(bus_id=config.MCP23017_I2C_BUS, addr=fallback_addr)

    # Motion coordinator
    controller = CraneController(hw, encoders, mcp, is_sim=is_sim)

    # SQLite data logger
    logger = CraneDataLogger(controller)

    # Telemetry and limit status web server
    app = create_app(controller, logger)
    print("🚀 Telemetry, 5V MCP23017 & Logging UI running on http://0.0.0.0:5002")
    app.run(host='0.0.0.0', port=5002, debug=False)

if __name__ == '__main__':
    main()