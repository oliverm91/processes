# Plan de Arquitectura — Reorganización de dominio y comunicación

> Documento de **planificación**. No introduce cambios de código por sí mismo.
> Define los problemas actuales, la arquitectura objetivo y un plan por fases
> aprobables de forma independiente.

---

## 1. Problemas actuales

### Problema 1 — Inversión de dependencia dominio → infraestructura (y el workaround de import circular)

`task.py` es el núcleo de dominio, pero importa la infraestructura de comunicación:

```python
# task.py:17
from .notification_channels import NotificationChannel, _FileChannel
```

`Task.__init__` construye los handlers de logging en el momento de la
construcción (`task.py:351-365`). Esto crea la cadena de importación:

```
task.py → notification_channels.py → _email_internals.py → task.py  ✗
                                       (necesita TaskStatus)
```

El ciclo se "resuelve" hoy con un **workaround**: los internals de comunicación
no importan `TaskStatus`, sino que comparan contra el string del valor del enum:

```python
# _webhook_internals.py
_STATUS_SUCCESS = "success"
...
if entry.status.value == _STATUS_SUCCESS:
```

```python
# _email_internals.py
_STATUS_ERRORED = "errored"
```

Esto es frágil (se rompe en silencio si cambia el `.value` del enum) y es el
síntoma visible de que la dirección de la dependencia está invertida: el dominio
no debería arrastrar la infraestructura.

### Problema 2 — Canales con doble contrato y transporte duplicado

`EmailChannel` y `WebhookChannel` implementan **dos** interfaces con modelos de
entrega distintos:

| | Task (`NotificationChannel`) | Report (`ReportChannel`) |
|---|---|---|
| Disparo | Evento de logging (`LogRecord`) | Llamada explícita |
| Momento | Durante la ejecución | Al finalizar |
| Entidad | `logging.LogRecord` (streaming) | `ProcessExecutionReport` (one-shot) |
| Quién envía | El `Handler` (autónomo, en `emit`) | El canal (directo, en `send_report`) |

Las dos interfaces son legítimamente diferentes. El problema **no** es que existan
ambas, sino que el **transporte está duplicado**:

- **Email**: `_HTMLEmailHandler.emit` (`_email_internals.py:170-192`) abre SMTP,
  arma el `MIMEText`, autentica, hace `sendmail` y `quit`. La función nueva
  `send_report_email` repite exactamente esa misma secuencia.
- **Webhook**: ya fue parcialmente deduplicado — `_WebhookHandler.emit` y
  `send_report_webhook` comparten `_post_json`. Falta cerrar la simetría del
  lado email.

### Problema 3 — Duplicación entre `Process` y `Task` (cierre de handlers y propiedad partida)

El mismo bucle de cierre de handlers aparece **idéntico** dos veces en `process.py`:

```python
# process.py:267-269  (remove_task)        y        process.py:376-379  (close_loggers)
for handler in list(task.logger.handlers):
    handler.close()
    task.logger.removeHandler(handler)
```

El problema de fondo es de **propiedad partida**: `Task` *crea* su logger y sus
handlers (`task.py:348-365`), pero `Process` los *destruye* metiendo la mano en
`task.logger.handlers`. La gestión del ciclo de vida del logger está repartida
entre dos clases.

### Problema 4 — Namespace plano con roles muy distintos

`src/processes/` mezcla en un solo nivel 2 módulos de dominio con ~10 de
comunicación:

```
process.py  task.py  execution_report.py  exceptions.py        ← dominio / orquestación
notification_channels.py  _email_internals.py  _webhook_internals.py
email_config.py  webhook_config.py  _error_data.py  _tb_utils.py
_logfile_formatting.py  exception_html_formatter.py  html_logging.py   ← comunicación
```

A medida que se añadan canales (Slack, SMS, etc.) el directorio raíz seguirá
creciendo con archivos cuyo rol no es evidente desde su ubicación.

---

## 2. Invariantes (lo que NO debe romperse)

1. **Definir un `Task` sigue siendo trivial para el usuario.** La firma pública
   se mantiene:
   ```python
   Task("t", func, channels=[EmailChannel(smtp_cfg)])
   ```
   El usuario nunca construye handlers ni transportes a mano.
