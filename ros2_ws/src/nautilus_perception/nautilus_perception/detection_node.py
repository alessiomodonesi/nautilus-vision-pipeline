#!/usr/bin/env python3
import rclpy
import cv2
import numpy as np
import message_filters
import os

from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose
from cv_bridge import CvBridge
from rcl_interfaces.msg import ParameterDescriptor

# logica e configurazione dal modulo 'detection'
from nautilus_perception.detection.core_detection import YoloDetector, SparseBlockMatcher
from nautilus_perception.detection.config import DEFAULT_MODEL, StereoConfig


class DetectionNode(Node):
    def __init__(self):
        super().__init__('detection_node')
        
        self.bridge = CvBridge()

        # dichiarazione dei parametri ROS 2 richiesti (soglie, modello, tipo di input)
        dyn_desc = ParameterDescriptor(dynamic_typing=True)
        self.declare_parameter('model_filename', descriptor=dyn_desc)
        self.declare_parameter('conf_threshold', descriptor=dyn_desc)
        self.declare_parameter('input_type', descriptor=dyn_desc)
        self.declare_parameter('enable_debug', descriptor=dyn_desc)
        self.declare_parameter('half_res', descriptor=dyn_desc)
        
        # utility function per estrarre e validare i parametri
        def get_param_strict(name):
            param = self.get_parameter(name)
            if param.type_ == rclpy.Parameter.Type.NOT_SET:
                self.get_logger().fatal(f"CRITICAL: Parameter '{name}' is missing in the YAML file!")
                raise ValueError(f"Incomplete configuration: parameter '{name}' is missing.")
            return param.value

        # lettura parametri dal file detection_params.yaml
        model_filename = get_param_strict('model_filename')
        conf = get_param_strict('conf_threshold')
        input_type = get_param_strict('input_type')
        self.enable_debug = get_param_strict('enable_debug')
        half_res = get_param_strict('half_res')

        # costruisce il percorso dinamico
        pkg_share = get_package_share_directory('nautilus_perception')
        model_path = os.path.join(pkg_share, 'data', 'weights', model_filename)

        self.get_logger().info(f"Initializing YOLOv8 with model: {model_path}")
        self.get_logger().info(f"OpenCV visual debugging: {'ENABLED' if self.enable_debug else 'DISABLED'}")
        self.get_logger().info(f"Half resolution inference: {'ENABLED' if half_res else 'DISABLED'}")

        # inizializzazione del detector passando il percorso assoluto calcolato
        self.detector = YoloDetector(model_path=model_path, conf=conf, half_res=half_res)

        # inizializzazione matcher stereo
        self.stereo_config = StereoConfig()
        self.matcher = SparseBlockMatcher(self.stereo_config)
        
        # matrici di calibrazione
        pkg_share = get_package_share_directory('nautilus_perception')
        calib_path = os.path.join(pkg_share, 'data', 'stereo_calib.npz')
        try:
            calib = np.load(calib_path)
            self.map1x, self.map1y = calib["map1x"], calib["map1y"]
            self.map2x, self.map2y = calib["map2x"], calib["map2y"]
            self.get_logger().info("Calibration matrices loaded successfully.")
        except Exception as e:
            self.get_logger().fatal(f"Error loading stereo_calib.npz: {e}")
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
            slop=0.2
        )
        self.ts.registerCallback(self.stereo_callback)

        # publisher per i target rilevati
        self.detection_pub = self.create_publisher(
            Detection2DArray,
            '/stereo_down/targets',
            10
        )
        
        self.get_logger().info(f"Detection node started. Listening on {left_topic} and {right_topic}")

    def stereo_callback(self, left_msg: Image, right_msg: Image):
        try:
            cv_left = self.bridge.imgmsg_to_cv2(left_msg, desired_encoding='bgr8')
            cv_right = self.bridge.imgmsg_to_cv2(right_msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"Error in image conversion: {e}")
            return
        
        # applicazione della rettifica stereo
        cv_left = cv2.remap(cv_left, self.map1x, self.map1y, cv2.INTER_LINEAR)
        cv_right = cv2.remap(cv_right, self.map2x, self.map2y, cv2.INTER_LINEAR)

        # forza la contiguità in RAM
        cv_left = np.ascontiguousarray(cv_left)
        cv_right = np.ascontiguousarray(cv_right)

        # rilevamento YOLO
        detections = self.detector.detect(cv_left)

        det_array_msg = Detection2DArray()
        det_array_msg.header = left_msg.header 

        distances = []
        if detections:
            # converti in scala di grigi per il matcher stereo per evitare ridondanze
            gray_l = cv2.cvtColor(cv_left, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(cv_right, cv2.COLOR_BGR2GRAY)

            for idx, (x, y, w, h, conf) in enumerate(detections):
                cx, cy = x + w // 2, y + h // 2

                # stima la distanza campionando il centro del bounding box
                dist = self.matcher.estimate_distance(gray_l, gray_r, cx, cy)
                distances.append(dist)

                # Stampa il log pulito solo se ci sono rilevamenti effettivi
                self.get_logger().info(
                    f"[TARGET DETECTED] Obj [{idx}] -> Box: x={x}, y={y}, w={w}, h={h} | Conf: {conf:.2f} | Distance (Z): {dist:.3f} m"
                )

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

        # chiamata esterna per il debug visivo
        if self.enable_debug:
            from nautilus_perception.detection.core_detection import draw_debug_window
            draw_debug_window(cv_left, detections, distances)

        # pubblicazione sul topic
        self.detection_pub.publish(det_array_msg)
        
def main(args=None):
    rclpy.init(args=args)
    node = DetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down detection node...")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
    