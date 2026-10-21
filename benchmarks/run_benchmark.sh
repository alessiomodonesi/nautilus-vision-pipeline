#!/bin/bash
# uso: ./run_benchmark.sh <config> <run_n>
#   config: A_baseline | B1_pt | B2_ov_fp32 | B3_ov_int8_640 | B4_ov_int8_416
#         | C_full
#         | B1_pt_oc | B2_ov_fp32_oc | B3_ov_int8_640_oc | B4_ov_int8_416_oc | C_full_oc
#   run_n:  1 | 2 | 3

set -e

CONFIG="$1"
RUN_N="$2"

if [ -z "$CONFIG" ] || [ -z "$RUN_N" ]; then
    echo "Uso: $0 <config> <run_n>"
    echo "  config: A_baseline | B1_pt | B2_ov_fp32 | B3_ov_int8_640 | B4_ov_int8_416"
    echo "        | C_full"
    echo "        | B1_pt_oc | B2_ov_fp32_oc | B3_ov_int8_640_oc | B4_ov_int8_416_oc | C_full_oc"
    echo "  run_n:  1 | 2 | 3"
    exit 1
fi

ROOT="$HOME/nautilus-vision-pipeline"
WS="$ROOT/ros2_ws"
DATE=$(date +%Y-%m-%d)
CSV_DIR="$ROOT/benchmarks/results/csv"
mkdir -p "$CSV_DIR"

# config → (ENH, DET, MODEL, HALF_RES, IMGSZ, NOTE)
case "$CONFIG" in
    # ── Fase A: senza overclock ─────────────────────────────────────────
    A_baseline)          ENH="false"; DET="false"; MODEL="";                          HALF_RES="true";  IMGSZ="640"; NOTE="baseline solo camera (no OC)" ;;
    B1_pt)               ENH="false"; DET="true";  MODEL="yolov8n.pt";                HALF_RES="true";  IMGSZ="640"; NOTE="yolov8n.pt (no OC)" ;;
    B2_ov_fp32)          ENH="false"; DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OpenVINO FP32 640 (no OC)" ;;
    B3_ov_int8_640)      ENH="false"; DET="true";  MODEL="yolov8n_640_int8_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OpenVINO INT8 640 (no OC)" ;;
    B4_ov_int8_416)      ENH="false"; DET="true";  MODEL="yolov8n_416_int8_openvino_model"; HALF_RES="false"; IMGSZ="416"; NOTE="OpenVINO INT8 416 (no OC)" ;;
    C_full)              ENH="true";  DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="full + OV FP32 640 (no OC)" ;;
    # ── Fase B: con overclock 2800 MHz ──────────────────────────────────
    B1_pt_oc)            ENH="false"; DET="true";  MODEL="yolov8n.pt";                HALF_RES="true";  IMGSZ="640"; NOTE="yolov8n.pt (OC 2800)" ;;
    B2_ov_fp32_oc)       ENH="false"; DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OpenVINO FP32 640 (OC 2800)" ;;
    B3_ov_int8_640_oc)   ENH="false"; DET="true";  MODEL="yolov8n_640_int8_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OpenVINO INT8 640 (OC 2800)" ;;
    B4_ov_int8_416_oc)   ENH="false"; DET="true";  MODEL="yolov8n_416_int8_openvino_model"; HALF_RES="false"; IMGSZ="416"; NOTE="OpenVINO INT8 416 (OC 2800)" ;;
    C_full_oc)           ENH="true";  DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="full + OV FP32 640 (OC 2800)" ;;
    *) echo "Config non valida: $CONFIG"; exit 1 ;;
esac

# cleanup condiviso dei nodi camera/detection/enhancement/metrics.
# libcamera può impiegare 3–5 s a rilasciare /dev/video* dopo SIGTERM:
# senza retry il camera_ros del launch successivo fallisce con
# "camera is not free" e il check post-launch abortisce la run.
# se dopo 8 s il processo è ancora vivo, SIGKILL di fallback.
cleanup_camera_nodes() {
    pkill -f camera_node      2>/dev/null || true
    pkill -f detection_node   2>/dev/null || true
    pkill -f enhancement_node 2>/dev/null || true
    pkill -f metrics_node     2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8; do
        if ! pgrep -f camera_node > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "WARN: camera_node ancora vivo dopo 8 s, invio SIGKILL"
    pkill -9 -f camera_node 2>/dev/null || true
    sleep 2
}

