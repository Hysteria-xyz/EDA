# PvP en EDA — Fase 1: investigación y plan

> Rama `feature/pvp-system` (desde `develop` @ f5c9ccb, 24-nov-2026). **Sólo investigación: no se modificó
> ningún archivo del juego ni del server.** Cada afirmación lleva su fuente: archivo:línea, sección de
> `MEDICIONES.md` / `PROTOCOLO.md`, dirección de `exe/EDA_limpio.exe` (md5 0799387e) o ruta dentro de
> `Data.dat` (extraído con `traduccion/herramientas/desempacar_data_dat.py ... extraer --todo`).
> 🟡 = deducción, sin medir. ❌ = buscado y **no** encontrado.

## 0 · Veredicto en una línea

**Un duelo 1 vs 1 es viable, pero no como lo pide el enunciado «el server autoridad del combate»:** en EDA el
combate corre dentro de cada cliente y viaja P2P por UDP; el server no ve golpes, daño, HP ni posición. Lo
alcanzable sin reescribir el cliente es **el server como árbitro** (sala, cuenta regresiva, muertes, ganador,
restauración, vuelta al lobby) y, en una segunda etapa y sólo si las mediciones de la Fase 0 lo permiten,
validación del daño con ganchos de la `d3d9.dll`. Antes de diseñar código hay **cuatro incógnitas que se
miden en el juego** (§10.1); la primera — si el motor deja que un jugador dañe a otro — decide todo.

---

## 1 · Arquitectura del juego

| pieza | qué es | evidencia |
|---|---|---|
| Motor | **LithTech** (versión exacta ❌) | cadenas «LithTech build %s initialized», `ILTServer`, `CLTClient`, `.ltb`, `object.lto` (MEDICIONES l.52-53) |
| Gráficos | Direct3D 9 | nuestra `d3d9.dll` proxy funciona (MEDICIONES §42) |
| Lenguaje del cliente | C++ (Visual C++ 7.1, CRT msvcr71) | firma «Rich» 3077, OEP `0x7E3A11` (MEDICIONES §56, l.117) |
| Guiones de stage | **Lua 5.1.4**, en texto, dentro de `Data.dat` | MEDICIONES §14 (l.1318-1323); 196 `.lua` en `Data.dat` |
| Interfaz | GUI propia sobre HGE + XML de layout (`menu/international/*.xml`) | MEDICIONES l.59-60 |
| Archivos | `Data.dat` = contenedor EldoS **SolFS** cifrado (clave = MD5 de `LTMsg.dll`) | `herramientas/dll_d3d9/eda_traduccion.c:4-18` |
| Protección | ASProtect (el original); usamos `EDA_limpio.exe` desempacado, 511/694 llamadas resueltas | README, `herramientas/contar_piezas.py` |
| Red | TCP cifrado AES-128-ECB con el server; **UDP P2P de LithTech entre clientes** | PROTOCOLO §2, §5.16; `RED_P2P.md` |
| Nuestro server | Python 3, por módulos, un manejador por comando (`@maneja`) | `servidor/LEEME.md`, `servidor/registro.py:12-15` |
| Cómo tocamos el cliente | en memoria desde `exe/d3d9.dll` (C, Zig 0.16), verificando bytes antes de parchear; o Frida | `documentacion/POR_QUE_LA_DLL.md`, MEDICIONES §57 |

Pantallas del cliente (RTTI en el exe): `CChannelLobbyScreen`, `CCharacterSelectScreen`, `CMiddleScreen`,
`CPlayGameScreen`, `CServerSelectScreen`, `CShopNInventoryScreen`, `CThreadRenderScreen`,
`CWaitRoom_MissionScreen` (`0x520827`). ❌ No hay `CWaitRoom_BattleScreen` ni otra pantalla de batalla.

## 2 · Protocolo cliente-servidor (lo que importa para PvP)

