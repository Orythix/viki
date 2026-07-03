"""
Phase 2: real evaluators for agent benchmarks.

Replaces the keyword-only grading in `viki/core/benchmark.py` with two real
graders:

- `ExecutionEvaluator` — runs Python code (or shell commands) in a sandboxed
  subprocess against a hidden test case. Suitable for HumanEval+, BigCodeBench,
  LiveCodeBench, SWE-bench. Returns a numeric score in [0, 1].

- `LLMJudgeEvaluator` — three-judge majority using frontier or local LLM(s)
  with an explicit rubric. Suitable for GAIA, AgentBench, free-form answers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, cast

from viki.config.logger import viki_logger


@dataclass
class EvalScore:
    score: float  # 0.0..1.0
    passed: bool
    reason: str = ""
    runtime_seconds: float = 0.0
    judge_votes: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "passed": bool(self.passed),
            "reason": self.reason,
            "runtime_seconds": round(self.runtime_seconds, 3),
            "judge_votes": self.judge_votes,
            "metrics": self.metrics,
        }


# ---------------------------------------------------------------------------
# ExecutionEvaluator
# ---------------------------------------------------------------------------
class ExecutionEvaluator:
    """
    Run agent-produced code against a hidden test in a subprocess sandbox.

    Inputs (via `evaluate(...)`):
      task: dict with optional fields:
        - "test_code"   : Python source containing a `check(candidate)` function or top-level asserts.
        - "stdin"       : str piped to stdin.
        - "expected_stdout": substring asserted in stdout.
        - "language"    : "python" (default) or "shell".
        - "timeout"     : seconds (default 8).
      candidate: the agent's answer text (we extract code blocks).
    """

    DEFAULT_TIMEOUT = 8

    def evaluate(self, task: dict[str, Any], candidate: str) -> EvalScore:
        t0 = time.perf_counter()
        language = (task.get("language") or "python").lower()
        timeout = int(task.get("timeout", self.DEFAULT_TIMEOUT))

        code = self._extract_code(candidate, language)
        if not code.strip():
            return EvalScore(
                score=0.0,
                passed=False,
                reason="No executable code block found in candidate.",
                runtime_seconds=time.perf_counter() - t0,
            )

        if language == "python":
            result = self._run_python(code, task, timeout)
        elif language == "shell":
            result = self._run_shell(code, task, timeout)
        else:
            return EvalScore(score=0.0, passed=False, reason=f"Unsupported language: {language}")

        result.runtime_seconds = time.perf_counter() - t0
        return result

    @staticmethod
    def _extract_code(candidate: str, language: str) -> str:
        """Pull a fenced code block out of the candidate; fall back to whole text."""
        if not candidate:
            return ""
        s = str(candidate)
        markers = (
            f"```{language}",
            "```python",
            "```py",
            "```sh",
            "```bash",
            "```",
        )
        for m in markers:
            idx = s.find(m)
            if idx != -1:
                rest = s[idx + len(m) :]
                end = rest.find("```")
                if end != -1:
                    return rest[:end].strip("\n").strip()
        return s.strip()

    @staticmethod
    def _validate_code_safety(code: str, test_code: str) -> str | None:
        """Return an error string if dangerous patterns are found, else None."""
        full = code + "\n" + test_code
        dangerous_patterns = [
            "os.system",
            "subprocess",
            "eval(",
            "exec(",
            "compile(",
            "__import__",
            "importlib",
            "ctypes",
            "multiprocessing",
            "pickle.loads",
            "marshal.loads",
            "open(",
        ]
        for pat in dangerous_patterns:
            if pat in full:
                return f"Dangerous pattern detected: {pat}"
        try:
            import ast

            tree = ast.parse(full)
        except SyntaxError as e:
            return f"Syntax error: {e}"
        dangerous_calls = {"eval", "exec", "compile", "__import__", "open"}
        dangerous_attrs = {
            "__globals__",
            "__code__",
            "__builtins__",
            "__class__",
            "__mro__",
            "__subclasses__",
            "__reduce__",
            "__reduce_ex__",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {
                        "subprocess",
                        "os",
                        "sys",
                        "ctypes",
                        "importlib",
                        "pickle",
                        "marshal",
                    }:
                        return f"Dangerous import: {alias.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module in {"subprocess", "os", "ctypes", "importlib", "pickle", "marshal"}:
                    return f"Dangerous import from: {node.module}"
                for alias in node.names:
                    if alias.name in dangerous_calls:
                        return f"Dangerous function import: {alias.name}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_calls:
                    return f"Dangerous function call: {node.func.id}()"
            if isinstance(node, ast.Attribute) and node.attr in dangerous_attrs:
                return f"Dangerous attribute access: {node.attr}"
        return None

    def _run_python(self, code: str, task: dict[str, Any], timeout: int) -> EvalScore:
        """Run candidate Python code under hidden checks in a fresh subprocess."""
        test_code = task.get("test_code") or ""
        stdin = task.get("stdin") or ""
        expected_stdout = (task.get("expected_stdout") or "").strip()

        safety_err = self._validate_code_safety(code, test_code)
        if safety_err:
            return EvalScore(score=0.0, passed=False, reason=f"Security rejection: {safety_err}")

        textwrap.dedent(
            """
            import sys
            import io
            import contextlib

            __captured_stdout = io.StringIO()
            with contextlib.redirect_stdout(__captured_stdout):
                _CANDIDATE_NAMESPACE = {}
            """
        )
        # Compose a single Python file that exec's the candidate then runs the test.
        # We make `_CANDIDATE_NAMESPACE` self-referential so test code can reach it.
        wrapper = textwrap.dedent(
            """
            import sys
            _CANDIDATE_NAMESPACE['_CANDIDATE_NAMESPACE'] = _CANDIDATE_NAMESPACE
            try:
                exec(compile(_CANDIDATE_CODE, '<candidate>', 'exec'), _CANDIDATE_NAMESPACE)
                if _TEST_CODE.strip():
                    exec(compile(_TEST_CODE, '<test>', 'exec'), _CANDIDATE_NAMESPACE)
                print('__VIKI_EVAL_PASS__')
            except SystemExit:
                print('__VIKI_EVAL_PASS__')
            except Exception as e:
                print(f'__VIKI_EVAL_FAIL__:{type(e).__name__}:{e}')
                sys.exit(1)
            """
        )
        full_source = (
            f"_CANDIDATE_CODE = {json.dumps(code)}\n"
            f"_TEST_CODE = {json.dumps(test_code)}\n"
            f"_CANDIDATE_NAMESPACE = {{}}\n"
            f"{wrapper}"
        )

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(full_source)
            path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, "-I", path],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return EvalScore(score=0.0, passed=False, reason=f"Timeout after {timeout}s")
        except Exception as e:
            return EvalScore(score=0.0, passed=False, reason=f"Exec failed: {e}")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        passed = "__VIKI_EVAL_PASS__" in stdout and proc.returncode == 0

        if expected_stdout and expected_stdout not in stdout:
            passed = False

        return EvalScore(
            score=1.0 if passed else 0.0,
            passed=passed,
            reason="ok" if passed else (stderr[:500] or stdout[:500] or "unknown"),
            metrics={
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "returncode": proc.returncode,
            },
        )

    def _run_shell(self, code: str, task: dict[str, Any], timeout: int) -> EvalScore:
        expected_stdout = (task.get("expected_stdout") or "").strip()
        try:
            proc = subprocess.run(
                code,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return EvalScore(score=0.0, passed=False, reason=f"Timeout after {timeout}s")
        except Exception as e:
            return EvalScore(score=0.0, passed=False, reason=f"Shell failed: {e}")

        stdout = proc.stdout or ""
        passed = proc.returncode == 0
        if expected_stdout:
            passed = passed and expected_stdout in stdout

        return EvalScore(
            score=1.0 if passed else 0.0,
            passed=passed,
            reason="ok" if passed else (proc.stderr or stdout)[:500],
            metrics={
                "stdout": stdout[:2000],
                "stderr": (proc.stderr or "")[:2000],
                "returncode": proc.returncode,
            },
        )


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator (three-judge majority)
# ---------------------------------------------------------------------------
class LLMJudgeEvaluator:
    """
    Three-judge majority using the model router's failover chain.
    Each judge returns a score in [0,1] and a one-line rationale; the final score
    is the mean, but `passed` is the majority vote on `score >= pass_threshold`.
    """

    DEFAULT_PASS_THRESHOLD = 0.6

    def __init__(
        self, model_router, num_judges: int = 3, pass_threshold: float = DEFAULT_PASS_THRESHOLD
    ):
        self.model_router = model_router
        self.num_judges = max(1, int(num_judges))
        self.pass_threshold = float(pass_threshold)

    async def evaluate(self, task: dict[str, Any], candidate: str) -> EvalScore:
        t0 = time.perf_counter()
        prompt = self._build_prompt(task, candidate)
        judges = self._select_judges()

        votes: list[dict[str, Any]] = []
        for i, judge in enumerate(judges):
            try:
                raw = await judge.chat(
                    [
                        {
                            "role": "system",
                            "content": "You are an impartial agent evaluator. Output only JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                )
                parsed = self._parse_judge_response(raw)
                votes.append(
                    {
                        "judge": getattr(judge, "model_name", f"judge_{i}"),
                        "provider": getattr(judge, "provider_name", "unknown"),
                        "score": float(parsed.get("score", 0.0)),
                        "rationale": str(parsed.get("rationale", ""))[:200],
                    }
                )
            except Exception as e:
                viki_logger.debug("LLM judge %s failed: %s", getattr(judge, "model_name", "?"), e)
                votes.append(
                    {
                        "judge": getattr(judge, "model_name", f"judge_{i}"),
                        "provider": getattr(judge, "provider_name", "unknown"),
                        "score": 0.0,
                        "rationale": f"judge_failure: {e}",
                    }
                )

        if not votes:
            return EvalScore(score=0.0, passed=False, reason="No judges available.")

        scores = [v["score"] for v in votes]
        mean_score = sum(scores) / len(scores)
        majority_pass = sum(1 for s in scores if s >= self.pass_threshold) > (len(scores) // 2)
        return EvalScore(
            score=mean_score,
            passed=majority_pass,
            reason=f"mean={mean_score:.3f}; majority_pass={majority_pass}",
            runtime_seconds=time.perf_counter() - t0,
            judge_votes=votes,
        )

    def _select_judges(self) -> list[Any]:
        """Pick `num_judges` distinct allowed models from the router's failover chain."""
        try:
            chain = self.model_router.get_failover_chain(["reasoning"], max_models=8)
        except Exception:
            chain = [self.model_router.get_model(["reasoning"])]
        seen_providers = set()
        judges = []
        # Prefer one judge per provider for diversity.
        for m in chain:
            provider = getattr(m, "provider_name", "unknown")
            if provider in seen_providers:
                continue
            seen_providers.add(provider)
            judges.append(m)
            if len(judges) >= self.num_judges:
                break
        # Fill remaining slots from chain head.
        idx = 0
        while len(judges) < self.num_judges and idx < len(chain):
            if chain[idx] not in judges:
                judges.append(chain[idx])
            idx += 1
        return judges

    @staticmethod
    def _build_prompt(task: dict[str, Any], candidate: str) -> str:
        rubric = (
            task.get("rubric") or "Score correctness, completeness, and faithfulness to the prompt."
        )
        ground_truth = task.get("ground_truth") or task.get("expected_outcome") or "(none)"
        return textwrap.dedent(
            f"""
            EVALUATE THIS AGENT RESPONSE.

            TASK:
            {task.get("prompt", "")}

            EXPECTED:
            {ground_truth}

            RUBRIC:
            {rubric}

            AGENT RESPONSE:
            {candidate}

            Score the response from 0.0 (terrible) to 1.0 (excellent). Output STRICT JSON:
            {{"score": <float>, "rationale": "<one sentence>"}}
            """
        ).strip()

    @staticmethod
    def _parse_judge_response(raw: Any) -> dict[str, Any]:
        text = raw if isinstance(raw, str) else str(raw or "")
        text = text.strip()
        # Extract first JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return cast("dict[str, Any]", json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                pass
        return {"score": 0.0, "rationale": "unparseable_judge_output"}
