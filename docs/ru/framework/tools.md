# Документация по тулам

Этот документ описывает общие принципы работы тулов во фреймворке SGR Deep Research, их категории, базовый класс `BaseTool`, конфигурацию и интеграцию с MCP.

Тулы делятся на две категории:

**Системные тулы** — основные тулы, необходимые для функционирования глубокого исследования. Без них исследовательский агент не сможет работать корректно.

**Вспомогательные тулы** — опциональные тулы, расширяющие возможности агента, но не являющиеся строго обязательными.

| Элемент | Категория | Описание |
| --- | --- | --- |
| [ReasoningTool](tools/reasoning-tool.md) | Системный | Базовый тул рассуждений для SGR-агентов, определяющий следующий шаг |
| [FinalAnswerTool](tools/final-answer-tool.md) | Системный | Финальный тул, завершающий задачу и обновляющий состояние агента |
| [CreateReportTool](tools/create-report-tool.md) | Системный | Тул для генерации детального исследовательского отчета с цитатами и сохранения его на диск |
| [ClarificationTool](tools/clarification-tool.md) | Системный | Тул для запроса уточнений у пользователя и приостановки выполнения до ответа |
| [GeneratePlanTool](tools/generate-plan-tool.md) | Системный | Тул для создания первоначального исследовательского плана и разбиения запроса на шаги |
| [AdaptPlanTool](tools/adapt-plan-tool.md) | Системный | Тул для обновления существующего плана на основе новой информации |
| [WebSearchTool](tools/web-search-tool.md) | Вспомогательный | Веб-поиск с использованием Tavily Search API для получения свежей информации |
| [ExtractPageContentTool](tools/extract-page-content-tool.md) | Вспомогательный | Тул для извлечения полного содержимого с конкретных веб-страниц через Tavily Extract API |
| [RunCommandTool](tools/run-command.md) | Вспомогательный | Тул для выполнения shell-команд в безопасном или небезопасном режиме в пределах рабочей директории |

## BaseTool

Все тулы наследуются от `BaseTool`, который обеспечивает основу функциональности тулов.

**Исходный код:** [sgr_agent_core/base_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/base_tool.py)

### Класс BaseTool

```python
class BaseTool(BaseModel, ToolRegistryMixin):
    tool_name: ClassVar[str] = None
    description: ClassVar[str] = None

    async def __call__(
        self, context: AgentContext, config: AgentConfig, **kwargs
    ) -> str:
        raise NotImplementedError("Execute method must be implemented by subclass")
```

### Ключевые особенности

- **Автоматическая регистрация**: Тулы автоматически регистрируются в `ToolRegistry` при определении
- **Pydantic-модель**: Все тулы являются Pydantic-моделями, что обеспечивает валидацию и сериализацию
- **Асинхронное выполнение**: Тулы выполняются асинхронно через метод `__call__`
- **Доступ к контексту**: Тулы получают `ResearchContext` и `AgentConfig` для доступа к состоянию и конфигурации

### Создание пользовательских тулов

Для создания пользовательского тула:

1. Наследуйтесь от `BaseTool`
2. Определите параметры тула как Pydantic-поля
3. Реализуйте метод `__call__`
4. Опционально установите переменные класса `tool_name` и `description`

**Пример: Базовый пользовательский тул**

```python
from sgr_agent_core.base_tool import BaseTool
from pydantic import Field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sgr_agent_core.agent_definition import AgentConfig
    from sgr_agent_core.models import AgentContext


class CustomTool(BaseTool):
    """Описание того, что делает этот инструмент."""

    tool_name = "customtool"  # Опционально, автогенерируется из имени класса если не задано

    reasoning: str = Field(description="Почему нужен этот тул")
    parameter: str = Field(description="Параметр тула")

    async def __call__(self, context: AgentContext, config: AgentConfig, **_) -> str:
        # Реализация тула
        result = f"Обработано: {self.parameter}"
        return result
```

Тул будет автоматически зарегистрирован в `ToolRegistry` при определении класса и может использоваться в конфигурациях агентов.

### Использование пользовательских тулов в конфигурации

После создания пользовательского тула вы можете использовать его в конфигурации двумя способами:

**Способ 1: Прямая ссылка (если тул импортирован и зарегистрирован)**

Если ваш пользовательский тул импортирован до создания агента, он будет автоматически зарегистрирован и на него можно ссылаться по имени:

```yaml
agents:
  my_agent:
    base_class: "SGRToolCallingAgent"
    tools:
      - "custom_tool"  # Прямая ссылка на зарегистрированный тул
      - "web_search_tool"
```

**Способ 2: Определение в секции tools с base_class**

Вы можете определить пользовательские тулы в секции `tools:` и указать `base_class`:

```yaml
tools:
  # Пользовательский тул с явным base_class
  custom_tool:
    base_class: "tools.CustomTool"  # Относительный путь импорта
    # Или использовать полный путь:
    # base_class: "my_package.tools.CustomTool"

agents:
  my_agent:
    base_class: "SGRToolCallingAgent"
    tools:
      - "custom_tool"  # Ссылка по имени из секции tools
      - "web_search_tool"
```

**Важные замечания:**

- Пользовательские тулы должны быть импортированы до создания агента для автоматической регистрации
- При использовании `base_class` в определениях тулов можно использовать:
  - Относительные пути импорта (например, `"tools.CustomTool"`) — разрешаются относительно расположения файла конфигурации
  - Полные пути импорта (например, `"my_package.tools.CustomTool"`) — разрешаются из `sys.path` Python
  - Имена классов (например, `"CustomTool"`) — разрешаются из `ToolRegistry`
- Тулы, определённые в секции `tools:`, имеют приоритет над тулами в `ToolRegistry`

## Конфигурация тулов

### Настройка тулов в агентах

Тулы настраиваются для каждого агента в файле `agents.yaml` или определениях агентов. Вы можете ссылаться на тулы тремя способами:

1. **По имени в snake_case** — используйте формат snake_case (например, `"web_search_tool"`) — **рекомендуется**
2. **По имени из секции tools** — определите тулы в секции `tools:` и ссылайтесь на них по имени
3. **По имени класса в PascalCase** — используйте формат PascalCase (например, `"WebSearchTool"`) — **для обратной совместимости**

!!! note "Именование тулов"
    Рекомендуемый формат — **snake_case** (например, `web_search_tool`). Формат PascalCase (например, `WebSearchTool`) поддерживается для обратной совместимости, но предпочтительнее использовать snake_case.

**Пример: Базовая конфигурация тулов**

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

### Определение тулов в конфигурации

Вы можете определить тулы в отдельной секции `tools:` в `config.yaml` или `agents.yaml`. Это позволяет:

- Определять пользовательские тулы с конкретными конфигурациями
- Ссылаться на тулы по имени в определениях агентов
- Переопределять классы тулов по умолчанию, используя `base_class`

**Формат определения тула:**

```yaml
tools:
  # Простое определение тула (использует base_class по умолчанию из ToolRegistry)
  reasoning_tool:
    # base_class по умолчанию: sgr_agent_core.tools.ReasoningTool

  # Пользовательский тул с явным base_class
  custom_tool:
    base_class: "tools.CustomTool"  # Относительный путь импорта или полный путь
    # Здесь можно добавить дополнительные параметры, специфичные для тула
```

**Использование определённых тулов в агентах:**

```yaml
tools:
  reasoning_tool:
    # Использует по умолчанию: sgr_agent_core.tools.ReasoningTool
  custom_file_tool:
    base_class: "tools.CustomFileTool"  # Пользовательский тул из локального модуля

agents:
  my_agent:
    base_class: "SGRToolCallingAgent"
    tools:
      - "reasoning_tool"  # Из секции tools
      - "custom_file_tool"  # Из секции tools
      - "web_search_tool"  # Из ToolRegistry
      - "final_answer_tool"  # Из ToolRegistry
```

!!! note "Порядок разрешения тулов"
    При разрешении тулов система проверяет в следующем порядке:
    1. Тулы, определённые в секции `tools:` (по имени)
    2. Тулы, зарегистрированные в `ToolRegistry` (по имени в snake_case — рекомендуется, или по имени класса в PascalCase для обратной совместимости)
    3. Автоконвертация из snake_case в PascalCase (например, `web_search_tool` → `WebSearchTool`) для обратной совместимости

### Управление доступностью тулов

Агенты автоматически фильтруют доступные тулы на основе лимитов выполнения:

- После `max_iterations`: Доступны только `create_report_tool` и `final_answer_tool`
- После `max_clarifications`: `clarification_tool` удаляется
- После `max_searches`: `web_search_tool` удаляется

Это гарантирует, что агенты завершают задачи в рамках настроенных лимитов.

## MCP-тулы

Тулы также могут создаваться из MCP (Model Context Protocol) серверов. Эти тулы наследуются от `MCPBaseTool` и автоматически генерируются из схем MCP-сервера.

**Исходный код:** [sgr_agent_core/base_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/base_tool.py) (класс MCPBaseTool)

**Конфигурация:**

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

**Поведение:**

- MCP-тулы автоматически преобразуются в экземпляры BaseTool
- Схемы тулов генерируются из входных схем MCP-сервера
- Выполнение вызывает MCP-сервер с полезной нагрузкой тула
- Ответ ограничен `execution.mcp_context_limit`

**Конфигурация:**

```yaml
execution:
  mcp_context_limit: 15000  # Максимальная длина контекста из ответа MCP-сервера
```
