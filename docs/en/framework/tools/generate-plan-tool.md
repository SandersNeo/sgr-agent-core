## GeneratePlanTool

**Type:** System Tool  
**Source:** [sgr_agent_core/tools/generate_plan_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/generate_plan_tool.py)

Generates a research plan to split complex requests into manageable steps.

**Parameters**

- `reasoning` (str) - justification for research approach  
- `research_goal` (str) - primary research objective  
- `planned_steps` (list[str], 3-4 items) - list of planned steps  
- `search_strategies` (list[str], 2-3 items) - information search strategies  

**Behavior**

- Returns JSON representation of the plan (excluding reasoning field)  
- Used to structure complex research tasks  

**Usage**

Use at the beginning of research to break down complex requests.

**Configuration**

No specific configuration required.

