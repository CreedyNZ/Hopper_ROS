from __future__ import absolute_import
import rospy
from hopper_msgs.msg import ServoTelemetry, HexapodTelemetry
from dynamixel import DynamixelDriver, search_usb_2_ax_port


class HexapodBodyController(object):
    def __init__(self):
        super(HexapodBodyController, self).__init__()
        self.telementrics_publisher = rospy.Publisher('hopper_telemetry', HexapodTelemetry, queue_size=5)
        self.servo_driver = DynamixelDriver(search_usb_2_ax_port())
        self.servo_ids = self.servo_driver.search_servos(0, 20)

    def set_compliance_movement_speed(self, servo_id, compliance, speed):
        self.servo_driver.set_compliance_slope(servo_id, compliance)
        self.servo_driver.set_moving_speed(servo_id, speed)

    def set_torque(self, servo_id, value):
        self.servo_driver.set_torque(servo_id, value)

    def set_motors(self, positions):
        self.servo_driver.group_sync_write_goal_degrees(positions)

    def read_motor_position(self, servo_id):
        return self.servo_driver.read_current_position_degrees(servo_id)
