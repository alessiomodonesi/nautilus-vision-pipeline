#!/usr/bin/env python3
import rclpy
import cv2
import math
import numpy as np
import message_filters
import os

from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose
from cv_bridge import CvBridge

# logica e configurazione dal modulo 'detection'
from nautilus_perception.detection.core_detection import YoloDetector, SparseBlockMatcher
from nautilus_perception.detection.config import DEFAULT_MODEL, StereoConfig


class DetectionNode(Node):
    def __init__(self):
        super().__init__('detection_node')
        
        self.bridge = CvBridge()

        # dichiarazione dei parametri ROS 2 richiesti (soglie, modello, tipo di input)
        self.declare_parameter('model_path', DEFAULT_MODEL)
        self.declare_parameter('conf_threshold', 0.3)
        self.declare_parameter('input_type', 'raw') # 'raw' o 'enhanced'

        model_path = self.get_parameter('model_path').get_parameter_value().string_value
        conf = self.get_parameter('conf_threshold').get_parameter_value().double_value
        input_type = self.get_parameter('input_type').get_parameter_value().string_value

        self.get_logger().info(f"Inizializzazione YOLOv8 con modello: {model_path}")

        # inizializzazione detector e matcher stereo
        self.detector = YoloDetector(model_path=model_path, conf=conf, half_res=True)
        self.stereo_config = StereoConfig()
        self.matcher = SparseBlockMatcher(self.stereo_config)
        
        # matrici di calibrazione
        pkg_share = get_package_share_directory('nautilus_perception')
        calib_path = os.path.join(pkg_share, 'data', 'stereo_calib.npz')
        try:
            calib = np.load(calib_path)
            self.map1x, self.map1y = calib["map1x"], calib["map1y"]
            self.map2x, self.map2y = calib["map2x"], calib["map2y"]
            self.get_logger().info("Matrici di calibrazione caricate correttamente.")
        except Exception as e:
            self.get_logger().fatal(f"Errore nel caricamento di stereo_calib.npz: {e}")
            raise e

        # configurazione dinamica dei topic in base all'input (raw o enhanced)
        left_topic = f'/camera/left/image_{input_type}'
        right_topic = f'/camera/right/image_{input_type}'

        # sincronizzazione dei flussi stereo tramite message_filters
        self.left_sub = message_filters.Subscriber(self, Image, left_topic)
        self.right_sub = message_filters.Subscriber(self, Image, right_topic)
        
        self.ts = message_filters.ApproximateTimeSynchronizer(
            [self.left_sub, self.right_sub], 
            queue_size=10, 
            slop=0.1
        )
        self.ts.registerCallback(self.stereo_callback)

        # publisher per i target rilevati
        self.detection_pub = self.create_publisher(
            Detection2DArray,
            '/stereo_down/targets',
            10
        )
        
        self.get_logger().info(f"Nodo detection avviato. In ascolto su {left_topic} e {right_topic}")

    def stereo_callback(self, left_msg: Image, right_msg: Image):
        try:
            cv_left = self.bridge.imgmsg_to_cv2(left_msg, desired_encoding='bgr8')
            cv_right = self.bridge.imgmsg_to_cv2(right_msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"Errore nella conversione dell'immagine: {e}")
            return
        
        # applica la rettifica stereo (cruciale per l'epipolar geometry)
        cv_left = cv2.remap(cv_left, self.map1x, self.map1y, cv2.INTER_LINEAR)
        cv_right = cv2.remap(cv_right, self.map2x, self.map2y, cv2.INTER_LINEAR)

        # trova i bounding box sull'immagine sinistra (Detect-Then-Range)
        detections = self.detector.detect(cv_left)

        det_array_msg = Detection2DArray()
        det_array_msg.header = left_msg.header 

        if detections:
            # converti in scala di grigi per il matcher stereo per evitare ridondanze
            gray_l = cv2.cvtColor(cv_left, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(cv_right, cv2.COLOR_BGR2GRAY)

            for (x, y, w, h, conf) in detections:
                cx, cy = x + w // 2, y + h // 2

                # stima la distanza campionando il centro del bounding box
                dist = self.matcher.estimate_distance(gray_l, gray_r, cx, cy)

                # compila il messaggio ROS 2
                det = Detection2D()
                det.header = left_msg.header
                
                det.bbox.center.position.x = float(cx)
                det.bbox.center.position.y = float(cy)
                det.bbox.size_x = float(w)
                det.bbox.size_y = float(h)

                hyp = ObjectHypothesisWithPose()
                hyp.hypothesis.class_id = "target"
                hyp.hypothesis.score = float(conf)
                
                # distanza stimata (Z) nella posa 3D
                if dist > 0.0:
                    hyp.pose.pose.position.z = float(dist)

                det.results.append(hyp)
                det_array_msg.detections.append(det)

        # pubblica i risultati indipendentemente per notificare anche l'assenza di target
        self.detection_pub.publish(det_array_msg)

def main(args=None):
    rclpy.init(args=args)
    node = DetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Chiusura nodo di detection...")
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
    