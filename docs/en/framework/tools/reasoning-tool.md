## ReasoningTool

**Type:** System Tool  
**Source:** [sgr_agent_core/tools/reasoning_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/reasoning_tool.py)

Core tool for Schema-Guided Reasoning agents. Determines the next reasoning step with adaptive planning capabilities.

**Parameters**

- `reasoning_steps` (list[str], 2-3 items) - step-by-step reasoning process  
- `current_situation` (str, max 300 chars) - current research situation assessment  
- `plan_status` (str, max 150 chars) - status of current plan  
- `enough_data` (bool, default=False) - whether sufficient data is collected  
- `remaining_steps` (list[str], 1-3 items) - remaining action steps  
- `task_completed` (bool) - whether the research task is finished  

**Behavior**

Returns JSON representation of reasoning state. Used by SGR agents to structure their decision-making process.

**Usage**

- Required tool for SGR-based agents  
- Must be used before any other tool execution in the reasoning phase  

**Configuration**

No specific configuration required. Tool behavior is controlled by agent prompts and LLM settings.

