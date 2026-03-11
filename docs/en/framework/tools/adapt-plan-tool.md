## AdaptPlanTool

**Type:** System Tool  
**Source:** [sgr_agent_core/tools/adapt_plan_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/adapt_plan_tool.py)

Adapts a research plan based on new findings.

**Parameters**

- `reasoning` (str) - why plan needs adaptation based on new data  
- `original_goal` (str) - original research goal  
- `new_goal` (str) - updated research goal  
- `plan_changes` (list[str], 1-3 items) - specific changes made to plan  
- `next_steps` (list[str], 2-4 items) - updated remaining steps  

**Behavior**

- Returns JSON representation of adapted plan (excluding reasoning field)  
- Allows dynamic plan adjustment during research  

**Usage**

Use when initial plan needs modification based on discovered information.

**Configuration**

No specific configuration required.

