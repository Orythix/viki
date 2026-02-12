import asyncio
import json
import os
import time
import numpy as np
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

HAS_SEMANTIC = False
SentenceTransformer = None
util = None


class LearningModule:
    """
    Semantic Memory 2.0: Now with Relationship Tracking (Pseudo-Graph).
    """
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.lessons_file = os.path.join(self.data_dir, "lessons_semantic.json")
        self.encoder = None
        global HAS_SEMANTIC, SentenceTransformer, util
        
        try:
            from sentence_transformers import SentenceTransformer, util
            HAS_SEMANTIC = True
            self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            viki_logger.warning(f"Semantic Engine unavailable ({e}). Falling back to keyword matching.")

                
        self.memory = self._load_memory()

    def _load_memory(self) -> Dict[str, Any]:
        default_struct = {'lessons': [], 'embeddings': [], 'relationships': [], 'macros': [], 'failures': [], 'metadata': []}
        if os.path.exists(self.lessons_file):
            try:
                with open(self.lessons_file, 'r') as f:
                    data = json.load(f)
                    # Support legacy and fill missing keys
                    for key in default_struct:
                        if key not in data: data[key] = default_struct[key]
                    return data
            except:
                return default_struct
        return default_struct

    def save_failure(self, action: str, error: str, context: str):
        """Records a failed attempt to prevent repetition."""
        if 'failures' not in self.memory: self.memory['failures'] = []
        
        failure_entry = {
            'action': action,
            'error': error,
            'context': context,
            'timestamp': time.time()
        }
        self.memory['failures'].append(failure_entry)
        
        # Limit failure memory size to most recent 50 to avoid bloat
        if len(self.memory['failures']) > 50:
            self.memory['failures'] = self.memory['failures'][-50:]
            
        self._save_memory()
        viki_logger.warning(f"Failure Recorded: {action} -> {error}")

    def get_relevant_failures(self, current_context: str, days_threshold: int = 7) -> List[str]:
        """
        Retrieves past failures with Decay logic:
        - Older than 'days_threshold' are ignored.
        - Matches based on intent similarity.
        """
        if not self.memory.get('failures'): return []
        
        now = time.time()
        max_age = days_threshold * 24 * 60 * 60
        relevant = []
        
        # 1. Temporal Decay Filter
        active_failures = [f for f in self.memory['failures'] if (now - f.get('timestamp', 0)) < max_age]
        
        if not active_failures: return []

        # 2. Context Matching
        current_lower = current_context.lower()
        
        # Try semantic matching if available
        if self.encoder and active_failures:
            try:
                fail_contexts = [f['context'] for f in active_failures]
                query_emb = self.encoder.encode(current_context, convert_to_tensor=True)
                fail_embs = self.encoder.encode(fail_contexts, convert_to_tensor=True)
                results = util.semantic_search(query_emb, fail_embs, top_k=3)
                
                for hit in results[0]:
                    if hit['score'] > 0.4: # Higher threshold for failures
                        f = active_failures[hit['corpus_id']]
                        relevant.append(f"PAST FAILURE (Sim: {hit['score']:.2f}): Tried '{f['action']}' in similar context and got '{f['error']}'")
            except Exception as e:
                viki_logger.warning(f"Semantic failure matching failed: {e}")

        # Fallback to simple keyword matching if semantic didn't fill it
        if not relevant:
            for f in active_failures:
                if any(word in current_lower for word in f['action'].lower().split() if len(word) > 3):
                    relevant.append(f"PAST FAILURE: Tried '{f['action']}' but got '{f['error']}'")
        
        return relevant[-3:]

    def save_macro(self, trigger_condition: str, action_sequence: List[Dict[str, Any]]):
        """Saves a procedural workflow/macro."""
        if 'macros' not in self.memory: self.memory['macros'] = []
        
        self.memory['macros'].append({
            'trigger': trigger_condition,
            'steps': action_sequence,
            'success_count': 1,
            'created_at': time.time()
        })
        self._save_memory()
        viki_logger.info(f"Macro Learned: {trigger_condition}")

    def _save_memory(self):
        with open(self.lessons_file, 'w') as f:
            json.dump(self.memory, f)

    def save_lesson(self, lesson: str, relationship: Optional[Dict[str, str]] = None, author: str = "Self", source_task: str = "Unknown"):
        if not lesson or len(lesson) < 5:
            return

        # Check for duplicates in text lessons
        if lesson in self.memory['lessons']:
            # Maybe update metadata instead of skipping?
            idx = self.memory['lessons'].index(lesson)
            self.memory['metadata'][idx]['last_accessed'] = time.time()
            self.memory['metadata'][idx]['count'] = self.memory['metadata'][idx].get('count', 1) + 1
            self._save_memory()
            return

        embedding = []
        if self.encoder:
            enc = self.encoder.encode(lesson, convert_to_tensor=False)
            embedding = enc.tolist() if isinstance(enc, np.ndarray) else enc
            
        self.memory['lessons'].append(lesson)
        self.memory['embeddings'].append(embedding)
        
        # v10: Knowledge Provenance Metadata
        self.memory['metadata'].append({
            'created_at': time.time(),
            'last_accessed': time.time(),
            'author': author,
            'source_task': source_task,
            'count': 1,
            'type': 'fact' if not relationship else 'relationship',
            'reliability': 1.0 if author == "User" else 0.8
        })

        if relationship:
            self.memory['relationships'].append(relationship)
        
        self._save_memory()

    async def analyze_session(self, model, trace: List[Dict[str, str]], outcome: str):
        """
        Extracts both flat facts and structured relationships.
        """
        prompt = [
            {"role": "system", "content": (
                "You are an Advanced Semantic Extraction Module.\n"
                "Extract PERMANENT USER FACTS and RELATIONSHIPS.\n"
                "Format: A JSON object with 'fact' (string), 'rel' (triple), and 'confidence' (0.0-1.0).\n"
                "MINIMUM CONFIDENCE: Only include facts with confidence > 0.8.\n"
                "Example: {'fact': 'User prefers Python', 'rel': ['User', 'prefers', 'Python'], 'confidence': 0.95}\n"
                "If nothing high-confidence is found, output 'NO_LESSON'."
            )},
            {"role": "user", "content": f"Trace: {json.dumps(trace)}\nOutcome: {outcome}"}
        ]
        
        try:
            # We use chat_structured if the model supports it, but for learning analysis 
            # we might just use chat and parse manually to be safe with smaller models.
            response = await model.chat(prompt)
            if "NO_LESSON" in response: return
            
            # Robust JSON extraction
            content = response.strip()
            
            # Find first { and last }
            start = content.find('{')
            end = content.rfind('}')
            
            if start != -1 and end != -1:
                content = content[start:end+1]
                try:
                    data = json.loads(content)
                    fact = data.get('fact')
                    rel = data.get('rel')
                    conf = data.get('confidence', 0.0)
                    
                    if fact and conf > 0.8:
                        self.save_lesson(fact, relationship=rel)
                        viki_logger.info(f"Memory Integrated: {fact} (Conf: {conf})")
                    else:
                        viki_logger.info(f"Lesson Rejected: Low confidence ({conf}) or missing fact.")
                except json.JSONDecodeError:
                    pass # Fallback to text
            else:
                 # Fallback to simple extraction
                clean_response = response.strip().split('\n')[0]
                if len(clean_response) > 5 and "NO_LESSON" not in clean_response:
                    self.save_lesson(clean_response)
        except Exception as e:
            viki_logger.error(f"Memory analysis error: {e}")

    def get_stable_lesson_count(self) -> int:
        """Count lessons that have been reinforced (count > 1)."""
        count = 0
        for meta in self.memory.get('metadata', []):
            if meta.get('count', 1) > 1:
                count += 1
        return count

    def get_relevant_lessons(self, context: str) -> List[str]:
        if not self.memory['lessons']: return []
        if not self.encoder or not self.memory['embeddings'] or not self.memory['embeddings'][0]:
            return self.memory['lessons'][-5:]

        try:
            query_embedding = self.encoder.encode(context, convert_to_tensor=True)
            corpus_embeddings = self.encoder.encode(self.memory['lessons'], convert_to_tensor=True) 
            results = util.semantic_search(query_embedding, corpus_embeddings, top_k=5)
            top_hits = results[0]
            
            relevant = []
            for hit in top_hits:
                if hit['score'] > 0.25:
                    idx = hit['corpus_id']
                    relevant.append(self.memory['lessons'][idx])
                    # Update usage metadata
                    self.memory['metadata'][idx]['last_accessed'] = time.time()
            
            return relevant if relevant else self.memory['lessons'][-3:]
        except Exception:
            return self.memory['lessons'][-5:]

    def prune_old_lessons(self, days: int = 30):
        """Removes lessons that haven't been accessed in X days."""
        now = time.time()
        max_age = days * 24 * 60 * 60
        
        indices_to_keep = []
        for i, meta in enumerate(self.memory.get('metadata', [])):
            if now - meta.get('last_accessed', 0) < max_age:
                indices_to_keep.append(i)
        
        if len(indices_to_keep) == len(self.memory['lessons']):
            return

        new_lessons = [self.memory['lessons'][i] for i in indices_to_keep]
        new_embeddings = [self.memory['embeddings'][i] for i in indices_to_keep]
        new_metadata = [self.memory['metadata'][i] for i in indices_to_keep]
        
        # Relationships are harder to index if they don't map 1:1, 
        # but in our current save_lesson they do map 1:1 if present.
        # Actually, let's keep relationships simple for now or filter them too.
        
        self.memory['lessons'] = new_lessons
        self.memory['embeddings'] = new_embeddings
        self.memory['metadata'] = new_metadata
        self._save_memory()
        viki_logger.info(f"Pruned {len(indices_to_keep) - len(new_lessons)} old memories.")
