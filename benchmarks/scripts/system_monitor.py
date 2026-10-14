#!/usr/bin/env python3
"""System monitor per benchmark Nautilus Vision (Raspberry Pi 5)."""
import argparse
import csv
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    print("ERROR: psutil not installed. Run: pip install psutil",
          file=sys.stderr)
    sys.exit(1)


def vcgencmd(args):
    try:
        out = subprocess.check_output(["vcgencmd"] + args.split(),
                                      stderr=subprocess.DEVNULL, timeout=2)
        return out.decode().strip()
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        return None


def parse_temp(s):
    try:    return float(s.split("=")[1].split("'")[0])
    except: return None


def parse_clock(s):
    try:    return int(s.split("=")[1])
    except: return None


def parse_throttled(s):
    try:    return s.split("=")[1]
    except: return None


class SystemMonitor:
    def __init__(self, out_path, interval=1.0, duration=None):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.duration = duration
        self.rows = []
        self.running = True
        self.t0 = None
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *a):
        self.running = False

    def sample(self):
        t = time.time()
        cpu = psutil.cpu_percent(interval=None)
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.virtual_memory()
        temp = parse_temp(vcgencmd("measure_temp"))
        clock = parse_clock(vcgencmd("measure_clock arm"))
        throttled = parse_throttled(vcgencmd("get_throttled"))
        return {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_s": round(t - self.t0, 3) if self.t0 else 0,
            "cpu_pct": round(cpu, 2),
            "cpu_per_core": ",".join(f"{c:.1f}" for c in per_cpu),
            "ram_used_mb": round((mem.total - mem.available) / 1024 / 1024, 1),
            "ram_total_mb": round(mem.total / 1024 / 1024, 1),
            "ram_pct": round(mem.percent, 2),
            "soc_temp_c": temp,
            "cpu_clock_mhz": round(clock / 1e6, 1) if clock else None,
            "throttled": throttled,
        }

    def run(self):
        # warmup
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self.t0 = time.time()
        print(f"System monitor: {self.out_path}")
        print(f"Interval: {self.interval}s  Duration: {self.duration}s\n")
        while self.running:
            row = self.sample()
            self.rows.append(row)
            print(f"[{row['elapsed_s']:>6.1f}s] "
                  f"CPU {row['cpu_pct']:>5.1f}%  "
                  f"RAM {row['ram_used_mb']:>6.1f}/{row['ram_total_mb']:.0f}MB  "
                  f"T {row['soc_temp_c']}°C  "
                  f"f {row['cpu_clock_mhz']}MHz  "
                  f"thr {row['throttled']}")
            if self.duration and (time.time() - self.t0) >= self.duration:
                break
            time.sleep(self.interval)
        self.write_csv()
        self.print_summary()

    def write_csv(self):
        if not self.rows:
            return
        with open(self.out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            w.writeheader()
            w.writerows(self.rows)
        print(f"\nWritten {len(self.rows)} samples to {self.out_path}")

    def print_summary(self):
        if not self.rows:
            return
        temps = [r["soc_temp_c"] for r in self.rows if r["soc_temp_c"] is not None]
        cpus = [r["cpu_pct"] for r in self.rows]
        rams = [r["ram_used_mb"] for r in self.rows]
        clocks = [r["cpu_clock_mhz"] for r in self.rows if r["cpu_clock_mhz"]]
        thr = sorted(set(r["throttled"] for r in self.rows))
        print("\nSummary")
        if temps:
            print(f"Temp:  min {min(temps):.1f}  max {max(temps):.1f}  "
                  f"mean {sum(temps)/len(temps):.1f} °C")
        if cpus:
            print(f"CPU:   min {min(cpus):.1f}  max {max(cpus):.1f}  "
                  f"mean {sum(cpus)/len(cpus):.1f} %")
        if rams:
            print(f"RAM:   min {min(rams):.1f}  max {max(rams):.1f}  "
                  f"mean {sum(rams)/len(rams):.1f} MB")
        if clocks:
            print(f"Clock: min {min(clocks):.0f}  max {max(clocks):.0f} MHz")
        print(f"Throttled flags: {thr}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=600)
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()
    SystemMonitor(args.out, args.interval, args.duration).run()


if __name__ == "__main__":
    main()
    