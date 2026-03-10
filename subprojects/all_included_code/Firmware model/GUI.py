import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, 
                             QSpinBox, QGroupBox, QGridLayout, QFileDialog)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

import pyqtgraph as pg

# Import our hardware backend
from simulation import CraneFirmware

class ChannelWidget(QGroupBox):
    def __init__(self, ch_id, firmware):
        super().__init__(f"CH {ch_id}")
        self.ch_id = ch_id
        self.firmware = firmware
        
        # UI Styling
        self.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #7f8c8d; border-radius: 6px; margin-top: 10px; } "
                           "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #3498db; }")
        
        layout = QVBoxLayout()
        
        # --- Data Readouts ---
        data_layout = QHBoxLayout()
        self.adc_label = QLabel("0.000V")
        self.adc_label.setFont(QFont("Monospace", 16, QFont.Bold))
        self.adc_label.setStyleSheet("color: #2ecc71;")
        
        self.enc_label = QLabel("0" if ch_id < 4 else "MAN")
        self.enc_label.setFont(QFont("Monospace", 16, QFont.Bold))
        self.enc_label.setStyleSheet("color: #f1c40f;")
        
        data_layout.addWidget(self.adc_label)
        data_layout.addStretch()
        data_layout.addWidget(self.enc_label)
        layout.addLayout(data_layout)
        
        # --- Graph Plots ---
        # 1. Analog IN (ADC) Plot
        self.adc_plot_widget = pg.PlotWidget(title="Analog IN (ADC)")
        self.adc_plot_widget.setBackground('#34495e')
        self.adc_plot_widget.setYRange(-10.5, 10.5)
        self.adc_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.adc_plot_widget.setFixedHeight(120) # Keep layout from getting too tall
        self.adc_plot_line = self.adc_plot_widget.plot(pen=pg.mkPen(color='#2ecc71', width=2))
        layout.addWidget(self.adc_plot_widget)

        # 2. Analog OUT (DAC) Plot
        self.dac_plot_widget = pg.PlotWidget(title="Analog OUT (DAC)")
        self.dac_plot_widget.setBackground('#34495e')
        self.dac_plot_widget.setYRange(-10.5, 10.5)
        self.dac_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.dac_plot_widget.setFixedHeight(120) # Keep layout from getting too tall
        self.dac_plot_line = self.dac_plot_widget.plot(pen=pg.mkPen(color='#e74c3c', width=2)) # Red line for output
        layout.addWidget(self.dac_plot_widget)

        # Arrays to hold time and voltage data for rolling graph
        self.time_data = []
        self.adc_volt_data = []
        self.dac_volt_data = []
        self.start_time = time.time()
        self.current_dac_out = 0.0 # Track commanded voltage
        
        # --- Inputs ---
        input_layout = QHBoxLayout()
        
        self.voltage_input = QDoubleSpinBox()
        self.voltage_input.setRange(-10.0, 10.0)
        self.voltage_input.setSingleStep(0.1)
        self.voltage_input.setValue(2.0)
        self.voltage_input.setSuffix(" V")
        input_layout.addWidget(self.voltage_input)
        
        if self.ch_id < 4:
            self.target_input = QSpinBox()
            self.target_input.setRange(-100000, 100000)
            self.target_input.setSingleStep(100)
            self.target_input.setValue(1000)
            input_layout.addWidget(self.target_input)
            
        layout.addLayout(input_layout)
        
        # --- Buttons ---
        self.go_btn = QPushButton("GO")
        self.go_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px;")
        self.go_btn.clicked.connect(self.send_go)
        layout.addWidget(self.go_btn)
        
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 8px;")
        self.stop_btn.clicked.connect(self.send_stop)
        layout.addWidget(self.stop_btn)
        
        if self.ch_id < 4:
            self.zero_btn = QPushButton("Zero")
            self.zero_btn.setStyleSheet("background-color: #7f8c8d; color: white; padding: 5px;")
            self.zero_btn.clicked.connect(self.send_zero)
            layout.addWidget(self.zero_btn)
            
        self.setLayout(layout)

    def send_go(self):
        v = self.voltage_input.value()
        self.current_dac_out = v
        self.firmware.hw.set_voltage_fast(self.ch_id, v)
        if self.ch_id < 4:
            self.firmware.targets[self.ch_id] = self.target_input.value()

    def send_stop(self):
        self.current_dac_out = 0.0
        self.firmware.hw.set_voltage_fast(self.ch_id, 0.0)
        self.firmware.targets[self.ch_id] = None

    def send_zero(self):
        if self.ch_id < 4:
            self.firmware.encoders[self.ch_id].reset()
            
    def update_graph(self, current_time, adc_voltage, dac_voltage):
        # Append new data points
        self.time_data.append(current_time - self.start_time)
        self.adc_volt_data.append(adc_voltage)
        self.dac_volt_data.append(dac_voltage)
        
        # Keep a rolling window of the last 40 samples (approx 10 seconds at 250ms)
        if len(self.time_data) > 40:
            self.time_data.pop(0)
            self.adc_volt_data.pop(0)
            self.dac_volt_data.pop(0)
            
        # Update lines
        self.adc_plot_line.setData(self.time_data, self.adc_volt_data)
        self.dac_plot_line.setData(self.time_data, self.dac_volt_data)

class CraneGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Crane Controller")
        # Increased window size further to accommodate the stacked graphs
        self.resize(1300, 950)
        self.setStyleSheet("background-color: #2c3e50; color: white;")
        
        # Initialize Firmware
        try:
            self.fw = CraneFirmware()
        except Exception as e:
            print(f"Failed to load firmware: {e}")
            sys.exit(1)

        self.is_paused = False

        # Build UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout is now vertical to hold the top bar and the grid
        main_vbox = QVBoxLayout(central_widget)

        # --- Top Control Bar for Documentation ---
        top_bar = QHBoxLayout()
        
        self.pause_btn = QPushButton("⏸ Pause Plotting")
        self.pause_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        top_bar.addWidget(self.pause_btn)

        self.export_btn = QPushButton("📸 Save Screenshot")
        self.export_btn.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.export_btn.clicked.connect(self.export_screenshot)
        top_bar.addWidget(self.export_btn)
        
        top_bar.addStretch()
        main_vbox.addLayout(top_bar)

        # --- Grid Layout for Channels ---
        grid_layout = QGridLayout()
        self.channels = []
        for i in range(5):
            ch_widget = ChannelWidget(i, self.fw)
            self.channels.append(ch_widget)
            # Arrange in a grid: 3 on top, 2 on bottom
            row = 0 if i < 3 else 1
            col = i % 3
            grid_layout.addWidget(ch_widget, row, col)
            
        main_vbox.addLayout(grid_layout)

        # Setup Update Timer (250ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(250)

    def toggle_pause(self):
        if self.pause_btn.isChecked():
            self.is_paused = True
            self.pause_btn.setText("▶ Resume Plotting")
            self.pause_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        else:
            self.is_paused = False
            self.pause_btn.setText("⏸ Pause Plotting")
            self.pause_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")

    def export_screenshot(self):
        # Capture the entire window
        pixmap = self.grab()
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "crane_test_plot.png", "PNG Files (*.png);;JPEG Files (*.jpg)", options=options)
        if file_name:
            pixmap.save(file_name)

    def update_data(self):
        adc_vals = self.fw.hw.read_adcs_safe()
        enc_vals = [e.pos for e in self.fw.encoders]
        current_time = time.time()
        
        for i, ch in enumerate(self.channels):
            # Update labels
            ch.adc_label.setText(f"{adc_vals[i]:.3f}V")
            if i < 4:
                ch.enc_label.setText(str(enc_vals[i]))
                if self.fw.targets[i] is None:
                    ch.current_dac_out = 0.0 # If no target, we should be at 0V             
            # Update live graphs only if not paused
            if not self.is_paused:
                ch.update_graph(current_time, adc_vals[i], ch.current_dac_out)

    def closeEvent(self, event):
        """Ensure safe shutdown of hardware when window closes"""
        self.fw.shutdown()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CraneGUI()
    window.show()
    sys.exit(app.exec_())