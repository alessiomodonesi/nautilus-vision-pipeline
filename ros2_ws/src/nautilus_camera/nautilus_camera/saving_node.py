import os
import cv2
import rclpy

from datetime import datetime
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_srvs.srv import SetBool
from cv_bridge import CvBridge
from message_filters import Subscriber, ApproximateTimeSynchronizer


class SavingNode(Node):
    """Nodo di salvataggio immagini stereo su filesystem locale.

    - Sottoscrive i topic di camera_ros (raw).
    - Salva left/right come JPEG (o PNG) in una cartella configurabile.
    - Naming monotonicamente crescente (nessun RTC necessario).
    - Espone un ROS 2 Service per attivare/disattivare il salvataggio a runtime.
    """

    def __init__(self):
        super().__init__('saving_node')

        # parametri
        self.declare_parameter('enable_saving', True)
        self.declare_parameter('left_topic',  '/stereo/lx/camera/image_raw')
        self.declare_parameter('right_topic', '/stereo/rx/camera/image_raw')
        self.declare_parameter('save_directory', '/home/nautilus/nautilus_data')
        self.declare_parameter('save_left',  True)
        self.declare_parameter('save_right', True)
        self.declare_parameter('image_format', 'jpg')
        self.declare_parameter('jpeg_quality', 95)
        self.declare_parameter('filename_prefix', 'nautilus')
        self.declare_parameter('queue_size', 10)
        self.declare_parameter('flush_every_n', 1)
        self.declare_parameter('max_files_per_session', 0)
        self.declare_parameter('sync_slop_sec', 0.05)

        self.enable_saving = self.get_parameter('enable_saving').value
        self.save_dir      = os.path.expanduser(self.get_parameter('save_directory').value)
        self.save_left     = self.get_parameter('save_left').value
        self.save_right    = self.get_parameter('save_right').value
        self.image_format  = self.get_parameter('image_format').value.lower()
        self.jpeg_quality  = int(self.get_parameter('jpeg_quality').value)
        self.prefix        = self.get_parameter('filename_prefix').value
        self.flush_every_n = int(self.get_parameter('flush_every_n').value)
        self.max_files     = int(self.get_parameter('max_files_per_session').value)
        self.sync_slop     = float(self.get_parameter('sync_slop_sec').value)

        if self.image_format not in ('jpg', 'jpeg', 'png'):
            raise ValueError(f'image_format non supportato: {self.image_format}')

        # struttura cartelle: <save_dir>/<YYYYmmdd-HHMMSS_session>/
        # l'orario di sistema sul Pi senza RTC è approssimativo o può ripetersi;
        # preveniamo la sovrascrittura di sessioni aggiungendo un suffisso incrementale se la directory esiste già.
        base_session_id = datetime.now().strftime('%Y%m%d-%H%M%S_session')
        session_id = base_session_id
        session_dir = os.path.join(self.save_dir, session_id)
        counter = 1
        while os.path.exists(session_dir):
            session_id = f'{base_session_id}_{counter}'
            session_dir = os.path.join(self.save_dir, session_id)
            counter += 1

        self.session_dir = session_dir
        os.makedirs(self.session_dir, exist_ok=True)

        # stato
        self.bridge = CvBridge()
        self.frame_counter = 0
        self.saved_count   = 0

        # sottoscrizioni sincronizzate
        left_topic  = self.get_parameter('left_topic').value
        right_topic = self.get_parameter('right_topic').value
        qsize       = self.get_parameter('queue_size').value

        self.left_sub  = Subscriber(self, Image, left_topic)
        self.right_sub = Subscriber(self, Image, right_topic)
        self.ts = ApproximateTimeSynchronizer(
            [self.left_sub, self.right_sub], queue_size=qsize, slop=self.sync_slop
        )
        self.ts.registerCallback(self._on_stereo_pair)

        # ROS 2 Service: attiva/disattiva il salvataggio a runtime
        self.srv = self.create_service(
            SetBool, '~/set_saving', self._handle_set_saving
        )

        self.get_logger().info(
            f'SavingNode avviato | dir={self.session_dir} '
            f'| format={self.image_format} | saving={self.enable_saving}'
        )


    def _handle_set_saving(self, request, response):
        """Abilita/disabilita il salvataggio via `ros2 service call`."""
        self.enable_saving = bool(request.data)
        response.success = True
        response.message = f'saving set to {self.enable_saving}'
        self.get_logger().info(f'[SERVICE] {response.message}')
        return response


    def _on_stereo_pair(self, left_msg: Image, right_msg: Image):
        if not self.enable_saving:
            return

        if self.max_files > 0 and self.saved_count >= self.max_files:
            if self.saved_count == self.max_files:
                self.get_logger().warn(
                    f'Raggiunto max_files_per_session={self.max_files}, '
                    f'salvataggio in pausa.'
                )
                self.saved_count += 1  # per non rispammare il warning
            return

        self.frame_counter += 1
        idx = self.frame_counter

        try:
            if self.save_left:
                self._save_one(left_msg, idx, 'lx')
            if self.save_right:
                self._save_one(right_msg, idx, 'rx')
            self.saved_count += 1

            # flush/sync su disco per evitare corruzione file su spegnimenti improvvisi (reed switch)
            if self.flush_every_n > 0 and (self.saved_count % self.flush_every_n == 0):
                os.sync()
        except Exception as e:
            self.get_logger().error(f'Errore salvataggio frame {idx}: {e}')


    def _save_one(self, msg: Image, idx: int, side: str):
        # conversione ROS -> OpenCV in formato BGR8 (formato nativo atteso da cv2.imwrite)
        cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        filename = f'{self.prefix}_{side}_{idx:08d}.{self.image_format}'
        path = os.path.join(self.session_dir, filename)

        if self.image_format in ('jpg', 'jpeg'):
            params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            cv2.imwrite(path, cv_img, params)
        else:  # png
            cv2.imwrite(path, cv_img)

        # log throttled
        if idx % 50 == 0:
            self.get_logger().info(
                f'Salvati {idx} frame stereo in {self.session_dir}'
            )


def main(args=None):
    rclpy.init(args=args)
    node = SavingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
    