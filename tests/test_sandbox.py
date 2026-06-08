"""
P1: tests for the sandbox executor selection + subprocess backend.

We deliberately don't run Docker in CI; we just confirm the selector picks
the correct backend and the subprocess path produces clean output.
"""
from __future__ import annotations

import asyncio
import unittest

from core.execution_environment import SubprocessSandbox, DockerSandbox, get_sandbox


def _run(coro):
    return asyncio.run(coro)


class TestSandbox(unittest.TestCase):
    def test_subprocess_runs_python(self):
        s = SubprocessSandbox()
        result = _run(s.run_python("print('hello sandbox')", timeout=10))
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello sandbox", result.stdout)

    def test_subprocess_reports_failure(self):
        s = SubprocessSandbox()
        result = _run(s.run_python("raise ValueError('bad')", timeout=10))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("ValueError", result.stderr)

    def test_get_sandbox_default_is_subprocess(self):
        s = get_sandbox(controller=None)
        self.assertIsInstance(s, SubprocessSandbox)

    def test_docker_falls_back_when_unavailable(self):
        # We patch is_available to False to confirm the runner falls through
        # to subprocess instead of crashing.
        original = DockerSandbox.is_available
        try:
            DockerSandbox.is_available = staticmethod(lambda: False)  # type: ignore
            d = DockerSandbox()
            result = _run(d.run_python("print('x')", timeout=10))
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.backend, "subprocess")
        finally:
            DockerSandbox.is_available = original  # type: ignore


if __name__ == "__main__":
    unittest.main()
