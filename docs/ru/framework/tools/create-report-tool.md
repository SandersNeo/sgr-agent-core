## CreateReportTool

**Тип:** Системный тул  
**Исходный код:** [sgr_agent_core/tools/create_report_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/create_report_tool.py)

Создает детальный отчет с цитатами как финальный шаг исследования.

**Параметры**

- `reasoning` (str) - почему агент готов создать отчет сейчас  
- `title` (str) - заголовок отчета  
- `user_request_language_reference` (str) - копия оригинального запроса пользователя для языковой согласованности  
- `content` (str) - исчерпывающий исследовательский отчет со встроенными цитатами [1], [2], [3]  
- `confidence` (Literal["high", "medium", "low"]) - уровень уверенности в результатах  

**Поведение**

- Сохраняет отчет в файл в `config.execution.reports_dir`  
- Формат имени файла: `{timestamp}_{safe_title}.md`  
- Включает полное содержимое с разделом источников  
- Возвращает JSON с метаданными отчета (title, content, confidence, sources_count, word_count, filepath, timestamp)  

**Использование**

Финальный шаг после сбора достаточных исследовательских данных.

**Конфигурация**

```yaml
execution:
  reports_dir: "reports"  # Директория для сохранения отчетов
```

**Важно**

- Каждое фактическое утверждение в содержимом должно иметь встроенные цитаты [1], [2], [3]  
- Цитаты должны быть интегрированы непосредственно в предложения  
- Содержимое должно использовать тот же язык, что и `user_request_language_reference`  

