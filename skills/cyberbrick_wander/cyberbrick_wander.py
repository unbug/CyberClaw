#!/usr/bin/env python3
import random
import time
import sys
import signal
import os
import argparse
import atexit
import random
import time

# Import Driver from sibling directory
# Note: cyberbrick_driver is in ../cyberbrick_driver/cyberbrick_driver.py
# We need to add parent/sibling to path or assume structure.
driver_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../cyberbrick_driver'))
if driver_dir not in sys.path:
    sys.path.append(driver_dir)

from cyberbrick_driver import CyberBrickDriver

# Initialize global driver instance
driver = None

# Hyperactive Kid Personality - CyberBrick Wander
# Features: Fast, Erratic, Exaggerated, Restless

# Lock file to control the wander loop
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(CURRENT_DIR, "wander.lock")

# Action Pool: Contains more complex combinations
ACTION_POOL = [
    # Basic Movement (Increased Duration - MAX POWER)
    {"type": "forward", "speed": (100, 100), "duration": (1.5, 3.5), "desc": "Full Speed Ahead! 🚀"},
    {"type": "backward", "speed": (100, 100), "duration": (1.0, 2.0), "desc": "Light Speed Retreat! 🔙"},
    {"type": "left", "speed": (100, 100), "duration": (1.0, 2.0), "desc": "Check Left! 👀"},
    {"type": "right", "speed": (100, 100), "duration": (1.0, 2.0), "desc": "Check Right! 👀"},
    
    # Composite Actions (Macros) - Increased weight for celebration
    {"type": "wiggle", "desc": "Crazy Wiggle 🐛"},
    {"type": "shake_head", "desc": "Crazy Head Shake 🤪"},
    {"type": "panic", "desc": "Panic! 😱"},
    {"type": "celebrate", "desc": "Celebrate Fire! 🎉"},
    {"type": "celebrate", "desc": "One More Shot! 💥"},
    {"type": "circle", "desc": "Magic Circle 🌀"},
]

# Driver Script Path (Relative to this script)
DRIVER_PATH = os.path.join(CURRENT_DIR, "..", "cyberbrick_driver", "cyberbrick_driver.py")

def run_driver(args):
    """Executes the cyberbrick_driver using the imported class instance."""
    global driver
    if driver is None:
        return

    # args is a list like ["forward", "100", "2.0"]
    command = args[0]
    
    try:
        if command == "forward":
            speed = int(args[1])
            duration = float(args[2])
            driver.move_forward(speed, duration)
        elif command == "backward":
            speed = int(args[1])
            duration = float(args[2])
            driver.move_backward(speed, duration)
        elif command == "left":
            speed = int(args[1])
            duration = float(args[2])
            driver.turn_left(speed, duration)
        elif command == "right":
            speed = int(args[1])
            duration = float(args[2])
            driver.turn_right(speed, duration)
        elif command == "turret":
            angle = int(args[1])
            driver.turret(angle)
        elif command == "fire":
            driver.fire()
        elif command == "stop":
            driver.stop()
    except Exception as e:
        print(f"Error executing command {command}: {e}")

def cleanup():
    """Cleanup lock file on exit."""
    if os.path.exists(LOCK_FILE):
        try:
            # Only remove if it's OUR lock file (PID matches)
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(LOCK_FILE)
        except:
            pass
    # Stop motors
    run_driver(["stop"])

def check_lock():
    """Check if we should still be running."""
    # In PID mode, we don't rely on file existence for stopping.
    # We rely on SIGTERM. But we can still check if lock file was stolen/deleted?
    if not os.path.exists(LOCK_FILE):
        print("\n🛑 Lock file missing. Stopping...")
        sys.exit(0)

def signal_handler(sig, frame):
    """Handle signals."""
    print(f"\n🛑 Signal {sig} received. Stopping...")
    sys.exit(0)

# --- Composite Action Definitions ---

def wiggle():
    """Large amplitude left-right wiggle"""
    for _ in range(4): 
        check_lock()
        run_driver(["left", "100", "0.3"]) 
        run_driver(["right", "100", "0.3"])

