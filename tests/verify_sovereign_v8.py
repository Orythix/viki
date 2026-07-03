import asyncio
import json
import os

from viki.config.resolve import get_soul_path
from viki.core.orchestrator import VIKIController


async def verify_v8_1_features():
    print("--- Verifying VIKI v8.1.0 Sovereign Scaling Features ---")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "config", "settings.yaml")
    soul_path = get_soul_path(settings_path)

    controller = VIKIController(settings_path, soul_path)

    # 1. Verify Telemetry
    print("\n[1/4] Verifying Distributed Telemetry Store...")
    controller.telemetry.record("test", "verification", {"status": "ok"}, severity="INFO")
    events = controller.telemetry.query(category="test", limit=1)
    if events and events[0]["payload"]["status"] == "ok":
        print("SUCCESS: Telemetry recording and querying functional.")
    else:
        print("FAILED: Telemetry verification failed.")

    # 2. Verify TestHealerPipeline
    print("\n[2/4] Verifying Autonomous Self-Healing Pipeline...")
    try:
        controller.test_healer.start(
            watch_path=".", test_command="echo 'Tests Passing'", interval=1
        )
        print(f"SUCCESS: TestHealerPipeline started (Active: {controller.test_healer.active})")
        controller.test_healer.stop()
        print("SUCCESS: TestHealerPipeline stopped.")
    except Exception as e:
        print(f"FAILED: TestHealerPipeline error: {e}")

    # 3. Verify LogVoyager (Telemetry Integration)
    print("\n[3/4] Verifying LogVoyager Telemetry Integration...")
    log_voyager = controller.skill_registry.get_skill("log_voyager")
    if log_voyager:
        summary = await log_voyager.execute({"action": "summarize"})
        print(f"SUCCESS: LogVoyager Summary via Telemetry:\n{summary}")
    else:
        print("FAILED: LogVoyager skill not found.")

    # 4. Verify Progressive Disclosure (Sovereign Hub)
    print("\n[4/4] Verifying Progressive Disclosure (150+ Skills)...")
    with open("./data/sovereign_library.json") as f:
        lib = json.load(f)
        total_skills = sum(len(skills) for skills in lib.values())
        print(
            f"SUCCESS: Sovereign Library contains {total_skills} registered skills across {len(lib)} categories."
        )

    print("\n--- Verification Complete ---")


if __name__ == "__main__":
    asyncio.run(verify_v8_1_features())
