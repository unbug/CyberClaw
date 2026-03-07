#!/usr/bin/env python3
import serial
import serial.tools.list_ports
import time
import sys
import argparse

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
        if not self.port:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                if "CyberBrick" in p.description or "usbmodem" in p.device:
                    self.port = p.device
                    break
        
        if not self.port:
            self.port = "/dev/cu.usbmodem14101"
            
        print(f"Connecting to {self.port} and resetting...")
        self.serial = serial.Serial(self.port, self.baud, timeout=2)
        
        # Hardware reset via DTR/RTS
        self.serial.dtr = False
        self.serial.rts = False
        time.sleep(0.1)
        self.serial.dtr = True
        self.serial.rts = True
        
        print("Waiting for device to boot...")
        time.sleep(2)
        
        # Break into REPL
        print("Breaking into REPL...")
        for _ in range(10):
            self.serial.write(b'\x03')
            time.sleep(0.1)
        
        self.serial.write(b'\r\n')
        time.sleep(0.5)
        
        resp = self.serial.read(self.serial.in_waiting).decode(errors='replace')
        if ">>>" in resp or ">" in resp or "MicroPython" in resp:
            print("REPL Ready.")
            return True
        else:
            print(f"Failed to get REPL. Output: {repr(resp)}")
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
        Fires the cannon using Pin 6/7.
        Uses 1000Hz PWM for DC motor.
        """
        script = """
from machine import Pin, PWM
import time
p6 = PWM(Pin(6), freq=1000)
p7 = PWM(Pin(7), freq=1000)
# Forward stroke
p6.duty(1023)
p7.duty(0)
time.sleep(0.5)
# Reverse stroke
p6.duty(0)
p7.duty(1023)
time.sleep(0.5)
# Stop
p6.deinit()
p7.deinit()
"""
        self.send_repl_code(script)

    def stop(self):
        """
        Force stop all known pins and return to manual control.
        """
        script = """
from machine import Pin, PWM
for i in [0, 1, 2, 3, 4, 5, 6, 7]:
    try:
        p = PWM(Pin(i), freq=50)
        p.deinit()
    except:
        pass
"""
        self.send_repl_code(script, reset_at_end=True)

    def dance(self):
        """
        Performs a lively dance sequence with larger amplitudes.
        """
        print("Dancing (Lively Version)...")
        
        # 1. Big Spin Intro (360-ish)
        print(">> Intro Spin")
        self.turn_left(100, 1.5)
        self.turret(130)
        self.turn_right(100, 1.5)
        self.turret(50)
        
        # 2. Big Steps (Forward/Back)
        print(">> Big Steps")
        self.move_forward(100, 0.8)
        self.move_backward(100, 0.8)
        self.move_forward(100, 0.8)
        self.move_backward(100, 0.8)
        
        # 3. Excited Wiggle (Fast but wider than before)
        print(">> Wiggle")
        for _ in range(3):
            self.turn_left(100, 0.6)
            self.turn_right(100, 0.6)
            
        # 4. Head Banging
        print(">> Head Bang")
        self.turret(130)
        time.sleep(0.3)
        self.turret(50)
        time.sleep(0.3)
        self.turret(130)
        time.sleep(0.3)
        self.turret(50)
        
        # 5. Finale
        print(">> Finale")
        self.fire()
        self.turn_left(100, 2.0) # 360 spin
        
        self.stop()
        print("Dance complete.")

    def reset_remote(self):
        """
        Soft-resets the remote controller to return to manual mode.
        """
        self.send_repl_code("print('Resetting...')", reset_at_end=True)

    def run_test_sequence(self):
        """
        Runs a full test sequence of all functions.
        """
        print("\n=== STARTING FULL CYBERBRICK TEST SEQUENCE ===")
        
        # 1. Forward
        print("\n1. Forward (80% speed, 2s)")
        self.move_forward(80, 2.0)
        time.sleep(1.0)
        
        # 2. Backward
        print("\n2. Backward (80% speed, 2s)")
        self.move_backward(80, 2.0)
        time.sleep(1.0)
        
        # 3. Turn Left
        print("\n3. Turn Left (50% speed, 2s)")
        self.turn_left(50, 2.0)
        time.sleep(1.0)
        
        # 4. Turn Right
        print("\n4. Turn Right (50% speed, 2s)")
        self.turn_right(50, 2.0)
        time.sleep(1.0)
        
        # 5. Turret Up
        print("\n5. Turret Up (Elevation 130)")
        self.turret(130)
        time.sleep(1.0)
        
        # 6. Turret Down
        print("\n6. Turret Down (Elevation 50)")
        self.turret(50)
        time.sleep(1.0)
        
        # 7. Fire
        print("\n7. Fire (Action: Push-Pull)")
        self.fire()
        time.sleep(1.0)
        
        # 8. Reset to Manual
        print("\n8. Finalizing: Stop and Reset to Manual Mode")
        self.stop()
        self.reset_remote()
        
        print("\n=== FULL TEST COMPLETED SUCCESSFULLY ===")

    def close(self):
        if self.serial:
            self.serial.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["forward", "backward", "left", "right", "turret", "fire", "stop", "reset", "test", "dance"])
    parser.add_argument("value", type=int, nargs='?', default=0)
    parser.add_argument("duration", type=float, nargs='?', default=None)
    parser.add_argument("--port", help="Serial port path")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    driver = CyberBrickDriver(port=args.port, baud=args.baud)
    try:
        if driver.connect():
            if args.command == "forward":
                dur = args.duration if args.duration is not None else 2.0
                driver.move_forward(args.value, dur)
            elif args.command == "backward":
                dur = args.duration if args.duration is not None else 2.0
                driver.move_backward(args.value, dur)
            elif args.command == "left":
                dur = args.duration if args.duration is not None else 2.0
                driver.turn_left(args.value, dur)
            elif args.command == "right":
                dur = args.duration if args.duration is not None else 2.0
                driver.turn_right(args.value, dur)
            elif args.command == "turret":
                driver.turret(args.value)
            elif args.command == "fire":
                driver.fire()
            elif args.command == "stop":
                driver.stop()
            elif args.command == "reset":
                driver.reset_remote()
            elif args.command == "test":
                driver.run_test_sequence()
            elif args.command == "dance":
                driver.dance()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.close()
