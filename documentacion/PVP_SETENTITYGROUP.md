# SetEntityGroup — qué es y si sirve para el PvP (análisis estático)

> Rama `feature/pvp-system`. Todo sale de `exe/EDA_limpio.exe` (md5 0799387e, base `0x400000`) desensamblado con
> capstone y de los `.lua` de `Data.dat`. Las direcciones son VA. ✅ = verificado en el código · 🟡 = deducción ·
> ❌ = buscado y no encontrado · ⏳ = falta probarlo con el juego andando. **Nada de esto prueba todavía que haya
> PvP: es la hipótesis con más evidencia, para las pruebas T04–T06 de [PVP_PROTOTIPO.md](PVP_PROTOTIPO.md).**

## 0 · En una línea

El juego **filtra cada golpe por grupo**. Todas las entidades llevan una máscara de bits en `entidad+0x40`, y los
golpes se descartan cuando atacante y víctima comparten un bit. Todos los jugadores se crean con la máscara
`0x1` y los NPC de los guiones con el grupo 2 (máscara `0x2`). ⇒ 🟡 **dos jugadores no se pueden dañar porque
están en el mismo grupo.** `scenario:SetEntityGroup(id, g)` cambia esa máscara y la **replica a los demás
clientes** por el TCP del server (`0x105C` → `0x105D`).

## 1 · La función

### 1.1 · Registro en Lua ✅

`CScenario` registra sus 71 funciones en `0x645800..0x648800` con el mismo molde:
`lua_pushstring(nombre)` (`0x7B4AC0`) → `lua_newuserdata(4)` (`0x7B55D0`) con el puntero a la función C++ →
`lua_pushcclosure(despachador, 1)` (`0x7B4B90`) → `lua_settable(-3)` (`0x7B4F80`). Para SetEntityGroup:

```
0x6479FB  push 0x89EAC8            ; "SetEntityGroup"
0x647A15  mov dword [eax], 0x6385F0 ; la función C++
0x647A1D  push 0x62F820            ; el despachador
```

### 1.2 · Firma ✅

El despachador `0x62F820` (el mismo de `ShowBossHPBar`, `scenario:ShowBossHPBar(NpcID, 3)` en `chapter1_10_e.lua:824`):
toma la función del upvalue 1 (`0x7B4950(L, -10003)`), exige que el argumento 1 sea el objeto (`0x7B4680`, si no
lanza el error de `0x89AA48`) y lee **los argumentos 2 y 3 con `lua_tonumber` (`0x7B4790`: tipo 3 = número)
pasados a entero (`_ftol`, `0x7DDC18`)**. Después llama a `0x6385F0` como `thiscall`.

```lua
scenario:SetEntityGroup(idEntidad, grupo)   -- dos números; se llama con «:» (el objeto va primero)
```

### 1.3 · Qué hace `CScenario::SetEntityGroup` (`0x6385F0`) ✅

```
0x63861E  mov al, [esi+0x168] ; test ; je fin  → SÓLO EL MÁSTER (la misma bandera que SendEvent/0x1064 y que
                                                  TeleportToMarker); en los demás no hace nada
0x63863E  CEntityManager (0x9348C8)::SetGroupById(id, grupo)  = 0x570A30
             → busca la entidad por ID (0x5706D0); si no existe devuelve 0 y NO se manda nada
             → CEntity::SetGroup(grupo) = 0x560CD0
0x638667  arma un paquete: u32 0x1B · u32 id · u32 grupo   (0x743640 / 0x7437D0 escriben 4 B cada uno)
0x638698  se lo da al delegado CScenario+0x688 → 0x5472E0 (lo ata 0x5139AA)
```

`0x5472E0` lo manda **al server por TCP como `0x105C`** (`0x547303 push 0x105C`), también sólo si el máster tiene
su bandera `+0x168`. Es el mismo camino que los demás eventos del guion (puertas, grupos de NPC).

### 1.4 · `CEntity::SetGroup` (`0x560CD0`) y `GetGroup` (`0x560CF0`) ✅

