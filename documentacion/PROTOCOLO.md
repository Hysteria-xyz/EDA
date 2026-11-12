# El protocolo de EDA, medido — del Broker al lobby

> Todo lo que hay acá salió de **medir** el cliente de 2009 andando (corridas 15 y 16 de
> `MEDICIONES.md`): bytes capturados con `herramientas/espiar_broker.py`, breakpoints en el
> propio exe con `herramientas/espiar_cripto.py`, y la pantalla con `herramientas/foto_juego.py`.
> Lo que es deducción está marcado 🟡. Es la base para escribir el server.
>
> La implementación de referencia, hoy: `herramientas/paquete_broker.py` (abrir/armar) y
> `herramientas/reglas_broker.py` (lo que se contesta a cada mensaje). Con eso el cliente llega
> al lobby con un personaje.

---

## 1 · Dónde se conecta

- **Broker**: `218.145.66.187:25000` TCP. Sale de un XML comprimido dentro de `Data.dat`:
  `<SERVER><ITEM IP="218.145.66.187" PORT="25000" SERVICE="12"/></SERVER>`.
- **Server de juego**: la IP:puerto que el Broker pone en la lista de servidores (§4.4). Al
  apretar ENTER el cliente cierra el Broker y abre una conexión TCP nueva ahí.
- **UDP**: el cliente escucha en 57654 (LithTech). Hasta el lobby sólo se usa para medir el NAT.

## 2 · El paquete (TCP)

```
┌─────────── cabecera, 8 bytes, EN CLARO ───────────┐┌──── cifrado ────┐
│ u16 largo │ u8 0 │ u8 servicio │ u16 largo cifrado │ u16 modo ││ AES-128-ECB      │
│ total − 4 │      │ 12 = Broker │ múltiplo de 16    │ 0x0202   ││                  │
└───────────┴──────┴─────────────┴───────────────────┴──────────┘└──────────────────┘
```

- **Cada bloque de 16 bytes cifrado** = `B6 A2 C2 A5` (la constante `0xA5C2A2B6`) + **12 bytes de
  datos**. Por eso el cliente redondea a múltiplos de 12.
- **Los datos** = `[u16 largo = datos − 4][u16 comando][cuerpo]`. Lo que sobra hasta múltiplo de
  12 es relleno (el cliente manda basura de la pila: no importa qué).
- **Modo** (lo que en la corrida 15 llamamos «versión»): `0x0201` / **`0x0202` = AES** /
  `0x0203` = un RSA de juguete (`n = 181·29`, semilla fija `0x2A4`). Todo lo medido va en 0x0202.
- ⚠ **Servicio**: con el Broker es `0x0C` = 12 (el `SERVICE` del XML). Con el server de juego
  es el byte `+0x31` del registro del servidor elegido. **El cliente DESCARTA todo paquete cuyo
  servicio no coincide** (`0x744910`). El server contesta con el mismo que recibió.

### ★ La clave AES = MD5(el exe del cliente + un byte 0x00)

`0x624990` abre el propio exe, lo lee entero en un buffer de **tamaño + 1** y le saca el MD5
(el byte de más queda en cero). Es un **control de integridad**: cada exe tiene su clave, y un
exe tocado no se entiende con el server. Medido con dos exes distintos (`paquete_broker.py
control` lo verifica). Si el exe no se puede leer, usa `7b210ddf49170c85857b7b67c1177b7a`.

- 🟡 Para el `EDA.exe` original de 2009 sería `a57ca836788301a9aff975159cbcbe97`.
- ⇒ el server prueba las claves de los exes que conoce: la magia de cada bloque dice cuál es.
- El cliente además **manda el MD5 de su exe (sin el 00) en texto** en el `0x100F` (§5.1).

## 3 · El orden de una sesión

```
── Broker (servicio 12) ─────────────────────────────────────────────────────────────
C→B 0x0604  huella del equipo                    B→C 0x0607  dónde medir el NAT (UDP)
C→B UDP 0x3002 cada 0,4 s (en claro)             B→C 0x0609  el tipo de NAT
C→B 0x0708  pide el anuncio                      B→C 0x0709  el anuncio
C→B 0x070A  pide la lista de servidores          B→C 0x070B  la lista
   [ENTER: cierra el Broker y conecta al server elegido]
── Server de juego (servicio = +0x31 del registro) ────────────────────────────────────
C→S 0x100F  quién soy (IP, MAC, md5 del exe)     S→C 0x1010  OK → pantalla SELECT CHARACTER
C→S 0x1001  «estoy vivo», cada 20 s              S→C 0x1001  (🟡 eco)
C→S 0x1011  pide la cuenta                       S→C 0x1012  la cuenta y sus personajes
C→S 0x1013  crear personaje                      S→C 0x1014  el personaje creado
C→S 0x1017  entrar al lobby                      S→C 0x1018  OK → pantalla LOBBY
```

⚠ **No hay usuario ni clave en ningún mensaje.** La cuenta la daba el launcher (`NyxLauncher`,
`IsLobbyLaunched` / `GetLobbyLaunchInfo` / `-cmdfile`). 🟡 El server la tendría que deducir de
otra cosa, o hay que fabricar ese archivo.

Cómo despacha el cliente: el ruteador (`0x4E5690`) manda `0x1003..0x100B` a un objeto y **todo lo
demás a la pantalla actual**, que tiene un mapa comando → manejador. Un comando que la pantalla
no registró se ignora en silencio.

## 4 · Broker

### 4.1 · `0x0604` C→B — la huella (44 B de datos)
40 bytes de texto UTF-16, armados en `0x545360` desde `0x623E60()+0xF0`. Contiene trozos de una
MAC del equipo, en parte alterados (🟡 una huella de hardware). Bajo depurador sale distinto.

