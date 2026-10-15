#!/usr/bin/env python3
"""Genera grafici comparativi dai CSV di benchmark Nautilus Vision."""
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


LATENCY_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<config>[ABC])_(?P<name>[\w\-]+)"
    r"_run(?P<run>\d+)_latency\.csv$")
SYSTEM_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<config>[ABC])_(?P<name>[\w\-]+)"
    r"_run(?P<run>\d+)_system\.csv$")
MAP_RE = re.compile(r"^map_.*\.csv$")

CONFIG_LABEL = {"A": "A — solo acquisizione",
                "B": "B — acquisizione + detection",
                "C": "C — pipeline completa"}
CONFIG_COLOR = {"A": "#4C72B0", "B": "#DD8452", "C": "#55A868"}


def load_latency(path):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            out.append({
                "stage": r["stage"],
                "n": int(r["n"]),
                "mean": float(r["mean_ms"]),
                "p50": float(r["p50_ms"]),
                "p95": float(r["p95_ms"]),
                "fps": float(r["fps"]),
            })
    return out


def load_system(path):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            def _f(k):
                v = r.get(k, "")
                return float(v) if v not in ("", "None") else None
            out.append({
                "elapsed_s": _f("elapsed_s"),
                "cpu_pct": _f("cpu_pct"),
                "ram_used_mb": _f("ram_used_mb"),
                "ram_pct": _f("ram_pct"),
                "soc_temp_c": _f("soc_temp_c"),
            })
    return out


def scan(csv_dir):
    csv_dir = Path(csv_dir)
    lat = defaultdict(list)
    sys_ = defaultdict(list)
    maps = []
    for p in sorted(csv_dir.glob("*.csv")):
        m = LATENCY_RE.match(p.name)
        if m:
            lat[m["config"]].append((int(m["run"]), load_latency(p)))
            continue
        m = SYSTEM_RE.match(p.name)
        if m:
            sys_[m["config"]].append((int(m["run"]), load_system(p)))
            continue
        if MAP_RE.match(p.name):
            maps.append(p)
    return lat, sys_, maps


def plot_mean_latency(lat, out_dir):
    stages = ["raw", "enhanced", "targets"]
    configs = [c for c in "ABC" if c in lat]
    if not configs:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(stages))
    width = 0.8 / len(configs)
    for i, cfg in enumerate(configs):
        means, errs = [], []
        for st in stages:
            vals = [r["mean"] for _, rows in lat[cfg]
                    for r in rows if r["stage"] == st]
            means.append(np.mean(vals) if vals else 0)
            errs.append(np.std(vals) if len(vals) > 1 else 0)
        offset = (i - (len(configs) - 1) / 2) * width
        bars = ax.bar(x + offset, means, width, yerr=errs, capsize=4,
                      label=CONFIG_LABEL[cfg], color=CONFIG_COLOR[cfg])
        for b, v in zip(bars, means):
            if v > 0:
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f}",
                        ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(stages)
    ax.set_ylabel("Latenza media [ms]")
    ax.set_title("Latenza media per stage e configurazione (± std sui run)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = Path(out_dir) / "01_latency_mean_by_config.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  {out}")


def plot_p50_p95(lat, out_dir):
    stages = ["raw", "enhanced", "targets"]
    configs = [c for c in "ABC" if c in lat]
    if not configs:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, metric in zip(axes, ["p50", "p95"]):
        x = np.arange(len(stages))
        width = 0.8 / len(configs)
        for i, cfg in enumerate(configs):
            vals = []
            for st in stages:
                vs = [r[metric] for _, rows in lat[cfg]
                      for r in rows if r["stage"] == st]
                vals.append(np.mean(vs) if vs else 0)
            offset = (i - (len(configs) - 1) / 2) * width
            ax.bar(x + offset, vals, width, label=CONFIG_LABEL[cfg],
                   color=CONFIG_COLOR[cfg])
        ax.set_xticks(x)
        ax.set_xticklabels(stages)
        ax.set_title(metric.upper())
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("Latenza [ms]")
    axes[0].legend()
    fig.suptitle("Latenza p50 / p95 per stage e configurazione")
    fig.tight_layout()
    out = Path(out_dir) / "02_latency_p50_p95.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  {out}")


