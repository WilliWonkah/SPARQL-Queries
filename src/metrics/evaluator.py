import logging
import re
from typing import Set, Dict, Any
from rdflib.term import Variable
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery

log = logging.getLogger(__name__)

class Evaluator:
    def __init__(self):
        self.metrics = {
            "total_processed": 0, 
            "dropped_gt_crash": 0,
            "dropped_empty_suite": 0,
            "dropped_empty_signal": 0,
            "evaluated_queries": 0,
            "executable_queries": 0,
            "syntax_valid": 0,
            "schema_conform": 0,
            "hallucinations": 0,
            "algebraic_equivalences": 0,         
            "co_occurring_reification_mismatch": 0,
            "strict_execution_accuracy_scores": [], 
            "test_suite_pass_rates": [],
            "signal_accuracies": [],
            "robustness_scores": [],
            "jaccard_similarities": [],
            "ttft_list": [],
            "tps_list": [],
        }
        self.detailed_results = []

    @staticmethod
    def _canonicalize_ast(node: Any) -> Any:
        """
        Rekursive Kanonisierung des SPARQL Abstract Syntax Tree (AST).
        Löst das Kommutativitäts-Problem bei BGPs, Joins und Unions.
        """
        from rdflib.plugins.sparql.parserutils import CompValue

        if isinstance(node, CompValue):
            # 1. Neuen Knoten instanziieren, um den originalen AST nicht zu mutieren
            new_node = CompValue(node.name)
            
            # 2. Post-Order Traversierung (Kinder zuerst kanonisieren)
            for k, v in node.items():
                new_node[k] = Evaluator._canonicalize_ast(v)
                
            # 3. Kommutative Operatoren sortieren
            if node.name == 'BGP' and 'triples' in new_node:
                # Tripel innerhalb eines Basic Graph Patterns sind als Set kommutativ
                new_node['triples'] = sorted(new_node['triples'], key=lambda t: str(t))

            elif node.name in ('Join', 'Union') and 'p1' in new_node and 'p2' in new_node:
                # Join und Union sind (für Sets) kommutativ: p1 und p2 deterministisch anordnen
                str_p1 = str(new_node['p1'])
                str_p2 = str(new_node['p2'])
                if str_p1 > str_p2:
                    new_node['p1'], new_node['p2'] = new_node['p2'], new_node['p1']

            return new_node

        elif isinstance(node, list):
            # Listen (z. B. Projektionsvariablen im SELECT) beibehalten, aber Elemente kanonisieren
            return [Evaluator._canonicalize_ast(item) for item in node]
        else:
            # Primitive Datentypen (URIRef, Variable, Literal) unverändert zurückgeben
            return node

    @staticmethod
    def _anonymize_variables(node: Any, var_mapping: dict) -> Any:
        """
        Ersetzt alle rdflib.term.Variable durch sequenzielle Platzhalter (z.B. ?v0, ?v1).
        Muss zwingend NACH der Kanonisierung (Sortierung) aufgerufen werden, 
        um deterministisches Mapping zu garantieren.
        """
        from rdflib.plugins.sparql.parserutils import CompValue

        if isinstance(node, Variable):
            var_name = str(node)
            if var_name not in var_mapping:
                var_mapping[var_name] = f"v{len(var_mapping)}"
            return Variable(var_mapping[var_name])

        elif isinstance(node, CompValue):
            new_node = CompValue(node.name)
            # Deterministische Traversierung über sortierte Keys ist zwingend
            for k, v in sorted(node.items()):
                new_node[k] = Evaluator._anonymize_variables(v, var_mapping)
            return new_node

        elif isinstance(node, list):
            return [Evaluator._anonymize_variables(item, var_mapping) for item in node]
        else:
            return node

    @staticmethod
    def calculate_algebraic_equivalence(pred_query: str, gt_query: str) -> bool:
        if not pred_query or not gt_query: return False

        try:
            # 1. Parsen und in relationale Algebra (AST) übersetzen
            pred_algebra = translateQuery(parseQuery(pred_query))
            gt_algebra = translateQuery(parseQuery(gt_query))
            
            # 2. AST kanonisieren (löst strukturelle Kommutativität auf)
            pred_canon = Evaluator._canonicalize_ast(pred_algebra)
            gt_canon = Evaluator._canonicalize_ast(gt_algebra)
            
            # 3. Variablen anonymisieren (Homomorphismus-Mapping auf dem sortierten Baum)
            pred_anon = Evaluator._anonymize_variables(pred_canon, {})
            gt_anon = Evaluator._anonymize_variables(gt_canon, {})
            
            # 4. Kanonischen String-Abgleich durchführen
            return str(pred_anon) == str(gt_anon)
        except Exception:
            return False

    @staticmethod
    def check_constraint_violation(pred_query: str, gt_query: str) -> bool:
        """
        Prüft, ob die Vorhersage p:/ps: (Reifizierung) nutzt, 
        obwohl die Ground Truth strikt wdt: (direkt) verwendet.
        """
        if not pred_query or not gt_query: return False

        gt_uses_reification = " p:" in gt_query or " ps:" in gt_query or " pq:" in gt_query
        pred_uses_reification = " p:" in pred_query or " ps:" in pred_query

        return pred_uses_reification and not gt_uses_reification

    def update(self, uid: str, question: str, prompt: str, pred_query: str, gt_query: str, 
               is_valid_syntax: bool, is_schema_conform: bool, 
               hallucinated_entities: Set[str], hallucinated_properties: Set[str], 
               strict_execution_accuracy: float, test_suite_pass_rate: float,
               signal_accuracy: float, robustness_score: float, jaccard_similarity: float,
               type_scores: Dict[str, list],
               is_executable: bool, 
               ttft: float, tps: float, num_tokens: int) -> None:

        self.metrics["evaluated_queries"] += 1

        if is_valid_syntax:
            self.metrics["syntax_valid"] += 1
            if is_schema_conform:
                self.metrics["schema_conform"] += 1
            else:
                self.metrics["hallucinations"] += 1

        algebraic_matches = self.calculate_algebraic_equivalence(pred_query, gt_query)
        if algebraic_matches:
            self.metrics["algebraic_equivalences"] += 1

        constraint_violated = self.check_constraint_violation(pred_query, gt_query)
        if constraint_violated and strict_execution_accuracy == 0.0:
            self.metrics["co_occurring_reification_mismatch"] += 1

        if is_executable:
            self.metrics["executable_queries"] += 1
            self.metrics["strict_execution_accuracy_scores"].append(strict_execution_accuracy) 

        self.metrics["test_suite_pass_rates"].append(test_suite_pass_rate)
        self.metrics["signal_accuracies"].append(signal_accuracy)
        self.metrics["robustness_scores"].append(robustness_score)
        self.metrics["jaccard_similarities"].append(jaccard_similarity)

        self.metrics["ttft_list"].append(ttft)
        self.metrics["tps_list"].append(tps)

        self.detailed_results.append({
            "uid": uid,
            "is_executable": is_executable,
            "question": question,
            "pred_query": pred_query,
            "gt_query": gt_query,
            "is_valid_syntax": is_valid_syntax,
            "is_schema_conform": is_schema_conform,
            "constraint_violated": constraint_violated, 
            "algebraic_matches": algebraic_matches,
            "strict_execution_accuracy": strict_execution_accuracy,
            "test_suite_pass_rate": test_suite_pass_rate,
            "signal_accuracy": signal_accuracy,
            "robustness_score": robustness_score,
            "jaccard_similarity": jaccard_similarity,
            "type_scores": type_scores,
            "metrics": {"ttft": ttft, "tps": tps, "num_tokens": num_tokens}
        })

    def get_summary(self) -> Dict[str, Any]:
        total_proc = self.metrics["total_processed"]
        t_all = self.metrics["evaluated_queries"]       
        t_exec = self.metrics["executable_queries"]     
        t_syntax = self.metrics["syntax_valid"]
        t_dropped = (self.metrics["dropped_gt_crash"]
                     + self.metrics["dropped_empty_suite"]
                     + self.metrics["dropped_empty_signal"])

        type_tprs = {}
        for result in self.detailed_results:
            for gtype, scores in result.get("type_scores", {}).items():
                if gtype not in type_tprs:
                    type_tprs[gtype] = []
                type_tprs[gtype].extend(scores)

        if t_all == 0: return {}

        def avg(key):
            return sum(self.metrics[key]) / t_all if t_all > 0 else 0.0

        return {
            "dataset_total": total_proc,
            "dropped_queries": t_dropped,
            "drop_rate_percent": (t_dropped / total_proc * 100) if total_proc > 0 else 0,
            "drop_breakdown": {
                "gt_crash": self.metrics["dropped_gt_crash"],
                "empty_suite": self.metrics["dropped_empty_suite"],
                "empty_signal": self.metrics["dropped_empty_signal"],
                "gt_crash_percent": (self.metrics["dropped_gt_crash"] / total_proc * 100) if total_proc > 0 else 0,
                "empty_signal_percent": (self.metrics["dropped_empty_signal"] / total_proc * 100) if total_proc > 0 else 0,
            },
            "evaluated_n_total": t_all,
            "evaluated_n_executable": t_exec,
            "syntax_accuracy_percent": (t_syntax / t_all * 100),
            "schema_conformity_percent": (self.metrics["schema_conform"] / t_syntax * 100) if t_syntax > 0 else 0.0,
            "hallucination_rate_percent": (self.metrics["hallucinations"] / t_syntax * 100) if t_syntax > 0 else 0.0,
            "isomorphism_violation_rate_percent": (self.metrics["co_occurring_reification_mismatch"] / t_all * 100),
            "algebraic_equivalence_rate_percent": (self.metrics["algebraic_equivalences"] / t_all * 100), 
            "strict_execution_accuracy": (sum(self.metrics["strict_execution_accuracy_scores"]) / t_exec) if t_exec > 0 else 0.0,
            "test_suite_pass_rate": avg("test_suite_pass_rates"),
            "stratified_tpr": {k: sum(v)/len(v) for k, v in type_tprs.items() if v},
            "signal_accuracy": avg("signal_accuracies"),
            "robustness_score": avg("robustness_scores"),
            "avg_jaccard_similarity": avg("jaccard_similarities"),
            "avg_ttft_sec": sum(self.metrics["ttft_list"]) / t_all,
            "avg_tps_per_query": sum(self.metrics["tps_list"]) / t_all
        }

    def print_summary(self) -> None:
        summary = self.get_summary()
        if not summary: return

        log.info("\n========================================================")
        log.info("                 EVALUATION SUMMARY")
        log.info("========================================================")
        log.info(f"Dataset Total:         {summary['dataset_total']}")
        log.info(f"Dropped:               {summary['dropped_queries']} ({summary['drop_rate_percent']:.2f}%)")
        log.info(f"Evaluated Subset (N):  {summary['evaluated_n_total']}")
        log.info("--------------------------------------------------------")
        log.info(f"Strict Execution Accuracy:  {summary['strict_execution_accuracy']:.4f}")
        log.info(f"Test-Suite Pass Rate:       {summary['test_suite_pass_rate']:.4f}")
        log.info(f"Stratified TPR:             {summary['stratified_tpr']}")
        log.info(f"Signal Accuracy:            {summary['signal_accuracy']:.4f}")
        log.info(f"Robustness Score:           {summary['robustness_score']:.4f}")
        log.info(f"Avg Jaccard Similarity:     {summary['avg_jaccard_similarity']:.4f}")
        log.info(f"Isomorphismus-Fehler:       {summary['isomorphism_violation_rate_percent']:.2f}%")
        log.info(f"Syntaktische Validität:{summary['syntax_accuracy_percent']:.2f}%")
        log.info("--------------------------------------------------------")
        log.info("              ZUSÄTZLICHE METRIKEN & LOGS")
        log.info("--------------------------------------------------------")
        log.info(f"Schema-Konformität:    {summary['schema_conformity_percent']:.2f}%")
        log.info(f"Halluzinationsrate:    {summary['hallucination_rate_percent']:.2f}% (Vocabulary Fehler)")
        log.info(f"Algebraische Äquivalenz: {summary['algebraic_equivalence_rate_percent']:.2f}%")
        log.info(f"Reification Mismatch Rate (bei False Negatives): {summary['isomorphism_violation_rate_percent']:.2f}%")
        log.info("--------------------------------------------------------")
        log.info("                 PERFORMANCE METRIKEN")
        log.info("--------------------------------------------------------")
        log.info(f"Avg TTFT (Latenz):     {summary['avg_ttft_sec']:.4f} s")
        log.info(f"Avg Throughput (TPS):  {summary['avg_tps_per_query']:.2f} tokens/s")
        log.info("========================================================")