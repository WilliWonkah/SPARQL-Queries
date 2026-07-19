import hydra
import asyncio
import logging
import os
import json
from omegaconf import DictConfig, OmegaConf
from hydra.utils import to_absolute_path
from urllib import response

from utils import set_deterministic_seed

from inference.engine import VLLMEngine

from validation.syntax_parser import SyntaxParser
from validation.execution_engine import create_executor, QueryExecutionError
from validation.schema_linker import SchemaLinker
from validation.semantic_checker import SemanticChecker

from data.types import EvalInstance
from data.lcquad_loader import LCQuadLoader

from metrics.evaluator import Evaluator
from metrics.exporter import ResultExporter

from prompts.cot_strategy import CoTStrategy
from prompts.no_shot_strategy import NoShotStrategy
from prompts.few_shot_strategy import FewShotStrategy

log = logging.getLogger(__name__)

# =========================================================================
# FACTORIES & HELPER
# =========================================================================

def create_prompt_strategy(strategy_name: str):
    strategies = {
        "no_shot": NoShotStrategy,
        "few_shot": FewShotStrategy,
        "cot": CoTStrategy
    }
    if strategy_name not in strategies:
        raise ValueError(f"Unbekannte Prompt-Strategie: {strategy_name}")
    return strategies[strategy_name]()

def create_engine(cfg: DictConfig):
    model_name = cfg.model.get("model_name")

    if not model_name:
        raise ValueError("Kein model_name in der Konfiguration (cfg.model.model_name) definiert!")

    log.info(f"[Setup] Initialisiere vLLM Engine: {model_name}")
    return VLLMEngine(
        model_name=model_name,
        temperature=cfg.model.get("temperature", 0.0),
        max_tokens=cfg.model.get("max_tokens", 512)
    )

def get_schema_context(mode: str, gt_query: str) -> str:
    # Die komplette Ableitungslogik ist nun zentral in SchemaLinker.get_context gesichert.
    return SchemaLinker.get_context(mode, gt_query)

def classify_gt_error(error_msg: str) -> str:
    """Best-effort-Einordnung von GT-Abstürzen anhand der Fehlermeldung."""
    msg = error_msg.lower()
    if "service" in msg:
        return "service_call"
    if any(k in msg for k in ("parse", "syntax", "expected", "bad escape")):
        return "parse_error"
    if any(k in msg for k in ("type", "convert", "literal", "datatype", "numeric", "date", "year")):
        return "filter_or_literal"
    return "other"

# =========================================================================
# ASYNCHRONE BATCH-LOGIK
# =========================================================================

