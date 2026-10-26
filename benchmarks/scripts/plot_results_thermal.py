#!/usr/bin/env python3
"""
Script per generare i grafici comparativi dai file benchmark *_thermal.csv di Nautilus Vision.
Supporta le configurazioni T_baseline, T_detection, T_full.
"""
import argparse
import glob
import os
import re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CONFIG_LABEL = {
    "T_baseline":  "T_baseline (Solo Camera)",
    "T_detection": "T_detection (Camera + YOLO)",
    "T_full":      "T_full (Pipeline Completa)",
}

CONFIG_COLOR = {
    "T_baseline":  "#4C72B0",
    "T_detection": "#DD8452",
    "T_full":      "#55A868",
}

def load_data(csv_dir):
    data = {}
    pattern = os.path.join(csv_dir, "*_thermal.csv")
    for filepath in sorted(glob.glob(pattern)):
        filename = Path(filepath).name
        m = re.search(r"_(T_[a-z]+)_run", filename)
        if m:
            cfg = m.group(1)
            data[cfg] = pd.read_csv(filepath)
    return data

def plot_soc_temp(data, out_dir):
    plt.figure(figsize=(10, 5))
    for cfg, df in data.items():
        plt.plot(df['t_elapsed_s'], df['temp_c'], label=CONFIG_LABEL.get(cfg, cfg), color=CONFIG_COLOR.get(cfg), alpha=0.8)
    plt.xlabel("Tempo [s]")
    plt.ylabel("Temperatura SoC [°C]")
    plt.title("Temperatura SoC nel tempo (Run 1 Ora)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "01_soc_temp.png", dpi=150)
    plt.close()

def plot_cpu_usage(data, out_dir):
    plt.figure(figsize=(10, 5))
    for cfg, df in data.items():
        smoothed = df['cpu_pct'].rolling(window=30, min_periods=1).mean()
        plt.plot(df['t_elapsed_s'], smoothed, label=CONFIG_LABEL.get(cfg, cfg), color=CONFIG_COLOR.get(cfg), alpha=0.8)
    plt.xlabel("Tempo [s]")
    plt.ylabel("Uso CPU [%]")
    plt.title("Uso CPU nel tempo (Media mobile 30s)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "02_cpu_usage.png", dpi=150)
    plt.close()

def plot_ram_usage(data, out_dir):
    plt.figure(figsize=(10, 5))
    for cfg, df in data.items():
        plt.plot(df['t_elapsed_s'], df['ram_pct'], label=CONFIG_LABEL.get(cfg, cfg), color=CONFIG_COLOR.get(cfg), alpha=0.8)
    plt.xlabel("Tempo [s]")
    plt.ylabel("Uso RAM [%]")
    plt.title("Uso RAM nel tempo")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "03_ram_usage.png", dpi=150)
    plt.close()

def plot_fps(data, out_dir):
    plt.figure(figsize=(10, 5))
    configs = list(data.keys())
    x = np.arange(len(configs))
    width = 0.25

    raw_fps = [data[cfg]['fps_/stereo/lx/camera/image_raw'].mean() for cfg in configs]
    enh_fps = [data[cfg]['fps_/stereo/lx/image_enhanced'].mean() if 'fps_/stereo/lx/image_enhanced' in data[cfg] else 0 for cfg in configs]
    tgt_fps = [data[cfg]['fps_/stereo_down/targets'].mean() if 'fps_/stereo_down/targets' in data[cfg] else 0 for cfg in configs]

    plt.bar(x - width, raw_fps, width, label='Camera Raw (LX)', color='#4C72B0')
    plt.bar(x, enh_fps, width, label='Enhanced (LX)', color='#F5B041')
    plt.bar(x + width, tgt_fps, width, label='Targets (Detection)', color='#55A868')

    for i in range(len(configs)):
        plt.text(i - width, raw_fps[i] + 0.1, f"{raw_fps[i]:.2f}", ha='center', fontsize=8)
        if enh_fps[i] > 0:
            plt.text(i, enh_fps[i] + 0.1, f"{enh_fps[i]:.2f}", ha='center', fontsize=8)
        if tgt_fps[i] > 0:
            plt.text(i + width, tgt_fps[i] + 0.1, f"{tgt_fps[i]:.2f}", ha='center', fontsize=8)

    plt.xticks(x, [CONFIG_LABEL.get(c, c) for c in configs], rotation=10)
    plt.ylabel("FPS Medi")
    plt.title("Throughput Effettivo (FPS)")
    plt.axhline(5.0, ls="--", c="gray", lw=1, label="Target Camera (5 FPS)")
    plt.grid(axis='y', alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "04_fps_comparison.png", dpi=150)
    plt.close()

def plot_stages_latency(data, out_dir):
    cfg_det = [c for c in data.keys() if (data[c]['infer_ms_mean'] > 0).any()]
    if not cfg_det:
        return
    plt.figure(figsize=(9, 5))
    x = np.arange(len(cfg_det))

    pre_means = [data[c][data[c]['pre_ms_mean'] > 0]['pre_ms_mean'].mean() for c in cfg_det]
    infer_means = [data[c][data[c]['infer_ms_mean'] > 0]['infer_ms_mean'].mean() for c in cfg_det]
    post_means = [data[c][data[c]['post_ms_mean'] > 0]['post_ms_mean'].mean() for c in cfg_det]

    plt.bar(x, pre_means, label='Pre-processing', color='#4C72B0')
    plt.bar(x, infer_means, bottom=pre_means, label='Inference (YOLO)', color='#DD8452')
    bottom_2 = np.array(pre_means) + np.array(infer_means)
    plt.bar(x, post_means, bottom=bottom_2, label='Post-processing', color='#55A868')

    for i in range(len(cfg_det)):
        tot = bottom_2[i] + post_means[i]
        plt.text(i, tot + 15, f"Tot: {tot:.1f} ms\n(Pre:{pre_means[i]:.0f}, Infer:{infer_means[i]:.0f}, Post:{post_means[i]:.0f})", 
                 ha='center', fontsize=8)

    plt.xticks(x, [CONFIG_LABEL.get(c, c) for c in cfg_det])
    plt.ylabel("Latenza Media [ms]")
    plt.title("Scomposizione Latenza per Stage (Pre / Inferenza / Post)")
    plt.grid(axis='y', alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "05_latency_stages.png", dpi=150)
    plt.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Directory dei file *_thermal.csv")
    parser.add_argument("--out", required=True, help="Directory dove salvare i grafici")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = load_data(args.csv)
    if not data:
        print("Nessun file *_thermal.csv trovato.")
        return

    plot_soc_temp(data, out_dir)
    plot_cpu_usage(data, out_dir)
    plot_ram_usage(data, out_dir)
    plot_fps(data, out_dir)
    plot_stages_latency(data, out_dir)
    print("Grafici generati con successo!")

if __name__ == "__main__":
    main()
    