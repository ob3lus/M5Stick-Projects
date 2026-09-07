import os, sys, io
import M5
from M5 import *
import network
import socket
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

btnA_press_start = None
btnA_confirmed_hold = False

ap = None
dns_sock = None
web_sock = None
ip_bytes_global = None
current_portal_ip = None
last_station_check = 0
STATION_CHECK_INTERVAL_MS = 1000

previous_station_macs = set()
connection_history = []
MAX_HISTORY_STORED = 20
ROWS_SHOWN = 6

portal_header = None
live_header = None
history_header = None
live_labels = []
history_labels = []
has_unread_message = False
unread_dot = None

MSG_CAP = 30
MSG_MAX_LEN = 60
messages_buffer = [None] * MSG_CAP
messages_write_idx = 0
messages_count = 0

in_messages_view = False
message_header = None
message_labels = []
MSG_ROWS_SHOWN = 8

LEFT_X = 5
RIGHT_X = 125
ROW_START_Y = 45
ROW_HEIGHT = 13
DOT_X = 225
DOT_Y = 10
DOT_RADIUS = 5

def url_decode(s):
    s = s.replace('+', ' ')
    result = ''
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                result += chr(int(s[i+1:i+3], 16))
                i += 3
                continue
            except Exception:
                pass
        result += s[i]
        i += 1
    return result

def add_message(msg_value):
    global messages_write_idx, messages_count
    msg_value = msg_value[:MSG_MAX_LEN]
    messages_buffer[messages_write_idx] = msg_value
    messages_write_idx = (messages_write_idx + 1) % MSG_CAP
    if messages_count < MSG_CAP:
        messages_count += 1

def get_message(index_from_newest):
    idx = (messages_write_idx - 1 - index_from_newest) % MSG_CAP
    return messages_buffer[idx]

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

def reset_list():
    global current_page, cursor_index
    current_page = 0
    cursor_index = 0
    redraw_list()

def rescan():
    global all_networks
    try:
        networks = wlan.scan()
        all_networks = [n for n in networks if n[0].decode('utf-8', 'ignore') != '']
    except Exception as e:
        print('rescan failed:', e)
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
    try:
        networks = wlan.scan()
    except Exception as e:
        print('hunt scan failed:', e)
        return
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

def handle_dns(sock, ip_bytes):
    if sock is None:
        return
    try:
        data, addr = sock.recvfrom(512)
    except OSError:
        return
    tid = data[0:2]
    response = tid + b'\x81\x80' + b'\x00\x01' + b'\x00\x01' + b'\x00\x00' + b'\x00\x00'
    idx = 12
    while data[idx] != 0:
        idx += data[idx] + 1
    idx += 5
    question = data[12:idx]
    answer = question + b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + ip_bytes
    sock.sendto(response + answer, addr)

HTML_FORM_PAGE = """<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { font-family: -apple-system, sans-serif; background: #111; color: #fff; margin: 0; padding: 24px 16px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; box-sizing: border-box; }
  h1 { font-size: 22px; text-align: center; margin-bottom: 24px; }
  form { width: 100%; max-width: 320px; display: flex; flex-direction: column; gap: 12px; }
  input[type=text] { font-size: 16px; padding: 14px; border-radius: 8px; border: 1px solid #444; background: #222; color: #fff; box-sizing: border-box; }
  button { font-size: 16px; padding: 14px; border-radius: 8px; border: none; background: #0af; color: #fff; font-weight: bold; }
  button:active { background: #08c; }
</style>
</head>
<body>
<h1>Send Me a Message</h1>
<form method="POST" action="/submit">
<input type="text" name="msg" placeholder="Type a message" maxlength="60">
<button type="submit">Send</button>
</form>
</body>
</html>"""

HTML_THANKS_PAGE = """<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { font-family: -apple-system, sans-serif; background: #111; color: #fff; margin: 0; padding: 24px 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; box-sizing: border-box; text-align: center; }
  h1 { font-size: 22px; }
  p { color: #aaa; font-size: 15px; }
</style>
</head>
<body>
<h1>Message sent!</h1>
<p>Thanks for reaching out.</p>
</body>
</html>"""

def send_response(conn, body_text):
    body_bytes = body_text.encode()
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html\r\n"
        "Content-Length: " + str(len(body_bytes)) + "\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    conn.sendall(header.encode())
    conn.sendall(body_bytes)

def mac_to_str(mac_bytes):
    return ':'.join('%02X' % b for b in mac_bytes)

