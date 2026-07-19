import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

log = logging.getLogger(__name__)

class ResultExporter:
    """Kapselt ausschließlich den JSON-Export der Pipeline-Resultate (SRP-Konform)."""
    
    @staticmethod
    def export_to_json(config_dict: Dict[str, Any], summary: Dict[str, Any], detailed_results: list, output_dir: str, prefix: str = "run_results") -> None:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(output_dir, f"{prefix}_{timestamp}.json")

        export_data = {
            "config": config_dict,
            "summary": summary,
            "detailed_results": detailed_results
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=4, ensure_ascii=False)

        log.info(f"[Export] Ergebnisse erfolgreich gespeichert unter: {filename}")