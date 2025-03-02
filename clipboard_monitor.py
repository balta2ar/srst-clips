import sys
import subprocess
import re
from collections import deque
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QListWidget, QPushButton, QLabel, QListWidgetItem, QSpinBox, QHBoxLayout,
                           QLineEdit)
from PyQt6.QtCore import QTimer, QObject, pyqtSlot
from PyQt6.QtGui import QClipboard, QFont, QKeySequence, QShortcut
from PyQt6.QtDBus import QDBusConnection, QDBusInterface

class ClipboardMonitor(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.clipboard = QApplication.clipboard()
        self.last_text = ""
        self.history_size = 10
        self.clipboard_history = deque(maxlen=self.history_size)
        self.target_window_id = None
        self.dbus_service_name = "org.srst.ClipboardMonitor"
        self.dbus_object_path = "/ClipboardMonitor"
        
        self.init_ui()
        self.setup_clipboard_monitoring()
        self.setup_dbus()
        self.setup_shortcuts()
        
        # Print command that can be used to activate the DBus function
        self.dbus_command = f"qdbus {self.dbus_service_name} {self.dbus_object_path} explain"
        print(f"To activate the explain function via DBus, use: {self.dbus_command}")
        
    def init_ui(self):
        self.setWindowTitle("Clipboard Monitor")
        self.setGeometry(300, 300, 600, 400)
        
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # History size control
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("History size:"))
        self.size_spinbox = QSpinBox()
        self.size_spinbox.setRange(1, 50)
        self.size_spinbox.setValue(self.history_size)
        self.size_spinbox.valueChanged.connect(self.update_history_size)
        size_layout.addWidget(self.size_spinbox)
        layout.addLayout(size_layout)
        
        # Clipboard history list
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        
        # Window finder button
        self.find_window_btn = QPushButton("Find window")
        self.find_window_btn.clicked.connect(self.find_window)
        layout.addWidget(self.find_window_btn)
        
        # Status label
        self.status_label = QLabel("No window selected")
        layout.addWidget(self.status_label)
        
        # DBus command line with label
        dbus_layout = QVBoxLayout()
        dbus_layout.addWidget(QLabel("DBus command (click to select all):"))
        self.dbus_command_line = QLineEdit()
        self.dbus_command_line.setReadOnly(True)
        dbus_layout.addWidget(self.dbus_command_line)
        layout.addLayout(dbus_layout)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
    def setup_clipboard_monitoring(self):
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_clipboard)
        self.timer.start(500)  # Check every 500ms
        
    def setup_dbus(self):
        if not QDBusConnection.sessionBus().isConnected():
            print("Could not connect to D-Bus session bus")
            return
            
        # Register service
        if not QDBusConnection.sessionBus().registerService(self.dbus_service_name):
            print(f"Could not register D-Bus service: {QDBusConnection.sessionBus().lastError().message()}")
            return
            
        # Register object and expose methods
        if not QDBusConnection.sessionBus().registerObject(self.dbus_object_path, self, 
                                                          QDBusConnection.RegisterOption.ExportAllSlots):
            print(f"Could not register object: {QDBusConnection.sessionBus().lastError().message()}")
            return
            
        print(f"DBus service registered: {self.dbus_service_name}, object: {self.dbus_object_path}")
        
        # Update the command line in the UI
        self.dbus_command = f"qdbus {self.dbus_service_name} {self.dbus_object_path} explain"
        self.dbus_command_line.setText(self.dbus_command)
    
    def setup_shortcuts(self):
        self.quit_shortcut1 = QShortcut(QKeySequence("Esc"), self)
        self.quit_shortcut1.activated.connect(self.close)
        
        self.quit_shortcut2 = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut2.activated.connect(self.close)
    
    def update_history_size(self, size):
        self.history_size = size
        # Create a new deque with updated max length and copy over existing items
        new_history = deque(maxlen=size)
        # Copy only the newest items that fit the new size
        items_to_copy = list(self.clipboard_history)[-size:] if len(self.clipboard_history) > size else self.clipboard_history
        for item in items_to_copy:
            new_history.append(item)
        self.clipboard_history = new_history
        # Update the UI list
        self.update_history_display()
    
    def find_window(self):
        self.status_label.setText("Please click on a window...")
        try:
            # Run xwininfo and get the output
            result = subprocess.run(['xwininfo'], capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout
                # Extract window ID from output
                match = re.search(r'Window id: (0x[0-9a-fA-F]+)', output)
                if match:
                    self.target_window_id = match.group(1)
                    self.status_label.setText(f"Selected window: {self.target_window_id}")
                    print(f"Window ID: {self.target_window_id}")
                else:
                    self.status_label.setText("Could not find window ID in xwininfo output")
            else:
                self.status_label.setText("xwininfo failed")
        except Exception as e:
            self.status_label.setText(f"Error finding window: {str(e)}")

    def check_clipboard(self):
        # This is a fallback in case the dataChanged signal doesn't fire correctly
        text = self.clipboard.text()
        if text != self.last_text and text.strip():
            self.process_clipboard_text(text)
            
    def on_clipboard_change(self):
        text = self.clipboard.text()
        if text.strip():  # Ignore empty clipboard
            self.process_clipboard_text(text)
    
    def process_clipboard_text(self, text):
        if text == self.last_text:
            return
            
        self.last_text = text
        
        # Add to history
        self.clipboard_history.append(text)
        
        # Update display
        self.update_history_display()
    
    def update_history_display(self):
        self.history_list.clear()
        
        # Process items in reverse order (newest first)
        for item in reversed(list(self.clipboard_history)):
            matches = self.find_matches(item)
            self.add_history_item(item, matches)
    
    def find_matches(self, text):
        """Find which previous clipboard items are contained in the given text."""
        matches = []
        # Skip the text itself and check only previous entries
        history_list = list(self.clipboard_history)
        if text in history_list:
            idx = history_list.index(text)
            for i, past_text in enumerate(history_list):
                if i != idx and past_text in text:
                    matches.append(past_text)
        return matches
    
    def add_history_item(self, text, matches):
        item = QListWidgetItem()
        
        if matches:
            # Create HTML with bold matches
            html_text = text
            for match in matches:
                html_text = html_text.replace(match, f"<b>{match}</b>")
            
            item.setText(f"{html_text} ({len(matches)})")
        else:
            item.setText(text)
        
        self.history_list.addItem(item)
    
    @pyqtSlot()
    def explain(self):
        """DBus method to explain the text with matches."""
        if not self.target_window_id:
            print("No target window selected")
            return "No target window selected"
            
        # Find the most recent text with multiple matches
        for item in reversed(list(self.clipboard_history)):
            matches = self.find_matches(item)
            if len(matches) > 1:
                self.send_to_ai_window(item)
                return f"Sent to AI: {item[:30]}..."
                
        return "No suitable text found"
    
    def send_to_ai_window(self, text):
        """Send text to the target window using xdotool."""
        if not self.target_window_id:
            return
            
        try:
            # Prepare the xdotool command
            cmd = [
                "xdotool", "windowactivate", self.target_window_id, 
                "&&", "xdotool", "key", "Escape", 
                "&&", "xdotool", "key", "g", "i", 
                "&&", "xdotool", "type", text,
                "&&", "xdotool", "key", "Return"
            ]
            
            # Execute the command
            subprocess.run(" ".join(cmd), shell=True)
            print(f"Sent text to window {self.target_window_id}")
        except Exception as e:
            print(f"Error sending text: {str(e)}")

def main():
    app = QApplication(sys.argv)
    monitor = ClipboardMonitor(app)
    monitor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
