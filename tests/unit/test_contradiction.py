"""Tests for contradiction detection logic."""

from __future__ import annotations

import pytest

from viki.core.contradiction import (
    _parse_llm_judgment,
    detect_contradiction,
    extract_key_claims,
    has_negation,
    heuristic_contradiction_score,
)


class TestExtractKeyClaims:
    def test_empty_text(self) -> None:
        assert extract_key_claims("") == set()

    def test_short_text_skipped(self) -> None:
        assert extract_key_claims("a b") == {"a b"}

    def test_normal_text(self) -> None:
        claims = extract_key_claims("I like Python programming")
        assert "i like python" in claims
        assert "like python programming" in claims

    def test_punctuation_removed(self) -> None:
        claims = extract_key_claims("Hello, world!")
        assert "hello world" in claims


class TestHasNegation:
    def test_no_negation(self) -> None:
        assert has_negation("I like pizza") is False

    def test_negation_present(self) -> None:
        assert has_negation("I don't like pizza") is True

    def test_negation_not_word_boundary(self) -> None:
        assert has_negation("notable") is False

    def test_multiple_negations(self) -> None:
        assert has_negation("never and not ever") is True


class TestHeuristicContradictionScore:
    def test_no_overlap_returns_zero(self) -> None:
        score = heuristic_contradiction_score(
            "I like cats",
            "The weather is nice",
        )
        assert score == 0.0

    def test_negation_asymmetry_detected(self) -> None:
        score = heuristic_contradiction_score(
            "I like Python",
            "I don't like Python",
        )
        assert score > 0.0

    def test_contradictory_pair_detected(self) -> None:
        score = heuristic_contradiction_score(
            "Enable debugging mode",
            "Disable debugging mode",
        )
        assert score == 0.8

    def test_same_meaning_no_contradiction(self) -> None:
        score = heuristic_contradiction_score(
            "Python is great",
            "Python is wonderful",
        )
        assert score == 0.0

    def test_empty_inputs(self) -> None:
        assert heuristic_contradiction_score("", "something") == 0.0
        assert heuristic_contradiction_score("something", "") == 0.0
        assert heuristic_contradiction_score("", "") == 0.0

    def test_asymmetric_negation_capped(self) -> None:
        score = heuristic_contradiction_score(
            "a b c d e f",
            "a b c d e f not",
        )
        assert 0.0 < score <= 1.0


class TestDetectContradiction:
    @pytest.mark.asyncio
    async def test_high_heuristic_returns_early(self) -> None:
        result = await detect_contradiction(
            "I love Python programming",
            "I hate Python programming",
            model_router=None,
        )
        assert result is not None
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_no_contradiction_returns_none(self) -> None:
        result = await detect_contradiction(
            "I like programming",
            "The sky is blue",
            model_router=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_ambiguous_uses_llm(self) -> None:
        class _FakeRouter:
            async def chat(self, messages: list) -> str:
                return '{"contradiction": true, "confidence": 0.6, "reason": "test"}'

        result = await detect_contradiction(
            "The quick brown fox jumps",
            "The quick brown fox does not jump",
            model_router=_FakeRouter(),
        )
        assert result is not None
        assert result.confidence == 0.6
        assert result.judgment is not None

    @pytest.mark.asyncio
    async def test_llm_returns_no_contradiction(self) -> None:
        class _FakeRouter:
            async def chat(self, messages: list) -> str:
                return '{"contradiction": false, "confidence": 0.9}'

        result = await detect_contradiction(
            "Python is fast",
            "Python is somewhat fast",
            model_router=_FakeRouter(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_none(self) -> None:
        class _BrokenRouter:
            async def chat(self, messages: list) -> str:
                raise RuntimeError("API down")

        result = await detect_contradiction(
            "Python is fast",
            "Python is slow",
            model_router=_BrokenRouter(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_low_heuristic_returns_none(self) -> None:
        result = await detect_contradiction(
            "I like apples",
            "I like oranges",
            model_router=None,
        )
        assert result is None


class TestParseLLMJudgment:
    def test_valid_json_contradiction(self) -> None:
        result = _parse_llm_judgment(
            '{"contradiction": true, "confidence": 0.75, "reason": "conflict"}'
        )
        assert result is not None
        assert result.confidence == 0.75
        assert result.reason == "conflict"

    def test_valid_json_no_contradiction(self) -> None:
        result = _parse_llm_judgment('{"contradiction": false, "confidence": 0.0}')
        assert result is None

    def test_invalid_json(self) -> None:
        result = _parse_llm_judgment("not json")
        assert result is None

    def test_json_with_surrounding_text(self) -> None:
        result = _parse_llm_judgment(
            'Here is my analysis: {"contradiction": true, "confidence": 0.8}'
        )
        assert result is not None

    def test_empty_input(self) -> None:
        result = _parse_llm_judgment("")
        assert result is None
