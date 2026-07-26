import unittest

from src.services.data_validator_service import DataValidatorService

# Mocking dependencies that would normally be imported from viki/services/...


class TestDataValidatorService(unittest.TestCase):
    """Tests the core validation logic of the DataValidatorService."""

    @classmethod
    def setUpClass(cls):
        # Setup: Ensure a clean slate for schema registry before running tests
        # In a real setup, we might need to clear global state or use mocking frameworks.
        print("Setting up test environment...")
        # Placeholder for actual cleanup/setup

    def setUp(self):
        """Set up a fresh validator instance before each test."""
        self.validator = DataValidatorService()

    # --- Test Case 1: Successful Validation (Triples) ---
    def test_validate_successful_triples(self):
        """Tests validation when data perfectly matches the expected triple schema."""
        valid_data: list[tuple[str, str, str]] = [("Skill", "REQUIRES", "Concept")]
        # We use 'triples' as the key because that is what we expect to validate here.
        report = self.validator.validate(valid_data, schema_key="triples")
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)

    # --- Test Case 2: Type Mismatch Failure (Usage Log) ---
    def test_validate_type_mismatch_usage_log(self):
        """Tests failure when a field has the wrong data type."""
        invalid_data = {
            "session_id": "abc-123",
            "event": "llm_inference",
            "prompt": 12345,  # Should be string, but is integer
        }
        report = self.validator.validate(invalid_data, schema_key="usage_log")
        self.assertFalse(report.is_valid)
        # Check if the specific error was logged
        error_found = any("Type Mismatch" in e["constraint"] for e in report.errors)
        self.assertTrue(error_found, "Expected Type Mismatch error not found.")

    # --- Test Case 3: Constraint Failure (KG Relationship) ---
    def test_validate_constraint_failure_kg(self):
        """Tests failure when a field value violates a custom constraint."""
        invalid_data = {
            "subject": "UnknownEntity",
            "predicate": "NON_EXISTENT_RELATIONSHIP",  # This should fail the schema check
            "object": "Concept",
        }
        report = self.validator.validate(invalid_data, schema_key="triples")
        self.assertFalse(report.is_valid)
        # Check if the specific constraint error was logged
        error_found = any("Custom Constraint Failed" in e["constraint"] for e in report.errors)
        self.assertTrue(error_found, "Expected Custom Constraint Failure not found.")

    # --- Test Case 4: Empty/Missing Data ---
    def test_validate_missing_required_field(self):
        """Tests failure when a required field is entirely missing."""
        incomplete_data = {
            "subject": "Skill",
            # 'predicate' is missing
            "object": "Concept",
        }
        report = self.validator.validate(incomplete_data, schema_key="triples")
        self.assertFalse(report.is_valid)
        error_found = any(
            "Missing required field 'predicate'" in e["message"] for e in report.errors
        )
        self.assertTrue(error_found, "Expected Missing Required Field error not found.")


if __name__ == "__main__":
    unittest.main()
