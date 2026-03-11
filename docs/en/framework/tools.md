# Tools Documentation

This document describes all available tools in the SGR Deep Research framework, their parameters, behavior, and configuration options.

Tools are divided into two categories:

**System** - Essential tools required for deep research functionality. Without these, the research agent cannot function properly.

**Auxiliary** - Optional tools that extend agent capabilities but are not strictly required.

| Item | Category | Description |
| --- | --- | --- |
| [ReasoningTool](tools/reasoning-tool.md) | System | Core tool for Schema-Guided Reasoning agents that determines the next reasoning step |
| [FinalAnswerTool](tools/final-answer-tool.md) | System | Final answer tool that completes the research task and updates agent state |
| [CreateReportTool](tools/create-report-tool.md) | System | Tool for generating a detailed research report with inline citations and saving it to disk |
| [ClarificationTool](tools/clarification-tool.md) | System | Tool for asking clarification questions and pausing execution until user response |
| [GeneratePlanTool](tools/generate-plan-tool.md) | System | Tool for creating an initial research plan and breaking a request into steps |
| [AdaptPlanTool](tools/adapt-plan-tool.md) | System | Tool for updating an existing research plan based on new information |
| [WebSearchTool](tools/web-search-tool.md) | Auxiliary | Web search tool powered by Tavily Search API for fresh information |
| [ExtractPageContentTool](tools/extract-page-content-tool.md) | Auxiliary | Tool for extracting full content from specific web pages using Tavily Extract API |
| [RunCommandTool](tools/run-command.md) | Auxiliary | Tool for executing shell commands in safe or unsafe mode inside a workspace boundary |

## BaseTool

All tools inherit from `BaseTool`, which provides the foundation for tool functionality.

**Source:** [sgr_agent_core/base_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/base_tool.py)

### BaseTool Class

```python
class BaseTool(BaseModel, ToolRegistryMixin):
    tool_name: ClassVar[str] = None
    description: ClassVar[str] = None

    async def __call__(
        self, context: AgentContext, config: AgentConfig, **kwargs
    ) -> str:
        raise NotImplementedError("Execute method must be implemented by subclass")
```

### Key Features

- **Automatic Registration**: Tools are automatically registered in `ToolRegistry` when defined
- **Pydantic Model**: All tools are Pydantic models, enabling validation and serialization
- **Async Execution**: Tools execute asynchronously via the `__call__` method
- **Context Access**: Tools receive `ResearchContext` and `AgentConfig` for state and configuration access

### Creating Custom Tools

To create a custom tool:

1. Inherit from `BaseTool`
2. Define tool parameters as Pydantic fields
3. Implement the `__call__` method
4. Optionally set `tool_name` and `description` class variables

**Example: Basic Custom Tool**

```python
from sgr_agent_core.base_tool import BaseTool
from pydantic import Field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sgr_agent_core.agent_definition import AgentConfig
    from sgr_agent_core.models import AgentContext


class CustomTool(BaseTool):
    """Description of what this tool does."""

    tool_name = "customtool"  # Optional, auto-generated from class name if not set

    reasoning: str = Field(description="Why this tool is needed")
    parameter: str = Field(description="Tool parameter")

    async def __call__(self, context: AgentContext, config: AgentConfig, **_) -> str:
        # Tool implementation
        result = f"Processed: {self.parameter}"
        return result
```

The tool will be automatically registered in `ToolRegistry` when the class is defined and can be used in agent configurations.

## Tool Configuration

### Configuring Tools in Agents

Tools are configured per agent in the `agents.yaml` file or agent definitions. You can reference tools in three ways:

1. **By name in snake_case** - Use snake_case format (e.g., `"web_search_tool"`) - **recommended**
2. **By name from tools section** - Define tools in a `tools:` section and reference them by name
3. **By PascalCase class name** - Use PascalCase format (e.g., `"WebSearchTool"`) - **for backward compatibility**

!!! note "Tool Naming"
    The recommended format is **snake_case** (e.g., `web_search_tool`). PascalCase format (e.g., `WebSearchTool`) is supported for backward compatibility but snake_case is preferred.

**Example: Basic Tool Configuration**

```yaml
agents:
  my_agent:
    base_class: "SGRAgent"
    tools:
      - "web_search_tool"
      - "extract_page_content_tool"
      - "create_report_tool"
      - "clarification_tool"
      - "generate_plan_tool"
      - "adapt_plan_tool"
      - "final_answer_tool"
    execution:
      max_clarifications: 3
      max_iterations: 10
    search:
      max_searches: 4
      max_results: 10
      content_limit: 1500
```

### Tool Availability Control

Agents automatically filter available tools based on execution limits:

- After `max_iterations`: Only `create_report_tool` and `final_answer_tool` are available
- After `max_clarifications`: `clarification_tool` is removed
- After `max_searches`: `web_search_tool` is removed

This ensures agents complete tasks within configured limits.

## MCP Tools

Tools can also be created from MCP (Model Context Protocol) servers. These tools inherit from `MCPBaseTool` and are automatically generated from MCP server schemas.

**Source:** [sgr_agent_core/base_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/base_tool.py) (MCPBaseTool class)

**Configuration:**

```yaml
mcp:
  mcpServers:
    deepwiki:
      url: "https://mcp.deepwiki.com/mcp"
    your_server:
      url: "https://your-mcp-server.com/mcp"
      headers:
        Authorization: "Bearer your-token"
```

**Behavior:**

- MCP tools are automatically converted to BaseTool instances
- Tool schemas are generated from MCP server input schemas
- Execution calls MCP server with tool payload
- Response is limited by `execution.mcp_context_limit`

**Configuration:**

```yaml
execution:
  mcp_context_limit: 15000  # Maximum context length from MCP server response
```

### Using Custom Tools in Configuration

Once you've created a custom tool, you can use it in your configuration via the `tools` section and by referencing tools by name from agent definitions. See the configuration examples below.
