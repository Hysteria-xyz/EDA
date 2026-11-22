# POP-UP de novedades en el launcher de R2Beat (para el administrador del launcher)

**Qué hace:** después de instalar bien una actualización de EDA, el jugador ve **una sola vez** un popup con:
- la versión nueva instalada;
- los errores corregidos;
- las mejoras;
- los avisos importantes.

Usa el popup de noticias que **ya tiene** el launcher (`noticias.js`, estilo notas de parche). No cambia nada del Rust, ni de cómo se baja o se verifica EDA.

## El cambio (sólo la pantalla del launcher)

| Archivo | Cambio |
|---|---|
| `novedades.js` (nuevo) | este directorio. Envuelve `LU.edaProg`, `LU.eda` y `Noticias.pintar`. |
| `noticias.js` | + `ultimaSinVer(juego, etiqueta)`, y la agrega al `return` (`noticias.js.diff`, 5 líneas). |
| `launcher.html` | + `<script src="novedades.js">` justo después de `noticias.js` (`launcher.html.diff`, 1 línea). |

Después hay que recompilar el launcher (Tauri) y publicarlo como siempre.

**Cuándo se abre solo:**
- el launcher **bajó** algo de EDA (`LU.edaProg` con un porcentaje), y
- terminó con `LU.eda({estado: 'listo'})`.

Abre la noticia `parche` de EDA más reciente que el jugador todavía no abrió.

**Una sola vez:** queda en `noticias_vistas`, las prefs que el launcher ya guarda.

**Cuándo NO se abre:**
- si sólo revisó y no bajó nada;
- si terminó en error;
- si el jugador ya la había leído en el acordeón.

**Juego abierto (`body.jugando`):** espera a que el juego se cierre.

**Noticias que llegan tarde:** si llegan después de la actualización, se abre cuando llegan.

## El texto: una noticia del panel (`launcher_contenido`)

Cada versión de EDA publica **una noticia**: juego `eda`, etiqueta `parche`, id `eda-<versión>`. La arma el repo de EDA desde `NOVEDADES.json`:

```
py herramientas\version_cliente.py noticia 2026.11.22.1
```

Sale el JSON con estos campos: `id`, `juego`, `etiqueta`, `fijada`, `imagen`, `fecha`, `titulo`, `texto`. El `texto` va con el formato de `noticias.js`: `**negrita**`, `# título`, `- lista`. Ese JSON se carga en el panel.

**Orden:** la noticia se publica **cuando se publica la versión**, no antes. Si aparece antes, el popup se abriría con la actualización anterior.

## La prueba (con la pantalla de verdad)

```
node launcher/popup-novedades/probar_popup.js <ruta>\Launcher.exe noticia.json
```

**Qué hace:**
1. Saca la pantalla del `Launcher.exe` instalado (no se guarda en el repo).
2. Le aplica el cambio y falla si ya no encaja.
3. La abre en Chrome con la vista previa (MOCK) que trae el mismo `launcher.js`.
4. Simula: noticias del panel → bajando → listo.

**Resultado 21-nov, con el `Launcher.exe` de TEST:** ✅ 14/14, captura `1-popup-tras-actualizar.png`.

**Qué comprueba:**
- se abre sola con la versión, los corregidos, las mejoras y los avisos;
- queda en `noticias_vistas`;
- otra actualización no la repite;
- si sólo revisó, no se abre;
- si terminó en error, no se abre;
- con el juego abierto espera;
- si las noticias llegan tarde, se abre cuando llegan;
- si ya la leyó en el acordeón, no se repite;
- no hay errores de JavaScript.

## Lo que falta confirmar con el código del launcher (no lo tenemos)

- **El número de versión de EDA.** La regla de EDA es `AAAA.MM.DD.N` (`2026.11.22.1`). Lo que el launcher ya aceptó tiene tres números (`2026.11.21`). Hay que confirmar si la comparación de `eda_ver_ok` usa `semver` (sólo tres números, sin ceros a la izquierda): de eso depende si la próxima sale como `2026.11.22.1` o como `2026.11.22`.

- **Progreso:** que el backend llame a `LU.edaProg(porcentaje, …)` mientras baja EDA, y `LU.edaProg(null)` + `LU.eda({estado: 'listo', …})` al terminar bien. Así lo hace el MOCK de `launcher.js`. Si el backend avisa de otra forma, alcanza con cambiar las dos envolturas de `novedades.js`.
- **Una prueba en el launcher compilado:** con una versión de TEST, ver que el popup salga una vez y no vuelva a salir al reabrir el launcher.
