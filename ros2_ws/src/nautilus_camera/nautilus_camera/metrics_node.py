import time
import numpy as np
import rclpy
import message_filters
import cv2

from collections import deque
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


class MetricsNode(Node):
    """Nodo di benchmark: FPS reali, jitter e skew stereo.

    È un puro osservatore: non pubblica nulla, non scrive su disco.
    Può essere spento senza impattare la pipeline di acquisizione.
    """

    def __init__(self):
        super().__init__('metrics_node')

        # parametri
        self.declare_parameter('left_topic',  '/stereo/lx/camera/image_raw')
        self.declare_parameter('right_topic', '/stereo/rx/camera/image_raw')
        self.declare_parameter('sync_slop_sec', 0.05)
        self.declare_parameter('window_size', 30)
        self.declare_parameter('log_interval_sec', 1.0)
        self.declare_parameter('display', False)

        left_topic  = self.get_parameter('left_topic').value
        right_topic = self.get_parameter('right_topic').value
        slop        = self.get_parameter('sync_slop_sec').value
        window      = self.get_parameter('window_size').value
        self.log_interval = self.get_parameter('log_interval_sec').value
        self.display_enabled = self.get_parameter('display').value

        if self.display_enabled:
            self.bridge = CvBridge()

        # sottoscrizioni sincronizzate
        self.left_sub  = message_filters.Subscriber(self, Image, left_topic)
        self.right_sub = message_filters.Subscriber(self, Image, right_topic)
        self.ts = message_filters.ApproximateTimeSynchronizer(
            [self.left_sub, self.right_sub],
            queue_size=10,
            slop=slop,
        )
        self.ts.registerCallback(self.sync_callback)

        # stato per FPS
        self.frame_count = 0
        self.start_time  = time.perf_counter()
        self.current_fps = 0.0

        # stato per jitter/skew
        self.intervals_left  = deque(maxlen=window)
        self.skew_window_ms  = deque(maxlen=window)
        self.last_stamp_left = None

        self.get_logger().info(
            f'MetricsNode avviato | left={left_topic} right={right_topic} '
            f'| slop={slop*1000:.1f} ms | window={window}'
        )


    def sync_callback(self, left_msg: Image, right_msg: Image):
        now = time.perf_counter()
        self.frame_count += 1

        # timestamp dei messaggi (secondi float)
        t_left  = left_msg.header.stamp.sec  + left_msg.header.stamp.nanosec  * 1e-9
        t_right = right_msg.header.stamp.sec + right_msg.header.stamp.nanosec * 1e-9

        skew_ms = abs(t_left - t_right) * 1000.0
        self.skew_window_ms.append(skew_ms)

        # jitter = std degli intervalli tra frame consecutivi (sx)
        if self.last_stamp_left is not None:
            dt = t_left - self.last_stamp_left
            if dt > 0:
                self.intervals_left.append(dt)
        self.last_stamp_left = t_left

        jitter_ms = (np.std(self.intervals_left) * 1000.0
                     if len(self.intervals_left) > 1 else 0.0)
        skew_avg_ms = float(np.mean(self.skew_window_ms)) if self.skew_window_ms else 0.0
        skew_max_ms = float(np.max(self.skew_window_ms))  if self.skew_window_ms else 0.0

        # display opzionale
        if self.display_enabled:
            self._maybe_display(left_msg, right_msg, jitter_ms, skew_ms)

        # logging periodico
        elapsed = now - self.start_time
        if elapsed >= self.log_interval:
            self.current_fps = self.frame_count / elapsed
            self.get_logger().info(
                f'FPS: {self.current_fps:5.2f} | '
                f'Jitter(sx): {jitter_ms:6.2f} ms | '
                f'Skew(sx-dx): avg {skew_avg_ms:5.2f} / max {skew_max_ms:5.2f} ms'
            )
            self.frame_count = 0
            self.start_time  = now


    def _maybe_display(self, left_msg, right_msg, jitter_ms, skew_ms):
        try:
            cv_left  = self.bridge.imgmsg_to_cv2(left_msg,  desired_encoding='bgr8')
            cv_right = self.bridge.imgmsg_to_cv2(right_msg, desired_encoding='bgr8')
            cv_left  = cv2.resize(cv_left,  (640, 360))
            cv_right = cv2.resize(cv_right, (640, 360))

            cv2.putText(cv_left, f'FPS: {self.current_fps:4.1f}',
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(cv_left, f'Jitter: {jitter_ms:.2f} ms',
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(cv_left, f'Skew: {skew_ms:.2f} ms',
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            cv2.imshow('Stereo Camera View - Left | Right',
                       cv2.hconcat([cv_left, cv_right]))
            cv2.waitKey(1)
        except Exception as e:
            self.get_logger().error(f'Display error: {e}')


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
