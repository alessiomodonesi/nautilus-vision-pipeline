# Installing Raspberry Pi Camera Module 3 on Pi 5 + Ubuntu Server

**Why this guide exists:** Unlike Raspberry Pi OS, Ubuntu does not ship
working Camera Module 3 support out of the box. `python3-picamera2` is not
published for Ubuntu's `noble` (24.04) release, and Ubuntu's stock
`libcamera` package doesn't include the Pi 5's `pisp` pipeline handler at
all. The only reliable fix (as of mid/late-2026) is building the
Raspberry Pi–specific camera stack from source. This guide captures the
exact working sequence, including every dead end worth skipping.

**Time estimate:** 60-90 minutes, mostly unattended build time.

**Tested on:** Ubuntu Server 24.04 (noble), Raspberry Pi 5, 2× Camera
Module 3 (IMX708) on dual CSI, Python 3.12.

---

## 0. Before you start

- Confirm you're actually on Ubuntu Server, not Desktop:
  `lsb_release -a`
- Confirm your Ubuntu codename is `noble` (24.04). This guide is written
  against that release; other releases may need adjusted package names.
- Have the camera physically connected before you boot, and confirm it's
  seated correctly in the CSI connector (metal contacts facing the correct
  way per the ribbon cable orientation).

## 1. Enable the `universe` repository

Ubuntu Server does **not** enable `universe` by default. A large chunk of
the build dependencies below (Boost, libjpeg-dev, python3-yaml, etc.) live
there, and you'll get `Unable to locate package` errors without it.

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt update
```

**Sanity check** — confirm `noble-updates` and `noble-backports` are also
being fetched (not just `noble` and `noble-security`):

```bash
sudo apt update
```

You should see `Hit:` lines for all four pockets: `noble`, `noble-updates`,
`noble-backports`, `noble-security`. If any are missing, check
`/etc/apt/sources.list.d/ubuntu.sources` — the `Suites:` line should read:

```txt
Suites: noble noble-updates noble-backports noble-security
```

## 2. Do NOT use the picamera2 PPA route

You'll find PPAs like `ppa:r41k0u/python3-simplejpeg` referenced in older
guides as a shortcut to `apt install python3-picamera2`. **As of writing,
this PPA has no build published for `noble`** — you'll hit a `404` on
`Release` no matter how many times you retry. Don't waste time on it;
skip straight to building from source below.

If you already added it and are seeing apt errors referencing it, remove
it cleanly:

```bash
sudo apt-add-repository --remove ppa:r41k0u/python3-simplejpeg
sudo apt update
```

## 3. Sync your package versions

Before installing build dependencies, make sure your system's installed
packages and available package lists actually agree — a partial/interrupted
upgrade can cause `apt install` to fail with confusing
`Depends: X (= version) but Y is to be installed` errors later.

```bash
sudo apt update
sudo apt full-upgrade -y
```

## 4. Install build dependencies

```bash
sudo apt install -y git python3-pip python3-jinja2 meson cmake ninja-build \
  build-essential libboost-dev libgnutls28-dev openssl libtiff5-dev \
  pybind11-dev python3-yaml python3-ply libglib2.0-dev \
  libgstreamer-plugins-base1.0-dev libboost-program-options-dev \
  libdrm-dev libexif-dev libepoxy-dev libjpeg-dev libpng-dev v4l-utils \
  libexpat1-dev
