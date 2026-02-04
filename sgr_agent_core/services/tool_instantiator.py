import re
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Type, get_args, get_origin

from pydantic import ValidationError
from pydantic_core import PydanticUndefined

if TYPE_CHECKING:
    from sgr_agent_core.base_tool import BaseTool


@dataclass
class ParameterDescription:
    """Description of a tool parameter."""

    name: str
    description: str
    required: bool
    default: Any = PydanticUndefined
    min_value: int | float | None = None
    max_value: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    field_type: Type = str
    _value: Any = PydanticUndefined

    @property
    def value(self) -> Any:
        """Get parameter value, returning default if value is
        PydanticUndefined."""
        return self._value if self._value is not PydanticUndefined else self.default

    @value.setter
    def value(self, val: Any) -> None:
        """Set parameter value."""
        self._value = val

    def validate(self) -> list[str]:
        errors = []
        if self.value is PydanticUndefined and self.required:
            errors.append(f"{self.name}: Required parameter is missing")
            return errors

        value = self.value
        if isinstance(value, (int, float)):
            if self.min_value is not None and value < self.min_value:
                errors.append(f"{self.name}: Value {value} is less than minimum {self.min_value}")
            if self.max_value is not None and value > self.max_value:
                errors.append(f"{self.name}: Value {value} is greater than maximum {self.max_value}")

        if isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                errors.append(f"{self.name}: String length {len(value)} is less than minimum {self.min_length}")
            if self.max_length is not None and len(value) > self.max_length:
                errors.append(f"{self.name}: String length {len(value)} is greater than maximum {self.max_length}")
        elif isinstance(value, list):
            if self.min_length is not None and len(value) < self.min_length:
                errors.append(f"{self.name}: List entries count {len(value)} is less than minimum {self.min_length}")
            if self.max_length is not None and len(value) > self.max_length:
                errors.append(f"{self.name}: List entries count {len(value)} is greater than maximum {self.max_length}")
        return errors


