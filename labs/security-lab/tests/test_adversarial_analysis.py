from security.adversarial_analysis import adversarial_prompt_report


def test_adversarial_report_shape() -> None:
    r = adversarial_prompt_report("What is SSRF?", max_chars=1024)
    assert "injection" in r
    assert r["injection"]["blocked"] is False
    assert "memory_poisoning_mitigation" in r
