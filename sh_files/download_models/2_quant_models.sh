#!/bin/bash

#SBATCH --job-name=hf_download_quant
#SBATCH --output=outputs/cluster_logs/download_quant_%j.out
#SBATCH --error=outputs/cluster_logs/download_quant_%j.err
#SBATCH --partition=students
#SBATCH --mem=64G
#SBATCH --cpus-per-task=32
#SBATCH --time=24:00:00

# === Konfiguration ===
PROJECT_DIR="/home/willilars@edu.local/Coding/Bachelor-Projekt"
TARGET_DIR="/tmp/willilars/models"

# WICHTIGER HINWEIS:
# Qwen veroeffentlicht AWQ offiziell nur als 4-Bit-Quantisierung ("-AWQ").
# Eine offizielle 8-Bit-AWQ-Variante existiert nicht. Als 8-Bit-Version
# stellt Qwen offiziell GPTQ-Int8 bereit ("-GPTQ-Int8") – ebenfalls eine
# 8-Bit-Gewichtsquantisierung und kompatibel mit vLLM, Transformers und TGI.

# === Umgebung aktivieren (venv mit uv) ===
cd "$PROJECT_DIR" || { echo "✗ Projektverzeichnis nicht gefunden: $PROJECT_DIR"; exit 1; }
source .venv/bin/activate
echo "✓ venv aktiviert"

# Prüfen ob uvx verfügbar ist
if ! command -v uvx &> /dev/null; then
    echo "✗ uvx nicht gefunden! Einmalig im aktivierten venv nachinstallieren: pip install uv"
    exit 1
fi

# === .env laden ===
ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo "✓ Lade HF_TOKEN aus $ENV_FILE"
    export HF_TOKEN=$(grep "^HF_TOKEN=" "$ENV_FILE" | cut -d '=' -f2)
else
    echo "✗ .env nicht gefunden unter: $ENV_FILE"
    echo "  Erstelle die Datei mit: echo 'HF_TOKEN=hf_...' > $ENV_FILE"
    exit 1
fi

# Prüfen ob Token geladen wurde
if [ -z "$HF_TOKEN" ] || [ "$HF_TOKEN" = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" ]; then
    echo "✗ HF_TOKEN ist leer oder noch ein Platzhalter!"
    echo "  Bitte füge deinen echten Token in $ENV_FILE ein."
    exit 1
fi

echo "✓ Token geladen (beginnt mit: ${HF_TOKEN:0:10}...)"

# === Ordner erstellen ===
echo ""
echo "=== Schritt 1: Ordner erstellen ==="
mkdir -p "$TARGET_DIR"
echo "✓ Zielverzeichnis $TARGET_DIR ist bereit."

# === Modelle herunterladen ===
echo ""
echo "=== Schritt 2: Modelle herunterladen (8-Bit GPTQ-Int8 + 4-Bit AWQ) ==="

download_model() {
    local model_name=$1
    local target_path="$TARGET_DIR/$(basename $model_name)"
    
    echo ""
    echo "Lade $model_name..."
    
    # Überspringe wenn bereits vorhanden
    if [ -d "$target_path" ] && [ "$(ls -A $target_path)" ]; then
        echo "  → Bereits vorhanden, überspringe"
        return 0
    fi
    
    # Download mit Token
    uvx --from huggingface-hub hf download "$model_name" \
        --local-dir "$target_path" \
        --token "$HF_TOKEN"
    
    if [ $? -eq 0 ]; then
        echo "  ✓ Erfolgreich"
    else
        echo "  ✗ Fehler beim Download"
        return 1
    fi
}

# Qwen2.5-Coder-32B-Instruct
download_model "Qwen/Qwen2.5-Coder-32B-Instruct-GPTQ-Int8"
download_model "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"

# Qwen2.5-32B-Instruct
download_model "Qwen/Qwen2.5-32B-Instruct-GPTQ-Int8"
download_model "Qwen/Qwen2.5-32B-Instruct-AWQ"

# Qwen2.5-72B-Instruct
download_model "Qwen/Qwen2.5-72B-Instruct-GPTQ-Int8"
download_model "Qwen/Qwen2.5-72B-Instruct-AWQ"

# Qwen2.5-Coder-7B-Instruct
download_model "Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int8"
download_model "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"

# Qwen2.5-7B-Instruct
download_model "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int8"
download_model "Qwen/Qwen2.5-7B-Instruct-AWQ"

echo ""
echo "=== Fertig! Alle Modelle in $TARGET_DIR ==="