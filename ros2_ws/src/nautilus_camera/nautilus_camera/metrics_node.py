import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import message_filters
import time
from collections import deque
import numpy as np

class MetricsNode(Node):
    def __init__(self):
        super().__init__('metrics_node')
        
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
        
        # variabili per jitter benchmark 
        self.latencies_left = deque(maxlen=30)
        self.last_stamp_left = None

    def sync_callback(self, left_msg, right_msg):
        current_time = time.perf_counter()
        self.frame_count += 1
        
        # calcolo skew temporale
        # misura la differenza assoluta di sincronizzazione tra i timestamp
        # della camera lx (t_left) e della camera rx (t_right)
        t_left = left_msg.header.stamp.sec + (left_msg.header.stamp.nanosec * 1e-9)
        t_right = right_msg.header.stamp.sec + (right_msg.header.stamp.nanosec * 1e-9)
        skew_ms = abs(t_left - t_right) * 1000.0
        
        # calcolo jitter (only lx)
        # misura la deviazione standard dei tempi di inter-arrivo (periodo)
        # tra frame consecutivi rispetto alla loro media
        if self.last_stamp_left is not None:
            delta_t = t_left - self.last_stamp_left
            self.latencies_left.append(delta_t)
        self.last_stamp_left = t_left
        jitter_ms = np.std(self.latencies_left) * 1000.0 if len(self.latencies_left) > 1 else 0.0
        
        # calcolo FPS
        # frequenza effettiva di ricezione/elaborazione calcolata su una finestra temporale
        elapsed = current_time - self.start_time
        if elapsed >= 1.0:
            fps = self.frame_count / elapsed
            self.get_logger().info(
                f"FPS: {fps:.1f} | Jitter (sx): {jitter_ms:.2f} ms | Skew (sx-dx): {skew_ms:.2f} ms"
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

if __name__ == '__main__':
    main()