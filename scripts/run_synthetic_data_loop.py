import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all necessary components from the newly created services
from src.services.log_analyzer import UsageLogAnalyzer  # noqa: E402
from src.services.observability_service import ObservabilityService  # noqa: E402
from src.services.synthetic_data_generator import SyntheticDataGenerator  # noqa: E402

def run_sdgl():
    """
    Orchestrates the entire Synthetic Data Generation Loop (SDGL) process:
    1. Analyze usage logs to find failure patterns.
    2. Use those patterns to generate synthetic training data.
    3. Save the resulting structured data for fine-tuning.
    """
    # Initialize Observability Service at the start of the main script execution
    observability = ObservabilityService()
    start_span = observability.start_span("SDGL_Pipeline")
    print("\n=========================================================")
    print("🚀 Starting Synthetic Data Generation Loop (SDGL) 🚀")
    print("=========================================================")

    # --- STEP 1: Analyze Usage Logs ---
    LOG_FILE = "data/usage_session.jsonl"
    analyzer = UsageLogAnalyzer(jsonl_path=LOG_FILE)
    try:
        analysis_report = analyzer.analyze_logs()
        observability.log_event("SDGL", {"step": "AnalysisComplete", "report": analysis_report})
        print("\n✅ Step 1 Complete: Log Analysis Report Generated.")
    except Exception as e:
        observability.end_span(start_span, status="FAILURE")
        print(f"\n❌ Error during log analysis (Step 1): {e}")
        return

    # --- STEP 2: Generate Synthetic Data ---
    generator = SyntheticDataGenerator(analysis_report=analysis_report)
    try:
        synthetic_data = generator.generate_interactions(data_format="DPO") # Start with DPO format
        observability.log_event("SDGL", {"step": "GenerationComplete", "count": len(synthetic_data)})
        print("\n✅ Step 2 Complete: Synthetic Interactions Generated.")
    except Exception as e:
        observability.end_span(start_span, status="FAILURE")
        print(f"\n❌ Error during synthetic data generation (Step 2): {e}")
        return

    # --- STEP 3: Save Data and Finalize ---
    from src.services.data_schema_manager import DataSchemaManager # Assuming this utility class exists or is created next
    try:
        DataSchemaManager().save_synthetic_data(synthetic_data, "DPO")
        observability.log_event("SDGL", {"step": "SaveComplete", "count": len(synthetic_data)})
        print("\n✅ Step 3 Complete: Synthetic data saved successfully.")
    except Exception as e:
        observability.end_span(start_span, status="FAILURE")
        print(f"\n❌ Error saving synthetic data (Step 3): {e}")
        return

    # Finalization
    observability.end_span(start_span, status="SUCCESS")
    print("\n=========================================================")
    print("✨ SDGL Pipeline Execution Finished Successfully! ✨")
    print("Generated data is ready for model fine-tuning.")
    print("=========================================================")


if __name__ == "__main__":
    # To run this script, ensure all dependencies (like the DataSchemaManager) are in place.
    run_sdgl()
