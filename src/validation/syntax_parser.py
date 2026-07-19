import re
import logging
from rdflib.plugins.sparql import prepareQuery

log = logging.getLogger(__name__)

# Unterdrückt Traceback-Warnungen von rdflib bei fehlerhaften LLM-Literalen
logging.getLogger("rdflib.term").setLevel(logging.ERROR)

class SyntaxParser:
    """Isoliert SPARQL-Code aus LLM-Outputs und validiert ihn."""

    # Vereinheitlichte Keys OHNE Doppelpunkt
    WIKIDATA_PREFIXES = {
        "wd": "PREFIX wd: <http://www.wikidata.org/entity/>",
        "wdt": "PREFIX wdt: <http://www.wikidata.org/prop/direct/>",
        "p": "PREFIX p: <http://www.wikidata.org/prop/>",
        "ps": "PREFIX ps: <http://www.wikidata.org/prop/statement/>",
        "pq": "PREFIX pq: <http://www.wikidata.org/prop/qualifier/>",
        "pr": "PREFIX pr: <http://www.wikidata.org/prop/reference/>",
        "psv": "PREFIX psv: <http://www.wikidata.org/prop/statement/value/>",
        "pqv": "PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>",
        "rdfs": "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>",
        "rv": "PREFIX rv: <http://www.wikidata.org/prop/reference/value/>",
        "rdf": "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>", 
        "skos": "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>",
        "bd": "PREFIX bd: <http://www.bigdata.com/rdf#>",
        "wikibase": "PREFIX wikibase: <http://wikiba.se/ontology#>",
        "wdtn": "PREFIX wdtn: <http://www.wikidata.org/prop/direct-normalized/>",
        "wds": "PREFIX wds: <http://www.wikidata.org/entity/statement/>",
        "schema": "PREFIX schema: <http://schema.org/>",
        "owl": "PREFIX owl: <http://www.w3.org/2002/07/owl#>",
        "xsd": "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
        "prov": "PREFIX prov: <http://www.w3.org/ns/prov#>",
        "geo": "PREFIX geo: <http://www.opengis.net/ont/geosparql#>",
        "mwapi": "PREFIX mwapi: <https://www.mediawiki.org/ontology#api/>",
        "dc": "PREFIX dc: <http://purl.org/dc/elements/1.1/>",
        "foaf": "PREFIX foaf: <http://xmlns.com/foaf/0.1/>"
    }

    @staticmethod
    def extract_sparql(text: str) -> str:
        extracted_query = ""
        markdown_pattern = r"\`{3}(?:sparql)?\s*(.*?)\s*\`{3}"
        match = re.search(markdown_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if match:
            extracted_query = match.group(1).strip()
        else:
            fallback_pattern = r"(?:PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b.*"
            match_fallback = re.search(fallback_pattern, text, re.DOTALL | re.IGNORECASE)
            
            if match_fallback:
                extracted_query = match_fallback.group(0).strip()
                last_brace = extracted_query.rfind('}')
                if last_brace != -1:
                    extracted_query = extracted_query[:last_brace+1]
                    
        if not extracted_query:
            log.warning("[Validation] Kein SPARQL-Block gefunden.")
            return ""

        # NEU: Entferne den Wikidata Label Service.
        # rdflib stürzt damit ab und LC-QuAD nutzt ohnehin rdfs:label.
        extracted_query = re.sub(r'SERVICE\s+wikibase:label\s*\{[^}]*\}', '', extracted_query, flags=re.IGNORECASE)
            
        missing_prefixes = []
        for prefix, prefix_decl in SyntaxParser.WIKIDATA_PREFIXES.items():
            if f"{prefix}:" in extracted_query:
                if not re.search(rf"PREFIX\s+{prefix}\s*:", extracted_query, re.IGNORECASE):
                    missing_prefixes.append(prefix_decl)
        
        if missing_prefixes:
            extracted_query = "\n".join(missing_prefixes) + "\n\n" + extracted_query

        return extracted_query

    @staticmethod
    def is_valid_sparql(query_string: str) -> bool:
        if not query_string: return False
        try:
            prepareQuery(query_string)
            return True
        except Exception as e:
            log.debug(f"[SyntaxParser] Parsing fehlgeschlagen: {e}\nQuery:\n{query_string}")
            return False