2. **API pública estable.** Todo lo exportado hoy en `processes/__init__.py`
   (`Task`, `Process`, `TaskStatus`, `ErrorData`, `EmailChannel`,
   `ProcessExecutionReport`, etc.) se sigue importando con `from processes import ...`.
3. **Rutas de módulo documentadas estables.** `processes.html_logging`
   (`HTMLSMTPHandler`) está expuesto en `docs/reference`. Si el archivo se
   reubica, se deja un *shim* de re-export en la ruta antigua para no romper
   `from processes.html_logging import ...`.
4. **Sin regresiones.** `pytest`, `mypy` y `ruff` quedan verdes tras cada fase.

---

## 3. Arquitectura objetivo

### 3.1 Capas

El dominio define **puertos** (clases abstractas); la comunicación provee
**adaptadores** (implementaciones concretas). Dentro de la comunicación se
separan tres responsabilidades hoy entremezcladas:

```
                 ┌──────────────────────────────────────────┐
   DOMINIO       │  Task · Process · ProcessExecutionReport  │
   (puertos)     │  TaskStatus · TaskResult · ErrorData      │
                 │  NotificationChannel · ReportChannel (ABC)│
                 └───────────────────┬──────────────────────┘
                                     │ depende solo de abstracciones
                 ┌───────────────────▼──────────────────────┐
   COMUNICACIÓN  │  Channels (adaptadores user-facing)       │
   (adaptadores) │     EmailChannel · WebhookChannel         │
                 │  Render  (entidad → payload)              │
                 │     HTML email · JSON webhook             │
                 │  Transport (payload → destino)            │
                 │     _SMTPTransport · _WebhookTransport    │
                 └──────────────────────────────────────────┘
```

- **Render** = "qué entregar": convierte un `LogRecord` (Task) o un
  `ProcessExecutionReport` (Report) en un cuerpo (HTML / JSON).
- **Transport** = "cómo entregarlo": una sola implementación de SMTP-send y una
  sola de HTTP-POST, usadas tanto por el handler de streaming como por el envío
  one-shot del reporte. **Aquí se elimina la duplicación del Problema 2.**
- **Channel** = objeto de configuración que el usuario pasa; cablea render +
  transport para sus dos roles. Al quedar render/transport como capas
  separadas, el canal es delgado y puede implementar ambos puertos sin duplicar
  nada (la doble capacidad pasa a ser una conveniencia honesta, no un smell).

### 3.2 Paquete `comms/`

Se agrupa toda la comunicación en un subpaquete plano (sin sub-subdirectorios:
`transports/` + `rendering/` con 2 archivos cada uno sería sobre-ingeniería):

```
src/processes/
  __init__.py            # API pública (sin cambios de exports)
  process.py             # Process, ProcessRunner
  task.py                # Task
  task_types.py          # TaskStatus, TaskResult, TaskDependency   ← LEAF (sin imports de comms)
  error_data.py          # ErrorData (dataclass puro)               ← LEAF
  _tb_utils.py           # utilidades de traceback                  ← LEAF (dominio)
  execution_report.py    # ProcessExecutionReport, TaskReportEntry
  exceptions.py
  html_logging.py        # shim de compatibilidad → comms
  comms/
    __init__.py          # re-exporta canales y ABCs públicos
    base.py              # PUERTOS: NotificationChannel, ReportChannel, ReportContent
    channels.py          # ADAPTADORES: EmailChannel, WebhookChannel, _FileChannel
    config.py            # SMTPConfig, HTMLEmailStyle, WebhookConfig
    _smtp.py             # _SMTPTransport (envío unificado) + handler de streaming
    _webhook.py          # _WebhookTransport (POST unificado) + handler de streaming
    _email_render.py     # _HTMLEmailFormatter (task) + render HTML del reporte
    _webhook_render.py   # _WebhookFormatter (task) + payload JSON del reporte
    _error_context.py    # _ErrorContextFormatter (lee LogRecord)
    _logfile_formatting.py
    exception_html_formatter.py
    themes/              # styles / palettes / languages
```

