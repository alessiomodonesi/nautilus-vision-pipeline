#!/usr/bin/env python3
import sys
import rclpy
from rclpy.node import Node
from diagnostic_msgs.msg import DiagnosticArray

EXPECTED = {
    # hardware_id substring → (nome logico, LensPosition attesa)
    "0": ("lx", 2.6),   # adatta le chiavi in base agli ID reali
    "1": ("rx", 1.5),
}

class LensDiag(Node):
    def __init__(self):
        super().__init__('lens_diag')
        self.create_subscription(DiagnosticArray, '/diagnostics', self.cb, 10)
        self.seen = {}
    def cb(self, msg):
        for st in msg.status:
            for kv in st.values:
                if kv.key == 'LensPosition':
                    self.seen[st.hardware_id] = kv.value
        if len(self.seen) >= 2:
            self.report()
            rclpy.shutdown()
    def report(self):
        ok = True
        for hid, v in sorted(self.seen.items()):
            print(f"{hid}: LensPosition = {v}")
        # euristica: primo id → lx=2.6, secondo → rx=1.5
        vals = [float(v) for v in self.seen.values()]
        vals.sort()
        if len(vals) != 2 or abs(vals[0] - 1.5) > 1e-3 or abs(vals[1] - 2.6) > 1e-3:
            print("WARN: attesi 1.5 (rx) e 2.6 (lx) — trovati valori diversi")
            ok = False
        print("OK" if ok else "FAIL")
        sys.exit(0 if ok else 1)

def main():
    rclpy.init()
    n = LensDiag()
    try:
        rclpy.spin(n)
    except (KeyboardInterrupt, Exception):
        pass
    finally:
        if rclpy.ok():
            n.destroy_node()
            rclpy.shutdown()

if __name__ == "__main__":
    main()
