import asyncio
import os
from typing import Any, cast


async def handle_forge_command(controller: Any, user_input: str, session_id: str) -> str:
    task = user_input.replace("/forge", "").strip()
    if not task:
        return "Usage: /forge [task description | bake | switch | list]"

    if any(task.startswith(cmd) for cmd in ["bake", "switch", "list"]):
        parts = task.split()
        action = parts[0]
        profile = parts[1] if len(parts) > 1 else "general"
        forge_skill = controller.skill_registry.get_skill("internal_forge")
        if forge_skill:
            return cast("str", await forge_skill.execute({"action": action, "profile": profile}))

    mutation = await controller.evolution.propose_skill(task)
    if mutation:
        return f"Neural Forge: Synthesis started for '{task}'. View proposal with /evolve."
    return "Neural Forge: Synthesis failed."


async def handle_evolve_command(controller: Any) -> str:
    pending = controller.evolution.get_pending_proposals()
    if not pending:
        return "Evolution Stack: Stable. No pending modifications."
    items = [f"- [{p['id']}] {p['description']} (Streak: {p['success_count']}/3)" for p in pending]
    return (
        "PENDING EVOLUTION PROPOSALS:\n"
        + "\n".join(items)
        + f"\n\nUse /approve <id> or {controller.REJECT_TOKEN} <id> to moderate."
    )


async def handle_approve_command(controller: Any, user_input: str) -> str:
    m_id = user_input.replace("/approve", "").strip()
    if controller.evolution.approve_mutation(m_id):
        return f"Evolution Success: Modification {m_id} applied to core architecture."
    return "Invalid Mutation ID."


async def handle_reject_command(controller: Any, user_input: str) -> str:
    m_id = user_input.replace(controller.REJECT_TOKEN, "").strip()
    if controller.evolution.reject_mutation(m_id):
        return f"Evolution Blocked: Modification {m_id} discarded."
    return "Invalid Mutation ID."


async def handle_crystallize_command(controller: Any) -> str:
    await controller.evolution.crystallize_identity()
    return "Evolution Stack: Identity Crystallized. Mutation log archived to long-term memory."


async def handle_benchmark_command(controller: Any, user_input: str) -> str:
    parts = user_input.strip().split(maxsplit=1)
    suite_name = parts[1].strip().lower() if len(parts) > 1 else "core"
    available_suites = controller.benchmark.list_suites()
    if suite_name not in available_suites:
        return f"Unknown benchmark suite '{suite_name}'. Available suites: {', '.join(available_suites)}"
    controller._create_tracked_task(
        controller.benchmark.run_suite("Current-VIKI", suite_name=suite_name),
        f"benchmark_{suite_name}",
    )
    return f"BENCHMARK SUITE '{suite_name}' INITIATED. Judgment validation in progress."


async def handle_scorecard_command(controller: Any) -> str:
    summary = controller.scorecard.get_summary()
    stats = "\n".join([f"- {k}: {v:.2f}" for k, v in summary.items()])
    return f"INTELLIGENCE SCORECARD (Longitudinal Stability):\n{stats}"


async def handle_model_command(controller: Any) -> str:
    active = controller.model_router.default_model.model_name
    profiles = list(controller.model_router.models.keys())
    return f"ACTIVE DEFAULT: {active}\nAVAILABLE PROFILES: {', '.join(profiles)}"


async def handle_dream_command(controller: Any) -> str:
    await controller.memory.episodic.consolidate(controller.model_router)
    return "Narrative Stack: Dream Cycle complete. Episodes consolidated into semantic wisdom."


async def handle_scan_command(controller: Any) -> str:
    workspace_dir = controller.settings.get("system", {}).get(
        "workspace_dir", controller.DEFAULT_WORKSPACE_DIR
    )
    controller.world.scan_codebase(workspace_dir)
    return f"World Engine: Codebase Graph rebuilt. {len(controller.world.state.codebase_graph)} modules mapped."


async def handle_restore_command(controller: Any, user_input: str) -> str:
    rest = user_input.strip()[7:].strip()
    if not rest:
        checkpoints = controller.history.list_checkpoints(limit=20)
        if not checkpoints:
            return "No checkpoints found. Checkpoints are created before file/shell actions."
        lines = ["ID       | Time                  | Action", "-" * 50]
        for cp in checkpoints:
            lines.append(
                f"{cp.get('id', '?'):8} | {cp.get('timestamp', '')[:19]:20} | {cp.get('summary', '')[:40]}"
            )
        return "CHECKPOINTS (use /restore <id> to revert):\n" + "\n".join(lines)
    cp_id = rest.split()[0] if rest.split() else ""
    if cp_id:
        _, _, msg = controller.history.restore_checkpoint(cp_id)
        return cast("str", msg)
    return "Usage: /restore  or  /restore <id>"


async def handle_undo_command(controller: Any) -> str:
    ok, restored, msg = controller.history.undo_last()
    if not ok:
        return cast("str", msg)
    extras = (" Restored: " + ", ".join(restored)) if restored else ""
    return f"Undo: {msg}{extras}"


