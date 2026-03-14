#!/usr/bin/env python3
import sys
import os
import time
import argparse
import threading

# Add SDK path to sys.path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../vendor'))
if sdk_path not in sys.path:
    sys.path.append(sdk_path)

import robomaster
from robomaster import robot

class RoboMasterDriver:
    def __init__(self, conn_type="sta", sn=None):
        self.conn_type = conn_type
        self.sn = sn
        self.robot = None
        self.chassis = None
        self.gimbal = None
        self.sensor = None
        self.blaster = None
        self.led = None
        self.connected = False

        self._connect_lock = threading.Lock()
        
        # Sensor Data Cache
        self.dist_lock = threading.Lock()
        self.ir_distances = {} # {id: distance}

    def connect(self, retries=8, retry_delay_s=2.0):
        """Establish connection to RoboMaster EP using SDK."""
        with self._connect_lock:
            if self.connected and self.robot:
                return True

            last_err = None
            for i in range(max(1, int(retries))):
                print(f"Connecting to RoboMaster via {self.conn_type}... ({i+1}/{retries})")
                try:
                    self._reset_robot_instance()
                    self.robot.initialize(conn_type=self.conn_type, sn=self.sn)
                    self.chassis = self.robot.chassis
                    self.gimbal = self.robot.gimbal
                    self.sensor = self.robot.sensor
                    self.blaster = self.robot.blaster
                    self.led = self.robot.led

                    self.sensor.sub_distance(freq=10, callback=self._sub_distance_handler)
                    self.robot.set_robot_mode(mode=robomaster.robot.CHASSIS_LEAD)
                    self.gimbal.recenter()

                    self.connected = True
                    print("Connected! (Mode: CHASSIS_LEAD)")
                    return True
                except Exception as e:
                    last_err = e
                    self.connected = False
                    try:
                        if self.robot:
                            self.robot.close()
                    except Exception:
                        pass
                    if i < retries - 1:
                        time.sleep(retry_delay_s)

            print(f"Connection failed: {last_err}")
            return False

    def disconnect(self):
        """Close connection."""
        with self._connect_lock:
            if self.connected:
                try:
                    if self.chassis:
                        self.chassis.drive_speed(x=0, y=0, z=0)
                except Exception:
                    pass
                try:
                    if self.robot:
                        self.robot.close()
                except Exception:
                    pass
                self.connected = False
                self.chassis = None
                self.gimbal = None
                self.sensor = None
                self.blaster = None
                self.led = None
                print("Disconnected.")

    def _reset_robot_instance(self):
        try:
            if self.robot:
                self.robot.close()
        except Exception:
            pass
        self.robot = robot.Robot()
        self.chassis = None
        self.gimbal = None
        self.sensor = None
        self.blaster = None
        self.led = None
        self.connected = False

    def _reconnect(self):
        self.disconnect()
        return self.connect()

    def _call_with_reconnect(self, fn, *args, **kwargs):
        if not self.connected:
            if not self.connect():
                raise RuntimeError("Not connected")
        try:
            return fn(*args, **kwargs)
        except Exception:
            if not self._reconnect():
                raise
            return fn(*args, **kwargs)

    def _sub_distance_handler(self, distance_info):
        """Callback for distance sensor data."""
        # distance_info is typically a tuple/list of distances?
        # SDK docs say: sub_distance callback receives distance in mm.
        # It seems to be a single value for the sensor that triggered it?
        # Or a list of all sensors?
        # Actually, `sub_distance` subscribes to ALL TOF sensors usually.
        # But wait, distance_info structure depends on the robot model.
        # For EP/S1, it's usually the TOF sensor.
        # Let's assume index 0 is the front sensor.
        try:
            # Check if it's a list/tuple
            if isinstance(distance_info, (list, tuple)):
                with self.dist_lock:
                    self.ir_distances[1] = distance_info[0] # Assuming sensor 1 is at index 0
        except:
            pass

    def move(self, x=0.0, y=0.0, z=0.0, xy_speed=0.8, z_speed=45):
        """
        Move chassis.
        x: forward/backward (m)
        y: left/right (m)
        z: rotation (degree)
        """
        def _do():
            print(f"Moving: x={x}, y={y}, z={z}, speed={xy_speed}m/s")
            return self.chassis.move(x=x, y=y, z=z, xy_speed=xy_speed, z_speed=z_speed).wait_for_completed()
        return self._call_with_reconnect(_do)

    def speed(self, x=0.0, y=0.0, z=0.0):
        """
        Set chassis speed.
        x: forward/backward speed (m/s)
        y: left/right speed (m/s)
        z: rotation speed (degree/s)
        """
        def _do():
            return self.chassis.drive_speed(x=x, y=y, z=z)
        return self._call_with_reconnect(_do)

    def move_gimbal(self, pitch=0, yaw=0, pitch_speed=20, yaw_speed=20):
        """
        Move gimbal relative to current position.
        """
        def _do():
            print(f"Gimbal move: p={pitch}, y={yaw}")
            return self.gimbal.move(pitch=pitch, yaw=yaw, pitch_speed=pitch_speed, yaw_speed=yaw_speed).wait_for_completed()
        return self._call_with_reconnect(_do)

    def move_gimbal_to(self, pitch=0, yaw=0, pitch_speed=20, yaw_speed=20):
        """
        Move gimbal to absolute position.
        """
        def _do():
            print(f"Gimbal to: p={pitch}, y={yaw}")
            return self.gimbal.moveto(pitch=pitch, yaw=yaw, pitch_speed=pitch_speed, yaw_speed=yaw_speed).wait_for_completed()
        return self._call_with_reconnect(_do)

    def recenter(self):
        """Recenter gimbal."""
        def _do():
            print("Recentering gimbal...")
            return self.gimbal.recenter().wait_for_completed()
        return self._call_with_reconnect(_do)

    def fire(self, type="ir", count=1):
        """
        Fire blaster.
        type: 'ir' or 'bead'
        """
        def _do():
            fire_type = "ir"
            print(f"Firing {fire_type}...")
            self.blaster.fire(fire_type=fire_type, times=int(count))
            time.sleep(max(1.0, count * 0.5))
        return self._call_with_reconnect(_do)

    def play_sound(self, sound, times=1, timeout_s=2.0):
        def _do():
            sound_id = _parse_sound_id(sound)
            t = int(times)
            if t <= 0:
                return True
            print(f"Playing sound: id={sound_id} times={t}")
            act = self.robot.play_sound(int(sound_id), times=t)
            if act is None:
                return False
            ok = act.wait_for_completed(timeout=float(timeout_s))
            return bool(ok)
        return self._call_with_reconnect(_do)

    def play_audio(self, path: str, timeout_s: float = 8.0):
        def _do():
            p = str(path)
            if not os.path.isabs(p):
                p = os.path.abspath(p)
            print(f"Playing audio: {p}")
            act = self.robot.play_audio(p)
            if act is None:
                return False
            ok = act.wait_for_completed(timeout=float(timeout_s))
            return bool(ok)
        return self._call_with_reconnect(_do)

    def set_led(self, comp="all", r=255, g=255, b=255, effect="on"):
        """
        Set LED effect.
        """
        def _do():
            print(f"LED: comp={comp}, rgb=({r},{g},{b}), effect={effect}")
            self.led.set_led(comp=comp, r=r, g=g, b=b, effect=effect)
            time.sleep(0.5)
        return self._call_with_reconnect(_do)

    def get_ir_distance(self, id=1):
        """Get cached IR distance."""
        with self.dist_lock:
            return self.ir_distances.get(id, None)

    def set_mode(self, mode="free"):
        """Set robot mode: free, gimbal_lead, chassis_lead"""
        mode_map = {
            "free": robomaster.robot.FREE,
            "gimbal_lead": robomaster.robot.GIMBAL_LEAD,
            "chassis_lead": robomaster.robot.CHASSIS_LEAD
        }
        if mode in mode_map:
            return self._call_with_reconnect(self.robot.set_robot_mode, mode=mode_map[mode])

    def get_system_info(self):
        """Get robot system information."""
        if not self.connected:
            if not self.connect():
                return None
        
        info = {}
        
        # SN
        try:
            info['sn'] = self.robot.get_sn()
        except:
            info['sn'] = "Unknown"
            
        # Version
        try:
            info['version'] = self.robot.get_version()
        except:
            info['version'] = "Unknown"
            
        # Modules presence check (heuristic)
        info['modules'] = {}
        
        # Camera
        try:
            # We can't easily check if camera is "plugged in" without streaming, 
            # but object existence is a good start.
            if self.robot.camera:
                info['modules']['camera'] = "Detected"
            else:
                info['modules']['camera'] = "Not Detected"
        except:
            info['modules']['camera'] = "Error"

        # Audio (Mic) - Usually implied by camera module on S1/EP
        # We can try to enable audio stream?
        info['modules']['microphone'] = "Integrated with Camera"

        # Sensor (ToF)
        try:
            # Check if sensor object is initialized
            if self.sensor:
                info['modules']['tof_sensor'] = "Detected"
            else:
                info['modules']['tof_sensor'] = "Not Detected"
        except:
            info['modules']['tof_sensor'] = "Error"
            
        return info


