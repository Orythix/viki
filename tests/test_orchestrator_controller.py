"""Tests for the decomposed VIKIController (mixins)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from viki.core.orchestrator import VIKIController


@pytest.fixture
def mock_controller():
    """Return a minimally initialized VIKIController with all deps mocked."""
    patcher = patch.multiple(
        "viki.core.orchestrator",
        SkillRegistry=MagicMock(),
        HierarchicalMemory=MagicMock(),
        CapabilityRegistry=MagicMock(),
        EthicalGovernor=MagicMock(),
        ModelRouter=MagicMock(),
        ReflexBrain=MagicMock(),
        DeliberationEngine=MagicMock(),
        ReflectorModule=MagicMock(),
        ConsciousnessStack=MagicMock(),
        MissionControl=MagicMock(),
        RuntimeHealthReporter=MagicMock(),
        IntelligenceScorecard=MagicMock(),
        SelfModel=MagicMock(),
        SafetyLayer=MagicMock(),
        JudgmentEngine=MagicMock(),
        Soul=MagicMock(),
        DreamModule=MagicMock(),
        LearningModule=MagicMock(),
        ContinuousLearner=MagicMock(),
        CognitiveRouter=MagicMock(),
        EndpointGuardService=MagicMock(),
        SemanticFS=MagicMock(),
        ConfigWatcher=MagicMock(),
        ControlledBenchmark=MagicMock(),
        ModelABTest=MagicMock(),
        ToolContractValidator=MagicMock(),
        SuperAdminLayer=MagicMock(),
        TestHealerPipeline=MagicMock(),
        TimeTravelModule=MagicMock(),
        KnowledgeGapDetector=MagicMock(),
        ForgeOrchestrator=MagicMock(),
        VoiceModule=MagicMock(),
        BioModule=MagicMock(),
        WatchdogModule=MagicMock(),
        MessagingNexus=MagicMock(),
        SimpleOpsPlanner=MagicMock(),
        TelemetryStore=MagicMock(),
        WellnessPulse=MagicMock(),
    )
    patcher.start()
    ctrl = VIKIController(
        settings_path=str(Path(__file__).parent / "fixtures" / "settings.yaml"),
        soul_path=str(Path(__file__).parent / "fixtures" / "soul.yaml"),
    )
    patcher.stop()
    return ctrl


class TestVIKIControllerDecomposition:
    """Verify the mixin decomposition preserves structure."""

    def test_mixin_mro(self):
        """VIKIController should inherit from all mixin classes."""
        names = [c.__name__ for c in VIKIController.__mro__]
        expected = [
            "LifecycleMixin",
            "SkillsMixin",
            "PipelineMixin",
            "ValidationMixin",
            "TelemetryMixin",
        ]
        for mixin in expected:
            assert mixin in names, f"{mixin} not found in MRO"

    def test_controller_init(self, mock_controller):
        """Controller should initialize without errors."""
        assert mock_controller is not None
        assert hasattr(mock_controller, "settings")
        assert hasattr(mock_controller, "skill_registry")
        assert hasattr(mock_controller, "memory")

    def test_shutdown_method_exists(self):
        """shutdown method should be defined and async."""
        assert hasattr(VIKIController, "shutdown")

    def test_process_request_method_exists(self):
        """process_request method should be defined and async."""
        assert hasattr(VIKIController, "process_request")
        assert callable(VIKIController.process_request)

    def test_attach_mcp_skills_sync(self, mock_controller):
        """attach_mcp_skills_sync (SkillsMixin) should be callable."""
        assert hasattr(mock_controller, "attach_mcp_skills_sync")

    def test_skills_mixin_loaded(self, mock_controller):
        """SkillsMixin methods should be accessible."""
        assert hasattr(mock_controller, "_register_default_skills")
        assert hasattr(mock_controller, "_execute_skill")
        assert hasattr(mock_controller, "attach_mcp_skills_sync")

    def test_validation_mixin_loaded(self, mock_controller):
        """ValidationMixin methods should be accessible."""
        assert hasattr(mock_controller, "_validate_required_params")
        assert hasattr(mock_controller, "_validate_param_spec")
        assert hasattr(mock_controller, "_validate_skill_output")

    def test_telemetry_mixin_loaded(self, mock_controller):
        """TelemetryMixin methods should be accessible."""
        assert hasattr(mock_controller, "track_touched_item")
        assert hasattr(mock_controller, "get_session_usage")
        assert hasattr(mock_controller, "get_runtime_health")
        assert hasattr(mock_controller, "get_sovereign_status")

    def test_lifecycle_mixin_loaded(self, mock_controller):
        """LifecycleMixin methods should be accessible."""
        assert hasattr(mock_controller, "_prewarm_default_model")
        assert hasattr(mock_controller, "resume_mission")

    def test_pipeline_mixin_loaded(self, mock_controller):
        """PipelineMixin methods should be accessible."""
        assert hasattr(mock_controller, "_process_reflex_outcome")
        assert hasattr(mock_controller, "_process_request_impl")
        assert hasattr(mock_controller, "_synthesize_answer_with_web_snippets")
