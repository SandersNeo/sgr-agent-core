import json
from json import JSONDecodeError
from typing import TYPE_CHECKING

from pydantic import ValidationError

if TYPE_CHECKING:
    from sgr_agent_core.base_tool import BaseTool


# YESS im trying in SO inside a framework
class ToolInstantiator:
    """Structured Output like Service for formatting, parsing raw LLM context
    and building tool instances."""

    _FORMAT_PROMPT_TEMPLATE = (
        "CRITICAL: Generate a JSON OBJECT with actual data values, NOT the schema definition.\n\n"
        "HOW TO GENERATE VALUES:\n"
        "- Use the conversation context above to understand what the user wants\n"
        "- Use the tool description to understand what this tool does\n"
        "- Fill each field with appropriate values based on its schema description,the context and tool purpose\n"
        "REQUIREMENTS:\n"
        "- Output ONLY raw JSON object (no markdown, no code blocks, no explanations)\n"
        "- Fill fields with actual values matching the schema types\n"
        "- All strings must be quoted, arrays in [], objects in {}\n\n"
        "<GoodExample>\n"
        '{"field": "value", "number": 42, "list": ["a", "b"]}\n'
        "</GoodExample>\n\n"
        "<WrongExample>\n"
        '{"field": {"type": "string", "description": "..."}}\n'
        "</WrongExample>\n\n"
        "<WrongExample>\n"
        "```json\n{...}\n```\n"
        "</WrongExample>\n\n"
        "The schema below shows the STRUCTURE - provide VALUES that match it.\n\n"
    )

    def __init__(self, tool_class: type["BaseTool"]):
        """Initialize tool instantiator.

        Args:
            tool_class: Tool class to instantiate
        """
        self.tool_class = tool_class
        self.errors: list[str] = []
        self.instance: "BaseTool | None" = None
        self.input_content: str = ""

    def _clearing_context(self, content: str) -> str:
        """Extract JSON object from content by finding first { and last }.

        Args:
            content: Raw content that may contain JSON mixed with other text

        Returns:
            Extracted JSON string (from first { to last })
        """
        first_brace = content.find("{")
        if first_brace == -1:
            return content

        last_brace = content.rfind("}")
        if last_brace == -1 or last_brace < first_brace:
            return content

        return content[first_brace : last_brace + 1]

    def _format_json_error(self, error: JSONDecodeError, content: str) -> str:
        """Format JSON decode error with context around the error position.

        Args:
            error: JSONDecodeError exception
            content: Content that failed to parse

        Returns:
            Formatted error message with context
        """
        error_pos = getattr(error, "pos", None)
        if error_pos is None:
            return f"Failed to parse JSON: {error}"

        # Calculate context window (±15 characters)
        context_size = 15
        start = max(0, error_pos - context_size)
        end = min(len(content), error_pos + context_size)

        context_before = content[start:error_pos]
        context_after = content[error_pos:end]

        # Show position and context
        error_msg = (
            f"JSON parse error at position {error_pos}: {error.msg}\n"
            f"Context: ...{context_before}[Error here]{context_after}..."
        )

        return error_msg

    def generate_format_prompt(
        self,
        include_errors: bool = True,
    ) -> str:
        """Generate a prompt describing the expected format for LLM.

        Args:
            mode: Which parameters to include:
                - "all": Show all parameters (default)
                - "required": Show only required parameters
                - "unfilled": Show only parameters where value is PydanticUndefined
            include_errors: If True, include error messages for parameters with validation errors

        Returns:
            Format description string
        """
        prompt = (
            f"<ToolInfo>\n"
            f"Tool name: {self.tool_class.tool_name}\n"
            f"Tool description: {self.tool_class.description}\n"
            f"</ToolInfo>\n\n"
            f"{self._FORMAT_PROMPT_TEMPLATE}"
            f"<Schema>\n"
            f"{json.dumps( self.tool_class.model_json_schema(), indent=2, ensure_ascii=False)}\n"
            f"</Schema>\n\n"
        )

        # Show errors at the end if requested
        if include_errors and self.errors:
            prompt += "PREVIOUS FILLING ITERATION ERRORS. AVOID OR FIX IT:\n"
            prompt += "fault content: \n" + self.input_content + "\n"
            for error in self.errors:
                prompt += f"  - {error}\n"

        return prompt

    def build_model(self, content: str) -> "BaseTool":
        """Build tool model instance from parsed parameters.

        Args:
            content: Raw content from LLM to parse

        Returns:
            Tool instance

        Raises:
            ValueError: If required parameters are missing or model creation fails
        """
        self.content = ""
        self.errors.clear()
        if not content:
            self.errors.append("No content provided")
            raise ValueError("No content provided")
        self.input_content = content

        try:
            content = self._clearing_context(content)
            self.instance = self.tool_class(**json.loads(content))
            return self.instance
        except ValidationError as e:
            for err in e.errors():
                self.errors.append(
                    f"pydantic validation error - type: {err['type']} - " f"field: {err['loc']} - {err['msg']}"
                )
            raise ValueError("Failed to build model") from e
        except JSONDecodeError as e:
            error_msg = self._format_json_error(e, content)
            self.errors.append(error_msg)
            raise ValueError("Failed to build model") from e
        except ValueError as e:
            self.errors.append(f"Failed to parse JSON: {e}")
            raise ValueError("Failed to build model") from e
