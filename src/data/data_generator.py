import logging
import random
import json
import re
from typing import List, Tuple
from pathlib import Path
import hydra
from omegaconf import DictConfig

log = logging.getLogger(__name__)

class TestSuiteGenerator:
    PREFIXES = """@prefix wd: <http://www.wikidata.org/entity/> .
                @prefix wdt: <http://www.wikidata.org/prop/direct/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                @prefix p: <http://www.wikidata.org/prop/> .
                @prefix ps: <http://www.wikidata.org/prop/statement/> .
                @prefix pq: <http://www.wikidata.org/prop/qualifier/> .
                @prefix skos: <http://www.w3.org/2004/02/skos/core#> ."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        
        # 1. Echte Entitäten und Prädikate für Near-Miss-Decoys in den RAM laden
        self.entities = self._load_entities("data/resource/entities_covered")
        self.predicates = self._load_predicates("data/resource/predicates_with_frequency")

    def _load_entities(self, path: str) -> List[str]:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.startswith("Q")]

    def _load_predicates(self, path: str) -> List[str]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Wir nehmen nur die Top 100 Prädikate für realistische Fehler
            return [list(d.keys())[0] for d in data][:100]

    def _extract_triples(self, sparql_gt: str) -> List[Tuple[str, str, str]]:
        match = re.search(r'\{\s*(.*?)\s*\}', sparql_gt, re.IGNORECASE | re.DOTALL)
        if not match: return []
        
        triples = []
        # FIX: Splitte nur an Punkten, denen zwingend ein Leerzeichen vorausgeht.
        # Das schützt Dezimalzahlen (z.B. wd:4017.36) und IP-Adressen vor dem Zerreißen.
        for raw_triple in re.split(r'\s\.', match.group(1)):
            raw_triple = raw_triple.strip()
            if not raw_triple: continue
            
            # SPARQL Keywords abschneiden
            raw_triple = re.split(r'(?i)\b(FILTER|OPTIONAL|BIND|MINUS|ORDER|LIMIT)\b', raw_triple)[0].strip()
            if not raw_triple: continue
                
            parts = raw_triple.split(maxsplit=2)
            if len(parts) == 3:
                s, p, o = parts
                if " " in o and not o.startswith('"') and not o.startswith("'"):
                    o = o.replace(" ", "_")
                triples.append((s, p, o))
                
        return triples

    def _build_graph(self, triples: List[Tuple[str, str, str]], prefix: str, mutation: str = None) -> str:
        graph_triples = []
        for s, p, o in triples:
            # JOIN-FIX: Nutze den echten Variablennamen
            s_inst = f"wd:{prefix}_{s[1:]}" if s.startswith("?") else s
            o_inst = f"wd:{prefix}_{o[1:]}" if o.startswith("?") else o

            # Mutationen zwingend ausführen und "Accidental Truths" verhindern
            if mutation == "type" and (o.startswith("wd:") or o.startswith("?")):
                # Zwinge den Generator zu einem WIRKLICHEN Decoy
                for _ in range(10):
                    new_o = f"wd:{self.rng.choice(self.entities)}"
                    if new_o != o:
                        o_inst = new_o
                        break
            elif mutation == "relation":
                for _ in range(10):
                    new_p = f"wdt:{self.rng.choice(self.predicates)}"
                    if new_p != p:
                        p = new_p
                        break
            elif mutation == "inversion":
                # Verhindert, dass symmetrische Triples (A -> A) das exakte Signal reproduzieren
                if s_inst != o_inst:
                    s_inst, o_inst = o_inst, s_inst
                else:
                    p = f"wdt:{self.rng.choice(self.predicates)}" # Fallback: Prädikat ändern

            graph_triples.append(f"{s_inst} {p} {o_inst} .")
        
        return " ".join(graph_triples)

    def generate_suite(self, sparql_gt: str, uid: str) -> List[str]:
        triples = self._extract_triples(sparql_gt)
        if not triples:
            return [self.PREFIXES] * 10
            
        signal_graph = self._build_graph(triples, f"SIGNAL_{uid}")
        has_vars = any(s.startswith("?") or o.startswith("?") for s, _, o in triples)
        
        graphs = []
        
        # ---------------------------------------------------------
        # LOGIK FÜR ASK-QUERIES (Ohne Variablen)
        # ---------------------------------------------------------
        if not has_vars:
            # Graph 1: Nur Signal (GT = True)
            graphs.append(f"{self.PREFIXES} {signal_graph}")
            
            # Graph 2-4: Negative Graphen (NUR Decoys, KEIN Signal! GT = False)
            # Fängt übermäßig allgemeine Queries ab (z.B. mit ?p statt festem Prädikat)
            for i in range(2, 5):
                mut = self.rng.choice(["type", "relation"])
                decoy_only = self._build_graph(triples, f"DECOY_{i}_{uid}", mutation=mut)
                graphs.append(f"{self.PREFIXES} {decoy_only}")
                
            # Graph 5-7: Signal + Decoys (GT = True)
            # Fängt falsche Annahmen trotz vorhandenem Signal ab
            for i in range(5, 8):
                mut = self.rng.choice(["type", "relation"])
                decoy = self._build_graph(triples, f"DECOY_{i}_{uid}", mutation=mut)
                graphs.append(f"{self.PREFIXES} {signal_graph} {decoy}")
                
            # Graph 8-9: Invertierte Graphen (NUR Inversion, KEIN Signal! GT = False)
            for i in range(8, 10):
                decoy_inv = self._build_graph(triples, f"DECOY_INV_{i}_{uid}", mutation="inversion")
                graphs.append(f"{self.PREFIXES} {decoy_inv}")
                
            # Graph 10: Leerer Graph (GT = False)
            graphs.append(self.PREFIXES)
            
            return graphs

        # ---------------------------------------------------------
        # LOGIK FÜR SELECT-QUERIES (Mit Variablen)
        # ---------------------------------------------------------
        # Graph 1: Reines Signal
        graphs.append(f"{self.PREFIXES} {signal_graph}")

        # Graph 2-4: Standard-Fallen (Typ- und Relations-Decoys)
        for i in range(2, 5):
            mut = self.rng.choice(["type", "relation"])
            decoy = self._build_graph(triples, f"DECOY_{i}_{uid}", mutation=mut)
            graphs.append(f"{self.PREFIXES} {signal_graph} {decoy}")

        # Graph 5-7: Hohe Decoy-Anzahl (Stress-Test für Join-Operationen)
        for i in range(5, 8):
            stress_components = [signal_graph]
            for j in range(5):
                mut = self.rng.choice(["type", "relation"])
                stress_components.append(self._build_graph(triples, f"DECOY_STRESS_{i}_{j}_{uid}", mutation=mut))
            graphs.append(self.PREFIXES + " " + " ".join(stress_components))

        # Graph 8-9: Struktur-Inversionen (Prüfung auf falsche Subjekt-Objekt-Richtung)
        for i in range(8, 10):
            decoy_inv = self._build_graph(triples, f"DECOY_INV_{i}_{uid}", mutation="inversion")
            graphs.append(f"{self.PREFIXES} {signal_graph} {decoy_inv}")

        # Graph 10: Leerer Graph
        graphs.append(self.PREFIXES)

        return graphs

@hydra.main(version_base=None, config_path="../../configs", config_name="config")
def main(cfg: DictConfig) -> None:
    input_path = Path(hydra.utils.to_absolute_path(cfg.benchmark.dataset_path))
    output_path = Path(hydra.utils.to_absolute_path(cfg.benchmark.output_path))

    if not input_path.exists():
        log.error(f"Input-Datei nicht gefunden: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    generator = TestSuiteGenerator()
    log.info(f"Verarbeite {len(dataset)} Einträge aus {input_path}...")

    # DEBUG: Wir prüfen, ob die Schleife überhaupt in den Block eintritt
    count = 0
    for entry in dataset:
        sparql_query = entry.get("sparql_wikidata", "")
        uid = str(entry.get("uid", entry.get("id", "unknown")))
        
        if not sparql_query:
            continue # Überspringe Einträge ohne SPARQL
            
        try:
            entry["test_suite"] = generator.generate_suite(sparql_query, uid)
            count += 1
            if count % 1000 == 0:
                log.info(f"Fortschritt: {count} Einträge verarbeitet...")
        except Exception as e:
            log.error(f"Fehler bei UID {uid}: {e}")
            continue # Weiter machen, statt zu stoppen

    # DEBUG: Anstatt nur parent.mkdir, erzwinge einen absoluten Pfad und logge ihn
    out_dir = output_path.parent
    if not out_dir.exists():
        log.info(f"Erstelle Verzeichnis: {out_dir}")
        out_dir.mkdir(parents=True, exist_ok=True)
    
    log.info(f"Schreibe Datei nach: {output_path.absolute()}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=4, ensure_ascii=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
        
    log.info(f"✅ Generierung abgeschlossen. Daten gespeichert unter: {output_path}")

if __name__ == "__main__":
    main()