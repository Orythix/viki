
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.cortex import ConsciousnessStack
from viki.core.llm import ModelRouter
from viki.core.world import WorldModel

class MockModel:
    def __init__(self, name="PlaceHolder"):
        self.model_name = name
    async def chat(self, prompt):
        return f"Perspective from {self.model_name}: This is a simulated response based on the prompt."
    async def chat_structured(self, messages, schema, image_path=None):
        # We need to return a VIKIResponse object
        from viki.core.schema import VIKIResponse, ThoughtObject, VIKIResponseLite
        
        if schema == VIKIResponse:
             return VIKIResponse(
                 final_thought=ThoughtObject(intent_summary="Test", primary_strategy="Test"),
                 final_response="Test response"
             )
        else:
             return VIKIResponseLite(final_response="Test").to_full_response()

class MockRouter:
    def __init__(self):
        self.default_model = MockModel()
    def get_model(self, capabilities=None):
        return self.default_model

async def verify_ensemble():
    print("--- Verifying Phase 5: Internal Ensemble Debate ---")
    
    # 1. Setup minimal stack with Mock Router
    router = MockRouter()
    cortex = ConsciousnessStack(router)
    
    # 2. Simulate a Coding Request (should trigger Architect)
    print("\n[Test 1] Simulating complex coding request...")
    user_input = "Refactor the memory module to be thread-safe and use redis."
    
    # We need to mock the context to simulate 'coding' intent detection effectively
    # triggering the ensemble logic inside DeliberationLayer
    
    # Actually, we can just test the EnsembleEngine directly first to verify agents exist
    from viki.core.ensemble import EnsembleEngine
    ensemble = EnsembleEngine(router)
    
    print(f"Agents loaded: {list(ensemble.agents.keys())}")
    
    if "architect" in ensemble.agents:
        print("SUCCESS: 'Architect' agent is present.")
    else:
        print("FAILURE: 'Architect' agent missing.")
        
    # 3. Test Ensemble Execution
    print("\n[Test 2] Running Ensemble Debate for Coding Task...")
    context = {"narrative_identity": "I am VIKI.", "conversation_history": []}
    selected = ["critic", "architect", "explorer"]
    
    results = await ensemble.run_ensemble(user_input, context, selected_agents=selected)
    
    print("\n--- DEBATE TRACE ---")
    for agent, perspective in results.items():
        print(f"\n[{agent.upper()}]: {perspective[:100]}...")
    
    if "architect" in results:
        print("\nSUCCESS: Architect perspective generated.")
    else:
        print("\nFAILURE: Architect did not participate.")

if __name__ == "__main__":
    asyncio.run(verify_ensemble())
