#!/usr/bin/env python3
import sys
import subprocess
import time
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtDBus import QDBusConnection, QDBusInterface

def is_service_running(bus, service_name):
    """Check if a DBus service is currently running"""
    return service_name in bus.interface().registeredServiceNames().value()

def main():
    app = QCoreApplication(sys.argv)
    
    service_name = "org.srst.ClipboardMonitor"
    object_path = "/ClipboardMonitor"
    
    # Create DBus connection
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Cannot connect to D-Bus session bus")
        return 1
    
    # Check if the clipboard monitor service is running
    if not is_service_running(bus, service_name):
        print("Clipboard monitor service not running, launching application...")
        
        try:
            # Start the clipboard monitor application
            subprocess.Popen(["srst-clips"], start_new_session=True)
            
            # Wait for the service to become available (with timeout)
            max_wait = 5  # Maximum wait time in seconds
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                if is_service_running(bus, service_name):
                    print("Service started successfully")
                    # Give it a moment to fully initialize
                    time.sleep(0.5)
                    break
                time.sleep(0.1)
            else:
                print("Timed out waiting for service to start")
                return 1
        except Exception as e:
            print(f"Error starting clipboard monitor: {e}")
            return 1
    
    # Create interface to the service
    interface = QDBusInterface(
        service_name,
        object_path,
        "",
        bus
    )
    
    if not interface.isValid():
        print(f"Failed to create D-Bus interface: {bus.lastError().message()}")
        return 1
    
    time.sleep(1.0)
    print("Calling explain method...")
    reply = interface.call("explain")
    result = reply.arguments()[0] if reply.arguments() else 'No response'
    print(f"Response: {result}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
