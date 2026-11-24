# PvP — arquitectura y arena (etapas 0.3 y 0.5)

> Rama `feature/pvp-system`. Sigue a [PVP_INVESTIGACION.md](PVP_INVESTIGACION.md) y
> [PVP_MEDICIONES.md](PVP_MEDICIONES.md). Todo es lectura del exe (`exe/EDA_limpio.exe`, md5 0799387e; dirección =
> 0x400000 + offset del archivo), de `Data.dat` (extraído con `traduccion/herramientas/desempacar_data_dat.py`) y del
> código del repo. ✅ = visto en el código/datos · 🟡 = deducción · ❌ = buscado y no está · ⏳ = hay que medirlo en
> el juego. **E1 (¿un jugador daña a otro?) y E2 (¿qué lleva el UDP del combate?) siguen sin medir**: todo lo que
> dependa de ellos está marcado.

## 0 · En una línea

El juego ya trae casi todas las piezas de una arena — apariciones por marcador, teletransporte, temporizadores,
mensajes en pantalla, conteo de vivos, fin de stage, animaciones de victoria/derrota — y la `d3d9.dll` **ya puede
reemplazar en memoria el guion y el XML de un escenario sin tocar `Data.dat`**. Lo que no se sabe es si el motor
deja que un jugador dañe a otro (E1). Por eso la recomendación es **A (server árbitro) ahora, B (extensión de
cliente) sólo si E1/E2 lo justifican, y C no se plantea** hasta tener esa evidencia.

---

## 1 · Recursos propios sin tocar `Data.dat` (la infraestructura de la dll)

✅ `herramientas/dll_d3d9/eda_traduccion.c`:

- **Un solo punto de paso.** Toda lectura de `Data.dat` — XML, texturas HGE, **Lua** y el motor 3D — pasa por 7
  funciones de EldoS SolFS (`SolFSOpenFile 0x7FA410`, `ReadFile 0x7FA800`, …) llamadas desde 16 sitios (l.7-18). La
  dll reescribe esos 16 `call` (l.875-886) **después** de verificar los 7 prólogos y las 16 llamadas (l.850-865); si
  uno no coincide, no toca nada.
- **El orden** (`tr_mi_open`, l.464-508): (1) archivo suelto `<carpeta de la dll>\traducciones\<idioma>\<ruta>`;
  (2) archivo embebido en la dll (`eda_traduccion_datos.h`); (3) `Data.dat`.
- **El embebido** lo genera `compilar.py` desde `traduccion/<idioma>/**` (`traduccion_archivos`,
  `generar_traduccion_header`, `compilar.py:184-253`); el CI lo hace con `--generar-traduccion`.
- **El límite:** todo depende del idioma. `tr_mi_open` sólo redirige con `g_tr_idioma[0]` (l.467) y `tr_instalar`
  no engancha nada con `idioma=off/en/vacío` o `[general] mejoras=0` (l.815-824). El idioma por defecto es `es`
  (`tr_leer_ini`, l.410), así que hoy está prendido para todos.

**Consecuencia práctica (✅ sin cambiar código):** en las carpetas de prueba de `dos_clientes.py`
(`EDA_pvp\A` y `\B`) un guion de arena se puede servir como archivo suelto en
`traducciones\es\data\scenario\easy\chapter1_1_e.lua` (y su `.xml`). Sólo esas dos instalaciones lo ven: el PvE de
los jugadores no cambia. ⏳ Falta probar que un `.lua` suelto se carga igual que uno de `Data.dat` (los `.lua` sí pasan
por la capa VFS según l.8-9, pero ningún `.lua` se redirigió todavía en una prueba).

