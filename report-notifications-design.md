# Diseño: notificación de `ProcessExecutionReport` (email + webhook)

> Branch: `feature/report-notifications`
> Estado: stubs `notify` / `notify_errors` ya creados (lanzan `NotImplementedError`).

## 1. Análisis de situación

El proyecto ya tiene infraestructura de notificación, pero **orientada a `Task`** y
**dirigida por logging**:

- `NotificationChannel` (ABC) expone un único método: `build_handler(task_name) -> logging.Handler`.
- `_FileChannel`, `EmailChannel`, `WebhookChannel` producen handlers que un `Task`
  adjunta a su logger. Emiten **por cada error**, mientras la tarea corre.
- El render de email (`_HTMLEmailFormatter` + templates en `themes/styles`,
  `themes/palettes`, `themes/languages`) está hecho para **un solo fallo**:
  substituciones `exception`, `traceback_highlight`, `traced_vars`,
  `downstream_items`, etc.
- Configs de transporte/presentación: `SMTPConfig`, `HTMLEmailStyle`,
  `WebhookConfig`.

`ProcessExecutionReport` ya sabe serializarse (`to_json()`, lossless), y se acaban
de agregar los stubs `notify()` / `notify_errors()`.

**Tensión central:** los dos consumidores tienen modos de entrega distintos.

| | `Task` | `ProcessExecutionReport` |
|---|---|---|
| Modo | streaming / push | one-shot / pull |
| Dirigido por | `logging.LogRecord` | objeto completo en memoria |
| Cuándo | cada error, durante el run | una vez, al terminar |
| Contenido | un fallo | tabla de N tasks (success/errored/skipped, tiempos) |

Forzar el reporte por el mismo `build_handler`/`SMTPHandler` obligaría a
**fabricar `LogRecord` falsos** → impedance mismatch. Hay que evitarlo.

## 2. Objetivo

Permitir que un `ProcessExecutionReport` se notifique vía:

- **Email**, configurable en **estilo** (layout/paleta/idioma, reusando el sistema
  de themes) y en **información** enviada.
- **Webhook**, como **JSON** (reusando `to_json()`).

Con dos entradas: `notify()` (reporte completo) y `notify_errors()` (solo entries
`ERRORED`). Idealmente, que un mismo "canal" se pueda anotar tanto a una `Task`
como a un `ProcessExecutionReport`, configurando el destino una sola vez, y
extensible a nuevos destinos (Slack/Teams/etc.).

## 3. Solución propuesta

### 3.1 Qué se reutiliza y qué no

| Pieza | Reutilizar | Nota |
|---|---|---|
| `SMTPConfig` | ✅ tal cual | Transporte puro, desacoplado de Task/logging. |
| `WebhookConfig` | ✅ tal cual | Transporte puro (URL/JSON). |
| Sistema de themes (`themes/`) | ✅ | Assets de estilo/paleta/idioma. |
| `HTMLEmailStyle` | 🟡 como selector de estilo | `traced_vars_frame_filter` es específico de fallo; evaluar un `ReportEmailStyle` o ignorar ese campo. |
| `_HTMLEmailFormatter` + templates de error + handlers | ❌ | Renderizan un solo fallo y son `LogRecord`-driven. El reporte necesita template y formatter propios, y envío one-shot. |

### 3.2 Abstracción de canales: dos interfaces angostas (no un ABC gordo)

```text
TaskChannel    -> build_handler(task_name) -> logging.Handler      (= NotificationChannel actual)
ReportChannel  -> send_report(report, *, errors_only) -> None
```

- `EmailChannel` / `WebhookChannel` implementan **ambas** (mismo destino, dos verbos),
  reusando internamente `SMTPConfig` / `WebhookConfig`.
- `_FileChannel` implementa **solo** `TaskChannel`.
- Composición sobre un ABC único: así ningún canal se ve forzado a un método que no
  tiene sentido (evita reintroducir `NotImplementedError`).

### 3.3 Render del reporte (email)

- Nuevo template "reporte" (tabla de tasks: nombre, estado, intentos, duración,
  y sección de errores con su contexto) reusando los directorios de
  styles/palettes/languages.
- Nuevo formatter que consume un `ProcessExecutionReport` (no un `LogRecord`).
- Envío SMTP one-shot (no vía `logging.handlers.SMTPHandler`).

### 3.4 Render del reporte (webhook)

- POST del payload `to_json()` (ya lossless). `errors_only` filtra a entries `ERRORED`.

## 4. Razón

- **Separar transporte de presentación de entrega.** El transporte
  (`SMTPConfig`/`WebhookConfig`) es lo genuinamente desacoplado y reutilizable; el
  render por-fallo no lo es. Reutilizar el transporte evita duplicar auth/URL/TLS.
- **Respetar streaming vs one-shot.** Son modos de entrega distintos; un único
  `build_handler` no modela ambos sin hacks (LogRecords falsos).
- **Interfaces angostas > ABC gordo.** Permite "anotar el mismo canal a Task o a
  Report" sin métodos irrelevantes, y deja extensibilidad limpia (un destino nuevo
  implementa lo que aplique).
- **No abstraer con un solo caso.** Empezar con configs directas y extraer canales
  cuando aparezca el 2º/3er destino reduce el riesgo de sobre-diseño.

