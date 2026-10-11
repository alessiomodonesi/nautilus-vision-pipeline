import os
import sys
import cv2
import numpy as np

# limitazione thread
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import message_filters
from rclpy.qos import qos_profile_sensor_data

BASE_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
sys.path.append(PACKAGE_DIR)

from nautilus_perception.detection.core_detection import YoloDetector, SparseBlockMatcher
from nautilus_perception.detection.config import StereoConfig

MODEL_PATH = os.path.join(BASE_DIR, 'data/weights/yolov8n.pt')
HALF_RES = True

# MODEL_PATH = os.path.join(BASE_DIR, 'data/weights/yolov8n_openvino_model')
# HALF_RES = False

CALIB_FILE = os.path.join(BASE_DIR, 'data/stereo_calib.npz')


class DistanceTesterNode(Node):
    def __init__(self):
        super().__init__('distance_tester_node')
        
        self.get_logger().info(f"Starting Distance Test | Model: {os.path.basename(MODEL_PATH)} | Half_Res: {HALF_RES}")
        
        self.bridge = CvBridge()
        self.config = StereoConfig()
        
        # inizializzazione detection & matcher
        self.detector = YoloDetector(model_path=MODEL_PATH, conf=0.3, half_res=HALF_RES)
        self.matcher = SparseBlockMatcher(self.config)
        
        # caricamento calibrazione stereo
        try:
            calib = np.load(CALIB_FILE)
            self.map1x, self.map1y = calib["map1x"], calib["map1y"]
            self.map2x, self.map2y = calib["map2x"], calib["map2y"]
            self.get_logger().info("Stereo calibration loaded successfully.")
        except Exception as e:
            self.get_logger().error(f"Failed to load calibration: {e}")
            sys.exit(1)

        # sottoscrizione sincronizzata ai topic con QoS per sensori
        self.sub_left = message_filters.Subscriber(
            self, Image, '/stereo/lx/camera/image_raw', qos_profile=qos_profile_sensor_data)
        self.sub_right = message_filters.Subscriber(
            self, Image, '/stereo/rx/camera/image_raw', qos_profile=qos_profile_sensor_data)
        
        # ApproximateTimeSynchronizer con slop aumentato a 0.2
        self.ts = message_filters.ApproximateTimeSynchronizer(
            [self.sub_left, self.sub_right], queue_size=10, slop=0.2)
        self.ts.registerCallback(self.sync_callback)
        
        self.get_logger().info("Waiting for synchronized stereo frames...")


    def sync_callback(self, msg_left, msg_right):
        try:
            # conversione da ROS image a OpenCV BGR
            frame_l = self.bridge.imgmsg_to_cv2(msg_left, desired_encoding='bgr8')
            frame_r = self.bridge.imgmsg_to_cv2(msg_right, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"CV Bridge error: {e}")
            return

        # rettifica stereo
        frame_l_rect = cv2.remap(frame_l, self.map1x, self.map1y, cv2.INTER_LINEAR)
        frame_r_rect = cv2.remap(frame_r, self.map2x, self.map2y, cv2.INTER_LINEAR)
        
        # inferenza YOLO / OpenVINO sull'immagine sinistra
        detections = self.detector.detect(frame_l_rect)
        
        # il Matcher richiede immagini in scala di grigi
        gray_l = cv2.cvtColor(frame_l_rect, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(frame_r_rect, cv2.COLOR_BGR2GRAY)
        
        # calcolo distanza per ogni target rilevato
        if not detections:
             self.get_logger().info("No targets detected.", throttle_duration_sec=2.0)
             
        for i, (x, y, w, h, conf) in enumerate(detections):
            cx, cy = x + w // 2, y + h // 2
            dist = self.matcher.estimate_distance(gray_l, gray_r, cx, cy)
            
            self.get_logger().info(
                f"Target {i} | Conf: {conf:.2f} | Box: [{x},{y},{w},{h}] | Center: ({cx},{cy}) | Z DISTANCE: {dist:.3f} m"
            )


def main(args=None):
    rclpy.init(args=args)
    tester_node = DistanceTesterNode()
    
    try:
        rclpy.spin(tester_node)
    except KeyboardInterrupt:
        pass
    finally:
        tester_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
            print("Test completed by user.")

if __name__ == "__main__":
    main()
    