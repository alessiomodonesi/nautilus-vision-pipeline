#!/bin/bash
# usage: ./run_benchmark.sh <config> <run_n>

set -e

CONFIG="$1"
RUN_N="$2"

if [ -z "$CONFIG" ] || [ -z "$RUN_N" ]; then
    echo "Usage: $0 <config> <run_n>"
    exit 1
fi

ROOT="$HOME/nautilus-vision-pipeline"
WS="$ROOT/ros2_ws"
DATE=$(date +%Y-%m-%d)
CSV_DIR="$ROOT/benchmarks/results/csv"
mkdir -p "$CSV_DIR"

case "$CONFIG" in
    A_baseline)          ENH="false"; DET="false"; MODEL="";                          HALF_RES="true";  IMGSZ="640"; NOTE="baseline" ;;
    B1_pt)               ENH="false"; DET="true";  MODEL="yolov8n.pt";                HALF_RES="true";  IMGSZ="640"; NOTE="yolov8n.pt" ;;
    B2_ov_fp32)          ENH="false"; DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OV FP32" ;;
    B3_ov_int8_640)      ENH="false"; DET="true";  MODEL="yolov8n_640_int8_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OV INT8 640" ;;
    B4_ov_int8_416)      ENH="false"; DET="true";  MODEL="yolov8n_416_int8_openvino_model"; HALF_RES="false"; IMGSZ="416"; NOTE="OV INT8 416" ;;
    C_full)              ENH="true";  DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="full" ;;
    B1_pt_oc)            ENH="false"; DET="true";  MODEL="yolov8n.pt";                HALF_RES="true";  IMGSZ="640"; NOTE="yolov8n.pt OC" ;;
    B2_ov_fp32_oc)       ENH="false"; DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OV FP32 OC" ;;
    B3_ov_int8_640_oc)   ENH="false"; DET="true";  MODEL="yolov8n_640_int8_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="OV INT8 640 OC" ;;
    B4_ov_int8_416_oc)   ENH="false"; DET="true";  MODEL="yolov8n_416_int8_openvino_model"; HALF_RES="false"; IMGSZ="416"; NOTE="OV INT8 416 OC" ;;
    C_full_oc)           ENH="true";  DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="full OC" ;;
    *) echo "Invalid config: $CONFIG"; exit 1 ;;
esac

cleanup_camera_nodes() {
    pkill -9 -f camera_node 2>/dev/null || true
    pkill -9 -f detection_node 2>/dev/null || true
    pkill -9 -f enhancement_node 2>/dev/null || true
    pkill -9 -f metrics_node 2>/dev/null || true
    sleep 1
}

TEMP=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
TEMP_INT=${TEMP%.*}
if [ "$TEMP_INT" -gt 55 ]; then
    echo "ERROR: SoC temperature ${TEMP}°C > 55°C. Please wait before starting."
    exit 1
fi
echo "== ${CONFIG} run ${RUN_N} =="
echo "Initial SoC temperature: ${TEMP}°C"

CUR_GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
if [ "$CUR_GOV" != "performance" ]; then
    echo "Setting CPU governor: ${CUR_GOV} -> performance"
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null 2>&1 || true
    sleep 1
fi
echo "CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

THR_START=$(vcgencmd get_throttled | cut -d= -f2)
CLK_START=$(vcgencmd measure_clock arm | cut -d= -f2)

source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

if [ -f "$HOME/nautilus-vision-pipeline/pipeline_config.env" ]; then
    source "$HOME/nautilus-vision-pipeline/pipeline_config.env"
fi

sudo systemctl stop nautilus-bag.service 2>/dev/null || true
sudo systemctl stop nautilus-vision.service 2>/dev/null || true
sudo systemctl stop lock-cameras.service 2>/dev/null || true

pkill -f "ros2 bag record" 2>/dev/null || true
cleanup_camera_nodes

ros2 daemon stop 2>/dev/null || true
ros2 daemon start 2>/dev/null || true
sleep 3

LAT_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_latency.csv"
SYS_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_system.csv"
LAUNCH_LOG="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_launch.log"
META="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_metadata.csv"

OVERRIDES=()
if [ -n "$MODEL" ]; then OVERRIDES+=("model_filename_override:=$MODEL"); fi
if [ -n "$HALF_RES" ]; then OVERRIDES+=("half_res_override:=$HALF_RES"); fi
if [ -n "$IMGSZ" ]; then OVERRIDES+=("imgsz_override:=$IMGSZ"); fi
if [ "$ENH" = "true" ]; then OVERRIDES+=("input_type_override:=enhanced"); else OVERRIDES+=("input_type_override:=raw"); fi

# ── Hardware unlock ───────────────────────────────────────────
echo "Unlocking camera hardware..."
sudo fuser -k -9 /dev/video0 /dev/video1 2>/dev/null || true
sleep 1
# ───────────────────────────────────────────────────────────────────────

ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_enhancement:=$ENH \
    enable_detection:=$DET \
    enable_metrics:=true \
    enable_debug:=false \
    params_file:=nautilus_camera.yaml \
    "${OVERRIDES[@]}" \
    > "$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!

sleep 5
python3 "$ROOT/deploy/lock_cameras.py" >> "$LAUNCH_LOG" 2>&1 || true

if grep -qE "is not a supported model format|stereo_callback failed|failed to acquire camera" "$LAUNCH_LOG" 2>/dev/null; then
    echo "WARNING: errors found in launch log, proceeding anyway..."
fi

echo "Warmup 30s..."
sleep 30

python3 "$ROOT/benchmarks/scripts/system_monitor.py" --duration 300 --out "$SYS_CSV" > /dev/null 2>&1 &
MON_PID=$!

TGT_TOPIC=""
ENH_TOPIC=""
STG_TOPIC=""
if [ "$DET" = "true" ]; then TGT_TOPIC="/stereo_down/targets"; STG_TOPIC="/stereo_down/timings"; fi
if [ "$ENH" = "true" ]; then ENH_TOPIC="/stereo/lx/image_enhanced"; fi

echo "Latency benchmark 120s..."
python3 "$ROOT/benchmarks/scripts/benchmark_pipeline.py" \
    --duration 120 \
    --out "$LAT_CSV" \
    --raw-topic /stereo/lx/camera/image_raw \
    --enhanced-topic "$ENH_TOPIC" \
    --targets-topic "$TGT_TOPIC" \
    --stages-topic "$STG_TOPIC"

wait $MON_PID 2>/dev/null || true

kill -9 $LAUNCH_PID 2>/dev/null || true
cleanup_camera_nodes

TEMP_END=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
echo "Final SoC temperature: ${TEMP_END}°C"

THR_END=$(vcgencmd get_throttled | cut -d= -f2)
CLK_END=$(vcgencmd measure_clock arm | cut -d= -f2)

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

echo "Cooldown 10s..."
sleep 10
echo "Ready for the next run."
