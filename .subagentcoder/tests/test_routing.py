"""Smoke tests for orchestrator routing auto-assignment heuristics.

Validates Requirement 2.5: Auto-assignment heuristics (orchestrator-side).
"""

from orchestrator.routing import auto_assign_routing


class TestLocalRouting:
    """Tasks routed to local: description ≤200 chars AND matches local keywords."""

    def test_short_extraction_task(self):
        desc = "Extract email field from JSON response"
        assert auto_assign_routing(desc) == "local"

    def test_boilerplate_task(self):
        desc = "Generate boilerplate CRUD handlers for User model"
        assert auto_assign_routing(desc) == "local"

    def test_repetitive_task(self):
        desc = "Apply repetitive import fixes across file"
        assert auto_assign_routing(desc) == "local"

    def test_single_file_task(self):
        desc = "Refactor single-file utility module"
        assert auto_assign_routing(desc) == "local"

    def test_scaffold_task(self):
        desc = "Scaffold a new controller module"
        assert auto_assign_routing(desc) == "local"

    def test_template_task(self):
        desc = "Create template for error response"
        assert auto_assign_routing(desc) == "local"

    def test_data_task(self):
        desc = "Parse data from CSV input"
        assert auto_assign_routing(desc) == "local"

    def test_config_task(self):
        desc = "Update config values for dev environment"
        assert auto_assign_routing(desc) == "local"

    def test_simple_task(self):
        desc = "Add simple validation to input field"
        assert auto_assign_routing(desc) == "local"

    def test_case_insensitive_matching(self):
        desc = "Generate BOILERPLATE for REST handler"
        assert auto_assign_routing(desc) == "local"

    def test_too_long_description_gets_auto(self):
        """Description over 200 chars with local keywords should NOT be local."""
        desc = "Extract " + "x" * 200  # > 200 chars total
        assert auto_assign_routing(desc) == "auto"


class TestCloudRouting:
    """Tasks routed to cloud: matches cloud keywords regardless of length."""

    def test_multi_step_task(self):
        desc = "Implement multi-step validation pipeline with rollback"
        assert auto_assign_routing(desc) == "cloud"

    def test_property_based_test(self):
        desc = "Write property-based test for concurrency validation"
        assert auto_assign_routing(desc) == "cloud"

    def test_property_test_shorthand(self):
        desc = "Add property test for routing heuristics"
        assert auto_assign_routing(desc) == "cloud"

    def test_pbt_keyword(self):
        desc = "Create PBT for fence stripping"
        assert auto_assign_routing(desc) == "cloud"

    def test_multiple_files_task(self):
        desc = "Refactor to split logic across multiple files"
        assert auto_assign_routing(desc) == "cloud"

    def test_sdk_task(self):
        desc = "Integrate AWS SDK for S3 uploads"
        assert auto_assign_routing(desc) == "cloud"

    def test_api_task(self):
        desc = "Design API endpoints for user management"
        assert auto_assign_routing(desc) == "cloud"

    def test_architecture_task(self):
        desc = "Redesign architecture for plugin system"
        assert auto_assign_routing(desc) == "cloud"

    def test_auth_task(self):
        desc = "Implement auth middleware with JWT"
        assert auto_assign_routing(desc) == "cloud"

    def test_security_task(self):
        desc = "Add security headers to all responses"
        assert auto_assign_routing(desc) == "cloud"

    def test_complex_logic_task(self):
        desc = "Implement complex logic for conflict resolution"
        assert auto_assign_routing(desc) == "cloud"

    def test_reasoning_task(self):
        desc = "Apply reasoning about dependency ordering"
        assert auto_assign_routing(desc) == "cloud"

    def test_case_insensitive_cloud(self):
        desc = "Write a PROPERTY-BASED TEST for the parser"
        assert auto_assign_routing(desc) == "cloud"

    def test_cloud_overrides_local_keywords(self):
        """If both local and cloud keywords present, cloud wins."""
        desc = "Extract data using SDK integration"
        assert auto_assign_routing(desc) == "cloud"


class TestAutoRouting:
    """Tasks routed to auto: neither local nor cloud patterns match."""

    def test_generic_short_description(self):
        desc = "Fix the bug in the parser"
        assert auto_assign_routing(desc) == "auto"

    def test_generic_long_description(self):
        desc = "Implement the new feature that handles user preferences and display settings"
        assert auto_assign_routing(desc) == "auto"

    def test_empty_description(self):
        desc = ""
        assert auto_assign_routing(desc) == "auto"

    def test_no_keyword_match(self):
        desc = "Update the logging format for production"
        assert auto_assign_routing(desc) == "auto"

    def test_local_keyword_but_too_long(self):
        """Local keyword present but description exceeds 200 chars → auto."""
        desc = "Extract the following fields from the response and map them to our internal representation which requires careful consideration of all edge cases and type conversions for each field including nested objects"
        assert len(desc) > 200
        assert auto_assign_routing(desc) == "auto"
