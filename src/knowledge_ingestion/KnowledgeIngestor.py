import time

from src.infrastructure.graph_db.neo4j_client import Neo4jClient
from src.knowledge_ingestion.log_connector import LogConnector
from src.knowledge_ingestion.text_connector import TextConnector
from src.services.knowledge_extractor import KnowledgeExtractor
from src.services.observability_service import ObservabilityService
from viki.config.logger import viki_logger


class KnowledgeIngestor:
    """
    Orchestrates the entire ETL pipeline for building and updating the Structured
    Knowledge Graph (SKG). This class manages data flow from raw sources to graph triples.
    """

    def __init__(self, db_client: Neo4jClient):
        self.db_client = db_client
        self.extractor = KnowledgeExtractor()
        self.observability = ObservabilityService()

    def ingest_all_sources(self, doc_paths: list[str], log_file_path: str) -> int:
        """
        Runs the full ingestion cycle across all defined data sources.
        Returns the total number of triples successfully committed to the graph.
        """
        start_span = self.observability.start_span("KnowledgeIngestionCycle")
        viki_logger.info("--- Starting Knowledge Graph Ingestion Cycle ---")
        all_triples: list[tuple[str, str, str]] = []

        try:
            # 1. Process Unstructured Text Documents (Docs, Playbooks)
            text_connector = TextConnector()
            all_chunks = text_connector.process_documents(doc_paths)
            self.observability.log_event(
                "KnowledgeIngestion", {"step": "TextChunking", "count": len(all_chunks)}
            )
            viki_logger.info("Found %d chunks from documentation.", len(all_chunks))

            all_triples.extend(self._process_chunks(all_chunks, source_type="Documentation"))

            # 2. Process Structured Log Sessions (Usage Data)
            log_connector = LogConnector(log_file_path)
            session_data = log_connector.process_logs()
            self.observability.log_event(
                "KnowledgeIngestion", {"step": "LogParsing", "count": len(session_data)}
            )
            viki_logger.info("Processed %d user sessions.", len(session_data))

            all_triples.extend(self._process_chunks(session_data, source_type="UsageLog"))

            # 3. Commit all extracted data to the graph database
            commit_span = self.observability.start_span(
                "GraphCommit", parent_context={"source": "KnowledgeIngestion"}
            )
            try:
                self.db_client.commit_batch(all_triples)
                self.observability.end_span(commit_span, status="SUCCESS")
            except Exception as e:
                self.observability.end_span(commit_span, status="ERROR")
                self.observability.log_event(
                    "KnowledgeIngestion", {"step": "DBWriteFailure", "error": str(e)}
                )
                viki_logger.warning("Failed to commit batch due to DB error: %s", e)
                return 0

            viki_logger.info("--- Knowledge Graph Ingestion Complete ---")
            return len(all_triples)
        finally:
            self.observability.end_span(
                start_span,
                status="SUCCESS",
                duration=time.time() - start_span["start_time"],
            )

    def _process_chunks(self, chunks: list[dict], source_type: str) -> list[tuple[str, str, str]]:
        """Helper method to extract triples from a batch of data chunks."""
        all_triples: list[tuple[str, str, str]] = []
        for chunk in chunks:
            # The extractor handles the complex logic of turning text/data into (S, P, O) tuples
            triples = self.extractor.extract_triples(chunk["content"], chunk["metadata"])
            all_triples.extend(triples)

        viki_logger.info("Extracted %d potential triples from %s.", len(all_triples), source_type)
        return all_triples
