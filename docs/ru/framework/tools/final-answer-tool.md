## FinalAnswerTool

**Тип:** Системный тул  
**Исходный код:** [sgr_agent_core/tools/final_answer_tool.py](https://github.com/vamplabAI/sgr-agent-core/blob/main/sgr_agent_core/tools/final_answer_tool.py)

Финализирует исследовательскую задачу и завершает выполнение агента.

**Параметры**

- `reasoning` (str) - почему задача завершена и как был верифицирован ответ  
- `completed_steps` (list[str], 1-5 элементов) - сводка выполненных шагов, включая верификацию  
- `answer` (str) - исчерпывающий финальный ответ с точными фактическими данными  
- `status` (Literal["completed", "failed"]) - статус завершения задачи  

**Поведение**

- Устанавливает `context.state` в указанный статус  
- Сохраняет `answer` в `context.execution_result`  
- Возвращает JSON-представление финального ответа  

**Использование**

Вызывается после завершения исследовательской задачи для финализации выполнения.

**Конфигурация**

Специальная конфигурация не требуется.

**Пример**

```yaml
execution:
  max_iterations: 10  # После этого лимита доступны только final_answer_tool и create_report_tool
```

