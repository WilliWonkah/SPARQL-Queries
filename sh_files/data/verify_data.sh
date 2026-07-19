#!/bin/bash

#SBATCH --job-name=Verify_Data
#SBATCH --output=outputs/cluster_logs/verify_data_%j.out
#SBATCH --error=outputs/cluster_logs/verify_data_%j.err
#SBATCH --partition=students
#SBATCH --mem=64G                     
#SBATCH --cpus-per-task=16             
#SBATCH --time=01:00:00               

PROJECT_DIR="..." # HIER ANPASSEN
cd $PROJECT_DIR

echo "🚀 Starte Verifikation der generierten Test-Suites (Mock-Graphen)..."

# Umgebung laden
source .venv/bin/activate
export PYTHONPATH=$PROJECT_DIR

# Ausführen des Validierungs-Skripts
echo "================================================================="
echo "Führe Semantik-Test mit rdflib aus: src/data/verify_data.py"
echo "================================================================="

python src/data/verify_data.py

echo "✅ Verifikation beendet. Ergebnisse in der Log-Datei (outputs/cluster_logs/verify_data_*.out) prüfen."