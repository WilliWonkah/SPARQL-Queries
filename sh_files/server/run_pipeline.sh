#!/bin/bash

#SBATCH --job-name=Server_Pipeline
#SBATCH --output=outputs/cluster_logs/combined_%j.out
#SBATCH --error=outputs/cluster_logs/combined_%j.err
#SBATCH --partition=students
#SBATCH --mem=256G
#SBATCH --cpus-per-task=32
#SBATCH --gres=gpu:a100:2
#SBATCH --time=24:00:00

PROJECT_DIR="..." # HIER ANPASSEN
cd $PROJECT_DIR

source .venv/bin/activate
export PYTHONPATH=$PROJECT_DIR

PORT=8000
export VLLM_CACHE_ROOT="/.vllm_cache"
export HF_HOME="$VLLM_CACHE_ROOT"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export VLLM_ATTENTION_BACKEND=XFORMERS

# =========================================================================
# 1. CACHE LÖSCHEN (vor jedem Start)
# =========================================================================
echo "🧹 Lösche vLLM/HF Cache..."
rm -rf "$VLLM_CACHE_ROOT"/*
mkdir -p "$VLLM_CACHE_ROOT"

# =========================================================================
# 2. ARGUMENTE AUFTEILEN
# =========================================================================
# Mapping: Hydra-Config-Name -> "Modell-Ordnername:Tensor-Parallel-Size"
declare -A MODEL_MAP=(
    ["qwen_72b_instruct"]="Qwen2.5-72B-Instruct:2"
    ["qwen_32b_coder"]="Qwen2.5-Coder-32B-Instruct:1"
    ["qwen_32b_instruct"]="Qwen2.5-32B-Instruct:1"
    ["qwen_7b_instruct"]="Qwen2.5-7B-Instruct:1"
    ["qwen_7b_coder"]="Qwen2.5-Coder-7B-Instruct:1"
    ["qwen_72b_instruct_awq"]="Qwen2.5-72B-Instruct-AWQ:2"
    ["qwen_32b_coder_awq"]="Qwen2.5-Coder-32B-Instruct-AWQ:1"
    ["qwen_32b_instruct_awq"]="Qwen2.5-32B-Instruct-AWQ:1"
    ["qwen_7b_instruct_awq"]="Qwen2.5-7B-Instruct-AWQ:1"
    ["qwen_7b_coder_awq"]="Qwen2.5-Coder-7B-Instruct-AWQ:1"
    ["qwen_72b_instruct_gptq_int8"]="Qwen2.5-72B-Instruct-GPTQ-Int8:2"
    ["qwen_32b_coder_gptq_int8"]="Qwen2.5-Coder-32B-Instruct-GPTQ-Int8:1"
    ["qwen_32b_instruct_gptq_int8"]="Qwen2.5-32B-Instruct-GPTQ-Int8:1"
    ["qwen_7b_instruct_gptq_int8"]="Qwen2.5-7B-Instruct-GPTQ-Int8:1"
    ["qwen_7b_coder_gptq_int8"]="Qwen2.5-Coder-7B-Instruct-GPTQ-Int8:1"
)

MODEL_NAME=""
TP=1
HYDRA_ARGS=""

for arg in "$@"; do
    if [[ "$arg" == model=* ]]; then
        MODEL_ARG="${arg#model=}"
        if [ -n "${MODEL_MAP[$MODEL_ARG]+x}" ]; then
            MODEL_NAME="${MODEL_MAP[$MODEL_ARG]%:*}"   # Teil vor dem ":"
            TP="${MODEL_MAP[$MODEL_ARG]#*:}"           # Teil nach dem ":"
        else
            echo "❌ Unbekanntes Modell: '$MODEL_ARG'"
            echo "   Verfügbar: ${!MODEL_MAP[@]}"
            exit 1
        fi
    fi
    # ALLES an Hydra weiterreichen, auch model=...
    HYDRA_ARGS="$HYDRA_ARGS $arg"
done

# Fallback, wenn gar kein model= übergeben wurde
if [ -z "$MODEL_NAME" ]; then
    echo "⚠️ Kein model= Override angegeben. Nutze Default: qwen_32b_coder"
    MODEL_NAME="Qwen2.5-Coder-32B-Instruct"
    TP=1
fi

# =========================================================================
# 3. GPU SETUP
# =========================================================================
if [ "$TP" -eq 2 ]; then
    export CUDA_VISIBLE_DEVICES=0,1
else
    export CUDA_VISIBLE_DEVICES=0
fi

# VRAM bereinigen
echo "🧹 Bereinige VRAM..."
pkill -9 -u $USER -f vllm 2>/dev/null
lsof -t /dev/nvidia* 2>/dev/null | xargs -r kill -9 2>/dev/null
sleep 3

# =========================================================================
# 4. MODELL KOPIEREN (falls nötig)
# =========================================================================
LOCAL_MODEL_PATH="/models/${MODEL_NAME}"
SOURCE_MODEL_PATH="$PROJECT_DIR/models/${MODEL_NAME}"

if [ ! -d "$LOCAL_MODEL_PATH" ]; then
    echo "📦 Kopiere Modell ${MODEL_NAME}..."
    mkdir -p "/tmp/willilars/models"
    rsync -a "$SOURCE_MODEL_PATH/" "$LOCAL_MODEL_PATH/"
fi

# =========================================================================
# 5. SERVER STARTEN (Background)
# =========================================================================
echo "🚀 Starte vLLM Server im Hintergrund..."
python -m vllm.entrypoints.openai.api_server \
    --model "$LOCAL_MODEL_PATH" \
    --tensor-parallel-size "$TP" \
    --gpu-memory-utilization 0.90 \
    --max-model-len 4096 \
    --enforce-eager \
    --disable-custom-all-reduce \
    --port "$PORT" \
    > "outputs/cluster_logs/vllm_server_${SLURM_JOB_ID}.log" 2>&1 &

VLLM_PID=$!
echo "📡 Server PID: $VLLM_PID"

# =========================================================================
# 6. AUF SERVER WARTEN
# =========================================================================
export VLLM_API_BASE="http://localhost:${PORT}/v1"
TIMEOUT=1800
ELAPSED=0

echo "⏳ Warte auf vLLM Server..."
while true; do
    if curl -s "${VLLM_API_BASE}/models" > /dev/null 2>&1; then
        echo "✅ vLLM Server ist bereit!"
        break
    fi
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "❌ Timeout beim Warten auf den Server."
        kill -9 $VLLM_PID 2>/dev/null
        exit 1
    fi
    sleep 5
    ELAPSED=$((ELAPSED+5))
done

# =========================================================================
# 7. PIPELINE AUSFÜHREN
# =========================================================================
echo "🚀 Starte Evaluierungs-Pipeline..."
echo "   Hydra Args: $HYDRA_ARGS"

python src/main.py \
    benchmark.dataset_path="data/dump_lcquad_2_0.json" \
    $HYDRA_ARGS

PIPELINE_EXIT=$?
echo "📊 Pipeline beendet mit Exit-Code: $PIPELINE_EXIT"

# =========================================================================
# 8. AUFRÄUMEN & BEENDEN
# =========================================================================
echo "🛑 Stoppe vLLM Server..."
kill -TERM $VLLM_PID 2>/dev/null
sleep 2
kill -9 $VLLM_PID 2>/dev/null

echo "🧹 Finaler Cleanup..."
rm -rf "$VLLM_CACHE_ROOT"/*

echo "✅ Job komplett. Beende SLURM-Job."
exit $PIPELINE_EXIT