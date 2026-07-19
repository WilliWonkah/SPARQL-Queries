import json
import logging
import os
from typing import List, Dict, Any

log = logging.getLogger(__name__)

class LCQuadLoader:
    """
    Lädt, formatiert und bereinigt den LC-QuAD 2.0 Datensatz.
    Bereitet die Daten für die Text-to-SPARQL Evaluierungspipeline auf.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_data(self, limit: int = None, filter_invalid_gt: bool = True) -> List[Dict[str, Any]]:
        """
        Lädt die JSON-Datei und extrahiert die relevanten Felder.
        
        Args:
            limit (int, optional): Maximale Anzahl an Fragen (für schnelle lokale Tests).
            filter_invalid_gt (bool): Wenn True, werden Fragen ohne Ground-Truth übersprungen.
        """
        if not os.path.exists(self.file_path):
            log.error(f"Datensatz-Datei nicht gefunden: {os.path.abspath(self.file_path)}")
            raise FileNotFoundError(f"Datensatz-Datei nicht gefunden: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        processed_data = []
        skipped = 0

        for entry in raw_data:
            # LC-QuAD 2.0 spezifische Schlüssel
            # Manchmal ist die ID ein Integer, wir casten sicherheitshalber zu String
            uid = str(entry.get("uid", len(processed_data) + skipped))
            
            # Bei LCQuad 2.0 gibt es oft Variationen der Keys, hier fangen wir sie ab
            question = entry.get("question", "")
            if not question and "NL" in entry:  # Fallback für manche Versionen
                question = entry["NL"]
                
            sparql_gt = entry.get("sparql_wikidata", entry.get("sparql", ""))

            # Bereinigung: Wir brauchen zwingend eine Ground-Truth für den Evaluator
            if filter_invalid_gt and not sparql_gt.strip():
                skipped += 1
                continue
                
            # Extraktion der Test Suite
            test_suite = entry.get("test_suite", [])

            processed_data.append({
                "uid": uid,
                "question": question,
                "sparql_gt": sparql_gt,
                "test_suite": test_suite
            })

            # Vorzeitiger Abbruch, wenn das Limit (z.B. für Tests) erreicht ist
            if limit and len(processed_data) >= limit:
                break

        log.info(f"[Loader] {len(processed_data)} Fragen aus '{os.path.basename(self.file_path)}' geladen. "
                 f"({skipped} übersprungen wegen fehlender Ground-Truth).")
        
        return processed_data