#!/bin/bash

#SBATCH --job-name=Data_Gen
#SBATCH --output=outputs/cluster_logs/data_gen_%j.out
#SBATCH --error=outputs/cluster_logs/data_gen_%j.err
#SBATCH --partition=students
#SBATCH --mem=256G
#SBATCH --cpus-per-task=32
#SBATCH --time=02:00:00

# Parallele Verarbeitung für Regex/Datenoperationen optimieren
export OMP_NUM_THREADS=32
export OPENBLAS_NUM_THREADS=32

PROJECT_DIR="/home/willilars@edu.local/Coding/Bachelor-Projekt"
cd $PROJECT_DIR

echo "🚀 Starte Pre-Processing: Generierung der Test-Suites (Mock-Graphen)..."

# Umgebung laden
source .venv/bin/activate
export PYTHONPATH=$PROJECT_DIR

# Die zu verarbeitenden Datensätze definieren
SPLITS=("data/lcquad_2_0.json")

for SPLIT in "${SPLITS[@]}"; do
    # Extrahiert den reinen Namen des Splits (z.B. "test" oder "train")
    SPLIT_NAME=$(basename "${SPLIT}" .json)
    
    echo "================================================================="
    echo "Verarbeite Datensatz: ${SPLIT} -> data/dump_${SPLIT_NAME}.json"
    echo "================================================================="
    
    # Aufruf mit Hydra-Overrides. 
    # Durch die dynamische Pfadangabe 'dump_${SPLIT_NAME}.json' wird ein Überschreiben verhindert.
    python src/data/data_generator.py \
        benchmark.dataset_path="${SPLIT}" \
        benchmark.output_path="data/dump_${SPLIT_NAME}.json"
    
done

echo "✅ Test-Suite erfolgreich generiert."