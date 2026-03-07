#!/usr/bin/env python
# coding=utf-8
#
# The CyberBrick Codebase License, see the file LICENSE for details.
#
# Copyright (c) 2025 MakerWorld
#

import time
import matplotlib.pyplot as plt
import numpy as np
import math

_High_Speed_Zone = 40   # (%)
_High_Speed_Zone_Time = 1.0

def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _high_speed_map(current_speed, target_speed, elapsed_time, total_time=2.0, cycle_time=0.02):
    remaining_time = total_time - elapsed_time

    c_speed = abs(current_speed)
    t_speed = abs(target_speed)

    if remaining_time < cycle_time:
        return target_speed

    if t_speed <= c_speed:
        return target_speed

    speed_change_rate = (t_speed - c_speed) / remaining_time

    speed_change_this_cycle = speed_change_rate * cycle_time

    new_speed = c_speed + speed_change_this_cycle
    return new_speed if target_speed >= 0 else -new_speed


current_speed = 0
target_speed = 0
elapsed_time = 0
cycle_time = 0.02
zone_time = _High_Speed_Zone_Time
total_time = 10

table_time = 0

last_tar_speed = 0
last_updata_tar_speed = 0
updata_tar_speed_threadhold = 200

times = []
speeds = []
target_speeds = []

while table_time < total_time:
    # target_speed += random.uniform(-25, 25)
    threahold = 2048
    target_speed = 0 + threahold * 6 * np.sin(table_time *2)
    if abs(target_speed) > threahold:
        target_speed = threahold if target_speed >= 0 else -threahold
    target_speeds.append(target_speed)

    # core start
    if abs(last_tar_speed - target_speed) > updata_tar_speed_threadhold or elapsed_time > zone_time:
        elapsed_time = 0

    if (abs(target_speed) > 2048 * (1 - _High_Speed_Zone / 100.0)):
        current_speed = _high_speed_map(current_speed, target_speed, elapsed_time, zone_time, cycle_time)
    else :
        current_speed = target_speed

    if abs(current_speed) - abs(target_speed) >= 0:
        elapsed_time = 0

    last_tar_speed = target_speed
    elapsed_time += cycle_time
    #core end

    times.append(table_time)
    speeds.append(current_speed)
    table_time += cycle_time
    time.sleep(cycle_time)

plt.figure(figsize=(10, 6))
plt.plot(times, speeds, label='Actual Speed', color='blue')
plt.plot(times, target_speeds, label='Target Speed', color='red',linestyle='--')

plt.xlabel('Time (s)')
plt.ylabel('Speed')
plt.title('Speed Ramp-up Over Time with Target Adjustments')
plt.legend()
plt.grid(True)
plt.show()
