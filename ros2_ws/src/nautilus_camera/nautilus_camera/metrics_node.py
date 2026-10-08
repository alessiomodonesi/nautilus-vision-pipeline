import rclpy
import message_filters
import cv2
import time
import numpy as np

from rclpy.node import Node
from sensor_msgs.msg import Image
from collections import deque
from cv_bridge import CvBridge


class MetricsNode(Node):
    def __init__(self):
        super().__init__('metrics_node')
        
        # parametro per la visualizzazione
        self.declare_parameter('display', False)
        self.display_enabled = self.get_parameter('display').get_parameter_value().bool_value
        
        # inizializzatore per convertire immagini ROS <-> OpenCV
        if self.display_enabled:
            self.bridge = CvBridge()
        
        # sottoscrizioni ai topic delle due fotocamere
        self.left_sub = message_filters.Subscriber(self, Image, '/stereo/lx/camera/image_raw')
        self.right_sub = message_filters.Subscriber(self, Image, '/stereo/rx/camera/image_raw')
        
        # filtro per sincronizzare i messaggi in base al timestamp
        # slop: tolleranza massima di skew temporale in secondi (es. 0.05 = 50 ms)
        self.ts = message_filters.ApproximateTimeSynchronizer([self.left_sub, self.right_sub], queue_size=10, slop=0.05)
        self.ts.registerCallback(self.sync_callback)
        
        # variabili per FPS benchmark 
        self.frame_count = 0
        self.start_time = time.perf_counter()
        self.current_fps = 0.0
        
        # variabili per jitter benchmark 
        self.latencies_left = deque(maxlen=30)
        self.last_stamp_left = None

    def sync_callback(self, left_msg, right_msg):
        current_time = time.perf_counter()
        self.frame_count += 1
        
        # calcolo skew temporale
        t_left = left_msg.header.stamp.sec + (left_msg.header.stamp.nanosec * 1e-9)
        t_right = right_msg.header.stamp.sec + (right_msg.header.stamp.nanosec * 1e-9)
        skew_ms = abs(t_left - t_right) * 1000.0
        
        # calcolo jitter (only lx)
        if self.last_stamp_left is not None:
            delta_t = t_left - self.last_stamp_left
            self.latencies_left.append(delta_t)
        self.last_stamp_left = t_left
        jitter_ms = np.std(self.latencies_left) * 1000.0 if len(self.latencies_left) > 1 else 0.0
        
        if self.display_enabled:
            try:
                # converte in OpenCV
                cv_left = self.bridge.imgmsg_to_cv2(left_msg, desired_encoding='bgr8')
                cv_right = self.bridge.imgmsg_to_cv2(right_msg, desired_encoding='bgr8')
                
                # ridimensionamento a 640x360
                cv_left_resized = cv2.resize(cv_left, (640, 360))
                cv_right_resized = cv2.resize(cv_right, (640, 360))
                
                # overlay delle metriche sull'immagine di sinistra
                cv2.putText(cv_left_resized, f"FPS: {self.current_fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(cv_left_resized, f"Jitter: {jitter_ms:.2f} ms", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(cv_left_resized, f"Skew: {skew_ms:.2f} ms", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                # affianca e mostra (sinistra | destra)
                stereo_view = cv2.hconcat([cv_left_resized, cv_right_resized])
                cv2.imshow("Stereo Camera View - Left | Right", stereo_view)
                cv2.waitKey(1)
            except Exception as e:
                self.get_logger().error(f"Display error: {e}")

        # calcolo FPS su intervallo di 1 secondo per il logging
        elapsed = current_time - self.start_time
        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.get_logger().info(
                f"FPS: {self.current_fps:.1f} | Jitter (sx): {jitter_ms:.2f} ms | Skew (sx-dx): {skew_ms:.2f} ms"
            )
            self.frame_count = 0
            self.start_time = current_time

def main(args=None):
    rclpy.init(args=args)
    node = MetricsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