## 5. Plan de implementación

**Fase 0 — hecho.** Stubs `notify` / `notify_errors` con firmas que referencian
`SMTPConfig`/`HTMLEmailStyle`/`WebhookConfig` (sin churn futuro).

**Fase 1 — Webhook (lo más simple).**
- Implementar `notify`/`notify_errors` para el caso webhook usando `to_json()` +
  `WebhookConfig`. `errors_only` filtra entries.
- Tests: payload correcto, filtrado de errores, no-op si no hay webhook.

**Fase 2 — Email (reporte completo).**
- Nuevo template de reporte + nuevo formatter (tabla de tasks + detalle de errores),
  reusando themes y `HTMLEmailStyle` como selector.
- Envío SMTP one-shot con `SMTPConfig`.
- Decidir: ¿qué es "información configurable"? (columnas/secciones, incluir
  tracebacks sí/no, etc.). ¿`HTMLEmailStyle` o nuevo `ReportEmailStyle`?
- Tests: render por estilo/paleta/idioma; modo errors-only.

**Fase 3 — Abstracción de canales.**
- Introducir `ReportChannel`; renombrar/alias `NotificationChannel` → `TaskChannel`
  (manteniendo compat).
- `EmailChannel`/`WebhookChannel` implementan ambas interfaces.
- `notify`/`notify_errors` aceptan objetos canal además de configs.

**Fase 4 — Docs + ejemplos.**
- Documentar en `docs/` y agregar ejemplo en `examples/`.

## 6. Decisiones abiertas

1. ¿`HTMLEmailStyle` reutilizado o `ReportEmailStyle` nuevo (por `traced_vars_frame_filter`)?
2. ¿Qué exactamente es "información configurable" del email del reporte?
3. ¿`send_report` síncrono y que propague errores de envío, o best-effort silencioso
   como hacen los handlers de logging hoy?
4. ¿`notify` recibe configs (simple) o canales (unificado) en la primera versión?

## 7. Alternativa simplificada (sin abstracción de canales)

En lugar de introducir `TaskChannel` / `ReportChannel`, `notify` y `notify_errors`
reciben **directamente** los objetos de transporte que ya existen — exactamente las
firmas de los stubs actuales:

```python
report.notify(
    email=SMTPConfig(...),
    email_style=HTMLEmailStyle(...),   # o ReportEmailStyle, ver 7.1
    webhook=WebhookConfig(...),
)
report.notify_errors(webhook=WebhookConfig(...))
```

El reporte arma internamente su payload (HTML para email, `to_json()` para webhook)
y lo envía. **No** hay interfaces de canal, **no** hay objeto que se anote a la vez a
`Task` y a `Report`.

**Pros**
- Mínimo: es literalmente implementar los stubs tal cual; cero abstracción nueva.
- Aprovecha lo genuinamente reutilizable (`SMTPConfig`/`WebhookConfig` son transporte
  puro), que es donde está casi todo el valor de reuso.
- En espíritu con una lib "lightweight, zero-dep".

**Contras**
- No unifica "configurar un destino una vez y usarlo en Task y en Report".
- Cada destino nuevo (Slack/Teams/SNS) es **otro parámetro** de `notify`, no una clase
  polimórfica. Escala mal si se esperan muchos destinos.
- Algo de duplicación entre el envío del lado-Task (handlers) y el lado-Report.

**Cuándo preferirla:** si la notificación del reporte es la única necesidad nueva y no
se prevén muchos destinos. **Recomendación:** empezar por aquí; extraer canales
(sección 3.2) recién cuando aparezca el 2º/3er destino o se quiera la ergonomía de
"un canal para ambos". Es reversible: las firmas con configs pueden coexistir o migrar
a aceptar canales después.

### 7.1 `ReportEmailStyle`: ¿subclase o hermanas?

`HTMLEmailStyle` tiene `style` / `palette` / `language` (comunes a cualquier email) y
`traced_vars_frame_filter` (**específico de un fallo**, sin sentido en un reporte).

| Opción | Veredicto | Razón |
|---|---|---|
| **A. `ReportEmailStyle(HTMLEmailStyle)`** (subclase) | ❌ Evitar | Heredaría `traced_vars_frame_filter`, que no aplica. Herencia debe **añadir**, no heredar-e-ignorar. Un reporte "no es un tipo de" estilo-de-error (LSP smell). |
| **B. Hermanas bajo base común `EmailStyle`** | ✅ Si aporta campos propios | Base `EmailStyle` = `style`/`palette`/`language`. `HTMLEmailStyle(EmailStyle)` añade `traced_vars_frame_filter`; `ReportEmailStyle(EmailStyle)` añade lo específico del reporte (qué columnas/secciones, incluir tracebacks, etc.). Sin campos muertos. |
| **C. Reusar `HTMLEmailStyle` tal cual** (ignorar el campo) | ✅ Si no aporta nada aún | Lo más simple. Trade-off: arrastra un campo semánticamente muerto en el contexto de reporte. |

**Recomendación:** empezar con **C** (reusar `HTMLEmailStyle`) en la versión simplificada;
migrar a **B** (extraer base `EmailStyle` + hermanas) en cuanto el email del reporte
necesite sus propios knobs. **Nunca A.**