```

**[FIX 2026-10-13]** Ubuntu Server does *not* ship `python3-venv` or
`ensurepip` by default, and installing them later is easy to forget until
you hit the error. Install them now, along with `libcap-dev` which
`python-prctl` (a `picamera2` dependency) needs at build time — without
it, `pip install picamera2` fails partway through with
`You need to install libcap development headers to build this module`:

```bash
sudo apt install -y python3.12-venv python3-pip libcap-dev
```

Everything here should install cleanly once steps 1 and 3 are done. If you
still see `Unable to locate package` for any of these, double check
`universe` is really enabled (step 1).

## 5. Build Raspberry Pi's `libcamera` fork from source

This is the actual fix — Raspberry Pi's fork adds the `pisp` pipeline
handler that the Pi 5 needs and that Ubuntu's stock `libcamera` lacks
entirely.

```bash
cd ~
git clone https://github.com/raspberrypi/libcamera.git
cd libcamera
meson setup build
ninja -C build
sudo ninja -C build install
```

This takes roughly 15-20 minutes. Watch for `imx708.json` (the Camera
Module 3 sensor's calibration file) being installed under both the `pisp`
and `vc4` pipeline data directories in the output — that's a good sign
your specific sensor is supported by this build.

**Where the Python bindings land:** `/usr/local/lib/python3/dist-packages/libcamera/`.
Not `/usr/local/lib/python/dist-packages/` (no `3`), and not
`/usr/local/lib/python3.12/dist-packages/` (versioned) — the unversioned
`python3/dist-packages` is the Debian/Ubuntu convention, and it *does*
contain the `3`. Verify after install:

```bash
ls -la /usr/local/lib/python3/dist-packages/libcamera/
# expect: __init__.py  __pycache__  _libcamera.cpython-312-aarch64-linux-gnu.so
```

## 6. Build `rpicam-apps`

These are the camera-stack-level command line tools (`rpicam-hello`,
`rpicam-vid`, etc.), and picamera2 relies on the same underlying
`libcamera` you just built.

```bash
cd ~
git clone https://github.com/raspberrypi/rpicam-apps.git
cd rpicam-apps
meson setup build
ninja -C build
sudo ninja -C build install
echo "/usr/local/lib/aarch64-linux-gnu" | sudo tee /etc/ld.so.conf.d/rpicam.conf
sudo ldconfig
```

## 7. Verify camera detection — the real milestone

```bash
rpicam-hello --list-cameras
```

You should see your camera(s) listed with sensor name `imx708` and
supported resolutions/framerates, e.g.:

```txt
0 : imx708 [4608x2592 10-bit RGGB] (/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a)
    Modes: 'SRGGB10_CSI2P' : 1536x864 [120.13 fps ...]
```

**If this works, the hard part is done.** Everything below is just wiring
up the Python side.

---

## 8. Set up your Python venv correctly

`picamera2` needs to be pip-installed *inside* your project's venv, but it
also needs to see the `libcamera` Python bindings you just built
system-wide. A plain venv can't see them, so:

```bash
cd ~/your_project
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

**[FIX 2026-10-13]** `--system-site-packages` gets you most of the way,
but the `/usr/local/lib/python3/dist-packages` path (where `libcamera`
landed in step 5) is still **not** on the venv's `sys.path`. The original
guide suggested a symlink — **do not use a symlink**. On Ubuntu 24.04 +
Python 3.12, `importlib` does not reliably follow symlinked *directories*
inside `site-packages`, so `import libcamera` fails with
`ModuleNotFoundError` even though the symlink looks correct in `ls -la`.

**Copy the directory instead:**

```bash
# Confirm the source path first
ls -la /usr/local/lib/python3/dist-packages/libcamera/

# Copy it physically into the venv
cp -r /usr/local/lib/python3/dist-packages/libcamera \
      ~/your_project/.venv/lib/python3.12/site-packages/libcamera

# Verify
python3 -c "import libcamera; print('libcamera OK:', libcamera.__file__)"
```

Expected: `libcamera OK: /home/<user>/<project>/.venv/lib/python3.12/site-packages/libcamera/__init__.py`

If the copy still doesn't import, debug with:

```bash
python3 -c "import sys; print('\n'.join(sys.path))"
python3 -c "import site; print(site.getsitepackages())"
```

The venv's own `site-packages` must appear in `sys.path`, and it must be
the same directory you copied into.

## 9. pip install picamera2

```bash
pip install picamera2 flask
python3 -c "from picamera2 import Picamera2; print('picamera2 OK')"
```

**[FIX 2026-10-13]** `flask` is added because `capture_calibration_pairs_web.py`
imports it at module load. If `pip install picamera2` fails partway
through with:

```text
error: subprocess-exited-with-error
× python setup.py egg_info did not run successfully.
You need to install libcap development headers to build this module
```

…you skipped the `libcap-dev` install in step 4. Install it and retry:

```bash
sudo apt install -y libcap-dev
pip install picamera2
```

## 10. Fix the `pykms` import error

