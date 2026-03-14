import sys
import os
import time
import math
import signal
import threading
import atexit
from collections import deque

# Lock file path
LOCK_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'wander.lock'))

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../vendor'))
if sdk_path not in sys.path:
    sys.path.append(sdk_path)

import robomaster
from robomaster import robot
import logging
import cv2
import numpy as np
try:
    from .grid_map import GridMapper
except ImportError:
    from grid_map import GridMapper

import matplotlib.pyplot as plt

MAX_TOF_RANGE_M = 2.0
DIST_STALE_S = 1.0
TELEMETRY_DROP_S = 3.5
CRUISE_DIST_MIN_M = 0.6
CRUISE_DIST_MAX_M = 1.8
CRUISE_SPEED_MIN = 0.12
CRUISE_SPEED_MAX = 0.45
EMERGENCY_BRAKE_DIST_M = 0.5

class Speaker:
    """Helper for playing sounds."""
    def __init__(self, robot_instance):
        self.robot = robot_instance
        self.last_sound_time = 0
        
    def play(self, sound_id):
        """Play a system sound if enough time has passed."""
        if time.time() - self.last_sound_time < 1.0: # Debounce
            return
        try:
            self.robot.play_sound(sound_id).wait_for_completed(timeout=1)
            self.last_sound_time = time.time()
        except:
            pass

class LedController:
    """Helper for LED effects."""
    def __init__(self, robot_instance):
        self.robot = robot_instance
        self.current_state = None
        self.last_update_time = 0
        
    def set_state(self, state, force=False):
        now = time.time()
        # Refresh every 2 seconds even if state hasn't changed
        if not force and self.current_state == state:
            if now - self.last_update_time < 2.0:
                return
        
        self.current_state = state
        self.last_update_time = now
        
        try:
            print(f"Setting LED State: {state}")
            
            # Helper to send command safely
            def send_cmd():
                if state == "CRUISE":
                    return self.robot.led.set_led(comp="all", r=0, g=255, b=0, effect="on")
                elif state == "SCAN":
                    return self.robot.led.set_led(comp="all", r=0, g=0, b=255, effect="flash", freq=2)
                elif state == "TURN":
                    return self.robot.led.set_led(comp="all", r=255, g=255, b=0, effect="on")
                elif state == "AVOID":
                    return self.robot.led.set_led(comp="all", r=255, g=0, b=0, effect="flash", freq=5)
                elif state == "HIT":
                    return self.robot.led.set_led(comp="all", r=255, g=0, b=255, effect="flash", freq=10)
                elif state == "IDLE":
                     return self.robot.led.set_led(comp="all", r=255, g=255, b=255, effect="on")
                return False

            # Send command (First Try)
            success = send_cmd()
            
            # Double Tap for reliability (Wait 50ms)
            time.sleep(0.05)
            if not success:
                print(f"⚠️ LED Command Retry: {state}")
                success = send_cmd()
            
            if success:
                print(f"✅ LED Set: {state}")
            else:
                print(f"❌ LED Failed: {state}")
                
        except Exception as e:
            print(f"⚠️ LED Error: {e}")

