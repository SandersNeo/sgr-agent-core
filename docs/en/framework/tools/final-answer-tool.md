## FinalAnswerTool

**Type:** System Tool
**Source:** [sgr_agent_core/tools/final_answer_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/final_answer_tool.py)

Finalizes research task and completes agent execution.

**Parameters**

- `reasoning` (str) - why task is complete and how answer was verified
- `completed_steps` (list[str], 1-5 items) - summary of completed steps including verification
- `answer` (str) - comprehensive final answer with exact factual details
- `status` (Literal["completed", "failed"]) - task completion status

**Behavior**

- Sets `context.state` to the specified status
- Stores `answer` in `context.execution_result`
- Returns JSON representation of the final answer

**Usage**

Call after completing a research task to finalize execution.

**Configuration**

No specific configuration required.

**Example**

```yaml
execution:
  max_iterations: 10  # After this limit, only final_answer_tool and create_report_tool are available
```
