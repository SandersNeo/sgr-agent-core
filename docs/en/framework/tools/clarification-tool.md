## ClarificationTool

**Type:** System Tool
**Source:** [sgr_agent_core/tools/clarification_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/clarification_tool.py)

Asks clarifying questions when facing an ambiguous request.

**Parameters**

- `reasoning` (str, max 200 chars) - why clarification is needed (1-2 sentences MAX)
- `unclear_terms` (list[str], 1-3 items) - list of unclear terms (brief, 1-3 words each)
- `assumptions` (list[str], 2-3 items) - possible interpretations (short, 1 sentence each)
- `questions` (list[str], 1-3 items) - specific clarifying questions (short and direct)

**Behavior**

- Returns questions as newline-separated string
- Pauses agent execution until clarification is received
- Sets agent state to `WAITING_FOR_CLARIFICATION`
- Increments `context.clarifications_used`

**Usage**

Use when user request is ambiguous or requires additional information.

**Configuration**

```yaml
execution:
  max_clarifications: 3  # Maximum number of user clarification requests
```

After reaching `max_clarifications`, the tool is automatically removed from available tools.