def plot_fps(lat, out_dir):
    configs = [c for c in "ABC" if c in lat]
    if not configs:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(configs))
    fps, err = [], []
    for cfg in configs:
        per_run = []
        for _, rows in lat[cfg]:
            stages = [r for r in rows if r["stage"] == "targets"] or \
                     [r for r in rows if r["stage"] == "raw"]
            if stages:
                per_run.append(stages[0]["fps"])
        fps.append(np.mean(per_run) if per_run else 0)
        err.append(np.std(per_run) if len(per_run) > 1 else 0)
    bars = ax.bar(x, fps, yerr=err, capsize=5,
                  color=[CONFIG_COLOR[c] for c in configs])
    for b, v in zip(bars, fps):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([CONFIG_LABEL[c] for c in configs], fontsize=8)
    ax.set_ylabel("FPS")
    ax.set_title("FPS medi per configurazione (output detection)")
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(5.0, ls="--", c="gray", lw=1, label="target 5 FPS")
    ax.legend()
    fig.tight_layout()
    out = Path(out_dir) / "03_fps_by_config.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  {out}")


def _time_series(sys_, out_dir, field, ylabel, title, out_name):
    configs = [c for c in "ABC" if c in sys_]
    if not configs:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    for cfg in configs:
        max_t = max((r["elapsed_s"] for _, rows in sys_[cfg]
                     for r in rows if r["elapsed_s"] is not None), default=0)
        if max_t == 0:
            continue
        grid = np.linspace(0, max_t, 300)
        interps = []
        for _, rows in sys_[cfg]:
            t = np.array([r["elapsed_s"] for r in rows
                          if r["elapsed_s"] is not None])
            v = np.array([r[field] if r[field] is not None else np.nan
                          for r in rows if r["elapsed_s"] is not None])
            if len(t) < 2:
                continue
            interps.append(np.interp(grid, t, v))
        if not interps:
            continue
        mean = np.nanmean(np.vstack(interps), axis=0)
        ax.plot(grid, mean, label=CONFIG_LABEL[cfg],
                color=CONFIG_COLOR[cfg])
    ax.set_xlabel("Tempo [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title + " (media sui run)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = Path(out_dir) / out_name
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  {out}")


def plot_map(maps, out_dir):
    if not maps:
        return
    tags, m50, m5095 = [], [], []
    for p in maps:
        with open(p) as f:
            for r in csv.DictReader(f):
                tags.append(r.get("tag", p.stem))
                m50.append(float(r["map50"]))
                m5095.append(float(r["map50_95"]))
    if not tags:
        return
    x = np.arange(len(tags))
    width = 0.4
    fig, ax = plt.subplots(figsize=(8, 5))
    b1 = ax.bar(x - width / 2, m50, width, label="mAP@0.5",
                color="#4C72B0")
    b2 = ax.bar(x + width / 2, m5095, width, label="mAP@0.5:0.95",
                color="#DD8452")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{b.get_height():.3f}", ha="center", va="bottom",
                    fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(tags, rotation=15, ha="right")
    ax.set_ylabel("mAP")
    ax.set_title("Accuratezza detection (validation set)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = Path(out_dir) / "07_map_comparison.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Cartella dei CSV")
    ap.add_argument("--out", required=True, help="Cartella dei plot")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lat, sys_, maps = scan(args.csv)
    print(f"Trovati: {sum(len(v) for v in lat.values())} latency, "
          f"{sum(len(v) for v in sys_.values())} system, "
          f"{len(maps)} map")
    print(f"Output in: {out_dir}\n")

    plot_mean_latency(lat, out_dir)
    plot_p50_p95(lat, out_dir)
    plot_fps(lat, out_dir)
    _time_series(sys_, out_dir, "soc_temp_c", "Temperatura SoC [°C]",
                 "Temperatura SoC nel tempo", "04_soc_temp.png")
    _time_series(sys_, out_dir, "cpu_pct", "CPU [%]",
                 "Uso CPU nel tempo", "05_cpu.png")
    _time_series(sys_, out_dir, "ram_used_mb", "RAM usata [MB]",
                 "RAM usata nel tempo", "06_ram.png")
    plot_map(maps, out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
    