**Por qué `ErrorData` y `_tb_utils` salen a leaf y `_ErrorContextFormatter` no:**
`ErrorData` es un dataclass de valor (contexto de fallo) que `TaskResult` referencia
— es dominio. `_tb_utils` construye ese contexto y lo usa `Task`
(`task.py:473-474`) — también dominio. En cambio `_ErrorContextFormatter` es un
`logging.Formatter` que lee un `LogRecord`: eso es comunicación y se queda en
`comms/`. Hoy `_error_data.py` los mezcla; se separan.

### 3.3 Cómo se rompe el ciclo (sin workaround)

Tras mover los tipos de valor a leaves sin dependencia de comms:

```
task.py        → task_types, error_data, _tb_utils, comms.base (ABC), comms (_FileChannel)
comms/*        → task_types, error_data, _tb_utils, comms.base, config
execution_report.py → task_types, error_data   (+ TYPE_CHECKING: comms.base.ReportChannel)
process.py     → task, task_types, error_data, execution_report, exceptions
```

`comms/` nunca importa `task.py` ni `process.py`. Los renderers importan
`TaskStatus` directamente desde `task_types` (leaf). **El ciclo desaparece y se
borran `_STATUS_SUCCESS` / `_STATUS_ERRORED`.**

> **Nota de honestidad sobre el alcance:** esto rompe el *ciclo* y elimina el
> workaround, pero `task.py` sigue dependiendo de `comms.base` para el ABC
> `NotificationChannel` y de `_FileChannel`. **No** es una inversión total
> dominio→infra. Se adopta deliberadamente el enfoque **ports & adapters
> pragmático**: las clases abstractas `NotificationChannel` / `ReportChannel` se
> consideran *puertos propiedad del dominio*, y `comms.base` se mantiene como un
> verdadero leaf que no importa ningún internal de `comms`. Para una librería de
> este tamaño esto es suficiente; reubicar los ABC al lado del dominio (inversión
> total) sería más churn sin beneficio proporcional.

### 3.4 Propiedad del logger unificada (Problema 3)

`Task` gana la responsabilidad de su propio teardown:

```python
# task.py
def close_handlers(self) -> None:
    """Cierra y desadjunta los handlers del logger de la tarea."""
    for handler in list(self.logger.handlers):
        handler.close()
        self.logger.removeHandler(handler)
```

`Process.close_loggers` y `Process.remove_task` dejan de duplicar el bucle y
llaman `task.close_handlers()`. El que *crea* los handlers es el que los
*destruye*.

---

## 4. Decisiones de diseño

| # | Decisión | Razón |
|---|---|---|
| A | Extraer tipos de valor (`TaskStatus`, `TaskResult`, `TaskDependency`, `ErrorData`) a módulos leaf sin imports de comms | Rompe el ciclo en la raíz; elimina el workaround de strings; cero cambio de API |
| B | Una sola implementación de transporte por medio (`_SMTPTransport`, `_WebhookTransport`) usada por streaming y one-shot | Elimina la duplicación de SMTP entre handler y reporte |
| C | Mantener `NotificationChannel` y `ReportChannel` como **dos ABCs separados** | Son modelos de entrega genuinamente distintos (streaming vs one-shot); forzar uno solo mezclaría conceptos |
| D | Mantener la doble capacidad de `EmailChannel`/`WebhookChannel` | Conveniencia de "un objeto, dos roles". Deja de ser smell una vez que render/transport son capas compartidas. `_FileChannel` (solo `NotificationChannel`) demuestra que los ABCs no se imponen a la fuerza |
| E | `Task.close_handlers()` | Unifica la propiedad del ciclo de vida del logger; elimina la duplicación Process/Task |
| F | Paquete `comms/` plano + shim en `processes.html_logging` | Agrupa por rol sin romper rutas públicas ni sobre-anidar |

---

## 5. Plan de implementación por fases

Cada fase deja `pytest` / `mypy` / `ruff` verdes y es aprobable por separado.

### Fase 0 — Romper el ciclo y la duplicación Process/Task (pequeña, sin cambio de API)
- Extraer `TaskStatus`, `TaskResult`, `TaskDependency` a `task_types.py`.
- Extraer `ErrorData` a `error_data.py`; dejar `_ErrorContextFormatter` donde está
  (luego se moverá a `comms/`).
- Borrar `_STATUS_SUCCESS` / `_STATUS_ERRORED`; los renderers importan `TaskStatus`.
- Añadir `Task.close_handlers()`; `Process.close_loggers` y `remove_task` lo usan.
- **Impacto:** nulo en API pública. Es la fase que ataca directamente los puntos
  que el usuario señaló (workaround + duplicación Process/Task).