```
0x560CD4  cmp eax, 1 ; jl fin
0x560CDB  cmp eax, 0x20 ; jg fin            → el grupo va de 1 a 32; fuera de eso no cambia nada
0x560CE8  shl eax, cl (cl = grupo-1)
0x560CEA  mov [edx+0x40], eax               → entidad+0x40 = 1 << (grupo-1)
```

`GetGroup` hace lo inverso (máscara → número). Los dos también están en la clase Lua `CEntity` como
`this:SetGroup(g)` / `this:GetGroup()` (`0x56ACC4` / `0x56ACD7`), pero **esa versión es sólo local: no manda
nada**. ❌ Ningún `.lua` de `Data.dat` usa `SetGroup`, `GetGroup` ni `SetEntityGroup`.

## 2 · Sincronización entre clientes ✅ (estático) · ⏳ (en vivo)

| quién | qué |
|---|---|
| máster | `SetEntityGroup` → aplica local → `0x105C` (TCP) con `[0x1B][id][grupo]` |
| server | `servidor/partida.py` `evento_guion_escenario`: reenvía el cuerpo del `0x105C` como `0x105D` a los demás que siguen en la stage (no lo cambia la rama `fix/validar-0x1062`: ésa descarta los `0x105D` que manda un cliente, no los `0x105C`) |
| los demás | `0x105D` → `0x546E60` → `0x643750`: lee el tipo (≤ 0x24) y salta por la tabla `0x644894`; **tipo 0x1B → `0x6445FE`**: lee `u32 id` (`0x742970`) y `u32 grupo` (`0x742830`) → `0x6250F0` → `0x570A30` → `SetGroup` |

⇒ el grupo queda igual en los dos juegos. Esto importa porque el que recibe un golpe por la red lo vuelve a
validar con el filtro de grupo (§3, `0x556893`): si el cambio no llegara al otro juego, éste rechazaría el golpe.

## 3 · Quién LEE la máscara (`entidad+0x40`)

En todos los casos se compara `atacante.grupo & víctima.grupo`; si da distinto de 0 (comparten un bit), el
golpe se descarta.

| función | lectura | qué es | evidencia |
|---|---|---|---|
| `0x554B70` | `0x554B8E` / `0x554B91` | ✅ **«¿puedo pegarle?» del que recibe un golpe por la red**: devuelve 0 si `+0x21D` (vivo) o `+0x27C` faltan o si comparten grupo | la llama `0x556893`, que lee el golpe de un paquete (`0x742610`, `0x742B20`) y contesta `0x400B` |
| `0x559630` | `0x5596CA` / `0x5596CD` | ✅ **daño de área**: recorre las entidades (`0x556690`), saltea las de su grupo, mide la distancia (`fsqrt`) contra el radio | |
| `0x5573B0` | `0x55758A` / `0x55758D` | ✅ **agarre (Hold)**: rayo físico (`[0x92CF50]+0x64`) → entidad viva → grupos disjuntos → no invulnerable (`0x5AFD70`) → la sujeta y manda `0x4008` | la llama el método virtual `0x55E580` (`0x55E888`) |
| `0x55E580` | `0x55EF19` / `0x55EF1C` | 🟡 método virtual de `CEntity` (vtable `0x89A968`+4) con 4 llamadores: un golpe cuerpo a cuerpo | |
| `0x55DB50`, `0x55E0D0` | `0x55DDFA`, `0x55E24E` | 🟡 ataques con efecto («24_S_Bombhhit», `Skill_BombH2.wav`): bombas/área | |
| `0x5571A0`, `0x582520`, `0x582800` | `0x557239`, `0x5826CA`, `0x58292A` | 🟡 otros barridos de entidades con el mismo filtro | |
| `0x584610`, `0x584820`, `0x5849F0`, `0x585040`, `0x585230`, `0x589FA0` | `cmp` de igualdad | 🟡 grupo IGUAL (no intersección): candidatos a la IA («¿es de los míos?») | están en tablas (`0x588DC6…`), no se llaman directo |

Escrituras: el constructor de `CEntity` lo pone en 0 (`0x56049D`); la creación lo pisa (§4); los proyectiles
copian el grupo del dueño (`0x55D262` / `0x55D265`).

