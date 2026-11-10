# ATLAS Editorial — checkpoint 2026-11-09

Editorial V2.2: fases 1, 2A, 2B, 3A, 3A.1 y 3A.2 completadas.
Incluyen contrato y navegación segura, candidatos SQL/Museum, sugerencias
conservadoras, confirmación explícita de identidad en Carta y correcciones UX.

## Validación manual comunicada por el operador

- `/carta22` y búsqueda de candidatos SQL.
- Súper Harry, ID SQL 82, con confirmación humana de identidad.
- Persistencia después de reiniciar el supervisor.
- Cancelación y retorno a V2.1.
- Retirada de teclados obsoletos.

## Pendiente

- Confirmar visualmente el indicador nativo de escritura de Telegram.
- Edición comercial utilizando los patches seguros existentes.
- No se ha implementado publicación ni activación automática.

## Consola de bots: inspección y punto de parada

El arranque existente conserva tres paneles: backend/supervisor, Vite y
Cloudflare/Notifications. Incidents y Editorial siguen siendo hijos del
supervisor. Sus salidas comparten la consola backend; no existen archivos de
log independientes que puedan seguirse directamente. Notifications imprime
desde el launcher de Cloudflare.

No se implementó captura de stdout ni se cambió WindowsChildren, el launcher
o los workers. Separar la salida actual exigiría modificar el transporte de
salida de procesos supervisados. Conforme a la condición de parada, queda
para revisión la alternativa mínima: logs separados y acotados de estados
saneados mediante logging estándar, con tres visores de solo lectura en
otra pestaña de Windows Terminal. Los visores no consumirían Telegram ni
serían supervisores; los tres paneles actuales y el acceso de inicio de
sesión permanecerían intactos. Los logs no deben incluir tokens, URLs con
credenciales, mensajes, propuestas, adjuntos ni otros contenidos privados.

En esta sesión no se arrancaron ni detuvieron servicios, no se contactó
Telegram, no se abrió ninguna SQLite y no se hicieron commits ni pushes.

Validación de cierre: 8 tests offline de supervisión con hijos simulados
aprobados; comprobaciones estáticas de continuaciones y comandos del BAT,
sintaxis Python y `git diff --check` correctas. El acceso directo de inicio
de sesión sigue apuntando al mismo terminal.bat. No se ejecutó Windows
Terminal ni se validó visualmente una nueva distribución de paneles.

Actualización posterior: se implementó la alternativa de logs operativos
rotativos y lectores independientes descrita en `bot-observability-console.md`.
La primera distribución gráfica y la recarga de procesos siguen pendientes de
validación manual autorizada; no se reinició la sesión activa.
