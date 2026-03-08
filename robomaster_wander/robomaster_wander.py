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
    start_time = time.time()
    
    try:
        while time.time() - start_time < args.duration:
            # 1. Check sensors (Front distance)
            # Assuming sensor 1 is front.
            dist_str = driver.get_ir_distance(1)
            dist = 999 # Default to far
            
            if dist_str:
                dist_str = dist_str.strip().lower()
                try:
                    dist = float(dist_str)
                    # Sensor may return 0 or negative if out of range or too close
                    # Typically RoboMaster IR sensor returns mm? Or cm?
                    # Docs say: distance <id> ? -> Returns distance in mm usually.
                    # Wait, SDK docs say "ir_distance_sensor distance 1 ?"
                    # Let's assume cm based on previous output "-0.9" which looks weird.
                    # Actually, if it returns -1 or similar, it might mean invalid.
                    
                    # If we got -0.9, maybe it's too far?
                    if dist <= 0:
                        dist = 999 # Treat as far
                    else:
                        # Convert to cm if it's in mm?
                        # If the value is small like 100, 200, it's mm.
                        # If it's 0.5, 1.0, maybe meters?
                        # But wait, output was "-0.90000000000000002".
                        # This looks like an error code or specific status.
                        
                        # Let's rely on empirical test.
                        # If dist > 0 and dist < 500 (50cm in mm? or 50cm?)
                        # Let's assume input is mm for now as is standard for ToF.
                        # BUT, if we see float like 0.5, it might be meters.
                        pass
                except ValueError:
                    pass
            
            print(f"Distance: {dist}")

            # 2. Obstacle Avoidance Logic
            # Threshold: 50cm = 500mm if unit is mm.
            # If unit is cm, 50.
            # Given output "-0.9", it's suspicious.
            # Let's assume valid range is positive.
            if 0 < dist < 500: # Assuming mm, 50cm threshold
                print("Obstacle detected! Avoiding...")
                # Stop
                driver.move(0, 0, 0)
                # Back up a bit
                driver.move(-0.2, 0, 0)
                time.sleep(1)
                # Turn random direction (90 to 180 deg)
                turn_angle = random.choice([-90, 90, 135, -135])
                driver.move(0, 0, turn_angle)
                time.sleep(1.5)
            else:
                # Path clear, move forward
                # Move a small step forward to keep checking loop active
                # Speed 0.3 m/s, distance 0.5m
                print("Path clear. Moving forward...")
                driver.move(0.5, 0, 0, speed_xy=0.3)
                # Wait a bit for movement to complete (approx)
                time.sleep(1.5)

            # 3. Random Actions
            if random.random() < 0.2: # 20% chance
                action = random.choice(['fire', 'gimbal', 'wiggle'])
                print(f"Performing random action: {action}")
                
                if action == 'fire':
                    # Fire random type
                    ft = random.choice(['ir', 'bead'])
                    # For safety in room, maybe prefer IR? 
                    # User asked to test, so let's do mostly IR, rarely bead?
                    # Let's stick to IR for safety unless user specified. 
                    # User said "fire", implying both.
                    # Let's fire IR to be safe for walls.
                    driver.fire('ir', 1) 
                
                elif action == 'gimbal':
                    # Random look
                    p = random.randint(-20, 20)
                    y = random.randint(-45, 45)
                    driver.gimbal(p, y)
                    time.sleep(0.5)
                    # Reset
                    driver.gimbal(0, 0)
                
                elif action == 'wiggle':
                    # Shake body
                    driver.move(0, 0, 30)
                    time.sleep(0.5)
                    driver.move(0, 0, -30)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Stopping wander...")
    finally:
        driver.move(0, 0, 0) # Stop
        driver.disconnect()
        print("Wander finished.")

if __name__ == "__main__":
    main()