# check temperatura
TEMP=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
TEMP_INT=${TEMP%.*}   # 52.1 -> 52
if [ "$TEMP_INT" -gt 55 ]; then
    echo "ERRORE: temperatura SoC ${TEMP}°C > 55°C. Aspetta prima di iniziare."
    exit 1
fi
echo "== ${CONFIG} run ${RUN_N} =="
echo "Temperatura SoC iniziale: ${TEMP}°C"

# forza il governor 'performance' su tutti i core per evitare che la CPU
# scali dinamicamente di frequenza durante il benchmark (default: powersave).
# va fatto prima di leggere il clock, altrimenti leggiamo 1600 MHz a idle.
# sudo -n: fallisce subito se NOPASSWD non è configurato, invece di
# restare appeso su un prompt in una sessione tmux detached.
CUR_GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
if [ "$CUR_GOV" != "performance" ]; then
    echo "Imposto governor CPU: ${CUR_GOV} -> performance"
    if ! echo performance | sudo -n tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null 2>&1; then
        echo "ERRORE: impossibile cambiare governor (sudo -n fallito)."
        echo "  Verifica /etc/sudoers.d/ per NOPASSWD dell'utente nautilus."
        echo "  Comandi richiesti: tee, systemctl"
        exit 1
    fi
    sleep 1
fi
echo "Governor CPU: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

# throttling/clock iniziale
THR_START=$(vcgencmd get_throttled | cut -d= -f2)
CLK_START=$(vcgencmd measure_clock arm | cut -d= -f2)

# cpu clock atteso in base alla fase
case "$CONFIG" in
    *_oc) EXPECT_CLOCK=2800 ;;
    *)    EXPECT_CLOCK=2400 ;;
esac

# attesa breve per far assestare il clock dopo il cambio governor
sleep 1
CLK_MHZ=$(( $(vcgencmd measure_clock arm | cut -d= -f2) / 1000000 ))
if [ "$CLK_MHZ" -lt "$EXPECT_CLOCK" ]; then
    echo "ERRORE: clock ${CLK_MHZ} MHz < atteso ${EXPECT_CLOCK} MHz per $CONFIG"
    echo "  governor corrente: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
    echo "  frequenza max disponibile: $(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq) kHz"
    exit 1
fi
echo "Clock CPU: ${CLK_MHZ} MHz (atteso ${EXPECT_CLOCK})"

# ambiente
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

# stop servizi + cleanup
# nota: lo stop deve precedere il pkill, altrimenti systemd interpreta la
# morte dei processi come crash e riavvia nautilus-vision.service a metà
# run (Restart=on-failure, RestartSec=5). è esattamente ciò che ha
# invalidato i primi run del 20/10/2026.
# nautilus-bag.service è PartOf/Requires=nautilus-vision.service, quindi
# lo stop cascada; lo esplicitiamo perché un recorder avviato a mano
# (start_pipeline.sh + ros2 bag record) non viene fermato dalla gerarchia.
# sudo -n per non bloccare il loop in tmux detached.
sudo -n systemctl stop nautilus-bag.service    2>/dev/null || true
sudo -n systemctl stop nautilus-vision.service 2>/dev/null || true
sudo -n systemctl stop lock-cameras.service    2>/dev/null || true

sleep 1
if systemctl is-active --quiet nautilus-vision.service; then
    echo "ERRORE: nautilus-vision.service ancora attivo dopo 'systemctl stop'."
    systemctl status --no-pager nautilus-vision.service 2>&1 | head -5 | sed 's/^/    /'
    exit 1
fi

pkill -f "ros2 bag record" 2>/dev/null || true
cleanup_camera_nodes

