import re
import logging
import random
import json
import hashlib
from typing import Set, List

log = logging.getLogger(__name__)
class RetrievedSchema:
    """Datenstruktur für das abgerufene Schema (Single Source of Truth)"""
    def __init__(self, entities: List[str], properties: List[str]):
        self.entities = entities
        self.properties = properties

class SchemaLinker:
    """
    Simuliert verschiedene Entity-Linking Strategien für Text-to-SPARQL Evaluierungen.
    """
    NOISE_PROPERTIES = []
    NOISE_ENTITIES = []

    @classmethod
    def load_empirical_noise(cls, entities_path: str, predicates_path: str):
        """
        Lädt die empirischen Verteilungen aus LC-QuAD 2.0 für realistischeres Graph-Retrieval.
        Pfade gemäss deiner Ordnerstruktur:
        data/resource/entities_covered
        data/resource/predicates_with_frequency
        """
        with open(entities_path, 'r', encoding='utf-8') as f:
            # Überspringt den Header "entity" in der ersten Zeile
            cls.NOISE_ENTITIES = [line.strip() for line in f.readlines() if line.startswith("Q")]
        
        with open(predicates_path, 'r', encoding='utf-8') as f:
            predicates_data = json.load(f)
            cls.NOISE_PROPERTIES = [list(d.keys())[0] for d in predicates_data]

    @classmethod
    def get_context(cls, mode: str, sparql_gt: str, num_distractors: int = 12, global_seed: int = None) -> str:
        """
        Hauptmethode für das Pipeline-Vorgehen.
        """
        # Safety-Check für die Statefulness
        if not cls.NOISE_ENTITIES or not cls.NOISE_PROPERTIES:
            log.warning("Empirischer Noise fehlt. 'load_empirical_noise()' wurde nicht aufgerufen!")
            
        if mode == "no_schema":
            return "Rely purely on your internal parametric knowledge."
            
        # Deterministischer Seed basierend auf der Query, falls kein globaler Seed erzwungen wird.
        # Garantiert Varianz zwischen Queries, aber 100% Reproduzierbarkeit pro Query.
        if global_seed is None:
            query_seed = int(hashlib.md5(sparql_gt.encode('utf-8')).hexdigest(), 16) % (2**32)
        else:
            query_seed = global_seed
            
        full_schema = cls._simulate_graph_retrieval(sparql_gt, num_distractors, query_seed)
        
        if mode == "full":
            return cls._format_schema_string(full_schema.entities, full_schema.properties)
            
        elif mode == "pruned":
            true_e = set(re.findall(r'wd:(Q\d+)', sparql_gt))
            PROPERTY_PATTERN = r'(?:wdt|p|ps|pq|wdtn|psv|pqv|pr|rv|wds):(P\d+)'
            true_p = set(re.findall(PROPERTY_PATTERN, sparql_gt))
            
            pruned_entities = [e for e in full_schema.entities if e in true_e]
            pruned_properties = [p for p in full_schema.properties if p in true_p]
            
            return cls._format_schema_string(pruned_entities, pruned_properties)
            
        raise ValueError(f"Unbekannter schema_mode: {mode}")

    @classmethod
    def _simulate_graph_retrieval(cls, sparql_gt: str, num_distractors: int, seed: int = 42) -> RetrievedSchema:
        """
        Simuliert den Graph-Retrieval-Prozess. 
        Nutzt einen lokalen Random-State für 100% Reproduzierbarkeit ohne globale Seiteneffekte.
        """
        # Lokaler Random Number Generator (RNG)
        rng = random.Random(seed)
        
        true_entities = set(re.findall(r'wd:(Q\d+)', sparql_gt))
        PROPERTY_PATTERN = r'(?:wdt|p|ps|pq|wdtn|psv|pqv|pr|rv|wds):(P\d+)'
        true_properties = set(re.findall(PROPERTY_PATTERN, sparql_gt))
        
        # Reihenfolge bleibt deterministisch, da aus Datei-Order abgeleitet
        safe_noise_props = [p for p in cls.NOISE_PROPERTIES if p not in true_properties]
        safe_noise_entities = [e for e in cls.NOISE_ENTITIES if e not in true_entities]
        
        # Sampling via lokalem RNG
        sampled_props = rng.sample(safe_noise_props, min(num_distractors, len(safe_noise_props)))
        sampled_entities = rng.sample(safe_noise_entities, min(num_distractors // 2, len(safe_noise_entities)))
        
        # Sortierung ist essenziell, da Set-Union nicht-deterministisch geordnet ist!
        all_entities = sorted(list(true_entities.union(set(sampled_entities))))
        all_properties = sorted(list(true_properties.union(set(sampled_props))))

        # Shuffling via lokalem RNG
        rng.shuffle(all_entities)
        rng.shuffle(all_properties)
        
        return RetrievedSchema(all_entities, all_properties)

    @staticmethod
    def _format_schema_string(entities: List[str], properties: List[str]) -> str:
        schema_lines = []
        if entities:
            schema_lines.append("Entities: " + ", ".join([f"wd:{e}" for e in entities]))
        if properties:
            schema_lines.append("Properties: " + ", ".join([f"wdt:{p}" for p in properties]))
            
        if not schema_lines:
            return "No specific schema provided."
            
        return " | ".join(schema_lines)