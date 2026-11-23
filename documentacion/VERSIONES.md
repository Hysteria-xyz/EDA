# Versiones del cliente y novedades (regla permanente, 21-nov-2026)

**Toda actualización que el launcher reparta a los jugadores lleva una versión nueva, sus novedades y su revisión.**
Se usa el sistema que ya funciona, sin inventar otro.

## Qué número es cuál
| qué | dónde vive | formato | quién lo sube |
|---|---|---|---|
| **Release del cliente** (lo que baja el launcher) | `version` de `eda.json` (`armar_cliente.py`), firmado con `firmar_manifiesto.py` | `AAAA.MM.DD` (o `AAAA.MM.DD.N`) | quien publica |
| **DLL** | `herramientas/dll_d3d9/VERSION`, más el commit y el build dentro de la DLL (`EDA-ID\|v=…\|c=…\|s=…`) | `x.y.z` | la PR que cambia la DLL |
| **Server** (solo server) | el commit de despliegue (`/opt/eda/actualizaciones.log`) | commit | el CI y el cron del VPS |

- El launcher guarda la última release que aceptó (`eda_ver_ok` en `launcher.json`) y **rechaza** una menor. Por eso cada publicación tiene que subir la versión.
- Un cambio **solo del server** no genera descarga ni release del cliente.
- **TEST y prod van por separado:**
  - TEST: canal `cliente-develop` (CI) y manifiesto de *ensayo* (`R2_EDA_MANIFIESTO_PRUEBA`).
  - Prod: manifiesto firmado en el dominio de EDA, con la orden de Rui.

## El número de versión (22-nov-2026; corregido el 23-nov con el dueño del launcher)
- La versión del cliente es **`AAAA.MM.DD`**: el día en que se publica.
- Si sale **más de una el mismo día**, se le agrega un número: `AAAA.MM.DD.1`, `AAAA.MM.DD.2`…
  La **primera del día va sin número**.
- Orden: `2026.11.21` < `2026.11.21.1` < `2026.11.21.2` < `2026.11.22`.
- ⛔ **Nada de letras** (`2026.11.22a`): el launcher valida la versión con `^[0-9]{1,8}(\.[0-9]{1,8}){0,7}$` (sólo
  números separados por puntos) y la compara número por número (`eda.rs`: `version_tupla`). Con una letra dice
  «número de versión inválido» y **nadie** baja esa actualización. `revisar` la rechaza.

## La regla (la hace cumplir `py herramientas\version_cliente.py revisar`)
1. La versión nueva es `AAAA.MM.DD` (o `AAAA.MM.DD.N`, si ya salió otra ese día) y **mayor** que la anterior.
2. Tiene su entrada en `NOVEDADES.json`, completa y sin `"borrador"`:
   - fecha y resumen;
   - al menos una de estas listas: corregidos, mejoras o avisos;
   - texto plano, sin HTML.
3. **Algo cambia.** Si no cambia ningún archivo, no se publica. Solo se bajan los archivos cuyo md5 cambió.
4. Si cambia `d3d9.dll`:
   - tiene la marca EDA-ID;
   - **no** es una compilación sucia;
   - es exactamente la del manifiesto (por md5: nada de archivos viejos);
   - su `VERSION` es **mayor** que la de la release anterior y coincide con `"dll"` de su entrada.
5. Si cambia `EDA_limpio.exe`, la revisión **se detiene**: su md5 es la clave del protocolo. Primero el server tiene que conocer la clave nueva.
6. `autoexec.cfg` y `eda_d3d9.ini` son del jugador: el launcher los baja solo si faltan.

## Publicar (con la orden de Rui)
1. Que la PR del cambio suba `herramientas/dll_d3d9/VERSION` (si cambia la DLL) y agregue su entrada a `NOVEDADES.json` (con `"borrador": true` mientras no se publica).
2. Compilar la DLL desde un clon limpio o tomar la del CI. **Nunca** la de una copia con cambios.
3. Armar y revisar:
   ```
   py herramientas\armar_cliente.py
   py herramientas\armar_cliente.py manifiesto AAAA.MM.DD BASE SERVIDOR CANJE
   py herramientas\version_cliente.py revisar _trabajo\eda.json ANTERIOR\eda.json --carpeta _trabajo\cliente_repartir
   ```
   Si dice ⛔, no se publica.
4. Quitar `"borrador"` y poner la fecha. Después:
   ```
   py herramientas\version_cliente.py novedades _trabajo\eda.json
   py herramientas\firmar_manifiesto.py firmar _trabajo\eda.json <privada> > manifiesto.jws
   ```
   Las novedades van **firmadas** junto con el resto.
5. Subir primero los archivos y **después** el manifiesto. Así nadie recibe un manifiesto que apunta a archivos que todavía no están.
6. Comprobar con `identificar.py` sobre una instalación hecha por el launcher: la DLL y la release tienen que ser las publicadas.

