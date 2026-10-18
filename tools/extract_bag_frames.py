#!/usr/bin/env python3
"""Estrae frame JPEG da una rosbag MCAP Nautilus (post-missione).

i CompressedImage in formato 'jpeg' contengono già un file JPEG completo:
lo script fa passthrough dei bytes, senza ricompressione.

non richiede ROS 2 installato: legge solo MCAP via mcap/mcap-ros2-support.

esempi:
  # bag singola, output in ./frames/
  ./extract_bag_frames.py ~/nautilus_bags/20261018_161956_smoke_test

  # bag rollata (più .mcap nella stessa dir), output custom
  ./extract_bag_frames.py ~/nautilus_bags/20261018_162051_stereo \\
      -o ~/frames/missione3

  # solo 1 frame ogni 10, range temporale
  ./extract_bag_frames.py <bag> --every 10 --start 16:21:00 --end 16:25:00
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from mcap.reader import make_reader
    from mcap_ros2.decoder import DecoderFactory
except ImportError:
    sys.exit(
        "Dipendenze mancanti. Installa con:\n"
        "  pip install mcap mcap-ros2-support"
    )


TOPIC_LX = "/stereo/lx/camera/image_raw/compressed"
TOPIC_RX = "/stereo/rx/camera/image_raw/compressed"
TOPIC_INFO_LX = "/stereo/lx/camera/camera_info"
TOPIC_INFO_RX = "/stereo/rx/camera/camera_info"


@dataclass
class Frame:
    log_time_ns: int    # timestamp di ricezione (monotono)
    stamp_ns: int       # header.stamp (timestamp di acquisizione)
    data: bytes | None  # None nel pass 1 (solo indici)
    side: str           # 'lx' | 'rx'


def _bag_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.mcap"))
    if not files:
        sys.exit(f"Nessun file .mcap in {path}")
    return files


def _iter_frames(mcap_files: list[Path], topics: set[str], want_data: bool):
    """Genera Frame per i topic richiesti, in ordine di log_time."""
    for mcap_path in mcap_files:
        with open(mcap_path, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, channel, message, ros_msg in reader.iter_decoded_messages(
                topics=list(topics), log_time_order=True
            ):
                side = "lx" if "lx" in channel.topic else "rx"
                stamp_ns = 0
                # header.stamp può essere zero se non popolato: fallback su log_time
                hdr = getattr(ros_msg, "header", None)
                if hdr is not None and getattr(hdr, "stamp", None) is not None:
                    stamp_ns = hdr.stamp.sec * 10**9 + hdr.stamp.nanosec
                if stamp_ns == 0:
                    stamp_ns = message.log_time

                yield Frame(
                    index=message.sequence if hasattr(message, "sequence") else -1,
                    log_time_ns=message.log_time,
                    stamp_ns=stamp_ns,
                    data=bytes(ros_msg.data) if want_data else None,
                    side=side,
                )


def _match_stereo(lx: list[Frame], rx: list[Frame], slop_ns: int):
    """Accoppia lx[i] con il frame rx più vicino in timestamp, entro slop_ns."""
    # due puntatori monotoni: entrambe le liste sono ordinate per log_time
    i = j = 0
    pairs = []
    unmatched_lx = unmatched_rx = 0
    while i < len(lx) and j < len(rx):
        dt = lx[i].log_time_ns - rx[j].log_time_ns
        if abs(dt) <= slop_ns:
            pairs.append((lx[i], rx[j]))
            i += 1
            j += 1
        elif dt < 0:  # lx più vecchio: rx non ha match
            unmatched_lx += 1
            i += 1
        else:         # rx più vecchio: lx non ha match
            unmatched_rx += 1
            j += 1
    unmatched_lx += len(lx) - i
    unmatched_rx += len(rx) - j
    return pairs, unmatched_lx, unmatched_rx


def _parse_time_arg(s: str | None) -> int | None:
    """Accetta 'HH:MM:SS' o 'HH:MM:SS.mmm' o interi Unix ns. None se non dato."""
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        pass
    # HH:MM:SS[.mmm]  ->  ns dall'inizio della giornata (approssimativo)
    parts = s.split(":")
    if len(parts) != 3:
        sys.exit(f"Formato tempo non valido: {s!r} (usa HH:MM:SS o ns Unix)")
    h, m, sec = parts
    sec_f = float(sec)
    return int((int(h) * 3600 + int(m) * 60 + sec_f) * 1e9)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Estrae frame da una rosbag MCAP Nautilus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("bag", type=Path, help="File .mcap o directory con .mcap")
    ap.add_argument("-o", "--out", type=Path, default=Path("frames"),
                    help="Directory di output (default: ./frames)")
    ap.add_argument("--prefix", default="nautilus",
                    help="Prefisso file (default: nautilus)")
    ap.add_argument("--every", type=int, default=1,
                    help="Estrai 1 frame ogni N (default: 1 = tutti)")
    ap.add_argument("--start", default=None,
                    help="Timestamp inizio (HH:MM:SS o ns Unix)")
    ap.add_argument("--end", default=None,
                    help="Timestamp fine (HH:MM:SS o ns Unix)")
    ap.add_argument("--sync-slop-ms", type=float, default=50.0,
                    help="Tolleranza sync stereo in ms (default: 50)")
    ap.add_argument("--no-sync", action="store_true",
                    help="Estrai lx e rx separatamente, senza accoppiare")
    ap.add_argument("--dump-camera-info", action="store_true",
                    help="Esporta anche camera_info (JSON, primo per lato)")
    # ap.add_argument("--jpeg-quality", type=int, default=None,
    #               help="Se dato, ricomprime i JPEG (default: passthrough)")
    args = ap.parse_args()

    if args.every < 1:
        sys.exit("--every deve essere >= 1")

    mcap_files = _bag_files(args.bag)
    print(f"Trovati {len(mcap_files)} file MCAP in {args.bag}")

    topics = {TOPIC_LX, TOPIC_RX}
    if args.dump_camera_info:
        topics |= {TOPIC_INFO_LX, TOPIC_INFO_RX}

    # pass 1: indici (veloce, niente data)
    lx_frames: list[Frame] = []
    rx_frames: list[Frame] = []
    cam_info_first = {"lx": None, "rx": None}
    for fr in _iter_frames(mcap_files, {TOPIC_LX, TOPIC_RX}, want_data=False):
        if fr.side == "lx":
            lx_frames.append(fr)
        else:
            rx_frames.append(fr)
    print(f"Frame trovati: lx={len(lx_frames)} rx={len(rx_frames)}")

    if args.dump_camera_info:
        for fr in _iter_frames(mcap_files, {TOPIC_INFO_LX, TOPIC_INFO_RX}, want_data=True):
            if cam_info_first[fr.side] is None:
                cam_info_first[fr.side] = fr
        # in realtà vogliamo il messaggio decodificato, non i bytes: piccolo workaround
        # lo rileggiamo sotto con un secondo giro specifico
        for mcap_path in mcap_files:
            with open(mcap_path, "rb") as f:
                reader = make_reader(f, decoder_factories=[DecoderFactory()])
                for schema, channel, message, ros_msg in reader.iter_decoded_messages(
                    topics=[TOPIC_INFO_LX, TOPIC_INFO_RX], log_time_order=True
                ):
                    side = "lx" if "lx" in channel.topic else "rx"
                    if cam_info_first[side] is None or cam_info_first[side].data is None:
                        cam_info_first[side] = type(
                            "Obj", (), {"ros_msg": ros_msg, "log_time_ns": message.log_time}
                        )()
            break  # basta il primo file

    # filtro temporale e ogni N
    def _in_range(fr: Frame) -> bool:
        t = fr.log_time_ns
        if args.start is not None and t < args.start:
            return False
        if args.end is not None and t > args.end:
            return False
        return True

    lx_frames = [f for f in lx_frames if _in_range(f)]
    rx_frames = [f for f in rx_frames if _in_range(f)]

    if args.no_sync:
        pairs = [(f, None) for f in lx_frames] + [(None, f) for f in rx_frames]
        unmatched_lx = unmatched_rx = 0
    else:
        slop_ns = int(args.sync_slop_ms * 1e6)
        pairs, unmatched_lx, unmatched_rx = _match_stereo(lx_frames, rx_frames, slop_ns)
        print(f"Coppie stereo: {len(pairs)} | lx orfani: {unmatched_lx} | rx orfani: {unmatched_rx}")

    # applica --every dopo il matching (così ogni N coppie complete)
    total_out = (len(pairs) + args.every - 1) // args.every
    print(f"Verranno estratti {total_out} frame per lato (every={args.every})")

    args.out.mkdir(parents=True, exist_ok=True)
    if args.dump_camera_info:
        for mcap_path in mcap_files:
            with open(mcap_path, "rb") as f:
                reader = make_reader(f, decoder_factories=[DecoderFactory()])
                for schema, channel, message, ros_msg in reader.iter_decoded_messages(
                    topics=[TOPIC_INFO_LX, TOPIC_INFO_RX], log_time_order=True
                ):
                    side = "lx" if "lx" in channel.topic else "rx"
                    if cam_info_first[side] is None:
                        cam_info_first[side] = type(
                            "Obj", (), {"ros_msg": ros_msg, "log_time_ns": message.log_time}
                        )()
            if all(v is not None for v in cam_info_first.values()):
                break

    # pass 2: leggi i bytes e scrivi
    # accumulo i dati in un dict temporaneo, poi scrivo nell'ordine delle coppie.
    # memoria: ~35 KB/frame * 2 lati * N frame nella finestra. con 10k coppie
    # (30 min a 5 FPS) sono ~700 MB: accettabile. per bag più grandi conviene
    # scrivere in streaming (vedi TODO in cima al file).
    wanted = set()
    for idx, (lx, rx) in enumerate(pairs):
        if idx % args.every != 0:
            continue
        if lx is not None:
            wanted.add((lx.log_time_ns, "lx"))
        if rx is not None:
            wanted.add((rx.log_time_ns, "rx"))

    data_map: dict[tuple[int, str], bytes] = {}
    for fr in _iter_frames(mcap_files, {TOPIC_LX, TOPIC_RX}, want_data=True):
        key = (fr.log_time_ns, fr.side)
        if key in wanted:
            data_map[key] = fr.data

    print(f"Letti {len(data_map)} frame da MCAP")

    # scrivi coppie
    counter = 0
    csv_path = args.out / "metadata.csv"
    with open(csv_path, "w", newline="") as csvf:
        writer = csv.writer(csvf)
        writer.writerow([
            "frame", "side", "filename",
            "log_time_ns", "stamp_ns",
        ])
        for idx, (lx, rx) in enumerate(pairs):
            if idx % args.every != 0:
                continue
            counter += 1
            for side, fr in (("lx", lx), ("rx", rx)):
                if fr is None:
                    continue
                data = data_map.get((fr.log_time_ns, side))
                if data is None:
                    continue
                fname = f"{args.prefix}_{side}_{counter:08d}.jpg"
                (args.out / fname).write_bytes(data)
                writer.writerow([
                    counter, side, fname,
                    fr.log_time_ns, fr.stamp_ns,
                ])
            if counter % 100 == 0 or counter == total_out:
                print(f"  scritti {counter}/{total_out}", end="\r", flush=True)

    print()
    print(f"Fatto: {counter} coppie in {args.out}")
    print(f"Metadati: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    