### 4.2 · `0x0607` B→C — `OnPktB2CNATTYPEInit` (6 B)
`u32 IP · u16 puerto` del «UDP label», **en orden de host** (el cliente les hace `ntohl`/`ntohs`).
El cliente le manda ahí, por UDP y cada 0,4 s, `[u16 0x2E][u16 0x3002]` + la huella (40) +
`u32 IP local · u16 puerto local` (en claro, sin cifrar). Si en ~4 s no llega el 0x0609, manda
`0x060C` (el camino de NAT bloqueado), que espera `0x060B` «RECONFIRM BROKER IP,PORT».

### 4.3 · `0x0609` B→C — el tipo de NAT (10 B)
`u8 tipo` (1 public, 2 Full Cone, 3 IP Restricted, 4 Port Restricted, 5 Symmetric, 6 Unknown,
8 Block; >8 = error) · 3 de relleno · `u32 IP pública` · `u16 puerto público` (orden de host).

### 4.4 · `0x0709` B→C — el anuncio (449 B)
`u8 hay anuncio` + 448: `u32 🟡 · título UTF-16[40 bytes] · u32 🟡 · cuerpo UTF-16[400 bytes]`.
Con el primer byte en 0, el panel NOTICE queda vacío.

### 4.5 · `0x070B` B→C — la lista de servidores
`u16 resultado (1 = OK)` · `u8 N` · N × 96 bytes:

| offset | qué |
|---|---|
| `+0x03` | **nombre**, UTF-16, 40 bytes |
| `+0x2B` u32 | **IP del server de juego, en orden de RED** (`inet_ntoa` directo) ⚠ distinto del 0x0607 |
| `+0x2F` u16 | **puerto**, en orden de host |
| `+0x31` u8 | **servicio** de ese server (va en la cabecera; ver §2) |
| `+0x33` u16 / `+0x35` u16 | **máximo / jugadores** → [Open] < 30 % · [Normal] < 60 % · [Busy] < lleno · [Full] |
| `+0x5F` u8 | **abierto** (con 0, ENTER muestra el error 5) |
| `+0x00`, `+0x01`, `+0x32`, `+0x37` (texto[40]) | 🟡 |

## 5 · Server de juego

### 5.1 · `0x100F` C→S — quién soy (237 B)
Lo arma `0x549940` copiando campos de la cuenta (`0x623E60()`), en lugares fijos. Desplazamientos
**del mensaje** (contando su `u16 largo · u16 comando`), medidos (MEDICIONES §39):

| mensaje | de la cuenta | qué es |
|---|---|---|
| `+0x08` (UTF-16, ≤20 car.) | `+0xF0` | ★ **el 1er dato del LAUNCHER** = el **usuario** del login (el mismo de la «huella» del `0x0604` y del UDP `0x3002`) |
| `+0x32` (UTF-16, ≤20 car.) | `+0x11A` | ★ **el 2º dato del LAUNCHER** = el **ticket** (medido con un bloque de verdad, MEDICIONES §45). ⚠ Con 20 caracteres no viene el 0 final; después del 0 hay basura |
| (UTF-16) | `+0x144` | la IP privada |
| **`+0x7E`** (UTF-16, 17 car.) | `+0x166` | ★★ **la MAC = la IDENTIDAD P2P** (la misma que va en los saludos `C354`) |
| (ASCII, 32) | `+0x1A6` | el MD5 del exe |
| `+0xDD`… | `+0x2B0` | las direcciones UDP privada y pública (§5.16) |

⚠ La MAC llega bien SÓLO si el juego se lanzó con la ruta **entre comillas** y sin bloque del
launcher (o con uno válido): ver «La línea de comandos del launcher» abajo.

#### La línea de comandos del launcher (`0x6229F0`, medido 11-nov)

Al arrancar, `0x6229F0` (método de la cuenta) primero pide la MAC a Windows (`GetAdaptersInfo`, el
1er adaptador, `"%02X:%02X:%02X:%02X:%02X:%02X"`) y la guarda en `+0x166` (UTF-16) y `+0x1C7`
(ASCII; ésta se la pasa `0x4E76AE` al «P2PHelper» como identidad). Después lee `GetCommandLineA()`:

```
"C:\ruta\EDA.exe" <BLOQUE>
   · si la línea empieza con comillas, el BLOQUE es lo que sigue a «" » (sin bloque: no hace nada)
   · ⚠ si NO empieza con comillas, toma la línea ENTERA como bloque
   BLOQUE = hexadecimal (sscanf "%02X" de a 2) → bytes XOR la MAC en texto ("AA:BB:…", en ciclo)
          = "<A> <B>"  (separados por UN espacio)  → A → cuenta+0xF0 · B → cuenta+0x11A (UTF-16)
```

Por eso, lanzado SIN comillas (Python `Popen([ruta])`), la ruta se «decodifica» como bloque: A y B
salen basura (la «huella» rara, con pedazos de la MAC: XOR contra ceros) y la copia se pasa de largo
y **pisa la MAC de `+0x166`**. ★ Es la puerta del LOGIN (A = usuario, B = ticket): el bloque lo arma
nuestra `d3d9.dll` desde `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]` y el server lo valida en
`servidor/porteria.py` (MEDICIONES §45). Si no vale, `0x1010` con `0x66` → «Can't Connect to server».

### 5.2 · `0x1010` S→C — entrada (12 B)
`u16 resultado` (1 = OK; `0x66`, `0x899`, `0x89A` = errores) · `u32 🟡` (→ `+0x2B8` de la
cuenta) · `u32 🟡` · `u16 🟡`. Con OK el cliente arranca el `0x1001` de cada 20 s y pasa a
SELECT CHARACTER.

