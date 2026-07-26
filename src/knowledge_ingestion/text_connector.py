import os
from typing import List, Dict, Any
from .connector_base import ConnectorBase

class TextConnector(ConnectorBase):
    """
    Handles reading and chunking of unstructured text documents from specified paths.
    This connector is responsible for preparing raw files into processable chunks 
    with rich metadata.
    """
    def __init__(self, chunk_size: int = 1024, overlap: int = 128):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process_documents(self, doc_paths: list[str]) -> List[Dict[str, Any]]:
        """
        Processes a list of file paths, reading content and splitting it into overlapping chunks.
        """
        all_chunks: List[Dict[str, Any]] = []
        for path in doc_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Simple chunking logic (can be improved with NLP libraries)
                    chunks = self._chunk_text(content, path)
                    all_chunks.extend(chunks)
            except FileNotFoundError:
                print(f"Warning: Document not found at {path}. Skipping.")
            except Exception as e:
                print(f"Error processing file {path}: {e}")
        return all_chunks

    def _chunk_text(self, content: str, source_path: str) -> List[Dict[str, Any]]:
        """Splits text into chunks of specified size with overlap."""
        chunks = []
        start = 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))
            chunk_text = content[start:end]
            
            # Metadata is crucial for traceability in the KG
            metadata = {
                'source_path': source_path, 
                'type': 'UnstructuredText', 
                'page_context': 'N/A' # Placeholder for future page detection
            }
            chunks.append({
                'content': chunk_text,
                'metadata': metadata
            })
            
            if end == len(content):
                break
            # Move start back by overlap amount to ensure continuity
            start += self.chunk_size - self.overlap
        return chunks

# ...existing code...