Paquete: cabecera de 8 B en claro + AES-128-ECB; datos = `u16 largo · u16 comando · cuerpo` (PROTOCOLO §2).
El cliente despacha cada comando **a la pantalla actual**; un comando que la pantalla no registró se ignora en
silencio (PROTOCOLO §3). ⇒ **No se pueden inventar mensajes nuevos**: un PvP tiene que expresarse con los
comandos que cada pantalla ya atiende, o con un parche del cliente.

Comandos que atiende la pantalla de la partida (`0x548F94`): `1058 1060 1062 1066 106B 106C 106D 106E 106F
1068 1069 1071 1072 1073 1054 1075 105D`; la de carga: `105E 1058`; la sala de espera (`0x550E44`): `1057 1059
1046 1058 104A 104B 1048 1052 1054 1050 104F 104D 105B`. Ninguno es de modo, equipo, bajas ni ranking.
Nombres NetTrace en el exe: sólo `OnPktS2C_Ntf_Play_Start`, `OnPktS2C_SomeOne_ChangeState` y 4 de NAT. ❌
ninguno de PvP.

## 3 · Combate y cálculo de daño

- **Corre en el cliente.** El guion Lua mueve puertas y saca NPC; al server sólo le *avisa* (PROTOCOLO §5.11,
  MEDICIONES §13 l.1284-1286).
- **El server no recibe daño.** Lo único: `0x1063` cada 10 golpes recibidos (`inc word [eax+0xF]; idiv 10`),
  `servidor/partida.py:444-457`.
- ❌ Fórmula de daño, dirección de la función de daño, hitbox, uso de STR/CON/DEX/INT/WIS en combate: no
  aparecen en ninguna fuente. Los stats sólo se conocen como offsets del personaje (PROTOCOLO §5.6).
- Tablas existentes: `datos/Skill.xml` (habilidades, MP, nivel), `datos/ItemTypeList.xml`. 🟡 cómo entran en
  el daño: no medido.
- Habilidades: en la partida **no se lanzan**, ni con el exe original; `SetCurSkill` (`0x560AD0`) nunca se
  llama (MEDICIONES §34). ⇒ hoy el combate es sólo ataque básico.
- API Lua de `CScenario` en el exe, útil para arbitrar: `GetPlayerDamage` (`0x49ED64`), `GetDeadPlayerNum`
  (`0x49ED84`), `GetAlivePlayerNum` (`0x49ED98`), `IsAllPlayerDead` (`0x49EC38`), `GetInAreaPlayers`
  (`0x49ED24`), `KillEntity` (`0x49EDDC`), `KillAllPlayer` (`0x49EDE8`), `GetCurRank`, `SendEvent`.

## 4 · Selección de objetivos

❌ Nada medido ni documentado: ni la función de selección, ni si un `Player` puede ser objetivo de otro
`Player`. Es la **incógnita nº 1** (§10.1, E1).

## 5 · Player, NPC y Monster

| | cómo se identifica | evidencia |
|---|---|---|
| Jugador | número en la sala (slot), `cuenta+0x705` el propio, tabla de miembros en `cuenta+0x240` (`0x61C110`) | `servidor/partida.py:449-455` |
| NPC / monstruo | índice dentro de la stage; grupos `NpcGroupNN` del guion, `NpcType01..12`, grupo 12 = jefe | PROTOCOLO §5.11, MEDICIONES §14 |
| Muerte de NPC | `0x1061` C→S (`u8 n · u8 1 · 6×0`); sólo cuenta la del máster | `servidor/partida.py:397` |
| Muerte de jugador | `0x1065` C→S `u8 jugador · u32 quién lo mató` (🟡 `0x108` = «Baby Tarantula») | PROTOCOLO §5.11 |

