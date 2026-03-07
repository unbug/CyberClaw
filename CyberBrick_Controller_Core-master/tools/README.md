# Tools
-------

## How to use
-------------

### HapticOpti_speed_curve.py

Installation environment dependency:

    $ pip install -r requirements.txt

Run the HapticOpti_stpeed_curve.py file, and you will see the curve of the input speed of the RC remote control stick.

    $ python ./HapticOpti_speed_curve.py

According to the parameters of Haptic Optimization, modify the _Acceleration, _Low_Speed_Zone, _Dead_Zone_Width in the source code， Re run to obtain custom curves.

### HapticOpti_time2speed_curve.py

Run the HapticOpti_stpeed_curve.py file, and you will see the motor's high-speed zone time mapped speed curve.

    $ python ./HapticOpti_time2speed_curve.py

Similarly to the above content, you can modify the values of _High_Speed_Zone and _High_Speed_Zone_Time based on the parameters in Haptic Optimization.
