#!/usr/bin/env python3
"""
capture_calibration_pairs.py  (ChArUco version)
=================================================
Capture synchronized ChArUco board image pairs from the two Pi Camera
Module 3s, for use with stereo_calibrate.py.

Run on the Raspberry Pi 5 itself (needs picamera2 + a display):

    DISPLAY=:0 python3 capture_calibration_pairs.py \\
        --squares-x 8 --squares-y 11 --square-length 0.015 --marker-length 0.011

(defaults already match calib_io_charuco_200x150_8x11_15_11_DICT_4X4.pdf —
adjust if you're using a different board)

Controls (window must be focused):
    SPACE / c   capture the current pair (works once enough shared corners
                are visible in BOTH images — status flashes green when ready)
    q / ESC     quit

Unlike a plain checkerboard, ChArUco doesn't need the WHOLE board visible
in both cameras — each corner has its own ID, so partial/angled views that
still share several corners between the two cameras are usable. Aim for
25-40 pairs, and make TILT VARIETY your top priority: several shots with
the board noticeably tilted left/right and up/down, not just moved around
while roughly facing the cameras. Weak tilt variety is the single most
common cause of a calibration that looks fine but gives wrong distances —
it under-constrains depth even when the reported reprojection error looks
OK-ish, so more pairs alone won't fix it.

Troubleshooting "board not seen":
- Bottom-left overlay shows live marker/corner counts per camera. If both
  read 0 consistently, --dict is almost certainly wrong for your board —
  try running with --auto-dict once to find the right one.
- If markers are found (>0) but charuco corners stay at 0, try
  --no-legacy-pattern (older/newer calib.io exports use different corner
  ID conventions).
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

from calibration.charuco_common import CharucoSetup, DICT_NAMES, require_aruco, detect_markers


def open_camera(camera_num, resolution, lens_position=None,
                lock_ae_awb=False, exposure_time=20000,
                analogue_gain=None, colour_gains=(1.5, 1.5)):
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise RuntimeError(
            "picamera2 is required for Pi Camera Module 3 support. "
            "Install with: sudo apt install -y python3-picamera2"
        ) from exc

    picam2 = Picamera2(camera_num=camera_num)
    cfg = picam2.create_video_configuration(main={"size": resolution, "format": "RGB888"})
    picam2.configure(cfg)
    picam2.start()
    time.sleep(1.0)   # lascia che AE/AWB convergano prima di (eventualmente) bloccarli

    controls = {}
    if lens_position is not None:
        controls["AfMode"] = 0                        # manual focus
        controls["LensPosition"] = float(lens_position)
    if lock_ae_awb:
        controls["AeEnable"] = False
        controls["AwbEnable"] = False
        controls["ExposureTime"] = int(exposure_time)
        controls["ColourGains"] = tuple(colour_gains)
        if analogue_gain is not None:
            controls["AnalogueGain"] = float(analogue_gain)

    if controls:
        picam2.set_controls(controls)
        time.sleep(0.5)
        print(f"Camera {camera_num}: controls applicati -> {controls}")
    return picam2


def auto_detect_dict(gray):
    """Try every DICT_4X4/5X5/6X6 size against one frame, report which
    finds the most markers. Handy one-off diagnostic when --dict is wrong."""
    require_aruco()
    best = (None, 0)
    for name in DICT_NAMES:
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))
        corners, ids, _ = detect_markers(gray, dictionary)
        n = 0 if ids is None else len(ids)
        print(f"  {name}: {n} markers detected")
        if n > best[1]:
            best = (name, n)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--left-cam", type=int, default=0)
    ap.add_argument("--right-cam", type=int, default=1)
    ap.add_argument("--squares-x", type=int, default=8)
    ap.add_argument("--squares-y", type=int, default=11)
    ap.add_argument("--square-length", type=float, default=0.015,
                     help="metres (calib.io filename '..._15_11_...' -> 0.015)")
    ap.add_argument("--marker-length", type=float, default=0.011,
                     help="metres (calib.io filename '..._15_11_...' -> 0.011)")
    ap.add_argument("--dict", default="DICT_4X4_50", choices=DICT_NAMES)
    ap.add_argument("--no-legacy-pattern", action="store_true",
                     help="Disable legacy ChArUco corner numbering (try this if "
                          "markers are detected but corners aren't)")
    ap.add_argument("--min-shared-corners", type=int, default=15,
                     help="Minimum charuco corners shared between L/R to allow capture")
    ap.add_argument("--outdir", default="calib_pairs")
    ap.add_argument("--auto-dict", action="store_true",
                     help="Test all dictionary sizes on the first frame and exit")
    ap.add_argument("--resolution", default="1280x720")
    ap.add_argument("--lens-left", type=float, default=3.0,
                    help="LensPosition per la camera sinistra (come in produzione)")
    ap.add_argument("--lens-right", type=float, default=1.0,
                    help="LensPosition per la camera destra (come in produzione)")
    ap.add_argument("--lock-ae-awb", action="store_true",
                    help="Blocca anche AE/AWB agli stessi valori della produzione")
    ap.add_argument("--exposure-time", type=int, default=20000,
                    help="Solo se --lock-ae-awb")
    ap.add_argument("--analogue-gain", type=float, default=None,
                    help="Solo se --lock-ae-awb (default: non impostato)")
    ap.add_argument("--colour-gains", type=float, nargs=2, default=[1.5, 1.5],
                    help="Solo se --lock-ae-awb")
    args = ap.parse_args()

    w, h = (int(x) for x in args.resolution.lower().split("x"))
    resolution = (w, h)

    print(f"Opening left=camera_num {args.left_cam}, right=camera_num {args.right_cam} "
          f"at {resolution} ...")
    try:
        cam_l = open_camera(args.left_cam, resolution,
                    lens_position=args.lens_left,
                    lock_ae_awb=args.lock_ae_awb,
                    exposure_time=args.exposure_time,
                    analogue_gain=args.analogue_gain,
                    colour_gains=tuple(args.colour_gains))
        cam_r = open_camera(args.right_cam, resolution,
                    lens_position=args.lens_right,
                    lock_ae_awb=args.lock_ae_awb,
                    exposure_time=args.exposure_time,
                    analogue_gain=args.analogue_gain,
                    colour_gains=tuple(args.colour_gains))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.auto_dict:
        frame = cam_l.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        print("Testing dictionaries against left camera frame:")
        name, n = auto_detect_dict(gray)
        print(f"\nBest match: {name} ({n} markers). Re-run with --dict {name}")
        cam_l.stop(); cam_r.stop()
        return

    setup = CharucoSetup(
        args.squares_x, args.squares_y, args.square_length, args.marker_length,
        dict_name=args.dict, legacy_pattern=not args.no_legacy_pattern,
    )

    os.makedirs(args.outdir, exist_ok=True)
    idx = len([f for f in os.listdir(args.outdir) if f.startswith("left_")])

    print(f"Board: {args.squares_x}x{args.squares_y} squares, dict={args.dict}, "
          f"legacy_pattern={not args.no_legacy_pattern}")
    print("Press SPACE/c to capture, q to quit.\n")

    while True:
        frame_l = cam_l.capture_array()
        frame_r = cam_r.capture_array()
        gray_l = cv2.cvtColor(frame_l, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(frame_r, cv2.COLOR_BGR2GRAY)

        corners_l, ids_l, markers_l = setup.detect(gray_l)
        corners_r, ids_r, markers_r = setup.detect(gray_r)

        n_l = 0 if ids_l is None else len(ids_l)
        n_r = 0 if ids_r is None else len(ids_r)
        shared = 0
        if ids_l is not None and ids_r is not None:
            shared = len(set(ids_l.flatten()) & set(ids_r.flatten()))

        ready = shared >= args.min_shared_corners

        disp_l, disp_r = frame_l.copy(), frame_r.copy()
        setup.draw(disp_l, corners_l, ids_l)
        setup.draw(disp_r, corners_r, ids_r)

        combined = np.hstack([disp_l, disp_r])
        color = (0, 255, 0) if ready else (0, 0, 255)
        cv2.putText(combined, "READY - press SPACE" if ready else "not enough shared corners",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(combined,
                    f"L: {markers_l} markers / {n_l} corners   "
                    f"R: {markers_r} markers / {n_r} corners   shared: {shared}",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.putText(combined, f"saved: {idx}", (10, combined.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.imshow("capture_calibration_pairs  (left | right)", combined)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        if key in (ord('c'), ord(' ')) and ready:
            lpath = os.path.join(args.outdir, f"left_{idx:03d}.png")
            rpath = os.path.join(args.outdir, f"right_{idx:03d}.png")
            cv2.imwrite(lpath, frame_l)
            cv2.imwrite(rpath, frame_r)
            print(f"Saved pair {idx}: shared corners={shared}")
            idx += 1
            flash = combined.copy(); flash[:] = (0, 255, 0)
            cv2.imshow("capture_calibration_pairs  (left | right)", flash)
            cv2.waitKey(80)

    cam_l.stop(); cam_r.stop()
    cv2.destroyAllWindows()
    print(f"\nDone. Captured {idx} pairs in '{args.outdir}/'.")
    print("Then run: python3 stereo_calibrate.py --dir", args.outdir,
          f"--squares-x {args.squares_x} --squares-y {args.squares_y} "
          f"--square-length {args.square_length} --marker-length {args.marker_length} "
          f"--dict {args.dict}" + (" --no-legacy-pattern" if args.no_legacy_pattern else ""))


if __name__ == "__main__":
    main()
