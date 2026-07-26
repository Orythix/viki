# ...existing code...
from src.knowledge_ingestion.text_connector import TextConnector
from src.knowledge_ingestion.log_connector import LogConnector
from src.services.knowledge_extractor import KnowledgeExtractor
from src.infrastructure.graph_db.neo4j_client import Neo4jClient

class KnowledgeIngestor:
    """
    Orchestrates the entire ETL pipeline for building and updating the Structured 
    Knowledge Graph (SKG). This class manages data flow from raw sources to graph triples.
    """
    def __init__(self, db_client: Neo4jClient):
        # Initialize core components
        self.db_client = db_client
        self.extractor = KnowledgeExtractor()

        # Initialize core components
        self.db_client = db_client
        self.observability = ObservabilityService()

    def __init__(self, db_client: Neo4jClient):
        # Initialize core components
        self.db_client = db_client
        self.observability = ObservabilityService()

    def ingest_all_sources(self, doc_paths: list[str], log_file_path: str) -> int:
        """
        Runs the full ingestion cycle across all defined data sources.
        Returns the total number of triples successfully committed to the graph.
        """
        start_span = self.observability.start_span("KnowledgeIngestionCycle")
        print(f"--- Starting Knowledge Graph Ingestion Cycle ---")
        total_triples = 0

        try:
            # 1. Process Unstructured Text Documents (Docs, Playbooks)
            text_connector = TextConnector()
            all_chunks = text_connector.process_documents(doc_paths)
            self.observability.log_event("KnowledgeIngestion", {"step": "TextChunking", "count": len(all_chunks)})
            print(f"Found {len(all_chunks)} chunks from documentation.")
            
            triples_from_docs = self._process_chunks(all_chunks, source_type="Documentation")
            total_triples += triples_from_docs

            # 2. Process Structured Log Sessions (Usage Data)
            log_connector = LogConnector()
            session_data = log_connector.process_logs(log_file_path)
            self.observability.log_event("KnowledgeIngestion", {"step": "LogParsing", "count": len(session_data)})
            print(f"Processed {len(session_data)} user sessions.")
            
            triples_from_logs = self._process_chunks(session_data, source_type="UsageLog")
            total_triples += triples_from_logs

            # 3. Commit all extracted data to the graph database
            self.observability.start_span("GraphCommit", parent_context={"source": "KnowledgeIngestion"})
            try:
                self.db_client.commit_batch(all_triples)
                self.observability.end_span(self.observability.start_span("GraphCommit"), status="SUCCESS")
            except Exception as e:
                 self.observability.log_event("KnowledgeIngestion", {"step": "DBWriteFailure", "error": str(e)})
                 print(f"Warning: Failed to commit batch due to DB error: {e}")

            print("--- Knowledge Graph Ingestion Complete ---")
            return total_triples
        finally:
            self.observability.end_span(start_span, status="SUCCESS", duration=time.time() - start_span['start_time'])
        finally:
            self.observability.end_span(start_span, status="SUCCESS", duration=time.time() - start_span['start_time'])

    def _process_chunks(self, chunks: list[dict], source_type: str) -> int:
        """Helper method to extract triples from a batch of data chunks."""
        all_triples = []
        for chunk in chunks:
            # The extractor handles the complex logic of turning text/data into (S, P, O) tuples
            triples = self.extractor.extract_triples(chunk['content'], chunk['metadata'])
            all_triples.extend(triples)
        
        print(f"Extracted {len(all_triples)} potential triples from {source_type}.")
        return len(all_triples)

# ...existing code...