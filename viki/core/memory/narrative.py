
import sqlite3
import json
import time
import os
import hashlib
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

try:
    from sentence_transformers import SentenceTransformer, util
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False

class NarrativeMemory:
    """
    Orythix Narrative Memory Subsystem.
    Stores and recalls episodic experiences with full context awareness.
    Implements 'Omniscience-like recall' for recent history and semantic search for long-term.
    """
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "orythix_narrative.db")
        
        self.encoder = None
        if HAS_SEMANTIC:
            try:
                _device = "cuda" if (os.getenv("VIKI_EMBED_GPU", "").lower() in ("1", "true", "yes")) else "cpu"
                self.encoder = SentenceTransformer("all-MiniLM-L6-v2", device=_device)
            except Exception as e:
                viki_logger.warning(f"Narrative Semantic Engine restricted: {e}")

        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        
        # Episodic Memory Schema (Context -> Intent -> Action -> Outcome)
        cur.execute('''CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY,
            timestamp REAL,
            trigger_context TEXT,
            intent TEXT,
            plan TEXT,
            action TEXT,
            outcome TEXT,
            confidence REAL,
            embedding TEXT,
            access_count INTEGER DEFAULT 1,
            last_accessed REAL
        )''')
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(timestamp)")
        
        # v25: Semantic Knowledge Table (Consolidated Wisdom)
        cur.execute('''CREATE TABLE IF NOT EXISTS semantic_knowledge (
            key TEXT PRIMARY KEY,
            insight TEXT,
            category TEXT, -- coding, ethics, workflow, user_pref
            source_count INTEGER,
            last_reinforced REAL
        )''')

        self.conn.commit()

    def add_episode(self, context: str, intent: str, plan: Dict, action: str, outcome: str, confidence: float):
        """Records a complete cognitive cycle as a narrative episode."""
        eid = hashlib.md5(f"{time.time()}{intent}".encode()).hexdigest()[:12]
        
        # Generate embedding for semantic recall
        embedding = []
        if self.encoder:
            try:
                # Embed the "story" of the episode
                story = f"Context: {context} | Intent: {intent} | Action: {action} | Outcome: {outcome}"
                embedding = self.encoder.encode(story).tolist()
            except: pass

        self.conn.execute('''INSERT INTO episodes 
            (id, timestamp, trigger_context, intent, plan, action, outcome, confidence, embedding, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (eid, time.time(), context, intent, json.dumps(plan), action, outcome, confidence, json.dumps(embedding), time.time()))
        
        self.conn.commit()
        viki_logger.info(f"Narrative Recorded: Intent='{intent}' | Outcome='{outcome[:50]}...'")

    def retrieve_context(self, current_intent: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        'Omniscience-like recall': Finds semantically relevant past episodes to inform the current decision.
        """
        if not self.encoder or not HAS_SEMANTIC:
            # Fallback to recent history
            return self._get_recent_episodes(limit)

        try:
            query_emb = self.encoder.encode(current_intent, convert_to_tensor=True)
            
            cur = self.conn.cursor()
            cur.execute("SELECT id, intent, action, outcome, embedding FROM episodes")
            rows = cur.fetchall()
            
            if not rows: return []
            
            corpus_embs = [json.loads(r['embedding']) for r in rows if r['embedding']]
            if not corpus_embs: return self._get_recent_episodes(limit)
            
            import torch
            # Safe semantic search
            hits = util.semantic_search(query_emb, torch.tensor(corpus_embs), top_k=limit)
            
            results = []
            for hit in hits[0]:
                idx = hit['corpus_id']
                row = rows[idx]
                results.append({
                    "intent": row['intent'],
                    "action": row['action'],
                    "outcome": row['outcome'],
                    "relevance": hit['score']
                })
                # Reinforce memory
                self._touch_memory(row['id'])
                
            return results
        except Exception as e:
            viki_logger.error(f"Context Retrieval Failed: {e}")
            return self._get_recent_episodes(limit)

    def _get_recent_episodes(self, limit: int):
        cur = self.conn.cursor()
        cur.execute("SELECT intent, action, outcome FROM episodes ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def _touch_memory(self, eid: str):
        self.conn.execute("UPDATE episodes SET access_count = access_count + 1, last_accessed = ? WHERE id = ?", (time.time(), eid))
        self.conn.commit()

    def decay_memories(self, retention_days: int = 60):
        """Prunes memories that haven't been reinforced."""
        cutoff = time.time() - (retention_days * 86400)
        self.conn.execute("DELETE FROM episodes WHERE last_accessed < ? AND access_count < 3", (cutoff,))
        self.conn.commit()

    def get_semantic_knowledge(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns consolidated wisdom for the current context."""
        cur = self.conn.cursor()
        cur.execute("SELECT category, insight FROM semantic_knowledge ORDER BY last_reinforced DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    async def consolidate(self, model_router=None):
        """
        DREAM CYCLE: Summarize raw episodes into higher-level 'Semantic Knowledge'.
        """
        if not model_router:
             return
        
        viki_logger.info("Narrative: Initiating DREAM CYCLE (Consolidation)...")
        
        # 1. Gather recent unconsolidated episodes
        cur = self.conn.cursor()
        cur.execute("SELECT id, intent, outcome FROM episodes WHERE access_count > 0 ORDER BY timestamp DESC LIMIT 20")
        rows = cur.fetchall()
        
        if not rows:
             return

        logs = "\n".join([f"- {r['intent']} -> Result: {r['outcome'][:100]}" for r in rows])
        
        # 2. Ask LLM to extract lasting semantic insights
        prompt = [
            {"role": "system", "content": (
                "You are the VIKI Narrative Architect. Your goal is to extract long-term SEMANTIC KNOWLEDGE "
                "from recent episodic logs. \n"
                "Constraints:\n"
                "- Extract 1-3 highly specific insights (e.g., 'User prefers Python over JS for data tasks').\n"
                "- Categorize them as: coding, ethics, workflow, or user_pref.\n"
                "- Format: CategorY: INSIGHT."
            )},
            {"role": "user", "content": f"RECENT LOGS:\n{logs}"}
        ]
        
        try:
             model = model_router.get_model(capabilities=["reasoning"])
             resp = await model.chat(prompt)
             
             # 3. Store the wisdom
             for line in resp.split("\n"):
                  if ":" in line:
                       cat, insight = line.split(":", 1)
                       cat = cat.strip().lower()
                       insight = insight.strip()
                       
                       key = hashlib.md5(insight.encode()).hexdigest()[:8]
                       self.conn.execute('''INSERT INTO semantic_knowledge (key, category, insight, source_count, last_reinforced)
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET source_count = source_count + 1, last_reinforced = ?''',
                           (key, cat, insight, 1, time.time(), time.time()))
             
             self.conn.commit()
             viki_logger.info("Narrative: DREAM CYCLE complete. 20 episodes consolidated.")
        except Exception as e:
             viki_logger.error(f"Narrative: Dream Cycle failed: {e}")
