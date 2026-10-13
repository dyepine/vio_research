"""Real ROS1 bag fixture: distinct receive/header stamps and a dropped right frame."""
import sys
import rosbag
import rospy
from sensor_msgs.msg import Image, Imu
from std_msgs.msg import Header
from geometry_msgs.msg import PoseStamped

with rosbag.Bag(sys.argv[1], 'w') as bag:
    for cam in (0,1):
        for i in range(3):
            if cam==1 and i==1:continue
            msg=Image(header=Header(stamp=rospy.Time(1,i*100000000),frame_id='camera'),
                      height=3,width=4,encoding='mono8',is_bigendian=0,step=4,data=bytes(range(12)))
            bag.write('/dalsa_gray/'+('left' if cam==0 else 'right')+'/image_raw',msg,rospy.Time(5,i*100000000))
    for i in range(4):
        msg=Imu(header=Header(stamp=rospy.Time((900000000+i*100000000)//1000000000,(900000000+i*100000000)%1000000000),frame_id='xsens'))
        msg.linear_acceleration.z=9.81
        bag.write('/imu/data',msg,rospy.Time(6,i*100000000))