**Volver atrás:** no se puede servir una versión menor, porque el launcher la rechaza. Se publica **otra versión mayor** con los archivos anteriores y una entrada en NOVEDADES que lo explique. Por eso se guardan los archivos de cada release (`/opt/eda/files-eda/<release>-<azar>/`).

## Lo que ve el jugador: la PÁGINA DE EDA en el launcher (23-nov-2026, decisión del dueño del launcher)
No hay POP-UP. Las novedades se ven en la **pantalla de EDA del launcher**, que es **contenido dinámico del
Coordinador** (como la de R2Beat 2013): cada juego tiene su página, y su staff la edita desde el panel.

1. **La fuente es `NOVEDADES.json` de `main`.** Cada entrada sin `"borrador"` es una versión publicada.
2. **El Coordinador la trae como BORRADOR** a «Página de EDA» (con su versión, fecha, resumen, corregidos, mejoras y
   avisos). Nada llega al jugador hasta que el staff de EDA (admin o el moderador que tiene EDA) lo **publica**.
3. **El staff la revisa, la corrige si hace falta y la publica** desde el panel: la versión actual, «qué cambió» y el
   historial, más el banner y las cajas de la pantalla.
4. **El launcher la muestra en la pantalla de EDA**, como texto plano (sin HTML): «Versión actual», «Qué cambió»
   (con NUEVO después de actualizar, hasta que el jugador lo mira) e «Historial».

Por eso lo que importa del lado de EDA es **escribir bien `NOVEDADES.json`**: corto, para el jugador, sin HTML ni
direcciones de memoria. `version_cliente.py revisar` lo controla. El bloque `novedades` del manifiesto firmado
(`version_cliente.py novedades`) sigue siendo opcional: el launcher ignora los campos que no conoce.

## Lo que cada entrega dice (plantilla)
```
Versión anterior: …        Versión nueva: …        (DLL: x.y.z → x.y.z')
Archivos modificados: …    (los demás no se vuelven a bajar)
Cambios visibles para los jugadores: …
Pruebas realizadas: … (automáticas / en el juego, entorno, fecha)
Texto para el jugador: (py herramientas\version_cliente.py popup VERSIÓN) — lo publica el Coordinador
Publicación: pasos 1–6 de arriba · Reversión: versión mayor con los archivos anteriores
```

## Borrador en curso: 2026.11.22 (dll 0.5.3) — qué pasó las pruebas

Estado: **borrador** (no publicado). El contenido final se decide por lo que pasa las pruebas, no por lo programado.
Base: develop **7823eca** (con #68, el selector de Stage = dll 0.5.1). La release lleva la dll **0.5.3** (`a9678cda`,
commit 04e141d): 0.5.1 (selector) + 0.5.2 (las llamadas sin resolver / mal resueltas) + 0.5.3 (el diagnóstico).

| Qué | Dónde | Resultado |
|---|---|---|
| La caída 0x7F4626 | EDA-PRUEBA-APIS, dll 0.5.1-candidata e2bf4df2 (21-nov 18:17–18:21) | ✅ se reproduce sin la reparación; con ella `setlocale("korean")` vuelve; 1 Stage sin errores |
| Pruebas sin juego | `prueba_apis.c/.py`, `prueba_selector.c`, `prueba_diag.c/.py`, `diag_partida control`, server | ✅ (CI) |
| El diagnóstico de punta a punta | EDA-PRUEBA-DIAG (server local, dll 0.5.3 a9678cda, 21-nov 19:15) | ✅ 7 lotes, 16 eventos, 0 fallos, el más lento 32 ms; el server los guardó y diag_partida los puso en su partida |
| FPS con y sin diagnóstico | EDA-PRUEBA-DIAG sin / con (1 Stage cada una, sin tope) | ✅ sin 148 (mín 66) · con 161 (mín 85): sin pérdida medible (la diferencia entre dos partidas es de ±10 %) |
| La caída 0x7F4626 con la dll final | EDA-PRUEBA-DIAG (las dos veces) | ✅ `setlocale("korean")` vuelve, sin errores |
| Partida de DOS en TEST | — | pendiente (después del despliegue autorizado) |

La versión ANTERIOR es **2026.11.21** (TEST, publicada el 21-nov ~19:00 con la dll 0.5.1 del selector: el launcher de la
PC de pruebas la bajó a las 19:02). Por eso las novedades de 2026.11.22 ya NO repiten el arreglo del selector.
✅ **El formato, confirmado con el dueño del launcher (23-nov):** tres números (`2026.11.22`) y, si sale otra el
mismo día, `.1`, `.2`… El launcher NO usa `semver` para EDA (ver «El número de versión» arriba).
Si se publica otro día, la versión es la de ESE día: `AAAA.MM.DD` (o `AAAA.MM.DD.1`, `AAAA.MM.DD.2`… si ya salió una ese
día), siempre mayor que la anterior; `version_cliente.py revisar` lo exige.
