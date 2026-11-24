# PvP — recuperar el modo «Battle» (etapa 0.4)

> Rama `feature/pvp-system`. Base: [PVP_INVESTIGACION.md](PVP_INVESTIGACION.md) §9. Investigación **estática**
> (sin abrir el juego): `Data.dat` extraído con `traduccion/herramientas/desempacar_data_dat.py`, y
> `exe/EDA_limpio.exe` (md5 0799387e) leído con capstone. ✅ = leído en el exe o en los datos · 🟡 = deducción ·
> ❌ = buscado y no está. Nada de esto se probó en el juego todavía.

## 0 · En una línea

Softnyx dejó **los datos** de Battle (la pestaña del lobby, una sala de equipos rojo/azul, el texto «~PVP
Battle~») y **un hueco en el código**: la pantalla nº 4 del juego existe como clase, pero vacía. No hay nada que
«prender». Lo recuperable sin tocar el exe es **la interfaz como archivos servidos en memoria por la
`d3d9.dll`** (layouts XML y texturas nuevas), sobre las pantallas que SÍ tienen código (lobby y sala de
misión); la lógica (equipos, duelo) va en el server.

## 1 · Cómo carga sus pantallas el juego — ✅

- **`Data.dat:data/main.xml`** numera las pantallas (`<MENU ROOTPATH="Menu\\International">`): 0 Openning ·
  1 ServerSelect · 2 CharacterSelect · 3 ChannelLobby · **4 WaitRoom_Battle** · 5 WaitRoom_Mission ·
  6 ShopNInventory · 7 Clan · 8 GameScene · 9 GameLoad · 10 RoadMap. Son los mismos números que usa el protocolo
  (3 = lobby, 5 = sala, 6 = tienda, 8 = partida: PROTOCOLO §5.7–5.17). Los nombres de los XML **no están en el
  exe** (ni ASCII ni UTF-16): salen de este archivo.
- **La fábrica de pantallas**: `0x4E7050`, un `switch` de 9 casos (tabla en `0x4E732C`), cada uno
  `new(tamaño)` + constructor: 0 `0x4FFB70` · 1 `0x516730` · 2 `0x4FA9D0` · 3 `0x4F5F50` (lobby) ·
  **4 `0x534840`** · 5 `0x53C920` (sala de misión) · 6 `0x52BF30` · 7 `0x4FB280` · 8 `0x515210` (partida).
- **La pantalla 4 es un cascarón** (`0x534840`, objeto de 0xD8 B = el tamaño de la clase base): llama al
  constructor base (`0x4E4080`), pone su vtable `0x89A1C0` y vuelve. Sus métodos propios son `ret`
  (`0x534880`, `0x534890`, `0x5348B0`), `xor eax,eax; ret` (`0x5348C0`), saltos a la base (`0x5348A0`,
  `0x5348D0`, `0x534900`, `0x534910`, `0x534940`), un «CursorCenter 0» (`0x534920`) y «soy la 4»
  (`0x534950: mov eax, 4`). ❌ No ata ningún control, no lee la sala, no atiende ningún mensaje.
  La 5 (misión), en cambio, tiene su vtable llena de código propio (`0x534AB0`, `0x53D680`, `0x535000`…).
  (La 7, Clan, es otro cascarón del mismo tamaño, y `Clan.xml` ni está en `Data.dat`.)

⇒ **Pasar a la pantalla 4 no tiene sentido hoy**: mostraría un layout sin código detrás (y con las texturas
faltantes, §3). Rehacerla sería escribir una pantalla entera dentro de la dll.

## 2 · La pestaña «Battle» del lobby — ✅ los datos, ❌ el código

`Data.dat:menu/international/channellobby.xml`, grupo `ROOMLIST` (ID 1, l.108):

| control | qué es | dónde |
|---|---|---|
| `BUTTONEXLIST 101` | `ChannelLobby_ModeBtnList`, 2 visibles, horizontal, en (229, 81) | l.120 |
| `BUTTONEX 102` | `ScenarioModeBtn`, textura 16 `lobby_tap_sinario.tga`, texto **3008 «Scenario»** | l.121 |
| `BUTTONEX 103` | `BattleModeBtn`, textura 43 `lobby_battle_tab.tga`, **`STRID="0"`** | l.126, textura l.77 |