`picamera2` unconditionally imports its DRM preview backend at module load
time — even if you never intend to use a preview window on a headless
server. This needs `pykms` (Python bindings for `kms++`), which also isn't
packaged for Ubuntu.

```bash
sudo apt install -y libfmt-dev libdrm-dev
cd ~
git clone https://github.com/tomba/kmsxx.git
cd kmsxx
git submodule update --init
meson setup build
ninja -C build
sudo ninja -C build install
sudo ldconfig
cp -r ~/kmsxx/build/py/pykms ~/your_project/.venv/lib/python3.12/site-packages/
```

**Important:** `sudo ninja -C build install` is required, not just
`ninja -C build` — the build alone produces `pykms.so` but doesn't install
the `libkms++.so.0` shared library it links against, causing an
`ImportError: libkms++.so.0: cannot open shared object file` even though
the Python module itself is found.

## 11. Final check

```bash
python3 -c "from picamera2 import Picamera2; print('picamera2 OK')"
```

**[FIX 2026-10-13]** Note: `picamera2.__version__` does **not** exist as
an attribute of the package (unlike many Python packages). Do not use
`python3 -c "import picamera2; print(picamera2.__version__)"` as a check —
it will raise `AttributeError` even when everything is fine. Use `from
picamera2 import Picamera2` instead, or `pip show picamera2 | grep -i version`.

If this prints cleanly, you're done — every layer (libcamera → rpicam-apps
→ picamera2 → pykms) is now correctly built, installed, and visible to
your venv.

---

## 12. Do NOT commit the venv to the repo

The `.venv/` directory is machine-specific (absolute paths in
`pyvenv.cfg`) and architecture-specific (the compiled `.so` files are
`aarch64`). Committing it makes the repo huge and useless to anyone on a
different machine. Exclude it in `.gitignore`:

```gitignore
.venv/
venv/
env/
ENV/
```

Anyone who clones the repo recreates the venv from this guide in ~30
seconds once the system-level build (steps 5, 6, 10) is done — and those
system-level components *are* machine-specific too and must be rebuilt
locally anyway.

---

## Troubleshooting index

| Symptom | Cause | Fix |
| --- | --- | --- |
| `E: Unable to locate package X` | `universe` not enabled | Step 1 |
| PPA gives `404 Not Found` on `Release` | PPA has no `noble` build | Skip PPA entirely, use source build |
| `Depends: X (= version) but Y is to be installed` | Stale/partial apt state | `apt update && apt full-upgrade -y` |
| `The virtual environment was not created successfully because ensurepip is not available` | `python3-venv` not installed | Step 4: `sudo apt install python3.12-venv` |
| `You need to install libcap development headers to build this module` (during `pip install picamera2`) | `libcap-dev` missing | Step 4: `sudo apt install libcap-dev` |
| `ModuleNotFoundError: No module named 'libcamera'` (inside venv) | Symlink inside `site-packages` not followed by importlib | Step 8: **copy** the directory, do not symlink |
| `ModuleNotFoundError: No module named 'pykms'` / `'kms'` | kms++ Python bindings not installed | Step 10 |
| `ImportError: libkms++.so.0: cannot open shared object file` | Built kmsxx but didn't run `sudo ninja -C build install` | Re-run install step + `ldconfig` |
| `AttributeError: module 'picamera2' has no attribute '__version__'` | Not a real error — `picamera2` simply doesn't expose `__version__` | Use `from picamera2 import Picamera2` as the import check |
| `rpicam-hello --list-cameras` shows nothing | Camera not seated, or libcamera build didn't pick up `pisp` handler | Reseat ribbon cable; re-check step 5 output for `pisp` pipeline |

---

## What you do NOT need

- `sudo apt install python3-picamera2` — not published for `noble` as of
  writing.
- Any `ppa:r41k0u/*` PPAs — no `noble` builds exist.
- Reflashing to Raspberry Pi OS — this guide is the alternative to that,
  useful if you specifically need Ubuntu for something else (e.g. ROS2,
  which ships official binaries for Ubuntu but not Raspberry Pi OS/Debian).
- Committing the `.venv/` directory to your project repo — recreate it
  locally instead (step 12).
