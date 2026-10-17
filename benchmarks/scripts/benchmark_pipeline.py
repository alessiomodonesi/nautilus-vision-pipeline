#!/usr/bin/env python3
"""Benchmark end-to-end pipeline Nautilus Vision."""
import argparse
import csv
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray
from std_msgs.msg import Float32MultiArray
from nautilus_common.qos_profiles import IMAGE_QOS, DETECTION_QOS, DEBUG_QOS


class TopicStats:
    def __init__(self, name):
        self.name = name
        self.latencies_ms = []
        self.arrivals = []

    def add(self, lat_ms, t_arrival):
        self.latencies_ms.append(lat_ms)
        self.arrivals.append(t_arrival)

    def summary(self):
        if not self.latencies_ms:
            return None
        arr = np.array(self.latencies_ms)
        dur = self.arrivals[-1] - self.arrivals[0] if len(self.arrivals) > 1 else 0
        fps = (len(self.arrivals) - 1) / dur if dur > 0 else 0.0
        return {
            "n": len(arr),
            "mean": float(np.mean(arr)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "fps": float(fps),
        }


class StageStats:
    def __init__(self):
        self.rows = []  # (pre, infer, post, total)

    def add(self, data):
        if len(data) >= 4:
            self.rows.append(tuple(float(x) for x in data[:4]))

    def summary(self):
        if not self.rows:
            return None
        a = np.array(self.rows)
        def _s(col):
            return {
                "mean": float(np.mean(col)),
                "p50":  float(np.percentile(col, 50)),
                "p95":  float(np.percentile(col, 95)),
            }
        return {
            "n":            len(self.rows),
            "pre":          _s(a[:, 0]),
            "infer":        _s(a[:, 1]),
            "post":         _s(a[:, 2]),
            "total":        _s(a[:, 3]),
        }
        

class Benchmark(Node):
    def __init__(self, raw, enhanced, targets, stages=None):
        super().__init__("benchmark_pipeline")
        self.stats = {}
        self.stages = None
        if raw:
            self.stats["raw"] = TopicStats(raw)
            self.create_subscription(Image, raw,
                lambda m: self._img("raw", m), IMAGE_QOS)
        if enhanced:
            self.stats["enhanced"] = TopicStats(enhanced)
            self.create_subscription(Image, enhanced,
                lambda m: self._img("enhanced", m), IMAGE_QOS)
        if targets:
            self.stats["targets"] = TopicStats(targets)
            self.create_subscription(Detection2DArray, targets,
                lambda m: self._tgt("targets", m), DETECTION_QOS)
        if stages:
            self.stages = StageStats()
            self.create_subscription(Float32MultiArray, stages,
                lambda m: self.stages.add(m.data), DEBUG_QOS)

    def _lat_ms(self, header):
        now = self.get_clock().now()
        stamp = rclpy.time.Time.from_msg(header.stamp)
        return (now - stamp).nanoseconds / 1e6

    def _img(self, key, msg):
        self.stats[key].add(self._lat_ms(msg.header), time.perf_counter())

    def _tgt(self, key, msg):
        self.stats[key].add(self._lat_ms(msg.header), time.perf_counter())

    def live(self):
        parts = []
        for k, s in self.stats.items():
            n = len(s.latencies_ms)
            parts.append(f"{k}=n{n}" +
                         (f"/{s.latencies_ms[-1]:.1f}ms" if n else ""))
        return " | ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--raw-topic", default="/stereo/lx/camera/image_raw")
    ap.add_argument("--enhanced-topic", default="/stereo/lx/image_enhanced")
    ap.add_argument("--targets-topic", default="/stereo_down/targets")
    ap.add_argument("--print-interval", type=float, default=2.0)
    ap.add_argument("--stages-topic", default="")
    ap.add_argument("--stages-out", default="")
    args = ap.parse_args()

    rclpy.init()
    node = Benchmark(args.raw_topic, args.enhanced_topic,
                 args.targets_topic, args.stages_topic or None)
    print(f"Duration: {args.duration}s")
    print(f"  raw:      {args.raw_topic}")
    print(f"  enhanced: {args.enhanced_topic}")
    print(f"  targets:  {args.targets_topic}\n")

    # timer per stampa live
    t0 = time.time()

    def print_live():
        dt = time.time() - t0
        print(f"[{dt:>6.1f}s] {node.live()}")

    def stop():
        print(f"\n[{time.time()-t0:>6.1f}s] Stopping...")
        raise KeyboardInterrupt

    node.create_timer(args.print_interval, print_live)
    node.create_timer(float(args.duration), stop)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[WARN] spin terminato con: {type(e).__name__}: {e}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summaries = {}
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "n", "mean_ms", "p50_ms", "p95_ms",
                    "min_ms", "max_ms", "fps"])
        for key in ["raw", "enhanced", "targets"]:
            if key not in node.stats:
                continue
            s = node.stats[key].summary()
            if s is None:
                continue
            summaries[key] = s
            w.writerow([key, s["n"],
                        f"{s['mean']:.3f}", f"{s['p50']:.3f}",
                        f"{s['p95']:.3f}", f"{s['min']:.3f}",
                        f"{s['max']:.3f}", f"{s['fps']:.3f}"])

    if node.stages and node.stages.summary():
        out = args.stages_out
        if not out:
            p = Path(args.out)
            out = str(p.with_name(p.stem.replace("_latency", "") + "_stages.csv"))
        s = node.stages.summary()
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["stage", "n", "mean_ms", "p50_ms", "p95_ms"])
            for k in ("pre", "infer", "post", "total"):
                v = s[k]
                w.writerow([k, s["n"],
                            f"{v['mean']:.3f}", f"{v['p50']:.3f}", f"{v['p95']:.3f}"])
        print(f"\nStage breakdown saved: {out}")
        
    print("\nSummary")
    for key, s in summaries.items():
        print(f"{key:>9s}: n={s['n']:>5d}  "
              f"mean={s['mean']:>7.1f}ms  "
              f"p50={s['p50']:>7.1f}ms  "
              f"p95={s['p95']:>7.1f}ms  "
              f"fps={s['fps']:.2f}")

    print("\nPer-stage (mean)")
    raw = summaries.get("raw", {}).get("mean")
    enh = summaries.get("enhanced", {}).get("mean")
    tgt = summaries.get("targets", {}).get("mean")
    if raw is not None:
        print(f"  driver raw:        {raw:>7.1f} ms")
    if enh is not None and raw is not None:
        print(f"  enhancement stage: {enh - raw:>7.1f} ms")
    if tgt is not None and enh is not None:
        print(f"  detection stage:   {tgt - enh:>7.1f} ms")
    elif tgt is not None and raw is not None:
        print(f"  detection stage:   {tgt - raw:>7.1f} ms")


    print(f"\nSaved: {out_path}")
    try:
        node.destroy_node()
    except Exception:
        pass
    if rclpy.ok():
        rclpy.shutdown()

if __name__ == "__main__":
    main()
    