❌ No hay estructura común Player/NPC documentada, ni bandos, facciones, «hostile» o fuego amigo (ni en el exe,
ni en los 196 `.lua`). ⚠ El manejador `0x547440` (`0x1062`) lee *ID de actor NPC muerto + slot del jugador
que lo mató* y desreferencia sin comprobar NULL: un `0x1062` mal armado tira el juego
(`servidor/partida.py:449-455`). **Contradice PROTOCOLO.md:294** («vida y maná del HUD»), y
`sincronizar_hud_companero` (`partida.py:460-466`) todavía lo reenvía tal cual: conviene revisarlo aparte.

## 6 · Mapas, instancias y salas

- **Mapas**: sólo `maps/chapter1/` (`chapter1_1..10.dat`, `chapter1_1t.dat`, `boss_room_s.dat`). ❌ arenas.
- **Escenarios**: 150 XML (50 por dificultad del capítulo 1); claves `CLEAR_TYPE` (0, 1, 3 = contrarreloj),
  `MAXPLAYER` (`0x49EFC0`), `KILL_POINT`, `RANK_POINT`, `TOTALEXP`, `MONSTER_CNT`. El server sólo guarda
  `[RANK_POINT, KILL_POINT, TOTALEXP, MONSTER_CNT]` (`servidor/datos.py:17`, `servidor/escenarios.json`).
- **Sala** (`estado.SALAS`, `servidor/estado.py:19`; se crea en `crear_sala`, `servidor/salas.py:901-924`):
  89 B crudos del cliente + `anfitrion`, `miembros`, `numeros`, `listos` y, en partida, `jugando`, `cargados`,
  `en_stage`, `muertos_stage`, `traspaso_master`, `partida_id`…
- Bytes de la sala: `+0x28` escenario · `+0x2C` dificultad (**el cliente no lo lee**: barrido 0x4D0000-0x660000)
  · `+0x2D` RoomState (1 Waiting / 2 Playing) · `+0x2E` jugadores · `+0x2F` máximo · `+0x30` 🟡 ¿tiene clave? ·
  `+0x31` clave. ❌ ningún byte de modo o equipo.
- El escenario lo elige el **cliente** (selector de stages) y el server lo copia; se cambia en vivo con
  `0x104B` tipo 1.

## 7 · Sincronización de movimiento, habilidades y animaciones

- P2P por UDP de LithTech. El server sólo reparte direcciones (`0x1059`; `servidor/salas.py` `pares()`,
  `servidor/relay.py` `dir_udp`), por casa / directo / relay (`RED_P2P.md`).
- Medido: el saludo `0xC354` (×~185 en 2 s, con la MAC como identidad), `0xC351`/`0xC352`; después
  `UdpMsgCnt:151` y los jugadores se ven moverse (MEDICIONES §21, §31).
- ❌ El formato de los paquetes UDP de movimiento, animación, golpe o habilidad. El relay los reenvía **sin
  interpretarlos** (MEDICIONES §31).
- **Máster**: sólo él manda bajas (`0x1061`) y el fin (`0x1064`); bandera `+0x168` del administrador de
  escenarios (`0x64583F`, `0x749020`, `0x747220`); el traspaso va por `0x1058` tipo 3
  (`servidor/partida.py:361-392, 611-618`). 🟡 que el máster sea autoridad de IA/posición de NPC: no medido.

## 8 · Muerte y reaparición

```
0x1065 (murió) → 0x1068 (15000 ms) → cuadro de moneda → 0x106A (sí/no) → 0x106B (1 revive · 0 se rinde · 2 revivió otro)
sin respuesta → 0x1069 (estado 0xA = espectador) → 0x1075 (al lobby)
```
`servidor/partida.py:570-605`, `game_over` (`:148`) desde el `tick` (`servidor/juego.py:158`). PROTOCOLO §5.12,
§5.12b, §5.15. Espectador: `0x106C` (`0x547A60`) cambia la cámara a otro jugador en estado 0xA. ⚠ `0x1075`
mandado en AWARD RESULTS tira el juego (`0x752B7E`, PROTOCOLO §5.15).

## 9 · Restos de PvP en el cliente — **existe un modo «Battle» a medio hacer**

