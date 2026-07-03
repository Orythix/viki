import asyncio
import unittest

from viki.core.performance_benchmark import ControlledBenchmark


class DummyControllerSuccess:
    async def process_request(self, prompt: str) -> str:
        # Universal response that satisfies all expected substrings in the
        # current superiority benchmark tasks.
        return (
            "Refusal cannot refuse safety won't can't unsafe dangerous. "
            "Request Clarification. "
            "Create folder then Move. Stable State Retention. "
            "Run verification. "
            "minimal patch smallest safe change Do not claim execution. "
            "capability validate precondition verification postcondition. "
            "Use research instead of guessing https://example.com CONTENT FROM https://example.com "
            "SOURCE: https://example.com fact. "
            "OpsPlan ApprovalRequirement request approval No side effects message_drafts "
            "channel audit facts_used OpsFact"
        )


class DummyControllerFailure:
    async def process_request(self, prompt: str) -> str:
        return "Random non-matching response."


class TestControlledBenchmark(unittest.TestCase):
    def async_test(coro):
        def wrapper(self):
            return asyncio.run(coro(self))

        return wrapper

    @async_test
    async def test_superiority_suite_loads(self):
        cb = ControlledBenchmark(controller=DummyControllerSuccess())
        suites = cb.list_suites()
        self.assertIn("superiority", suites)
        tasks = cb.get_tasks("superiority")
        self.assertGreater(len(tasks), 0)

    @async_test
    async def test_superiority_suite_scoring_success(self):
        cb = ControlledBenchmark(controller=DummyControllerSuccess())
        tasks = cb.get_tasks("superiority")
        results = await cb.run_suite(model_label="dummy-success", suite_name="superiority")
        self.assertEqual(len(results), len(tasks))
        self.assertTrue(all(r.success for r in results))
        self.assertTrue(all(isinstance(r.latency, float) for r in results))

    @async_test
    async def test_superiority_suite_scoring_failure(self):
        cb = ControlledBenchmark(controller=DummyControllerFailure())
        tasks = cb.get_tasks("superiority")
        results = await cb.run_suite(model_label="dummy-failure", suite_name="superiority")
        self.assertEqual(len(results), len(tasks))
        self.assertTrue(any(not r.success for r in results))


if __name__ == "__main__":
    unittest.main()
