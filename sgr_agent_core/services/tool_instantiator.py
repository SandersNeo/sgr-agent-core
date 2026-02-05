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
        "<Example>\n"
        '{"field": "value", "number": 42, "list": ["a", "b"]}\n'
        "</Example>\n\n"
        "<WrongExample>\n"
        '{"field": {"type": "string", "description": "..."}}\n'
        "OR\n"
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
            content = content.strip().replace("\n", "")
            self.instance = self.tool_class(**json.loads(content))
            return self.instance
        except ValidationError as e:
            for err in e.errors():
                self.errors.append(
                    f"pydantic validation error - type: {err['type']} - " f"field: {err['loc']} - {err['msg']}"
                )
            raise ValueError("Failed to build model") from e
        except (JSONDecodeError, ValueError) as e:
            self.errors.append(f"Failed to parse JSON: {e}")
            raise ValueError("Failed to build model") from e
