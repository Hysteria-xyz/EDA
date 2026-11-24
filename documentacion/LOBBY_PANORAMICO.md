# Pantallas panorámicas: Lobby y Select Character

> 24-nov-2026 · rama `feature/ui-selectcharacter-lobby-widescreen` · EXPERIMENTAL (se prende solo si la carpeta
> `ancho\` está junto al exe; `[pantalla] lobby_panoramico=0` lo apaga).
> ✅ medido en el juego · 🧪 cubierto por pruebas · ⏳ sin medir en vivo.

## 0 · En una línea

En pantallas más anchas que 4:3, **Lobby** y **Select Character** usan un lienzo de interfaz más ancho que 800
(**1066×600** en 16:9, **960×600** en 16:10), con su propio XML y su propio fondo. Los paneles se reacomodan con
anclajes, los marcos se arman por segmentos (no se estiran esquinas ni bordes) y lo que se ve coincide con lo que se
clickea. El resto de las pantallas (sala, Stage, Shop/Inventory, servidores) no cambia: siguen en 800 centrado.

## 1 · Cómo está hecha la interfaz (verificado)

| qué | dónde | evidencia |
|---|---|---|
| layout del lobby | `Data.dat:menu/international/channellobby.xml`: posiciones ABSOLUTAS en un lienzo de 800×600 (X/Y/W/H por control, los hijos de un POPUP relativos al popup) | el archivo |
| layout de Select Character | `Data.dat:menu/international/characterselect.xml` (fondo, 4 botones, 2 flechas, `AVATAR 199`, lista de 5 slots `BUTTONEXLIST 100`, popups 200/300/400/500) | el archivo |
| marcos y fondo | UNA textura por pantalla con los marcos metálicos PINTADOS: `ChannelLobby/lobby_bg.tga`, `CharacterSelect/EDA_characterselect_bg.tga` (1024×1024, se usa 800×600) | extraídas con `battle_ui.leer_original` |
| texturas en el XML | se toman por ORDEN en la lista (no por ID) | PVP_BATTLE_UI.md (24-nov) |
| escala a pantallas grandes | la d3d9.dll (`eda_escala2d.c`): proyección ortográfica, viewports de partes, scissor, dibujos XYZRHW y mouse, todo con `s`, `rx`, `ry` | Punto 5 |
| escenas | lobby = vtable `0x899670`, Select Character = `0x899740`, servidores `0x899DC0`, sala `0x89A268`, Stage `0x899C20`, Shop/Inventory `0x899F10` | `(vigía)` en eda_d3d9.log |
| el personaje 3D | `AVATAR` del XML (X, Y, Z de cámara), dibujado con la perspectiva en el viewport de 800×600 desde `rx` | medido: 1 unidad de X = 1,5 de interfaz (al revés) |
| el clic | el juego recibe la posición convertida por `e2d_mouse`; su prueba de punto es `0x775A70` (rect, x, y) | `eda_d3d9.c · selector_punto` |

**Medido 24-nov (1600×900):** el juego dibuja y hace clic en controles con **x > 800** (hasta el borde derecho), pero
**no con x < 0** (el cursor desaparece y no hay clic). Por eso el lienzo ancho empieza en el borde izquierdo de la
pantalla y todo queda en coordenadas positivas.

## 2 · Qué se cambió

| archivo | cambio |
|---|---|
| `herramientas/lobby_ancho.py` (nuevo) | lee los XML y fondos de TU `Data.dat` (no se suben al repo), arma las variantes 1066 y 960 (XML + fondo `ancho_*.tga` de 2048×1024) y las instala en `<juego>\ancho\<ancho>\`; `control` = 34 pruebas con su revés |
| `dll_d3d9/eda_traduccion.c` | `tr_ancho_elegir(w, h)` (1066 / 960 / 0 según `W·600/H`) y `tr_abrir_ancho`: sirve el XML de la variante al abrirlo y sus texturas `ancho_*` de la misma; anota `g_e2d_lobby_ancho` / `g_e2d_sel_ancho` |
| `dll_d3d9/eda_escala2d.c` | `g_e2d_lienzo` + `e2d_geometria()` (s = mín(W/L, H/600), rx centrado); `e2d_lienzo_de(vt, …)` elige el lienzo por escena en cada cuadro; los dibujos XYZRHW aceptan hasta x = lienzo; `e2d_pan_en_boton` (la columna del lobby) |
| `dll_d3d9/eda_d3d9.c` | con Options/Messenger abiertos, los botones del lobby panorámico se reconocen en la columna derecha |
| `dll_d3d9/eda_graficos.c` | las franjas con ambiente usan el ancho del lienzo |
| pruebas | `prueba_escala2d.c` (+16: lienzo por escena y 11 resoluciones), `prueba_traduccion.c` (+5: la variante por resolución), `prueba_graficos.c` (stub) |

## 3 · Lobby (1066×600)

- **Panel izquierdo** (LOBBY, personaje 3D con sus flechas, estadísticas, EXP): igual, pegado a la izquierda (x 0–214). ✅
- **Centro**: sube 58 (donde estaban los botones de arriba) y se ensancha hasta la columna. La lista de salas queda más
  ancha y alta (10 filas en lugar de 8), con las columnas redistribuidas (Número, candado, Nombre del Stage, Nombre de
  la sala, Participantes, Estado) y su barra de scroll al borde. Buscar Stage / Crear Stage / Entrar, repartidos parejo. ✅
- **Chat**: más ancho (texto y escritura); la lista de usuarios, más ancha en su 2ª columna. ✅ (mensaje escrito y visto)
- **Columna derecha**: Shop, Inventory, Clan, Messenger, Options, Select Character, Exit Game en vertical, con las
  mismas texturas y controles (mismo INDEX: mismos eventos, sonidos y estados). ✅ (Inventory, Select Character)
- **Barra de abajo**: sus puntas iguales, el tramo del medio al ancho; el texto que corre, al ancho. ✅
- **Fondo**: por segmentos: se estiran sólo tramos lisos de los marcos; esquinas y uniones quedan iguales. Todas las
  posiciones del centro pasan por la misma función que el fondo (`f` en x, `g` en y). ✅
- **Ventanas emergentes**: centradas (crear sala 560, lista de salas 590, avisos). ✅ (crear sala desde el mapa)
- ⚠ **El mapa de capítulos (500 y 530) queda donde estaba**: el juego ubica los stages del mapa respecto de la ventana
  500, en coordenadas de 800. Corrida 133, el stage «Inicio de la búsqueda» quedaba en x −116..−76 (original 17..57) y
  el doble clic no lo encontraba (medido con la prueba de punto). En su lugar el mapa es idéntico al original (tapa el
  panel izquierdo y el centro; la columna sigue a la vista). ✅ doble clic → Create Stage → sala → vuelta al lobby.

## 4 · Select Character (1066×600)

- **Marco**: el encabezado «SELECT CHARACTER» y las esquinas, iguales; se estiran sólo los tramos lisos. El pasillo del
  fondo se **agranda parejo** (sin deformar) para cubrir el panel más ancho. ✅
- **Personaje 3D y flechas**: al centro del lugar libre a la izquierda de los slots (`AVATAR X` corregido con la medida
  1 : 1,5). ✅ (rotación con las flechas)
- **Slots**: pegados a la derecha (43 de margen, como en 800); oro / cash en su caja, a la derecha. ✅ (elegir slot)
- **Botones de abajo** (Seleccionar servidor, Crear personaje, Eliminar personaje, Entrar al lobby): repartidos parejo,
  con las rayas de unión redibujadas de botón a botón. ✅
- **Crear personaje** (popup 200, 800×600) y los avisos: centrados. ✅ (un personaje creado desde ahí, 0x1013)

## 4b · Shop / Inventory / Refinery / Skill (rama `feature/widescreen-character-management`)

**Arquitectura compartida (verificado):** las cuatro son UNA escena (`0x899F10`) y UN layout,
`menu/international/shopninventory.xml`; la DLL distingue la pantalla por `[escena+0xDC]` = 4 / 5 / 6 / 7 (Shop,
Inventory, Refinery, Skill). Lo compartido está en los grupos 0–3: el fondo (`Shared/EDA_worlds_bg.bmp`), UN marco de
una pieza (`EDA_shop_b.tga`, 782×537 en (11, 62)) con las uniones pintadas, la barra de arriba (Lobby, Clan, Options,
Messenger, Exit), el selector Tienda/Inventario/Refinería/Habilidades, las estadísticas con sus «+», y
nombre/nivel/clase/oro/cash/CASH. Cada pantalla sólo cambia qué ventanas (POPUP) muestra: a la izquierda el equipo con
el personaje 3D (400), la refinería (700–780) o las habilidades (800–860); a la derecha el catálogo (500–580) o el
inventario con sus 5 pestañas (600–650). Los controles de adentro de una ventana son RELATIVOS a la ventana. Por eso
todo se reacomoda en un solo lugar (`lobby_ancho.py · _tie_ancho`, regla `tie_d(L)`): cambiar de pantalla no mueve
nada compartido.

| qué | cambio |
|---|---|
| marco | ensanchado por segmentos (tramos lisos; esquinas y adornos de las uniones iguales); el panel izquierdo gana 36 % y el derecho 64 % |
| fondo | agrandado parejo (sin deformar) a L×600 |
| barra de arriba | en la columna derecha, en los MISMOS lugares que en el lobby (Lobby 1, Clan 3, Messenger 4, Options 5, Exit 7); la DLL reconoce Clan/Messenger/Options ahí |
| ventanas | centradas en su panel; las grillas, slots e iconos no cambian de tamaño (celdas cuadradas, índices iguales) |
| personaje 3D del equipo | `AVATAR X` corregido (la cámara no sigue a la ventana: medido) |
| estadísticas / nombre y oro | la columna izquierda +⅓, la derecha +⅔ del ancho ganado; nombre/oro/CASH con el panel derecho |
| Refinery | las 4 pestañas (Encantar, Refinar piedra, Crear ranura, Reparar) a 90 px con la pestaña original ampliada por segmentos (`ancho_tab_refineria.tga`); el texto de la elegida, blanco (era rojo sobre rojo) |
| Skill | «Eliminar habilidad» a 115 px con el botón original ampliado por segmentos (`ancho_btn_eliminar.tga`) |

**Probado en vivo a 1600×900:** comprar (Espada larga Básica 1200: oro 5678 → 4478, 0x103F/0x1040), vender (480:
→ 4958, 0x1041/0x1042), tooltips junto al objeto, equipar / desequipar con clic derecho (cabeza: estadísticas bajan y
vuelven), «No puedes equipar este objeto» con uno de Cazadora, el «+» de Fuerza (0 → 1, puntos 72 → 71), cambiar
entre las 4 pantallas, las pestañas y el submenú Reparar, la columna (Lobby, Inventory, Select Character), las
ventanas de confirmación centradas.
**⏳ Sin verificar:** poner objetos en las casillas de la Refinería y arrastrar habilidades: con la automatización no
anduvo NI en la pantalla original (no es una diferencia del panorámico) → probar a mano.

## 5 · Resoluciones

| resolución | variante | cómo se verificó |
|---|---|---|
| 1600×900 | 1066 | ✅ en el juego (las dos pantallas, clics, chat, mapa, sala, crear personaje) |
| 1280×720 · 1366×768 · 1920×1080 · 2560×1440 · 3840×2160 | 1066 (escala del alto, sin franjas) | 🧪 `prueba_escala2d` (lienzo, escala, mouse 0..1065) + `prueba_traduccion` · ⏳ en vivo |
| 1440×900 · 1680×1050 (16:10) | 960 | 🧪 · ⏳ en vivo |
| 2560×1080 (21:9) | 1066 centrado, franjas con ambiente | 🧪 |
| 1024×768 · 1280×1024 · 800×600 | el original | 🧪 (y es lo de siempre) |

Las resoluciones por encima del monitor (2560×1440, 3840×2160 en un monitor de 1920×1080) no se pueden abrir en
ventana en esta PC; la cuenta es la misma que en 1920×1080 con otra escala.

## 6 · Límites

- Funciona con la traducción prendida (`[traduccion] idioma=es`): la capa `ancho\` va por el mismo enganche de archivos.
  Con `idioma=en/off` las pantallas quedan originales.
- La pestaña Battle (`[pvp] batalla=1`) usa otro `channellobby.xml`: el panorámico manda; `lobby_ancho.py generar
  --batalla` la incluye.
- El mapa de capítulos no se ensancha (ver §3).
- «Borroso / chico» de la interfaz escalada: no cambia (haría falta un filtro de nitidez en la 2D).
- Las herramientas de prueba que reconocen pantallas por píxeles (`pantallas.py`, `llevar lobby`) no conocen el lobby
  panorámico (dicen «otra»); el juego no se entera.

## 7 · Cómo probarlo

```
py herramientas\lobby_ancho.py generar
py herramientas\lobby_ancho.py instalar            # _trabajo\juego y A/B/C/D de dos_clientes
py herramientas\lobby_ancho.py control
```
En el juego, con `escala2d=1` y una resolución ancha: eda_d3d9.log dice `(panorámico) 1600×900 → el lobby de 1066×600`
y `escena 0x00899670 → lienzo 1066×600`. Para volver al original: `lobby_ancho.py quitar` o `lobby_panoramico=0`.
