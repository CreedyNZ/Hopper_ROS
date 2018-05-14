#!/usr/bin/env python

from __future__ import division
from threading import Thread
import math
import rospy
from geometry_msgs.msg import Twist, TransformStamped, PoseWithCovariance, TwistWithCovariance
from hopper_msgs.msg import ServoTelemetrics, HexapodTelemetrics, WalkingMode, HopperMoveCommand
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
import tf.transformations as transformations
import tf2_ros


from hexapod.hexapod_gait_engine import GaitEngine, MovementController, TripodGait
from hexapod.hexapod_ik_driver import IkDriver, Vector2, Vector3
from dynamixel.dynamixel_driver import DynamixelDriver, search_usb_2_ax_port


def create_empty_transform_stamped(parent_name, child_name):
    transform_stamped = TransformStamped()
    transform_stamped.header.frame_id = parent_name
    transform_stamped.child_frame_id = child_name
    quaternion_zero = transformations.quaternion_from_euler(0, 0, 0)
    transform_stamped.transform.rotation.x = quaternion_zero[0]
    transform_stamped.transform.rotation.y = quaternion_zero[1]
    transform_stamped.transform.rotation.z = quaternion_zero[2]
    transform_stamped.transform.rotation.w = quaternion_zero[3]
    return transform_stamped


def create_empty_odometry_msg(parent_frame_name, child_frame_name):
    odom = Odometry()
    odom.header.frame_id = parent_frame_name
    odom.child_frame_id = child_frame_name
    quaternion_zero = transformations.quaternion_from_euler(0, 0, 0)
    odom.pose.pose.orientation.x = quaternion_zero[0]
    odom.pose.pose.orientation.y = quaternion_zero[1]
    odom.pose.pose.orientation.z = quaternion_zero[2]
    odom.pose.pose.orientation.w = quaternion_zero[3]
    return odom


class SoundPlayer(object):
    def __init__(self, speech_publisher):
        super(SoundPlayer, self).__init__()
        self.publisher = speech_publisher

    def say(self, file_name):
        self.publisher.publish(file_name)


class MessagePublisher(Thread):
    def __init__(self):
        super(MessagePublisher, self).__init__()
        self._callbacks = []
        self._rate = rospy.Rate(30)
        self.start()

    def add_message_sender(self, callback):
        self._callbacks.append(callback)

    def run(self):
        while not rospy.is_shutdown():
            for callback in self._callbacks:
                callback()
            self._rate.sleep()


class JointStatePublisher(object):
    def __init__(self, publisher):
        super(JointStatePublisher, self).__init__()
        self._publisher = publisher
        self._last_message = JointState()

    def update_joint_states(self, joint_names, joint_positions):
        """
        :param joint_names: list of names of the joints
        :param joint_positions: positions of joints
        :return:
        """
        joint_state = JointState()
        joint_state.name = joint_names
        joint_state.position = joint_positions
        joint_state.velocity = []
        joint_state.effort = []
        self._last_message = joint_state

    def publish(self):
        self._last_message.header.stamp = rospy.Time.now()
        self._publisher.publish(self._last_message)


class OdomPublisher(object):
    def __init__(self, transform_broadcaster, odom_publisher, parent_link_name="odom", child_link_name="base_footprint", publish_to_tf=True):
        super(OdomPublisher, self).__init__()
        self._publish_to_tf = publish_to_tf
        self._transform_broadcaster = transform_broadcaster
        self._odom_publisher = odom_publisher
        self._parent_link_name = parent_link_name
        self._child_link_name = child_link_name
        # initialize default tf transform
        self._last_tf_odometry_message = create_empty_transform_stamped(self._parent_link_name, self._child_link_name)
        self.odometry_rotation = transformations.quaternion_from_euler(0, 0, 0)
        self.odometry_position = Vector2()
        # init odometry message
        self._last_odom_msg = create_empty_odometry_msg(self._parent_link_name, self._child_link_name)

    def update_translation(self, direction, rotation):
        """
        :type direction: Vector2
        :type rotation: float
        """
        new_rotation = transformations.quaternion_from_euler(0, 0, math.radians(rotation))
        self.odometry_rotation = transformations.quaternion_multiply(new_rotation, self.odometry_rotation)
        current_rotation = transformations.euler_from_quaternion(self.odometry_rotation)[2]
        self.odometry_position += direction.rotate_by_angle_rad(current_rotation)
        tf_message = create_empty_transform_stamped(self._parent_link_name, self._child_link_name)
        tf_message.transform.translation.x = self.odometry_position.x / 100
        tf_message.transform.translation.y = self.odometry_position.y / 100
        tf_message.transform.rotation.x = self.odometry_rotation[0]
        tf_message.transform.rotation.y = self.odometry_rotation[1]
        tf_message.transform.rotation.z = self.odometry_rotation[2]
        tf_message.transform.rotation.w = self.odometry_rotation[3]
        odom_message = create_empty_odometry_msg(self._parent_link_name, self._child_link_name)
        odom_message.pose.pose.position.x = self.odometry_position.x / 100
        odom_message.pose.pose.position.y = self.odometry_position.y / 100
        odom_message.pose.pose.orientation.x = self.odometry_rotation[0]
        odom_message.pose.pose.orientation.y = self.odometry_rotation[1]
        odom_message.pose.pose.orientation.z = self.odometry_rotation[2]
        odom_message.pose.pose.orientation.w = self.odometry_rotation[3]
        odom_message.twist.twist.linear.x = direction.x / 100
        odom_message.twist.twist.linear.y = direction.y / 100
        odom_message.twist.twist.angular.z = math.radians(rotation.y)
        self._last_tf_odometry_message = tf_message
        self._last_odom_msg = odom_message

    def publish(self):
        now = rospy.Time.now()
        self._last_tf_odometry_message.header.stamp = now
        self._last_odom_msg.header.stamp = now
        if self._publish_to_tf:
            self._transform_broadcaster.sendTransform(self._last_tf_odometry_message)
        self._odom_publisher.publish(self._last_odom_msg)