async def handle_save_command(controller: Any, user_input: str, session_id: str) -> str:
    name = user_input.strip()[5:].strip()
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        return "Usage: /save <name>  (e.g. /save my-session)"
    data_dir = controller.settings.get("system", {}).get("data_dir", controller.DEFAULT_DATA_DIR)
    sessions_dir = os.path.join(data_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    path = os.path.join(sessions_dir, f"{name}.json")
    try:
        trace = controller.memory.working.get_trace(session_id=session_id)
        await asyncio.to_thread(controller._write_json, path, {"messages": trace}, indent=2)
        return f"Session saved to {path} ({len(trace)} messages)."
    except Exception as e:
        return f"Save failed: {e}"


async def handle_load_command(controller: Any, user_input: str, session_id: str) -> str:
    name = user_input.strip()[5:].strip()
    if not name:
        return "Usage: /load <name>  (e.g. /load my-session)"
    data_dir = controller.settings.get("system", {}).get("data_dir", controller.DEFAULT_DATA_DIR)
    path = os.path.join(data_dir, "sessions", f"{name}.json")
    if not os.path.isfile(path):
        return f"Session not found: {path}"
    try:
        data = await asyncio.to_thread(controller._read_json, path)
        messages = data.get("messages", [])
        controller.memory.working.replace_trace(messages, session_id=session_id)
        return f"Loaded session '{name}' ({len(messages)} messages)."
    except Exception as e:
        return f"Load failed: {e}"


async def handle_fork_command(controller: Any, user_input: str, session_id: str) -> str:
    parts = user_input.strip().split(maxsplit=1)
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return "Usage: /fork <branch-name>  (e.g. /fork experiment-1)\nUse /branches to see all branches."
    description = ""
    if " " in name:
        name, description = name.split(maxsplit=1)
    bm = getattr(controller, "branch_manager", None)
    if bm is None:
        return "Branch manager not available."
    return cast(str, bm.fork(name, controller, description=description, session_id=session_id))


async def handle_switch_command(controller: Any, user_input: str) -> str:
    parts = user_input.strip().split(maxsplit=1)
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return "Usage: /switch <branch-name>\nUse /branches to list branches."
    bm = getattr(controller, "branch_manager", None)
    if bm is None:
        return "Branch manager not available."
    return cast(str, bm.switch(name, controller))


async def handle_branches_command(controller: Any) -> str:
    bm = getattr(controller, "branch_manager", None)
    if bm is None:
        return "Branch manager not available."
    current_sid = getattr(getattr(controller, "memory", None), "working", None)
    if current_sid:
        current_sid = getattr(current_sid, "default_session_id", None)
    return cast(str, bm.format_branch_list(current_session_id=current_sid))


async def handle_diff_command(controller: Any, user_input: str) -> str:
    parts = user_input.strip().split(maxsplit=1)
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return "Usage: /diff <branch-name>\nCompare current conversation with a branch."
    bm = getattr(controller, "branch_manager", None)
    if bm is None:
        return "Branch manager not available."
    return cast(str, bm.diff(name, controller))


async def handle_test_gen_command(controller: Any, user_input: str) -> str:
    parts = user_input.strip().split(maxsplit=1)
    rest = parts[1].strip() if len(parts) > 1 else ""
    if not rest:
        return "Usage: /test-gen <path> [--save] [--overview]\nExamples:\n  /test-gen src/viki/core/branch_manager.py\n  /test-gen src/viki/core/branch_manager.py --save\n  /test-gen src/viki/core/branch_manager.py --overview"
    path = ""
    save = False
    overview = False
    tokens = rest.split()
    for t in tokens:
        if t == "--save":
            save = True
        elif t == "--overview":
            overview = True
        elif not path:
            path = t
    if not path:
        return "Error: path is required."
    skill = controller.skill_registry.get_skill("test_gen")
    if skill is None:
        return "TestGenSkill not registered."
    return cast("str", await skill.execute({"path": path, "save": save, "overview": overview}))


async def handle_skills_command(controller: Any, user_input: str) -> str:
    """Manage community skills via the registry index."""
    from viki.skills.registry_public import SkillRegistryIndex

    parts = user_input.strip().split(maxsplit=2)
    action = parts[1].strip().lower() if len(parts) > 1 else ""
    arg = parts[2].strip() if len(parts) > 2 else ""

    data_dir = controller.settings.get("system", {}).get("data_dir", "./data")
    registry = SkillRegistryIndex(data_dir=data_dir)

    if action == "refresh":
        count = await registry.refresh_index()
        return f"Registry index refreshed: {count} packages found."

    if action == "search":
        if not arg:
            return "Usage: /skills search <query>"
        results = registry.search(arg)
        if not results:
            return f"No packages found for '{arg}'."
        lines = [f"{'Name':20} {'Version':10} {'Description':40}", "-" * 72]
        for pkg in results[:20]:
            lines.append(f"{pkg.name:20} {pkg.version:10} {pkg.description[:40]:40}")
        return "REGISTRY SEARCH RESULTS:\n" + "\n".join(lines)

    if action == "install":
        if not arg:
            return "Usage: /skills install <package-name>"
        result = await registry.install(arg)
        return result

    if action in ("list", "installed"):
        installed = registry.list_installed()
        if not installed:
            return "No packages installed."
        lines = [f"{'Name':20} {'Version':10} {'Path':40}", "-" * 72]
        for pkg in installed:
            lines.append(f"{pkg.name:20} {pkg.version:10} {pkg.install_path[:40]:40}")
        return "INSTALLED PACKAGES:\n" + "\n".join(lines)

    return "Usage: /skills <refresh|search|install|list> [args]"
