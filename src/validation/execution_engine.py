import logging
import time
from abc import ABC, abstractmethod
from typing import Set, Dict
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.error import HTTPError
import rdflib
from rdflib.namespace import XSD

# Verhindert Abstürze durch unsaubere Wikidata-Typen (Daten, historische Zeiten, Zahlen mit Kommata)
rdflib.term.bind(XSD.dateTime, str, constructor=str) 
rdflib.term.bind(XSD.date, str, constructor=str) 
rdflib.term.bind(XSD.integer, str, constructor=str) 

log = logging.getLogger(__name__)

class QueryExecutionError(Exception):
    """Wird geworfen, wenn die Query-Ausführung technisch fehlschlägt (Timeout, Syntax, Crash)."""
    pass

class BaseExecutor(ABC):
    @abstractmethod
    # Signatur-Update: Rückgabewert ist jetzt Set[tuple] statt Set[str]
    def execute_query(self, query: str) -> Set[tuple]:
        pass

class HTTPExecutor(BaseExecutor):
    def __init__(self, endpoint: str, delay_ms: int = 0):
        self.delay_ms = delay_ms
        self.sparql = SPARQLWrapper(endpoint)
        self.sparql.setReturnFormat(JSON)
        self.sparql.agent = "Bachelor3.0_Text2SPARQL_Eval/1.0"
        log.info(f"[ExecutionEngine] HTTP-Modus initialisiert. Endpoint: {endpoint}")

    def execute_query(self, query: str) -> Set[tuple]:
        if not query.strip(): return set()
        
        self.sparql.setQuery(query)
        if self.delay_ms > 0: 
            time.sleep(self.delay_ms / 1000.0)
            
        for attempt in range(3):
            try:
                results = self.sparql.query().convert()
                return self._extract_results(results)
            except HTTPError as e:
                if e.code == 429: 
                    time.sleep(2 ** attempt)
                else: 
                    # Aktives Werfen statt Maskieren
                    raise QueryExecutionError(f"HTTP Error {e.code}: {e.reason}")
            except Exception as e:
                raise QueryExecutionError(f"SPARQL Execution Error: {str(e)}")
        
        raise QueryExecutionError("Max retries exceeded (HTTP 429).")

    # Angepasste rdflib-Extraktion für Tupel
    def _extract_results(self, results: Dict) -> Set[tuple]:
        entities = set()
        if "results" in results and "bindings" in results["results"]:
            for binding in results["results"]["bindings"]:
                # Variablen deterministisch sortieren, um Projektionsreihenfolge zu fixieren
                sorted_vars = sorted(binding.keys())
                row_tuple = tuple(str(binding[var]["value"]).lower().strip() for var in sorted_vars)
                if row_tuple:
                    entities.add(row_tuple)
        elif "boolean" in results:
            entities.add((str(results["boolean"]).lower().strip(),))
        return entities

class LocalExecutor(BaseExecutor):
    def __init__(self, path: str):
        self.graph = rdflib.Graph()
        try:
            self.graph.parse(path, format="turtle")
            log.info(f"[ExecutionEngine] Lokaler Graph geladen: {path} ({len(self.graph)} Triples)")
        except FileNotFoundError:
            log.warning(f"[ExecutionEngine] Dump {path} nicht gefunden. Graph ist leer.")

    def execute_query(self, query: str) -> Set[tuple]:
        if not query.strip(): return set()
        try:
            results = self.graph.query(query)
            return self._extract_results(results)
        except Exception as e:
            # Crash an Pipeline weitergeben
            log.error(f"[ExecutionEngine] Ausführung fehlgeschlagen: {e}")
            raise QueryExecutionError(str(e))

    def _extract_results(self, results) -> Set[tuple]:
        entities = set()
        if getattr(results, "type", None) == "ASK":
            entities.add((str(bool(results)).lower().strip(),))
            return entities
            
        for row in results:
            # KORREKTUR: KEIN sorted() verwenden! Die Reihenfolge der row 
            # wird durch den AST vorgegeben und muss erhalten bleiben.
            row_tuple = tuple(
                (str(term.value).lower().strip() if isinstance(term, rdflib.Literal) else str(term).lower().strip())
                for term in row if term is not None
            )
            if row_tuple:
                entities.add(row_tuple)
        return entities

class TestSuiteExecutor(BaseExecutor):
    def __init__(self):
        log.info("[ExecutionEngine] TestSuite-Modus initialisiert (In-Memory Graph Parsing).")

    def execute_query(self, query: str) -> Set[tuple]:
        raise NotImplementedError("Nutze execute_query_on_graph für Test Suites.")

    def execute_query_on_graph(self, query: str, graph_ttl: str) -> Set[tuple]:
        if not query.strip(): return set()
        
        g = rdflib.Graph()
        try:
            # Graph direkt aus dem String der Test-Suite parsen
            g.parse(data=graph_ttl, format="turtle")
            results = g.query(query)
            return self._extract_results(results)
        except Exception as e:
            raise QueryExecutionError(f"TestSuite Execution Error: {str(e)}")

    # FEHLENDE METHODE HINZUGEFÜGT: Nutzt die gleiche rdflib-Logik wie der LocalExecutor
    def _extract_results(self, results) -> Set[tuple]:
        entities = set()
        if getattr(results, "type", None) == "ASK":
            entities.add((str(bool(results)).lower().strip(),))
            return entities
            
        for row in results:
            # KORREKTUR: sorted() ZWINGEND entfernen
            row_tuple = tuple(
                (str(term.value).lower().strip() if isinstance(term, rdflib.Literal) else str(term).lower().strip())
                for term in row if term is not None
            )
            if row_tuple:
                entities.add(row_tuple)
        return entities

def create_executor(cfg) -> BaseExecutor:
    mode = cfg.execution.mode
    if mode == "http":
        return HTTPExecutor(cfg.execution.endpoint_or_path, cfg.execution.delay_ms)
    elif mode == "local":
        return LocalExecutor(cfg.execution.endpoint_or_path)
    elif mode == "testsuite": # <--- NEU
        return TestSuiteExecutor()
    raise ValueError(f"Unbekannter Ausführungsmodus: {mode}")