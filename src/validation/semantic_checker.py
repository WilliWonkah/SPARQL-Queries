import re
import logging
from typing import Set, Tuple # WICHTIG: Tuple importieren!

log = logging.getLogger(__name__)

class SemanticChecker:
    """
    Führt semantische Constraint-Checks durch (Filter-Gate).
    Prüft, ob generierte Queries nur den bereitgestellten Schema-Kontext verwenden.
    """

    @staticmethod
    def extract_iris(text: str) -> Set[str]:
        """
        Extrahiert alle Wikidata-Entities (Q...) und Properties (P...) aus einem String.
        Robust gegenüber fehlenden PREFIX-Deklarationen (wie in LC-QuAD 2.0) sowie 
        absoluten URIs (wie sie oft von LLMs generiert werden).
        """
        if not text:
            return set()
            
        # 1. Deckt ab: wd:Q123, wds:Q123 sowie <.../entity/Q123>
        entities = set(re.findall(r'(?:wd:|wds:|entity/)(Q\d+)\b', text, re.IGNORECASE))
        
        # 2. Deckt ab: wdt:P123, p:P123, ps:P123 etc. sowie <.../prop/direct/P123>
        properties = set(re.findall(r'(?:wdt?|p|ps|pq|wdtn|psv|pqv|pr|rv|wds|prop/[a-z\-/]+)[:/](P\d+)\b', text, re.IGNORECASE))
        
        # 3. Normalisierung auf Uppercase zur Behebung von LLM-Case-Fehlern (z.B. wd:q123 -> Q123)
        entities = {e.upper() for e in entities}
        properties = {p.upper() for p in properties}
        
        return entities.union(properties)

    @staticmethod
    def is_schema_conform(sparql_query: str, schema_context: str) -> Tuple[bool, Set[str], Set[str]]:
        """
        Ebene 1 Check: Verwendet die Query ausschließlich erlaubte IRIs?
        WICHTIG: Erhält nur den reinen schema_context (Output des SchemaLinkers), 
        niemals den gesamten LLM-Prompt!
        """
        if not sparql_query:
            return False, set(), set()
            
        used_iris = SemanticChecker.extract_iris(sparql_query)
        allowed_iris = SemanticChecker.extract_iris(schema_context)
        
        # Dynamischer Bypass für Parametric Knowledge (no-schema Modus).
        # Da wir nur den schema_context prüfen, ist allowed_iris hier garantiert leer.
        # Muss auch hier leere Sets zurückgeben!
        if not allowed_iris and not used_iris:
            return True, set(), set()
        if not allowed_iris and used_iris:
            # Alles Generierte ist zwangsläufig eine Halluzination
            return False, {e for e in used_iris if e.startswith('Q')}, {p for p in used_iris if p.startswith('P')}
            
        # Prüfung auf Differenz: Verwendete IRIs, die nicht im RAG-Kontext existieren
        hallucinated = used_iris - allowed_iris
        
        if hallucinated:
            h_entities = {iri for iri in hallucinated if iri.startswith('Q')}
            h_properties = {iri for iri in hallucinated if iri.startswith('P')}
            log.warning(f"[SemanticChecker] Halluzinationen -> Entities: {h_entities}, Properties: {h_properties}")
            return False, h_entities, h_properties
            
        # KORREKTUR: Erfolgsfall am Ende muss zwingend auch leere Sets zurückgeben!
        return True, set(), set()