## 4 · Los grupos que existen ✅

| entidad | cómo nace | máscara |
|---|---|---|
| **jugador** | `CEntityManager::Create` `0x5758A0` (6 argumentos; el **3º se escribe tal cual en `+0x40`**, `0x5758DB`). Las 9 llamadas (`0x4EA52B`, `0x4EA5D5`, `0x4F8302`, `0x4F9686`, `0x529CC6`, `0x537D61`, `0x537EAE`, `0x644D46`, `0x6454C9`) pasan **1** | `0x1` (grupo 1) |
| **NPC** | `CreateNpc` / `CreateNpcDelayed` → `0x63FA60` valida el grupo 1..32 y lo vuelve máscara (`0x63FB37 shl`) → `0x5759D0` lo escribe (`0x575A58`). **3334 llamadas en los `.lua`, todas con el grupo 2** (`scenario:CreateNpcDelayed("NpcGroup01", 2, …)`) | `0x2` (grupo 2) |
| NPC sueltos del C++ | `0x5759D0` desde `0x4EA6C6` con **2** | `0x2` |

`eEntityType` (`0x56CBD6`): `Player`, `Npc`, `MapObject`, `Camera`, `Projectile` (🟡 los números no se leyeron).
❌ No hay facción, bando ni equipo aparte del grupo.

## 5 · IDs para llamarla ✅

| función | firma | qué devuelve |
|---|---|---|
| `scenario:GetPlayerID(i)` | `0x62A9A0`, despachador `0x62F230` | el ID de entidad del jugador **número `i`** (u8, desde 0) de la lista `CScenario+0x90` (`[jugador+8]`); 0 si no hay |
| `scenario:GetLocalPlayerID()` | `0x625180` | el ID del jugador de ESTE juego (`[CScenario+0x160]+8`) |
| `this:GetIdentifier()` | `0x560C00` | `entidad+8` = el mismo ID |

✅ **Medido** (24-nov, sesión `20261124-064447`, con rui anfitrión y kai invitado): `GetPlayerID(0..4)` =
`-1, 1, -1, 0, -1`. El `i` **no** es el número de sala; un lugar vacío da **−1** (no 0), y el ID de entidad **0 es
un jugador** (rui). Para recorrerlos: `i = 0..8`, descartar −1.

## 6 · Lo que NO se encontró

- ❌ Dónde se resta la vida. `entidad+0x20C` (float, `GetHP` `0x560F20`) sólo la escriben `SetHP` (`0x560F00`) y
  `0x58B490`, que es la **sincronización por red** del estado (lee 8 B de un paquete: `m_HP`, `m_nWeaponType`;
  mensajes de entidad `0x4003..0x4017`, despachador `0x58B8F0`). 🟡 Cada juego manda la vida de SU personaje.
- `OnDamaged` del guion del jugador (`warrior.lua:180`) sólo pone efectos y sonido; no toca la vida.

## 7 · Llamada propuesta para T04 (la firma quedó verificada)

En el guion de la arena (sólo lo ejecuta el máster; los demás reciben el cambio por `0x105D`):

```lua
-- ⚠ (medido después) GetPlayerID(0) NO es rui: ver §5. La arena recorre 0..8 y toma el 2º ID válido.
scenario:SetEntityGroup(<id de un jugador>, 3)   -- máscara 0x4; el otro sigue en 0x1, los NPC en 0x2
```

Se usa el **3** y no el 2: con el 2, kai quedaría del lado de los NPC (ni ellos a él ni él a ellos).
Qué tiene que pasar si la hipótesis es correcta: con `GetGroup` (`this:GetGroup()` o leyendo `+0x40`) los dos
juegos dicen 4 para kai, y los golpes entre rui y kai **se aplican** (vida que baja en `vida.py`, `OnDamaged`).
Si no se aplican, el filtro no era el único y lo siguiente es seguir `0x554B70` / `0x55E580` en vivo.

## 8 · Puntos de enganche (Frida, sólo lectura)