def _parse_sound_id(v):
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if not s:
        raise ValueError("sound id is empty")
    aliases = {
        "attack": getattr(robomaster.robot, "SOUND_ID_ATTACK", 0x101),
        "shoot": getattr(robomaster.robot, "SOUND_ID_SHOOT", 0x102),
        "scanning": getattr(robomaster.robot, "SOUND_ID_SCANNING", 0x103),
        "recognized": getattr(robomaster.robot, "SOUND_ID_RECOGNIZED", 0x104),
        "gimbal_move": getattr(robomaster.robot, "SOUND_ID_GIMBAL_MOVE", 0x105),
        "count_down": getattr(robomaster.robot, "SOUND_ID_COUNT_DOWN", 0x106),
        "countdown": getattr(robomaster.robot, "SOUND_ID_COUNT_DOWN", 0x106),
    }
    key = s.lower().replace("-", "_")
    if key in aliases:
        return int(aliases[key])
    return int(s, 0)

def main():
    parser = argparse.ArgumentParser(description="RoboMaster EP Driver (SDK)", conflict_handler="resolve")
    # Connection args
    parser.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Move
    mv = subparsers.add_parser("move", help="Move chassis")
    mv.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    mv.add_argument("x", type=float, help="Forward/Back (m)")
    mv.add_argument("y", type=float, default=0.0, nargs='?', help="Left/Right (m)")
    mv.add_argument("z", type=float, default=0.0, nargs='?', help="Rotation (deg)")

    # Shortcuts
    fw = subparsers.add_parser("forward", help="Move forward")
    fw.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    fw.add_argument("dist", type=float, help="Distance in meters")

    bk = subparsers.add_parser("back", help="Move backward")
    bk.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    bk.add_argument("dist", type=float, help="Distance in meters")

    lt = subparsers.add_parser("left", help="Turn left")
    lt.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    lt.add_argument("angle", type=float, help="Angle in degrees")

    rt = subparsers.add_parser("right", help="Turn right")
    rt.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    rt.add_argument("angle", type=float, help="Angle in degrees")
    
    tn = subparsers.add_parser("turn", help="Turn chassis")
    tn.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    tn.add_argument("angle", type=float, help="Angle in degrees (positive=left, negative=right)")

    ut = subparsers.add_parser("uturn", help="Turn 180 degrees")
    ut.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")

    # Gimbal
    gim = subparsers.add_parser("gimbal", help="Move gimbal")
    gim.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    gim.add_argument("p", type=float)
    gim.add_argument("y", type=float, default=0.0, nargs='?')
    gim.add_argument("--abs", action="store_true", help="Absolute positioning")

    # Fire
    fire = subparsers.add_parser("fire", help="Fire blaster")
    fire.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    fire.add_argument("type", default="ir", choices=['ir', 'bead'])
    fire.add_argument("count", type=int, default=1)

    # Sound
    snd = subparsers.add_parser("sound", help="Play a system sound")
    snd.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    snd.add_argument("sound", help="Sound id (e.g. 0x103) or alias (attack/shoot/scanning/recognized/gimbal_move/count_down)")
    snd.add_argument("--times", type=int, default=1)
    snd.add_argument("--timeout", type=float, default=2.0)

    # Audio
    aud = subparsers.add_parser("audio", help="Upload and play a wav file (mono 48kHz)")
    aud.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    aud.add_argument("path", help="Path to wav file")
    aud.add_argument("--timeout", type=float, default=10.0)

    # Recenter
    rc = subparsers.add_parser("recenter", help="Recenter gimbal")
    rc.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")

    # Sensor
    sens = subparsers.add_parser("sensor", help="Read sensors")
    sens.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    sens.add_argument("--dist", action="store_true", help="Read distance")
    
    # LED
    led_p = subparsers.add_parser("led", help="Control LEDs")
    led_p.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")
    led_p.add_argument("--comp", default="all", help="Component: all, top_all, bottom_all, etc.")
    led_p.add_argument("-r", type=int, default=255, help="Red (0-255)")
    led_p.add_argument("-g", type=int, default=255, help="Green (0-255)")
    led_p.add_argument("-b", type=int, default=255, help="Blue (0-255)")
    led_p.add_argument("--effect", default="on", choices=["on", "off", "flash", "breath", "scrolling"], help="Effect")

    # Info
    inf = subparsers.add_parser("info", help="Get system info")
    inf.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    driver = RoboMasterDriver(conn_type=args.conn)
    if not driver.connect():
        sys.exit(1)

    try:
        if args.command == "move":
            driver.move(args.x, args.y, args.z)
        elif args.command == "forward":
            driver.move(x=args.dist)
        elif args.command == "back":
            driver.move(x=-args.dist)
        elif args.command == "left":
            driver.move(z=args.angle)
        elif args.command == "right":
            driver.move(z=-args.angle)
        elif args.command == "turn":
            driver.move(z=args.angle)
        elif args.command == "uturn":
            driver.move(z=180)
        elif args.command == "gimbal":
            if args.abs:
                driver.move_gimbal_to(args.p, args.y)
            else:
                driver.move_gimbal(args.p, args.y)
        elif args.command == "fire":
            driver.fire(args.type, args.count)
        elif args.command == "sound":
            driver.play_sound(args.sound, times=args.times, timeout_s=args.timeout)
        elif args.command == "audio":
            driver.play_audio(args.path, timeout_s=args.timeout)
        elif args.command == "recenter":
            driver.recenter()
        elif args.command == "sensor":
            if args.dist:
                time.sleep(1) # Wait for data
                print(f"Distance: {driver.get_ir_distance(1)}")
        elif args.command == "led":
            driver.set_led(comp=args.comp, r=args.r, g=args.g, b=args.b, effect=args.effect)
        elif args.command == "info":
            info = driver.get_system_info()
            print("\n=== RoboMaster System Info ===")
            print(f"SN: {info['sn']}")
            print(f"Version: {info['version']}")
            print("Modules:")
            for k, v in info['modules'].items():
                print(f"  - {k}: {v}")
            print("==============================\n")
            
    except KeyboardInterrupt:
        pass
    finally:
        driver.disconnect()

if __name__ == "__main__":
    main()