# ── reset cache discovery ──────────────────────────────────────────────
# dopo un kill, CycloneDDS tiene il nodo in cache per 60-90 s. senza
# reset, il check pre-launch 1 può abortire per un fantasma anche se
# /dev/video* è libero.
ros2 daemon stop 2>/dev/null || true
ros2 daemon start 2>/dev/null || true
sleep 2

# ── check pre-launch 1: nessun nodo della pipeline già attivo ──────────
STALE_NODES=$(ros2 node list 2>/dev/null | grep -E "^/stereo/|^/detection_node$|^/metrics_node$" || true)
if [ -n "$STALE_NODES" ]; then
    # distinguere nodo vivo da fantasma: se /dev/video* è libero,
    # i nodi sono fantasmi del discovery e possiamo procedere.
    if fuser /dev/video0 /dev/video1 > /dev/null 2>&1; then
        echo "ERRORE: nodi ROS 2 già attivi e /dev/video* occupato:"
        echo "$STALE_NODES" | sed 's/^/  /'
        fuser -v /dev/video0 /dev/video1 2>&1 | sed 's/^/    /'
        exit 1
    fi
    # device liberi ma discovery mostra nodi: fantasmi, attendi e riprova
    echo "WARN: nodi fantasma nel discovery (device libero), attendo 5 s..."
    sleep 5
    STALE_NODES=$(ros2 node list 2>/dev/null | grep -E "^/stereo/|^/detection_node$|^/metrics_node$" || true)
    if [ -n "$STALE_NODES" ]; then
        echo "ERRORE: nodi ancora visibili dopo reset daemon:"
        echo "$STALE_NODES" | sed 's/^/  /'
        echo "  Device /dev/video*: libero. Forza con: ros2 daemon stop; ros2 daemon start"
        exit 1
    fi
fi

# ── check pre-launch 2: nessun publisher già attivo sui topic raw ──────
# anche se i nodi non compaiono nella lista (fase di shutdown, discovery
# in ritardo), un publisher attivo impedisce a camera_ros di acquisire.
for topic in /stereo/lx/camera/image_raw /stereo/rx/camera/image_raw; do
    if ros2 topic info "$topic" 2>/dev/null | grep -qE "Publisher count: [1-9]"; then
        echo "ERRORE: publisher già attivo su $topic"
        echo "  Un processo esterno sta usando le camere (servizio systemd"
        echo "  ripartito o launch manuale dimenticato). Fermalo con:"
        echo "    pkill -9 -f camera_node"
        exit 1
    fi
done

# ── check pre-launch 3: nessun recorder bag attivo ─────────────────────
# un ros2 bag record attivo durante il benchmark consuma I/O su MicroSD
# e falsa le misure di latenza degli stage che scrivono su disco.
if pgrep -f "ros2 bag record" > /dev/null 2>&1; then
    echo "ERRORE: processo 'ros2 bag record' ancora attivo."
    echo "  Il recorder consuma I/O e falsa le misure di latenza."
    echo "  Fermalo con:"
    echo "    pkill -f 'ros2 bag record'"
    exit 1
fi

# output paths
LAT_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_latency.csv"
SYS_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_system.csv"
LAUNCH_LOG="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_launch.log"
META="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_metadata.csv"

# costruzione argomenti di override: vanno passati SOLO se non vuoti,
# altrimenti ros2 launch esce con "malformed launch argument".
# input_type_override è sempre passato esplicitamente (raw per B*, enhanced
# per C_full) per non dipendere dal valore di input_type nel YAML: se lo
# cambi per un test manuale, le B* si romperebbero silenziosamente
# (subscriber su un topic senza publisher).
OVERRIDES=()
if [ -n "$MODEL" ]; then
    OVERRIDES+=("model_filename_override:=$MODEL")
fi
if [ -n "$HALF_RES" ]; then
    OVERRIDES+=("half_res_override:=$HALF_RES")
fi
if [ -n "$IMGSZ" ]; then
    OVERRIDES+=("imgsz_override:=$IMGSZ")
fi
if [ "$ENH" = "true" ]; then
    OVERRIDES+=("input_type_override:=enhanced")
else
    OVERRIDES+=("input_type_override:=raw")
fi

