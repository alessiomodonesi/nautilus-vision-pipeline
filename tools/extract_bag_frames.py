#!/usr/bin/env python3
"""Estrae frame JPEG da una rosbag MCAP Nautilus (post-missione).

scopo: dopo una missione acquatica, convertire la bag MCAP registrata da
nautilus-bag.service in una cartella di file .jpg leggibili dai biologi
(più eventuale calibrazione stereo e CSV di metadata per il re-training).

perché è veloce: i messaggi CompressedImage in formato 'jpeg' contengono
già un file JPEG completo (bytes di un .jpg valido). Lo script fa
passthrough dei bytes, senza decodifica né ricompressione. Zero perdita
di qualità, zero CPU sprecata.

non richiede ROS 2 installato: legge solo MCAP via mcap/mcap-ros2-support,
quindi gira anche su un portatile senza ROS (laboratorio).

esempi:
  ./extract_bag_frames.py ~/nautilus_bags/20261018_161956_smoke_test
  ./extract_bag_frames.py ~/nautilus_bags/20261018_162051_stereo -o frames/
  ./extract_bag_frames.py <bag> --every 10 --copy-calibration stereo_calib_720p.npz
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
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


# topic della pipeline Nautilus (path assoluti, come in camera_params.yaml)
TOPIC_LX = "/stereo/lx/camera/image_raw/compressed"
TOPIC_RX = "/stereo/rx/camera/image_raw/compressed"
TOPIC_INFO_LX = "/stereo/lx/camera/camera_info"
TOPIC_INFO_RX = "/stereo/rx/camera/camera_info"


@dataclass
class Frame:
    """Metadati minimi di un frame. `data` è None nel pass 1 (solo indici)."""
    log_time_ns: int    # quando la bag ha ricevuto il messaggio (monotono)
    stamp_ns: int       # header.stamp (quando la camera ha acquisito; può
                        # essere 0 se il driver non lo popola, fallback su log_time)
    data: bytes | None  # contenuto JPEG (None nel pass 1)
    side: str           # 'lx' (sinistra) | 'rx' (destra)


def _bag_files(path: Path) -> list[Path]:
    """Accetta un singolo .mcap o una directory con più .mcap (bag rollata)."""
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.mcap"))
    if not files:
        sys.exit(f"Nessun file .mcap in {path}")
    return files


def _iter_frames(mcap_files, topics, want_data):
    """Genera Frame per i topic richiesti, in ordine di log_time.

    `want_data=False` (pass 1): non copia i bytes, solo metadati → veloce.
    `want_data=True`  (pass 2): copia i bytes → serve per scrivere i file.
    Questo split evita di tenere in RAM i bytes di tutta la bag in una volta.
    """
    for mcap_path in mcap_files:
        with open(mcap_path, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, channel, message, ros_msg in reader.iter_decoded_messages(
                topics=list(topics), log_time_order=True
            ):
                side = "lx" if "lx" in channel.topic else "rx"

                # header.stamp è il timestamp "vero" di acquisizione; se 0
                # (driver che non lo popola) uso log_time (ricezione bag).
                stamp_ns = 0
                hdr = getattr(ros_msg, "header", None)
                if hdr is not None and getattr(hdr, "stamp", None) is not None:
                    stamp_ns = hdr.stamp.sec * 10**9 + hdr.stamp.nanosec
                if stamp_ns == 0:
                    stamp_ns = message.log_time

                yield Frame(
                    log_time_ns=message.log_time,
                    stamp_ns=stamp_ns,
                    data=bytes(ros_msg.data) if want_data else None,
                    side=side,
                )


def _match_stereo(lx, rx, slop_ns):
    """Accoppia lx[i] con il frame rx più vicino in log_time, entro slop_ns.

    Le liste sono già ordinate per log_time (l'iteratore MCAP garantisce
    log_time_order=True), quindi bastano due puntatori monotoni: O(N).
    Non uso ApproximateTimeSynchronizer di ROS perché qui non c'è ROS.
    """
    i = j = 0
    pairs = []
    unmatched_lx = unmatched_rx = 0
    while i < len(lx) and j < len(rx):
        dt = lx[i].log_time_ns - rx[j].log_time_ns
        if abs(dt) <= slop_ns:
            # match entro tolleranza: consuma entrambi
            pairs.append((lx[i], rx[j]))
            i += 1
            j += 1
        elif dt < 0:
            # lx più vecchio di rx: rx non ha match per questo lx
            unmatched_lx += 1
            i += 1
        else:
            # rx più vecchio di lx: lx non ha match per questo rx
            unmatched_rx += 1
            j += 1
    # residui (uno dei due esaurito prima dell'altro)
    unmatched_lx += len(lx) - i
    unmatched_rx += len(rx) - j
    return pairs, unmatched_lx, unmatched_rx


def _read_first_camera_info(mcap_files):
    """Ritorna {'lx': CameraInfo|None, 'rx': CameraInfo|None} (primo per lato).

    Nota: se camera_ros non ha un file di calibrazione configurato, il
    messaggio esiste ma è "vuoto" (width=0, height=0, k=[]). Lo script
    lo segnala con un warning ma non è un errore fatale: la vera
    calibrazione stereo per il post-processing sta in stereo_calib_720p.npz,
    che si include con --copy-calibration.
    """
    result = {"lx": None, "rx": None}
    for mcap_path in mcap_files:
        with open(mcap_path, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, channel, message, ros_msg in reader.iter_decoded_messages(
                topics=[TOPIC_INFO_LX, TOPIC_INFO_RX], log_time_order=True
            ):
                side = "lx" if "lx" in channel.topic else "rx"
                if result[side] is None:
                    result[side] = ros_msg
        if all(v is not None for v in result.values()):
            break
    return result


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
    ap.add_argument("--sync-slop-ms", type=float, default=50.0,
                    help="Tolleranza sync stereo in ms (default: 50)")
    ap.add_argument("--no-sync", action="store_true",
                    help="Estrai lx e rx separatamente, senza accoppiare")
    ap.add_argument("--dump-camera-info", action="store_true",
                    help="Esporta anche camera_info (JSON, primo per lato; "
                         "può essere vuoto se camera_ros non ha calibrazione)")
    ap.add_argument("--copy-calibration", type=Path, default=None,
                    help="Copia il file di calibrazione stereo "
                         "(es. stereo_calib_720p.npz) nell'output")
    args = ap.parse_args()

    if args.every < 1:
        sys.exit("--every deve essere >= 1")

    mcap_files = _bag_files(args.bag)
    print(f"Trovati {len(mcap_files)} file MCAP in {args.bag}")

    # pass 1: solo metadati (nessun byte), per contare e accoppiare
    lx_frames, rx_frames = [], []
    for fr in _iter_frames(mcap_files, {TOPIC_LX, TOPIC_RX}, want_data=False):
        (lx_frames if fr.side == "lx" else rx_frames).append(fr)
    print(f"Frame trovati: lx={len(lx_frames)} rx={len(rx_frames)}")

    # camera_info: letto UNA volta sola, riusato sotto per stampa+JSON
    camera_info = {"lx": None, "rx": None}
    if args.dump_camera_info:
        camera_info = _read_first_camera_info(mcap_files)

    # matching stereo (o passthrough se --no-sync)
    if args.no_sync:
        pairs = [(f, None) for f in lx_frames] + [(None, f) for f in rx_frames]
        total_out = (len(pairs) + args.every - 1) // args.every
        print(f"Verranno estratti {total_out} frame totali (no-sync, every={args.every})")
    else:
        slop_ns = int(args.sync_slop_ms * 1e6)
        pairs, un_lx, un_rx = _match_stereo(lx_frames, rx_frames, slop_ns)
        total_out = (len(pairs) + args.every - 1) // args.every
        print(f"Coppie stereo: {len(pairs)} | lx orfani: {un_lx} | rx orfani: {un_rx}")
        print(f"Verranno estratti {total_out} frame per lato (every={args.every})")

    # output dir + calibrazione opzionale
    args.out.mkdir(parents=True, exist_ok=True)

    if args.copy_calibration is not None:
        if args.copy_calibration.is_file():
            dst = args.out / args.copy_calibration.name
            shutil.copy2(args.copy_calibration, dst)
            print(f"  calibrazione copiata: {dst}")
        else:
            print(f"  [warn] calibrazione non trovata: {args.copy_calibration}")

    # camera_info JSON (unico blocco, unica lettura)
    if args.dump_camera_info:
        ci_dir = args.out / "camera_info"
        ci_dir.mkdir(exist_ok=True)
        for side, info in camera_info.items():
            if info is None:
                print(f"  [warn] nessun camera_info per {side}")
                continue
            if info.width == 0 or info.height == 0:
                # camera_ros senza file di calibrazione: messaggio vuoto.
                # non scrivo JSON inutili, ma lo dico chiaramente.
                print(f"  [warn] camera_info {side} vuoto (0x0): "
                      f"camera_ros non ha un file di calibrazione. "
                      f"Usa --copy-calibration per includere stereo_calib_720p.npz.")
                continue
            print(f"  camera_info {side}: {info.width}x{info.height}")
            payload = {
                "header": {"stamp": {
                    "sec": info.header.stamp.sec,
                    "nanosec": info.header.stamp.nanosec,
                }},
                "width": info.width,
                "height": info.height,
                "distortion_model": info.distortion_model,
                "d": [float(x) for x in info.d],
                "k": [float(x) for x in info.k],
                "r": [float(x) for x in info.r],
                "p": [float(x) for x in info.p],
            }
            (ci_dir / f"{side}.json").write_text(json.dumps(payload, indent=2))
        print(f"  camera_info esportati in {ci_dir}")

    # pass 2: leggi i bytes solo dei frame che servono e scrivi
    # pre-calcolo le chiavi (log_time_ns, side) dei frame da estrarre: così
    # il secondo giro sulla bag scarta subito tutto ciò che non ci interessa
    # (utile con --every N su bag lunghe).
    wanted = set()
    for idx, (lx, rx) in enumerate(pairs):
        if idx % args.every != 0:
            continue
        if lx is not None:
            wanted.add((lx.log_time_ns, "lx"))
        if rx is not None:
            wanted.add((rx.log_time_ns, "rx"))

    data_map = {}
    for fr in _iter_frames(mcap_files, {TOPIC_LX, TOPIC_RX}, want_data=True):
        key = (fr.log_time_ns, fr.side)
        if key in wanted:
            data_map[key] = fr.data
    print(f"Letti {len(data_map)} frame da MCAP")

    # scrittura file .jpg + metadata.csv
    # metadata.csv ha due timestamp: log_time_ns (monotono, per riordinare)
    # e stamp_ns (acquisizione, può saltare se l'orologio si resetta).
    counter = 0
    csv_path = args.out / "metadata.csv"
    with open(csv_path, "w", newline="") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["frame", "side", "filename", "log_time_ns", "stamp_ns"])
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
                # Passthrough: `data` è già un JPEG completo (non ricomprimo).
                fname = f"{args.prefix}_{side}_{counter:08d}.jpg"
                (args.out / fname).write_bytes(data)
                writer.writerow([counter, side, fname, fr.log_time_ns, fr.stamp_ns])
            if counter % 100 == 0 or counter == total_out:
                print(f"  scritti {counter}/{total_out}", end="\r", flush=True)

    print()
    print(f"Fatto: {counter} coppie in {args.out}")
    print(f"Metadati: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