**El cambio mínimo para un canal propio (no implementado):** una segunda raíz `pvp\<ruta>` consultada **antes** de
`traducciones\<idioma>\` en `tr_mi_open`, y que `tr_instalar` enganche si existe esa carpeta aunque el idioma esté
apagado (hoy sale en l.820). Unas 30 líneas en el mismo archivo, con su prueba en `prueba_traduccion.c`. Sirve para
separar lo experimental de la traducción; para repartir una arena a todos haría falta embeberla como hoy se embebe
`traduccion/es/` (y subir la VERSION de la dll, regla de `LEEME.md` de la dll).

## 2 · El escenario 1011 y la API Lua

### 2.1 · Los archivos (✅ `Data.dat`)

`data/scenario/easy/chapter1_1_e.xml`:

```xml
<STRINGID NAME="1011" … BRIEFING="1011"/>
<CLEAR_TYPE MAIN="1" DATA="1" DATA2="0" SUB="0"/>
<RANKRATE S="0.8" A="0.6" B="0.4" C="0.2" D="0.1"/>
<INFO RANK_POINT="29" KILL_POINT="120" TOTALEXP="128" MONSTER_CNT="56"/>
<SCRIPT PATH="Data\Scenario\Easy\Chapter1_1_E.lua"/>
<MAP PATH="Maps\Chapter1\Chapter1_1.dat"/>
<STAGEREWARD Index="1011"/>
<CONDITION TYPE="0" NUM="0"><SCENARIO ID="0"/></CONDITION>
```

`MAXPLAYER` **no** está en el XML del escenario: está en el índice (`data/scenariolist.xml`, l.7: `ID="1011" …
PATH="Data\Scenario\Easy\Chapter1_1_E.xml" MINIMAP="…" MAXPLAYER="3"`). ❌ No hay posiciones de inicio en el XML.

`chapter1_1_e.lua` (467 líneas): `Initialize` → `scenario:InitPlayGame("Player Start")` +
`InsertFunction("Briefing_01", 0)` (l.145-149); `Briefing_01` → mensaje del operador y `OnStart` a los 6,5 s; `OnStart`
arma los disparadores (`OnTrigger_01` a 1 s, `OnSwitch_01`, `DoorSwitch_01..03`); los NPC salen con
`CreateNpcDelayed(grupo, 2, tipos, niveles, marcas, ia, marcadores, tiempos)` (l.232); las puertas abren con
`MoveMapObjectByForward("DoorL01", true)` al entrar a un marcador (`IsEnterMarker("DoorM01", 500)`, l.188); al final
`OnSwitch_09` → `InsertFunction("OnEnd", 5000)` → `scenario:SendEvent()` (l.457-466), que es el `0x1064` del máster
(PROTOCOLO §5.13).

**Cómo corre el guion:** `InsertFunction(nombre, ms)` agenda una función; si devuelve 0 se vuelve a llamar (es el
«mientras»: `DoorSwitch_01` devuelve 0 hasta que alguien entra al marcador). ⇒ hay **temporizadores y
sondeo** sin código nuevo.

### 2.2 · Dónde aparecen los jugadores

- ✅ En **marcadores del mapa** de LithTech, por nombre: `InitPlayGame("Player Start")` en 1011; en otros
  `InitPlayGame(tmppos[RandomData.value])` con `tmppos = {"LSP", "KSP", "TSP"}` (p. ej. `chapter1_15_e.lua:32`).
  Contados en los 196 `.lua`: «Player Start» 15, «KSP» 13, «TSP» 13, «MSP» 13, «PSP» 12, «PPS» 3, y 111 al azar.
- ✅ Los nombres están dentro de los `.dat`: `chapter1_1.dat` trae «Player Start», «LSP», «KSP», «TSP», «PSP» (8
  apariciones de cada uno), «BossNP» (6), «Area 01», «E_AP_01», «Event01». 🟡 Que cada grupo sean 8 puntos (uno por
  lugar) es deducción del conteo.
- ✅ **Teletransporte de jugadores**: `TeleportAllPlayers(T_marker)` en `chapter1_14_e.lua:996-1015` recorre
  `scenario:GetPlayerID(i)` (i desde 1; `nil` o `0xFFFFFFFF` = lugar vacío) y llama
  `scenario:TeleportToMarker(PlayerID, marcador)`.
- ❌ `boss_room_s.dat` **no tiene ningún marcador** (ni «Player Start» ni «BossNP» ni áreas) y ningún escenario lo usa
  (los 150 XML usan `Chapter1_1.dat` … `Chapter1_10.dat`). Sin editar el mapa no sirve de arena.

### 2.3 · La API Lua de `CScenario` (✅ exe)

Registradas entre `0x64633F` y `0x647CA2` (cada una: `push "<nombre>"` en esa dirección y, unas instrucciones
después, `mov [eax], <implementación>`). Los argumentos salen **sólo** de usos reales en los `.lua`.

| función | registro | argumentos vistos | uso en la arena |
|---|---|---|---|
| `InitPlayGame` | 0x64633F | `("Player Start")`, `(tmppos[i])` | aparición inicial |
| `InsertFunction` | 0x646401 | `("OnStart", 6500)` | temporizador / sondeo |
| `SendEvent` | 0x646462 | `()` | fin de la stage → `0x1064` |
| `ShowMsg` | 0x646709 | `(1101, 4000, 0xffffffff)` (texto del archivo de cadenas del capítulo) | cuenta regresiva, ganador |
| `ShowMsgWithPlayerName` | 0x64676A | `("1304", scenario:GetData(1)…)` | «gana X» 🟡 |
| `GetAlivePlayerNum` | 0x646B34 | `()` (`chapter1_11_e.lua:344`) | detectar vivos |
| `GetDeadPlayerNum` / `GetPlayerNum` | 0x646B95 / 0x646AD3 | — (sin usos) | |
| `IsAllPlayerDead` | 0x6472C8 (impl. `0x62A810`) | — | |
| `GetPlayerDamage` | 0x646C57 | — (sin usos) | ⏳ ¿daño por jugador? |
| `GetPlayerID` / `GetLocalPlayerID` | 0x646D19 / 0x646CB8 | `(i)` / `()` | quién es quién |
| `TeleportToMarker` | 0x6466A8 (impl. `0x637BF0`) | `(PlayerID, "LSP")`, `(T_BossID, "BossNP 04")` | separar a los dos |
| `GetInAreaPlayers` / `IsInAreaAllPlayers` / `IsInAreaPlayers` | 0x646DDB / 0x646F5F / 0x647082 | `("Area 03")` → `.size` | límites |
| `IsEnterMarker` | 0x647267 | `("DoorM01", 500)` | límites por radio |
| `KillEntity` / `KillAllPlayer` | 0x64694F / 0x6468EE | — (sin usos) | ⏳ fuera de límites |
| `GetTimer` | 0x6469B0 | — | |
| `GetCurRank` | 0x646A72 | — | |
| `SetEntityGroup` | 0x6479FB (impl. `0x6385F0`) | — (sin usos) | 🟡 ver §2.4 |
| `CreateNpc`, `IsNpcGroupDead`, `MoveMapObject*`, `ShowBossHPBar`, minimapa… | 0x646647 … | | (PvE) |

`manager:` (del objeto de entidades): `GetHP` (291 usos), `GetPosition`, `GetEntityType`, `UpdatedHP`, `UpdatedMP`,
`SetFallDownRate`, `AddDebuff`.

⚠ **Sólo el máster ejecuta lo que cambia el mundo**: `TeleportToMarker` (`0x637C25`) y `SetEntityGroup`
(`0x63861E`) miran `byte [obj+0x168]` — la misma bandera de máster de `servidor/partida.py:611-618` — y propagan con un
mensaje de red (`0x533310`). 🟡 El guion corre en todos los clientes; los efectos los da el máster.

### 2.4 · Lo que el motor sabe del combate (✅, relevante para E1)

- `eEntityType` (registrado en `0x56CBD5`): **`Player`, `Npc`, `MapObject`, `Camera`**. ❌ No hay «equipo»,
  «bando» ni «aliado».
- `DamageType` (`0x56C9DE`): `Swing`, `Shoot`, `ZoneAttack`, …, `DamageOverTime`.
- El guion de cada clase (`data/entityscript/player/warrior.lua`, `hunter.lua`) recibe los golpes:
  `OnDamaged(entityID, damage, guard, pos, hitPoint, hitDirection, critical, damageType)` (l.180; efecto
  `Blood_Player`), `OnAttacked(entityID, animationID, …)` (l.198), `OnStateSync(Recv)` («al recibir el paquete de
  sincronización», l.157-158), `OnDeath`, `OnDead`, `OnRebirth` (l.243: `SetHP(GetMaxHP())`,
  `SetMP(GetMaxMP())`). Las acciones incluyen `Win` = `Win_Player` y `Lose` (l.21-22). `hunter.lua:259` distingue
  objetivos con `manager:GetEntityType(entityID) == eEntityType.MapObject`.
- 🟡 Estos callbacks **reaccionan** al golpe (efectos, sonido): quién decide si un golpe pega lo decide el C++. Que
  `OnDamaged` traiga el `entityID` del atacante es lo que dejaría, en B, saber quién le pegó a quién.
- 🟡 `SetEntityGroup(entidad, grupo)` arma un mensaje de red de tipo `0x1B` con la entidad y el grupo (`0x638667`).
  Ningún guion lo usa. Es el único candidato visto a «bando»; ⏳ hay que medir qué cambia (p. ej. si dos jugadores
  en grupos distintos pasan a ser objetivo uno del otro).

## 3 · Cómo se eligen los escenarios

- ✅ `data/scenariolist.xml` es el índice: `CHAPTERS MESSAGE=…Chapter1_string.xml` y tres `SCENARIOS NUM="50"` (Easy,
  Normal, Hard). Cada `SCENARIO` da `ID`, `ICON`, `PATH`, `MINIMAP`, `MAXPLAYER`. Lo lee `0x64CEC8`…`0x64D42E`
  (`SCENARIOLISTXML`, `CHAPTERS`, `SCENARIOS`, `MAXPLAYER`…). El selector habilita cada uno según su `CONDITION` y la
  lista de terminados del `0x1018` (PROTOCOLO §5.7, §6).
- ✅ El server **no** tiene la lista: copia el escenario que manda el cliente en la sala (`+0x28`,
  `servidor/salas.py:901-924`) y busca sus números en `servidor/escenarios.json` (`datos.py:17`).
- **Reemplazar vs. agregar:** reemplazar los archivos de un ID existente (§1) no toca el índice, el selector ni el
  server: es lo seguro para la arena experimental. Agregar un ID nuevo exige reemplazar también
  `scenariolist.xml`; ⏳ no se sabe si el selector dibuja un 51.º marcador (el mapa del capítulo tiene 50 posiciones
  fijas). No se recomienda para el prototipo.
- **El mapa de la arena: `Chapter1_1.dat`** (el de 1011): tiene «Player Start», `LSP`, `KSP`, `TSP`, `PSP` y
  `BossNP` (§2.2), es la stage que ya usa `dos_clientes.py llevar`, y sus puertas sólo abren por guion (§2.1): sin
  `DoorSwitch_*` la zona de inicio queda cerrada. 🟡 Si eso alcanza como «ring» hay que verlo en el juego.

## 4 · La arena experimental

> ★ (25-nov) Implementada y medida: el estado al día de cada fila está en `herramientas/pvp/arena/LEEME.md`.
> Resuelto desde esta tabla: las dos apariciones (04/08, y por equipo), `ShowMsg` con índices nuevos (1180–1190),
> el bloqueo durante la cuenta (los grupos se cambian al terminarla: con el mismo grupo no hay daño, T01),
> `GetHP` con jugadores y el fin por tiempo (empate en el server). Siguen a mano: los límites, la vida al volver y
> el 2 vs 2.

Guion de arena = un `chapter1_1_e.lua` propio servido por la dll **sólo en las instalaciones de prueba**, y el
server en «modo duelo» para esa sala.

| requisito | pieza real que lo haría | estado |
|---|---|---|
| dos apariciones | `InitPlayGame("Player Start")` y, desde el máster, `TeleportToMarker(GetPlayerID(1), "LSP")` / `(GetPlayerID(2), "KSP")` (patrón de `TeleportAllPlayers`) | ⏳ que `LSP`/`KSP` de este mapa queden separados |
| sin monstruos | el guion no llama `CreateNpc*` ni los `OnTrigger_*` | ✅ (es sólo no llamarlos) |
| cuenta regresiva | `InsertFunction` cada 1000 ms + `ShowMsg(n, 900, color)`; textos nuevos en `chapter1_string.xml` servido igual que el `.lua` | ⏳ que `ShowMsg` acepte índices nuevos |
| bloqueo durante la cuenta | 🟡 sin API vista para congelar jugadores; alternativa: aparecer separados por una puerta y abrirla al final con `MoveMapObjectByForward` | ⏳ |
| límites | puertas cerradas (no se llama `DoorSwitch_*`); `IsInAreaPlayers("Area 01")` + `KillEntity` si alguien sale | ⏳ `KillEntity` sin usos en 2009 |
| detección de vivos | `GetAlivePlayerNum()` sondeado con `InsertFunction`; en el server, cada `0x1065` | ⏳ que la muerte por otro jugador cuente (E1) |
| fin del duelo | guion: con 1 vivo → `SendEvent()` (el `0x1064` del máster). Server: `fin_de_stage` en modo duelo arma el resultado | ✅ el camino del `0x1064` ya existe |
| ganador | server: el que no mandó `0x1065`; aviso por chat (`0x100D`) y en `0x106E` (rango, tiempo) | 🟡 diseño |
| muerte sin revivir | server en modo duelo **no** manda el `0x1068`: sin él el muerto queda tirado (medido, PROTOCOLO §5.12); o `0x1069` = espectador | ✅ comportamiento medido en PvE |
| desconexiones | `cerrada()` → `_sacar_de_sala` (`salas.py:303-338`): en modo duelo, el que queda gana; `vigilar_master` / `vigilar_stage_trabada` como hoy | 🟡 diseño |
| restauración | la vida/MP se rehacen al cargar la stage siguiente y `OnRebirth` llena HP/MP; la cuenta no pierde monedas ni EXP (el server no descuenta en duelo) | ⏳ que la vida vuelva llena al volver a la sala |
| vuelta al lobby | el camino medido: `0x1073` → `0x106E` → cartas → premios → sala (PROTOCOLO §5.14); o `0x1075` desde la partida. ⚠ Nunca `0x1075` en AWARD RESULTS (cae en `0x752B7E`) | ✅ medido en PvE |

**Marcar la sala como duelo (server):** ningún byte de la sala significa «modo» (PVP_INVESTIGACION.md §6). Opciones:
un comando de chat del anfitrión (`/duelo`, como los de GM de `salas.py:477`) o un prefijo en el título. Con el
escenario 1011 reemplazado, el server tiene que saber que esa sala es duelo para no dar los premios de 1011.

## 5 · Las tres arquitecturas

### A · Server árbitro con el protocolo original

- **Qué es:** el combate sigue P2P como en 2009. El server decide sala, inicio, fin, ganador, premios y ranking con
  lo que ya recibe (`0x1065`, `0x1064`, `0x1074`, desconexiones) y descarta lo incoherente (muerte sin partida,
  ganador que no estaba, fin antes de la cuenta).
- **Requisitos:** E1 = sí (que los jugadores se puedan dañar). Si E1 = no, A sola no alcanza.
- **Coste:** bajo. `servidor/pvp.py` ramificado desde los manejadores actuales (`registro.py:15` no deja registrar
  dos veces un comando) + el guion de arena (§4) + pruebas.
- **Riesgos:** un cliente modificado puede mentir su muerte o no mandarla. El `u32` «quién lo mató» del `0x1065`
  (🟡 `0x108` = el monstruo) ⏳ tendría que traer al otro jugador para saber quién mató a quién; si no, sólo «quién
  quedó vivo».
- **Compatibilidad PvE:** total (todo detrás de `s["modo"] == "duelo"`).

### B · Híbrida: extensión del cliente en la `d3d9.dll`

- **Qué es:** la dll (que ya engancha el exe en memoria con verificación previa) agrega lo que falte: (a) si E1 = no,
  hacer que un `Player` sea objetivo válido para otro `Player` (el filtro, cuando se encuentre); (b) reportar al
  server cada golpe entre jugadores (atacante, víctima, daño, hora), por ejemplo desde un gancho que ve lo mismo que
  `OnDamaged`.
- **Cómo podría reportar:** (1) **el chat** (`0x100D`): ya llega al server en orden y por la conexión autenticada;
  el server lo intercepta antes de difundirlo (hoy lo hace con `/comandos`). Coste bajo, latencia de TCP; ⚠ hay que
  evitar que se vea en el chat de los demás. (2) **El canal de diagnóstico** (`eda_diag.c` → `POST /eda/diag`,
  firmado con HMAC derivado del ticket): sólo en TEST, lotes cada 10 s, ≤ 64 KB: **no sirve para tiempo real**, sí
  para registrar duelos y estudiarlos. (3) Un mensaje TCP nuevo: el server lo recibe sin problema, pero no hay
  comando libre conocido del lado del cliente y armarlo dentro del cifrado del juego cuesta más.
- **Requisitos:** E1/E2 medidos, y la dirección del código de daño (con `vida.py` como ancla: un punto de ruptura
  sobre la escritura de la vida lleva a quien la escribe).
- **Coste:** medio-alto (ingeniería inversa del daño y del objetivo; cada parche con su verificación y su prueba,
  regla de `POR_QUE_LA_DLL.md`; versión nueva de la dll).
- **Riesgos:** los dos jugadores tienen que tener la misma dll; un cambio de comportamiento del combate entra
  también en PvE si no se limita a la arena (se limita con la bandera de modo).

### C · Combate validado por el server

- **Qué es:** el server decide cada golpe (o al menos lo valida antes de que cuente).
- **Requisitos:** saber qué viaja en el UDP del combate (E2) y que el server lo vea: hoy el relay lo reenvía sin
  interpretarlo (`herramientas/relay_udp.py`) y en «directo» ni pasa por el server. Además, mover la decisión del
  daño del cliente al server exigiría cambiar el motor de combate del cliente.
- **Coste:** alto y sin cota: no hay evidencia de que el cliente acepte un daño que no calculó él.
- **Evidencia que falta:** E1, E2, el formato del UDP de LithTech, cómo llega el daño de un remoto (¿`OnStateSync`?).
- **Recomendación:** no planificarla. Si B anda, C se puede evaluar como «B + validación más estricta en el
  relay» (forzar `EDA_P2P=relay` en salas de duelo para que todo pase por el server), sin prometerla antes.

### Resumen

| | A | B | C |
|---|---|---|---|
| depende de E1 | sí | resuelve E1 = no | sí |
| depende de E2 | no | parcialmente | sí |
| toca el cliente | no (sólo datos servidos por la dll) | sí (código de la dll) | sí (mucho) |
| coste | bajo | medio-alto | alto, sin cota |
| anti-trampa | débil | media | fuerte |

## 6 · Plan del prototipo 1 vs 1

Cada paso se da por hecho sólo con su prueba en `servidor/pruebas.py` (con su caso al revés) **y** con dos clientes
reales (`herramientas/pvp/dos_clientes.py`). Nada del PvE cambia mientras `s["modo"]` no sea `"duelo"`.

1. **Medir E1** (PVP_MEDICIONES.md §2). Puerta: con E1 = sí, seguir con A; con E1 = no, primero B(a).
2. **Arena servida por la dll (experimental):** `chapter1_1_e.lua` sin monstruos, con `InitPlayGame` + dos
   `TeleportToMarker`, en `EDA_pvp\A|B\traducciones\es\…`. Verificar con dos clientes: aparecen separados, sin NPC,
   con las puertas cerradas. Revés: sin el archivo suelto, 1011 es la de siempre.
3. **Cuenta regresiva y fin en el guion:** `InsertFunction` + `ShowMsg` con textos propios; `GetAlivePlayerNum()`
   == 1 → `SendEvent()`. Verificar que el `0x1064` llega del máster al morir uno.
4. **Modo duelo en el server** (`servidor/pvp.py`): `/duelo` marca la sala (máx. 2); `murio` en duelo no manda
   `0x1068`; `fin_de_stage` en duelo arma el resultado sin `StageReward`; la desconexión da la victoria al otro.
   Pruebas con las conexiones falsas de `pruebas_multijugador` (`pruebas.py:1272`): duelo normal, empate por
   desconexión de los dos, y los reveses (una sala normal con los mismos mensajes sigue igual que hoy).
5. **Ranking:** campos nuevos con valor por defecto en la cuenta (`cuentas.py`); prueba de que una cuenta vieja carga.
6. **Dos clientes reales**: el ciclo completo cinco veces seguidas (sala → duelo → ganador → sala → otro duelo), con
   `vida.py` y `udp_combate.py` grabando; recién ahí se marca «duelo funcionando» en la matriz.
7. **Para repartir** (fuera del prototipo): el canal `pvp\` de la dll (§1), el guion embebido, versión nueva de la
   dll, y el server de prueba (35900) antes de prod.
