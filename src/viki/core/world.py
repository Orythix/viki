import os
import json
import time
import ast
from typing import Dict, Any, List, Optional
from core.schema import WorldState
from config.logger import viki_logger
from core.utils.debouncer import SyncDebouncer

class WorldModel:
    """
    v10: Persistent Internal model of the environment.
    Unlike Memory, this is absolute stateful understanding.
    """
    def __init__(self, data_path: str):
        self.path = os.path.join(data_path, "world_state.json")
        self.state = self._load()
        # Debounce saves: wait 5s between saves, max 30s total
        self._debouncer = SyncDebouncer(delay=5.0, max_delay=30.0)

    def _load(self) -> WorldState:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                    return WorldState(**data)
            except (json.JSONDecodeError, IOError, TypeError) as e:
                viki_logger.warning(f"Failed to load world state from {self.path}: {e}")
        return WorldState()

    def _do_save(self):
        """Internal save method called by debouncer."""
        self.state.last_updated = time.time()
        with open(self.path, 'w') as f:
            json.dump(self.state.model_dump(), f, indent=4)
    
    def save(self):
        """Debounced save - actual write happens after delay."""
        self._debouncer.mark_dirty()
        self._debouncer.execute(self._do_save)
    
    def flush(self):
        """Force immediate save (call on shutdown)."""
        self._debouncer.flush(self._do_save)

    def track_app_usage(self, app_name: str, status: str = "known"):
        """Records installed apps and common statuses."""
        self.state.apps[app_name] = {
            "status": status,
            "last_used": time.time(),
            "count": self.state.apps.get(app_name, {}).get("count", 0) + 1
        }
        self.save()

    def define_safety_zone(self, path: str, tier: str):
        """Marks specific directories/apps with fixed stability/safety tiers."""
        self.state.safety_zones[path] = tier
        self.save()

    def map_path(self, path: str, purpose: str):
        """Maps a physical path to a semantic purpose (e.g. 'Project VIKI')."""
        self.state.semantic_paths[path] = purpose
        self.save()

    def set_active_file(self, file_path: str):
        """v25: Tracks the currently hot file context."""
        if file_path in self.state.active_context:
            self.state.active_context.remove(file_path)
        self.state.active_context.insert(0, file_path)
        # Keep latest 5 hot files
        self.state.active_context = self.state.active_context[:5]
        self.save()

    def add_habit(self, pattern: str, frequency: str = "occasional"):
        """Records a recurring user behavior for context injection."""
        self.state.user_habits.append({
            "pattern": pattern,
            "frequency": frequency,
            "recorded_at": time.time()
        })
        # Keep only latest 10 habits
        if len(self.state.user_habits) > 10:
            self.state.user_habits.pop(0)
        self.save()

    def _exceeds_depth(self, root: str, root_dir: str, max_depth: int) -> bool:
        """Returns True when the walk depth exceeds the limit."""
        depth = root[len(root_dir):].count(os.sep)
        return depth > max_depth

    def _to_lower_set(self, items: List[str]) -> set:
        """Lowercase a list of path parts for efficient set intersections."""
        return {str(x).lower() for x in items}

    def _maybe_record_project(self, root: str, dirs_l: set, files_l: set, project_markers_l: set) -> int:
        """Record a semantic path landmark when project markers are present."""
        if not (project_markers_l & dirs_l) and not (project_markers_l & files_l):
            return 0

        # Only count when we add a new landmark.
        if root in self.state.semantic_paths:
            return 0

        purpose = f"Active Project: {os.path.basename(root)}"
        self.state.semantic_paths[root] = purpose
        viki_logger.debug(f"WorldModel: Discovered project structure at {root}")
        return 1

    def _protect_dev_envs(self, root: str, dirs_l: set, safe_envs: set) -> int:
        """Protect known dev environment folders by adding them to safety_zones."""
        protected = 0
        for env_name in dirs_l & safe_envs:
            env_path = os.path.join(root, env_name)
            if env_path in self.state.safety_zones:
                continue
            self.state.safety_zones[env_path] = "protected"
            viki_logger.debug(f"WorldModel: auto-protecting sensitive zone: {env_path}")
            protected += 1
        return protected

    def analyze_workspace(self, root_dir: str):
        """
        v22: Autonomous World Discovery.
        Scans the filesystem to identify projects, dev environments, and protected zones.
        """
        viki_logger.info(f"WorldModel: Initiating autonomous scan of {root_dir}...")

        project_markers = {".git", ".project", "architecture.md", "viki"}
        safe_envs = {".venv", "node_modules", "dist", "build", "__pycache__"}
        project_markers_l = {m.lower() for m in project_markers}

        discovered_paths = 0
        for root, dirs, files in os.walk(root_dir):
            # Limit depth for performance
            if self._exceeds_depth(root, root_dir, max_depth=3):
                continue

            dirs_l = self._to_lower_set(dirs)
            files_l = self._to_lower_set(files)

            discovered_paths += self._maybe_record_project(
                root=root,
                dirs_l=dirs_l,
                files_l=files_l,
                project_markers_l=project_markers_l,
            )
            discovered_paths += self._protect_dev_envs(root=root, dirs_l=dirs_l, safe_envs=safe_envs)

        if discovered_paths <= 0:
            return

        viki_logger.info(
            f"WorldModel: Scan complete. Discovered {discovered_paths} semantic landmarks."
        )
        self.save()

    def scan_codebase(self, root_dir: str):
        """
        v25: Deep Codebase Awareness (Phase 4).
        Parses all Python files to build a dependency graph and structural map.
        """
        viki_logger.info(f"WorldModel: Building Codebase Graph for {root_dir}...")

        graph: Dict[str, Any] = {}
        for root, _, files in os.walk(root_dir):
            if "node_modules" in root or ".venv" in root or "__pycache__" in root:
                continue

            for file in files:
                if not file.endswith(".py"):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir)
                entry = self._scan_python_file(full_path=full_path, rel_path=rel_path)
                if entry is not None:
                    graph[rel_path] = entry

        self.state.codebase_graph = graph
        viki_logger.info(f"WorldModel: Codebase Graph complete. {len(graph)} modules mapped.")
        self.save()

    def _extract_imports_from_ast(self, tree: ast.AST) -> List[str]:
        """Extract import targets from an AST."""
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        return imports

    def _scan_python_file(self, full_path: str, rel_path: str) -> Optional[Dict[str, Any]]:
        """Scan a single Python file for structural metadata."""
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)

            imports = self._extract_imports_from_ast(tree)
            return {
                "imports": list(set(imports)),
                "size": len(content),
                "last_scan": time.time(),
            }
        except Exception as e:
            viki_logger.debug(f"WorldModel: Failed to parse {rel_path}: {e}")
            return None

    def start_mission(self, goal: str, project: Optional[str] = None):
        """v26: Initializes an autonomous execution mission."""
        self.state.active_goal = goal
        self.state.active_project = project or os.path.basename(os.getcwd())
        self.state.current_phase = "PLANNING"
        self.state.execution_started = True
        self.state.retry_count = 0
        viki_logger.info(f"WorldModel: Mission Started -> {goal}")
        self.save()

    def update_mission_phase(self, phase: str):
        """v26: Transitions the mission to a new lifecycle phase."""
        self.state.last_phase = self.state.current_phase
        self.state.current_phase = phase.upper()
        viki_logger.info(f"WorldModel: Mission Phase Transition -> {self.state.current_phase}")
        self.save()

    def finish_mission(self, summary: str = "", success: bool = True):
        """Finalize the current mission and archive state."""
        status = "COMPLETE" if success else "FAILED"
        self.state.current_phase = "complete"
        viki_logger.info(f"WorldModel: Mission {status}. Summary: {summary[:50]}...")
        self.state.active_goal = None
        self.state.execution_started = False
        self._save_state()

    def get_active_mission(self) -> Optional[Dict[str, Any]]:
        """Returns the current active mission if one exists."""
        if self.state.active_goal and self.state.current_phase.upper() != "COMPLETE":
            return {
                "goal": self.state.active_goal,
                "project": self.state.active_project,
                "phase": self.state.current_phase
            }
        return None

    def get_understanding(self) -> str:
        """Returns a summarized textual prompt of the current world understanding."""
        apps = ", ".join(list(self.state.apps.keys())[:5])
        zones = ", ".join([f"{k}({v})" for k, v in list(self.state.safety_zones.items())[:3]])
        paths = ", ".join([f"{v}" for v in list(self.state.semantic_paths.values())[:5]])
        habits = ", ".join([h['pattern'] for h in self.state.user_habits[-3:]])
        
        # v25: Graph Insight
        active = self.state.active_context
        graph_size = len(self.state.codebase_graph)

        lines: List[str] = ["WORLD MODEL AWARENESS:"]
        # Always show CWD so the LLM knows what directory it can read files from
        cwd = os.path.abspath(os.getcwd())
        lines.append(f"- Current Working Directory: {cwd}")
        
        # v26: Mission Status
        if self.state.active_goal:
            lines.append(f"- Active Goal: {self.state.active_goal}")
            lines.append(f"- Current Phase: {self.state.current_phase}")

        if apps:
            lines.append(f"- Identified Apps: {apps}")
        if paths:
            lines.append(f"- Known Projects/Zones: {paths}")
        if habits:
            lines.append(f"- Personal Habits: {habits}")
        if zones:
            lines.append(f"- Safety Rules: {zones}")

        graph_focus_line = self._build_graph_focus_line(graph_size=graph_size, active=active)
        if graph_focus_line:
            lines.append(graph_focus_line)

        return "\n".join(lines)

    def _build_graph_focus_line(self, graph_size: int, active: List[str]) -> Optional[str]:
        """Build the single-line codebase graph insight block."""
        if graph_size <= 0:
            return None

        graph_line = f"- Codebase Graph: {graph_size} modules mapped."
        if not active:
            return graph_line

        primary_path = active[0].replace("/", os.sep).replace("\\", os.sep)
        primary_mod = primary_path.replace(".py", "").replace(os.sep, ".")

        graph_line += f" Focus: {primary_path}."

        dependents = self._find_dependents(primary_mod=primary_mod)
        if dependents:
            graph_line += f" Note: Impacted by changes to {primary_path}: {', '.join(dependents[:3])}."

        return graph_line

    def _find_dependents(self, primary_mod: str) -> List[str]:
        """Find files impacted by changes to the given module."""
        dependents: List[str] = []
        primary_tail = primary_mod.split(".")[-1]
        for p, data in self.state.codebase_graph.items():
            for imp in data.get("imports", []):
                if primary_mod in imp or imp.endswith(primary_tail):
                    dependents.append(p)
                    break
        return dependents
