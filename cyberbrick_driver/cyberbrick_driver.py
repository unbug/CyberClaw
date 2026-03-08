#!/usr/bin/env python3
import serial
import serial.tools.list_ports
import time
import sys
import argparse

import os

class CyberBrickDriver:
    """
    CyberBrick Universal Driver using direct hardware pin mapping for ESP32-C3 Remote.
    Compatible with CyberBrick Mini T and other standard CyberBrick devices.
    
    Hardware Mapping (Standard CyberBrick Layout):
    - Pin 2: Motor/Servo A (e.g. Left Track)
    - Pin 4, 5: Motor B (e.g. Right Track)
    - Pin 3: Servo C (e.g. Turret)
    - Pin 6, 7: Motor D (e.g. Cannon/Fire)
    """
    def __init__(self, port=None, baud=115200):
        self.port = port
        self.baud = baud
        self.serial = None

    def connect(self):
        # 1. Try manually provided port (via constructor/CLI)
        if self.port:
            pass # Already set
            
        # 2. Try environment variable
        if not self.port:
            self.port = os.environ.get("CYBERBRICK_PORT")
            if self.port:
                print(f"Using port from CYBERBRICK_PORT: {self.port}")

        # 3. Try cached port
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".port_cache")
        if not self.port and os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached_port = f.read().strip()
                if os.path.exists(cached_port):
                    self.port = cached_port
                    print(f"Using cached port: {self.port}")
            except:
                pass

        # 4. Try auto-detection
        if not self.port:
            print("Auto-detecting CyberBrick device...")
            ports = list(serial.tools.list_ports.comports())
            candidates = []
            for p in ports:
                # VID 0x303a / PID 0x1001 is common for ESP32-C3 / CyberBrick
                if p.vid == 0x303a and p.pid == 0x1001:
                    candidates.insert(0, p) # High priority
                elif "CyberBrick" in p.description or "usbmodem" in p.device or "USB Serial" in p.description or "CP210" in p.description:
                    candidates.append(p)
            
            if candidates:
                self.port = candidates[0].device
                print(f"Found candidate: {self.port} ({candidates[0].description})")
                # Save to cache
                try:
                    with open(cache_file, "w") as f:
                        f.write(self.port)
                except:
                    pass
        
        if not self.port:
            print("❌ Error: Could not detect CyberBrick device.")
            print("Please specify the port using:")
            print("  1. Command line argument: --port /dev/tty.xxx")
            print("  2. Environment variable: export CYBERBRICK_PORT=/dev/tty.xxx")
            print("\nAvailable ports:")
            found_ports = list(serial.tools.list_ports.comports())
            if not found_ports:
                print("  (No serial ports found)")
            else:
                for p in found_ports:
                    print(f"  - {p.device} ({p.description}) VID={hex(p.vid) if p.vid else 'N/A'} PID={hex(p.pid) if p.pid else 'N/A'}")
            return False
            
        print(f"Connecting to {self.port}...")
        try:
            self.serial = serial.Serial(self.port, self.baud, timeout=2)
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
        
        # Try soft handshake first (fastest)
        if self._handshake():
            print("✅ Connected via Soft Handshake.")
            return True
            
        # If soft handshake fails, try hard reset
        print("Soft handshake failed. Performing hard reset...")
        self.serial.dtr = False
        self.serial.rts = False
        time.sleep(0.1)
        self.serial.dtr = True
        self.serial.rts = True
        
        print("Waiting for device to boot...")
        time.sleep(2.0)
        
        if self._handshake():
            print("✅ Connected after Hard Reset.")
            return True
            
        return False

    def _handshake(self):
        """Attempts to break into REPL and verify connection."""
        print("Breaking into REPL...")
        # Send Ctrl-C multiple times
        for _ in range(5):
            self.serial.write(b'\x03')
            time.sleep(0.05)
        
        # Flush input
        self.serial.read(self.serial.in_waiting)
        
        # Send a newline to trigger prompt
        self.serial.write(b'\r\n')
        time.sleep(0.2)
        
        resp = self.serial.read(self.serial.in_waiting).decode(errors='replace')
        if ">>>" in resp or ">" in resp or "MicroPython" in resp:
            return True
        return False

    def send_repl_code(self, code, reset_at_end=False):
        """
        Send MicroPython code to the device via Raw REPL.
        """
        # 1. Enter Raw REPL (Ctrl-A)
        self.serial.write(b'\x01')
        time.sleep(0.5)
        self.serial.read(self.serial.in_waiting) # Flush junk
        
        # 2. Execute the command
        self.serial.write(code.encode('utf-8') + b'\x04')
        
        # 3. Read output and wait for finish
        resp = ""
        start_time = time.time()
        while time.time() - start_time < 5:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='replace')
                resp += chunk
                if ">" in chunk or "OK" in chunk:
                    break
            time.sleep(0.1)
        
        if resp:
            print(f"Device Output:\n{resp.strip()}")
        
        # 4. Optional: Exit Raw REPL and soft-reset (Ctrl-B)
        if reset_at_end:
            print("Soft-resetting remote (returning to manual control)...")
            self.serial.write(b'\x02')
            time.sleep(1) # Wait for reboot
        else:
            # We stay in Raw REPL to prevent main.py from restarting and causing "ghost" movements
            pass
            
        return resp

    def move_backward(self, speed, duration=2.0):
        """
        Moves the tank backward.
        Left: Duty 1023 (BACKWARD) - High Freq Test
        Right: Pin 5 High (BACKWARD) - High Freq Test (1000Hz)
        """
        speed = abs(speed)
        # Left: Duty 1023 is BACKWARD.
        p2_duty = int(speed * 10.23) 
        
        # Right: Pin 5 High is BACKWARD (1000Hz).
        # Pin 4 = 0, Pin 5 = Speed.
        dc_duty = int(speed * 10.23)
        p4_duty = 0
        p5_duty = dc_duty
        
        script = f"""
from machine import Pin, PWM
import time
p2 = PWM(Pin(2), freq=1000)
p4 = PWM(Pin(4), freq=1000)
p5 = PWM(Pin(5), freq=1000)
p2.duty({p2_duty})
p4.duty({p4_duty})
p5.duty({p5_duty})
time.sleep({duration})
p2.deinit()
p4.deinit()
p5.deinit()
"""
        self.send_repl_code(script)

    def move_forward(self, speed, duration=2.0):
        """
        Moves the tank forward.
        Left: Duty 0 (FORWARD)
        Right: Pin 4 High (FORWARD) - High Freq Test (1000Hz)
        """
        speed = abs(speed)
        # Left: Duty 0 is FORWARD.
        p2_duty = 0
        
        # Right: Pin 4 High is FORWARD.
        # Pin 4 = Speed, Pin 5 = 0.
        dc_duty = int(speed * 10.23)
        p4_duty = dc_duty
        p5_duty = 0
        
        script = f"""
from machine import Pin, PWM
import time
p2 = PWM(Pin(2), freq=1000)
p4 = PWM(Pin(4), freq=1000)
p5 = PWM(Pin(5), freq=1000)
p2.duty({p2_duty})
p4.duty({p4_duty})
p5.duty({p5_duty})
time.sleep({duration})
p2.deinit()
p4.deinit()
p5.deinit()
"""
        self.send_repl_code(script)

    def turn_left(self, speed, duration=2.0):
        """
        Turns the tank left (Pivot Turn).
        Left Stop (Deinit), Right Forward (Pin 4 High).
        """
        speed = abs(speed)
        dc_duty = int(speed * 10.23)
        p4_duty = dc_duty
        p5_duty = 0
        
        script = f"""
from machine import Pin, PWM
import time
# Only drive Right Track
p4 = PWM(Pin(4), freq=1000)
p5 = PWM(Pin(5), freq=1000)
p4.duty({p4_duty})
p5.duty({p5_duty})
# Ensure Left Track (Pin 2) is OFF
try:
    p2 = PWM(Pin(2), freq=1000)
    p2.deinit()
except:
    pass
time.sleep({duration})
p4.deinit()
p5.deinit()
"""
        self.send_repl_code(script)

    def turn_right(self, speed, duration=2.0):
        """
        Turns the tank right (Pivot Turn).
        Left Forward (Duty 0), Right Stop.
        """
        speed = abs(speed)
        p2_duty = 0
        
        script = f"""
from machine import Pin, PWM
import time
# Only drive Left Track
p2 = PWM(Pin(2), freq=1000)
p2.duty({p2_duty})
# Ensure Right Track (Pin 4/5) is OFF
try:
    p4 = PWM(Pin(4), freq=1000)
    p5 = PWM(Pin(5), freq=1000)
    p4.deinit()
    p5.deinit()
except:
    pass
time.sleep({duration})
p2.deinit()
"""
        self.send_repl_code(script)

    def turret(self, elevation):
        """
        Adjusts turret elevation (Pin 3). Elevation 0-180, 90 is neutral.
        """
        duty = int(elevation * 102 / 180 + 25)
        script = f"""
from machine import Pin, PWM
import time
p3 = PWM(Pin(3), freq=50)
p3.duty({duty})
time.sleep(0.5)
p3.deinit()
"""
        self.send_repl_code(script)

    def fire(self):
        """
        Fires the cannon (Pin 6/7).
        """
        script = """
from machine import Pin, PWM
import time
p6 = PWM(Pin(6), freq=1000)
p7 = PWM(Pin(7), freq=1000)
p6.duty(1023)
p7.duty(0)
time.sleep(0.5)
p6.deinit()
p7.deinit()
"""
        self.send_repl_code(script)

    def stop(self):
        """Stops all motors."""
        script = """
from machine import Pin, PWM
try:
    p2 = PWM(Pin(2))
    p2.deinit()
except: pass
try:
    p3 = PWM(Pin(3))
    p3.deinit()
except: pass
try:
    p4 = PWM(Pin(4))
    p4.deinit()
except: pass
try:
    p5 = PWM(Pin(5))
    p5.deinit()
except: pass
try:
    p6 = PWM(Pin(6))
    p6.deinit()
except: pass
try:
    p7 = PWM(Pin(7))
    p7.deinit()
except: pass
"""
        self.send_repl_code(script)

