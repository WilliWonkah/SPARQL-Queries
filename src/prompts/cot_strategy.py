from prompts.base_strategy import PromptStrategy

class CoTStrategy(PromptStrategy):
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


        return f"""You are an expert in translating natural language to Wikidata SPARQL.

{context_block}
Question: {question}

Instructions:
- Pay attention to the direction of the relations (subject vs. object).
- If the question asks for a specific type (e.g., 'What country'), use wdt:P31 (instance of) if applicable.
- YOU MUST include the necessary Wikidata prefixes in your SPARQL query.
{schema_instructions}

Please think step-by-step. Wrap your reasoning in <think>...</think> tags. In your reasoning:
1. Identify the Subject and Object from the context.
2. Determine the correct path direction.
3. Evaluate the Constraints below to decide on the structural topology (e.g., direct vs. reified properties).
4. Construct the query logically.

IMPORTANT: You MUST end your response with exactly this format:

<think>
[Your step-by-step thinking process here]
</think>
```sparql
[YOUR COMPLETE SPARQL QUERY HERE]
```

Constraints:
- CRITICAL SYNTAX: Use direct properties (wdt:P...) for all basic relations.
- CRITICAL SYNTAX: DO NOT use reified statement structures (p:P... / ps:P...) UNLESS the question explicitly requires temporal constraints, qualifiers, or ranking.
- CRITICAL SYNTAX: The query MUST match the simplest, most direct canonical form possible.
- STRICTLY output ONLY the code block at the end.
- NO conversational filler (e.g., "Here is your query:").
"""