### 5.3 · `0x1001` — «estoy vivo» (1 B: `0x80`)
Cada 20 s. Sin respuesta, al rato el cliente arma él mismo un `0x1003` y muestra «conexión
inestable». 🟡 Contestarle el mismo `0x1001` alcanza para que no corte.

### 5.4 · `0x1012` S→C — la cuenta
Cabecera de 33: `u16 resultado` (1 = OK; `0x65` = error) · cuenta (copiada por `0x53EBC0`) ·
`u16 N1` (`+0x1C`) · `u16 N2` (`+0x1E`) · `u8 N3` (`+0x20`); después N1×21 + N2×36 + N3×186.

| offset (en el cuerpo) | qué |
|---|---|
| `+0x0F` u32 | **Cash** (visto en pantalla) |
| `+0x13` u32 | **Gold** (visto en pantalla) |
| `+0x19` u8 | **lugares de personaje habilitados** (con 0 no se puede clickear ninguno) |
| N3 × 186 | **los personajes** (§5.6) |

### 5.5 · `0x1013` C→S / `0x1014` S→C — crear personaje
C→S: `u32 lugar · u16 clase · nombre UTF-16`. S→C: `u16 resultado` (1 = OK; `0x8FD..` errores)
+ **un personaje de 186 bytes**. El cliente lo agrega, lo dibuja y dice «Character Creation is
Complete».

### 5.6 · El personaje (186 bytes)
`+0x00`, `+0x24`, `+0x5E`, `+0x6E` son vtables del objeto en el cliente: en el mensaje se ignoran.

| offset | qué |
|---|---|
| `+0x04` u8 | ★ **CLASE**, desde 1 (1 = Warrior). Con 0 el cliente muere al dibujar el modelo |
| `+0x05` | **nombre**, UTF-16, 26 bytes |
| `+0x1F` u8 | ★ **NIVEL**: el lobby y la pantalla de personajes hacen `movzx eax, byte [pj+0x1F]` → `"%dLV"` (`0x4EF93E`, `0x4F9888`; medido con un breakpoint en `_woutput`). Con 1: «1LV» |
| `+0x20` u32 | ★ **EXP**: con 11 la barra dice «(11/300)»; el 300 sale de la tabla de niveles del juego (con nivel 0 decía «(1/0)»: el nivel 0 no está en la tabla) |
| `+0x28` u16 | 🟡 (no se ve) |
| `+0x2A` | texto UTF-16 de 40 bytes 🟡 |
| `+0x52` u8 | ★ **el LUGAR** (0..4): con 1 «rui» pasa al segundo; con 33 el personaje no aparece |
| `+0x53` u32 / `+0x57` u32 | ★ **partidas / abandonos**: el lobby muestra «Quit Rate  +0x57 / +0x53 (%)» |
| `+0x5B`, `+0x5C`, `+0x5D` u8 | 🟡 (no se ven) |
| `+0x62` `+0x64` `+0x66` `+0x68` `+0x6A` u16 | ★ **Strength, Constitution, Dexterity, Intelligence, Wisdom** (vistos en el lobby con 101..105) |
| `+0x6C` u16 | 🟡 (no se ve) |
| `+0x72` | **9 × u32: el equipo** (cada uno se busca en la base de ítems del juego) |
| `+0x96`..`+0xB6` | 9 × u32 más 🟡 (no se ven) |

⛔ Corregido: primero se creyó que «el nivel y la EXP no están en este registro». Era un error de
la prueba: los valores de prueba se escribían ANTES que los campos fijos y éstos los pisaban
(`+0x1F`, `+0x20`, `+0x28`). Con el orden arreglado, `+0x1F` = nivel y `+0x20` = EXP.

✅ **No hay tutorial**: ni «tutorial», «training», «newbie» ni «beginner» en el exe ni en la
memoria del juego (ASCII y UTF-16). El personaje empieza con el nivel que diga el server: el
nuestro manda nivel 1.

### 5.7 · `0x1017` C→S / `0x1018` S→C — entrar al lobby
C→S: `u32 🟡 · u8 🟡`. S→C: cabecera de 16 — `u16 resultado` (1 = OK; `0x899` = error 11) ·
`u8 (+2)` el personaje elegido (→ `+0x21C`) · **`u32 N1 (+3)`** · `u16 N2 (+7)` · 7 B (+9 →
`0x6103E0`, cuenta `+0x220`) 🟡 — y N1×10 + N2×13.
⚠ **Corregido el 10-nov**: antes decía «4 🟡 · u8 (+6) · u32 N1 (+7) · u16 N2 (+0xB)» — mal
contado un `push ebx` (`0x54470E`). Con N1 en +7 el cliente leía N1 = 0 y el mapa de misiones
terminadas quedaba vacío (medido llamando al buscador del juego, `0x620820`: 0 entradas).
- N1 × 10 = **las misiones terminadas**: `[u32 · u32 escenario · u8 · u8]` → `0x621620` (clave
  = el escenario, en +4; el u8 de +8 tiene que ser ≥ 1). Las consulta `0x6209F0` («¿el escenario
  N está disponible?») según la `<CONDITION>` del XML de cada escenario: TIPO 0 = alcanza con
  uno de la lista terminado. La cadena del capítulo 1: **1011 Easy → 1012 Normal → 1013 Hard →
  1021 Easy 1-2 → …** (no es 1011 → 1021).
