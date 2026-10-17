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

# check temperatura
TEMP=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
if (( $(echo "$TEMP > 55" | bc -l) )); then
    echo "ERRORE: temperatura SoC ${TEMP}°C > 55°C. Aspetta prima di iniziare."
    exit 1
fi
echo "== ${CONFIG} run ${RUN_N} =="
echo "Temperatura SoC iniziale: ${TEMP}°C"

# forza il governor 'performance' su tutti i core per evitare che la CPU
# scali dinamicamente di frequenza durante il benchmark (default: powersave).
# va fatto prima di leggere il clock, altrimenti leggiamo 1600 MHz a idle.
CUR_GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
if [ "$CUR_GOV" != "performance" ]; then
    echo "Imposto governor CPU: ${CUR_GOV} -> performance"
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
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
sudo systemctl stop nautilus-vision.service 2>/dev/null || true
sudo systemctl stop lock-cameras.service 2>/dev/null || true
pkill -f camera_node 2>/dev/null || true
pkill -f detection_node 2>/dev/null || true
pkill -f enhancement_node 2>/dev/null || true
pkill -f metrics_node 2>/dev/null || true
sleep 2

# output paths
LAT_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_latency.csv"
SYS_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_system.csv"
LAUNCH_LOG="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_launch.log"
META="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_metadata.csv"

# costruzione argomenti di override: vanno passati SOLO se non vuoti,
# altrimenti ros2 launch esce con "malformed launch argument".
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

# lancio pipeline in background
# include_stereo_camera:=true è obbligatorio perché il wrapper ha appena
# fermato i servizi: le camere non sono attive e pipeline.launch.py di
# default non le avvia (assume che siano già su).
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_enhancement:=$ENH \
    enable_detection:=$DET \
    enable_saving:=false \
    enable_metrics:=true \
    enable_debug:=false \
    "${OVERRIDES[@]}" \
    > "$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!

# attesa boot + lock fotometrico
sleep 5
python3 "$ROOT/deploy/lock_cameras.py" >> "$LAUNCH_LOG" 2>&1 || true

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
pkill -f camera_node 2>/dev/null || true
pkill -f detection_node 2>/dev/null || true
pkill -f enhancement_node 2>/dev/null || true
pkill -f metrics_node 2>/dev/null || true

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
enable_saving,false
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
