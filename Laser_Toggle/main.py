import os, sys, io
import M5
from M5 import *
from unit import LaserTXUnit

laser_tx_0 = None
laser_state = False
was_pressed_last = False

def setup():
    global laser_tx_0
    M5.begin()
    Widgets.setRotation(0)
    Widgets.fillScreen(0x000000)
    laser_tx_0 = LaserTXUnit((10, 9), mode=1)

def loop():
    global laser_state, laser_tx_0, was_pressed_last
    M5.update()
    is_pressed_now = BtnA.isPressed()
    if is_pressed_now and not was_pressed_last:
        laser_state = not laser_state
        if laser_state:
            laser_tx_0.on()
        else:
            laser_tx_0.off()
    was_pressed_last = is_pressed_now

if __name__ == '__main__':
    setup()
    while True:
        loop()