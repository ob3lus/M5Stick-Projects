import os, sys, io
import M5
from M5 import *
import network
import time
import gc
wlan = None
labels = []
label_page = None
all_networks = []
current_page = 0
per_page = 6
was_pressed_a_last = False
last_scan_time = 0
SCAN_INTERVAL_MS = 15000
cursor_index = 0
was_pressed_b_last = False
btnB_press_start = None
btnB_confirmed_hold = False
HOLD_THRESHOLD_MS = 500
mode = 'list'
target_ssid = None
last_hunt_scan = 0
HUNT_SCAN_INTERVAL_MS = 500
hunt_indicator = None
hunt_outline = None
CIRCLE_CENTER_X = 150
CIRCLE_CENTER_Y = 65
MAX_RADIUS = 53
def setup():
    global wlan, labels, label_page
    M5.begin()
    Widgets.setRotation(3)
    Widgets.fillScreen(0x000000)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    for i in range(per_page):
        lbl = Widgets.Label('', 5, 5 + i * 18, 1.0, 0xFFFFFF, 0x000000, Widgets.FONTS.DejaVu12)
        labels.append(lbl)
    label_page = Widgets.Label('', 5, 5 + per_page * 18, 1.0, 0x888888, 0x000000, Widgets.FONTS.DejaVu12)
    BtnA.setCallback(type=BtnA.CB_TYPE.WAS_HOLD, cb=btnA_wasHold_event)
def btnA_wasHold_event(state):
    global current_page, cursor_index, mode, target_ssid
    if mode == 'hunt':
        exit_hunt()
    else:
        current_page = 0
        cursor_index = 0
        redraw_list()
def rescan():
    global all_networks
    networks = wlan.scan()
    all_networks = [n for n in networks if n[0].decode('utf-8', 'ignore') != '']
    gc.collect()
def redraw_list():
    global current_page, cursor_index, all_networks
    total_pages = max(1, (len(all_networks) + per_page - 1) // per_page)
    if current_page >= total_pages:
        current_page = 0
    if cursor_index >= per_page:
        cursor_index = 0
    start = current_page * per_page
    page_items = all_networks[start:start + per_page]
    for i in range(per_page):
        if i < len(page_items):
            ssid = page_items[i][0].decode('utf-8', 'ignore')
            rssi = page_items[i][3]
            prefix = '>' if i == cursor_index else ' '
            text = prefix + ssid[:15] + ': ' + str(rssi)
            labels[i].setText(text)
            if i == cursor_index:
                labels[i].setColor(0xFFFFFF, 0x333333)
            else:
                labels[i].setColor(0xFFFFFF, 0x000000)
        else:
            labels[i].setText('')
            labels[i].setColor(0xFFFFFF, 0x000000)
    label_page.setText('Page ' + str(current_page + 1) + '/' + str(total_pages))
def enter_hunt(ssid):
    global mode, target_ssid, hunt_indicator, hunt_outline
    mode = 'hunt'
    target_ssid = ssid
    for lbl in labels:
        lbl.setText('')
        lbl.setColor(0xFFFFFF, 0x000000)
    label_page.setText('')
    labels[2].setText(target_ssid[:20])
    labels[3].setText('...')
    if hunt_outline is None:
        hunt_outline = Widgets.Circle(CIRCLE_CENTER_X, CIRCLE_CENTER_Y, MAX_RADIUS, 0xFFFFFF, 0x000000)
    else:
        hunt_outline.setVisible(True)
    if hunt_indicator is None:
        hunt_indicator = Widgets.Circle(CIRCLE_CENTER_X, CIRCLE_CENTER_Y, 8, 0x333333, 0x333333)
    else:
        hunt_indicator.setRadius(r=8)
        hunt_indicator.setColor(color=0x333333, fill_c=0x333333)
        hunt_indicator.setVisible(True)
def exit_hunt():
    global mode, target_ssid, hunt_indicator, hunt_outline, current_page, cursor_index
    mode = 'list'
    target_ssid = None
    current_page = 0
    cursor_index = 0
    if hunt_indicator is not None:
        hunt_indicator.setVisible(False)
    if hunt_outline is not None:
        hunt_outline.setVisible(False)
    redraw_list()
def rssi_to_radius_and_color(rssi):
    clamped = max(-90, min(-30, rssi))
    ratio = (clamped + 90) / 60.0
    radius = int(8 + ratio * 45)
    if ratio < 0.4:
        color = 0xFF0000
    elif ratio < 0.7:
        color = 0xFFFF00
    else:
        color = 0x00FF00
    return radius, color
def update_hunt():
    global target_ssid, hunt_indicator
    networks = wlan.scan()
    found = False
    for n in networks:
        ssid = n[0].decode('utf-8', 'ignore')
        if ssid == target_ssid:
            rssi = n[3]
            labels[3].setText(str(rssi) + ' dBm')
            radius, color = rssi_to_radius_and_color(rssi)
            hunt_indicator.setRadius(r=radius)
            hunt_indicator.setColor(color=color, fill_c=color)
            found = True
            break
    if not found:
        labels[3].setText('Out of range')
        hunt_indicator.setRadius(r=8)
        hunt_indicator.setColor(color=0x333333, fill_c=0x333333)
    gc.collect()
def loop():
    global was_pressed_a_last, current_page, last_scan_time
    global cursor_index, was_pressed_b_last
    global btnB_press_start, btnB_confirmed_hold
    global mode, last_hunt_scan
    M5.update()
    now = time.ticks_ms()
    is_pressed_a = BtnA.isPressed()
    if mode == 'list' and is_pressed_a and not was_pressed_a_last:
        current_page += 1
        cursor_index = 0
        redraw_list()
    was_pressed_a_last = is_pressed_a
    if mode == 'list':
        is_pressed_b = BtnB.isPressed()
        if is_pressed_b:
            if btnB_press_start is None:
                btnB_press_start = now
                btnB_confirmed_hold = False
            held_duration = time.ticks_diff(now, btnB_press_start)
            if held_duration >= HOLD_THRESHOLD_MS:
                if not btnB_confirmed_hold:
                    btnB_confirmed_hold = True
                    start = current_page * per_page
                    page_items = all_networks[start:start + per_page]
                    if cursor_index < len(page_items):
                        ssid = page_items[cursor_index][0].decode('utf-8', 'ignore')
                        enter_hunt(ssid)
        else:
            if was_pressed_b_last and not btnB_confirmed_hold:
                cursor_index += 1
                redraw_list()
            btnB_press_start = None
            btnB_confirmed_hold = False
        was_pressed_b_last = is_pressed_b
        if time.ticks_diff(now, last_scan_time) > SCAN_INTERVAL_MS:
            rescan()
            redraw_list()
            last_scan_time = now
    else:
        if time.ticks_diff(now, last_hunt_scan) > HUNT_SCAN_INTERVAL_MS:
            update_hunt()
            last_hunt_scan = now
    time.sleep_ms(50)
if __name__ == '__main__':
    setup()
    while True:
        loop()