async def run_pipeline(dataset: list, cfg: DictConfig, engine, executor, evaluator):
    concurrency_limit = cfg.execution.get("max_concurrent_tasks", 100)
    sem = asyncio.Semaphore(concurrency_limit)
    prompt_gen = create_prompt_strategy(cfg.prompt.prompt_strategy)

    drop_log = []  # sammelt alle GT-bedingten Ausschlüsse dieser Konfiguration

    log.info(f"[Execution] Starte Pipeline für {len(dataset)} Instanzen...")

    # 1. Instanziierung
    eval_instances = []
    for dp in dataset:
        schema_context = get_schema_context(cfg.schema_injection_depth, dp['sparql_gt'])
        prompt = prompt_gen.generate_prompt(dp['question'], schema_context)
        eval_instances.append(EvalInstance(dp=dp, prompt=prompt, schema_context=schema_context))

    # 2. Generierung (LLM-Requests) — PARALLEL für Geschwindigkeit
    async def fetch_llm_response(instance: EvalInstance, sem: asyncio.Semaphore):
        async with sem:
            response = await engine.generate(instance.prompt)
            instance.response = response
            return instance

    llm_tasks = [fetch_llm_response(inst, sem) for inst in eval_instances]
    await asyncio.gather(*llm_tasks)

    log.info("[Execution] Generierung beendet. Starte Validierung...")

    # 3. Evaluierung & Ausführung — SERIELL für rdflib-Thread-Safety
    async def evaluate_single(inst: EvalInstance):
        res = inst.response
        generated_text = res["text"]
        dp = inst.dp

        evaluator.metrics["total_processed"] += 1
        full_gt_query = "\n".join(SyntaxParser.WIKIDATA_PREFIXES.values()) + "\n\n" + dp['sparql_gt']

        # 1. GROUND TRUTH AUSFÜHRUNG
        gt_results_per_suite = []
        gt_is_executable = True

        for g_idx, suite_graph in enumerate(dp['test_suite']):
            try:
                # DON'T add prefixes here - they're already in suite_graph!
                gt_set = executor.execute_query_on_graph(dp['sparql_gt'], suite_graph)
                gt_results_per_suite.append(gt_set)
            except QueryExecutionError as e:
                log.error(f"UID {dp['uid']}: GT query crashed on graph {g_idx}: {e}")
                evaluator.metrics["dropped_gt_crash"] += 1
                drop_log.append({
                    "uid": dp["uid"],
                    "reason": "gt_crash",
                    "category": classify_gt_error(str(e)),
                    "graph_index": g_idx,
                    "error": str(e)[:300],
                })
                gt_is_executable = False
                break

        if not gt_is_executable:
            return
        if not gt_results_per_suite:
            evaluator.metrics["dropped_empty_suite"] += 1
            drop_log.append({"uid": dp["uid"], "reason": "empty_suite",
                             "category": "empty_suite", "graph_index": None, "error": ""})
            return
        if len(gt_results_per_suite[0]) == 0:
            evaluator.metrics["dropped_empty_signal"] += 1
            drop_log.append({"uid": dp["uid"], "reason": "empty_signal",
                             "category": "empty_signal", "graph_index": 0, "error": ""})
            return

        # 2. SYNTAX-PRÜFUNG
        pred_query = SyntaxParser.extract_sparql(generated_text)
        is_valid_syntax = SyntaxParser.is_valid_sparql(pred_query)

        # 3. SEMANTIK & PRED-QUERY AUSFÜHRUNG
        pred_set = set()
        strict_execution_accuracy = 0.0
        test_suite_pass_rate = 0.0
        signal_accuracy = 0.0
        robustness_score = 0.0
        jaccard_similarity = 0.0
        h_entities, h_properties = set(), set()
        is_schema_conform = False
        pred_is_executable = False

        # LOKALES DICT für stratified scores
        type_scores = {
            "signal": [],
            "noise_decoy": [],
            "noise_stress": [],
            "inversion": [],
            "empty": []
        }

        if is_valid_syntax:
            check_context = inst.schema_context
            if "parametric knowledge" in check_context:
                is_schema_conform = True
                h_entities, h_properties = set(), set()
            else:
                is_schema_conform, h_entities, h_properties = SemanticChecker.is_schema_conform(pred_query, check_context)

            suite_scores = []
            jaccard_scores = []
            pred_is_executable = True

            for i, suite_graph in enumerate(dp['test_suite']):
                try:
                    pred_set = executor.execute_query_on_graph(pred_query, suite_graph)
                    gt_set = gt_results_per_suite[i]

                    # Categorize graph type
                    if i == 0:
                        graph_type = "signal"
                    elif i in [1, 2, 3]:
                        graph_type = "noise_decoy"
                    elif i in [4, 5, 6]:
                        graph_type = "noise_stress"
                    elif i in [7, 8]:
                        graph_type = "inversion"
                    else:
                        graph_type = "empty"
                    
                    # A. Exact match per graph
                    graph_match = (pred_set == gt_set)
                    suite_scores.append(1.0 if graph_match else 0.0)
                    type_scores[graph_type].append(1.0 if graph_match else 0.0)

                    # B. Jaccard similarity
                    intersection = len(pred_set & gt_set)
                    union = len(pred_set | gt_set)
                    if union > 0:
                        jaccard_scores.append(intersection / union)
                    else:
                        jaccard_scores.append(1.0 if len(pred_set) == len(gt_set) == 0 else 0.0)

                except QueryExecutionError as e:
                    log.warning(f"[Pipeline] UID {dp['uid']}: Pred-Query crasht auf Suite {i} - {e}")
                    pred_is_executable = False
                    suite_scores.append(0.0)
                    jaccard_scores.append(0.0)

            if suite_scores:
                test_suite_pass_rate = sum(suite_scores) / len(suite_scores)
                signal_accuracy = suite_scores[0]
                robustness_score = sum(suite_scores[1:]) / len(suite_scores[1:]) if len(suite_scores) > 1 else 0.0
                strict_execution_accuracy = 1.0 if all(s == 1.0 for s in suite_scores) else 0.0

            if jaccard_scores:
                jaccard_similarity = sum(jaccard_scores) / len(jaccard_scores)

        # 4. METRIKEN PUSHEN
        evaluator.update(
            uid=dp['uid'],
            question=dp['question'],
            prompt=inst.prompt,
            pred_query=pred_query,
            gt_query=full_gt_query,
            is_valid_syntax=is_valid_syntax,
            is_schema_conform=is_schema_conform,
            hallucinated_entities=h_entities,
            hallucinated_properties=h_properties,
            strict_execution_accuracy=strict_execution_accuracy,
            test_suite_pass_rate=test_suite_pass_rate,
            signal_accuracy=signal_accuracy,
            robustness_score=robustness_score,
            jaccard_similarity=jaccard_similarity,
            type_scores=type_scores,
            is_executable=pred_is_executable,
            ttft=res.get("ttft", 0.0),
            tps=res.get("tps", 0.0),
            num_tokens=res.get("num_tokens", 0)
        )

    # Evaluation SERIELL
    for inst in eval_instances:
        await evaluate_single(inst)
    
    return drop_log

