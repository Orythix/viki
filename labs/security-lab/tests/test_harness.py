from security.testing_harness import (
    run_injection_suite,
    run_jailbreak_policy_suite,
    run_tool_abuse_checks,
)


def test_injection_suite_all_pass():
    results = run_injection_suite()
    for name, ok, rep in results:
        assert ok, f"case {name} failed score={rep.score} reasons={rep.reasons}"


def test_jailbreak_policy_suite_all_pass():
    results = run_jailbreak_policy_suite()
    for name, ok, rep in results:
        assert ok, f"case {name} failed score={rep.score} reasons={rep.reasons}"


def test_tool_abuse_checks_all_pass():
    checks = run_tool_abuse_checks()
    assert checks
    assert all(c["passed"] for c in checks), checks