def main():
    parser = argparse.ArgumentParser(description="CyberBrick Driver CLI")
    parser.add_argument("--port", help="Serial port (e.g. /dev/tty.usbmodem14101)")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Forward
    p_fwd = subparsers.add_parser("forward", help="Move forward")
    p_fwd.add_argument("speed", type=int, help="Speed (0-100)")
    p_fwd.add_argument("duration", type=float, default=2.0, nargs='?', help="Duration (s)")
    
    # Backward
    p_bwd = subparsers.add_parser("backward", help="Move backward")
    p_bwd.add_argument("speed", type=int, help="Speed (0-100)")
    p_bwd.add_argument("duration", type=float, default=2.0, nargs='?', help="Duration (s)")
    
    # Left
    p_left = subparsers.add_parser("left", help="Turn left")
    p_left.add_argument("speed", type=int, help="Speed (0-100)")
    p_left.add_argument("duration", type=float, default=2.0, nargs='?', help="Duration (s)")
    
    # Right
    p_right = subparsers.add_parser("right", help="Turn right")
    p_right.add_argument("speed", type=int, help="Speed (0-100)")
    p_right.add_argument("duration", type=float, default=2.0, nargs='?', help="Duration (s)")
    
    # Turret
    p_turret = subparsers.add_parser("turret", help="Move turret")
    p_turret.add_argument("angle", type=int, help="Angle (0-180)")
    
    # Fire
    subparsers.add_parser("fire", help="Fire cannon")
    
    # Stop
    subparsers.add_parser("stop", help="Stop all motors")
    
    # Raw
    p_raw = subparsers.add_parser("raw", help="Execute raw MicroPython code")
    p_raw.add_argument("code", help="MicroPython code string")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    driver = CyberBrickDriver(port=args.port)
    if not driver.connect():
        sys.exit(1)

    if args.command == "forward":
        driver.move_forward(args.speed, args.duration)
    elif args.command == "backward":
        driver.move_backward(args.speed, args.duration)
    elif args.command == "left":
        driver.turn_left(args.speed, args.duration)
    elif args.command == "right":
        driver.turn_right(args.speed, args.duration)
    elif args.command == "turret":
        driver.turret(args.angle)
    elif args.command == "fire":
        driver.fire()
    elif args.command == "stop":
        driver.stop()
    elif args.command == "raw":
        driver.send_repl_code(args.code)

if __name__ == "__main__":
    main()
