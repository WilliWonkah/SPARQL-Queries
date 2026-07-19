from prompts.base_strategy import PromptStrategy

class FewShotStrategy(PromptStrategy):
    def generate_prompt(self, question: str, schema_context: str) -> str:
        
        is_no_schema = "parametric knowledge" in schema_context
        
        if is_no_schema:
            context_block = ""
            schema_instructions = "- Rely completely on your internal knowledge to recall the correct Wikidata Q-IDs and P-IDs."
        else:
            context_block = f"Context (Schema & Entities):\n{schema_context}\n"
            schema_instructions = (
                "- STRICT SCHEMA COMPLIANCE: You MUST ONLY use the Q-IDs and P-IDs provided in the Context.\n"
                "- Do not invent or infer external properties."
            )

        # 3 Diverse Beispiele zur Format-Konditionierung für Wikidata.
        # Die Beispiele demonstrieren die strikte Trennung von wdt: (Standard) und p:/ps: (Ausnahme für Qualifiers).
        examples = """
Example 1 (Standard wdt: usage for simple relations):
Question: Which country has Angela Merkel as head of government?
Context: Entities: wd:Q567, wd:Q6256 | Properties: wdt:P6, wdt:P31
Query: 
```sparql
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

SELECT ?sbj WHERE { ?sbj wdt:P6 wd:Q567 . ?sbj wdt:P31 wd:Q6256 . }
```

Example 2 (EXCEPTION: Using p:/ps: because of a temporal qualifier):
Question: What was the population of Paris in 2010?
Context: Entities: wd:Q90 | Properties: p:P1082, ps:P1082, pq:P585
Query:
```sparql
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>

SELECT ?obj WHERE { 
        wd:Q90 p:P1082 ?s . 
        ?s ps:P1082 ?obj . 
        ?s pq:P585 ?time 
        FILTER(CONTAINS(YEAR(?time), '2010')) 
}
```

Example 3 (Multi-Hop / Graph Join with standard wdt:):
Question: Who is the spouse of the author of Harry Potter?
Context: Entities: wd:Q8337 | Properties: wdt:P50, wdt:P26
Query:
```sparql
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

SELECT ?spouse WHERE { wd:Q8337 wdt:P50 ?author . ?author wdt:P26 ?spouse . }
```
"""
        return f"""You are an expert in translating natural language to Wikidata SPARQL.

Instructions:
- Pay attention to the direction of the relations (subject vs. object).
- If the question asks for a specific type (e.g., 'What country'), use wdt:P31 (instance of) if applicable.
- YOU MUST include the necessary Wikidata prefixes in your SPARQL query.
{schema_instructions}
- Directly output the final SPARQL query enclosed in ```sparql ... ``` tags without any explanation.

{examples}

Constraints:
- CRITICAL SYNTAX: Use direct properties (wdt:P...) for all basic relations.
- CRITICAL SYNTAX: DO NOT use reified statement structures (p:P... / ps:P...) UNLESS the question explicitly requires temporal constraints, qualifiers, or ranking (as shown in Example 2).
- CRITICAL SYNTAX: The query MUST match the simplest, most direct canonical form possible.
- NO conversational filler (e.g., "Here is your query:").

Now, answer the following:

{context_block}
Question: {question}
Query:
"""