| hallazgo | dónde | estado |
|---|---|---|
| Texto `~PVP Battle~` | `Data.dat:string/international/uistring.xml:44` (INDEX 40; el 41 es «Service Currently Not available») | presente, sin uso medido |
| Pestaña de modo en el lobby: `ChannelLobby_ModeBtnList` con `ScenarioModeBtn` (texto 3008 «Scenario») y **`ChannelLobby_BattleModeBtn`** | `Data.dat:menu/international/channellobby.xml:120-126`; textura `lobby_battle_tab.tga` (l.77) | layout y textura existen |
| **Sala de espera de equipos rojo/azul, 8 vs 8** (casillas 303-310 rojo, 311-318 azul) | `Data.dat:menu/international/waitroom_battle.xml` («by ulelio (SoftNyx)», l.2, l.17-21) | **huérfana**: faltan las texturas (`image/.../WaitRoom_Battle` no existe; sólo `waitroom_mission`), los textos 4027-4029 y la pantalla en el exe |
| Música `bg_battle*.mp3`, insignias de rango `RESULT_mission_rankS..D.tga` | `Data.dat:sounds/`, `menu/international/gamescene.xml:51-55` | reutilizables |
| Historia | «PvP: en septiembre [2009] todavía no existía» | `documentacion/HISTORIA.md:16, 30` |

❌ Buscado sin resultado (exe, `d3dx9_29.dll`, 196 `.lua`, `traduccion/`, `datos/`, `servidor/`): versus,
duel, arena, deathmatch, teammatch, redteam/blueteam, ctf, survival, ladder, ranking, spectat, gamemode,
roomtype, playmode, clan/guild war, hostile, friendlyfire, team (fuera de equipamiento), faction. Los 85
«pvp» en bytes del exe son código, no texto. **No quedó ningún código de PvP**: sólo datos de interfaz.

## 10 · Viabilidad, limitaciones y lo reutilizable

### 10.1 · Las cuatro incógnitas (se miden antes de escribir código de juego)

| # | pregunta | cómo medirla (herramientas que ya existen) | si sale mal |
|---|---|---|---|
| **E1** | ¿Un jugador puede **golpear y dañar** a otro? (selección de objetivo, colisión del arma con un Player) | dos clientes en la misma PC (`segundo_jugador.bat`), cara a cara en una stage; mirar HP con `herramientas/buscar_en_memoria.py`; buscar la función de daño con breakpoints de memoria sobre el HP (Frida/`espiar_*`) | hace falta un parche de cliente que marque al otro jugador como objetivo válido: **trabajo de ingeniería inversa grande, sin plazo estimable** |
| E2 | ¿Qué viaja por UDP cuando alguien ataca? | capturar en `herramientas/relay_udp.py` (ya ve todo el UDP en modo relay) con y sin ataque | sin esto no hay validación de daño posible: sólo arbitraje |
| E3 | ¿Puede un escenario propio (XML + Lua) servirse **en memoria** con el mecanismo de la traducción? | `eda_traduccion.c` ya redirige toda lectura de `Data.dat` a `traducciones\<idioma>\<ruta>` (l.25-28): probar un escenario copia de uno existente sin NPC, con `OnEnd` controlado | el duelo se haría sobre un escenario PvE existente, ignorando a los NPC |
| E4 | ¿Qué hace el cliente con `0x1065` cuando lo mató **otro jugador**? (el `u32` del atacante) | E1 + espiar el `0x1065` en el server (`_trabajo\broker\espia.log`) | el server no sabe quién ganó; se decide por «el que queda vivo» |

### 10.2 · Choque con las restricciones del enunciado

- **«El server como autoridad del combate»: hoy imposible.** El server es ciego al combate (§3, §7). Se
  propone en dos niveles: **(A) arbitraje** (alcanzable): el server decide inicio, fin, ganador, premios y
  restauración, y descarta lo incoherente (muerte sin partida, ganador que no estaba en la sala, duelo
  terminado antes de la cuenta regresiva). **(B) validación de daño** (sólo si E1 y E2 salen bien): la
  `d3d9.dll` reporta cada golpe entre jugadores y el server lo acepta o rechaza por distancia/tiempo/daño
  máximo. (B) no se puede prometer hoy.
