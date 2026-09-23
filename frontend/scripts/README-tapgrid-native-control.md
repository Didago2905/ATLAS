# TapGrid: control nativo BrowserStack

## Propósito y requisitos

Una prueba diagnóstica en iPhone real (`realMobile=true`): Safari vía
BrowserStack/Appium/XCUITest → contexto `NATIVE_APP` → W3C Actions multitouch →
WEBVIEW → exportación JSON plana del Tap Timing Lab → evaluación de entrada y toggle.
No usa eventos DOM sintéticos ni emulación de mouse.

Requiere Python 3.9+ (sólo biblioteca estándar), acceso a BrowserStack Automate y
una URL pública de ATLAS operativa con `/?tapTimingLab=1`. No requiere BrowserStack
Local ni instalar paquetes. El frontend debe exponer
`window.ATLAS_TAP_TIMING_LAB.reset()` y `exportSession()`.

## Ejecución

Inyectar en el entorno `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY` y
`ATLAS_PUBLIC_URL`. No guardar sus valores en código, documentación ni comandos
versionados. `--url` puede sustituir la URL del entorno; se navega a la raíz con
`?tapTimingLab=1`.

Desde la raíz del repositorio, inspeccionar el plan sin crear sesión ni hacer requests:

```sh
python frontend/scripts/tapgrid-native-control.py
```

Ejecutar una sola prueba control, defaults iPhone 13 Pro Max / iOS 18:

```sh
python frontend/scripts/tapgrid-native-control.py --run
```

Para otra combinación disponible:

```sh
python frontend/scripts/tapgrid-native-control.py --run --device "iPhone 14 Pro Max" --ios "16"
```

Consultar primero el catálogo vigente de BrowserStack Automate
(`GET https://api.browserstack.com/automate/browsers.json`, autenticación por entorno).
No hardcodear futuras matrices basándose en resultados históricos. Con `--run`, el
harness hace preflight HTTP de ATLAS y valida dispositivo/iOS/Safari/realMobile en
ese catálogo **antes** de `POST /session`; el modo sin `--run` no consulta catálogo.
El hub es `https://hub.browserstack.com/wd/hub`.

Cada ejecución crea como máximo una sesión y envía como máximo un `/actions`, sin
retries automáticos. Ambos dedos siguen DOWN → 60 ms → UP → 140 ms → DOWN → 60 ms
→ UP, con aproximadamente 200 ms entre inicios de chords. `gestureSent=true` sólo
se registra tras respuesta exitosa de `/actions`. Un timeout no demuestra que el
dispositivo no recibió la petición: no repetir automáticamente. Toda sesión con
ID conocido intenta `DELETE` en `finally`.

## Preparación y seguridad

- Recursos de flujo: `.home-controls__museum img` y `img.home-catalog-icon` deben
  ser únicos, estar cargados y tener dimensiones intrínsecas y cajas válidas.
  `document.readyState=complete` no garantiza layout final.
- Hay 15 s para readiness/recursos y, desde que están listos, otros 15 s para
  estabilidad: al menos cuatro muestras durante dos segundos. Una petición HTTP
  en curso puede extender el tiempo de pared hasta su timeout.
- Identidad y viewport deben coincidir; centros/puntos admiten rango de 1 px y
  dimensiones web de 7 px. Se conservan hit-tests y márgenes interiores.
- `featuredShake` cambia bounding boxes sin volver inseguro el punto táctil. No
  exigir igualdad del bounding box nativo ni de coeficientes entre calibraciones.
  La seguridad depende de identidad, contexto/ventana, calibración fresca y puntos
  finitos dentro de imagen/ventana con margen de 12 px y proyección inversa segura.
- `/source` se usa internamente para localizar una única imagen visible por el alt
  de la tarjeta; el XML completo no se persiste. El mapping requiere confirmación
  posterior mediante las coordenadas táctiles recibidas, no se presume demostrado.
- Reset ocurre en WEBVIEW después de revalidar la geometría web y antes de volver
  a NATIVE_APP. El export proyecta primitivas y copias planas para evitar referencias
  compartidas/no transferibles del resumen del lab.

## Interpretación y resultados locales

- **PASS:** entrada completa válida, decisión del segundo chord disponible y en
  ventana temporal, toggle reconocido y cambio de modo esperado (focus ↔ gallery).
- **RECOGNIZER_FAIL:** esa entrada y evidencia de decisión están demostradas, pero
  no se reconoce el toggle o no se obtiene el modo esperado. Nunca sin `inputValid=true`.
- **INCONCLUSIVE:** preparación/infraestructura fallida, entrada incompleta o fuera
  de ventana, mapping no confirmado, evidencia insuficiente o error de cierre/export.
  No atribuir un fallo al recognizer ni modificar producción ante evidencia ambigua.

Revisar `reason`, `errors`, `inputValid`, `recognizerEvaluated`, `toggleRecognized`,
`modeBefore/After` y `sessionDeleted`. `readiness` conserva conteo, última muestra,
último reinicio y momento de recursos listos; `initial`, `geometryRevalidation`,
`geometryChecks`, calibraciones y evidencia táctil permiten auditar las decisiones.
La versión solicitada puede no venir en capabilities: `osVersionStatus=unconfirmed`
no significa iOS confirmado; no inferirlo de rutas internas ni del catálogo.

Los JSON se guardan en `frontend/tests/results/tapgrid-native-control/` (ignorado
por Git); `--output` admite una ruta alternativa nueva. Son artefactos locales,
no memoria permanente. No versionar resultados ni copiar secretos o URLs temporales
a esta guía. El harness sanea credenciales antes de consola/JSON. No borrar evidencia
existente como parte de una ejecución normal.

## Validated baseline

Resultados históricos comunicados del laboratorio realMobile + Safari/XCUITest:

| Dispositivo | iOS solicitado | Resultado |
|---|---|---|
| iPhone 13 Pro Max | 18 | PASS |
| iPhone 14 Pro Max | 16 | PASS |
| iPhone 15 Pro Max | 17 | PASS |
| iPhone 16 Pro | 18 | PASS |
| iPhone 17 Pro | 26 | PASS |

Son combinaciones solicitadas/observadas en BrowserStack, no una garantía universal
para todos los modelos/versiones ni confirmación de una versión que el proveedor
no haya informado. No sustituyen el catálogo vigente. En esos controles se reportó
entrada válida, toggle reconocido, focus → gallery y ningún error.
