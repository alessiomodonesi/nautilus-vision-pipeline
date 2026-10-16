#!/usr/bin/env python3
import rclpy
import cv2
import numpy as np
import message_filters
import os
import time

from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose
from cv_bridge import CvBridge
from rcl_interfaces.msg import ParameterDescriptor
from nautilus_perception.detection.config import StereoConfig
from std_msgs.msg import Float32MultiArray


def _to_bool(value):
    """Normalizza un parametro booleano che può arrivare come bool (yaml)
    oppure come stringa 'true'/'false'/'1'/'0' (launch argument)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(value)


class DetectionNode(Node):
    def __init__(self):
        super().__init__('detection_node')
        
        self.bridge = CvBridge()

        # dichiarazione di TUTTI i parametri con dynamic_typing:
        # - il yaml fornisce i default (tipizzati)
        # - i launch arg possono sovrascrivere per run specifiche (stringhe)
        # - la validazione "strict" (parametro mancante = errore fatale)
        #   viene applicata in modo uniforme, senza eccezioni.
        dyn_desc = ParameterDescriptor(dynamic_typing=True)
        self.declare_parameter('model_filename', descriptor=dyn_desc)
        self.declare_parameter('conf_threshold', descriptor=dyn_desc)
        self.declare_parameter('input_type', descriptor=dyn_desc)
        self.declare_parameter('enable_debug', descriptor=dyn_desc)
        self.declare_parameter('half_res', descriptor=dyn_desc)
        self.declare_parameter('imgsz', descriptor=dyn_desc)
        self.declare_parameter('num_threads', descriptor=dyn_desc)
        self.declare_parameter('sync_slop_sec', descriptor=dyn_desc)

        # lettura parametri dal file detection_params.yaml.
        # ogni parametro critico passa dalla stessa funzione di validazione
        model_filename = self._get_param_strict('model_filename')
        conf           = float(self._get_param_strict('conf_threshold'))
        input_type     = self._get_param_strict('input_type')
        self.enable_debug = _to_bool(self._get_param_strict('enable_debug'))
        half_res       = _to_bool(self._get_param_strict('half_res'))
        imgsz          = int(self._get_param_strict('imgsz'))
        num_threads    = int(self._get_param_strict('num_threads'))
        sync_slop      = float(self._get_param_strict('sync_slop_sec'))

        # imposta le variabili d'ambiente prima di importare il detector
        os.environ["OMP_NUM_THREADS"] = str(num_threads)
        os.environ["MKL_NUM_THREADS"] = str(num_threads)
        self.get_logger().info(f"Set OMP_NUM_THREADS and MKL_NUM_THREADS to {num_threads}")

        # importa il detector
        from nautilus_perception.detection.core_detection import YoloDetector, SparseBlockMatcher
        
        # costruisce il percorso dinamico
        pkg_share = get_package_share_directory('nautilus_perception')
        model_path = os.path.join(pkg_share, 'data', 'weights', model_filename)

        self.get_logger().info(f"Initializing YOLOv8 with model: {model_path}")
        self.get_logger().info(f"OpenCV visual debugging: {'ENABLED' if self.enable_debug else 'DISABLED'}")
        self.get_logger().info(f"Half resolution inference: {'ENABLED' if half_res else 'DISABLED'}")

        # inizializzazione del detector passando il percorso assoluto calcolato
        self.detector = YoloDetector(model_path=model_path, conf=conf, half_res=half_res, imgsz=imgsz)

        # inizializzazione matcher stereo
        self.stereo_config = StereoConfig()
        self.matcher = SparseBlockMatcher(self.stereo_config)
        
        # matrici di calibrazione
        calib_path = os.path.join(pkg_share, 'data', 'stereo_calib_720p.npz')
        try:
            calib = np.load(calib_path)
            self.map1x, self.map1y = calib["map1x"], calib["map1y"]
            self.map2x, self.map2y = calib["map2x"], calib["map2y"]
            self.get_logger().info("Calibration matrices loaded successfully.")
        except Exception as e:
            self.get_logger().fatal(f"Error loading stereo_calib_720p.npz: {e}")
            raise e

        # configurazione dinamica dei topic in base all'input (raw o enhanced)
        if input_type == 'raw':
            left_topic = '/stereo/lx/camera/image_raw'
            right_topic = '/stereo/rx/camera/image_raw'
        elif input_type == 'enhanced':
            left_topic = '/stereo/lx/image_enhanced'
            right_topic = '/stereo/rx/image_enhanced'
        else:
            self.get_logger().fatal(f"Unknown input_type: {input_type}")
            raise ValueError(f"Unknown input_type: {input_type}")

        # sincronizzazione dei flussi stereo tramite message_filters
        self.left_sub = message_filters.Subscriber(self, Image, left_topic)
        self.right_sub = message_filters.Subscriber(self, Image, right_topic)
        
        self.ts = message_filters.ApproximateTimeSynchronizer(
            [self.left_sub, self.right_sub], 
            queue_size=10, 
            slop=sync_slop
        )
        self.ts.registerCallback(self.stereo_callback)

        # publisher per i target rilevati
        self.detection_pub = self.create_publisher(
            Detection2DArray,
            '/stereo_down/targets',
            10
        )
        
        self.timing_pub = self.create_publisher(Float32MultiArray, '/stereo_down/timings', 10)
        self.get_logger().info(f"Detection node started. Listening on {left_topic} and {right_topic}")

    def _get_param_strict(self, name):
        """Legge un parametro e fallisce in modo esplicito se manca.

        usata per tutti i parametri critici, così il comportamento è
        uniforme: nessun default silenzioso che maschera errori di config.
        """
        param = self.get_parameter(name)
        if param.type_ == rclpy.Parameter.Type.NOT_SET:
            self.get_logger().fatal(f"CRITICAL: Parameter '{name}' is missing in the YAML file!")
            raise ValueError(f"Incomplete configuration: parameter '{name}' is missing.")
        return param.value

    def stereo_callback(self, left_msg: Image, right_msg: Image):
        t0 = time.perf_counter()

        # pre-processing
        try:
            cv_left = self.bridge.imgmsg_to_cv2(left_msg, desired_encoding='bgr8')
            cv_right = self.bridge.imgmsg_to_cv2(right_msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"Error in image conversion: {e}")
            return

        # applicazione della rettifica stereo, copia e forzatura a uint8
        cv_left = cv2.remap(cv_left, self.map1x, self.map1y, cv2.INTER_LINEAR).copy().astype(np.uint8)
        cv_right = cv2.remap(cv_right, self.map2x, self.map2y, cv2.INTER_LINEAR).copy().astype(np.uint8)
        t_pre = time.perf_counter()

        # inferenza
        # NB: YoloDetector.detect() include internamente letterbox + infer + NMS.
        # per una separazione più fine bisogna instrumentare core_detection.py.
        detections = self.detector.detect(cv_left)
        t_infer = time.perf_counter()

        # post-processing
        det_array_msg = Detection2DArray()
        det_array_msg.header = left_msg.header
        distances = []

        if detections:
            # converti in scala di grigi per il matcher stereo per evitare ridondanze
            gray_l = cv2.cvtColor(cv_left, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(cv_right, cv2.COLOR_BGR2GRAY)

            for idx, (x, y, w, h, conf) in enumerate(detections):
                cx, cy = x + w // 2, y + h // 2
                mx, my = max(1, w // 4), max(1, h // 4)
                points = [(cx, cy), (cx, y+my), (cx, y+h-my), (x+mx, cy), (x+w-mx, cy)]
                
                # stima la distanza campionando il centro del bounding box
                dists = [d for px, py in points
                         if (d := self.matcher.estimate_distance(gray_l, gray_r, px, py)) > 0.0]
                dist = float(np.median(dists)) if dists else 0.0
                distances.append(dist)

                # stampa il log pulito solo se ci sono rilevamenti effettivi
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
        t_post = time.perf_counter()

        # timings
        timings = Float32MultiArray()
        timings.data = [
            (t_pre   - t0)      * 1000.0,   # pre_ms
            (t_infer - t_pre)   * 1000.0,   # infer_ms
            (t_post  - t_infer) * 1000.0,   # post_ms
            (t_post  - t0)      * 1000.0,   # total_ms
        ]
        self.timing_pub.publish(timings)
    
    
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
    