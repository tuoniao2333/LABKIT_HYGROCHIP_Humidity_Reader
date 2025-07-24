# 20250724 by mawenjing
import sys
import serial
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, QSettings, Qt
from PyQt6.QtWidgets import (QMessageBox, QApplication, QLabel, QVBoxLayout, 
                             QWidget, QHBoxLayout, QComboBox, QPushButton)
import serial.tools.list_ports

class SerialWorker(QObject):
    humidityReceived = pyqtSignal(float)
    errorOccurred = pyqtSignal(str)
    connectionStatus = pyqtSignal(str)
    closeRequested = pyqtSignal()  
    
    def __init__(self, port_name):
        super().__init__()
        self.port_name = port_name
        self.serial = None
        self.timer = None
        self.buffer = ""
        
        self.closeRequested.connect(self.close_serial, Qt.ConnectionType.QueuedConnection)
        
    def connect_serial(self):
        try:
            self.serial = serial.Serial(
                port=self.port_name,
                baudrate=4800,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1
            )

            self.timer = QTimer()
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.read_data)
            self.timer.start()

            self.connectionStatus.emit("Connected")
            return True
        except serial.SerialException as e:
            self.errorOccurred.emit(f"port connect error: {str(e)}")
            return False
    
    def read_data(self):
        if not self.serial or not self.serial.is_open:
            return
        
        try:
            data = self.serial.readline().decode('ascii', errors='ignore')
            if data:
                print(f"Raw data received: {repr(data)}")
                self.buffer += data
                if '$' in self.buffer:
                    data_block, self.buffer = self.buffer.split('$', 1)
                    print(f"Data block: {repr(data_block)}")

                lines = data_block.split('\r')
                
                for line in lines:
                    line = line.strip()
                    
                    print(f"Processing line: {repr(line)}")
                    
                    if line.startswith('V01') or line.startswith('V02'):
                        if len(line) >= 7:  
                            humidity_hex = line[3:7]
                            
                            print(f"Extracted hex: {humidity_hex}")
                            
                            try:
                                humidity_value = int(humidity_hex, 16) * 0.005
                                
                                print(f"Calculated humidity: {humidity_value:.2f}%")
                                
                                self.humidityReceived.emit(humidity_value)
                            except ValueError:
                                print(f"ValueError on line: {line}")
    
        except Exception as e:
            self.errorOccurred.emit(f"read error: {str(e)}")
            print(f"Error: {str(e)}")
    
    def close_serial(self):
        if self.timer and self.timer.isActive():
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

        if self.serial and self.serial.is_open:
            self.serial.close()

        self.connectionStatus.emit("Disconnected")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Read Humidity")
        self.resize(300, 250)
        
        layout = QVBoxLayout()

        port_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(250)
        self.refresh_btn = QPushButton("Refresh")
        self.connect_btn = QPushButton("Connect")
        port_layout.addWidget(QLabel("Choose Port:"))
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(self.refresh_btn)
        port_layout.addWidget(self.connect_btn)
        layout.addLayout(port_layout)
        
        self.humidity_label = QLabel("wait data")
        self.humidity_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(self.humidity_label)
        
        self.status_label = QLabel("not connected")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)

        self.refresh_ports()
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.settings = QSettings("MyCompany", "SensorApp")
        last_port = self.settings.value("last_port", "")
        if last_port:
            index = self.port_combo.findData(last_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            
        self.is_connected = False

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_device()
        else:
            self.connect_device()
    
    def connect_device(self):
        port_name = self.port_combo.currentData()

        if not port_name:
            QMessageBox.warning(self, "Error", "Please select a valid port")
            return
        
        self.settings.setValue("last_port", port_name)
        
        self.serial_thread = QThread()
        self.serial_worker = SerialWorker(port_name)
        self.serial_worker.moveToThread(self.serial_thread)
        
        self.serial_worker.humidityReceived.connect(self.update_humidity)
        self.serial_worker.errorOccurred.connect(self.show_error)
        self.serial_worker.connectionStatus.connect(self.update_status)
        
        self.serial_thread.started.connect(self.serial_worker.connect_serial)
        
        self.serial_thread.finished.connect(self.serial_worker.deleteLater)
        self.serial_thread.finished.connect(self.serial_thread.deleteLater)
        
        self.serial_thread.start()
        self.is_connected = True
        self.connect_btn.setText("Disconnect")
        self.status_label.setText("Status: Connecting...")
    
    def disconnect_device(self):
        if hasattr(self, 'serial_thread') and self.serial_thread.isRunning():
            self.serial_worker.closeRequested.emit()
            
            self.serial_thread.quit()
            self.serial_thread.wait()
            
            self.is_connected = False
            self.connect_btn.setText("Connect")
            self.status_label.setText("Status: Disconnected")

    def update_humidity(self, value):
        self.humidity_label.setText(f"Humidity: {value:.2f}%")
    
    def show_error(self, message):
        self.status_label.setText(f"error: {message}")

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")
    
    def closeEvent(self, event):
        if hasattr(self, 'serial_thread') and self.serial_thread.isRunning():
            self.disconnect_device()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())