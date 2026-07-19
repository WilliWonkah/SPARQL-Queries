# 🎓 Bachelorarbeit: Optimierung der LLM-basierten SPARQL-Generierung

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Dieses Repository enthält den Code, die Daten und die Auswertungsskripte für meine Bachelorarbeit. Die Arbeit untersucht die Generierung von SPARQL-Abfragen durch Large Language Models (LLMs) mit besonderem Fokus auf Prompting-Strategien, Kontext-Optimierung und den Auswirkungen von Modell-Quantisierung.

## 🎯 Zentrale Leitfrage

> **Inwiefern beeinflussen Prompting-Techniken, die Präzision des Schema-Kontexts sowie die Gewichtsquantisierung die syntaktische Validität und Ausführbarkeit generierter SPARQL-Abfragen durch Allzweck- und Code-spezifische Sprachmodelle?**

Im Rahmen der Arbeit werden Modelle (insbesondere *Qwen2.5* als Allzweckmodell und *Qwen2.5-Coder* als Code-Modell) hinsichtlich ihrer Resilienz gegenüber Quantisierungsverlusten sowie ihrer Reaktion auf unterschiedliche Prompting- und Schema-Injektionsstrategien evaluiert.

## 📊 Untersuchte Dimensionen & Metriken

**Evaluationsmetriken:**
- **Syntaktische Validität:** Ist die generierte SPARQL-Abfrage nach den offiziellen Grammatikregeln korrekt?
- **Strict Execution Accuracy:** Führt die Abfrage auf dem Ziel-Graphen zum exakt korrekten und erwarteten Ergebnis?

**Experimentelle Variablen:**
1. **Prompting-Strategien:** Zero-Shot vs. Few-Shot vs. Chain-of-Thought (CoT)
2. **Schema-Injektion:** Kein Schema vs. Volles Schema vs. Pruned Schema (gefiltert/präzise)
3. **Modell-Quantisierung:** Unquantisiert (Referenz) vs. 8-Bit vs. 4-Bit
4. **Modell-Typen:** General-Purpose (Qwen2.5) vs. Code-spezifisch (Qwen2.5-Coder)

## 📂 Projektstruktur
```sh
Bachelor/
├── .git/
├── .env/                           # Enthält Hugging-Face Token
├── .venv/                          # Von uv verwaltete virtuelle Umgebung (Ignoriert)
├── .gitignore                 
├── pyproject.toml                  # Projektmetadaten und Abhängigkeiten (Hydra, rdflib, vLLM)
├── uv.lock                         # Deterministischer Lock-File (Muss zwingend ins Git!)
├── README.md                       # Dokumentation des Labor-Setups und der Pipeline
│
├── data/                           # Lokaler Datenordner (Inhalte via .gitignore ignoriert)
│   ├── resource/                   # Unveränderter 'resource' Ordner vom originalen LC-QuAD 2.0
│   │	├── entities_covered
│   │	└── predicates_with_frequency
│   ├── lcquad_2_0.json/            # LC-QuAD 2.0 Datensatz              
│   └── dump_lcquad_2_0.json/       # Test Suites für die Validierung
│
├── models/                         # Lokale Modellgewichte (z.B. AWQ/GPTQ) (Ignoriert)
│
├── outputs/                        # Von Hydra automatisch generierte Logs (aufgeräumt)
│   └── YYYY-MM-DD/                 # Enthält pro Run: Logs, Ergebnisse und config.yaml-Kopie
│
├── notebooks/                      # Jupyter Notebooks für Tests (Ignoriert)
│   └── ...ipynb
├── temp/                           # Explortive Pyhton-Skripte (Ignoriert)
│   └── ...py
│
├── sh_files/                       # Slurm-Job-Skripte für die Laborinfrastruktur
│   ├── data/                       
│   │	├── generate_data.sh        # Generiert die Test Suites
│   │	└── verify_data.sh          # Prüft die Test Suites auf Fehler nach der Generierung
│   │
│   ├── download_models/            # Lädt ...           
│   │	├── 1_full_models.sh        # volle Modelle herunter
│   │	└── 2_quant_models.sh       # die quantisierten Modelle herunter
│   │
│   └── server/                      
│   	└── run_pipeline.sh         # Führt Experimente auf dem HPC-Cluster durch.
│
├── configs/                        # Hydra Konfigurationsverzeichnis (Deklarativ)
│   ├── config.yaml                 # Hauptkonfiguration (Einstiegspunkt für Defaults)
│   ├── model/                      # LLM-Spezifikationen (z.B. llama3.yaml, deepseek.yaml)
│   ├── prompt/                     # Prompt-Hyperparameter (z.B. cot.yaml, php.yaml)
│   └── benchmark/                  # Datensatz-Konfigurationen (z.B. lcquad.yaml)
│
└── src/                            # Ausführbarer Quellcode der Pipeline
    ├── __init__.py
    │
    ├── data/              	        # Zur Handhabung des Datensatzes & dessen Generierung
    │  	├── data_generator.py       # Generiert die Test Suites
    │  	├── lcquad_loader.py        # Ladet die Daten
    │  	├── types.py        
    │   └── verify_data.py          # Prüft die Test Suites
    │
    ├── inference/                  # Gekapselte vLLM-Logik
    │   └── engine.py               # GPU-Server Anbindung & Request-Handling
    │
    ├── metrics/                    # Metriken für die Evaluation
    │  	├── evaluator.py            # Berechnung der Metriken
    │   └── exporter.py             # Exportiert die Werte vom evaluator.py
    │
    ├── prompts/                    # Strategy-Pattern für Prompt-Generierung
    │   ├── base_strategy.py        # Abstrakte Basisklasse (Interface)
    │   ├── no_shot_strategy.py     # Zero-Shot Implementierung
    │   ├── few_shot_strategy.py    # Few-Shot Implementierung
    │   └── cot_strategy.py         # Chain-of-Thought Implementierung
    │
    ├── validation/                 # Trennung von Syntax und Semantik + Metrikberechnungen/Überprüfung
    │   ├── execution_engine.py     # Führt die generierten SPARQL-Abfragen auf der Datenbank aus
    │   ├── schema_linker.py        # Bereitet den Graphen-Kontext für Text-to-SPARQL-Modelle vor
    │   ├── syntax_parser.py        # Offline-Prüfung via rdflib
    │   └── execution_engine.py     # Online-Abfrage gegen Triple-Store (z.B. Virtuoso)
    │
    ├── main.py                     # Zentraler Einstiegspunkt (mit @hydra.main dekoriert)
    └── utils.py                    # Random-Seed setzen
```

