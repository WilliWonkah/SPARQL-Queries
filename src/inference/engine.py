import time
import logging
from openai import AsyncOpenAI

log = logging.getLogger(__name__)

class VLLMEngine:
    def __init__(self, model_name: str, temperature: float = 0.0, max_tokens: int = 512):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.port = 8000 
        
        self.client = AsyncOpenAI(
            api_key="EMPTY", 
            base_url=f"http://localhost:{self.port}/v1"
        )
        log.info(f"[vLLM Client] Asynchron verbunden mit API Server auf Port {self.port} (Streaming-Modus)")

    async def generate(self, prompt: str) -> dict:
        start_time = time.perf_counter()
        ttft = 0.0
        generated_text = ""
        num_tokens = 0

        try:
            response_stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=42,
                stop=["```\n", "```\r", "``` ", "<|im_end|>"],
                stream=True,
                stream_options={"include_usage": True}
            )
            
            async for chunk in response_stream:
                # Zeiterfassung beim Eintreffen des allerersten Tokens
                if ttft == 0.0:
                    ttft = time.perf_counter() - start_time # HIER WAR time.time()
                
                # Text aggregieren
                if chunk.choices and chunk.choices[0].delta.content:
                    generated_text += chunk.choices[0].delta.content
                
                # Token-Usage aus dem finalen Chunk extrahieren
                if chunk.usage:
                    num_tokens = chunk.usage.completion_tokens

            generation_time = time.perf_counter() - start_time
            
            # WISSENSCHAFTLICHER FIX: Isolation der Decode-Phase für TPS
            decode_time = generation_time - ttft
            if decode_time > 0 and num_tokens > 1:
                tps = (num_tokens - 1) / decode_time
            elif generation_time > 0:
                tps = num_tokens / generation_time # Fallback bei nur 1 Token
            else:
                tps = 0.0
            
            return {
                "text": generated_text.strip(), 
                "ttft": ttft, 
                "tps": tps, 
                "num_tokens": num_tokens
            }
            
        except Exception as e:
            log.error(f"[vLLM Client] Fehler bei der API-Anfrage: {e}")
            return {"text": "", "ttft": 0.0, "tps": 0.0, "num_tokens": 0}