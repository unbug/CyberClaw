#!/usr/bin/env python3
import random
import time
import subprocess
import sys
import signal
import os
import argparse

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
    """Executes the cyberbrick_driver.py with given arguments"""
    cmd = ["python3", DRIVER_PATH] + [str(a) for a in args]
    try:
        subprocess.run(cmd, check=False, capture_output=True)
    except Exception as e:
        print(f"Error running driver: {e}")

def check_lock():
    """Check if the lock file exists. If not, stop motors and exit."""
    if not os.path.exists(LOCK_FILE):
        print("\n🛑 Stop signal received (Lock file missing). Stopping...")
        run_driver(["stop"])
        run_driver(["turret", "90"])
        sys.exit(0)

def signal_handler(sig, frame):
    """Handle Ctrl+C by removing lock file and stopping."""
    print("\n🛑 Signal received. Cleaning up...")
    stop_wander()
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
    if os.path.exists(LOCK_FILE):
        print("⚠️ Wander seems to be already running (Lock file exists). Overwriting...")
    
    # Create lock file
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    print("👶 Hey! I am a nuclear-powered little tank! Time to wreck havoc! 💥")
    print(f"Started wandering. Lock file created at: {LOCK_FILE}")
    print("Run 'python3 cyberbrick_wander.py stop' to stop me.")
    
    signal.signal(signal.SIGINT, signal_handler)
    
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
    """Stop the wander loop by removing the lock file."""
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            print("✅ Stop signal sent (Lock file removed).")
            # Force stop driver just in case
            run_driver(["stop"])
        except Exception as e:
            print(f"Error removing lock file: {e}")
    else:
        print("⚠️ Not running (Lock file not found).")
        run_driver(["stop"])

def main():
    parser = argparse.ArgumentParser(description="CyberBrick Wander Skill")
    parser.add_argument("command", choices=["start", "stop"], nargs='?', default="start", help="Start or stop wandering")
    args = parser.parse_args()

    if args.command == "start":
        start_wander()
    elif args.command == "stop":
        stop_wander()

if __name__ == "__main__":
    main()
