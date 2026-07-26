import abc
from typing import List, Dict, Any

class ConnectorBase(abc.ABC):
    """
    Abstract Base Class for all data source connectors in the Knowledge Graph pipeline.
    All concrete connectors must inherit from this class and implement the process method.
    """
    @abc.abstractmethod
    def process(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Processes raw input data (files, paths, etc.) and returns a list of 
        dictionaries, where each dictionary represents a chunk of content ready for extraction.

        Each returned dictionary must contain at least:
        - 'content': The text chunk to be analyzed.
        - 'metadata': A dictionary containing source information (e.g., {'source_path': '...', 'type': '...'}).
        """
        raise NotImplementedError("Subclasses must implement the process method.")

# ...existing code...