## 🚀 Installation & Setup

1. **Repository klonen:**
   ```bash
   git clone https://github.com/DEIN_NAME/DEIN_REPO.git
   cd DEIN_REPO
   ```

2. **Umgebung erstellen & Abhängigkeiten installieren (mit `uv`):**
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```

## ⚙️ Ausführung & Pipeline (Slurm)

Die gesamten Experimente, das Herunterladen der Modelle und das Aufsetzen der Server sind in modulare Shell-Skripte unterteilt und für die Ausführung auf einem Rechencluster via Slurm (`sbatch`) konfiguriert. 

Die Skripte können vor der Ausführung in den jeweiligen `.sh`-Dateien bei Bedarf an spezifische Anforderungen angepasst werden.

## WICHTIG: 
Vor Start der Pipeline müssen Ordnerpfade in den Configs & .sh files angegeben/angepasst werden.
Ebenfalls muss im .env der Hugging-Face Token angegeben werden für einen schnellen download der Modelle.

### 1. Modelle herunterladen
Lädt die benötigten Large Language Models in den Cache.
```bash
# Unquantisierte Modelle herunterladen:
sbatch sh_files/download_models/1_full_models.sh

# Quantisierte Modelle herunterladen:
sbatch sh_files/download_models/2_quant_models.sh
```

### 2. Daten einrichten
Bevor die Evaluierungspipeline starten kann, muss der LC-QuAD 2.0 Datensatz heruntergeladen werden und die Test-Suites generiert werden.
[![Offizieller LInk zu LC-QuAD 2.0](https://figshare.com/projects/LCQuAD_2_0/62270)]

#### WICHTIG: 
Vor Generierung der Daten: In 'configs/benchmark/lcquad_2_0.yaml' 'dataset_path' auf data/lcquad_2_0.json verweisen, um Daten zu generieren. Dannach kann es wieder auf 'data/dump_lcquad_2_0.json' verwiesen werden.

```bash
sbatch sh_files/data/generate_data.sh      # Test-Suites generieren
sbatch sh_files/data/verify_data.sh        # Daten evaluieren (1,77% fehlgeschlagen)
```

### 3. LLM Server & Eval Pipeline starten
Sobald Daten bereit sind, können die Sprachmodelle geladen und die eigentlichen Generierungs- und Evaluierungsschritte ausgeführt werden.

**Pipeline starten:**
```bash
bash sh_files/server/run_pipeline.sh

# Optional mit Spezifikationen (genaue Variationen können dem config.yaml entnommen werden):
bash sh_files/server/run_pipeline.sh model=qwen_72b_instruct prompt=cot schema_injection_depth=full
```

### 4. Data Coverage überprüfen
Um die Abdeckung und Qualität der geladenen Daten zu evaluieren (setzt Schritt 2 *Data-Server einrichten* voraus):
```bash
sbatch sh_files/server/start_servers.sh
sbatch sh_files/data/evaluate_coverage.sh
```

---

## ✍️ Autor
**Lars Willi**  
Bachelorarbeit im Studiengang Computational and Data Science
Fachhochschule Graubünden