# YESS im trying in SO inside a framework
class ToolInstantiator:
    """Sctuctured Output like Service for parsing LLM context and building tool
    instances."""

    _FORMAT_PROMPT_TEMPLATE = (
        "CRITICAL: You MUST generate parameters in the EXACT format specified below. "
        "Each parameter must be on a separate line. This format is MANDATORY for correct parsing.\n\n"
        "Expected format (one parameter per line):\n"
        "field_name: field_value\n\n"
        "For list parameters, use numbered list format:\n"
        "field_name:\n"
        "1. value1\n"
        "2. value2\n"
        "3. value3\n\n"
        "<Examples>\n"
        "<Example>\n"
        "query: Python programming tutorial\n"
        "max_results: 5\n"
        "reasoning_steps:\n"
        "1. First step\n"
        "2. Second step\n"
        "3. Third step\n"
        "</Example>\n\n"
        "<Example>\n"
        "current_situation: Researching Python frameworks\n"
        "plan_status: Analyzing available options\n"
        "remaining_steps:\n"
        "1. Compare Django and Flask\n"
        "2. Evaluate performance\n"
        "task_completed: false\n"
        "</Example>\n"
        "</Examples>\n\n"
    )

    def __init__(self, tool_class: Type["BaseTool"]):
        """Initialize tool instantiator.

        Args:
            tool_class: Tool class to instantiate
        """
        self.tool_class = tool_class

        # Patterns for parsing context
        # Pattern 1: Single value fields: "field_name: value"
        self._single_value_pattern = re.compile(r"^(\w+)\s*:\s*([^\n]+)$", re.MULTILINE)
        # Pattern 2: List fields: "field_name:\n1. value1\n2. value2"
        self._list_field_pattern = re.compile(r"^(\w+)\s*:\s*$", re.MULTILINE)
        self._list_item_pattern = re.compile(r"^\s*(\d+)\.\s+(.+)$", re.MULTILINE)

        # Extract parameter descriptions from Pydantic model
        self.parameters: dict[str, ParameterDescription] = {}
        self.errors: list[str] = []
        self._extract_parameters()

    @property
    def all_parameters(self) -> list[ParameterDescription]:
        """Get all parameter descriptions."""
        return list(self.parameters.values())

    @property
    def required_parameters(self) -> list[ParameterDescription]:
        """Get all required parameter descriptions."""
        return [param for param in self.parameters.values() if param.required]

    @property
    def optional_parameters(self) -> list[ParameterDescription]:
        """Get all optional parameter descriptions."""
        return [param for param in self.parameters.values() if not param.required]

    def _extract_parameters(self) -> None:
        """Extract parameter descriptions from Pydantic model."""

        model_fields = self.tool_class.model_fields
        for field_name, field_info in model_fields.items():
            min_value = None
            max_value = None
            min_length = None
            max_length = None
            for constraint in field_info.metadata:
                constraint_type = type(constraint).__name__
                if constraint_type == "MinLen":
                    min_length = constraint.min_length
                elif constraint_type == "MaxLen":
                    max_length = constraint.max_length
                elif constraint_type == "Le":
                    max_value = constraint.le
                elif constraint_type == "Lt":
                    max_value = constraint.lt
                elif constraint_type == "Ge":
                    min_value = constraint.ge
                elif constraint_type == "Gt":
                    min_value = constraint.gt

            param = ParameterDescription(
                name=field_name,
                description=field_info.description,
                required=field_info.is_required(),
                default=field_info.default,
                min_value=min_value,
                max_value=max_value,
                min_length=min_length,
                max_length=max_length,
                field_type=field_info.annotation,
            )

            self.parameters[field_name] = param

    def generate_format_prompt(
        self,
        mode: Literal["all", "required", "unfilled"] = "all",
        include_errors: bool = False,
    ) -> str:
        """Generate prompt describing the expected format for LLM.

        Args:
            mode: Which parameters to include:
                - "all": Show all parameters (default)
                - "required": Show only required parameters
                - "unfilled": Show only parameters where value is PydanticUndefined
            include_errors: If True, include error messages for parameters with validation errors

        Returns:
            Format description string
        """
        # Filter parameters based on mode
        if mode == "required":
            params_to_show = self.required_parameters
        elif mode == "unfilled":
            all_params = self.required_parameters + self.optional_parameters
            params_to_show = [p for p in all_params if p._value is PydanticUndefined]
        else:  # mode == "all"
            params_to_show = self.required_parameters + self.optional_parameters

        prompt = (
            f"{self._FORMAT_PROMPT_TEMPLATE}"
            f"Tool: {self.tool_class.tool_name}\n"
            f"Description: {self.tool_class.description}\n\n"
        )

        for param in params_to_show:
            prompt += f"- {param.name}: {param.description}"
            if param.required:
                prompt += " (required)\n"
            else:
                prompt += " (optional)\n"
            if param.default is not PydanticUndefined:
                prompt += f"  Default: {param.default}\n"
            if param.min_value is not None:
                prompt += f"  Minimum: {param.min_value}\n"
            if param.max_value is not None:
                prompt += f"  Maximum: {param.max_value}\n"
            if param.min_length is not None:
                prompt += f"  Min length: {param.min_length}\n"
            if param.max_length is not None:
                prompt += f"  Max length: {param.max_length}\n"
            origin = get_origin(param.field_type)
            if origin is types.UnionType:
                union_types = get_args(param.field_type)
                type_names = [getattr(t, "__name__", str(t)) for t in union_types]
                prompt += f"  Type: {' | '.join(type_names)}\n"
            elif origin is list and (args := get_args(param.field_type)):
                prompt += f"  Type: list[{args[0].__name__}] (use numbered list format)\n"
            else:
                prompt += f"  Type: {param.field_type.__name__}\n"

        # Show errors at the end if requested
        if include_errors and self.errors:
            prompt += "\nPREVIOUS FILLING ITERATION ERRORS. AVOID OR FIX IT:\n"
            for error in self.errors:
                prompt += f"  - {error}\n"

        return prompt

    def parse_context(self, context: str) -> None:
        """Parse context string and update parameter values.

        Args:
            context: LLM context string to parse

        Raises:
            ValueError: If parsing fails or required parameters are missing
        """
        self.errors.clear()

        parsed_params = self._extract_fields(context)
        recognized_params = self._recognize_params(parsed_params)

        for param_name, param_value in recognized_params.items():
            param_desc = self.parameters[param_name]
            param_desc.value = self._convert_type(param_value, param_desc.field_type)
            self.errors.extend(param_desc.validate())

        missing_required = [param.name for param in self.required_parameters if param.value is PydanticUndefined]
        if missing_required:
            self.errors.append(f"Missing required parameters for {self.tool_class.tool_name}: {missing_required}. ")
        if self.errors:
            raise ValueError(f"Failed to parse context: {self.errors}")

    def _extract_fields(self, context: str) -> dict[str, Any]:
        """Extract all fields from a context string.

        Args:
            context: Context string to parse

        Returns:
            Dictionary with lowercase field names as keys
        """
        parsed_params: dict[str, Any] = {}
        lines = context.split("\n")

        # Find all single-value fields: "field_name: value"
        for match in self._single_value_pattern.finditer(context):
            field_name = match.group(1).lower().strip()
            value = match.group(2).strip().strip("\"'")
            parsed_params[field_name] = value

        # Find all list fields: "field_name:\n1. value1\n2. value2"
        for match in self._list_field_pattern.finditer(context):
            field_name = match.group(1).lower().strip()
            match_end_line = context[: match.end()].count("\n")

            # Find list items after this field declaration
            list_values = []
            for i in range(match_end_line + 1, len(lines)):
                line = lines[i]
                item_match = self._list_item_pattern.match(line)
                if item_match:
                    value = item_match.group(2).strip().strip("\"'")
                    list_values.append(value)
                elif line.strip():
                    # Not a list item and not empty, stop parsing
                    break

            if list_values:
                parsed_params[field_name] = list_values

        return parsed_params

    def _recognize_params(self, parsed_params: dict[str, Any]) -> dict[str, Any]:
        """Recognize parameter names and report unknown ones.

        Args:
            parsed_params: Dictionary with field names

        Returns:
            Dictionary with actual parameter names as keys
        """
        normalized_params: dict[str, Any] = {}
        for parsed_key, parsed_value in parsed_params.items():
            if parsed_key in self.parameters:
                normalized_params[parsed_key] = parsed_value
            else:
                self.errors.append(f"Unknown parameter: '{parsed_key}' check spelling")

        return normalized_params

    # def _recognize_params(self, parsed_params: dict[str, Any]) -> dict[str, Any]:
    #     """Recognize parameter names using case-insensitive matching and report unknown ones.
    #
    #     Args:
    #         parsed_params: Dictionary with lowercase field names
    #
    #     Returns:
    #         Dictionary with actual parameter names as keys
    #     """
    #     normalized_params: dict[str, Any] = {}
    #
    #     # Create lowercase index for fast lookup of parameter names
    #     param_lower_index: dict[str, str] = {
    #         param_name.lower(): param_name for param_name in self.parameters.keys()
    #     }
    #
    #     # Iterate over parsed params and match with known parameters
    #     for parsed_key, parsed_value in parsed_params.items():
    #         parsed_lower = parsed_key.lower()
    #         if parsed_lower in param_lower_index:
    #             # Parameter recognized, use actual parameter name
    #             param_name = param_lower_index[parsed_lower]
    #             normalized_params[param_name] = parsed_value
    #         else:
    #             # Unknown parameter, report as error
    #             self.errors.append(f"Unknown parameter: '{parsed_key}'")
    #
    #     return normalized_params

    def _convert_and_validate_types(self, normalized_params: dict[str, Any]):
        """Convert parameter values to appropriate types and collect errors.

        Args:
            normalized_params: Dictionary with normalized parameter names

        Returns:
            Dictionary with converted typed values
        """

    def build_model(self) -> "BaseTool":
        """Build tool model instance from parsed parameters.

        Returns:
            Tool instance

        Raises:
            ValueError: If required parameters are missing or model creation fails
        """
        parsed_params = {
            name: param.value for name, param in self.parameters.items() if param.value is not PydanticUndefined
        }

        # Try to create model instance
        try:
            instance = self.tool_class(**parsed_params)
            return instance
        except ValidationError as e:
            error_msg = f"Failed to validate model: {e}"
            self.errors.append(error_msg)
            raise ValueError(error_msg) from e

    def _convert_type(self, value: Any, target_type: Type | Any) -> Any:
        origin = get_origin(target_type)
        if origin is list:
            args = get_args(target_type)
            item_type = args[0] if args else str

            if not isinstance(value, list):
                self.errors.append(
                    f"Parameter expects a list (e.g., '1. item1\n2. item2'), "
                    f"but received a non-list type: {type(value).__name__} for value '{value}'"
                )
                return PydanticUndefined

            converted_items = []
            for item in value:
                item_value = self._convert_type(item, item_type)
                converted_items.append(item_value)
            return converted_items

        if origin is types.UnionType:
            union_types = get_args(target_type)
            for union_type in union_types:
                converted_value = self._convert_type(value, union_type)
                return converted_value
            type_names = [getattr(t, "__name__", str(t)) for t in union_types]
            self.errors.append(f"Cannot convert '{value}' to any of: {' | '.join(type_names)}")
            return PydanticUndefined

        if target_type is bool:
            if value in ("true", "True", "TRUE" "1", True):
                return True
            elif value in ("false", "False", "FALSE", "0", False):
                return False
            else:
                self.errors.append(f"Cannot convert '{value}' to boolean. Use 'true'/'false', 'yes'/'no', or '1'/'0'")
                return PydanticUndefined

        if target_type is int:
            try:
                return int(value)
            except ValueError:
                self.errors.append(f"Cannot convert '{value}' to integer")
                return PydanticUndefined

        if target_type is float:
            try:
                return float(value)
            except ValueError:
                self.errors.append(f"Cannot convert '{value}' to number")
                return PydanticUndefined

        return str(value)


def simplify_schema(schema: dict, defs: dict = None) -> Any:
    """Recursively build a simplified dictionary describing the schema."""
    # On first call, store the top-level "$defs" so we can resolve refs.
    if defs is None:
        defs = schema.get("$defs", {})

    # If this schema references something by "$ref", resolve that first.
    if "$ref" in schema:
        ref_path = schema["$ref"]
        # Typical ref is like "#/$defs/SomeModel"
        ref_name = ref_path.split("/")[-1]
        ref_schema = defs.get(ref_name, {})
        return simplify_schema(ref_schema, defs)

    schema_type = schema.get("type")

    if schema_type == "object":
        # For an object, recursively simplify each property
        properties = schema.get("properties", {})
        result = {}
        for prop_name, prop_schema in properties.items():
            result[prop_name] = simplify_schema(prop_schema, defs)
        return result

    elif schema_type == "array":
        # For an array, look at its "items" and recurse
        items_schema = schema.get("items", {})
        return [simplify_schema(items_schema, defs)]

    else:
        # Assume a primitive type
        field_type = schema.get("type", "string")  # default to string if missing
        field_desc = schema.get("description", "")
        return f"({field_type}) {field_desc}"