- **«No modificar archivos originales»: se cumple.** Todo cliente va por la `d3d9.dll` en memoria y por
  archivos sueltos/embebidos que reemplazan lecturas de `Data.dat` (`eda_traduccion.c:3-5`); `Data.dat`,
  `EDA_limpio.exe` y `LTMsg.dll` no se tocan (y no se pueden tocar: el MD5 del exe es la clave AES, PROTOCOLO
  §2; el de `LTMsg.dll`, la de `Data.dat`).
- **Sin mensajes nuevos** (§2): la sala PvP, la cuenta regresiva y el resultado se arman con comandos que el
  cliente ya atiende (`0x101E`/`0x1020`/`0x104F`/`0x105E`/`0x1065`/`0x1069`/`0x1073`/`0x106E`/`0x1075`, el
  chat `0x100D`).
- **La pestaña «Battle» y la sala rojo/azul no se pueden activar** sólo con datos: falta la pantalla en el exe.

### 10.3 · Reutilizable

- Todo el ciclo de sala y partida del server (`servidor/salas.py`, `servidor/partida.py`): crear, entrar,
  listo, largar, carga, largada, muerte, espectador, fin, vuelta al lobby, traspaso de máster, guardias.
- La red P2P (casa / directo / relay) tal cual.
- Los ganchos de `Data.dat` de la `d3d9.dll` (escenario/guion/texturas/textos propios sin tocar originales).
- API Lua `CScenario` (`GetAlivePlayerNum`, `IsAllPlayerDead`, `KillAllPlayer`, `SendEvent`) para un guion de
  duelo que termine solo cuando queda uno.
- El texto `~PVP Battle~`, la música de batalla, las insignias de rango, el mapa `boss_room_s.dat` como arena
  🟡 (sala cerrada; no medido).
- Las pruebas con conexiones falsas (`pruebas_multijugador`, `servidor/pruebas.py:1272`;
  `pruebas_fin_stage_grupo`, `:1882`) como molde de las del PvP.

---

## 11 · Plan de implementación

### Etapa 0 — Medir (sin código de juego; cada resultado entra a `MEDICIONES.md`)

E1 → E4 de §10.1, en ese orden. **Puerta**: si E1 da «no», se detiene el plan y se decide entre (a) invertir
en ingeniería inversa del sistema de objetivos o (b) un PvP indirecto (carrera/contrarreloj por la misma
stage, comparando tiempos y puntos: 100 % servible hoy con lo que ya existe).

### Etapa 1 — Arquitectura (los componentes del enunciado, adaptados a lo real)

Un módulo `servidor/pvp.py` **no puede registrar de nuevo** `0x1065`, `0x1064` ni `0x104E`
(`servidor/registro.py:15`, `assert`). Se ramifica dentro de los manejadores existentes con
`if s.get("modo") == "duelo": return pvp.<x>(...)`, de modo que con `modo` ausente el PvE es byte por byte el
mismo de hoy.

| componente pedido | dónde vive en la arquitectura real |
|---|---|
| PvPManager | `servidor/pvp.py`: funciones puras llamadas desde `salas.py`/`partida.py`/`juego.tick` |
| PvPRoom | la misma sala de `estado.SALAS` con `s["modo"]="duelo"` (marcado por un comando de chat `/duelo` antes de crear, o por un rango de escenario 🟡; **no** por un byte del cliente: ninguno significa modo) |
| PvPMatch | la misma partida de `estado.PARTIDAS` con un bloque `p["pvp"]` (vidas, muertes, atacante, reloj) |
| PvPTeam | lista de números de sala por equipo dentro de `s["pvp"]` (1 vs 1 = dos equipos de uno) |
| PvPCombatHandler | nivel A: `murio` en modo duelo → registrar baja y atacante (E4), no abrir el cuadro de moneda; nivel B (si E1/E2): mensajes de golpe que reporta la dll |
| PvPSpawnManager | posiciones distintas: guion Lua propio servido en memoria (E3) |
| PvPRanking | campos nuevos con valor por defecto en la cuenta (`servidor/cuentas.py:15`): `pvp_ganadas`, `pvp_perdidas`, `pvp_puntos` |
| PvPRewardManager | `_fin_de_uno` en modo duelo arma su propio `0x1073`/`0x106E` (sin `StageReward`) |

