"""
Knowledge Gap Detection System
Identifies areas where VIKI lacks knowledge for targeted learning.
"""
import time
from typing import List, Dict, Any
from collections import Counter
from viki.config.logger import viki_logger


class KnowledgeGapDetector:
    """Detects areas where VIKI lacks knowledge for targeted research."""
    
    def __init__(self, learning_module):
        self.learning = learning_module
        self.low_confidence_queries = []
        self.max_queries = 100  # Keep last 100
    
    def record_low_confidence(self, query: str, confidence: float):
        """Track queries with low confidence."""
        if confidence < 0.4:
            self.low_confidence_queries.append({
                'query': query,
                'confidence': confidence,
                'timestamp': time.time()
            })
            
            # Keep only recent queries
            if len(self.low_confidence_queries) > self.max_queries:
                self.low_confidence_queries.pop(0)
            
            viki_logger.debug(f"KnowledgeGap: Recorded low-confidence query: {query[:50]} (conf: {confidence:.2f})")
    
    def get_research_topics(self, limit: int = 5) -> List[str]:
        """Generate research topics from knowledge gaps."""
        if not self.low_confidence_queries:
            return []
        
        # Cluster similar queries
        clusters = self._cluster_queries(self.low_confidence_queries)
        
        # Generate research query for each cluster
        topics = []
        for cluster in clusters[:limit]:
            # Use the most recent query in cluster as representative
            cluster.sort(key=lambda x: x['timestamp'], reverse=True)
            representative = cluster[0]['query']
            
            # Generalize the query for research
            research_topic = self._generalize_query(representative)
            topics.append(research_topic)
        
        viki_logger.info(f"KnowledgeGap: Generated {len(topics)} research topics from {len(clusters)} clusters")
        return topics
    
    def _cluster_queries(self, queries: List[Dict]) -> List[List[Dict]]:
        """Cluster similar queries by keyword overlap."""
        if not queries:
            return []
        
        clusters = []
        
        for query_data in queries:
            query_text = query_data['query']
            query_words = set(self._extract_keywords(query_text))
            
            # Try to add to existing cluster
            added = False
            for cluster in clusters:
                cluster_words = set(self._extract_keywords(cluster[0]['query']))
                
                # Calculate Jaccard similarity
                if cluster_words and query_words:
                    intersection = len(query_words & cluster_words)
                    union = len(query_words | cluster_words)
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > 0.3:  # 30% keyword overlap
                        cluster.append(query_data)
                        added = True
                        break
            
            if not added:
                clusters.append([query_data])
        
        # Sort clusters by size (larger gaps = more important)
        clusters.sort(key=lambda c: len(c), reverse=True)
        
        return clusters
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        # Simple stopword removal
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'what', 'which', 'who', 'when', 'where', 'why', 'how'
        }
        
        words = text.lower().split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        return keywords
    
    def _generalize_query(self, query: str) -> str:
        """Generalize a specific query into a research topic."""
        # Extract main subject/topic
        keywords = self._extract_keywords(query)
        
        if not keywords:
            return query
        
        # Take top keywords by frequency (if multiple queries) or just use first 3
        topic_words = keywords[:3]
        
        # Build research query
        research_query = " ".join(topic_words)
        
        # Add context for better search results
        if any(word in query.lower() for word in ['how', 'what', 'why']):
            research_query = f"guide to {research_query}"
        else:
            research_query = f"{research_query} overview and facts"
        
        return research_query
    
    def get_gap_summary(self) -> Dict[str, Any]:
        """Get summary of knowledge gaps."""
        if not self.low_confidence_queries:
            return {
                'total_gaps': 0,
                'clusters': 0,
                'avg_confidence': 0.0
            }
        
        clusters = self._cluster_queries(self.low_confidence_queries)
        avg_conf = sum(q['confidence'] for q in self.low_confidence_queries) / len(self.low_confidence_queries)
        
        return {
            'total_gaps': len(self.low_confidence_queries),
            'clusters': len(clusters),
            'avg_confidence': round(avg_conf, 3),
            'top_topics': self.get_research_topics(limit=3)
        }
