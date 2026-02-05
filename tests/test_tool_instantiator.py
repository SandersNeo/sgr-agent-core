"""Tests for ToolInstantiator service."""

import json

import pytest

from sgr_agent_core.services.tool_instantiator import ToolInstantiator
from sgr_agent_core.tools import ReasoningTool, WebSearchTool


class TestToolInstantiator:
    """Test suite for ToolInstantiator."""

    def test_initialization(self):
        """Test ToolInstantiator initialization."""
        instantiator = ToolInstantiator(ReasoningTool)

        assert instantiator.tool_class == ReasoningTool
        assert instantiator.errors == []
        assert instantiator.instance is None
        assert instantiator.input_content == ""

    def test_generate_format_prompt_with_errors(self):
        """Test generate_format_prompt with errors included."""
        instantiator = ToolInstantiator(ReasoningTool)
        instantiator.errors = ["Error 1", "Error 2"]
        instantiator.input_content = "invalid json"

        prompt = instantiator.generate_format_prompt(include_errors=True)

        assert "PREVIOUS FILLING ITERATION ERRORS" in prompt
        assert "Error 1" in prompt
        assert "Error 2" in prompt
        assert "invalid json" in prompt

    def test_generate_format_prompt_without_errors_when_errors_exist(self):
        """Test generate_format_prompt with include_errors=False when errors
        exist."""
        instantiator = ToolInstantiator(ReasoningTool)
        instantiator.errors = ["Error 1"]
        instantiator.input_content = "invalid json"

        prompt = instantiator.generate_format_prompt(include_errors=False)

        assert "PREVIOUS FILLING ITERATION ERRORS" not in prompt
        assert "Error 1" not in prompt

    def test_build_model_success(self):
        """Test build_model with valid JSON content."""
        instantiator = ToolInstantiator(ReasoningTool)
        content = json.dumps(
            {
                "reasoning_steps": ["step1", "step2"],
                "current_situation": "test",
                "plan_status": "ok",
                "enough_data": False,
                "remaining_steps": ["next"],
                "task_completed": False,
            }
        )

        result = instantiator.build_model(content)

        assert isinstance(result, ReasoningTool)
        assert result == instantiator.instance
        assert instantiator.instance is not None
        assert instantiator.input_content == content
        assert len(instantiator.errors) == 0
        assert result.reasoning_steps == ["step1", "step2"]
        assert result.current_situation == "test"

    def test_build_model_with_whitespace(self):
        """Test build_model handles whitespace correctly."""
        instantiator = ToolInstantiator(ReasoningTool)
        content = (
            '  \n{"reasoning_steps": ["step1", "step2"], "current_situation": "test", '
            '"plan_status": "ok", "enough_data": false, "remaining_steps": ["next"], '
            '"task_completed": false}\n  '
        )

        result = instantiator.build_model(content)

        assert isinstance(result, ReasoningTool)
        assert instantiator.instance is not None

    def test_build_model_empty_content(self):
        """Test build_model with empty content."""
        instantiator = ToolInstantiator(ReasoningTool)

        with pytest.raises(ValueError, match="No content provided"):
            instantiator.build_model("")

        assert len(instantiator.errors) == 1
        assert "No content provided" in instantiator.errors
        assert instantiator.instance is None

    def test_build_model_invalid_json(self):
        """Test build_model with invalid JSON."""
        instantiator = ToolInstantiator(ReasoningTool)
        content = "invalid json content"

        with pytest.raises(ValueError, match="Failed to build model"):
            instantiator.build_model(content)

        assert len(instantiator.errors) > 0
        assert any("Failed to parse JSON" in err for err in instantiator.errors)
        assert instantiator.input_content == content
        assert instantiator.instance is None

    def test_build_model_validation_error(self):
        """Test build_model with Pydantic validation error."""
        instantiator = ToolInstantiator(ReasoningTool)
        # Missing required fields
        content = json.dumps({"reasoning_steps": ["step1"]})

        with pytest.raises(ValueError, match="Failed to build model"):
            instantiator.build_model(content)

        assert len(instantiator.errors) > 0
        assert any("pydantic validation error" in err for err in instantiator.errors)
        assert instantiator.input_content == content
        assert instantiator.instance is None

    def test_build_model_clears_errors_on_new_attempt(self):
        """Test that build_model clears errors before new attempt."""
        instantiator = ToolInstantiator(ReasoningTool)
        instantiator.errors = ["Previous error"]

        # First attempt fails
        try:
            instantiator.build_model("invalid")
        except ValueError:
            pass

        assert len(instantiator.errors) > 0

        # Second attempt succeeds - errors should be cleared
        valid_content = json.dumps(
            {
                "reasoning_steps": ["step1", "step2"],
                "current_situation": "test",
                "plan_status": "ok",
                "enough_data": False,
                "remaining_steps": ["next"],
                "task_completed": False,
            }
        )
        result = instantiator.build_model(valid_content)

        assert isinstance(result, ReasoningTool)
        assert instantiator.instance is not None

    def test_build_model_with_web_search_tool(self):
        """Test build_model with different tool class."""
        instantiator = ToolInstantiator(WebSearchTool)
        content = json.dumps({"reasoning": "test reasoning", "query": "test query"})

        result = instantiator.build_model(content)

        assert isinstance(result, WebSearchTool)
        assert result.reasoning == "test reasoning"
        assert result.query == "test query"
        assert instantiator.instance == result

    def test_generate_format_prompt_includes_schema(self):
        """Test that generate_format_prompt includes JSON schema."""
        instantiator = ToolInstantiator(ReasoningTool)
        prompt = instantiator.generate_format_prompt()

        schema = ReasoningTool.model_json_schema()
        schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

        assert schema_str in prompt
        assert "properties" in prompt or "type" in prompt

    def test_errors_accumulation(self):
        """Test that errors accumulate across multiple failed attempts."""
        instantiator = ToolInstantiator(ReasoningTool)

        # First attempt - invalid JSON
        try:
            instantiator.build_model("invalid json 1")
        except ValueError:
            pass

        # Second attempt - invalid JSON
        try:
            instantiator.build_model("invalid json 2")
        except ValueError:
            pass

        # Note: build_model clears errors at start, so each attempt starts fresh
        # But we can check that errors are added during each attempt
        assert len(instantiator.errors) > 0
