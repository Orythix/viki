import os
import json
import time
import ast
from typing import Dict, Any, List
from viki.core.schema import WorldState
from viki.config.logger import viki_logger

class WorldModel:
    """
    v10: Persistent Internal model of the environment.
    Unlike Memory, this is absolute stateful understanding.
    """
    def __init__(self, data_path: str):
        self.path = os.path.join(data_path, "world_state.json")
        self.state = self._load()

    def _load(self) -> WorldState:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                    return WorldState(**data)
            except:
                pass
        return WorldState()

    def save(self):
        self.state.last_updated = time.time()
        with open(self.path, 'w') as f:
            json.dump(self.state.model_dump(), f, indent=4)

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

    def analyze_workspace(self, root_dir: str):
        """
        v22: Autonomous World Discovery.
        Scans the filesystem to identify projects, dev environments, and protected zones.
        """
        viki_logger.info(f"WorldModel: Initiating autonomous scan of {root_dir}...")
        
        project_markers = {".git", ".project", "architecture.md", "viki"}
        safe_envs = {".venv", "node_modules", "dist", "build", "__pycache__"}
        
        discovered_paths = 0
        for root, dirs, files in os.walk(root_dir):
            # Limit depth for performance
            depth = root[len(root_dir):].count(os.sep)
            if depth > 3: continue
            
            # 1. Identify Projects (Semantic Paths)
            if any(marker in [d.lower() for d in dirs] or marker in [f.lower() for f in files] for marker in project_markers):
                purpose = f"Active Project: {os.path.basename(root)}"
                if root not in self.state.semantic_paths:
                    self.state.semantic_paths[root] = purpose
                    viki_logger.debug(f"WorldModel: Discovered project structure at {root}")
                    discovered_paths += 1
            
            # 2. Identify and Protect Dev Environments
            for d in dirs:
                if d.lower() in safe_envs:
                    env_path = os.path.join(root, d)
                    if env_path not in self.state.safety_zones:
                        self.state.safety_zones[env_path] = "protected"
                        viki_logger.debug(f"WorldModel: auto-protecting sensitive zone: {env_path}")
                        discovered_paths += 1
        
        if discovered_paths > 0:
            viki_logger.info(f"WorldModel: Scan complete. Discovered {discovered_paths} semantic landmarks.")
            self.save()

    def scan_codebase(self, root_dir: str):
        """
        v25: Deep Codebase Awareness (Phase 4).
        Parses all Python files to build a dependency graph and structural map.
        """
        viki_logger.info(f"WorldModel: Building Codebase Graph for {root_dir}...")
        
        graph = {}
        for root, _, files in os.walk(root_dir):
            if "node_modules" in root or ".venv" in root or "__pycache__" in root:
                continue
                
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir)
                    
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            tree = ast.parse(content)
                            
                        imports = []
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    imports.append(alias.name)
                            elif isinstance(node, ast.ImportFrom):
                                imports.append(node.module or "")
                        
                        # Store structural metadata
                        graph[rel_path] = {
                            "imports": list(set(imports)),
                            "size": len(content),
                            "last_scan": time.time()
                        }
                    except Exception as e:
                        viki_logger.warning(f"WorldModel: Failed to parse {rel_path}: {e}")
        
        self.state.codebase_graph = graph
        viki_logger.info(f"WorldModel: Codebase Graph complete. {len(graph)} modules mapped.")
        self.save()

    def get_understanding(self) -> str:
        """Returns a summarized textual prompt of the current world understanding."""
        apps = ", ".join(list(self.state.apps.keys())[:5])
        zones = ", ".join([f"{k}({v})" for k, v in list(self.state.safety_zones.items())[:3]])
        paths = ", ".join([f"{v}" for v in list(self.state.semantic_paths.values())[:5]])
        habits = ", ".join([h['pattern'] for h in self.state.user_habits[-3:]])
        
        # v25: Graph Insight
        active = self.state.active_context
        graph_size = len(self.state.codebase_graph)
        
        understanding = f"WORLD MODEL AWARENESS:\n"
        if apps: understanding += f"- Identified Apps: {apps}\n"
        if paths: understanding += f"- Known Projects/Zones: {paths}\n"
        if habits: understanding += f"- Personal Habits: {habits}\n"
        if zones: understanding += f"- Safety Rules: {zones}\n"
        
        # Codebase Graph Injection
        if graph_size > 0:
             understanding += f"- Codebase Graph: {graph_size} modules mapped. "
             if active:
                  primary_path = active[0].replace("/", os.sep).replace("\\", os.sep)
                  # Convert path to module name for matching
                  primary_mod = primary_path.replace(".py", "").replace(os.sep, ".")
                  
                  understanding += f"Focus: {primary_path}. "
                  
                  # Find what depends on this file
                  dependents = []
                  for p, data in self.state.codebase_graph.items():
                      for imp in data.get('imports', []):
                          # Normalize paths for comparison
                          if primary_mod in imp or imp.endswith(primary_mod.split('.')[-1]):
                              dependents.append(p)
                              break
                  
                  if dependents:
                       understanding += f"Note: Impacted by changes to {primary_path}: {', '.join(dependents[:3])}."
        
        return understanding