Con OK pasa a la pantalla 3, **LOBBY**.
- N1 × 10: van a un mapa con clave `u32` + dos bytes por entrada (`0x621620`, `+0x444`) 🟡
  ¿progreso por misión?
- N2 × 13: van a `+0x728` (`0x61F710`) 🟡

### 5.8 · `0x101D` C→S / `0x101E` S→C — crear la sala (Create Stage → Create)
C→S (93 B): `u32 🟡` + la sala serializada (el objeto entero, con el lugar de su vtable adelante):
`+4 u16 número` (0xFFFF = sin número) · `+6 título UTF-16` (hasta +0x28) · `+0x28 u32 escenario`
(1011) · `+0x2C..+0x30` 🟡 · `+0x31 clave UTF-16`.
S→C (`0x543500`, 94 B): `u16 resultado` (1 = OK) · `u8 🟡` · `u8 (+3)` · `u8 (+4)` (si son iguales
arranca además lo de UDP: 🟡 ser el anfitrión) · 89 B = **la sala desde su +0** (como el personaje:
desde +4 el escenario queda corrido y el cliente muere en `0x5367D4`). `+0x2F` = **máximo de
jugadores**. Con OK: pantalla 5, **WAITING ROOM**, con el jugador local como anfitrión.

### 5.8b · `0x1025` C→S / `0x1026` S→C — Quick Join (Entrada rápida a sala)
C→S (`0x543160`, 30 B): solicitud de entrada rápida a cualquier sala con cupo libre.
S→C (`0x5424E0`, 5 B): `u16 resultado` (1 = OK, `0x0BB9` = sin salas libres) · `u16 sala` · `u8 modo` (0).
Con resultado 1, el cliente transiciona de inmediato (`0x4EBEE0`) y envía `0x101F` (`entrar_sala`) con la sala asignada.

### 5.8c · `0x104B` S→C — Actualización de ajustes de sala (escenario y dificultad en vivo)
S→C (`0x54F500`): difunde cambios del anfitrión al resto de miembros en la sala de espera.
- Tipo 1 (Escenario): `u16 1` · 34 B del escenario (`0x54F53D`, actualiza minimapa e información).
- Tipo 2 (Dificultad): `u16 2` · 20 B de dificultad (`0x54F55E`, actualiza modo EASY/NORMAL/HARD).

### 5.8d · `0x105B` S→C / C→S — Sincronización 3D de equipamiento en sala de espera
C→S (`0x54F700`): solicitud de actualización de apariencia 3D del personaje en la sala.
S→C (`0x54F740`, 633 B / 0x279 B): `u32 id_miembro · u8 0 · 6 × u16 stats · 18 × 34 B items` (vtable `0x89A38C` · `u16 tipo` · vtable `0x89A380` · 24 B ceros).
Se difunde a todos los miembros de la sala al cambiar equipamiento (`0x102D`) o al solicitarlo, actualizando en tiempo real la malla 3D LithTech del personaje en la escena (`0x540B50`).

### 5.9 · `0x104E` C→S / `0x104F` S→C — F9 START GAME
C→S: `u8 🟡`. S→C (`0x54F170`): `u16 🟡 · u32 → +0x53 del personaje (partidas) · u8 🟡 · u8 N` +
N × 68 (`[u8 índice del jugador en la sala][9 × 7 B: 🟡 su equipo]`). Con eso: pantalla 8, la
partida, y empieza a **cargar el mapa** (un hilo aparte, `0x534770`, que bombea la red mientras).

### 5.10 · La carga y la LARGADA: `0x105C` / `0x105F` C→S, `0x105E` S→C
Mientras carga, el cliente avisa `0x105C` (el primer evento del guion Lua, «Briefing_01») y al
terminar **`0x105F`** (u32 = ms que tardó en cargar). Después se queda en
`while (!this[0xE0]) Sleep(1)` (`0x500643`, «NOW LOADING» en pantalla) hasta que el server da la
largada:

**`0x105E` S→C — `OnPktS2C_Ntf_Play_Start`** (`0x5333D0`): `u16 resultado · u32 valor`.
Con resultado 1 arma un mensaje INTERNO con comando 1 = `[u8 1][u32 valor]` y se lo pasa al
callback de la escena (`0x510D50`), que guarda el valor en `+0xEC` (🟡 el tiempo de la stage),
pone `[0xE0]` y pasa al estado 3. NetTrace.log: `OnPktS2C_Ntf_Play_Start Succeed` ·
`NetUpdateON` · `Delete LoadingScene!!` · `Briefing Time!!` → **el personaje en el mapa**.
- ⚠ El 0x105E sólo se atiende durante la carga: lo despacha el mapa de comandos de la escena de
  carga (`+0x168`, lo llena su constructor `0x5343D0`; ahí también está `0x1058`
  «OnPktS2C_SomeOne_ChangeState» → `0x534370`). Un «comando 1» mandado por la red NO llega
  (medido: el cliente lo ignora y sigue en NOW LOADING; es el control al revés).

### 5.11 · EN la partida: lo que el cliente AVISA (medido el 10-nov, el tester jugando)
El juego corre **adentro del cliente** (el guion Lua del escenario mueve las puertas y saca los
NPC); al server sólo le avisa, por el mismo TCP:

| C→S | cuerpo | 🟡 qué es |
|---|---|---|
| `0x105C` | `u32 tipo` + … | un evento del guion. Tipo 0 = `u32 largo · texto · u32` («Briefing_01», «OnStart», «OnTrigger_01» con 1000, «OnSwitch_01», «DoorSwitch_01..03», «MessageTrigger_01» con 1500, «OnTrigger_03» con 3000); 0x17 = un grupo de NPC con su lista («NpcGroup01», 189 B); 0x18 = `«NpcGroup01» · u32 n`, uno por NPC que aparece (0..4); 0x0D = una puerta («DoorL01», abierta); 0x05/0x11/0x12/0x13/0x15 = 🟡 |
| `0x1061` | `u8 n · u8 1 · 6 × 0` | un NPC muerto (n = el número de NPC: 0..4 del grupo 1, 5..7 del grupo 3) |
| `0x1065` | `u8 jugador · u32 0x108` | ★ **el jugador murió** (a los 14:31:21, cuando el tester murió; 🟡 0x108 = quién lo mató, la «Baby Tarantula») |
| `0x1001` | `u8` | sigue el «estoy vivo» cada 20 s |

Los manejadores S→C de la pantalla de la partida (`0x548F80`, cada `push cmd` con su `mov edi`):
`1058→0x5482A0` · `1060→0x546D60` · `1062→0x547440` · **`1066→0x547940`** · `1068→0x546920` ·
`1069→0x547180` · `106B→0x547680` · `106C→0x547A60` · `106D→0x546750` · `106E→0x546960` ·
`106F→0x546A00` · `1071→0x546B70` · `1072→0x546CA0` · `1073→0x548AF0` · `1054→0x546D90` ·
`1075→0x546F40` · `105D→0x546E60`. Y los que manda el cliente salen de `0x5461E7` (1061),
`0x5462B5` (1067), `0x5463B2` (1063), `0x5464B7` (1064), `0x546588` (106A), `0x5466A7` (1065),
`0x546AE4` (1070), `0x546EBD` (1074).
- `0x1066` (`0x547940`) lee 6 B: `u8 jugador · u32 objeto · u8 → +0x322 del miembro de la sala`
  y llama `0x6360F0(jugador, objeto)`. Con estado 1 o 2 al muerto: no abre nada (no es eso).
- `0x1063` C→S `u8 0 · u16 n` (n = 0x0A, 0x1E…): sale justo antes de morir y en la pelea 🟡.
- `0x1062` S→C (`0x547440`, 16 B) / C→S: `u32 id_miembro · u32 0 · u16 hp · u8 0 · u32 mp · u8 buffs`. Sincroniza barras de vida y maná en el HUD cooperativo (`0x612A90` en `ebp + 0xF8`). El servidor lo difunde a los compañeros de equipo al recibir `0x1063` (`le_pegaron`) o al registrar daño/gasto de maná.

### 5.12 · ★ MORIR Y REVIVIR (medido el 10-nov, todo en automático)
```
  cliente                                   server
  0x1065  u8 jugador · u32 quién lo mató   →
                                            ←  0x1068  u32 = tiempo para decidir (ms; 15000)
  «Do you want to use current coin to respawn?» + cuenta regresiva + Confirm / Cancel
  0x106A  u8 0 · u8 1 (sí) / 0 (no) · u8 FF →
                                            ←  0x106B  u16 1 · u8 modo · u16 monedas que QUEDAN · u8
  modo 1 = revive (estado 4: HP lleno, de pie) · 0 = se rinde (estado 0xA) · 2 = revivió OTRO
```
- **`0x1068`** (`0x546920`): u32 → `+0xEC` y llama `0x5037D0`, que abre el cuadro `0x1770`
  sólo si hay monedas. Sin el `0x1068` el muerto queda tirado aunque tenga monedas (medido).
  Con 10 la cuenta salió ya en 0 y Confirm no respondía; con 15000, Confirm → `0x106A`.
- **Las monedas** = `u16` en `+0x2C9` de la cuenta = **`cuerpo[0x17]` del `0x1012`** (la cuenta
  se copia de cuerpo+2 a `+0x2B4`; cierra con la plata, `cuerpo[0x13]` = `+0x2C5`). Se ven en
  el HUD como «● X3» al lado del nombre (texto 6016 `X%u`). Las cambian `0x106B`, `0x1073`,
  `0x1075` y el `0x1054` de la sala.
- Probado: muerto con X3 → `0x1068` → Confirm → `0x106A 00 01 FF` → `0x106B` (1, 1, 2) → rui
  de pie con HP lleno y **X2**. Y con la regla puesta, la segunda muerte abrió el cuadro sola.

### 5.12b · GAME OVER: cuando vence el tiempo para revivir (medido el 10-nov)
- Al vencer la cuenta del cuadro de revivir el cliente **no manda nada** (medido 15:19: el cuadro
  queda en 0). El game over lo da el SERVER: **`0x1069`** (`0x547180`, 1 B) → estado 0xA =
  **modo espectador**: se va el HUD y dice «<Jump Key> pushing allow viewing of other players».
  Lo mismo hace `0x106B` en modo 0 («Cancel» o sin monedas).
- Con todos muertos no hay a quién mirar: `0x1075` (§5.15) lo lleva al **LOBBY** (medido 16:22,
  sin caerse, desde el modo espectador). 🟡 Con varios jugadores, el server original seguramente
  esperaba a que murieran todos.
- `servidor/juego.py`: muerte → reloj de 15,5 s; si no llegó el `0x106A`, en el próximo «estoy
  vivo» (`0x1001`, cada 20 s: es el único momento en que el server puede hablar sin que le
  pregunten) manda `0x1069` y, 6 s después, `0x1075`.

### 5.13 · El FIN de la stage: `0x1064` C→S / `0x1073` S→C `PlayEnd`
- El guion termina con `OnEnd()` → `scenario:SendEvent()` (`0x636EA0`) → el delegado de
  `+0x668` = **`0x546480`, que manda `0x1064` (`u8 jugador`)**.