### Fase 1 — Unificar transporte
- Introducir `_SMTPTransport.send(subject, html_body)` con la conexión + MIME +
  auth + `sendmail` + `quit` en un solo lugar.
- `_HTMLEmailHandler.emit` y `send_report_email` delegan en él. (El handler puede
  simplificarse a un `logging.Handler` plano, ya que hoy sobreescribe casi todo
  `SMTPHandler`.)
- Cerrar la simetría del webhook alrededor de `_WebhookTransport` (formaliza el
  ya existente `_post_json`).
- **Impacto:** nulo en API pública; elimina la duplicación del Problema 2.

### Fase 2 — Introducir el paquete `comms/`
- Mover los módulos de comunicación a `comms/` según §3.2.
- `comms/__init__.py` re-exporta los símbolos públicos; `processes/__init__.py`
  pasa a importar desde `comms`.
- Dejar shim en `processes/html_logging.py`.
- **Impacto:** movimientos de archivo + actualización de imports. API pública y
  rutas documentadas intactas (verificado por los tests existentes + invariante 3).

### Fase 3 — (Opcional) Formalizar la capa de render
- Separar limpiamente render de transport donde aún convivan en un mismo archivo,
  si la Fase 1/2 no lo dejó ya nítido.

---

## 6. Extensibilidad — añadir un canal nuevo

Con la estructura objetivo, agregar p. ej. un canal de Slack:

1. ¿POSTea JSON? Reutiliza `_WebhookTransport` tal cual.
2. Render: añade un formateador/render en `comms/_webhook_render.py` (o uno nuevo)
   si el payload difiere.
3. `class SlackChannel(NotificationChannel, ReportChannel)` en `comms/channels.py`,
   cableando render + transport. Implementa `build_handler` y/o `send_report`
   según los roles que soporte.
4. Exportar en `comms/__init__.py` y `processes/__init__.py`.

No se toca el dominio (`task.py`, `process.py`, `execution_report.py`): solo se
añade un adaptador. Esa es la escalabilidad que se busca.

---

## 7. Resumen

| Problema | Solución | Fase |
|---|---|---|
| Workaround de import circular | Tipos de valor en leaves; renderers importan `TaskStatus` | 0 |
| Duplicación Process/Task | `Task.close_handlers()` | 0 |
| Transporte duplicado (email/report) | `_SMTPTransport` / `_WebhookTransport` compartidos | 1 |
| Namespace plano con roles mezclados | Paquete `comms/` + shims | 2 |
| Doble contrato de canal | Se conserva (2 ABCs) — deja de ser smell al compartir capas | 1–2 |

Recomendación: aprobar e implementar **Fase 0 y 1** primero (correctitud y
deduplicación, riesgo mínimo, sin cambio de API). La **Fase 2** (paquete) es la
más "churny" y conviene revisarla como PR aparte.

---

## 8. Estado de implementación (as-built)

Fases 0, 1 y 2 implementadas y verdes (134 tests, mypy, ruff; wheel verificado
con `comms/themes/` incluido). Desviaciones menores respecto al plan, todas
deliberadas:

- **Configs no se fusionaron** en un único `config.py`: se mantienen
  `comms/email_config.py` y `comms/webhook_config.py` (menos churn, sin
  beneficio real en fusionar).
- **Nombres de módulo de delivery**: `comms/_email.py` y `comms/_webhook.py`
  (en vez de `_smtp.py`/`_webhook.py`); contienen render + transporte +
  handler de su medio. `_logfile_formatting.py` → `comms/_logfile.py`.
- **Sin shims** en rutas viejas: los tests acoplados a rutas internas se
  repuntaron a la nueva ubicación (o al import público cuando el símbolo es
  público). `html_logging.py` ya no existía, así que no hubo shim que mantener.
- **Fase 3 (separar render/transport en archivos distintos): no realizada.**
  Las clases de transporte (`_SMTPTransport`, `_WebhookTransport`) ya quedan
  nítidamente delimitadas dentro de sus archivos; separarlas más sería
  fragmentación sin beneficio. Queda como refinamiento opcional futuro.
