# -*-coding:utf-8-*-
#
# The CyberBrick Codebase License, see the file LICENSE for details.
#
# Copyright (c) 2025 MakerWorld
#

__all__ = ["Devices"]


class Devices:
    MOTOR_1 = 1
    MOTOR_2 = 2
    LED_1 = 3
    LED_2 = 4
    PWM_1 = 5
    PWM_2 = 6
    PWM_3 = 7
    PWM_4 = 8
    BUZZER_1 = 9
    BUZZER_2 = 10
    CODE_EXEC = 11

    _max_value = max(v for k, v in locals().items() if isinstance(v, int))

    _base_multiplier = 10 ** len(str(_max_value))

    @classmethod
    def get_base_multiplier(cls):
        return cls._base_multiplier


if __name__ == '__main__':
    print(Devices.get_base_multiplier())  # 14us