- **`0x1073` PlayEnd** (`0x548AF0`, NetTrace «PlayEnd- RoomState :%u»): cabecera de 28 B —
  `u16 1 · u16 monedas · u32 plata · u32 EXP (+0x20 del personaje) · u16 (+0x6C) · u8 nivel
  (si sube: festejo, `0x548900`) · 10 B misión terminada [u32 · u32 escenario · u8 · u8]
  (`0x621620`: el mapa de terminadas, el que habilita la stage siguiente) · u8 N1 · u8 · u8 N2`
  + N1 × 21 (ítems; si +0x11 = −1, 36 B más) + N2 × 10 + lo de `0x61FA90` + `u8 M` jugadores
  [u32 id · u8 nivel · u32 EXP]. Al final `0x503770(1)` habilita el botón `0xFD8` de la ventana
  `0x190`. Probado mandándolo A MITAD de la partida: lo procesa («PlayEnd End- RoomState :0»)
  pero la partida sigue. ✅ La pantalla de resultado NO la abre el PlayEnd sino `0x106E` (§5.14).

### 5.14 · ★★★ Después del PlayEnd: resultado → cartas → premios (medido el 10-nov, pantalla por pantalla)
Encontrado desde el layout de la interfaz (dentro de `Data.dat`: `MissionResult_POPUP` = popup
200, `RewardCard_POPUP` = 300, `RewardResult_POPUP` = 400 con su Confirm 4056 = `0xFD8`) y los
que piden esas ventanas (`0x7510F0(200)` → `0x503C80`, llamado sólo desde el manejador de 0x106E).

| S→C | cuerpo | pantalla |
|---|---|---|
| `0x106E` (`0x546960`, 19 B) | `u32 🟡 · u16 monstruos muertos · u16 golpes recibidos · u16 revividas · u32 tiempo (ms) · u32 puntos · u8 rango` (1 = D) | **MISSION COMPLETION RESULT** |
| `0x106F` (`0x546A00`, 16 B) | `u32 tiempo para elegir (ms) · u32 precio I · u32 precio II · u32 precio III` | **REWARD CHOICE**: 4 cartas doradas / 6 plateadas / 8 de bronce, cada fila con «EXP» |
| ← `0x1070` C→S | `u8 · u8 CARTA de corrido` (oro 0–3, plata 4–9, bronce 10–17 → la fila, `0x500810`; DOBLE clic en la carta: `0x5007D0` → `0x546A80`) | |
| `0x1071` (`0x546B70`, 11 B) | `u8 1 · u8 FILA · u8 JUGADOR (= cuenta+0x705, si no, se ignora) · u32 EXP de cartas acumulada · u32 puntos que QUEDAN` | «Earned Point» 400 → 50 (medido) |
| `0x1072` (`0x546CA0`) | `u32 ÍNDICE de StageReward · u8 N · N × (u8 jugador · u8 1)` | **AWARD RESULTS** (`0x612B40`): EXP de cartas + Σ Type 0 = oro, Σ Type 1 = EXP, Type 2 = ítems de esa stage |

- Probado con fotos: cada campo del `0x106E` con valores distintos (03:05 = 185000 ms, rango
  D). 🟡 La carta elegida no se dio vuelta con «carta 0»: falta qué ítem va en el `u32`.
- ✅ El Confirm de AWARD RESULTS (`0x5151F0`, control 4056) lleva SOLO a la **WAITING ROOM**,
  sin mensaje del server (medido 15:50: la sala «EDA vuelve» con rui y F9 Start Game). El ciclo
  entero cierra: sala → F9 → partida → fin → resultado → cartas → premios → sala.

### 5.15 · Salir de la stage: `0x1074` / `0x1075` → el LOBBY
- ESC (al `Edit` oculto del IME: a la ventana de arriba no llega) → «Do you want to quit the
  stage and return to Lobby?» (popup 700) → Confirm (control 7000 → `0x546E70`) → **`0x1074`**
  (`u8 jugador`).
- **`0x1075`** (`0x546F40`, 16 B): `u16 1 · u16 monedas · u32 abandonos (+0x57: el «Quit Rate»)
  · u8 nivel · u32 EXP · u16 (+0x6C) · u8 N × 10 B` → `0x4E7350(3)` = **el LOBBY**. Medido: de
  vuelta en el lobby con «Quit Rate 1/1 (100%)» y «EXP 150/300».
- ⚠ Mandado estando en AWARD RESULTS, el juego se cae en `0x752B7E` (un objeto nulo).
- `0x1054` en la partida (`0x546D90`): `u16 motivo · u8` → motivo 1 = al lobby; 2 = «[BAD_PING]
  ROOMOUT», 3 = «[ROOM_ERR] Head Will Hacker», 4 = «[ROOM_OUT] Admin».
- `0x1069` (`0x547180`): 🟡 la stage PERDIDA (estado 0xA, el de «me rindo»).

## 5.16 · ★★ CÓMO SE ENCUENTRAN LOS CLIENTES: IP pública, LAN, cíber (NAT) — mapa (10-nov)

El tester: «en R2Beat fue algo que nos trabó bastante». EDA lo resolvía con **tres piezas**, todas a
cargo de los servers; el cliente sólo informa y obedece. Lo medido y lo leído del exe:

```
 1. BROKER (TCP 25000) — ¿qué NAT tengo?
    C→B 0x0604 (la huella)  →  B→C 0x0607 «UDPLabel» (IP:puerto UDP del server de prueba)
    el cliente manda UDP a ese «label»; el server ve DE QUÉ IP:puerto llega (la pública)
    B→C 0x0609 = TIPO DE NAT + IP:puerto PÚBLICOS  (NetTrace: «[NETWORK NAT Type] 1 public,
        2 Full Cone, 3 IP Restricted, 4 Port Restricted, 5 Symmetric, 6 Unknown, 8 Block»)
    (+ «SendC2BNATTYPEReconfirm» / «OnPktRBC2NATTypeSort»: 🟡 una segunda prueba)
 2. SERVER DE JUEGO (TCP)
    C→S 0x100F lleva las DOS direcciones del cliente: +0xDD IP PRIVADA · +0xE1 puerto privado ·
        +0xE3 IP PÚBLICA · +0xE7 puerto público (los del 0x0609) — todo como enteros
    S→C 0x1010 dice dónde está el SERVER UDP DE PUNCH (u32 IP · u16 puerto → `0x6218F0`,
        «[Punch UDP IP, PORT]») — y la cuenta (+0x2B8 = cuerpo[6] del 0x1012) es su id
 3. PUNCH (UDP) + SALA
    C→P 0x3006 (UDP sin cifrar: u16 largo · u16 0x3006 · u32 id de la cuenta), ×4: «registrame»
        → el server de punch ve el IP:puerto PÚBLICO REAL de ese cliente (el de su NAT)
    S→C 0x1059 «Peer Public IP» a cada miembro: u8 id · u32 IP · u16 puerto (ENTEROS) de los
        OTROS (el propio no: se cae) → cada cliente saluda a cada par: 0xC354 ×~185 en 2 s (con su
        IDENTIDAD P2P = su MAC en texto) y 0xC351 / 0xC352 = apretón de manos
    el ping de la sala lo busca la capa UDP por la identidad que va en +0xA del miembro (0x1020 /
        0x1057) → ✅ MEDIDO: 77 / 74 ms, y en la partida se ven moverse (UdpMsgCnt 151)
    (+ «SendC2RUDPConnect»: cliente → RELAY, 🟡 para cuando el punch no alcanza: NAT simétrica)
```

- **IP pública** (o Full Cone): alcanza con la dirección pública que vio el server de punch.
- **Varios en la misma LAN / el mismo cíber** (misma IP pública): entre ellos el punch hacia la
  pública suele fallar (el router no hace «hairpin»): para eso el `0x100F` trae la PRIVADA → el
  server, si dos miembros tienen la misma IP pública, les da la privada del otro en el `0x1059`.
  (🟡 Deducción: es lo que permiten los datos; el código que elige no está medido.)
- **NAT simétrica** (tipo 5): el puerto cambia por destino y el punch no anda → el *relay*
  (C2R): el server reenvía el UDP de uno al otro.
- ⚠ Lo que nos falta medir: la respuesta del punch (`0x3007`, el ruteador UDP `0x4E57C0` manda
  0x3000–0x3007 a `[esi+0x48]` vt+4 y 0x3008–0x300A a `[esi+0x44]` vt+0x34), y el formato del
  relay. Hoy (dos clientes en la misma PC): `udp_punch.py` en 127.0.0.1:25001 recibe los 0x3006;
  **el P2P anda** (ping y movimiento). ⏭ Para PCs distintas: (a) la identidad P2P de cada uno
  sale del 0x100F, que la trae ofuscada (hoy se usa un atajo local); (b) la dirección PÚBLICA
  real la ve el server de punch en el origen de los 0x3006 (por id de cuenta); (c) si dos tienen
  la misma IP pública (cíber), darles la PRIVADA del otro.

## 5.17 · ★★ TIENDA E INVENTARIO (pantalla 6, `ShopNInventory`) — medido el 10-nov

Entrar: lobby → Shop/Inventory = `0x1027` (u32 · u8 pestaña: 4 Shop, 5 Inventory) → `0x1028`
(u16 1); desde la SALA → `0x104C` (u8) → `0x104D` (u16 1 · u8 → cuenta+0x2DE), y al irse el
`0x102E` va en modo 9 (los 0x63 B del `0x1020` sin su u16 + todos los miembros de 0x32C →
pantalla 5). El cliente mueve los ítems SOLO (clic derecho = equipar/desequipar) y avisa al irse.
**Premios**: el ítem de `StageReward.xml` llega en el PlayEnd (`0x1073`, N1 × 21 B; con +0x11 =
−1 la ficha de 36 B va pegada).

| C→S | qué | S→C (manejador) | formato de la respuesta |
|---|---|---|---|
| `0x102D` (`0x54BE70`) | tocar «Lobby»: u32 · 16 B stats (vt 0x89A368 + 6 u16) · u16 N · u16 N2 · u16 N3 · N × (u32 serial · u8 casillero) | `0x102E` (`0x54CD70`) | u16 1 · u8 MODO (3 → lobby; 9 → sala, 🟡) · u8 (→ cuenta+0x21C) · 7 B canal (como el 0x1018) · 16 B stats · 76 B EQUIPO (vt 0x89A388 + 18 u32 = serial por parte) · u16 N × (u32 serial · u8 cantidad · u8 casillero) · u16 M × (u32 · u8 · u8, 🟡) |
| `0x102B` | cambiar de pestaña: lo mismo con u8 PESTAÑA en +4 | `0x102C` (`0x54BBB0`) | u16 1 · u8 pestaña (→ pantalla+0xDC) · 16 B stats · 76 B equipo · las dos listas |
| `0x103F` (`0x54DA47`) | comprar: u32 · u8 N · N × u16 ID de producto (`Product.xml`) | `0x1040` (`0x54D340`) | u16 1 · u32 ORO · u32 CASH · u8 nA · u16 nB · u16 nC · nA × u16 producto · nB × ítem (21 B + ficha de 36 B si el tipo es 1–19999) · nC 🟡 |
| `0x1041` | vender: u32 · u32 serial | `0x1042` (`0x54AA80`) | u16 1 · u32 serial · u32 ORO · u8 1 = borrar su ficha |
| `0x103B` (`0x54A850`) | verificar un libro: u32 · u32 serial del LIBRO · u32 serial del PERGAMINO | `0x103C` (`0x54B1E0`, 31 B) | u16 1 · u32 serial del pergamino · i32 los que quedan (≤ 0 = se borra) · el ítem nuevo (21 B, reemplaza al de su serial) |
| `0x103D` (`0x54C9B0`) | aprender: u32 · u32 serial del libro · u16 N2 · u16 N3 · listas de la grilla | `0x103E` (`0x54CB70`) | u16 1 · u8 modo (0 agregar) · u32 ORO (+3) · u32 serial del libro (+7) · u32 clave a borrar (+0xB, modo 1) · la habilidad (13 B) · u16 N × (u32 · u8 · u8) |