def refresh_messages_view():
    for i in range(MSG_ROWS_SHOWN):
        if i < messages_count:
            msg = get_message(i)
            message_labels[i].setText(str(i + 1) + ': ' + msg[:28])
        else:
            message_labels[i].setText('')

def handle_request(conn, request_text):
    global has_unread_message

    first_line = request_text.split('\r\n')[0]

    if first_line.startswith('POST /submit'):
        body = request_text.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request_text else ''
        msg_value = ''
        for pair in body.split('&'):
            if pair.startswith('msg='):
                msg_value = url_decode(pair[4:])
                break

        if msg_value:
            add_message(msg_value)

            if in_messages_view:
                refresh_messages_view()
            else:
                has_unread_message = True
                if unread_dot is not None:
                    unread_dot.setColor(color=0x00FF00, fill_c=0x00FF00)

        send_response(conn, HTML_THANKS_PAGE)
    else:
        send_response(conn, HTML_FORM_PAGE)

    gc.collect()

def start_portal():
    global mode, wlan, ap, dns_sock, web_sock, ip_bytes_global, current_portal_ip
    global previous_station_macs, connection_history
    global portal_header, live_header, history_header, live_labels, history_labels
    global has_unread_message, unread_dot
    global messages_write_idx, messages_count

    wlan.active(False)
    time.sleep(1)

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid='Send Me a Message', authmode=network.AUTH_OPEN)
    ip = ap.ifconfig()[0]
    current_portal_ip = ip
    ip_bytes_global = bytes(int(x) for x in ip.split('.'))

    dns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dns_sock.bind(('0.0.0.0', 53))
    dns_sock.setblocking(False)

    web_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    web_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    web_sock.bind(('0.0.0.0', 80))
    web_sock.listen(5)
    web_sock.setblocking(False)

    previous_station_macs = set()
    connection_history = []
    messages_write_idx = 0
    messages_count = 0
    has_unread_message = False

    for lbl in labels:
        lbl.setText('')
    label_page.setText('')

    portal_header = Widgets.Label('Send Me a Message ' + ip, 5, 3, 1.0, 0xFFFFFF, 0x000000, Widgets.FONTS.DejaVu12)
    live_header = Widgets.Label('LIVE', LEFT_X, 22, 1.0, 0x00FF00, 0x000000, Widgets.FONTS.DejaVu12)
    history_header = Widgets.Label('HISTORY', RIGHT_X, 22, 1.0, 0xFFFF00, 0x000000, Widgets.FONTS.DejaVu12)

    live_labels = []
    history_labels = []
    for i in range(ROWS_SHOWN):
        y = ROW_START_Y + i * ROW_HEIGHT
        live_labels.append(Widgets.Label('', LEFT_X, y, 1.0, 0xFFFFFF, 0x000000, Widgets.FONTS.DejaVu9))
        history_labels.append(Widgets.Label('', RIGHT_X, y, 1.0, 0xAAAAAA, 0x000000, Widgets.FONTS.DejaVu9))

    if unread_dot is None:
        unread_dot = Widgets.Circle(DOT_X, DOT_Y, DOT_RADIUS, 0x333333, 0x333333)
    else:
        unread_dot.setColor(color=0x333333, fill_c=0x333333)
        unread_dot.setVisible(True)

    mode = 'portal'

def stop_portal():
    global mode, wlan, ap, dns_sock, web_sock, last_scan_time

    if dns_sock is not None:
        dns_sock.close()
        dns_sock = None
    if web_sock is not None:
        web_sock.close()
        web_sock = None
    if ap is not None:
        ap.active(False)
        ap = None

    time.sleep(1)

    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(2)

    if unread_dot is not None:
        unread_dot.setVisible(False)

    Widgets.fillScreen(0x000000)
    for lbl in labels:
        lbl.setText('')
    for i in range(per_page):
        lbl = Widgets.Label('', 5, 5 + i * 18, 1.0, 0xFFFFFF, 0x000000, Widgets.FONTS.DejaVu12)
        labels[i] = lbl

    mode = 'list'
    last_scan_time = time.ticks_ms()
    reset_list()
    gc.collect()

