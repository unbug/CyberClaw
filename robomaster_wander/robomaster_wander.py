#!/usr/bin/env python3
import sys
import os
import time
import random
import argparse

# Add sibling directory to path to import driver
current_dir = os.path.dirname(os.path.abspath(__file__))
driver_dir = os.path.join(current_dir, '..', 'robomaster_driver')
sys.path.append(driver_dir)

from robomaster_driver import RoboMasterDriver

def get_dist(driver):
    """Helper to get safe distance."""
    dist_str = driver.get_ir_distance(1)
    dist = 999
    if dist_str:
        dist_str = dist_str.strip().lower()
        try:
            d = float(dist_str)
            if d < 0:
                dist = 999
            else:
                dist = d
        except ValueError:
            pass
    return dist

def scan_for_exit(driver):
    """
    Intelligent scan:
    1. Switch to 'free' mode (gimbal independent).
    2. Scan Left (-60, -30) and Right (30, 60).
    3. Find direction with max distance.
    4. Switch back to 'gimbal_lead'.
    5. Return best angle to turn chassis.
    """
    print("Scanning for exit...")
    driver.set_mode("free")
    time.sleep(0.5)
    
    # Angles to scan: Left 60, Left 30, Right 30, Right 60
    # Prefer smaller turns if clear? Or max clear?
    # Let's check: -45, 45, -90, 90
    scan_angles = [-45, 45, -90, 90]
    best_angle = 180 # Default to turn around if all blocked
    max_dist = -1
    
    threshold = 500 # 50cm safe distance
    
    for ang in scan_angles:
        # Move gimbal quickly
        driver.gimbal_to(0, ang, speed_p=50, speed_y=100)
        time.sleep(0.8) # Wait for move
        
        d = get_dist(driver)
        print(f"Scan {ang} deg: {d}")
        
        if d > max_dist:
            max_dist = d
            best_angle = ang
            
        # If we found a "good enough" path (e.g. > 1m), take it immediately to save time?
        if d > 1000:
            print(f"Found clear path at {ang}!")
            best_angle = ang
            break
            
    # Reset gimbal
    driver.recenter()
    time.sleep(0.5)
    
    # Switch back
    driver.set_mode("gimbal_lead")
    time.sleep(0.2)
    
    return best_angle

def main():
    parser = argparse.ArgumentParser(description="RoboMaster Autonomous Wander")
    parser.add_argument("--host", default="192.168.1.116", help="Robot IP address")
    parser.add_argument("--port", type=int, default=40923, help="Robot SDK port")
    parser.add_argument("--duration", type=int, default=300, help="Wander duration in seconds (default 5 min)")
    parser.add_argument("--mock", action="store_true", help="Mock mode")
    
    args = parser.parse_args()

    driver = RoboMasterDriver(host=args.host, port=args.port, mock=args.mock)
    
    print(f"Connecting to {args.host}...")
    if not driver.connect():
        print("Failed to connect.")
        sys.exit(1)

    print(f"Starting autonomous wander for {args.duration} seconds...")
    
    # Use 'free' mode so gimbal can scan independently of chassis
    print("Setting robot mode to 'free' (Independent Gimbal/Chassis)...")
    driver.set_mode("free")
    time.sleep(1)

    start_time = time.time()
    
    # Current chassis heading relative to start (not really trackable without odometry, 
    # but we only care about relative turns).
    # Actually, in 'free' mode:
    # - gimbal move is relative to gimbal current pos? No, relative to chassis? 
    #   Wait, 'gimbal move' is relative. 'gimbal moveto' is absolute (relative to chassis front).
    #   So 0 is always chassis front.
    
    try:
        while time.time() - start_time < args.duration:
            # 1. Continuous Scanning Strategy
            # Instead of just moving forward, we should proactively scan.
            # But constantly scanning while moving is hard with one sensor.
            # Strategy:
            # - Look Forward (0)
            # - Look Left (-45)
            # - Look Right (45)
            # - (Maybe extreme angles if blocked)
            
            # Let's verify front first.
            driver.gimbal_to(0, 0, speed_p=100, speed_y=100)
            time.sleep(0.3)
            dist_front = get_dist(driver)
            
            # If front is clear (> 1m), just go.
            if dist_front > 1000:
                print(f"Front clear ({dist_front}). Moving forward...")
                driver.speed(0.5, 0, 0) # Faster speed
                time.sleep(0.5) # Move for a bit
                continue
                
            # If front is blocked or somewhat close (< 1m), start scanning for better path.
            print(f"Front obstacle ({dist_front}). Scanning...")
            driver.speed(0, 0, 0) # Stop
            
            # Scan angles: -90 (Left), -45, 0 (already done), 45, 90 (Right)
            # We can also look behind if trapped? 180?
            angles = [-90, -45, 45, 90, 180]
            best_ang = 0
            max_d = dist_front
            
            for ang in angles:
                driver.gimbal_to(0, ang, speed_p=50, speed_y=200) # Fast scan
                time.sleep(0.5)
                d = get_dist(driver)
                print(f"Scan {ang}: {d}")
                
                if d > max_d:
                    max_d = d
                    best_ang = ang
            
            # Decide
            if max_d > 500: # Found a viable path > 50cm
                print(f"Found path at {best_ang} (dist {max_d}). Turning...")
                
                # Turn chassis to match best_ang
                # Note: In free mode, we turn chassis. Gimbal stays? 
                # No, we want to turn chassis so that 'front' becomes 'best_ang'.
                # If we turn chassis by 'best_ang', the gimbal (which is at 'best_ang' relative to chassis)
                # will now be at... wait.
                # If gimbal is at 90 (right), and we turn chassis 90 right.
                # The gimbal stays at world-angle? In free mode yes.
                # So relative to chassis, gimbal becomes 0?
                # Actually, SDK 'chassis move z' turns the chassis.
                # If we turn chassis 90, we should also recenter gimbal to 0 relative to new front?
                # Or just turn chassis, then recenter gimbal.
                
                driver.move(0, 0, best_ang) # Turn chassis
                time.sleep(1.0)
                driver.recenter() # Reset gimbal to look forward relative to new chassis
                time.sleep(0.3)
            else:
                # Trapped? Turn around completely or back up.
                print("Trapped! Backing up...")
                driver.move(-0.3, 0, 0)
                time.sleep(1.0)
                driver.move(0, 0, 180) # Turn 180
                time.sleep(1.5)
                driver.recenter()

            # Random wiggle just for fun if bored (only if path was clear)
            # (Skipped to prioritize navigation)

    except KeyboardInterrupt:
        print("Stopping wander...")
    finally:
        driver.speed(0, 0, 0) # Stop velocity
        driver.disconnect()
        print("Wander finished.")

if __name__ == "__main__":
    main()
