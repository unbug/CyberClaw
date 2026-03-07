#!/usr/bin/env python
# coding=utf-8
#
# The CyberBrick Codebase License, see the file LICENSE for details.
#
# Copyright (c) 2025 MakerWorld
#

import numpy as np
import matplotlib.pyplot as plt

_Acceleration = 1.45
_Low_Speed_Zone = 60    # (%)
_Dead_Zone_Width = 200

def adc_value_deal(x, max=4096, mid= 2000, dz=200):
        def convert(x, i_min, i_max, o_min, o_max):
            return (x - i_min) * (o_max - o_min) / (i_max - i_min) + o_min

        if mid-dz <= x <= mid+dz:
            return 0

        m_mid = max / 2

        if x <= mid:
            x = convert(x, 0, mid-dz, -m_mid, 0)
        elif x > mid:
            x = convert(x, mid + dz, max, 0, m_mid)
        return x


def _low_speed_map(value, start, end, rate):
    if value <= start+1:
        return 0
    elif value >= end:
        return 2047

    mapped_value = rate*((value - start) ** 2) / (2 * (end - start))
    # mapped_value = rate * math.log(value - start) * (end - start)
    return int(mapped_value)


def nonlinear_map(set_speed, dead_zone=0, low_speed_percentage=0.3, linear_rate=1.18):
    THRESHOLD = 2047
    speed = abs(set_speed)
    if (speed) < dead_zone:
        return 0
    if speed > THRESHOLD:
        speed = THRESHOLD

    low_speed_threshold = dead_zone + (2048 - 2 * dead_zone) * low_speed_percentage

    tracker_speed = _low_speed_map(min(speed, low_speed_threshold - 1), dead_zone, low_speed_threshold, linear_rate)
    if speed >= low_speed_threshold:
        tracker_speed = tracker_speed + (speed - low_speed_threshold) * linear_rate

    tracker_speed = min(tracker_speed, THRESHOLD)
    return int(tracker_speed if set_speed >= 0 else -tracker_speed )


if 1:
    set_speeds = np.arange(-2047, 2048, 0.1)
    tracker_speeds = [nonlinear_map(speed, dead_zone=_Dead_Zone_Width, low_speed_percentage=_Low_Speed_Zone/100, linear_rate=_Acceleration) for speed in set_speeds]
else:
    set_speeds = np.arange(0, 4096, 0.1)
    tracker_speeds = [adc_value_deal(speed) for speed in set_speeds]


plt.figure(figsize=(10, 5))
plt.plot(set_speeds, tracker_speeds, label='Nonlinear Mapping')
plt.title('Nonlinear Mapping of Motor Speed')
plt.xlabel('Set Speed (motor1_set_speed)')
plt.ylabel('Tracker Speed (motor1_tracker_speed)')
plt.axhline(0, color='black',linewidth=0.5)
plt.axvline(0, color='black',linewidth=0.5)
plt.grid(color = 'gray', linestyle = '--', linewidth = 0.5)
plt.legend()
plt.show()
