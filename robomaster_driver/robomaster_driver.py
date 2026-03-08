#!/usr/bin/env python3
import socket
import sys
import argparse
import time
import os

class RoboMasterDriver:
    def __init__(self, host="192.168.1.116", port=40923, mock=False):
        self.host = host
        self.port = port
        self.mock = mock
        self.socket = None

    def connect(self):
        """Establish connection to RoboMaster EP."""
        if self.mock:
            print(f"[MOCK] Connecting to {self.host}:{self.port}...")
            print("[MOCK] Connected!")
            return True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10) # 10 seconds timeout
            print(f"Connecting to {self.host}:{self.port}...")
            self.socket.connect((self.host, self.port))
            print("Connected!")
            
            # Enter SDK mode
            if not self.send_command("command"):
                print("Failed to enter SDK mode.")
                return False
            
            # Enable IR distance sensor measurement
            # "ir_distance_sensor measure on"
            # Note: For EP, it seems we might need to enable specific ports if attached?
            # But the command "ir_distance_sensor measure on" is global.
            self.send_command("ir_distance_sensor measure on")
            # Also try to enable specific sensor just in case if using extension module protocol?
            # But "ir_distance_sensor measure on" is the standard text sdk command.
            
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Exit SDK mode and close connection."""
        if self.mock:
            print("[MOCK] Disconnected.")
            return

        if self.socket:
            try:
                # Try to exit SDK mode gracefully
                self.send_command("quit")
            except:
                pass
            self.socket.close()
            self.socket = None
            print("Disconnected.")

    def send_command(self, cmd):
        """Send a text command and return the response."""
        if self.mock:
            print(f"[MOCK] Sending: {cmd.strip()}")
            if "battery" in cmd:
                return "85"
            return "ok"

        if not self.socket:
            print("Not connected.")
            return None

        # Add terminator if missing
        if not cmd.endswith(';'):
            cmd += ';'

        try:
            print(f"Sending: {cmd.strip()}")
            self.socket.send(cmd.encode('utf-8'))
            
            # Receive response
            # Increase timeout slightly or handle buffer?
            # RoboMaster might send multiple responses if we send commands too fast?
            # Or if we have async notifications enabled?
            buf = self.socket.recv(1024)
            resp = buf.decode('utf-8').strip()
            print(f"Response: {resp}")
            return resp
        except socket.timeout:
            print("Error sending command: timed out")
            return None
        except socket.error as e:
            print(f"Error sending command: {e}")
            return None

    # --- High Level Skills ---

    def set_mode(self, mode="chassis_lead"):
        """
        Set robot motion mode.
        mode: 
            'chassis_lead' (Gimbal follows Chassis? No, wait. 
                            SDK: chassis_lead -> Gimbal follows Chassis YAW.
                            SDK: gimbal_lead -> Chassis follows Gimbal YAW.
                            SDK: free -> Independent.)
        Docs say:
        - chassis_lead: Gimbal yaw follows chassis yaw.
        - gimbal_lead: Chassis yaw follows gimbal yaw.
        - free: Independent.
        """
        # robot mode <mode>
        # Note: The user requested "chassis follows gimbal", which is likely 'gimbal_lead' in SDK terms?
        # Let's check docs snippet from earlier.
        # "chassis_lead; : 将机器人的运动模式设置为“云台跟随底盘模式”" -> Gimbal follows Chassis.
        # "底盘跟随云台模式" -> Chassis follows Gimbal. This is likely 'gimbal_lead'.
        # Wait, let's verify if 'gimbal_lead' is the keyword.
        # Docs usually match enum. Let's assume 'gimbal_lead'.
        cmd = f"robot mode {mode}"
        return self.send_command(cmd)

    def move(self, x=0.0, y=0.0, z=0.0, speed_xy=0.5, speed_z=30):
        """
        Move chassis relative to current position.
        x: forward/backward (m)
        y: left/right (m)
        z: rotation (degree)
        """
        # chassis move x <dist_x> y <dist_y> z <degree_z> vxy <speed_xy> vz <speed_z>
        cmd = f"chassis move x {x} y {y} z {z} vxy {speed_xy} vz {speed_z}"
        return self.send_command(cmd)

    def speed(self, x=0.0, y=0.0, z=0.0):
        """
        Set chassis speed.
        x: forward/backward speed (m/s)
        y: left/right speed (m/s)
        z: rotation speed (degree/s)
        """
        cmd = f"chassis speed x {x} y {y} z {z}"
        return self.send_command(cmd)

    def gimbal(self, pitch=0, yaw=0, speed_p=20, speed_y=20):
        """
        Move gimbal relative to current position.
        pitch: up/down (degree)
        yaw: left/right (degree)
        """
        # gimbal move p <pitch> y <yaw> vp <speed_p> vy <speed_y>
        cmd = f"gimbal move p {pitch} y {yaw} vp {speed_p} vy {speed_y}"
        return self.send_command(cmd)

    def gimbal_to(self, pitch=0, yaw=0, speed_p=20, speed_y=20):
        """
        Move gimbal to absolute position.
        pitch: up/down (degree)
        yaw: left/right (degree)
        """
        # gimbal moveto p <pitch> y <yaw> vp <speed_p> vy <speed_y>
        cmd = f"gimbal moveto p {pitch} y {yaw} vp {speed_p} vy {speed_y}"
        return self.send_command(cmd)

    def fire(self, type="ir", count=1):
        """
        Fire blaster.
        type: 'ir' (infrared/laser) or 'bead' (water gel)
        If type is 'ir', fires repeatedly for 'count' seconds (approximate).
        If type is 'bead', fires 'count' number of shots.
        """
        if type == "ir":
            # For IR, treat 'count' as duration in seconds.
            # We fire as fast as we can for that duration.
            start_time = time.time()
            duration = float(count)
            shots = 0
            print(f"Firing IR laser for {duration} seconds...")
            while time.time() - start_time < duration:
                # blaster fire type ir cnt 1
                # Use 'fire_type' instead of 'type' which is more likely consistent with Python SDK
                self.send_command("blaster fire fire_type ir cnt 1")
                shots += 1
                time.sleep(0.1) # Prevent flooding
            return f"Fired IR approx {shots} times"
        else:
            # For bead, treat 'count' as number of shots
            # Explicitly force type in command string
            cmd = f"blaster fire fire_type {type} cnt {count}"
            return self.send_command(cmd)

    def led(self, r=255, g=255, b=255, effect="on"):
        """
        Set LED effect.
        effect: on, off, flash, breath, scrolling
        """
        # led control comp all r <r> g <g> b <b> effect <effect>
        cmd = f"led control comp all r {r} g {g} b {b} effect {effect}"
        return self.send_command(cmd)

    def status(self):
        """Get battery level."""
        return self.send_command("robot battery ?")

    # --- Sensor Skills ---

    def get_chassis_position(self):
        """Get chassis position (x, y, z)."""
        # chassis position ?
        # Returns: <x> <y> <z>
        return self.send_command("chassis position ?")

    def get_chassis_speed(self):
        """Get chassis speed."""
        # chassis speed ?
        # Returns: <x> <y> <z> <w1> <w2> <w3> <w4>
        return self.send_command("chassis speed ?")

    def get_chassis_attitude(self):
        """Get chassis attitude (pitch, roll, yaw)."""
        # chassis attitude ?
        # Returns: <pitch> <roll> <yaw>
        return self.send_command("chassis attitude ?")

    def get_gimbal_attitude(self):
        """Get gimbal attitude (pitch, yaw)."""
        # gimbal attitude ?
        # Returns: <pitch> <yaw>
        return self.send_command("gimbal attitude ?")

    def get_ir_distance(self, id=1):
        """Get IR distance sensor value (cm). ID: 1-4"""
        # ir_distance_sensor distance <id> ?
        # Returns: <distance>
        return self.send_command(f"ir_distance_sensor distance {id} ?")

    def observe(self):
        """Aggregate all sensor data into a dictionary."""
        data = {}
        
        # Battery
        bat = self.status()
        data['battery'] = bat.strip() if bat else "unknown"

        # Position
        pos = self.get_chassis_position()
        if pos:
            parts = pos.split()
            if len(parts) >= 3:
                data['position'] = {'x': parts[0], 'y': parts[1], 'z': parts[2]}

        # Attitude
        att = self.get_chassis_attitude()
        if att:
            parts = att.split()
            if len(parts) >= 3:
                data['attitude'] = {'pitch': parts[0], 'roll': parts[1], 'yaw': parts[2]}

        # IR Distance (Try 4 sensors)
        ir_data = {}
        for i in range(1, 5):
            dist = self.get_ir_distance(i)
            if dist and "error" not in dist.lower():
                ir_data[f'ir_{i}'] = dist.strip()
        data['ir_distance'] = ir_data

        import json
        return json.dumps(data, indent=2)

def main():
    parser = argparse.ArgumentParser(description="RoboMaster EP Driver")
    parser.add_argument("--host", default="192.168.1.116", help="Robot IP address")
    parser.add_argument("--port", type=int, default=40923, help="Robot SDK port")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no hardware connection)")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Move command
    mv_parser = subparsers.add_parser("move", help="Move chassis")
    mv_parser.add_argument("x", type=float, help="X distance (m)")
    mv_parser.add_argument("y", type=float, default=0.0, nargs='?', help="Y distance (m)")
    mv_parser.add_argument("z", type=float, default=0.0, nargs='?', help="Z rotation (deg)")

    # Gimbal command
    gim_parser = subparsers.add_parser("gimbal", help="Move gimbal")
    gim_parser.add_argument("p", type=float, help="Pitch (deg)")
    gim_parser.add_argument("y", type=float, default=0.0, nargs='?', help="Yaw (deg)")

    # Fire command
    fire_parser = subparsers.add_parser("fire", help="Fire blaster")
    fire_parser.add_argument("type", default="ir", nargs='?', choices=['ir', 'bead'], help="Fire type: ir (laser) or bead (water gel)")
    fire_parser.add_argument("count", type=float, default=1.0, nargs='?', help="For IR: duration in seconds. For Bead: number of shots.")

    # Status command
    subparsers.add_parser("status", help="Get status (battery)")

    # Sensor command
    sensor_parser = subparsers.add_parser("sensor", help="Query sensors")
    sensor_parser.add_argument("--all", action="store_true", help="Get all sensor data (JSON)")
    sensor_parser.add_argument("--pos", action="store_true", help="Get chassis position")
    sensor_parser.add_argument("--speed", action="store_true", help="Get chassis speed")
    sensor_parser.add_argument("--att", action="store_true", help="Get chassis attitude")
    sensor_parser.add_argument("--dist", type=int, help="Get IR distance (ID 1-4)")

    # Raw command
    raw_parser = subparsers.add_parser("raw", help="Send raw SDK command")
    raw_parser.add_argument("cmd", nargs='+', help="Command string")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    driver = RoboMasterDriver(host=args.host, port=args.port, mock=args.mock)
    if not driver.connect():
        sys.exit(1)

    try:
        if args.command == "move":
            driver.move(args.x, args.y, args.z)
        elif args.command == "gimbal":
            driver.gimbal(args.p, args.y)
        elif args.command == "fire":
            driver.fire(args.type, args.count)
        elif args.command == "status":
            driver.status()
        elif args.command == "sensor":
            if args.all:
                print(driver.observe())
            elif args.pos:
                driver.get_chassis_position()
            elif args.speed:
                driver.get_chassis_speed()
            elif args.att:
                driver.get_chassis_attitude()
            elif args.dist:
                driver.get_ir_distance(args.dist)
            else:
                print(driver.observe()) # Default to all
        elif args.command == "raw":
            cmd_str = " ".join(args.cmd)
            driver.send_command(cmd_str)
            
    finally:
        driver.disconnect()

if __name__ == "__main__":
    main()
