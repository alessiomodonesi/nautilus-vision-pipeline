#!/bin/bash
# usage: ./run_thermal_test.sh <config> <run_n>
#
# fase 7 — stress test termico.
# differenze rispetto a run_benchmark.sh (fase 6):
#   - sostituisce system_monitor.py + benchmark_pipeline.py con
#     thermal_stress_test.py (un csv unico, una riga al secondo, 3600 s)
#   - cooldown finale fino a SoC ≤ 45 °C
#   - --timings-topic solo per le config con detection attiva
# tutto il resto (governor, systemd stop, hardware unlock, lock cameras,
# launch, grep errori, metadata) è identico per rendere i due dataset
# confrontabili.

set -e

CONFIG="$1"
RUN_N="$2"
DURATION="${3:-3600}"

if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
    echo "ERROR: DURATION must be an integer, got '$DURATION'"
    exit 1
fi

if [ -z "$CONFIG" ] || [ -z "$RUN_N" ]; then
    echo "Usage: $0 <config> <run_n>"
    exit 1
fi

ROOT="$HOME/nautilus-vision-pipeline"
WS="$ROOT/ros2_ws"
DATE=$(date +%Y-%m-%d)
CSV_DIR="$ROOT/benchmarks/thermal_results/csv"
mkdir -p "$CSV_DIR"

source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

if [ -f "$HOME/nautilus-vision-pipeline/pipeline_config.env" ]; then
    source "$HOME/nautilus-vision-pipeline/pipeline_config.env"
fi

case "$CONFIG" in
    T_baseline)   ENH="false"; DET="false"; MODEL="";                                HALF_RES="true";  IMGSZ="640"; NOTE="thermal baseline" ;;
    T_detection)  ENH="false"; DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="thermal detection" ;;
    T_full)       ENH="true";  DET="true";  MODEL="yolov8n_640_fp32_openvino_model"; HALF_RES="false"; IMGSZ="640"; NOTE="thermal full" ;;
    *) echo "Invalid config: $CONFIG"; exit 1 ;;
esac

cleanup_camera_nodes() {
    pkill -9 -f camera_node     2>/dev/null || true
    pkill -9 -f detection_node  2>/dev/null || true
    pkill -9 -f enhancement_node 2>/dev/null || true
    pkill -9 -f metrics_node    2>/dev/null || true
    sleep 1
}

# stop servizi e kill residui
sudo systemctl stop nautilus-bag.service      2>/dev/null || true
sudo systemctl stop nautilus-vision.service   2>/dev/null || true
sudo systemctl stop lock-cameras.service      2>/dev/null || true

pkill -f "ros2 bag record" 2>/dev/null || true
cleanup_camera_nodes

ros2 daemon stop  2>/dev/null || true
ros2 daemon start 2>/dev/null || true
sleep 3

# governor CPU → performance
CUR_GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
if [ "$CUR_GOV" != "performance" ]; then
    echo "Setting CPU governor: ${CUR_GOV} -> performance"
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null 2>&1 || true
    sleep 1
fi
echo "CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

# attesa stabilità termica prima di iniziare (idle plateau)
echo "Waiting for thermal stability before start..."
PREV=-999
STABLE_COUNT=0
for i in $(seq 1 60); do
    T=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
    T_INT=${T%.*}
    DIFF=$((T_INT - PREV))
    if [ "$PREV" -ne -999 ] && [ "$DIFF" -ge -1 ] && [ "$DIFF" -le 1 ]; then
        STABLE_COUNT=$((STABLE_COUNT + 1))
    else
        STABLE_COUNT=0
    fi
    if [ "$STABLE_COUNT" -ge 3 ]; then
        echo "SoC stable at ${T}°C"
        break
    fi
    echo "  temp=${T}°C (delta ${DIFF}°C, stable=${STABLE_COUNT}/3)"
    PREV=$T_INT
    sleep 5
done
TEMP=$T

THR_START=$(vcgencmd get_throttled | cut -d= -f2)
CLK_START=$(vcgencmd measure_clock arm | cut -d= -f2)

# path output
THERMAL_CSV="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_thermal.csv"
LAUNCH_LOG="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_launch.log"
META="$CSV_DIR/${DATE}_${CONFIG}_run${RUN_N}_metadata.csv"

# override launch
OVERRIDES=()
if [ -n "$MODEL" ];    then OVERRIDES+=("model_filename_override:=$MODEL"); fi
if [ -n "$HALF_RES" ]; then OVERRIDES+=("half_res_override:=$HALF_RES"); fi
if [ -n "$IMGSZ" ];    then OVERRIDES+=("imgsz_override:=$IMGSZ"); fi
if [ "$ENH" = "true" ]; then
    OVERRIDES+=("input_type_override:=enhanced")
else
    OVERRIDES+=("input_type_override:=raw")
fi

# hardware unlock
echo "Unlocking camera hardware..."
sudo fuser -k -9 /dev/video0 /dev/video1 2>/dev/null || true
sleep 1

# launch pipeline
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_enhancement:=$ENH \
    enable_detection:=$DET \
    enable_metrics:=true \
    enable_debug:=false \
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

# stress test termico
TIMINGS_ARG=""
TIMINGS_META="none"
if [ "$DET" = "true" ]; then
    TIMINGS_ARG="--timings-topic /stereo_down/timings"
    TIMINGS_META="/stereo_down/timings"
fi

echo "Thermal test ${DURATION}s → $THERMAL_CSV"
python3 "$ROOT/benchmarks/scripts/thermal_stress_test.py" \
    --duration "$DURATION" \
    --out "$THERMAL_CSV" \
    $TIMINGS_ARG || true

ROWS=$(wc -l < "$THERMAL_CSV" 2>/dev/null || echo 0)
EXPECTED=$((DURATION + 1))   # +1 header
if [ "$ROWS" -lt $((EXPECTED / 2)) ]; then
    echo "WARNING: thermal CSV has only ${ROWS} rows (expected ~${EXPECTED})."
    echo "         Check the log of thermal_stress_test.py and the launch log."
fi

# cleanup
kill -9 $LAUNCH_PID 2>/dev/null || true
cleanup_camera_nodes

TEMP_END=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
echo "Final SoC temperature: ${TEMP_END}°C"

THR_END=$(vcgencmd get_throttled | cut -d= -f2)
CLK_END=$(vcgencmd measure_clock arm | cut -d= -f2)

# metadata
COMMIT=$(cd "$ROOT" && git rev-parse HEAD 2>/dev/null || echo "unknown")
cat > "$META" <<EOF
field,value
commit_hash,$COMMIT
config,$CONFIG
run,$RUN_N
thermal_duration_s,$DURATION
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
timings_topic,$TIMINGS_META
EOF

# cooldown fino a stabilità termica (max 15 min)
echo "Cooldown: waiting for thermal stability..."
PREV=-999
STABLE_COUNT=0
for i in $(seq 1 90); do
    T=$(vcgencmd measure_temp | sed "s/temp=//;s/'C//")
    T_INT=${T%.*}
    DIFF=$((T_INT - PREV))
    if [ "$PREV" -ne -999 ] && [ "$DIFF" -ge -1 ] && [ "$DIFF" -le 1 ]; then
        STABLE_COUNT=$((STABLE_COUNT + 1))
    else
        STABLE_COUNT=0
    fi
    if [ "$STABLE_COUNT" -ge 3 ]; then
        echo "Cooldown complete: stable at ${T}°C"
        break
    fi
    echo "  temp=${T}°C (delta ${DIFF}°C, stable=${STABLE_COUNT}/3)"
    PREV=$T_INT
    sleep 10
done

echo "Ready for the next run."
