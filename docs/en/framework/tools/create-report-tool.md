## CreateReportTool

**Type:** System Tool
**Source:** [sgr_agent_core/tools/create_report_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/create_report_tool.py)

Creates a comprehensive detailed report with citations as the final step of research.

**Parameters**

- `reasoning` (str) - why ready to create report now
- `title` (str) - report title
- `user_request_language_reference` (str) - copy of original user request for language consistency
- `content` (str) - comprehensive research report with inline citations [1], [2], [3]
- `confidence` (Literal["high", "medium", "low"]) - confidence level in findings

**Behavior**

- Saves report to file in `config.execution.reports_dir`
- Filename format: `{timestamp}_{safe_title}.md`
- Includes full content with sources section
- Returns JSON with report metadata (title, content, confidence, sources_count, word_count, filepath, timestamp)

**Usage**

Final step after collecting sufficient research data.

**Configuration**

```yaml
execution:
  reports_dir: "reports"  # Directory for saving reports
```

**Important**

- Every factual claim in content MUST have inline citations [1], [2], [3]
- Citations must be integrated directly into sentences
- Content must use the same language as `user_request_language_reference`
