import json
import os
import re
import shlex
import subprocess
import sys
from collections import deque

from PyQt6.QtCore import QObject, QPoint, QSettings, QSize, Qt, QTimer, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface
from PyQt6.QtGui import QClipboard, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


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
        self.window_config_file = "/tmp/srst_clips_window_config.json"

        # Allow the window to be as small as possible
        self.setMinimumWidth(1)
        self.setMinimumHeight(1)

        self.init_ui()
        self.restore_window_geometry()
        self.setup_clipboard_monitoring()
        self.setup_dbus()
        self.setup_shortcuts()

        self.dbus_command = f"qdbus {self.dbus_service_name} {self.dbus_object_path} explain"
        print(f"To activate the explain function via DBus, use: {self.dbus_command}")

    def init_ui(self):
        self.setWindowTitle("Clipboard Monitor")
        self.setGeometry(100, 100, 200, 200)

        main_widget = QWidget()
        layout = QVBoxLayout()

        # Set small margins to save space
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(1)

        size_layout = QHBoxLayout()
        size_layout.setSpacing(1)
        size_label = QLabel("Size:")
        size_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        size_layout.addWidget(size_label)

        self.size_spinbox = QSpinBox()
        self.size_spinbox.setRange(1, 50)
        self.size_spinbox.setValue(self.history_size)
        self.size_spinbox.valueChanged.connect(self.update_history_size)
        self.size_spinbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        size_layout.addWidget(self.size_spinbox)
        layout.addLayout(size_layout)

        self.history_list = QListWidget()
        self.history_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.history_list)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(1)

        self.find_window_btn = QPushButton("Find window")
        self.find_window_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.find_window_btn.clicked.connect(self.find_window)
        button_layout.addWidget(self.find_window_btn)

        self.explain_btn = QPushButton("Explain")
        self.explain_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.explain_btn.clicked.connect(self.explain_button_clicked)
        button_layout.addWidget(self.explain_btn)

        layout.addLayout(button_layout)

        self.status_label = QLabel("No window selected")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        dbus_layout = QVBoxLayout()
        dbus_layout.setSpacing(1)
        dbus_label = QLabel("DBus cmd:")
        dbus_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        dbus_layout.addWidget(dbus_label)

        self.dbus_command_line = QLineEdit()
        self.dbus_command_line.setReadOnly(True)
        self.dbus_command_line.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        dbus_layout.addWidget(self.dbus_command_line)
        layout.addLayout(dbus_layout)

        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    def restore_window_geometry(self):
        try:
            if os.path.exists(self.window_config_file):
                with open(self.window_config_file, 'r') as f:
                    config = json.load(f)

                    if 'pos_x' in config and 'pos_y' in config:
                        self.move(config['pos_x'], config['pos_y'])

                    if 'width' in config and 'height' in config:
                        self.resize(config['width'], config['height'])

                    if 'target_window_id' in config and config['target_window_id']:
                        self.target_window_id = config['target_window_id']
                        self.status_label.setText(f"Selected window: {self.target_window_id}")

                print(f"Configuration restored from {self.window_config_file}")
        except Exception as e:
            print(f"Error restoring configuration: {e}")

    def save_window_geometry(self):
        try:
            config = {
                'pos_x': self.pos().x(),
                'pos_y': self.pos().y(),
                'width': self.width(),
                'height': self.height(),
                'target_window_id': self.target_window_id
            }

            with open(self.window_config_file, 'w') as f:
                json.dump(config, f)

            print(f"Configuration saved to {self.window_config_file}")
        except Exception as e:
            print(f"Error saving configuration: {e}")

    def moveEvent(self, event):
        super().moveEvent(event)
        self.save_window_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.save_window_geometry()

    def closeEvent(self, event):
        self.save_window_geometry()
        super().closeEvent(event)

    def setup_clipboard_monitoring(self):
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_clipboard)
        self.timer.start(500)

    def setup_dbus(self):
        if not QDBusConnection.sessionBus().isConnected():
            print("Could not connect to D-Bus session bus")
            return

        if not QDBusConnection.sessionBus().registerService(self.dbus_service_name):
            print(f"Could not register D-Bus service: {QDBusConnection.sessionBus().lastError().message()}")
            return

        if not QDBusConnection.sessionBus().registerObject(self.dbus_object_path, self,
                                                          QDBusConnection.RegisterOption.ExportAllSlots):
            print(f"Could not register object: {QDBusConnection.sessionBus().lastError().message()}")
            return

        print(f"DBus service registered: {self.dbus_service_name}, object: {self.dbus_object_path}")

        self.dbus_command = f"qdbus {self.dbus_service_name} {self.dbus_object_path} explain"
        self.dbus_command_line.setText(self.dbus_command)

    def setup_shortcuts(self):
        self.quit_shortcut1 = QShortcut(QKeySequence("Esc"), self)
        self.quit_shortcut1.activated.connect(self.close)

        self.quit_shortcut2 = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut2.activated.connect(self.close)

    def update_history_size(self, size):
        self.history_size = size
        new_history = deque(maxlen=size)
        items_to_copy = list(self.clipboard_history)[-size:] if len(self.clipboard_history) > size else self.clipboard_history
        for item in items_to_copy:
            new_history.append(item)
        self.clipboard_history = new_history
        self.update_history_display()

    def find_window(self):
        self.status_label.setText("Please click on a window...")
        try:
            result = subprocess.run(['xwininfo'], capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout
                match = re.search(r'Window id: (0x[0-9a-fA-F]+)', output)
                if match:
                    self.target_window_id = match.group(1)
                    self.status_label.setText(f"Selected window: {self.target_window_id}")
                    print(f"Window ID: {self.target_window_id}")
                    self.save_window_geometry()
                else:
                    self.status_label.setText("Could not find window ID in xwininfo output")
            else:
                self.status_label.setText("xwininfo failed")
        except Exception as e:
            self.status_label.setText(f"Error finding window: {str(e)}")

    def check_clipboard(self):
        text = self.clipboard.text()
        if text != self.last_text and text.strip():
            self.process_clipboard_text(text)

    def on_clipboard_change(self):
        text = self.clipboard.text()
        if text.strip():
            self.process_clipboard_text(text)

    def process_clipboard_text(self, text):
        if text == self.last_text:
            return

        self.last_text = text
        self.clipboard_history.append(text)

        matches = self.find_matches(text)
        if matches and len(matches) > 0:
            match_count = len(matches)
            self.show_notification(f"{match_count} matches found", text[:100] + ("..." if len(text) > 100 else ""))

        self.update_history_display()

    def show_notification(self, title, message):
        try:
            subprocess.run(["notify-send", title, message], check=False)
        except Exception as e:
            print(f"Error showing notification: {e}")

    def update_history_display(self):
        self.history_list.clear()

        for item in reversed(list(self.clipboard_history)):
            matches = self.find_matches(item)
            self.add_history_item(item, matches)

    def find_matches(self, text):
        matches = []
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
            html_text = text
            for match in matches:
                html_text = html_text.replace(match, f"<b>{match}</b>")

            item.setText(f"({len(matches)}) {html_text}")
        else:
            item.setText(text)

        self.history_list.addItem(item)

    def explain_button_clicked(self):
        result = self.explain()
        self.status_label.setText(result)

    @pyqtSlot()
    def explain(self):
        if not self.target_window_id:
            print("No target window selected")
            return "No target window selected"

        for item in reversed(list(self.clipboard_history)):
            matches = self.find_matches(item)
            if len(matches) > 0:
                formatted_text = self.format_text_for_ai(item, matches)
                self.send_to_ai_window(formatted_text)
                self.clipboard_history.clear()
                self.update_history_display()
                return f"Sent to AI: {item[:30]}..."

        return "No suitable text found"

    def format_text_for_ai(self, text, matches):
        sorted_matches = sorted(matches, key=len, reverse=True)
        formatted_text = text
        for match in sorted_matches:
            formatted_text = formatted_text.replace(match, f"*{match}*")

        return formatted_text

    def send_to_ai_window(self, text):
        if not self.target_window_id:
            return

        print(f"Sending text: {text}")
        try:
            original_clipboard = self.clipboard.text()
            self.clipboard.setText(text)

            cmd_parts = [
                f"xdotool windowactivate {self.target_window_id}",
                "xdotool key Escape",
                "sleep 0.2",
                "xdotool key g i",
                "sleep 0.2",
                "xdotool key ctrl+v",
                "sleep 0.2",
                "xdotool key Return"
            ]

            full_cmd = ' && '.join(cmd_parts)
            subprocess.run(full_cmd, shell=True)
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
