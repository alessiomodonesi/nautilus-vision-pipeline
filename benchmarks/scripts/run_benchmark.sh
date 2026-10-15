#!/bin/bash
# lancia un singolo run di benchmark per una config.
# uso: ./run_benchmark.sh <config> <run_n>
#   config: A_baseline | B_pt | B_ov | C_pt | C_ov
#   run_n:  1 | 2 | 3

set -e

CONFIG="$1"
RUN_N="$2"

if [ -z "$CONFIG" ] || [ -z "$RUN_N" ]; then
    echo "Uso: $0 <config> <run_n>"
    echo "  config: A_baseline | B_pt | B_ov | C_pt | C_ov"
    echo "  run_n:  1 | 2 | 3"
    exit 1
fi

ROOT="$HOME/nautilus-vision-pipeline"
WS="$ROOT/ros2_ws"
DATE=$(date +%Y-%m-%d)
CSV_DIR="$ROOT/benchmarks/results/csv"
mkdir -p "$CSV_DIR"

# interpreta config
case "$CONFIG" in
    A_baseline) ENH="false"; DET="false"; PARAMS="detection_params_pt.yaml"; NOTE="baseline solo camera" ;;
    B_pt)       ENH="false"; DET="true";  PARAMS="detection_params_pt.yaml"; NOTE="yolov8n.pt half_res=True" ;;
    B_ov)       ENH="false"; DET="true";  PARAMS="detection_params_ov.yaml"; NOTE="OpenVINO FP32 half_res=False" ;;
    C_pt)       ENH="true";  DET="true";  PARAMS="detection_params_pt.yaml"; NOTE="full pipeline .pt" ;;
    C_ov)       ENH="true";  DET="true";  PARAMS="detection_params_ov.yaml"; NOTE="full pipeline OpenVINO" ;;
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
echo "Params file: ${PARAMS}"

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

# lancio pipeline in background
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=$ENH \
    enable_detection:=$DET \
    enable_saving:=false \
    enable_metrics:=true \
    enable_debug:=false \
    params_file:=$PARAMS \
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
if [ "$DET" = "true" ]; then TGT_TOPIC="/stereo_down/targets"; fi
if [ "$ENH" = "true" ]; then ENH_TOPIC="/stereo/lx/image_enhanced"; fi

echo "Benchmark latenze 120s..."
python3 "$ROOT/benchmarks/scripts/benchmark_pipeline.py" \
    --duration 120 \
    --out "$LAT_CSV" \
    --raw-topic /stereo/lx/camera/image_raw \
    --enhanced-topic "$ENH_TOPIC" \
    --targets-topic "$TGT_TOPIC"

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
params_file,$PARAMS
soc_temp_initial_c,$TEMP
soc_temp_final_c,$TEMP_END
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