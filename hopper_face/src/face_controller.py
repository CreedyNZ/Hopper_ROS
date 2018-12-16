#!/usr/bin/env python

from __future__ import print_function

import serial
import random
import rospy

from colorsys import hsv_to_rgb
from time import sleep
from std_msgs.msg import String


RESET_MSG = 121
RESET_MSG_COUNT = 243
PIXEL_COUNT = 40

PIXELS_ON_BIGGER_RING = 24
PIXELS_ON_SMALLER_RING = 16

BIGGER_TOP_INDEX = 7
BIGGER_BOTTOM_INDEX = 19
SMALLER_TOP_INDEX = 35
SMALLER_BOTTOM_INDEX = 27


def map_linear(value, in_min, in_max, out_min, out_max):
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def clamp(value, a, b):
    min_value = min(a, b)
    max_value = max(a, b)
    return max(min(max_value, value), min_value)


class Color():
    def __init__(self, red=0, green=0, blue=0, name=None):
        self.red = red
        self.green = green
        self.blue = blue
        if name is not None:
            web_color = webcolors.name_to_rgb(name)
            self.red = web_color.red
            self.green = web_color.green
            self.blue = web_color.blue

    def to_data(self):
        return [self.red, self.green, self.blue]


class ColorPacket():
    def __init__(self, from_color=None):
        if from_color is not None:
            self.data = from_color.to_data() * PIXEL_COUNT
        else:
            self.data = Color().to_data() * PIXEL_COUNT

    def set_pixel(self, index, color):
        self.data[index * 3] = color.red
        self.data[index * 3 + 1] = color.green
        self.data[index * 3 + 2] = color.blue

    def to_data(self):
        return bytearray(self.data)


def reset(port):
    payload = bytearray([RESET_MSG] * RESET_MSG_COUNT)
    port.write(payload)
    sleep(1)


def color_transitions(port, color_a, color_b, steps, delay):
    def get_transitioning_color(val_from, val_to, step, steps):
        val = map_linear(step, 0, steps, val_from, val_to)
        return clamp(int(round(val)), 0, 255)
    for step in range(steps):
        new_color = Color()
        new_color.red = get_transitioning_color(
            color_a.red, color_b.red, step, steps)
        new_color.green = get_transitioning_color(
            color_a.green, color_b.green, step, steps)
        new_color.blue = get_transitioning_color(
            color_a.blue, color_b.blue, step, steps)
        port.write(ColorPacket(new_color).to_data())
        sleep(delay)


def alternate_transitions(port, color_from, color_to, delay):
    current_color = Color(color_from.red, color_from.green, color_from.blue)
    while current_color.red < color_to.red or current_color.green < color_to.green or current_color.blue < color_to.blue:
        if current_color.red < color_to.red:
            current_color.red += 1
        if current_color.green < color_to.green:
            current_color.green += 1
        if current_color.blue < color_to.blue:
            current_color.blue += 1
        port.write(ColorPacket(current_color).to_data())
        sleep(delay)
    while current_color.red > color_to.red or current_color.green > color_to.green or current_color.blue > color_to.blue:
        if current_color.red > color_to.red:
            current_color.red -= 1
        if current_color.green > color_to.green:
            current_color.green -= 1
        if current_color.blue > color_to.blue:
            current_color.blue -= 1
        port.write(ColorPacket(current_color).to_data())
        sleep(delay)


def cycle(port, color_from, color_to, delay):
    pixel_data = ColorPacket(color_from)
    for pixel in range(PIXEL_COUNT):
        current_color = Color(
            color_from.red, color_from.green, color_from.blue)
        while current_color.red < color_to.red or current_color.green < color_to.green or current_color.blue < color_to.blue:
            if current_color.red < color_to.red:
                current_color.red += 1
            if current_color.green < color_to.green:
                current_color.green += 1
            if current_color.blue < color_to.blue:
                current_color.blue += 1
            pixel_data.set_pixel(pixel, current_color)
            port.write(pixel_data.to_data())
            sleep(delay)
        while current_color.red > color_to.red or current_color.green > color_to.green or current_color.blue > color_to.blue:
            if current_color.red > color_to.red:
                current_color.red -= 1
            if current_color.green > color_to.green:
                current_color.green -= 1
            if current_color.blue > color_to.blue:
                current_color.blue -= 1
            pixel_data.set_pixel(pixel, current_color)
            port.write(pixel_data.to_data())
            sleep(delay)


def breathing(port, color, delay):
    for i in range(15):
        new_color = Color()
        new_color.red = 0 if color.red == 0 else color.red + i
        new_color.green = 0 if color.green == 0 else color.green + i
        new_color.blue = 0 if color.blue == 0 else color.blue + i
        pixel_data = ColorPacket(new_color)
        port.write(pixel_data.to_data())
        sleep(delay)
    for i in reversed(range(15)):
        new_color = Color()
        new_color.red = 0 if color.red == 0 else color.red + i
        new_color.green = 0 if color.green == 0 else color.green + i
        new_color.blue = 0 if color.blue == 0 else color.blue + i
        pixel_data = ColorPacket(new_color)
        port.write(pixel_data.to_data())
        sleep(delay)


COLORS = {
    "red": Color(10, 0, 0),
    "blue": Color(0, 0, 10),
    "green": Color(0, 10, 0),
    "purple": Color(10, 10, 0)
}


class LedController(object):
    def __init__(self):
        super(LedController, self).__init__()
        rospy.init_node("face_controller")
        self.port = None
        self.selected_mode = "idle_1"
        self.selected_color = "red"
        self.modes = {
            "idel_1": self.idel_1,
            "idle_2": self.idle_2,
            "idle_3": self.idle_3,
            "breathing": self.breathing
        }
        rospy.Subscriber("hopper/face/mode", String,
                         self.on_mode_change, queue_size=3)
        self.main_loop()

    def on_mode_change(self, msg):
    new_mode = msg.data.lower()
    # special case for random
    if new_mode == "random":
        self.selected_color = random.choice(COLORS)
        self.selected_mode = random.choice(self.modes)
        return
    if ":" in new_mode:
        mode, color = new_mode.split(":")
        if color in COLORS:
            self.selected_color = color
        else:
            rospy.logwarn("Color: " + color + " unknown")
        new_mode = mode
    if new_mode in self.modes:
        self.selected_mode = new_mode
    else:
        rospy.logwarn("Mode: " + new_mode + " unknown")

    def main_loop(self):
        with serial.Serial('/dev/ttyUSB0', 115200) as port:
            reset(port)
            self.port = port
            while not rospy.is_shutdown():
                self.modes[self.selected_mode]()
                # set all off at the end
            port.write(ColorPacket().to_data())

    def idle_1(self):
        delay = 0.1
        red = COLORS["red"]
        blue = COLORS["blue"]
        green = COLORS["green"]
        alternate_transitions(self.port, red, blue, delay)
        alternate_transitions(self.port, blue, green, delay)
        alternate_transitions(self.port, green, red, delay)

    def idle_2(self):
        red = COLORS["red"]
        blue = COLORS["blue"]
        cycle(self.port, red, blue, 0.01)
        cycle(self.port, blue, red, 0.01)

    def idle_3(self):
        red = COLORS["red"]
        blue = COLORS["blue"]
        color_transitions(self.port, red, blue, 10, 0.1)
        color_transitions(self.port, blue, red, 10, 0.1)

    def breathing(self):
        breathing(port, COLORS[self.selected_color], 0.05)


if __name__ == "__main__":
    LedController()