def shake_head():
    """Crazy head shake"""
    check_lock()
    run_driver(["turret", "160"]) 
    time.sleep(0.15)
    check_lock()
    run_driver(["turret", "20"])
    time.sleep(0.15)
    check_lock()
    run_driver(["turret", "140"])
    time.sleep(0.15)
    run_driver(["turret", "40"])
    time.sleep(0.15)
    run_driver(["turret", "90"])

def panic():
    """Panic: Rapid retreat + random turns"""
    check_lock()
    run_driver(["backward", "100", "0.8"])
    run_driver(["left", "100", "0.6"])
    run_driver(["right", "100", "0.6"])
    run_driver(["left", "100", "0.6"])
    run_driver(["stop"])
    time.sleep(0.3) 

def celebrate():
    """Celebrate: Double fire + huge spin"""
    check_lock()
    run_driver(["fire"])
    time.sleep(0.3)
    run_driver(["fire"])
    run_driver(["left", "100", "2.0"])

def circle():
    """Crazy Circle - Max Speed"""
    check_lock()
    run_driver(["right", "100", "3.0"])

def start_wander():
    """Start the wander loop."""
    global driver
    
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process exists
            os.kill(pid, 0)
            print(f"⚠️ Wander script already running (PID {pid}).")
            sys.exit(1)
        except OSError:
            print("⚠️ Stale lock file found. Removing...")
            os.remove(LOCK_FILE)
        except ValueError:
            os.remove(LOCK_FILE)

    # Initialize driver
    print("Connecting to CyberBrick Driver...")
    driver = CyberBrickDriver()
    if not driver.connect():
        print("❌ Failed to connect to CyberBrick. Exiting.")
        sys.exit(1)

    # Create lock file with PID
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    # Register cleanup
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    print(f"🚀 CyberBrick WANDER started! (PID {os.getpid()})")
    
    while True:
        check_lock()
        
        # Extremely short decision interval
        if random.random() < 0.05:
            pause = random.uniform(0.3, 0.8)
            print(f"🤔 Catching breath {pause:.1f}s...")
            run_driver(["stop"])
            time.sleep(pause)
            continue

        # Randomly choose an action
        action = random.choice(ACTION_POOL)
        print(f"⚡️ {action['desc']}")
        
        atype = action["type"]
        
        if atype == "wiggle":
            wiggle()
        elif atype == "shake_head":
            shake_head()
        elif atype == "panic":
            panic()
        elif atype == "celebrate":
            celebrate()
        elif atype == "circle":
            circle()
        else:
            if random.random() < 0.4: 
                print("💥 Moving Fire!")
                run_driver(["fire"])
            
            speed = random.randint(*action["speed"])
            duration = random.uniform(*action["duration"])
            run_driver([atype, speed, duration])
            time.sleep(duration)
            
        time.sleep(random.uniform(0.01, 0.1))

def stop_wander():
    """Stop the wander loop."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            print(f"🛑 Stopping PID {pid}...")
            os.kill(pid, signal.SIGTERM)
            
            # Wait and check
            time.sleep(1)
            try:
                os.kill(pid, 0)
                print("Force killing...")
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass # Already dead
                
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception as e:
            print(f"Error stopping: {e}")
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
    else:
        print("⚠️ No lock file found. Nothing to stop.")
    
    # Force stop motors just in case
    # Note: stop_wander runs in a separate process, so it needs its own driver instance
    # if we want to send a stop command. But signal handling in the main process
    # should handle cleanup().
    # However, if main process is dead/stuck, we might want to force stop here.
    try:
        d = CyberBrickDriver()
        if d.connect():
            d.stop()
            print("✅ CyberBrick stopped via direct command.")
    except:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CyberBrick Wander Control")
    parser.add_argument("--stop", action="store_true", help="Stop the wandering script")
    args = parser.parse_args()

    if args.stop:
        stop_wander()
    else:
        start_wander()
