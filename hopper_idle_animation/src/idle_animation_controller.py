#!/usr/bin/env python

import random
import rospy

from random import randint
from hopper_msgs.msg import HopperMoveCommand
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist

IDLE_ANIMATIONS = [
    "bored_looking_around",
    "bored_stretch",
    "bored_lift_leg",
    "happy_spin",
    "happy_dance"
]


def move_towards(target, current, step=1):
    if abs(target-current) < step:
        return target, True
    else:
        if target > current:
            return current + step, False
        else:
            return current - step, False


class IdleAnimationController(object):

    breathing_variation = 0.001

    def __init__(self):
        super(IdleAnimationController, self).__init__()
        rospy.init_node("hopper_idle_animation")
        
        self.last_action_time = rospy.Time.now() + rospy.Duration(20)
        self.last_idle_action_time = rospy.Time.now()  + rospy.Duration(20)

        self.idle_timeout = rospy.Duration(randint(10, 15))
        self.idle_action_timeout = rospy.Duration(randint(5, 15))

        self.robot_height = 0.0
        self.current_breathing_offset = 0.0
        self.breathing_up = True
        
        self.animations_enabled = rospy.get_param("idle_enabled_startup", False)
        rospy.Subscriber("hopper/idle_animations/enabled", Bool, self.on_idle_animations_enabled, queue_size=10)
        rospy.Subscriber("hopper/move_command", HopperMoveCommand, self.on_move_command, queue_size=10)
        rospy.Subscriber("hopper/stance_translate", Twist, self.on_stance_message, queue_size=1)
        rospy.Subscriber("hopper_schedule_move", String, self.on_move_scheduled, queue_size=1)
        self.animation_publisher = rospy.Publisher("hopper_schedule_move", String, queue_size=5)
        self.translation_publisher = rospy.Publisher("hopper/stance_translate", Twist, queue_size=5)
        while not rospy.is_shutdown():
            self.idler_check()
            self.breathing_tick()
            rospy.sleep(0.002)

    def on_move_command(self, msg):
        moving = msg.direction.linear.x != 0 or \
            msg.direction.linear.y != 0 or \
            msg.direction.linear.z != 0 or \
            msg.direction.angular.x != 0 or \
            msg.direction.angular.y != 0 or \
            msg.direction.angular.z != 0
        if moving:
            self.last_action_time = rospy.Time.now()

    def on_stance_message(self, msg):
        if msg._connection_header["callerid"] == rospy.get_name():
            return
        self.last_action_time = rospy.Time.now()
        self.robot_height = msg.linear.z

    def on_move_scheduled(self, msg):
        self.last_idle_action_time = rospy.Time.now()

    def is_idle(self):
        now = rospy.Time.now()
        rospy.logdebug("Time since action:" + str((now - self.last_action_time).to_sec()))
        return now - self.last_action_time > self.idle_timeout and \
            now - self.last_idle_action_time > self.idle_action_timeout

    def on_idle_animations_enabled(self, msg):
        self.animations_enabled = msg.data

    def idler_check(self):
        if self.animations_enabled and self.is_idle():
            rospy.logdebug("Idle action executed")
            self.animation_publisher.publish(String(random.choice(IDLE_ANIMATIONS)))
            self.idle_action_timeout = rospy.Duration(randint(5, 15))
            self.last_idle_action_time = rospy.Time.now()

    def breathing_tick(self):
        if self.animations_enabled and self.is_idle():
            current_target = self.breathing_variation
            if not self.breathing_up:
                current_target = -current_target
            self.current_breathing_offset, done = move_towards(current_target, self.current_breathing_offset, 0.0001)
            if done:
                self.breathing_up = not self.breathing_up
            msg = Twist()
            msg.linear.z = self.robot_height + self.current_breathing_offset
            self.translation_publisher.publish(msg)


if __name__ == "__main__":
    IdleAnimationController()
