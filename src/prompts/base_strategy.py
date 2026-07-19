from abc import ABC, abstractmethod

class PromptStrategy(ABC):
    """Interface für alle Prompting-Methoden."""
    
    @abstractmethod
    def generate_prompt(self, question: str, schema_context: str) -> str:
        """
        Kombiniert die Frage und das Schema zu einem modellspezifischen Prompt.
        """
        pass