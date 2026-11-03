import pigpio
import config
from hardware import FastCraneHardware, EncoderReader, MockHardware, MockEncoder
from logic import CraneController
from logger import CraneDataLogger
from gui import create_app

def main():
    pi = pigpio.pi()
    is_sim = not pi.connected

    if is_sim:
        print(" HARDWARE NOT DETECTED: Running in Simulation Mode.")
        hw = MockHardware()
        encoders = {
            'spin': MockEncoder(),
            'trolley': MockEncoder()
        }
    else:
        print(" HARDWARE DETECTED: Initializing CM4 GPIO, IIO bus, and Encoders...")
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

    # Core motion and arbitration controller
    controller = CraneController(hw, encoders, is_sim=is_sim)

    # SQLite data logging engine
    logger = CraneDataLogger(controller)

    # Telemetry web server
    app = create_app(controller, logger)
    print("🚀 Telemetry & Logging UI operational on http://0.0.0.0:5002")
    app.run(host='0.0.0.0', port=5002, debug=False)

if __name__ == '__main__':
    main()