# Task 5. Набор интеграционных и end-to-end тестов

Ниже приведён набор тестов для проверки реализации Saga-процесса обработки платежа в OrchestrPay.  
В таблице покрыты:
- основной успешный сценарий;
- отказные и компенсационные ветки;
- ручная проверка и cut-off;
- проблемы интеграции, идемпотентность и восстановление после сбоев.

| Название | Тип | Компоненты | Предусловия |
| --- | --- | --- | --- |
| `Create payment and debit funds` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Запущены orchestrator и `Payment Service`, создан тестовый заказ, у клиента достаточно средств |
| `Approve fraud check leads to transfer` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service`, `Payment Service` | Для тестовой транзакции antifraud возвращает `approve` |
| `Reject fraud check triggers refund` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service`, `Payment Service` | Для тестовой транзакции antifraud возвращает `reject`, деньги уже списаны |
| `Manual review puts process into waiting state` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service`, `Tasklist/Camunda` | Для тестовой транзакции antifraud возвращает `manual_review` |
| `Manual review approve completes payment` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service`, `Payment Service`, `Tasklist/Camunda` | Процесс уже находится в состоянии ожидания ручной проверки, оператор завершает user task с решением `approve` |
| `Manual review reject triggers compensation` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service`, `Payment Service`, `Tasklist/Camunda` | Процесс уже находится в состоянии ожидания ручной проверки, оператор завершает user task с решением `reject` |
| `Cut-off auto approve after timeout` | Интеграционный | `Saga Orchestrator`, `Camunda timer`, `Payment Service` | Процесс находится в `manual_review`, решение оператора не поступает до истечения cut-off-time |
| `Refund path marks payment rejected` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Запущена компенсационная ветка после `reject` или ошибки до pivot |
| `Reject path sends customer notification and security alert in parallel` | Интеграционный | `Saga Orchestrator`, `Notification Service`, `Security Service` | Платёж переведён в ветку `MARK_PAYMENT_REJECTED` |
| `Transfer to merchant is executed only after positive decision` | Интеграционный | `Saga Orchestrator`, `Payment Service`, `FraudCheck Service` | Для набора тестов доступны сценарии `approve`, `reject`, `manual_review` |
| `No refund after pivot` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Платёж уже прошёл шаг `TRANSFER_TO_MERCHANT`, искусственно моделируется поздняя ошибка после pivot |
| `Idempotent retry for create payment` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Для одного `orderId` повторно отправляется команда создания платежа с тем же idempotency key |
| `Idempotent retry for refund` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Команда возврата по одной и той же транзакции повторяется после сетевой ошибки |
| `Fraud service temporary failure is retried` | Интеграционный | `Saga Orchestrator`, `FraudCheck Service` | `FraudCheck Service` на первой попытке отвечает ошибкой/timeout, на следующей — корректным результатом |
| `Notification failure does not break financial consistency` | Интеграционный | `Saga Orchestrator`, `Notification Service`, `Payment Service` | Платёж завершён, `Notification Service` временно недоступен |
| `Orchestrator restores process state after restart` | Интеграционный | `Saga Orchestrator`, `Camunda/State store` | В момент ожидания `manual_review` выполняется рестарт оркестратора |
| `Payment service failure before pivot leads to compensation` | Интеграционный | `Saga Orchestrator`, `Payment Service` | Моделируется ошибка после списания средств, но до `TRANSFER_TO_MERCHANT` |
| `Security alert is emitted only for suspicious/rejected flow` | Интеграционный | `Saga Orchestrator`, `Security Service` | Доступны сценарии `approve` и `reject` для сравнения результатов |
| `Happy path e2e payment completed successfully` | End-to-end | `Camunda`, `Saga Orchestrator`, `Payment Service`, `FraudCheck Service`, `Notification Service` | Поднят полный стенд через `docker-compose`, доступен тестовый клиент и заказ, antifraud отвечает `approve` |
| `Rejected payment e2e is refunded automatically` | End-to-end | `Camunda`, `Saga Orchestrator`, `Payment Service`, `FraudCheck Service`, `Notification Service`, `Security Service` | Поднят полный стенд, antifraud отвечает `reject`, у клиента достаточно средств для исходного списания |
| `Manual review e2e waits in Tasklist` | End-to-end | `Camunda`, `Tasklist`, `Saga Orchestrator`, `FraudCheck Service` | Поднят полный стенд, antifraud отвечает `manual_review`, пользовательская задача отображается в `Tasklist` |
| `Manual review approve e2e completes after user task` | End-to-end | `Camunda`, `Tasklist`, `Saga Orchestrator`, `Payment Service`, `Notification Service` | Поднят полный стенд, создан `manual_review` инстанс, оператор может завершить user task с `approve` |
| `Manual review reject e2e refunds after user task` | End-to-end | `Camunda`, `Tasklist`, `Saga Orchestrator`, `Payment Service`, `Security Service`, `Notification Service` | Поднят полный стенд, создан `manual_review` инстанс, оператор может завершить user task с `reject` |
| `Cut-off e2e completes without operator action` | End-to-end | `Camunda`, `Saga Orchestrator`, `Payment Service`, `Tasklist` | Поднят полный стенд, создан `manual_review` инстанс, оператор не завершает задачу до истечения таймера |
| `Three concurrent manual reviews are visible in Camunda UI` | End-to-end | `Camunda Operate`, `Tasklist`, `Saga Orchestrator`, `Payment Service` | Поднят полный стенд, одновременно запущены 3 инстанса со сценарием `manual_review` |
| `E2E logs contain handlers for approve reject and timeout` | End-to-end | `payment-worker`, `Camunda`, `Saga Orchestrator` | Поднят полный стенд, последовательно запущены сценарии `approve`, `reject`, `manual_review timeout` |

## Примечания к покрытию

1. Интеграционные тесты должны выполняться на изолированном окружении с моками или тестовыми double для внешних сервисов.
2. End-to-end тесты должны запускаться на полном стенде из `docker-compose`, чтобы проверять не только бизнес-результат, но и состояние в `Operate` / `Tasklist`.
3. Для финансовых шагов обязательна проверка идемпотентности и отсутствия двойного списания / двойного возврата.
4. Для сценариев `manual_review` важно проверять не только итоговый статус, но и наличие user task и корректную работу таймера.
