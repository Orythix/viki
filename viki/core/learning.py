import asyncio
import json
import os
import time
import hashlib
import sqlite3
import numpy as np
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

HAS_SEMANTIC = False
SentenceTransformer = None
util = None


class LearningModule:
    """
    Semantic Memory 3.0: High-performance SQLite backend with automatic JSON migration.
    Supports structured knowledge, narrative experiences, and automated failure tracking.
    """
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "viki_knowledge.db")
        self.legacy_file = os.path.join(self.data_dir, "lessons_semantic.json")
        
        self.encoder = None
        global HAS_SEMANTIC, SentenceTransformer, util
        
        try:
            from sentence_transformers import SentenceTransformer, util
            HAS_SEMANTIC = True
            # Use CPU by default to avoid high GPU usage; set VIKI_EMBED_GPU=1 to use GPU
            _device = "cuda" if (os.getenv("VIKI_EMBED_GPU", "").lower() in ("1", "true", "yes")) else "cpu"
            self.encoder = SentenceTransformer("all-MiniLM-L6-v2", device=_device)
        except Exception as e:
            viki_logger.warning(f"Semantic Engine restricted ({e}). Using keyword proximity.")

        self._init_db()
        self._migrate_if_needed()

    def _init_db(self):
        """Initialize SQLite schema for all knowledge types."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        
        # Lessons & Facts
        cur.execute('''CREATE TABLE IF NOT EXISTS lessons (
            id TEXT PRIMARY KEY,
            content TEXT,
            text_representation TEXT,
            embedding TEXT,
            created_at REAL,
            last_accessed REAL,
            access_count INTEGER DEFAULT 1,
            author TEXT,
            source_task TEXT,
            reliability REAL
        )''')
        
        # Relationships (Knowledge Graph)
        cur.execute('''CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT,
            subj TEXT,
            pred TEXT,
            obj TEXT,
            FOREIGN KEY(lesson_id) REFERENCES lessons(id)
        )''')
        
        # Narratives (Episodic Experience)
        cur.execute('''CREATE TABLE IF NOT EXISTS narratives (
            id TEXT PRIMARY KEY,
            event TEXT,
            significance REAL,
            mood TEXT,
            timestamp REAL
        )''')
        
        # Failures (Negative Knowledge)
        cur.execute('''CREATE TABLE IF NOT EXISTS failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            error TEXT,
            context TEXT,
            timestamp REAL
        )''')
        
        # Macros (Procedural Workflows)
        cur.execute('''CREATE TABLE IF NOT EXISTS macros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_condition TEXT,
            steps TEXT,
            success_count INTEGER DEFAULT 1,
            created_at REAL
        )''')
        
        # Indices for speed
        cur.execute("CREATE INDEX IF NOT EXISTS idx_lessons_accessed ON lessons(last_accessed)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_narratives_time ON narratives(timestamp)")
        
        self.conn.commit()

    def save_macro(self, trigger_condition: str, action_sequence: List[Dict[str, Any]]):
        """Saves a procedural workflow/macro."""
        self.conn.execute('''INSERT INTO macros (trigger_condition, steps, created_at)
            VALUES (?, ?, ?)''', (trigger_condition, json.dumps(action_sequence), time.time()))
        self.conn.commit()
        viki_logger.info(f"Macro Learned: {trigger_condition}")

    def _migrate_if_needed(self):
        """One-way migration from legacy JSON memory to SQLite."""
        if not os.path.exists(self.legacy_file):
            return
            
        try:
            viki_logger.info("MIGRATION: Moving legacy JSON memory to SQLite...")
            with open(self.legacy_file, 'r') as f:
                data = json.load(f)
            
            lessons = data.get('lessons', [])
            embeddings = data.get('embeddings', [])
            metadata = data.get('metadata', [])
            narratives = data.get('narratives', [])
            failures = data.get('failures', [])
            
            # Migrate lessons
            for i, lesson in enumerate(lessons):
                meta = metadata[i] if i < len(metadata) else {}
                emb = embeddings[i] if i < len(embeddings) else []
                
                text_rep = str(lesson)
                if isinstance(lesson, dict):
                    text_rep = f"{lesson.get('trigger', '')}: {lesson.get('fact', '')}"
                
                lid = hashlib.md5(text_rep.encode()).hexdigest()[:12]
                
                self.conn.execute('''INSERT OR IGNORE INTO lessons 
                    (id, content, text_representation, embedding, created_at, last_accessed, access_count, author, source_task, reliability)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (lid, json.dumps(lesson), text_rep, json.dumps(emb), 
                     meta.get('created_at', time.time()), meta.get('last_accessed', time.time()),
                     meta.get('count', 1), meta.get('author', 'Legacy'), 
                     meta.get('source_task', 'Migration'), meta.get('reliability', 1.0))
                )
            
            # Migrate Narratives
            for n in narratives:
                nid = n.get('id', hashlib.md5(n['event'].encode()).hexdigest()[:8])
                self.conn.execute('''INSERT OR IGNORE INTO narratives 
                    (id, event, significance, mood, timestamp)
                    VALUES (?, ?, ?, ?, ?)''',
                    (nid, n['event'], n['significance'], n.get('mood', 'neutral'), n['timestamp']))
            
            # Migrate Failures
            for f in failures:
                self.conn.execute('''INSERT INTO failures (action, error, context, timestamp)
                    VALUES (?, ?, ?, ?)''', (f['action'], f['error'], f['context'], f['timestamp']))

            self.conn.commit()
            
            # Rename legacy file to avoid re-migration
            os.rename(self.legacy_file, self.legacy_file + ".bak")
            viki_logger.info("MIGRATION COMPLETE. JSON memory archived.")
        except Exception as e:
            viki_logger.error(f"Migration Failed: {e}")

    def save_lesson(self, lesson: str = None, relationship: Optional[Dict[str, str]] = None, author: str = "Self", source_task: str = "Unknown", **kwargs):
        """Saves a lesson, generates embeddings, and creates a unique knowledge trace."""
        if not lesson and 'fact' in kwargs:
            trigger = kwargs.get('trigger', 'Knowledge Acquisition')
            fact = kwargs['fact']
            lesson_obj = {"trigger": trigger, "fact": fact}
            lesson_str = f"{trigger}: {fact}"
        else:
            lesson_obj = lesson
            lesson_str = lesson

        if not lesson_str or (isinstance(lesson_str, str) and len(lesson_str) < 5):
            return

        lid = hashlib.md5(lesson_str.encode()).hexdigest()[:12]
        
        # Update if exists
        cur = self.conn.cursor()
        cur.execute("SELECT id, access_count FROM lessons WHERE id = ?", (lid,))
        row = cur.fetchone()
        
        if row:
            cur.execute("UPDATE lessons SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?", 
                       (time.time(), lid))
            self.conn.commit()
            return

        # New lesson - embedding
        embedding = []
        if self.encoder:
            try:
                enc = self.encoder.encode(lesson_str, convert_to_tensor=False)
                embedding = enc.tolist() if isinstance(enc, np.ndarray) else enc
            except: pass

        cur.execute('''INSERT INTO lessons 
            (id, content, text_representation, embedding, created_at, last_accessed, access_count, author, source_task, reliability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (lid, json.dumps(lesson_obj), lesson_str, json.dumps(embedding), 
             time.time(), time.time(), 1, author, source_task, kwargs.get('reliability', 0.8)))
        
        if relationship:
            cur.execute("INSERT INTO relationships (lesson_id, subj, pred, obj) VALUES (?, ?, ?, ?)",
                       (lid, relationship.get('subject'), relationship.get('predicate'), relationship.get('object')))
        
        self.conn.commit()

    def get_frequent_lessons(self, min_count: int = 3) -> List[str]:
        """Returns lessons that have been reinforced (access_count >= min_count)."""
        cur = self.conn.cursor()
        cur.execute("SELECT text_representation FROM lessons WHERE access_count >= ?", (min_count,))
        return [r['text_representation'] for r in cur.fetchall()]

    def get_all_lessons(self) -> List[Dict[str, Any]]:
        """Returns all lessons as a list of dicts for the Forge/Training."""
        cur = self.conn.cursor()
        cur.execute("SELECT content FROM lessons")
        return [json.loads(r['content']) for r in cur.fetchall()]

    def get_total_lesson_count(self) -> int:
        """Returns the total number of unique lessons in the DB."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM lessons")
        return cur.fetchone()[0]

    def get_relevant_lessons(self, context: str, limit: int = 5) -> List[str]:
        """Performs semantic or lexical search over the knowledge base."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, content, text_representation, embedding FROM lessons")
        rows = cur.fetchall()
        
        if not rows: return []
        
        if self.encoder:
            try:
                contents = [r['text_representation'] for r in rows]
                embeddings = [json.loads(r['embedding']) for r in rows]
                
                # Check if we have valid embeddings
                if not any(embeddings):
                    return contents[-limit:]

                query_emb = self.encoder.encode(context, convert_to_tensor=True)
                corpus_embs = self.encoder.encode(contents, convert_to_tensor=True)
                results = util.semantic_search(query_emb, corpus_embs, top_k=limit)
                
                relevant = []
                for hit in results[0]:
                    if hit['score'] > 0.25:
                        idx = hit['corpus_id']
                        relevant.append(contents[idx])
                        # Async update access metadata? For now, sync.
                        lid = rows[idx]['id']
                        cur.execute("UPDATE lessons SET last_accessed = ? WHERE id = ?", (time.time(), lid))
                
                self.conn.commit()
                return relevant if relevant else contents[-3:]
            except: pass
            
        # Fallback to recent retrieval from the already fetched rows
        return [r['text_representation'] for r in rows[-limit:]]

    def has_macros(self) -> bool:
        """Checks if any procedural macros are learned."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM macros")
        return cur.fetchone()[0] > 0

    def save_narrative(self, event: str, significance: float = 0.5, mood: str = "neutral"):
        """Saves a shared experience moment."""
        nid = hashlib.md5(event.encode()).hexdigest()[:8]
        self.conn.execute('''INSERT OR REPLACE INTO narratives (id, event, significance, mood, timestamp)
            VALUES (?, ?, ?, ?, ?)''', (nid, event, significance, mood, time.time()))
        self.conn.commit()
        viki_logger.info(f"Narrative Logged: {event[:40]}...")

    def get_relevant_narratives(self, query: str = None, limit: int = 2) -> List[str]:
        """Recalls past experiences based on keyword matching (fast)."""
        cur = self.conn.cursor()
        if not query:
            cur.execute("SELECT event FROM narratives ORDER BY timestamp DESC LIMIT ?", (limit,))
        else:
            # Simple keyword match for narratives
            words = [w.lower() for w in query.split() if len(w) > 3]
            if not words:
                cur.execute("SELECT event FROM narratives ORDER BY timestamp DESC LIMIT ?", (limit,))
            else:
                clauses = " OR ".join(["event LIKE ?" for _ in words])
                params = [f"%{w}%" for w in words] + [limit]
                cur.execute(f"SELECT event FROM narratives WHERE {clauses} ORDER BY significance DESC, timestamp DESC LIMIT ?", params)
        
        return [r['event'] for r in cur.fetchall()]

    def save_failure(self, action: str, error: str, context: str):
        self.conn.execute("INSERT INTO failures (action, error, context, timestamp) VALUES (?, ?, ?, ?)",
                         (action, error, context, time.time()))
        self.conn.commit()

    def get_relevant_failures(self, context: str, limit: int = 3) -> List[str]:
        cur = self.conn.cursor()
        now = time.time()
        max_age = 7 * 24 * 60 * 60
        cur.execute("SELECT action, error FROM failures WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 50", (now - max_age,))
        rows = cur.fetchall()
        
        relevant = []
        context_lower = context.lower()
        for r in rows:
            if any(word in context_lower for word in r['action'].lower().split() if len(word) > 3):
                relevant.append(f"PAST FAILURE: Tried '{r['action']}' but got '{r['error']}'")
        return relevant[-limit:]

    def get_stable_lesson_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM lessons WHERE access_count > 1")
        return cur.fetchone()[0]

    def close(self):
        self.conn.close()

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

    def prune_old_lessons(self, days: int = 30):
        """Removes lessons that haven't been accessed in X days."""
        now = time.time()
        max_age = days * 24 * 60 * 60
        
        cur = self.conn.cursor()
        cur.execute("DELETE FROM lessons WHERE last_accessed < ?", (now - max_age,))
        self.conn.commit()
        viki_logger.info(f"Pruned old memories (older than {days} days).")
