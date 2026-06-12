import pytest
from viki.core.orchestrator import VIKIController
from viki.core.rapid_response_system import ReflexBrain
from viki.skills.builtins.time_skill import TimeSkill


@pytest.fixture
async def orchestrator():
    # Use a mock/test config path
    settings_path = "./tests/test_settings.yaml"
    soul_path = "./tests/data/test_soul.yaml"
    orc = VIKIController(settings_path, soul_path)
    yield orc
    await orc.shutdown()


@pytest.mark.asyncio
async def test_scenario_time_reflex():
    """Scenario 1: Direct Reflex Hit for Time."""
    reflex = ReflexBrain()
    # Test "what time is it in Sweden"
    resp, action = reflex.think("what time is it in Sweden")

    assert resp is None
    assert action is not None
    assert action.skill_name == "time_skill"
    assert action.parameters.get("location") == "sweden"

    # Test execution
    skill = TimeSkill()
    result = await skill.execute({"location": "sweden"})
    assert "CET" in result or "CEST" in result
    assert "Sweden" in result


@pytest.mark.asyncio
async def test_scenario_singularity_activation(orchestrator):
    """Scenario 2: Singularity Activation Trigger."""
    # This should hit the reflex layer inside process_request
    resp = await orchestrator.process_request("give superpower to viki")

    assert "Sovereign Singularity mode activated" in resp
    assert orchestrator.is_singularity_mode is True


@pytest.mark.asyncio
async def test_scenario_response_discipline(orchestrator):
    """Scenario 3: Verifying Concise Response (No Monologues)."""
    # We check if the DeliberationLayer correctly builds directives with SINGULARITY_MANDATE
    from viki.core.cognitive_processor import DeliberationLayer

    # We find the DeliberationLayer in the orchestrator's cortex
    deliberation = next(
        layer for layer in orchestrator.cortex.layers if isinstance(layer, DeliberationLayer)
    )

    # Build directives with singularity=True
    directives = deliberation._build_operating_directives(
        skills_context="[Skills]",
        url_info="",
        awareness="",
        react_note="",
        is_singularity_mode=True,
    )

    assert "[SINGULARITY MODE ACTIVATED]" in directives
    assert "CONCISE & DIRECT" in directives
    assert "NO MONOLOGUES" in directives
    assert "autonomy is absolute" in directives


@pytest.mark.asyncio
async def test_scenario_memory_management(orchestrator):
    """Scenario 4: Memory Skill CRUD & Stats."""
    mem_skill = orchestrator.skill_registry.get_skill("memory")
    assert mem_skill is not None

    # Check stats
    res = await mem_skill.execute({"action": "stats"})
    assert "Sovereign Memory Stats" in res
    assert "Lessons" in res

    # Check sessions
    orchestrator.memory.working.add_message("user", "Scenario testing")
    res = await mem_skill.execute({"action": "sessions"})
    assert "ACTIVE SESSIONS" in res
