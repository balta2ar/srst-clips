#!/usr/bin/env python3
import sys
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtDBus import QDBusConnection, QDBusInterface

def main():
    app = QCoreApplication(sys.argv)
    
    # Create DBus interface
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Cannot connect to D-Bus session bus")
        return 1
    
    interface = QDBusInterface(
        "org.srst.ClipboardMonitor",
        "/ClipboardMonitor",
        "",
        bus
    )
    
    if not interface.isValid():
        print(f"Failed to create D-Bus interface: {bus.lastError().message()}")
        return 1
    
    # Call the explain method
    reply = interface.call("explain")
    print(f"Response: {reply.arguments()[0] if reply.arguments() else 'No response'}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
