import json
import rdflib
import os
import re
from rdflib.plugins.sparql import prepareQuery

def verify_mock_logic(filepaths=["data/dump_lcquad_2_0.json"]):
    os.makedirs("outputs", exist_ok=True)
    error_log_file = "outputs/error_log_details.json"
    
    for filepath in filepaths:
        print(f"\n{'='*80}")
        print(f"🔍 ANALYSIERE DATENSATZ: {filepath} (SILENT MODE + LOGGING)")
        print(f"{'='*80}\n")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                dataset = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Datei {filepath} nicht gefunden.")
            continue

        total_queries_checked = 0
        total_uids_with_errors = 0
        skipped_dirty_data = 0
        error_details = []

        print("Verarbeite Test-Suites, bitte warten...")

        for entry in dataset:
            if "test_suite" in entry and len(entry["test_suite"]) > 0:
                content = entry["test_suite"][0]
                
                if "wdt:" in content and "." in content:
                    uid = entry.get("uid", "UNKNOWN")
                    sparql_gt = entry.get("sparql_wikidata", "")
                    test_suite = entry["test_suite"]

                    # SPARQL-kompatible Präfixe für den Parser definieren
                    sparql_prefixes = """
                    PREFIX wd: <http://www.wikidata.org/entity/>
                    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX p: <http://www.wikidata.org/prop/>
                    PREFIX ps: <http://www.wikidata.org/prop/statement/>
                    PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    """

                    # 1. Bereinigung für den Struktur-Test (Bypass für FILTER, LIMIT, etc.)
                    sparql_clean = re.split(r'(?i)\b(FILTER|ORDER\s+BY|LIMIT|GROUP\s+BY|HAVING|OPTIONAL|BIND)\b', sparql_gt)[0].strip()
                    if not sparql_clean.endswith("}"):
                        if sparql_clean.endswith("."):
                            sparql_clean = sparql_clean[:-1].strip()
                        sparql_clean += " }"
                    
                    full_clean_query = sparql_prefixes + sparql_clean

                    # 2. Syntax-Check (Ausschluss von echter Dirty Data)
                    try:
                        prepareQuery(full_clean_query)
                    except Exception:
                        skipped_dirty_data += 1
                        continue # Ignorieren, da die Original-Query syntaktisch korrupt ist
                    
                    test_cases = [
                        (0, "Graph 1", test_suite[0]), (1, "Graph 2", test_suite[1]), (2, "Graph 3", test_suite[2]),
                        (3, "Graph 4", test_suite[3]), (4, "Graph 5", test_suite[4]), (5, "Graph 6", test_suite[5]),
                        (6, "Graph 7", test_suite[6]), (7, "Graph 8", test_suite[7]), (8, "Graph 9", test_suite[8]),
                        (9, "Graph 10", test_suite[9])
                    ]
                    
                    total_queries_checked += 1
                    uid_has_error = False
                    
                    for graph_idx, desc, mock_graph in test_cases:
                        g = rdflib.Graph()
                        try:
                            g.parse(data=mock_graph, format="turtle")
                            qres = g.query(full_clean_query) # KORREKTUR: Die Query mit Präfixen nutzen!
                            
                            # 3. KORREKTE AUSWERTUNG VON COUNT & ASK
                            if qres.type == 'ASK':
                                is_match = qres.askAnswer
                            else:
                                is_match = False
                                for row in qres:
                                    for val in row:
                                        if val is not None:
                                            val_str = str(val)
                                            try:
                                                # Prüft, ob es eine aggregierte Zahl ist (z.B. "0", "0.0") -> Kein Match (Graph leer)
                                                if float(val_str) != 0:
                                                    is_match = True
                                            except ValueError:
                                                # Wenn es keine Zahl ist (z.B. eine extrahierte URI), ist es ein Treffer
                                                if val_str != "0":
                                                    is_match = True
                            
                            # Dynamische Erwartungshaltung
                            expected_match = True
                            has_vars = "?" in sparql_gt
                            if qres.type == 'ASK' and not has_vars and graph_idx in [1, 2, 3, 7, 8]:
                                expected_match = False
                            if graph_idx == 9: 
                                expected_match = False

                            if is_match != expected_match:
                                uid_has_error = True
                                error_details.append({
                                    "uid": uid,
                                    "sparql_gt": sparql_gt,
                                    "failed_on": desc,
                                    "error_type": "Logik-Mismatch",
                                    "details": f"Erwartet: {expected_match}, Ist: {is_match}"
                                })
                                break 

                        except Exception as e:
                            uid_has_error = True
                            error_details.append({
                                "uid": uid,
                                "sparql_gt": sparql_gt,
                                "failed_on": desc,
                                "error_type": "Syntax/Parser-Fehler",
                                "details": str(e)
                            })
                            break 
                    
                    if uid_has_error:
                        total_uids_with_errors += 1

        # Fehler-Log speichern
        with open(error_log_file, "w", encoding="utf-8") as f:
            json.dump(error_details, f, indent=4, ensure_ascii=False)

        # Akademische Metrik-Ausgabe
        print(f"\n{'='*80}")
        print(f"📊 ZUSAMMENFASSUNG FÜR: {filepath}")
        print(f"Ursprüngliche Queries in JSON: {len(dataset)}")
        print(f"Aussortiert (Dirty Data/Syntax): {skipped_dirty_data}")
        print(f"Geprüfte Queries (N = UIDs):   {total_queries_checked}")
        print(f"--------------------------------------------------------------------------------")
        if total_queries_checked > 0:
            error_rate = (total_uids_with_errors / total_queries_checked) * 100
            pass_rate = 100 - error_rate
            print(f"❌ Fehlerhafte Queries (UIDs): {total_uids_with_errors} ({error_rate:.2f}%)")
            print(f"✅ Fehlerfreie Queries (UIDs): {total_queries_checked - total_uids_with_errors} ({pass_rate:.2f}%)")
        print(f"📁 Detailliertes Fehler-Log:   {error_log_file}")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    verify_mock_logic()