class HeightPublisher(object):
    def __init__(self, transform_broadcaster, parent_link_name="base_footprint", child_link_name="base_stabilized"):
        super(HeightPublisher, self).__init__()
        self._transform_broadcaster = transform_broadcaster
        self._parent_link_name = parent_link_name
        self._child_link_name = child_link_name
        # initialize default tf transform
        self._last_message = create_empty_transform_stamped(self._parent_link_name, self._child_link_name)

    def update_height(self, height):
        self._last_message.transform.translation.z = height / 100

    def publish(self):
        self._last_message.header.stamp = rospy.Time.now()
        self._transform_broadcaster.sendTransform(self._last_message)


class HexapodController(object):
    def __init__(self):
        super(HexapodController, self).__init__()
        rospy.init_node('hopper_controller')
        servo_driver = DynamixelDriver(search_usb_2_ax_port())
        self.join_state_publisher = rospy.Publisher('joint_states', JointState, queue_size=10)
        self.odometry_publisher = rospy.Publisher('robot_odom', Odometry, queue_size=10)
        # publisher for tf and joint states
        transform_broadcaster = tf2_ros.TransformBroadcaster()
        self._message_publisher = MessagePublisher()
        publish_odometry_to_tf = rospy.get_param("~publish_odometry_to_tf", True)
        transform_publisher = OdomPublisher(transform_broadcaster, self.odometry_publisher, publish_to_tf=publish_odometry_to_tf)
        height_publisher = HeightPublisher(transform_broadcaster)
        joint_state_publisher = JointStatePublisher(self.join_state_publisher)
        self._message_publisher.add_message_sender(transform_publisher.publish)
        self._message_publisher.add_message_sender(joint_state_publisher.publish)
        self._message_publisher.add_message_sender(height_publisher.publish)
        # build controller
        ik_driver = IkDriver(servo_driver, joint_state_publisher)
        tripod_gait = TripodGait(ik_driver, height_publisher)
        gait_engine = GaitEngine(tripod_gait, transform_publisher)
        self.speech_publisher = rospy.Publisher('hopper_play_sound', String, queue_size=5)
        self.sound_player = SoundPlayer(self.speech_publisher)
        self.controller = MovementController(gait_engine, self.sound_player)
        self.telemetrics_publisher = rospy.Publisher('hopper_telemetrics', HexapodTelemetrics, queue_size=5)
        rospy.Subscriber("hopper_move_command", Twist, self.update_direction)
        rospy.Subscriber("hopper/cmd_vel", Twist, self.on_nav_system_move_command)
        rospy.Subscriber("hopper/move_command", HopperMoveCommand, self.on_move_command)
        rospy.Subscriber("hopper_walking_mode", WalkingMode, self.set_walking_mode)
        rospy.Subscriber("hopper_stance_translate", Twist, self.update_pose)
        rospy.Subscriber("hopper_schedule_move", String, self.schedule_move)
        self.controller.subscribe_to_telemetrics(self.publish_telemetrics_data)

    def on_move_command(self, move_command):
        # convert directions from meter to cm
        direction = Vector2(move_command.direction.linear.x, move_command.direction.linear.y) * 100
        rotation = move_command.direction.angular.x
        self.controller.set_move_command(direction,
                                         math.degrees(rotation),
                                         move_command.lift_height,
                                         move_command.static_speed_mode,
                                         move_command.turbo)

    def on_nav_system_move_command(self, move_command):
        # convert directions from meter to cm
        if abs(move_command.angular.z) > 0.17:
            move_command.angular.z = math.copysign(0.17, move_command.angular.z)
        if abs(move_command.linear.x) > 0.1:
            move_command.linear.x = math.copysign(0.1, move_command.linear.x)
        if abs(move_command.linear.y) > 0.1:
            move_command.linear.y = math.copysign(0.1, move_command.linear.y)
        direction = Vector2(move_command.linear.x, move_command.linear.y) * 100
        rotation = move_command.angular.z
        self.controller.set_move_command(direction,
                                         math.degrees(rotation),
                                         2,
                                         False,
                                         False)

    def set_walking_mode(self, walking_mode):
        static_speed_mode_enabled = walking_mode.selectedMode == WalkingMode.STATIC_SPEED
        self.controller.set_walking_mode(static_speed_mode_enabled, walking_mode.liftHeight)

    def update_direction(self, twist):
        direction = Vector2(twist.linear.x, twist.linear.y)
        rotation = twist.angular.x
        self.controller.set_direction(direction, rotation)

    def update_pose(self, twist):
        transform = Vector3(twist.linear.x, twist.linear.y, twist.linear.z)
        rotation = Vector3(twist.angular.x, twist.angular.y, twist.angular.z)
        self.controller.set_relaxed_pose(transform, rotation)

    def schedule_move(self, move_name):
        self.controller.schedule_move(move_name.data)

    def publish_telemetrics_data(self, telemetrics):
        msg = HexapodTelemetrics()
        msg.servos = []
        for id, voltage, temperature in telemetrics:
            tele = ServoTelemetrics()
            tele.id = id
            tele.temperature = temperature
            tele.voltage = voltage
            msg.servos.append(tele)
        self.telemetrics_publisher.publish(msg)

    def spin(self):
        rospy.spin()
        self.controller.stop()


if __name__ == '__main__':
    HexapodController().spin()
