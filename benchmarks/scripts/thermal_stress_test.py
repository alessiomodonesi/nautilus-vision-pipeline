#!/usr/bin/env python3
"""Fase 7 — stress test termico.

Un CSV, una riga al secondo, con:
  - metriche di sistema (temp SoC, clock ARM, throttled, CPU%, RAM%)
  - FPS per ogni topic sottoscritto (raw lx/rx, enhanced lx/rx, targets)
  - jitter stereo calcolato dai header.stamp del raw sinistro
  - pre/infer/post medi per secondo da /stereo_down/timings

Il segnale più sensibile al throttling termico è infer_ms_mean: cresce
prima che clock_mhz scenda e prima che gli FPS di /stereo_down/targets
calino (il rate è limitato dal sync message_filters a 5 Hz).
"""
import argparse
import csv
import subprocess
import time
from collections import deque
from datetime import datetime

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray
from vision_msgs.msg import Detection2DArray
import psutil

try:
    from nautilus_common.qos_profiles import DEBUG_QOS
except ImportError:
    # fallback se il workspace non è sourced: best-effort, depth 10.
    # se il publisher usa RELIABLE il subscriber non riceve nulla:
    # in quel caso lanciare lo script dentro un ambiente ROS configurato.
    DEBUG_QOS = QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
    )

IMAGE_SUB_QOS_LOCAL = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

RAW_LEFT_TOPIC = '/stereo/lx/camera/image_raw'


# helpers vcgencmd
def vc(cmd):
    try:
        return subprocess.check_output(
            ['vcgencmd', cmd], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return ''


def temp_c():
    s = vc('measure_temp')
    return float(s.replace("temp=", "").replace("'C", "")) if s else float('nan')


def clock_mhz():
    s = vc('measure_clock arm')
    return int(s.split('=')[1]) // 1_000_000 if '=' in s else -1


def throttled():
    s = vc('get_throttled')
    return s.split('=')[1] if '=' in s else '0x0'


# nodo monitor
class ThermalMonitor(Node):
    def __init__(self, topics, out_csv, duration, timings_topic=''):
        super().__init__('thermal_monitor')
        self.out_csv = out_csv
        self.duration = duration
        self.timings_topic = timings_topic

        self.counts = {t: 0 for t in topics}
        self.last = self.start = time.time()

        # jitter (stessa formula di metrics_node, ma su tutti i frame raw sx)
        self.last_left_stamp = None
        self.intervals_left = deque(maxlen=30)

        # timing detection: aggregazione per-secondo
        self.pre_buf = deque(maxlen=200)
        self.infer_buf = deque(maxlen=200)
        self.post_buf = deque(maxlen=200)

        psutil.cpu_percent(interval=None)  # warmup, scarta il risultato
        
        for t in topics:
            if 'targets' in t:
                msg_t = Detection2DArray
            elif 'timings' in t:
                msg_t = Float32MultiArray
            else:
                msg_t = Image
            self.create_subscription(
                msg_t, t,
                lambda m, tt=t: self._on_msg(tt, m),
                IMAGE_SUB_QOS_LOCAL,
            )

        if timings_topic:
            self.create_subscription(
                Float32MultiArray, timings_topic,
                self._on_timings, DEBUG_QOS,
            )

        self.f = open(out_csv, 'w', newline='')
        self.w = csv.writer(self.f)
        header = [
            't_iso', 't_elapsed_s', 'temp_c', 'clock_mhz', 'throttled',
            'cpu_pct', 'ram_pct', 'jitter_ms',
            'pre_ms_mean', 'infer_ms_mean', 'post_ms_mean',
        ] + [f'fps_{t}' for t in topics]
        self.w.writerow(header)
        self.f.flush()

        self.create_timer(1.0, self._tick)
        self.get_logger().info(
            f'Logging to {out_csv} for {duration}s | '
            f'topics={topics} | timings={timings_topic or "none"}'
        )

    # callback
    def _on_msg(self, topic, msg):
        self.counts[topic] += 1
        if topic == RAW_LEFT_TOPIC:
            t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            if self.last_left_stamp is not None:
                dt = t - self.last_left_stamp
                if dt > 0:
                    self.intervals_left.append(dt)
            self.last_left_stamp = t

    def _on_timings(self, msg):
        # layout prodotto da detection_node: [pre_ms, infer_ms, post_ms, total_ms]
        if len(msg.data) >= 4:
            self.pre_buf.append(msg.data[0])
            self.infer_buf.append(msg.data[1])
            self.post_buf.append(msg.data[2])

    # tick periodico
    def _tick(self):
        now = time.time()
        dt = now - self.last
        if dt <= 0:
            return
        elapsed = now - self.start

        fps = {t: self.counts[t] / dt for t in self.counts}

        jitter_ms = (float(np.std(self.intervals_left) * 1000.0)
                     if len(self.intervals_left) > 1 else 0.0)
        pre_mean = float(np.mean(self.pre_buf)) if self.pre_buf else 0.0
        infer_mean = float(np.mean(self.infer_buf)) if self.infer_buf else 0.0
        post_mean = float(np.mean(self.post_buf)) if self.post_buf else 0.0

        row = [
            datetime.now().isoformat(timespec='seconds'),
            round(elapsed, 1),
            temp_c(),
            clock_mhz(),
            throttled(),
            psutil.cpu_percent(interval=None),
            psutil.virtual_memory().percent,
            round(jitter_ms, 2),
            round(pre_mean, 2),
            round(infer_mean, 2),
            round(post_mean, 2),
        ]
        row += [round(fps[t], 3) for t in self.counts]
        self.w.writerow(row)
        self.f.flush()

        # reset per-secondo
        self.counts = {t: 0 for t in self.counts}
        self.pre_buf.clear()
        self.infer_buf.clear()
        self.post_buf.clear()
        self.last = now

        if elapsed >= self.duration:
            self.get_logger().info('Duration reached, closing.')
            self.f.close()
            rclpy.shutdown()


# main
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--duration', type=int, default=3600,
                   help='Durata totale del log in secondi (default 3600).')
    p.add_argument('--out', required=True,
                   help='Path del CSV termico da scrivere.')
    p.add_argument('--timings-topic', default='',
                   help='Topic Float32MultiArray di detection_node '
                        '(vuoto per config senza detection).')
    p.add_argument('--topics', nargs='+', default=[
        '/stereo/lx/camera/image_raw',
        '/stereo/rx/camera/image_raw',
        '/stereo/lx/image_enhanced',
        '/stereo/rx/image_enhanced',
        '/stereo_down/targets',
    ], help='Topic di cui contare gli FPS.')
    a = p.parse_args()

    rclpy.init()
    node = ThermalMonitor(a.topics, a.out, a.duration, a.timings_topic)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if not node.f.closed:
            node.f.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
    