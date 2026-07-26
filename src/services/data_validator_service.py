from typing import Dict, Any, List, Tuple, Union
from src.services.schema_registry import SchemaRegistry

class ValidationReport:
    """A structured report detailing validation outcomes."""
    def __init__(self, is_valid: bool = True):
        self.is_valid = is_valid
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

    def add_error(self, field: str, source: str, message: str, constraint: str):
        self.is_valid = False
        self.errors.append({"field": field, "source": source, "message": message, "constraint": constraint})

    def add_warning(self, field: str, source: str, message: str):
        self.warnings.append({"field": field, "source": source, "message": message})

class DataValidatorService:
    """
    Centralized service responsible for validating data against registered schemas.
    Acts as the mandatory gatekeeper before persistence or training.
    """
    def __init__(self):
        print("DataValidatorService initialized and ready to enforce schema rules.")

    def validate(self, data: Union[Dict, List[Dict], List[Tuple]], schema_key: str) -> ValidationReport:
        """
        Validates the input data against the specified schema key.
        Returns a detailed ValidationReport object.
        """
        schema = SchemaRegistry.get_schema(schema_key)
        if not schema:
            raise ValueError(f"No schema registered for key: {schema_key}")

        report = ValidationReport()

        # --- Dispatch based on expected data type/structure ---
        if isinstance(data, dict):
            self._validate_single_dict(data, schema, report)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._validate_single_dict(item, schema, report)
                # Add logic for other types (e.g., tuples for triples)
        else:
             report.add_error("N/A", "System", "Unsupported data type provided to validator.", "Type Error")

        return report

    def _validate_single_dict(self, data: Dict[str, Any], schema: Dict[str, Any], report: ValidationReport):
        """Validates a single dictionary against the schema."""
        # 1. Check for required fields
        for field in schema.get("required", []):
            if field not in data or data[field] is None:
                report.add_error(field, "SchemaCheck", f"Missing required field '{field}'.", "Required Field Missing")

        # 2. Check types and constraints for present fields
        for field, value in data.items():
            if field not in schema["types"]: continue # Skip unknown fields

            expected_type = schema["types"][field]
            
            # Type check
            if not isinstance(value, expected_type):
                report.add_error(field, "TypeCheck", f"Expected type {expected_type.__name__}, got {type(value).__name__}.", "Type Mismatch")
                continue # Cannot proceed with constraints if type is wrong

            # Constraint check (e.g., regex, range)
            if "constraints" in schema and field in schema["constraints"]:
                constraint_func = schema["constraints"][field]
                try:
                    if not constraint_func(value):
                        report.add_error(field, "ConstraintCheck", f"Value '{value}' failed custom validation.", "Custom Constraint Failed")
                except Exception as e:
                     report.add_warning(field, "ConstraintCheck", f"Error during constraint check: {e}")

# ...existing code...