- **Las dos texturas existen** (`image/ui_image/international/channellobby/`, 128×128 con 118×81 útiles) y son
  **iguales en estilo**: tres estados (normal / encima / marcado) de una pestaña negra con filigrana gris, **sin
  letras**. El nombre lo pone el texto. ⇒ **la pestaña vacía que se ve al lado de «Scenario» es la de Battle**:
  sale sin nombre porque su `STRID` es 0.
- **El código del lobby no la usa** (✅): el constructor del lobby (`0x4F5F50`) ata sus manejadores con
  `0x4DF900(evento, id, función)` — 55 ataduras, a los controles 1, 6, 7, 100, 110–113, 261–263, 265/266,
  301, 303–310, 402/403, 560, 1003, 2003, 3011–3013, 3017/3018, 4000–4002, 6000/6001, 7001–7003, 8002/8003,
  9001/9002, 10005 y 11000/11001 — **ninguna a 101, 102 ni 103**. Lo único: al iniciar, `0x4F8223` marca a la fuerza la 102
  (`0x7673C0(102)` sobre la lista 101 = «Scenario» seleccionada). 🟡 Dos ataduras llevan el id en un registro
  (`0x4F60BF`, `0x4F7353`): no cambian el cuadro (todo lo demás está a la vista).
- ⇒ **Clic en Battle hoy**: la GUI la marca (es `CHECK="1"`), y nada más: la lista de salas no se filtra, no
  se manda nada al server. 🟡 Medir en el juego (§6, paso 1).
- (Descartado: `0x4F8FA0` resta `0x65` al id del botón, pero es la elección de PERSONAJE: escribe el lugar
  elegido en `cuenta+0x2B0+0x454` y busca el personaje con ese `+0x52` entre 5 registros de 186 B; lo atan los
  5 botones de CharacterSelect, `0x4FB0BB…0x4FB20B`.)

## 3 · La sala de equipos `waitroom_battle.xml` — ✅ los datos, ❌ todo lo demás

`Data.dat:menu/international/waitroom_battle.xml` (16 755 B, «by ulelio (SoftNyx)»):

| grupo | controles | nota |
|---|---|---|
| 0 GLOBAL | 0–8 | |
| 2 MAPINFO | 100–103 | |
| 3 ROOMINFO | 200–212 | |
| **4 USERLIST** | **300** fondo (STRID **4027**) · **301** botón ROJO (STRID **4028**, textura 8) · **302** botón AZUL (STRID **4029**, textura 9) · **303–310** 8 casillas rojas (x 211) · **311–318** 8 azules (x 496) | 8 vs 8 |
| 5 Chatting | 400–403 | |
| 6 MYINFO | 500–512 | |
| 7 ERR_POPUP | 600 | |