| dirección | qué | qué leer |
|---|---|---|
| `0x6385F0` | `CScenario::SetEntityGroup` (thiscall) | `ecx` = escenario; `[esp+4]` = id; `[esp+8]` = grupo; `byte [ecx+0x168]` = ¿máster? |
| `0x560CD0` | `CEntity::SetGroup` | `ecx` = entidad; `[esp+4]` = grupo; al salir, `[ecx+0x40]` |
| `0x6445FE` | llegó el `0x105D` tipo 0x1B (el otro juego aplica el grupo) | después de `0x644611`: `[esp+0x10]` = id, `[esp+0x20]` = grupo |
| `0x5472E0` | sale un `0x105C` (evento del guion) | `[esp+4]` = el paquete |
| `0x554B70` | ¿se acepta un golpe que llegó por la red? (5 argumentos, `ret 0x14`) | `ecx` = la entidad; `[esp+4]` al entrar = la otra entidad; **valor de retorno `al`** |
| `0x5596CA` | filtro del daño de área | `esi` = candidato, `edi` = atacante; `[esi+0x40]`, `[edi+0x40]`, si salta en `0x5596D0` |
| `0x55758A` | filtro del agarre | `eax` = objetivo, `edi` = atacante |
| `0x559940` | despacho al `OnDamaged` del guion (virtual, `CEntity`) | `ecx` = la entidad golpeada (`[ecx+8]` id, `[ecx+0x20C]` vida); 7 argumentos (los del `OnDamaged` de Lua) |
| `0x58B4C4` | llega por red la vida de otro (`+0x20C`) | `eax` = entidad, `ecx` = la vida nueva (float) |
| `0x560F00` | `SetHP` | `ecx` = entidad, `[esp+4]` = vida |
| `0x55707D` | muerte (`+0x21D = 0`) | `esi` = entidad (`[esi+8]` id) |
| `0x55493D` | vuelve a vivir (`+0x21D = 1`) | `esi` = entidad |

Campos de `CEntity` usados: `+4` tipo · `+8` id · `+0x40` máscara de grupo · `+0x20C` vida (float) · `+0x21D` vivo ·
`+0x21F` invulnerable · `+0x168` objeto LithTech.

## 9 · Medido en vivo (24-nov) — `herramientas/pvp/entidades.py`, dos clientes, la arena con `--grupos`

- ✅ Los 10 puntos de §8 se engancharon en los dos juegos (bytes verificados contra el exe).
- ✅ `SetEntityGroup(1, 3)` llega a `0x6385F0` con `máster = 1` **en los dos clientes** (los dos corren el guion) y
  `SetGroup` deja la entidad 1 (kai) con máscara `0x4` en A y en B; el paquete `1b000000 01000000 03000000` pasó por
  el server (`0x105C` → `0x105D`).
- ✅ Con kai en `0x4` y rui en `0x1`, **los golpes entre los dos se aplican**: `OnDamaged` (`0x559940`) en los dos
  clientes con la víctima, el atacante (el 1er argumento es un puntero a la entidad que pega) y el daño (2º argumento,
  float: 15.6 … 22.2); la vida (`+0x20C`) baja igual en los dos (`0x58B4C4` la trae por red); muerte (`0x55707D`) en
  los dos; el server recibe `0x1065` con el atacante. Detalle en PVP_PROTOTIPO.md §0.
- ⚠ Ninguno de los filtros enganchados (`0x554B70`, `0x5596CA`, `0x55758A`) se llamó con los golpes cuerpo a cuerpo,
  ni con grupos iguales ni distintos: el test que decide el golpe cuerpo a cuerpo es otro (sin ubicar).
- ⛔→✅ Los DOS clientes corren el guion y cada uno ordena los IDs distinto: si cada uno cambia «el segundo», los dos
  jugadores terminan en el mismo grupo (sesión `-074413`). La arena ahora ordena los IDs y asigna los dos grupos
  explícitamente (sesión `-074909`: rui `0x1`, kai `0x4` en los dos).
- ✅ El control negativo (24-nov, sesión `20261124-070421`): la misma arena **sin** `SetEntityGroup`, golpes a mano
  de los dos lados → cero `OnDamaged`, vida llena. ⇒ **la máscara `+0x40` es lo que decide si un jugador daña a otro.**