- **Habilidades** (pestaña Skill = 7): un «libro» es un ítem de habilidad (tipo 31000–33999 =
  REFID de `Skill.xml`) con **+0xE = 0** (se ve como «Unknown Skill Book»). Clic derecho en el
  Skill Check Scroll (40051) + clic en el libro → `0x103B`. Ya verificado, clic derecho →
  «%d Gold will be used» (COST_GOLD) → `0x103D`. Pide nivel (ACQUIRE_LEVEL), clase y **lugares
  = personaje +0x5B** (`0x523E41`). La habilidad (13 B, vt 0x89A3A4): u32 clave · u8 1 activa /
  2 pasiva · u16 ID · u8 · u8 (🟡 lugar en la grilla). Al entrar al lobby van en el **`0x1018`:
  N2 (+7) × 13 B**.
- El GUI pregunta por el botón apretado con **`GetKeyState(VK_LBUTTON)`**: para ARRASTRAR hace
  falta `clic_juego.arrastrar_de_verdad` (Frida); los clics y el clic derecho andan por mensajes.

- **Ítem** (21 B, `0x617630`): u32 · u32 SERIAL · u16 TIPO · u8 CANTIDAD · u8 CASILLERO (0–11
  equipo, 12–17 barra, 18… bolsa) · u16 · u8 · u16 · u32.
- **Equipo** (personaje +0x72, 18 u32): índice = PARTE (🟡 por la familia del tipo, tipo // 1000:
  0 arma · 1 segunda · 3 máscara · 4 torso · 5 piernas · 6 guantes · 7 cinturón · 8 botas).
- Precios: `<Product SellGold SellCash>` (lo que cobra la tienda) y `<BuyItem BuyGold>` (lo que
  paga). Nivel y clase de cada pieza: `ItemTypeList.xml` (`LEVEL_RESTRICT`, `USECLASS`).

## 6 · Lo que todavía no

- ✅★ **RESUELTO: el selector anda.** Se abre una stage con **DOBLE CLIC en su marcador** (el
  botón cian de la izquierda): sale la ventana CREATE STAGE (mapa 3D, «3 Players», dificultad
  EASY, «Defeat all enemies that appear.», «Start of the Search», Room Title, Password, Create /
  Cancel). Medido antes: `0x6209F0` («¿el escenario N está disponible?») contesta 1 para 1011 y
  0 para los otros 49 del capítulo (cada uno exige haber terminado el anterior: el mapa de
  terminados está en `+0x444` de la cuenta, y lo llena la N1 del 0x1018).
  ⏭ Falta: escribir el Room Title (el texto entra por un `Edit` oculto que maneja el objeto del
  IME, y con mensajes no llega: hace falta foco de teclado de verdad) y apretar Create.
- (historia) El selector de stages (Create Stage) quedaba en «Target search……» sin pedirle nada al server.
  ✅ Medido: la lista de escenarios del juego SÍ carga (`0x64CD90` → 150 escenarios con OK, 1
  capítulo). ⛔ Probado: un registro N1 con la misión 1011 en el 0x1018 no cambia nada.
  ⛔ Probado: con nivel 1 tampoco. ✅ Y no es una pieza del exe: en todo el camino lobby → Create
  Stage → selector → NEXT CHAPTER **no se alcanza ni una trampa** (medido bajo el depurador).
  🟡 Lo que se sabe del XML: 50 escenarios por dificultad en el capítulo 1 (IDs 1011, 1021…, el
  último dígito = dificultad: 1013 = Hard), y cada uno trae `<CONDITION TYPE="0" NUM="1">
  <SCENARIO ID="…"/>`: **requiere haber terminado otro**. Candidato: la lista de escenarios
  terminados del personaje viene del server (¿la N1 del 0x1018?) en un formato que todavía no
  se conoce.
- Las pestañas del lobby (Shop, Inventory, Clan, Messenger), la lista de salas, el chat.
- La partida en sí: ✅ arranca (§5.10) y el personaje aparece en el mapa; falta lo que pase
  ADENTRO (enemigos, golpes, el fin de la stage) — por ahora con NetTrace en `TcpMsg:0 ·
  UdpMsgCnt:0` cada 3 s: el cliente no le pide nada al server.
- La cuenta: cómo se logueaba sin usuario ni clave (el launcher).

## 7 · Cómo se prueba hoy

```
py herramientas\reglas_broker.py               # escribe el guion (reglas.json)
py herramientas\espiar_broker.py control       # WinDivert + oyente (UAC; dura una hora)
cd _trabajo\juego && EDA_limpio.exe            # EDA Local → ENTER → rui → Enter Lobby
py herramientas\foto_juego.py --en 10          # una foto de la pantalla
```
