from typing import Any

from viki.config.logger import viki_logger

from .connector_base import ConnectorBase


class TextConnector(ConnectorBase):
    """
    Handles reading and chunking of unstructured text documents from specified paths.
    This connector is responsible for preparing raw files into processable chunks
    with rich metadata.
    """

    def __init__(self, chunk_size: int = 1024, overlap: int = 128):
        if overlap >= chunk_size:
            raise ValueError(
                f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size}); "
                "otherwise chunking never advances."
            )
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process(self, doc_paths: list[str]) -> list[dict[str, Any]]:
        """Implements the ConnectorBase contract; see :meth:`process_documents`."""
        return self.process_documents(doc_paths)

    def process_documents(self, doc_paths: list[str]) -> list[dict[str, Any]]:
        """
        Processes a list of file paths, reading content and splitting it into overlapping chunks.
        """
        all_chunks: list[dict[str, Any]] = []
        for path in doc_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    # Simple chunking logic (can be improved with NLP libraries)
                    chunks = self._chunk_text(content, path)
                    all_chunks.extend(chunks)
            except FileNotFoundError:
                viki_logger.warning("Document not found at %s. Skipping.", path)
            except Exception as e:
                viki_logger.error("Error processing file %s: %s", path, e)
        return all_chunks

    def _chunk_text(self, content: str, source_path: str) -> list[dict[str, Any]]:
        """Splits text into chunks of specified size with overlap."""
        chunks = []
        start = 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))
            chunk_text = content[start:end]

            # Metadata is crucial for traceability in the KG
            metadata = {
                "source_path": source_path,
                "type": "UnstructuredText",
                "page_context": "N/A",  # Placeholder for future page detection
            }
            chunks.append({"content": chunk_text, "metadata": metadata})

            if end == len(content):
                break
            # Move start back by overlap amount to ensure continuity
            start += self.chunk_size - self.overlap
        return chunks


# ...existing code...