# lancio pipeline in background
# include_stereo_camera:=true è obbligatorio perché il wrapper ha appena
# fermato i servizi: le camere non sono attive e pipeline.launch.py di
# default non le avvia (assume che siano già su).
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_enhancement:=$ENH \
    enable_detection:=$DET \
    enable_metrics:=true \
    enable_debug:=false \
    "${OVERRIDES[@]}" \
    > "$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!

# attesa boot + lock fotometrico
sleep 5
python3 "$ROOT/deploy/lock_cameras.py" >> "$LAUNCH_LOG" 2>&1 || true

# ── check post-launch 1: nessun errore fatale nel launch log ───────────
# il launch gira in background: un crash di detection_node (es. modello
# OpenVINO passato come .xml invece che come directory) non propaga
# l'errore al wrapper. lo intercettiamo qui prima di sprecare 120 s.
if grep -qE "is not a supported model format|stereo_callback failed|failed to acquire camera" "$LAUNCH_LOG" 2>/dev/null; then
    echo "ERRORE: errori fatali nel launch log:"
    grep -E "is not a supported model format|stereo_callback failed|failed to acquire camera" "$LAUNCH_LOG" | head -3 | sed 's/^/  /'
    echo ""
    echo "  Chi tiene /dev/video0 e /dev/video1:"
    fuser -v /dev/video0 /dev/video1 2>&1 | sed 's/^/    /' || echo "    (nessuno)"
    kill $LAUNCH_PID 2>/dev/null || true
    cleanup_camera_nodes
    sleep 2
    exit 1
fi

# ── check post-launch 2: camera node attivo ────────────────────────────
sleep 2
if ! ros2 node list 2>/dev/null | grep -q "^/stereo/lx/camera$"; then
    echo "ERRORE: /stereo/lx/camera non attivo. Controlla $LAUNCH_LOG"
    echo "  (causa tipica: camera occupata da un altro processo)"
    kill $LAUNCH_PID 2>/dev/null || true
    cleanup_camera_nodes
    sleep 2
    exit 1
fi

# verifica che anche rx sia attivo (parte 3 s dopo lx per via del TimerAction)
if ! ros2 node list 2>/dev/null | grep -q "^/stereo/rx/camera$"; then
    echo "ERRORE: /stereo/rx/camera non attivo dopo 7 s. Controlla $LAUNCH_LOG"
    kill $LAUNCH_PID 2>/dev/null || true
    cleanup_camera_nodes
    sleep 2
    exit 1
fi