class SlamPatrol:
    def __init__(self, conn_type="sta", verbose=False):
        self.conn_type = conn_type
        self.verbose = verbose
        self.create_lock_file()
        
        # Enable SDK logging if verbose
        if self.verbose:
            # Configure console logging instead of file
            # robomaster.enable_logging_to_file() # Don't use this
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            robomaster.logger.addHandler(handler)
            robomaster.logger.setLevel(logging.INFO)
            print("SDK Console Logging Enabled.")
            
        self.robot = None
        self.chassis = None
        self.gimbal = None
        self.sensor = None
        self.camera = None
        self._connect_lock = threading.Lock()
        
        self.running = True
        self.mapper = GridMapper(width_m=20.0, height_m=20.0, resolution=0.1, max_range_m=MAX_TOF_RANGE_M)
        self.speaker = None
        self.led_ctl = None
        
        # State
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0 # radians (Chassis Yaw)
        self.gimbal_yaw = 0.0 # radians (Relative to Chassis)
        self.hit_detected = False
        self.last_hit_armor = 0
        
        # Sensor
        self.last_dist = None
        self.last_dist_time = 0
        self.last_pos_time = 0
        
        # Vision
        self.visual_obstacles = [] # List of (angle_rad, dist_m) relative to gimbal center
        self.ai_obstacles = []
        self.last_ai_time = 0
        self._edge_block_hist = deque(maxlen=5)
        self._last_edge_check_t = 0.0
        self.camera_stream_enabled = False
        self._unstick_side = 1
        self._unstick_attempts = 0
        self._unstick_window_t = 0.0
        self._last_unstick_t = 0.0
        self._action_fail_count = 0
        self._action_fail_window_t = 0.0
        
        self.lock = threading.Lock()
        
        # Signal handling
        signal.signal(signal.SIGINT, self.stop_signal)
        signal.signal(signal.SIGTERM, self.stop_signal)
        
        # Cleanup on exit
        atexit.register(self.cleanup)

        # Visualization
        self.fig, self.ax = plt.subplots()
        self.img = None
        plt.ion() # Interactive mode

    def _cruise_speed(self, dist_m):
        if dist_m is None:
            return 0.0
        d = max(CRUISE_DIST_MIN_M, min(CRUISE_DIST_MAX_M, dist_m))
        t = (d - CRUISE_DIST_MIN_M) / (CRUISE_DIST_MAX_M - CRUISE_DIST_MIN_M)
        return CRUISE_SPEED_MIN + t * (CRUISE_SPEED_MAX - CRUISE_SPEED_MIN)

    def _visual_obstacles_snapshot(self):
        with self.lock:
            return list(self.visual_obstacles) + list(self.ai_obstacles)

    def _angle_penalty_distance(self, angle_rad, default_dist):
        effective = default_dist
        obs = self._visual_obstacles_snapshot()
        if not obs:
            return effective
        for oa, od in obs:
            if od is None:
                continue
            if od > MAX_TOF_RANGE_M + 0.5:
                continue
            da = abs((oa - angle_rad + math.pi) % (2 * math.pi) - math.pi)
            if da <= math.radians(20):
                effective = min(effective, max(0.0, od - 0.2))
        return effective

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
        self.camera = None
        self.camera_stream_enabled = False
        self.speaker = Speaker(self.robot)
        self.led_ctl = LedController(self.robot)

    def _note_action_failure(self):
        now = time.time()
        if now - self._action_fail_window_t > 10.0:
            self._action_fail_window_t = now
            self._action_fail_count = 0
        self._action_fail_count += 1
        if self._action_fail_count >= 3:
            raise RuntimeError("Control channel unresponsive")

    def _try_move(self, x=0.0, y=0.0, z=0.0, xy_speed=0.6, z_speed=90, timeout=6, fatal_on_fail=False):
        try:
            action = self.chassis.move(x=x, y=y, z=z, xy_speed=xy_speed, z_speed=z_speed)
            ok = action.wait_for_completed(timeout=timeout)
            if not ok:
                self._note_action_failure()
                if fatal_on_fail:
                    raise RuntimeError("Move Timeout")
            return bool(ok)
        except Exception:
            self._note_action_failure()
            if fatal_on_fail:
                raise
            return False

    def _unstick(self):
        now = time.time()
        if now - self._unstick_window_t > 30.0:
            self._unstick_window_t = now
            self._unstick_attempts = 0
        self._unstick_attempts += 1
        self._last_unstick_t = now

        self.chassis.drive_speed(x=0, y=0, z=0)
        time.sleep(0.15)

        side = self._unstick_side
        self._unstick_side *= -1

        back = 0.25
        strafe = 0.35
        turn = 35 * side
        if self._unstick_attempts == 2:
            back = 0.35
            strafe = 0.45
            turn = 90 * side
        elif self._unstick_attempts >= 3:
            back = 0.45
            strafe = 0.55
            turn = 180

        ok = self._try_move(x=-back, xy_speed=0.6, timeout=5)
        if not ok:
            return False

        ok = self._try_move(y=strafe * side, xy_speed=0.6, timeout=6)
        if not ok:
            return False

        ok = self._try_move(z=turn, z_speed=120, timeout=8)
        return bool(ok)

    def create_lock_file(self):
        if os.path.exists(LOCK_FILE):
            print(f"Lock file exists: {LOCK_FILE}")
            print("Another instance might be running. Please stop it first.")
            # Check if process is actually running?
            # For simplicity, we just overwrite or fail.
            # Let's try to read PID and check.
            try:
                with open(LOCK_FILE, 'r') as f:
                    pid = int(f.read().strip())
                try:
                    os.kill(pid, 0) # Check if process exists
                    print(f"Process {pid} is running. Exiting.")
                    sys.exit(1)
                except OSError:
                    print("Stale lock file found. Removing.")
                    os.remove(LOCK_FILE)
            except:
                pass
        
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))

    def cleanup(self):
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        self.stop()

    def stop_signal(self, signum, _frame):
        print(f"Received signal {signum}. Stopping...")
        self.running = False
        self.cleanup()
        sys.exit(0)

    def stop(self):
        """Force stop robot"""
        self.running = False
        print("Stopping robot...")
        try:
            if self.chassis:
                self.chassis.drive_speed(x=0, y=0, z=0)
            if self.robot:
                self.robot.close()
        except:
            pass

    def initialize(self):
        print("Initializing SLAM Patrol...")
        while self.running:
            try:
                with self._connect_lock:
                    self._reset_robot_instance()

                # Try connecting
                print(f"Connecting via {self.conn_type}...")
                self.robot.initialize(conn_type=self.conn_type)
                self.chassis = self.robot.chassis
                self.gimbal = self.robot.gimbal
                self.sensor = self.robot.sensor
                self.camera = self.robot.camera
                
                self.camera_stream_enabled = False
                if self.conn_type in ("ap", "rndis"):
                    print("Starting Camera Stream...")
                    self.camera.start_video_stream(display=False)
                    self.camera_stream_enabled = True
                else:
                    print("Camera Stream Disabled for conn_type=sta")
                
                # Subscriptions
                self.chassis.sub_position(freq=20, callback=self.cb_pos)
                self.chassis.sub_attitude(freq=20, callback=self.cb_att)
                self.sensor.sub_distance(freq=20, callback=self.cb_dist)
                self.gimbal.sub_angle(freq=20, callback=self.cb_gimbal)
                
                # Vision
                if self.robot.vision:
                    print("Enabling Vision Detection (Person, Marker)...")
                    self.robot.vision.sub_detect_info(name="person", callback=self.cb_vision_person)
                    self.robot.vision.sub_detect_info(name="marker", callback=self.cb_vision_marker)

                try:
                    if self.robot.ai_module:
                        print("Enabling AI Module Detection...")
                        self.robot.ai_module.sub_ai_event(callback=self.cb_ai_event)
                except Exception:
                    pass
                
                # Armor Hit Detection
                if self.robot.armor:
                    print("Enabling Armor Hit Detection...")
                    self.robot.armor.set_hit_sensitivity(comp="all", sensitivity=5)
                    self.robot.armor.sub_hit_event(callback=self.cb_hit)
                
                # Default Mode: CHASSIS_LEAD (Gimbal follows Chassis)
                self.robot.set_robot_mode(mode=robomaster.robot.CHASSIS_LEAD)
                time.sleep(1)
                # Ensure Gimbal is looking straight and level (Pitch 0)
                self.gimbal.moveto(pitch=0, yaw=0, pitch_speed=30, yaw_speed=30).wait_for_completed()
                self.gimbal.recenter().wait_for_completed()
                
                # Re-init LED Controller with fresh robot instance
                self.speaker = Speaker(self.robot)
                self.led_ctl = LedController(self.robot)
                
                print("✅ Robot Connected (CHASSIS_LEAD Mode).")
                self.speaker.play(robomaster.robot.SOUND_ID_RECOGNIZED)
                self.led_ctl.set_state("CRUISE", force=True)
                with self.lock:
                    now = time.time()
                    self.last_dist_time = now
                    self.last_pos_time = now
                return True
            except Exception as e:
                print(f"❌ Connection failed: {e}")
                print("Retrying in 5 seconds...")
                try:
                    self.robot.close()
                except:
                    pass
                time.sleep(5)
                # If we are stopping, break
                if not self.running: return False

    def cb_hit(self, sub_info):
        """
        Callback for Armor Hit.
        sub_info: (armor_id, hit_type)
        """
        try:
            armor_id, hit_type = sub_info
            print(f"⚠️ Armor Hit Detected! ID: {armor_id}, Type: {hit_type}")
            with self.lock:
                self.hit_detected = True
                self.last_hit_armor = armor_id
        except:
            pass

    def cb_pos(self, info):
        # x, y, z
        with self.lock:
            self.x, self.y, _ = info
            self.last_pos_time = time.time()

    def cb_att(self, info):
        # yaw, pitch, roll (degrees)
        with self.lock:
            self.yaw = math.radians(info[0])

    def cb_gimbal(self, info):
        # pitch, yaw, pitch_speed, yaw_speed
        # yaw is relative to chassis (usually)
        # Note: In FREE mode, gimbal yaw is separate?
        # But sub_angle usually returns joint angle.
        with self.lock:
            self.gimbal_yaw = math.radians(info[1])

    def cb_dist(self, info):
        # dist in mm
        try:
            d_mm = info[0]
            with self.lock:
                self.last_dist = d_mm / 1000.0 # Convert to meters
                self.last_dist_time = time.time()
        except:
            pass

    def cb_vision_person(self, info):
        """
        Callback for Person Detection.
        info: list of (x, y, w, h) normalized.
        """
        self._process_vision(info, type="person")

    def cb_vision_marker(self, info):
        """
        Callback for Marker Detection.
        info: list of (x, y, w, h, info) normalized.
        """
        self._process_vision(info, type="marker")

    def cb_ai_event(self, sub_info):
        try:
            _num, ai_info = sub_info
        except Exception:
            return

        obstacles = []

        if isinstance(ai_info, list):
            for item in ai_info:
                if not isinstance(item, (list, tuple)) or len(item) < 5:
                    continue
                x = item[1] if len(item) > 1 else item[0]
                w = item[3] if len(item) > 3 else None
                if x is None or w is None:
                    continue

                try:
                    xf = float(x)
                    wf = float(w)
                except Exception:
                    continue

                if xf <= 1.5:
                    x_norm = xf
                elif xf <= 320:
                    x_norm = xf / 320.0
                else:
                    x_norm = xf / 1280.0

                if wf <= 1.5:
                    w_norm = wf
                elif wf <= 320:
                    w_norm = wf / 320.0
                else:
                    w_norm = wf / 1280.0

                x_norm = max(0.0, min(1.0, x_norm))
                w_norm = max(1e-6, min(1.0, w_norm))

                angle = (x_norm - 0.5) * math.radians(90)
                dist = 0.3 / w_norm
                if dist > 3.0:
                    continue
                obstacles.append((angle, dist))

        with self.lock:
            self.ai_obstacles = obstacles
            self.last_ai_time = time.time()

    def _process_vision(self, info, type):
        obstacles = []
        if info:
            for obj in info:
                # x, y are center coordinates (0.0 - 1.0)
                # w, h are dimensions (0.0 - 1.0)
                x, _y, w, _h = obj[0], obj[1], obj[2], obj[3]
                
                # Filter small objects (noise or far away)
                if w < 0.05: continue
                
                # Calculate Angle relative to camera center
                # FOV_H approx 96 deg? Let's assume 90 deg for safety ( +/- 45 )
                # x=0.5 -> 0 deg. x=0 -> -45 deg. x=1 -> +45 deg.
                angle = (x - 0.5) * math.radians(90) # Negative = Left
                
                # Estimate Distance
                # Heuristic: Person width ~0.5m. Marker ~0.2m.
                # d = real_w * focal_len / pixel_w
                # normalized w = pixel_w / img_w
                # d = real_w / (w * 2 * tan(FOV/2))
                # Simplified: d = K / w
                
                if type == "person":
                    k = 0.5 # Calibration factor
                else:
                    k = 0.2
                
                dist = k / w
                if dist > 3.0: continue # Ignore far objects
                
                obstacles.append((angle, dist))
        
        with self.lock:
            # Replace old obstacles of this type?
            # Actually, this callback might be high freq.
            # We should maintain a list. But simpler: just store latest.
            # We merge lists from person/marker?
            # For now, let's just append to a temporary list and clear it periodically?
            # Or better: `self.visual_obstacles` is a list of ALL current valid detections.
            # Since we have separate callbacks, we need separate storage or a merged one.
            # Let's use `self.vision_data = {'person': [], 'marker': []}`
            if not hasattr(self, 'vision_data'):
                self.vision_data = {'person': [], 'marker': []}
            
            self.vision_data[type] = obstacles
            
            # Flatten
            self.visual_obstacles = self.vision_data.get('person', []) + self.vision_data.get('marker', [])

    def detect_visual_obstacle(self):
        try:
            now = time.time()
            if now - self._last_edge_check_t < 0.15:
                if len(self._edge_block_hist) == 0:
                    return False
                return sum(self._edge_block_hist) >= 3
            self._last_edge_check_t = now
            if not self.camera_stream_enabled:
                self._edge_block_hist.append(False)
                return sum(self._edge_block_hist) >= 3

            # Get latest frame
            img = self.camera.read_cv2_image(strategy="newest")
            if img is None:
                self._edge_block_hist.append(False)
                return sum(self._edge_block_hist) >= 3
            
            # Crop ROI: Bottom-Center (Focus on floor/legs)
            # Img shape: (360, 640) or (720, 1280)
            h, w = img.shape[:2]
            # Look at the bottom 40% of the image, center 60% width
            roi_h_start = int(h * 0.6)
            roi_h_end = h
            roi_w_start = int(w * 0.2)
            roi_w_end = int(w * 0.8)
            
            roi = img[roi_h_start:roi_h_end, roi_w_start:roi_w_end]
            
            # Preprocessing
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Canny Edge Detection
            # Thresholds tuned for "sharp edges" like table legs
            edges = cv2.Canny(blurred, 50, 150)
            
            edge_pixels = np.count_nonzero(edges)
            total_pixels = edges.size
            density = edge_pixels / total_pixels if total_pixels else 0.0

            gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
            angle = np.degrees(np.arctan2(gy, gx))
            angle_abs = np.abs(angle)

            edge_mask = edges > 0
            if np.any(edge_mask):
                vertical_grad_mask = (angle_abs <= 20) | (np.abs(angle_abs - 180) <= 20)
                vertical_edge_pixels = np.count_nonzero(edge_mask & vertical_grad_mask)
                vertical_fraction = vertical_edge_pixels / max(1, edge_pixels)
            else:
                vertical_fraction = 0.0

            raw_block = (density > 0.06) or (density > 0.03 and vertical_fraction > 0.65)
            self._edge_block_hist.append(bool(raw_block))
            return sum(self._edge_block_hist) >= 3
                
        except Exception:
            # print(f"Vision Error: {e}")
            self._edge_block_hist.append(False)
            return sum(self._edge_block_hist) >= 3

    def run(self):
        # Main Loop for Auto-Reconnect
        while self.running:
            # 1. Connect
            if not self.initialize():
                break # Failed to init or stopping
            
            print("SLAM Patrol Started. Mapping and Navigating...")
            
            # State Machine: "CRUISE", "SCAN", "TURN", "AVOID", "UNSTICK"
            state = "CRUISE"
            state_enter_t = time.time()
            last_scan_t = 0.0
            last_pose = (0.0, 0.0)
            last_progress_t = time.time()
            last_viz_t = 0.0
            
            try:
                while self.running:
                    # Check connection health?
                    # SDK doesn't expose `is_connected()` easily.
                    # We rely on exceptions from actions.
                    
                    # 1. Update Map
                    with self.lock:
                        rx, ry, ryaw = self.x, self.y, self.yaw
                        dist = self.last_dist
                        dist_t = self.last_dist_time
                        pos_t = self.last_pos_time
                        gyaw = self.gimbal_yaw # Relative to chassis

                    now = time.time()

                    if (dist_t and (now - dist_t) > TELEMETRY_DROP_S) or (pos_t and (now - pos_t) > TELEMETRY_DROP_S):
                        raise RuntimeError("Telemetry stalled")

                    dist_valid = dist if (dist is not None and (now - dist_t) <= DIST_STALE_S) else None
                    if dist_valid is None and (now - dist_t) > DIST_STALE_S and int(now) % 2 == 0:
                        print("⚠️ Warning: Sensor data stale!")

                    self.mapper.update(rx, ry, ryaw, gyaw, dist_valid)
                    
                    # Safety Brake (IR Distance OR Visual)
                    edge_block = False
                    obj_block = False
                    obj_block_dist = None
                    if state == "CRUISE":
                        edge_block = self.detect_visual_obstacle()
                        if edge_block and int(now) % 2 == 0:
                            print("👁️ Visual Obstacle Detected! (Edge)")

                        obs = self._visual_obstacles_snapshot()
                        for oa, od in obs:
                            if od is None:
                                continue
                            if od > MAX_TOF_RANGE_M + 0.5:
                                continue
                            if abs(oa) <= math.radians(15):
                                if obj_block_dist is None or od < obj_block_dist:
                                    obj_block_dist = od
                        if obj_block_dist is not None and obj_block_dist < 1.2:
                            obj_block = True
                            if int(now) % 2 == 0:
                                print(f"👁️ Visual Obstacle Detected! (SDK Vision) {obj_block_dist:.2f}m")

                    # Print Distance for Debug
                    if state == "CRUISE" and (int(now * 10) % 10 == 0):
                         d_str = f"{dist_valid:.2f}m" if dist_valid is not None else "None"
                         print(f"DEBUG: Dist={d_str}")

                    # Stop if sensor not ready
                    if state == "CRUISE" and dist_valid is None:
                        self.chassis.drive_speed(x=0, y=0, z=0)
                        print("⏳ Waiting for sensor data...")
                        time.sleep(0.1)
                        continue

                    if state == "CRUISE" and ((dist_valid is not None and dist_valid < EMERGENCY_BRAKE_DIST_M) or edge_block or obj_block):
                        # Since we are in CHASSIS_LEAD, sensor is always forward.
                        if dist_valid is not None and dist_valid < EMERGENCY_BRAKE_DIST_M:
                            reason = f"IR {dist_valid:.2f}m"
                        elif obj_block_dist is not None:
                            reason = f"Vision {obj_block_dist:.2f}m"
                        else:
                            reason = "Edge"
                        print(f"🛑 Emergency Brake! Obstacle ({reason})")
                        self.speaker.play(robomaster.robot.SOUND_ID_ATTACK) # Alert sound
                        self.chassis.drive_speed(x=0, y=0, z=0)
                        state = "AVOID"
                        state_enter_t = now
                        self.led_ctl.set_state("AVOID", force=True)
                        continue

                    # Armor Hit Reaction (Highest Priority)
                    if self.hit_detected:
                        print("⚠️ REACTING TO HIT!")
                        self.speaker.play(robomaster.robot.SOUND_ID_ATTACK)
                        self.led_ctl.set_state("HIT", force=True)
                        
                        # Determine reaction based on hit direction
                        # Armor IDs: 1:Back, 2:Front, 3:Left, 4:Right
                        reaction_turn = 0
                        reaction_move_x = 0
                        
                        if self.last_hit_armor == 1: # Hit from Back -> Run Forward
                            reaction_move_x = 0.5
                        elif self.last_hit_armor == 2: # Hit from Front -> Back up + Turn
                            reaction_move_x = -0.3
                            reaction_turn = 180
                        elif self.last_hit_armor == 3: # Hit from Left -> Turn Right
                            reaction_turn = -90
                        elif self.last_hit_armor == 4: # Hit from Right -> Turn Left
                            reaction_turn = 90
                        else: # Unknown -> Spin
                            reaction_turn = 180
                            
                        # Execute Reaction
                        if reaction_move_x != 0:
                            self._try_move(x=reaction_move_x, y=0, z=0, xy_speed=1.0, timeout=2, fatal_on_fail=True)
                        if reaction_turn != 0:
                            self._try_move(x=0, y=0, z=reaction_turn, z_speed=180, timeout=2, fatal_on_fail=True)
                            
                        self.hit_detected = False
                        state = "CRUISE"
                        state_enter_t = now
                        self.led_ctl.set_state("CRUISE", force=True)
                        continue

                    # State Logic
                    if state == "CRUISE":
                        self.led_ctl.set_state("CRUISE")
                        cruise_speed = self._cruise_speed(dist_valid)
                        self.chassis.drive_speed(x=cruise_speed, y=0, z=0)

                        moved = math.hypot(rx - last_pose[0], ry - last_pose[1])
                        if moved > 0.03:
                            last_pose = (rx, ry)
                            last_progress_t = now

                        preempt_scan = (dist_valid is not None and dist_valid < 0.9) or edge_block or obj_block
                        stuck = (now - last_progress_t) > 2.5 and cruise_speed > 0.08
                        cooldown_ok = (now - last_scan_t) > 1.2
                        if stuck and (now - self._last_unstick_t) > 5.0:
                            self.chassis.drive_speed(x=0, y=0, z=0)
                            state = "UNSTICK"
                            state_enter_t = now
                        elif (preempt_scan and cooldown_ok) or (stuck and (now - last_scan_t) > 2.5):
                            self.chassis.drive_speed(x=0, y=0, z=0)
                            state = "SCAN"
                            state_enter_t = now
                    
                    elif state == "AVOID":
                        self.led_ctl.set_state("AVOID", force=True)
                        self.chassis.drive_speed(x=0, y=0, z=0)
                        time.sleep(0.5)
                        state = "SCAN"
                        state_enter_t = time.time()
                        
                    elif state == "SCAN":
                        self.led_ctl.set_state("SCAN", force=True)
                        print("Scanning surroundings (Chassis Mode)...")
                        # Stop chassis
                        self.chassis.drive_speed(x=0, y=0, z=0)
                        last_scan_t = time.time()
                        
                        # Ensure we are in CHASSIS_LEAD
                        self.robot.set_robot_mode(mode=robomaster.robot.CHASSIS_LEAD)
                        # Recenter Gimbal
                        self.gimbal.recenter().wait_for_completed()
                        
                        measurements = {}
                        current_heading_offset = 0
                        
                        # Helper to scan one angle (Turns Chassis)
                        def scan_at(yaw_angle_rel):
                            nonlocal current_heading_offset
                            # Calculate turn needed
                            turn_needed = yaw_angle_rel - current_heading_offset
                            
                            # Move Chassis
                            if turn_needed != 0:
                                # Normalize angle to -180 to 180
                                turn_needed = (turn_needed + 180) % 360 - 180
                                if not self._try_move(x=0, y=0, z=turn_needed, z_speed=45, timeout=5):
                                    print("⚠️ Scan Turn Timeout!")
                                current_heading_offset += turn_needed
                            
                            # Wait for sensor reading to update (timestamp > move_time)
                            move_end_time = time.time()
                            d = MAX_TOF_RANGE_M
                            
                            # Wait up to 1.0s for a fresh reading
                            for _ in range(10):
                                time.sleep(0.1)
                                if self.last_dist_time > move_end_time:
                                    d = self.last_dist
                                    break
                            else:
                                print("⚠️ Sensor Lag: Using old distance")
                                d = self.last_dist if self.last_dist else MAX_TOF_RANGE_M

                            # Update Map
                            with self.lock:
                                _rx, _ry, _ryaw = self.x, self.y, self.yaw
                                _gyaw = self.gimbal_yaw
                            self.mapper.update(_rx, _ry, _ryaw, _gyaw, d)
                            d_eff = self._angle_penalty_distance(-math.radians(yaw_angle_rel), d)
                            return d, d_eff

                        # 1. Center (0)
                        _d0, d0_eff = scan_at(0)
                        measurements[0] = d0_eff
                        print(f"Scan 0 deg: {d0_eff:.2f}m")
                        
                        # Quick Check: If Front is clear (> 1.5m), skip side scan!
                        if d0_eff > 1.5:
                            print("🚀 Front is clear! Skipping full scan.")
                            best_ang = 0
                            max_d = d0_eff
                        else:
                            # Full Scan Initiated: Play Sound Here
                            self.speaker.play(robomaster.robot.SOUND_ID_SCANNING)
                            
                            _d60, d60_eff = scan_at(60)
                            measurements[60] = d60_eff
                            print(f"Scan 60 deg: {d60_eff:.2f}m")

                            _dm60, dm60_eff = scan_at(-60)
                            measurements[-60] = dm60_eff
                            print(f"Scan -60 deg: {dm60_eff:.2f}m")

                            _d120, d120_eff = scan_at(120)
                            measurements[120] = d120_eff
                            print(f"Scan 120 deg: {d120_eff:.2f}m")

                            _dm120, dm120_eff = scan_at(-120)
                            measurements[-120] = dm120_eff
                            print(f"Scan -120 deg: {dm120_eff:.2f}m")
                            
                            # Find best direction (Strictly Max Distance)
                            best_ang = 0
                            max_d = -1.0
                            
                            print("Scan Results:")
                            for ang, d in measurements.items():
                                print(f"  Angle {ang}: {d:.2f}m")
                                if d > max_d:
                                    max_d = d
                                    best_ang = ang
                                elif d == max_d:
                                    if abs(ang) < abs(best_ang):
                                        best_ang = ang
                            
                            # Dead End Check (< 0.6m)
                            if max_d < 0.6:
                                print("⚠️ Dead End Detected! Turning 180.")
                                best_ang = 180

                        print(f"🏆 Best Direction: {best_ang} deg (Dist: {max_d:.2f}m)")
                        
                        # Calculate final turn needed to reach best_ang from current_heading_offset
                        final_turn = best_ang - current_heading_offset
                        # Normalize
                        final_turn = (final_turn + 180) % 360 - 180
                        
                        self.target_turn_deg = final_turn
                        
                        state = "TURN"
                        state_enter_t = time.time()
                    
                    elif state == "PLAN":
                        state = "CRUISE"
                        state_enter_t = now

                    elif state == "UNSTICK":
                        self.led_ctl.set_state("AVOID", force=True)
                        ok = self._unstick()
                        if not ok:
                            self.chassis.drive_speed(x=0, y=0, z=0)
                            time.sleep(0.5)
                        with self.lock:
                            last_pose = (self.x, self.y)
                        last_progress_t = time.time()
                        state = "SCAN"
                        state_enter_t = time.time()
                    
                    elif state == "TURN":
                        self.led_ctl.set_state("TURN", force=True)
                        if self.target_turn_deg != 0:
                            print(f"Turning Chassis ({self.target_turn_deg:.1f} deg)...")
                            # Turn Chassis with controlled speed
                            turn_cmd = self.target_turn_deg
                            # No limit range (allow 180 turn)
                            
                            if not self._try_move(x=0, y=0, z=turn_cmd, z_speed=45, timeout=8):
                                print("⚠️ Turn Timeout! Wi-Fi unstable?")
                        
                        state = "CRUISE"
                        state_enter_t = time.time()
                        self.led_ctl.set_state("CRUISE", force=True)

                    if (now - state_enter_t) > 18.0 and state in ("SCAN", "TURN"):
                        self.chassis.drive_speed(x=0, y=0, z=0)
                        state = "UNSTICK"
                        state_enter_t = now

                    # Visualization
                    if self.running:
                        if now - last_viz_t > 0.2:
                            last_viz_t = now
                            self.ax.clear()
                            self.ax.imshow(self.mapper.map.T, origin='lower', cmap='Greys', extent=[0, 20, 0, 20])
                            self.ax.plot(rx + 10, ry + 10, 'ro')
                            d_line = dist_valid if dist_valid is not None else MAX_TOF_RANGE_M
                            ex = (rx + 10) + d_line * math.cos(ryaw + gyaw)
                            ey = (ry + 10) + d_line * math.sin(ryaw + gyaw)
                            self.ax.plot([rx+10, ex], [ry+10, ey], 'g-')
                            plt.pause(0.01)

                    time.sleep(0.05)
            
            except Exception as e:
                print(f"⚠️ Runtime Error (Disconnected?): {e}")
                print("Attempting to reconnect...")
                try:
                    self.robot.close()
                except:
                    pass
                # Loop will restart and call initialize()
                time.sleep(2)

