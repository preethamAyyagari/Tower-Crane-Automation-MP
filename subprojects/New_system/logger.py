import os
import sqlite3
import time
import threading
from datetime import datetime
import config

class CraneDataLogger:
    def __init__(self, controller):
        self.controller = controller
        self.is_logging = False
        self.log_thread = None
        self.db_path = None
        self.conn = None
        self.cursor = None

        # Resolve logs directory: 2 folders above this code
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.logs_dir = os.path.abspath(os.path.join(base_dir, config.LOGS_DIR_RELATIVE))
        os.makedirs(self.logs_dir, exist_ok=True)

        # Table names for each channel
        self.tables = {
            # ADC Sensors
            f"adc_{config.ADC_CH_JOYSTICK_X}_joy_x": "Joystick X Input",
            f"adc_{config.ADC_CH_JOYSTICK_Y}_joy_y": "Joystick Y Input",
            f"adc_{config.ADC_CH_HOOK_SENSOR}_hook": "Hook Sensor",
            f"adc_{config.ADC_CH_TILT_SENSOR}_tilt": "Tilt Sensor",
            f"adc_{config.ADC_CH_SWING_ALPHA}_alpha": "Swing Alpha Sensor",
            f"adc_{config.ADC_CH_SWING_BETA}_beta": "Swing Beta Sensor",
            # DAC Channels
            f"dac_{config.DAC_CH_SPIN}_spin": "Spin Motor DAC Output",
            f"dac_{config.DAC_CH_TROLLEY}_trolley": "Trolley Motor DAC Output",
            f"dac_{config.DAC_CH_HOOK}_hook": "Hook DAC Output",
            f"dac_{config.DAC_CH_TILT}_tilt": "Tilt DAC Output"
        }

    def start(self):
        if self.is_logging:
            return self.db_path

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.db_path = os.path.join(self.logs_dir, f"crane_log_{timestamp_str}.db")
        
        # Initialize SQLite DB and create individual tables
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

        for table_name in self.tables.keys():
            self.cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    timestamp REAL,
                    value REAL
                )
            """)
        self.conn.commit()

        self.is_logging = True
        self.log_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.log_thread.start()
        print(f" Logging started: {self.db_path} (Interval: {config.LOGGING_INTERVAL_SEC}s)")
        return self.db_path

    def stop(self):
        if not self.is_logging:
            return None

        self.is_logging = False
        if self.log_thread:
            self.log_thread.join(timeout=1.0)
        
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None
            self.cursor = None

        print(f" Logging saved and closed: {self.db_path}")
        path = self.db_path
        self.db_path = None
        return path

    def _log_worker(self):
        start_time = time.time()
        interval = config.LOGGING_INTERVAL_SEC

        while self.is_logging:
            cycle_start = time.time()
            elapsed_time = round(cycle_start - start_time, 4)

            # Fetch fresh hardware snapshot
            status = self.controller.get_status()
            adcs = status['adc']
            dacs = status['dac']

            try:
                # 1. Insert ADC channel readings
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_JOYSTICK_X}_joy_x VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_JOYSTICK_X]))
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_JOYSTICK_Y}_joy_y VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_JOYSTICK_Y]))
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_HOOK_SENSOR}_hook VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_HOOK_SENSOR]))
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_TILT_SENSOR}_tilt VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_TILT_SENSOR]))
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_SWING_ALPHA}_alpha VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_SWING_ALPHA]))
                self.cursor.execute(f"INSERT INTO adc_{config.ADC_CH_SWING_BETA}_beta VALUES (?, ?)", (elapsed_time, adcs[config.ADC_CH_SWING_BETA]))

                # 2. Insert DAC output readings
                self.cursor.execute(f"INSERT INTO dac_{config.DAC_CH_SPIN}_spin VALUES (?, ?)", (elapsed_time, dacs[config.DAC_CH_SPIN]))
                self.cursor.execute(f"INSERT INTO dac_{config.DAC_CH_TROLLEY}_trolley VALUES (?, ?)", (elapsed_time, dacs[config.DAC_CH_TROLLEY]))
                self.cursor.execute(f"INSERT INTO dac_{config.DAC_CH_HOOK}_hook VALUES (?, ?)", (elapsed_time, dacs[config.DAC_CH_HOOK]))
                self.cursor.execute(f"INSERT INTO dac_{config.DAC_CH_TILT}_tilt VALUES (?, ?)", (elapsed_time, dacs[config.DAC_CH_TILT]))

                self.conn.commit()
            except Exception as e:
                print(f" SQL Logging Error: {e}")

            # Precise execution timing
            spent = time.time() - cycle_start
            sleep_time = interval - spent
            if sleep_time > 0:
                time.sleep(sleep_time)