- **Faltan las 18 texturas** que pide: las 16 de `WaitRoom_Battle\` (`BG.tga` 800×600, `grb_001` 166×30,
  `grb_button` 91×90, `grb_002` 780×29, `grb_mapinfo` 180×284, `tempMapImage` 155×97, `grb_roominfo` 180×202,
  **`grb_userlist` 587×317, `grb_userlist_red`/`_blue` 283×69, `grb_userlist_red_a`/`_blue_a` 283×66**,
  `grb_chatting` 396×145, `grb_chatting_ComboListBack` 16×16, `grb_chatting_ComboButton` 29×50, `grb_myinfo`
  180×166) **y** `Shared\popup.tga` / `Shared\popup_button_ok.tga` — que en este build se llaman
  `popup_common01.tga` / `popup_ok_button.tga`. ⇒ es el layout de **una versión anterior** que quedó en el
  contenedor. ❌ La carpeta `WaitRoom_Battle` no existe; sólo `waitroom_mission` (16 archivos).
- **Faltan los textos 4027–4029** en `uistring.xml` (llega a 4026).

### 3.1 · ¿Puede la sala de misión cargar el layout de Battle? — ❌

La pantalla 5 ata 301–308 (evento 5: las 8 filas de jugadores) y 309, y pide por id (`0x7510F0`) los controles
100–105, 201/202, 300, 309, 400 (×3), 500, 600, 700, 800 (×7), 920 y 1100 (✅, barrido de `0x534980–0x5410A0`).
En `waitroom_mission.xml` el **300 es una `BUTTONEXLIST`** (8 filas verticales, 301–308 de 337×29, textura 11
`waitroom_bar_userlist.tga`), el 400/500/600/700 son popups y el chat es 200–202. En `waitroom_battle.xml` el
300 es un `BOARD`, el 400 el fondo del chat y el 600 el popup de error. ⇒ servir el de Battle en lugar del de
misión **cruza tipos de control**: el código pediría una lista y recibiría un cuadro. Riesgo cierto de caída.

## 4 · Servir archivos propios sin tocar `Data.dat` — ✅ el mecanismo existe

`herramientas/dll_d3d9/eda_traduccion.c` engancha las 7 funciones de SolFS por las que pasa **toda** lectura de
`Data.dat` (XML, texturas HGE, Lua, `.dtx`; l.7-18). En `tr_mi_open` (l.464-507) busca **antes** de abrir
`Data.dat`: (1) el archivo suelto `traducciones\<idioma>\<ruta>`, (2) el embebido en la dll, (3) `Data.dat`.
⇒ por el código, **también sirve una ruta que no existe en `Data.dat`** (una textura nueva) 🟡 (no medido con
una ruta nueva). Dos límites:
- sólo engancha si hay idioma activo (`g_tr_idioma`, l.467): con `idioma=en/off` no hay redirección. Para la
  interfaz de PvP conviene una capa propia (p. ej. `[pvp] activo=1` con su carpeta), independiente del idioma;
- todo lo que se sirve tiene que respetar los id y los tipos de control que el código espera (§3.1).

## 5 · Textos

- `uistring.xml` 40 = «~PVP Battle~», 41 = «Service Currently Not available» (l.44-45). 🟡 El exe no los pide
  con número fijo: de 189 llamadas a la lectura de textos (`0x5D42F0` → `0x5CF240` → **`0x607D10(id, búfer,
  0x400)`**), 97 tienen el número a la vista y ninguna es 40 ni 41 (sí 38, 39, 42). Las otras 92 lo calculan:
  no se puede descartar.
- Agregar un texto = el mismo camino que la traducción: un `uistring.xml` servido en memoria con los índices
  nuevos (`traduccion/es/string/international/uistring.xml` ya es ese archivo para el español). Faltarían el
  nombre de la pestaña (para el `STRID` del 103) y, si se hace la lista de equipos, «Rojo» / «Azul».

## 6 · Equipos rojo / azul: qué datos hay — 🟡

- En la sala y en el miembro de 0x32C **no hay ningún campo de equipo identificado** (PVP_INVESTIGACION §6;
  `servidor/salas.py:39-95`): +4/+5 id y **número de jugador**, +0xA identidad P2P, +0x48 direcciones UDP,
  +0x54 personaje, +0xBA equipamiento, +0x322 listo, +0x323 🟡 (lo cambia el `0x1058` tipo 2; tiene que estar
  en 0 para largar: coincide con el ícono de «en la tienda», textura 24 `Waitingtoom_b_shop.tga`), +0x324 /
  +0x328 u32 sin significado conocido.
- ⇒ **el equipo lo decide y lo guarda el server** (`s["pvp"]["equipos"]` por número de jugador). Mostrarlo en
  la sala de misión sólo es posible si la fila de cada jugador es fija por número (🟡 sin medir: hoy no se sabe
  si la fila 301 es siempre el número 0).

## 7 · Qué se recupera, cómo, y qué NO se habilita todavía

| pieza | se puede | cómo | ¿se muestra ya? |
|---|---|---|---|
| nombre de la pestaña Battle | sí | `STRID` del 103 → un texto nuevo, en el `channellobby.xml` + `uistring.xml` servidos por la dll | **NO** hasta que el clic haga algo de verdad (regla: nada que aparente funcionar) |
| que el clic en Battle filtre / cree salas de duelo | sólo con código | un gancho en la dll sobre la lista 101 (o un atajo: la pestaña manda `/duelo` por el chat, como hacen ya los botones Clan/Messenger con `[mazino] botones`) | NO hasta probarlo con dos clientes |
| sala de equipos 8 vs 8 propia (pantalla 4) | no razonablemente | habría que escribir la pantalla entera en la dll | — |
| sala de duelo sobre la de misión | sí | la sala normal + estado PvP en el server; avisos por chat | sólo cuando el duelo ande (PVP_MEDICIONES §3) |
| barras roja / azul con la estética de EDA | sí | teñir `waitroom_bar_userlist.tga` (341×93, 3 estados grises neutros: medido) y `lobby_battle_tab.tga`; servirlas como archivos nuevos | NO mientras no haya equipos reales |
| las 16 texturas de `WaitRoom_Battle\` | no hacen falta | el layout que las pide no tiene pantalla | — |

## 8 · Riesgos

- Cruzar ids o tipos de control en un layout servido → caída al abrir la pantalla (§3.1).
- La redirección depende del idioma activo (§4): un jugador con `idioma=off` vería la interfaz original.
- Un `channellobby.xml` servido reemplaza el de todos los que tengan la dll: cualquier error se ve en el lobby
  de todos. Va primero detrás de una clave del ini, apagada por defecto, y se mide en dos PCs (la regla de la
  dll, `documentacion/ENTORNOS.md`).
- 🟡 Los textos 40/41 podrían estar en uso con número calculado: no reusarlos; agregar índices nuevos.

## 9 · Plan (cada paso con su verificación)

1. **Medir la pestaña tal cual** (sin tocar nada): en el lobby, clic en la pestaña vacía con
   `udp_combate.py`/el registro del server mirando. Esperado (§2): se marca y no pasa nada más (ningún mensaje
   TCP nuevo en `server.log`). Si pasa algo, este documento se corrige.
   ✅ **Medido el 24-nov** (sesión `20261124-081432`, clic automático en (408, 96)): la pestaña se marca y
   «Escenario» se apaga; **ningún mensaje al server**; la lista de salas no cambia; volver a «Escenario» deja todo
   igual. Coincide con §2.
2. **Capa `[pvp]` en la dll** (apagada por defecto): la misma redirección de §4 desde una carpeta propia
   (`pvp\<ruta>`), sin depender del idioma. Verificación: con la clave apagada, `eda_d3d9.log` no redirige nada
   (el revés); prendida, redirige un `uistring.xml` de prueba.
3. **El nombre de la pestaña**: `channellobby.xml` con `STRID` nuevo en el 103 + `uistring.xml` con ese texto,
   servidos por la capa `[pvp]`. Verificación: la pestaña muestra el nombre y Scenario sigue igual (las salas
   del PvE se listan como siempre). **Se publica sólo junto con el paso 4.**
   ✅ **Hecho en las instalaciones de prueba** (24-nov, sesión `20261124-081801`), sin capa `[pvp]` todavía (la
   carpeta suelta `traducciones\es\` de las dos instancias): `herramientas/pvp/battle_ui.py generar` lee
   `channellobby.xml` de TU `Data.dat` (el de Softnyx no se copia al repo) y cambia **sólo** `STRID="0"` → `"40"`
   en el 103. No hizo falta un texto nuevo: el **40** es el que el juego trae para esto («~PVP Battle~»; en la
   traducción, «Batalla PvP»), y no se le cambia el valor. Resultado: la pestaña dice **«Batalla PvP»** con la
   letra, el color y la textura originales, y entra en los 118 px; la dll la sirvió
   (`[traduccion] #6 (suelto) → menu\international\channellobby.xml`); «Escenario» sigue igual: rui creó una sala,
   kai la vio en la lista (`0x101C`) y entró (`0x101F` → `0x1020`). ⚠ Sigue sin hacer nada al clic: **no se
   publica** hasta el paso 4.
4. **Que la pestaña haga algo**: gancho mínimo en la dll sobre el cambio de selección de la lista 101 (el aviso
   0xC de `0x7673C0`) que mande un comando de chat al server (como `[mazino] botones`); el server responde con
   la lista de salas de duelo. Verificación con dos clientes.
   ⏳ Requiere código nuevo en la dll y compilarla (Zig 0.16.0, `herramientas/dll_d3d9/bajar_zig.py`: ~90 MB de
   ziglang.org); en esta PC todavía no hay compilador.
5. **Equipos en la sala de misión**: medir primero si la fila = número de jugador; si sí, servir un
   `waitroom_mission.xml` con las mismas ids y tipos y las filas 301–304 / 305–308 con las barras roja / azul
   teñidas. Verificación: abrir la sala, entrar y salir, F9, volver de la partida, sin caídas.
6. La pantalla 4 propia queda fuera de alcance mientras los pasos 1–5 no estén probados.
