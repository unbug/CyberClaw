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
    
    # Set robot mode to 'gimbal_lead' so chassis follows gimbal yaw.
    # This ensures that if we turn the gimbal (where the sensor is), the chassis will align to it.
    # Or, user requested "chassis follows gimbal mode".
    # But wait, if we are in 'gimbal_lead', turning gimbal turns chassis eventually.
    # However, for wandering, we might want to scan with gimbal, then align chassis to move.
    # Actually, if sensor is on gimbal, we MUST ensure gimbal points forward relative to movement.
    # So 'gimbal_lead' is good because it keeps them aligned naturally?
    # Or 'chassis_lead' and we just keep gimbal at 0?
    # User said: "IR sensor is on gimbal, so keep gimbal centered, always let chassis follow gimbal mode".
    # This implies 'gimbal_lead' mode.
    print("Setting robot mode to 'gimbal_lead' (Chassis follows Gimbal)...")
    driver.set_mode("gimbal_lead")
    # Center gimbal just in case
    driver.gimbal(0, 0)
    time.sleep(1)

    start_time = time.time()
    
    try:
        while time.time() - start_time < args.duration:
            # 1. Check sensors (Front distance)
            # Ensure gimbal is centered so we are checking the front!
            # If we don't center, we might be checking the side while moving forward.
            # But constantly sending gimbal move might be jittery?
            # Let's check gimbal attitude first?
            # Or just send center command periodically?
            # Or, better: if we are moving forward, we MUST be centered.
            # Let's enforce it here.
            # Use 'gimbal_to' for absolute centering!
            # We want it at 0, 0 quickly (speed 50).
            # We only send this if we are not already centered? 
            # To avoid flooding, we can just send it every loop. The robot handles redundant commands usually fine.
            # But if it interrupts movement...
            # Actually, gimbal commands run parallel to chassis unless conflicting.
             # In gimbal_lead mode, moving gimbal moves chassis.
             # So if we force gimbal to 0, chassis will try to align to 0.
             # If we are moving forward, we want chassis at 0 relative to itself.
             
            # Actually, simply calling gimbal_to(0,0) every loop ensures we look forward.
            # But constant recenter might reset PID controller too often and cause jitter.
            # We only need to ensure it's centered if we were doing something else.
            # Or maybe just send it periodically (e.g. every 1 sec)?
            # Or better: enforce it once when we enter "move forward" state.
            
            # Let's remove the constant recenter here and put it in logic branches.
            
            dist_str = driver.get_ir_distance(1)
            dist = 999 # Default to far
            
            if dist_str:
                dist_str = dist_str.strip().lower()
                try:
                    d = float(dist_str)
                    # If we got -0.9, it likely means out of range (too far) or invalid.
                    # We treat negative values as safe/far.
                    if d < 0:
                        dist = 999 # Treat as far
                    else:
                        dist = d
                except ValueError:
                    pass
            
            print(f"Distance: {dist}")

            # 2. Obstacle Avoidance Logic
            # RoboMaster EP IR sensor usually returns mm. 
            # 50cm = 500mm.
            # So < 500 is a safe bet for "too close".
            if 0 < dist < 500: # Obstacle within 500 units (mm)
                print("Obstacle detected! Avoiding...")
                # Stop immediately
                driver.speed(0, 0, 0)
                time.sleep(0.5)
                
                # Back up a bit
                driver.move(-0.2, 0, 0)
                time.sleep(1)
                
                # Intelligent Scan
                turn_angle = scan_for_exit(driver)
                print(f"Turning chassis to best angle: {turn_angle}")
                
                # Turn chassis
                driver.move(0, 0, turn_angle)
                time.sleep(1.5)
                
                # Reset gimbal to center after turn to look forward
                driver.recenter()
                time.sleep(0.5)
            else:
                # Path clear, move forward using velocity control for responsiveness
                # This allows checking sensors in the loop while moving
                print(f"Path clear ({dist}). Moving forward...")
                driver.speed(0.3, 0, 0)
                
                # Periodically recenter? Or only if we were not moving forward?
                # Actually, if we are in 'gimbal_lead', the chassis follows gimbal.
                # If gimbal drifts, chassis drifts.
                # It's good to recenter periodically or ensure it's 0.
                # But let's rely on the recenter after avoidance/random action.

            # 3. Random Actions
            if random.random() < 0.1: # Reduced chance (10%) to check sensors more often
                action = random.choice(['fire', 'gimbal', 'wiggle'])
                print(f"Performing random action: {action}")
                
                if action == 'fire':
                    # Fire random type
                    # Keep moving while firing? Maybe safest to stop or just fire.
                    # Firing doesn't affect movement much.
                    driver.fire('ir', 1) 
                
                elif action == 'gimbal':
                    # Stop chassis while looking around to be safe?
                    driver.speed(0, 0, 0)
                    time.sleep(0.2)
                    
                    # Random look
                    p = random.randint(-20, 20)
                    y = random.randint(-45, 45)
                    driver.gimbal(p, y)
                    time.sleep(0.5)
                    # Reset
                    driver.recenter()
                    time.sleep(0.5)
                
                elif action == 'wiggle':
                    # Stop chassis first
                    driver.speed(0, 0, 0)
                    time.sleep(0.2)
                    
                    # Shake body
                    driver.move(0, 0, 30)
                    time.sleep(0.5)
                    driver.move(0, 0, -30)
                    time.sleep(0.5)
                    
                    # Reset gimbal
                    driver.recenter()

            time.sleep(0.1) # Loop rate 10Hz approx

    except KeyboardInterrupt:
        print("Stopping wander...")
    finally:
        driver.speed(0, 0, 0) # Stop velocity
        driver.disconnect()
        print("Wander finished.")

if __name__ == "__main__":
    main()
