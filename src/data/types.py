from dataclasses import dataclass
from typing import Optional

@dataclass
class EvalInstance:
    """Strukturierte Kapselung pro Datenpunkt."""
    dp: dict
    prompt: str
    schema_context: str
    response: Optional[str] = None  # Wird nach der Generierung befüllt