Reglas del server que se respetan: estado vivo sólo en `estado.py`/`SALAS`/`PARTIDAS` (la recarga en
caliente borra los módulos, `servidor/__init__.py:44`); todo cambio de estado bajo `servidor.CANDADO` o desde
el `tick`; nunca mandar a alguien fuera de la stage mensajes de la stage (`partida.py:435`).

### Etapa 2 — Duelo 1 vs 1 (cada punto con su prueba en `servidor/pruebas.py`, con su caso al revés)

1. Sala de duelo: máximo 2, `s["modo"]="duelo"`; el revés: una sala normal no cambia.
2. Entran dos jugadores, listos, F9 (ciclo de hoy).
3. Posiciones iniciales distintas: guion de escenario servido por la dll (depende de E3).
4. Cuenta regresiva: en el chat (`0x100D`) antes del `0x105E`, o el tiempo del propio `0x105E`/`0x106D` 🟡.
5. Daño validado: nivel A (arbitraje de muertes); nivel B sólo si E1+E2.
6. Habilidades/animaciones: las sincroniza LithTech P2P como hoy (las habilidades activas hoy no andan:
   MEDICIONES §34).
7. Muerte: `0x1065` en duelo → sin cuadro de moneda; el otro gana.
8. Ganador: `0x1073` + `0x106E` con el resultado, y aviso por chat.
9. Restaurar: HP/estado lo restaura el cliente al cargar la próxima stage; la cuenta no pierde monedas ni EXP.
10. Vuelta segura: el mismo camino que hoy (resultado → sala), nunca `0x1075` en AWARD RESULTS.

Verificación de cada etapa: `py servidor\juego.py control`, `relay_udp.py control`, `contar_piezas.py
control`, `compilar.py` si cambia la dll, y **dos clientes reales** (misma PC y luego casas distintas contra
el server de prueba, 35900) antes de marcar algo como hecho.

### Etapa 3 — Expansión (sólo diseño; nada se marca hecho sin probar)

- **Team Deathmatch / todos contra todos**: `s["pvp"]["equipos"]` con N listas; el máximo de la sala lo
  limita `MAXPLAYER` del escenario y el `+0x2F` (hoy 3 por defecto, `salas.py:901-924`).
- **Captura de bandera**: objetos activables del mapa (`0x1067`/`0x1066`, cofres) + eventos del guion
  (`0x105C`/`0x105D`) 🟡.
- **Partidas personalizadas**: comandos de chat al estilo de los de GM (`/oro`, `/fin`, PR #76).
- **Ranking y temporadas**: campos de la cuenta + panel interno (`servidor/panel.py`).
- **Matchmaking**: sobre la entrada rápida `0x1025`/`0x1026` (el cliente ya la atiende, PROTOCOLO §5.8b).
- **Espectadores**: estado 0xA + `0x106C` (cambio de cámara), ya en el cliente.
- **La pantalla «Battle» del lobby** (rojo/azul): requiere crear la pantalla en el exe vía dll; sólo si lo
  anterior funciona.

## 12 · Archivos tocados en esta fase

| archivo | cambio |
|---|---|
| `documentacion/PVP_INVESTIGACION.md` | nuevo (este informe) |

Ningún otro archivo del repo, del cliente ni del server cambió.