def stop_robot():
    """Helper to stop running instance."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            print(f"Stopping process {pid}...")
            os.kill(pid, signal.SIGTERM)
            # Wait a bit
            time.sleep(1)
            if os.path.exists(LOCK_FILE):
                print("Force killing...")
                os.kill(pid, signal.SIGKILL)
                os.remove(LOCK_FILE)
        except Exception as e:
            print(f"Error stopping process: {e}")
            # Fallback to direct stop command
            try:
                r = robot.Robot()
                r.initialize(conn_type="sta")
                r.chassis.drive_speed(x=0, y=0, z=0)
                r.close()
                print("Robot stopped via direct command.")
            except:
                pass
    else:
        print("No lock file found. Sending direct stop command...")
        try:
            r = robot.Robot()
            r.initialize(conn_type="sta")
            r.chassis.drive_speed(x=0, y=0, z=0)
            r.close()
            print("Robot stopped.")
        except Exception as e:
            print(f"Failed to stop robot: {e}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true", help="Stop the robot immediately")
    parser.add_argument("--conn", default="sta", choices=["sta", "ap", "rndis"], help="Connection type (sta/ap/rndis)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    if args.stop:
        stop_robot()
    else:
        bot = SlamPatrol(conn_type=args.conn, verbose=args.verbose)
        bot.run()