# =========================================================================
# HAUPTPROGRAMM
# =========================================================================

@hydra.main(version_base=None, config_path="../configs", config_name="config")
def main(cfg: DictConfig):
    set_deterministic_seed(cfg.get("seed", 42))
    log.info(f"--- Starte Validierungs-Pipeline ---\nKonfiguration:\n{OmegaConf.to_yaml(cfg)}")

    entities_path = to_absolute_path("data/resource/entities_covered")
    predicates_path = to_absolute_path("data/resource/predicates_with_frequency")
    SchemaLinker.load_empirical_noise(entities_path, predicates_path)

    dataset_path = cfg.benchmark.get("dataset_path", "data/dump_lcquad_2_0.json")
    limit = cfg.benchmark.get("limit", None)

    dataset = LCQuadLoader(to_absolute_path(dataset_path)).load_data(limit=limit, filter_invalid_gt=True)
	
    engine = create_engine(cfg)
    executor = create_executor(cfg)
    evaluator = Evaluator()

    drop_log = asyncio.run(run_pipeline(dataset, cfg, engine, executor, evaluator))

    model_tag = cfg.model.get("model_name", "unknown").replace("/", "_")
    drop_log_path = to_absolute_path(
        f"outputs/drop_log_{model_tag}_{cfg.prompt.prompt_strategy}_{cfg.schema_injection_depth}.jsonl"
    )
    with open(drop_log_path, "w", encoding="utf-8") as f:
        for entry in drop_log:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log.info(f"Drop-Log geschrieben: {drop_log_path} ({len(drop_log)} Einträge)")

    sorted_detailed_results = sorted(evaluator.detailed_results, key=lambda x: int(x["uid"]))

    ResultExporter.export_to_json(
        config_dict=OmegaConf.to_container(cfg, resolve=True),
        summary=evaluator.get_summary(),
        detailed_results=sorted_detailed_results,
        output_dir=to_absolute_path("outputs")
    )

    evaluator.print_summary()

    log.info(f"Detailed results: {len(evaluator.detailed_results)}")

if __name__ == "__main__":
    main()
