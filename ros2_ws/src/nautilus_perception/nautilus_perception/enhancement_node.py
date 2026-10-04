import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import time
import os
from ament_index_python.packages import get_package_share_directory

from nautilus_perception.enhancement.main import WaternetEnhancer

class EnhancementNode(Node):
    def __init__(self):
        super().__init__('enhancement_node')
        
        # recupero del percorso della cartella share definita nel setup.py
        pkg_share = get_package_share_directory('nautilus_perception')
        weights_file = os.path.join(pkg_share, 'enhancement', 'weights.pt')
        
        # inizializzazione della classe wrapper che contiene l'algoritmo
        self.enhancer = WaternetEnhancer(weights_path=weights_file)
        
        # utility per convertire i messaggi ROS in array NumPy per OpenCV
        self.bridge = CvBridge()
        
        # sottoscrizione al topic raw
        self.subscription = self.create_subscription(
            Image,
            'image_raw',
            self.image_callback,
            10
        )
        
        # publisher per l'immagine migliorata
        self.publisher = self.create_publisher(Image, 'image_enhanced', 10)
        
        # variabili per il calcolo di delay e FPS
        self.frame_count = 0
        self.start_time = time.perf_counter()

    def image_callback(self, msg):
        # inizio misurazione delay entrata-uscita
        t0 = time.perf_counter()
        
        # conversione da ROS Image a BGR OpenCV
        cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        
        # applicazione dell'algoritmo (WaterNet -> Laplacian -> CLAHE)
        enhanced_image = self.enhancer.enhance_image(cv_image)
        
        # conversione da OpenCV a ROS Image
        out_msg = self.bridge.cv2_to_imgmsg(enhanced_image, encoding='bgr8')
        
        # header originale per garantire la sincronizzazione dei timestamp nei nodi successivi
        out_msg.header = msg.header 
        
        # pubblicazione
        self.publisher.publish(out_msg)
        
        # fine misurazione delay entrata-uscita
        t1 = time.perf_counter()
        delay_ms = (t1 - t0) * 1000.0
        
        # calcolo FPS 
        self.frame_count += 1
        current_time = time.perf_counter()
        elapsed = current_time - self.start_time
        
        if elapsed >= 1.0:
            fps = self.frame_count / elapsed
            self.get_logger().info(
                f"FPS: {fps:.1f} | Delay entrata-uscita: {delay_ms:.2f} ms"
            )
            self.frame_count = 0
            self.start_time = current_time

def main(args=None):
    rclpy.init(args=args)
    node = EnhancementNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()