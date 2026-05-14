import asyncio
import json
import os
import time
import hashlib
import re
import sqlite3
from typing import List, Dict, Any, Optional
from viki.config.logger import viki_logger

try:
    import numpy as np
except Exception as e:
    np = None
    viki_logger.warning(f"NumPy unavailable during LearningModule import ({e}). Semantic features will use list fallback.")

HAS_SEMANTIC = False
SentenceTransformer = None
try:
    from sentence_transformers import util
except Exception:
    util = None


def _lesson_content_trigger_fact(content: Optional[str], text_representation: str) -> tuple[Optional[str], str]:
    """
    Normalize stored lesson `content` for export. JSON may decode to a dict
    ({trigger, fact}), a legacy plain string from save_lesson(lesson=str), or
    other shapes from migration — not always a dict.
    """
    if not content:
        return None, text_representation
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None, text_representation
    if isinstance(parsed, dict):
        fact = parsed.get("fact") or text_representation
        trig = parsed.get("trigger")
        return (str(trig) if trig else None), str(fact)
    if isinstance(parsed, str):
        return None, (parsed if parsed else text_representation)
    return None, json.dumps(parsed, ensure_ascii=False)


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

        # Lazy encoder: defer importing `sentence_transformers` until the
        # first call that actually needs an embedding. On a 4 GB / 4-core
        # box this saves ~1-3 s and ~150 MB at boot. Greetings / acks
        # never trigger the import at all.
        self._encoder = None
        self._encoder_loaded = False

        self._init_db()
        self._migrate_if_needed()
        # Phase 6: vector index over the embeddings column. Built lazily when
        # first queried so cold-start cost stays low.
        self._vector_backend = None
        self._vector_backend_dirty = True
        self._vector_index_path = os.path.join(self.data_dir, "lessons_vector.sqlite")

    @property
    def encoder(self):
        """Lazily import and instantiate the sentence-transformer encoder."""
        if not self._encoder_loaded:
            self._encoder_loaded = True
            try:
                global HAS_SEMANTIC
                from viki.core.embeddings import get_encoder
                self._encoder = get_encoder()
                if self._encoder is not None:
                    HAS_SEMANTIC = True
            except Exception as e:
                viki_logger.debug(f"LearningModule encoder lazy-load failed: {e}")
                self._encoder = None
        return self._encoder

    def _init_db(self):
        """Initialize SQLite schema for all knowledge types."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL")
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

    def _encode_lesson_embedding(self, lesson_str: str):
        """Best-effort embedding encoding for lessons."""
        try:
            enc = self.encoder.encode(lesson_str, convert_to_tensor=False)
            if np is not None and isinstance(enc, np.ndarray):
                return enc.tolist()
            if hasattr(enc, "tolist"):
                return enc.tolist()
            return enc
        except Exception as e:
            viki_logger.debug("Lesson embedding encode: %s", e)
            return []

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

        # Allow callers to pass source= or source_task= (e.g. "user_correction", "web")
        effective_source = kwargs.get('source', kwargs.get('source_task', source_task))

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
            embedding = self._encode_lesson_embedding(lesson_str)

        cur.execute('''INSERT INTO lessons 
            (id, content, text_representation, embedding, created_at, last_accessed, access_count, author, source_task, reliability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (lid, json.dumps(lesson_obj), lesson_str, json.dumps(embedding), 
             time.time(), time.time(), 1, author, effective_source, kwargs.get('reliability', 0.8)))
        
        if relationship:
            if isinstance(relationship, list) and len(relationship) >= 3:
                subj, pred, obj = relationship[0], relationship[1], relationship[2]
            elif isinstance(relationship, dict):
                subj = relationship.get('subject') or relationship.get('subj')
                pred = relationship.get('predicate') or relationship.get('pred')
                obj = relationship.get('object') or relationship.get('obj')
            else:
                subj, pred, obj = None, None, None

            if subj and pred and obj:
                cur.execute("INSERT INTO relationships (lesson_id, subj, pred, obj) VALUES (?, ?, ?, ?)",
                           (lid, str(subj), str(pred), str(obj)))
        
        self.conn.commit()
        self.mark_vector_dirty()

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

    def get_lessons(self, query: str = None, source: str = None, author: str = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Returns detailed lesson records with optional filtering."""
        cur = self.conn.cursor()
        sql = "SELECT id, text_representation, content, author, source_task, reliability, access_count, created_at FROM lessons WHERE 1=1"
        params = []
        if query:
            sql += " AND text_representation LIKE ?"
            params.append(f"%{query}%")
        if source:
            sql += " AND source_task = ?"
            params.append(source)
        if author:
            sql += " AND author = ?"
            params.append(author)
        
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def delete_lesson(self, lesson_id: str) -> bool:
        """Removes a lesson and its relationships."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM relationships WHERE lesson_id = ?", (lesson_id,))
        cur.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        self.conn.commit()
        self.mark_vector_dirty()
        return cur.rowcount > 0

    def update_lesson(self, lesson_id: str, fact: str = None, reliability: float = None) -> bool:
        """Updates an existing lesson's fact content or reliability."""
        cur = self.conn.cursor()
        updates = []
        params = []
        if fact:
            updates.append("text_representation = ?, content = ?")
            params.extend([fact, json.dumps({"fact": fact})])
        if reliability is not None:
            updates.append("reliability = ?")
            params.append(reliability)
        
        if not updates:
            return False
            
        sql = f"UPDATE lessons SET {', '.join(updates)} WHERE id = ?"
        params.append(lesson_id)
        cur.execute(sql, params)
        self.conn.commit()
        self.mark_vector_dirty()
        return cur.rowcount > 0

    def get_total_lesson_count(self) -> int:
        """Returns the total number of unique lessons in the DB."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM lessons")
        return cur.fetchone()[0]

    def get_relevant_lessons(self, context: str, limit: int = 5) -> List[str]:
        """Performs semantic or lexical search over the knowledge base.

        Phase 6: backed by a persistent vector index (sqlite-vss when available,
        numpy fallback otherwise). The Python-level encode-everything-per-call
        path is gone; we encode the query once and let the index do the rest.
        """
        # Cheap-retrieve fast path: trivial inputs (greetings, short acks)
        # never benefit from a lesson lookup; skip the SQL query AND the
        # embedding encode entirely.
        try:
            from viki.core.utils.trivial_input import is_trivial_input
            if is_trivial_input(context):
                return []
        except Exception:
            pass

        cur = self.conn.cursor()
        cur.execute("SELECT id, content, text_representation, embedding FROM lessons")
        rows = cur.fetchall()
        contents = [r['text_representation'] for r in rows]
        viki_logger.info("LearningModule: get_relevant_lessons scanning %s lesson row(s)", len(rows))
        viki_logger.debug(
            "LearningModule: lesson text preview (first 3, truncated): %s",
            [(c or "")[:120] for c in contents[:3]],
        )
        if not rows:
            return []

        if self.encoder is not None:
            try:
                backend = self._get_vector_backend(rows)
                if backend is not None:
                    query_emb = self.encoder.encode(context).tolist()
                    hits = backend.search(query_emb, top_k=limit, query_text=context)
                    if hits:
                        text_to_id = {r['text_representation']: r['id'] for r in rows}
                        out: List[str] = []
                        seen = set()
                        for h in hits:
                            if h.text in seen:
                                continue
                            seen.add(h.text)
                            out.append(h.text)
                            lid = text_to_id.get(h.text)
                            if lid is not None:
                                cur.execute(
                                    "UPDATE lessons SET last_accessed = ? WHERE id = ?",
                                    (time.time(), lid),
                                )
                        self.conn.commit()
                        return out or contents[-min(limit, 3):]
            except Exception as e:
                viki_logger.debug("get_relevant_lessons vector path failed: %s", e)

        return self._lexical_rank_lessons(rows, context=context, limit=limit)

    def _get_vector_backend(self, rows):
        """Build (or rebuild when dirty) the vector index over current rows."""
        if self.encoder is None:
            return None
        valid_rows = []
        for r in rows:
            try:
                emb = json.loads(r['embedding']) if r['embedding'] else None
            except Exception:
                emb = None
            if emb:
                valid_rows.append((r['id'], emb, r['text_representation'] or ''))
        if not valid_rows:
            return None

        if self._vector_backend is None or self._vector_backend_dirty:
            from viki.core.vector_memory import build_vector_backend

            dim = len(valid_rows[0][1])
            try:
                self._vector_backend = build_vector_backend(
                    dim=dim,
                    db_path=self._vector_index_path,
                    prefer=["sqlite-vss", "numpy-memory"],
                )
            except Exception as e:
                viki_logger.debug("vector backend init failed: %s", e)
                return None
            try:
                row_iter = (
                    (
                        abs(hash(str(rid))) % (2**31),
                        emb,
                        text,
                        {"raw_id": rid},
                    )
                    for rid, emb, text in valid_rows
                )
                self._vector_backend.upsert_many(row_iter)
                self._vector_backend_dirty = False
            except Exception as e:
                viki_logger.debug("vector backend upsert failed: %s", e)
                return None
        return self._vector_backend

    def mark_vector_dirty(self) -> None:
        """Invalidate the vector index after a write so the next query rebuilds."""
        self._vector_backend_dirty = True

    def _lexical_rank_lessons(self, rows, context: str, limit: int) -> List[str]:
        """
        Lexical overlap ranking for when embeddings are unavailable.
        Keeps the original recency behavior if no lexical signal exists.
        """
        context = context or ""
        query_tokens = set(re.findall(r"\w+", context.lower()))
        recent = [r["text_representation"] for r in rows[-limit:]]
        if not query_tokens:
            return recent

        scored = []
        for idx, r in enumerate(rows):
            text = r["text_representation"] or ""
            tokens = set(re.findall(r"\w+", text.lower()))
            overlap = len(query_tokens & tokens)
            score = overlap / (len(query_tokens) + 1e-6)
            scored.append((score, idx, text))

        if not scored:
            return []

        max_score = max(s for s, _, _ in scored)
        if max_score <= 0:
            return recent

        # Tie-break with recency.
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [text for _, _, text in scored[:limit]]

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

    @staticmethod
    def resolve_export_min_access_count(
        explicit: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Threshold for export_training_dataset: YAML system.lesson_export_min_access_count, then env, then default 2."""
        if explicit is not None:
            try:
                return max(1, int(explicit))
            except (TypeError, ValueError):
                pass
        sys = (settings or {}).get("system") or {}
        raw = sys.get("lesson_export_min_access_count")
        if raw is not None:
            try:
                return max(1, int(raw))
            except (TypeError, ValueError):
                pass
        env = (os.environ.get("VIKI_LESSON_EXPORT_MIN_ACCESS") or "").strip()
        if env:
            try:
                return max(1, int(env))
            except ValueError:
                pass
        return 2

    def export_training_dataset(
        self,
        output_path: str,
        format: str = "jsonl",
        min_access_count: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
        include_failures: bool = False,
    ) -> str:
        """
        Export reinforced lessons for LoRA / external trainers.
        Rows include lessons with access_count >= min_access_count (default from settings/env, usually 2).
        format: jsonl (default, one object per line with \"text\" for TRL/Unsloth), alpaca, openai
        include_failures: If True, also exports negative examples from the failures table.
        """
        min_ac = self.resolve_export_min_access_count(min_access_count, settings)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT text_representation, content, access_count, source_task, reliability FROM lessons "
            "WHERE access_count >= ? ORDER BY last_accessed DESC",
            (min_ac,),
        )
        rows = cur.fetchall()
        if not rows:
            return f"No lessons with access_count >= {min_ac} to export."

        parent = os.path.dirname(os.path.abspath(output_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        lines: List[str] = []

        if format == "jsonl":
            for r in rows:
                trig_raw, fact = _lesson_content_trigger_fact(r["content"], r["text_representation"])
                trig = trig_raw or "context"
                block = (
                    f"### Instruction:\nRemember this for future VIKI interactions.\n"
                    f"### Input:\n{trig}\n### Response:\n{fact}"
                )
                lines.append(json.dumps({"text": block}, ensure_ascii=False))

        elif format == "alpaca":
            for r in rows:
                trig_raw, fact = _lesson_content_trigger_fact(r["content"], r["text_representation"])
                lines.append(
                    json.dumps(
                        {
                            "instruction": "Remember this for future VIKI interactions.",
                            "input": trig_raw or "context",
                            "output": fact,
                        },
                        ensure_ascii=False,
                    )
                )

        elif format == "openai":
            for r in rows:
                trig_raw, fact = _lesson_content_trigger_fact(r["content"], r["text_representation"])
                trig = trig_raw or "user context"
                lines.append(
                    json.dumps(
                        {
                            "messages": [
                                {"role": "system", "content": "You are VIKI's knowledge consolidation trainer."},
                                {"role": "user", "content": str(trig)},
                                {"role": "assistant", "content": str(fact)},
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
        else:
            raise ValueError(f"Unknown export format: {format}")

        if include_failures:
            cur.execute("SELECT action, error, context FROM failures ORDER BY timestamp DESC LIMIT 100")
            fail_rows = cur.fetchall()
            for f in fail_rows:
                action, error, context = f["action"], f["error"], f["context"]
                if format == "jsonl":
                    block = (
                        f"### Instruction:\nFailure Avoidance: Do not repeat this past mistake.\n"
                        f"### Input:\nContext: {context}\nAction: {action}\n### Response:\n"
                        f"Result was an ERROR: {error}. In the future, identify a safer or more correct strategy."
                    )
                    lines.append(json.dumps({"text": block}, ensure_ascii=False))
                elif format == "alpaca":
                    lines.append(json.dumps({
                        "instruction": "Failure Avoidance: Do not repeat this past mistake.",
                        "input": f"Context: {context}\nAction: {action}",
                        "output": f"Avoid this. Result: {error}"
                    }, ensure_ascii=False))
                elif format == "openai":
                    lines.append(json.dumps({
                        "messages": [
                            {"role": "system", "content": "You are VIKI's failure avoidance trainer."},
                            {"role": "user", "content": f"Context: {context}\nAction: {action}"},
                            {"role": "assistant", "content": f"This action failed with: {error}. Do not repeat."}
                        ]
                    }, ensure_ascii=False))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        status_msg = f"Exported {len(lines)} rows to {output_path} ({format}, min_access_count={min_ac})"
        if include_failures:
            status_msg += " (including failure cases)"
        return status_msg

    def import_lessons_from_jsonl(
        self,
        path: str,
        *,
        reinforce: bool = False,
        source_task: str = "jsonl_import",
    ) -> str:
        """
        Import lessons from a JSONL file (curated facts for training).
        Supported shapes per line: {\"trigger\",\"fact\"}, {\"instruction\",\"input\",\"output\"},
        {\"messages\":[{\"role\",\"content\"},...]}, or {\"text\": \"...\"}.
        Optional per-line fields: source_task, author, reliability (float).
        If reinforce=True, each imported row is saved twice so access_count reaches 2 when new.
        """
        if not os.path.isfile(path):
            return f"import_lessons_from_jsonl: file not found: {path}"
        n = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                trigger: Optional[str] = None
                fact: Optional[str] = None
                if "text" in obj and isinstance(obj["text"], str):
                    trigger = "imported_block"
                    fact = obj["text"].strip()
                elif "trigger" in obj and "fact" in obj:
                    trigger = str(obj.get("trigger") or "").strip() or "imported"
                    fact = str(obj.get("fact") or "").strip()
                elif "instruction" in obj and "output" in obj:
                    trigger = str(obj.get("input") or obj.get("instruction") or "imported").strip()
                    fact = str(obj.get("output") or "").strip()
                elif "messages" in obj and isinstance(obj["messages"], list):
                    user_txt = ""
                    asst_txt = ""
                    for m in obj["messages"]:
                        if not isinstance(m, dict):
                            continue
                        role = (m.get("role") or "").lower()
                        content = m.get("content")
                        if not isinstance(content, str):
                            content = json.dumps(content) if content is not None else ""
                        if role == "user":
                            user_txt = content.strip()
                        elif role == "assistant":
                            asst_txt = content.strip()
                    if user_txt and asst_txt:
                        trigger, fact = user_txt, asst_txt
                if not fact or len(fact) < 3:
                    continue
                row_source = str(obj.get("source_task") or source_task).strip() or source_task
                row_author = str(obj.get("author") or "Self").strip() or "Self"
                row_rel = obj.get("reliability")
                rel_kw: Dict[str, Any] = {}
                if isinstance(row_rel, (int, float)):
                    rel_kw["reliability"] = float(row_rel)
                self.save_lesson(
                    trigger=trigger or "imported",
                    fact=fact,
                    source_task=row_source,
                    author=row_author,
                    **rel_kw,
                )
                if reinforce:
                    self.save_lesson(
                        trigger=trigger or "imported",
                        fact=fact,
                        source_task=row_source,
                        author=row_author,
                        **rel_kw,
                    )
                n += 1
        return f"Imported {n} lesson row(s) from {path}."

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
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    
                    if not isinstance(data, dict):
                         viki_logger.debug(f"Learning: Expected dict from JSON, got {type(data)}")
                         return

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
    def close(self):
        """Properly close the SQLite connection."""
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
                self.conn = None
                viki_logger.info("Learning: SQLite connection closed.")
            except Exception as e:
                viki_logger.debug(f"Learning: Failed to close SQLite: {e}")