def check_stations():
    global previous_station_macs, connection_history

    try:
        stations = ap.status('stations')
    except Exception:
        stations = []

    current_macs = set()
    for entry in stations:
        mac_str = mac_to_str(entry[0])
        current_macs.add(mac_str)

    new_macs = current_macs - previous_station_macs

    for mac_str in new_macs:
        connection_history.insert(0, mac_str)

    if len(connection_history) > MAX_HISTORY_STORED:
        connection_history[:] = connection_history[:MAX_HISTORY_STORED]

    for i in range(ROWS_SHOWN):
        if i < len(current_macs):
            mac_str = list(current_macs)[i]
            live_labels[i].setText(mac_str)
        else:
            live_labels[i].setText('')

    for i in range(ROWS_SHOWN):
        if i < len(connection_history):
            history_labels[i].setText(connection_history[i])
        else:
            history_labels[i].setText('')

    previous_station_macs = current_macs

def enter_messages_view():
    global in_messages_view, message_header, message_labels, has_unread_message

    in_messages_view = True
    has_unread_message = False
    if unread_dot is not None:
        unread_dot.setColor(color=0x333333, fill_c=0x333333)

    portal_header.setText('')
    live_header.setText('')
    history_header.setText('')
    for lbl in live_labels:
        lbl.setText('')
    for lbl in history_labels:
        lbl.setText('')

    if message_header is None:
        message_header = Widgets.Label('MESSAGES', 5, 3, 1.0, 0xFFFF00, 0x000000, Widgets.FONTS.DejaVu12)
    else:
        message_header.setText('MESSAGES')

    if not message_labels:
        for i in range(MSG_ROWS_SHOWN):
            y = 25 + i * 13
            message_labels.append(Widgets.Label('', 5, y, 1.0, 0xFFFFFF, 0x000000, Widgets.FONTS.DejaVu9))

    refresh_messages_view()

def exit_messages_view():
    global in_messages_view

    in_messages_view = False

    message_header.setText('')
    for lbl in message_labels:
        lbl.setText('')

    portal_header.setText('Send Me a Message ' + current_portal_ip)
    live_header.setText('LIVE')
    history_header.setText('HISTORY')
    check_stations()

def loop():
    global was_pressed_a_last, current_page, last_scan_time
    global cursor_index, was_pressed_b_last
    global btnB_press_start, btnB_confirmed_hold
    global btnA_press_start, btnA_confirmed_hold
    global last_scan_time, last_hunt_scan, last_station_check

    M5.update()
    now = time.ticks_ms()

    is_pressed_a = BtnA.isPressed()
    is_pressed_b = BtnB.isPressed()

    if mode == 'list':
        if is_pressed_a:
            if btnA_press_start is None:
                btnA_press_start = now
                btnA_confirmed_hold = False
            held_duration = time.ticks_diff(now, btnA_press_start)
            if held_duration >= HOLD_THRESHOLD_MS and not btnA_confirmed_hold:
                btnA_confirmed_hold = True
                start_portal()
        else:
            if was_pressed_a_last and not btnA_confirmed_hold:
                current_page += 1
                cursor_index = 0
                redraw_list()
            btnA_press_start = None
            btnA_confirmed_hold = False
        was_pressed_a_last = is_pressed_a

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

    elif mode == 'hunt':
        if is_pressed_a:
            if btnA_press_start is None:
                btnA_press_start = now
            held_duration = time.ticks_diff(now, btnA_press_start)
            if held_duration >= HOLD_THRESHOLD_MS and not btnA_confirmed_hold:
                btnA_confirmed_hold = True
                exit_hunt()
        else:
            btnA_press_start = None
            btnA_confirmed_hold = False
        was_pressed_a_last = is_pressed_a

        if time.ticks_diff(now, last_hunt_scan) > HUNT_SCAN_INTERVAL_MS:
            update_hunt()
            last_hunt_scan = now

    elif mode == 'portal':
        if is_pressed_a and not was_pressed_a_last:
            if in_messages_view:
                exit_messages_view()
            else:
                enter_messages_view()
        was_pressed_a_last = is_pressed_a

        if is_pressed_b and not was_pressed_b_last:
            if not in_messages_view:
                stop_portal()
        was_pressed_b_last = is_pressed_b

        if mode == 'portal':
            handle_dns(dns_sock, ip_bytes_global)

            if not in_messages_view and time.ticks_diff(now, last_station_check) > STATION_CHECK_INTERVAL_MS:
                check_stations()
                last_station_check = now

            try:
                conn, addr = web_sock.accept()
                try:
                    request = conn.recv(2048).decode('utf-8', 'ignore')
                    handle_request(conn, request)
                except Exception as e:
                    print('Request error:', e)
                finally:
                    conn.close()
            except OSError:
                pass

    time.sleep_ms(50)

if __name__ == '__main__':
    setup()
    while True:
        loop()