# ── check post-launch 3: rate raw coerente con FrameDurationLimits ─────
# se il rate misurato è ~30 Hz invece di ~5 Hz, i frame vengono da un
# processo esterno che pubblica sullo stesso topic (servizio systemd
# ripartito durante lo stop, launch manuale). il check pre-launch 2
# dovrebbe intercettarlo, ma questo è una seconda linea di difesa: il
# rate viene misurato sul flusso effettivo, non sulla discovery.
CAM_YAML="$WS/install/nautilus_camera/share/nautilus_camera/config/nautilus_camera.yaml"
FDL_US=$(python3 -c "
import yaml
try:
    with open('$CAM_YAML') as f:
        cfg = yaml.safe_load(f)
    print(int(cfg['/stereo/lx/camera']['ros__parameters']['FrameDurationLimits'][0]))
except Exception:
    print(200000)
" 2>/dev/null || echo "200000")
EXPECTED_FPS=$(( 1000000 / FDL_US ))
LOW=$(( EXPECTED_FPS * 7 / 10 ))
HIGH=$(( EXPECTED_FPS * 13 / 10 ))

RAW_INT=$(timeout 8 ros2 topic hz /stereo/lx/camera/image_raw 2>/dev/null \
          | grep -oE "average rate: [0-9.]+" | tail -1 \
          | grep -oE "[0-9]+" | head -1) || RAW_INT="0"
RAW_INT=${RAW_INT:-0}

if [ "$RAW_INT" -lt "$LOW" ] || [ "$RAW_INT" -gt "$HIGH" ]; then
    echo "ERRORE: rate raw ${RAW_INT} Hz, atteso ~${EXPECTED_FPS} Hz (range ${LOW}-${HIGH})"
    echo "  Se il rate è ~30 Hz, i frame vengono da un processo esterno:"
    echo "    ros2 topic info /stereo/lx/camera/image_raw -v"
    echo "  Controlla $LAUNCH_LOG per 'failed to acquire camera'."
    kill $LAUNCH_PID 2>/dev/null || true
    cleanup_camera_nodes
    sleep 2
    exit 1
fi
echo "Camera OK: raw ~${RAW_INT} Hz (atteso ~${EXPECTED_FPS} Hz, range ${LOW}-${HIGH})"

# ── check post-launch 4: detection node attivo (se DET=true) ───────────
# il nodo detection carica il modello YOLO in __init__ (0.5–2 s): diamo
# 10 retry * 0.5 s = 5 s di margine oltre ai ~8 s già trascorsi.
if [ "$DET" = "true" ]; then
    DET_UP=0
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if ros2 node list 2>/dev/null | grep -q "^/detection_node$"; then
            DET_UP=1
            break
        fi
        sleep 0.5
    done
    if [ "$DET_UP" -ne 1 ]; then
        echo "ERRORE: /detection_node non attivo dopo 5 s di attesa."
        echo "  Controlla $LAUNCH_LOG per errori di caricamento modello."
        kill $LAUNCH_PID 2>/dev/null || true
        cleanup_camera_nodes
        sleep 2
        exit 1
    fi
fi

# warmup (30 s)
echo "Warmup 30s..."
sleep 30

# system monitor in background (300 s)
python3 "$ROOT/benchmarks/scripts/system_monitor.py" \
    --duration 300 \
    --out "$SYS_CSV" \
    > /dev/null 2>&1 &
MON_PID=$!

# benchmark latenze (120 s)
TGT_TOPIC=""
ENH_TOPIC=""
STG_TOPIC=""
if [ "$DET" = "true" ]; then TGT_TOPIC="/stereo_down/targets"; fi
if [ "$ENH" = "true" ]; then ENH_TOPIC="/stereo/lx/image_enhanced"; fi

echo "Benchmark latenze 120s..."
if [ "$DET" = "true" ]; then STG_TOPIC="/stereo_down/timings"; fi

python3 "$ROOT/benchmarks/scripts/benchmark_pipeline.py" \
    --duration 120 \
    --out "$LAT_CSV" \
    --raw-topic /stereo/lx/camera/image_raw \
    --enhanced-topic "$ENH_TOPIC" \
    --targets-topic "$TGT_TOPIC" \
    --stages-topic "$STG_TOPIC"

# attesa monitor
wait $MON_PID 2>/dev/null || true

# cleanup pipeline
kill $LAUNCH_PID 2>/dev/null || true
sleep 3
cleanup_camera_nodes

# temperatura finale
TEMP_END=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
echo "Temperatura SoC finale: ${TEMP_END}°C"

# throttling/clock finale
THR_END=$(vcgencmd get_throttled | cut -d= -f2)
CLK_END=$(vcgencmd measure_clock arm | cut -d= -f2)

# metadata
COMMIT=$(cd "$ROOT" && git rev-parse HEAD 2>/dev/null || echo "unknown")
cat > "$META" <<EOF
field,value
commit_hash,$COMMIT
config,$CONFIG
run,$RUN_N
enable_enhancement,$ENH
enable_detection,$DET
enable_metrics,true
model_filename,$MODEL
half_res,$HALF_RES
imgsz,$IMGSZ
soc_temp_initial_c,$TEMP
soc_temp_final_c,$TEMP_END
throttled_initial,$THR_START
throttled_final,$THR_END
cpu_clock_initial_mhz,$((CLK_START / 1000000))
cpu_clock_final_mhz,$((CLK_END / 1000000))
notes,$NOTE
EOF

echo ""
echo "Files salvati:"
echo "  $LAT_CSV"
echo "  $SYS_CSV"
echo "  $META"
echo "  $LAUNCH_LOG"
echo ""
echo "Cooldown 30s..."
sleep 30
echo "Pronto per il prossimo run."
