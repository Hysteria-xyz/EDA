# Lo que se fue midiendo

> Una entrada por corrida, con fecha. ✅ = medido · 🟡 = deducción, sin confirmar.
> La evidencia cruda queda en `_trabajo/` (no va a git).

## 2026-11-08 · corrida 1 — abrir `EDA.exe` con `proxy_mitm.py DESCUBRIR=1`

El tester abrió `cliente/EDA.exe` (directo, sin launcher) con el proxy en modo descubrir corriendo
desde las 14:06. Evidencia: `_trabajo/descubrir/corrida1/`.

- ✅ **GameGuard frena el juego antes de que haga nada de red propio**: cartel
  *«Game guard error : 361»* (pide mandar los `*.erl` a un mail de INCA).
- ✅ A las **14:09:47** sale una conexión nueva a **`211.233.43.45:8080`**; en ese mismo minuto
  GameGuard escribe `GameGuard/GameGuard.ver` (14:09) y `npg*.erl` + `npgmup.des` (14:10).
  `npgmup.des` (el actualizador) trae código HTTP (`http://%s%s`, `HttpSendRequestA`).
  Hoy esa IP no contesta (`Test-NetConnection` al 8080: falla; sin PTR).
- 🟡 Por eso: `211.233.43.45:8080` sería el **server de actualización de GameGuard**, y el 361 =
  «no pude actualizarme». Sin fuente; IP coreana sólo por el rango.
- ✅ Las demás conexiones de esa ventana son **ruido** de la máquina, no del juego: otras dos conexiones de la PC aparecen ANTES de abrirlo (14:06); `192.168.*:7680/8009` son la LAN;
  `192.168.x.x:28004/28008/28101` son R2Beat.
- ✅ Los `.erl` vienen **cifrados** (empiezan `00 FC CC 00`): no se pueden leer.
- ✅ **El juego ensucia su carpeta**: crea `GameGuard/` (6 archivos, incluida una copia idéntica
  de `EdaENGTest.ini`, md5 `285c8a47…`), y al cerrarse **crashea** dejando `EDA.dmp` (164 KB,
  minidump chico) + `EDA.rpt` (ACCESS_VIOLATION en `0x00402FC0`, al salir tras el error de GG).
  Todo eso se movió a `_trabajo/descubrir/corrida1/`; `inventario.py` volvió a 57/57.
  ⇒ **De acá en adelante el juego se corre desde una copia**, no desde `cliente/`.
- ✅ Control del método: el caché DNS de Windows (`Get-DnsClientCache`) **sale vacío** en esta
  máquina aun después de resolver un nombre: no sirve para ver qué nombres busca el juego. Para eso
  quedó `herramientas/mirar_dns.py` (todavía no corrió de verdad).

## 2026-11-08 · ¿con qué está empaquetado `EDA.exe`?

- ✅ **ASProtect** (la familia 1.2x–2.x): el punto de entrada (RVA `0x1000`) empieza con el stub
  clásico `68 01 .. .. 00 E8 01 00 00 00 C3 C3`, más la sección `.adata`. Todas las secciones de
  código y datos con entropía ~8.0 (comprimidas/cifradas), incluida `.data` (7.93).
- ✅ Barrido de las otras: 0 apariciones de `Themida`, `WinLicense`, `VMProtect`, `.vmp`.
- 🟡 Consecuencia: el código no está virtualizado como en Themida; al arrancar se desempaca entero
  en memoria ⇒ un volcado de memoria con el juego abierto debería dar el código legible. Lo molesto
  de ASProtect es reconstruir los imports y los «stolen bytes» del arranque, que sólo hacen falta
  para que la copia volcada CORRA, no para leerla.

## 2026-11-08 · corrida 2 — volcar el exe desempacado (`herramientas/volcar_exe.py`)

Juego abierto desde la copia `_trabajo/juego/EDA.exe`, quieto en el cartel de GG 361. Sin UAC: el
juego corre como usuario común. Salida: `_trabajo/volcado/eda_1/` (`imagen.bin`, `EDA_volcado.exe`,
`modulos.json` con 65 DLL, 389 zonas ejecutables sueltas, `cadenas.txt`).

- ✅ **Control** (un exe NO empaquetado, `SysWOW64\PING.EXE`): memoria vs disco 97 % igual en `.text`
  (lo distinto = relocaciones). **EDA**: las secciones sin nombre dan **0,4 %** igual, y hay **5.189**
  cadenas legibles contra **485** en el archivo ⇒ el volcado es el código desempacado.
  `.data` (99,3 %) y `.adata` (100 %) no cambian: son el propio ASProtect, no el juego.
- ✅ **LithTech confirmado**: «LithTech build %s initialized in %.2f seconds», `ILTServer`, `CLTClient`,
  `.ltb`, `object.lto`, `LTDirectMusic`, «Unable to load ltmsg.dll».
- ✅ **La red de Softnyx encima de LithTech**: `CTCPHelper`, «ATryConnectBroker», «Broker ConnectFail»,
  «TcpMsg:%u», `COpenningScreen::SendC2RUDPConnect()`, `CChannelLobbyScreen`; y el UDP de LithTech
  («UDP: Connection to %d.%d.%d.%d:%d accepted»).
  🟡 Deducción: login/lobby por TCP a un «Broker», la partida por UDP. ⚠ `DESCUBRIR=1` sólo mira TCP.
- ✅ Del launcher: `CLTClient::IsLobbyLaunched`, `GetLobbyLaunchInfo`, `-cmdfile`, `ICommandLineArgs`.
- ✅ Otras piezas: «Softnyx File System» (UTF-16, = `Data.dat` 🟡), zlib 1.2.3 / unzip 1.01, Lua 5.1.4,
  GUI con HGE (`HGELIB`), boost.
- ✅ Mensajes de GG en el exe, entre ellos «Game guard update server connection failed…»: el 361
  muestra el genérico («attach the *.erl files…»).
- ✅ Barrido de la memoria privada del proceso (4 MB) buscando IPs y claves de config: **nada**. 🟡 El
  juego muere en GG antes de leer su config de red.

### ¿El código volcado es legible y quedó fuera de ASProtect?

- ✅ **Legible**: en la 1ª sección hay **1.259** comienzos de función típicos del compilador
  (`55 8B EC`); en la misma sección del archivo empaquetado, **0**.
- ✅ **Las llamadas a Windows van directo a las DLL reales**: de los 273 casilleros de llamada
  indirecta usados ≥2 veces, apuntan a KERNEL32 66, user32 56, mss32 49, GDI32 27, ws2_32 25,
  ntdll 8, winmm 5, combase 5, oleaut32 2, wsock32 2, ole32 1; 14 apuntan a código del propio juego
  (tablas de funciones en la 3ª sección → 1ª sección), 13 están en cero, y **0** apuntan a código
  de ASProtect (ni a `.data`/`.adata` ni a memoria fuera de módulos). ASProtect no dejó APIs redirigidas.
- 🟡 Lo que sigue siendo de ASProtect: el punto de entrada (su cargador), sus secciones `.data`/`.adata`,
  y lo que haya hecho con los primeros bytes del arranque real (sin medir). Para que el volcado
  CORRA hace falta el arranque real del juego (OEP) y una tabla de imports nueva con NOMBRES
  (las direcciones de hoy cambian en cada reinicio de Windows).

## 2026-11-08 · corrida 3 — ★ dónde arranca GameGuard (leído en el volcado)

Herramienta nueva: `herramientas/leer_exe.py` (adaptada de la de R2Beat; trabaja sobre `imagen.bin`,
donde VA = offset + 0x400000). `py herramientas\leer_exe.py control` comprueba que ve bien.

- ✅ **La función que arranca GG y avisa: `0x402BB0`.**
  Llama a `0x7CE840` (el init de GG) y compara el código devuelto con **`0x755` (1877)**:
  - igual ⇒ camino bueno (`0x402CCE`), termina en `mov al, 1`;
  - distinto ⇒ elige el mensaje por código (tablas de saltos en `0x402D0C`/`0x402D30`/`0x402D78`),
    lo arma con «Game guard error : %lu» (`0x88B408`) y lo muestra con `MessageBoxA`; devuelve 0.
- ✅ **Quien decide cortar: `0x403606`**, dentro de la rutina de arranque `0x4035F0`:
  `call 0x402BB0` → `test al, al` → `je 0x403764` ⇒ **si GG falla, el arranque se abandona ahí**
  y el juego nunca llega a su red. Es el único llamador de `0x402BB0` en todo el exe.
- ✅ **Los wrappers de GG** (`0x7CE840`, `0x7CE860`, `0x7CEB30`) empiezan todos mirando `[0x949E30]`
  y, si está en cero, no hacen nada. ⇒ 🟡 si GG nunca se carga, el resto de las llamadas a GG
  quedan inertes solas: saltear el arranque debería ser consistente, no hace falta tocar más.
- 🟡 **Parche candidato (3 bytes)**: `0x402BB0` ← `B0 01 C3` (`mov al,1; ret`): GG no se inicia, no
  hay cartel, y el arranque sigue. Sin probar todavía.
- ⚠ **No se puede parchear el archivo**: esos bytes en disco están cifrados por ASProtect. El parche
  tiene que escribirse **en memoria**, después del desempaque y antes de `0x403606`.
- ✅ **Por dónde entrar**: la tabla de imports del ARCHIVO empaquetado incluye `d3d9.dll`
  (`Direct3DCreate9`), o sea que **Windows la carga antes del punto de entrada**, antes incluso del
  cargador de ASProtect ⇒ la **DLL proxy `d3d9` de R2Beat** (`R2B herramientas/dll_d3d9/`) sirve de
  puerta: desde ahí, un hilo espera a que aparezcan los bytes de `0x402BB0` y escribe el parche.
  Al ser el propio proceso no hay `WriteProcessMemory` de por medio, y GG todavía no está mirando.

## 2026-11-08 · corrida 4 — ★ reconstruir un EDA.exe sin ASProtect (`herramientas/desempacar.py`)

Objetivo: un exe que corra **sin** ASProtect. Hace falta (1) el arranque original, (2) una tabla de
imports por NOMBRE (el volcado sólo tiene direcciones de esa corrida).

- ✅ **La tabla de imports, reconstruida: 303 funciones de 16 DLL**, en 64 tiras contiguas.
  Método: cada `call/jmp dword ptr [X]` del código cuyo X guarde un puntero a una DLL; la dirección
  se traduce a nombre con la tabla de exports del ARCHIVO de esa DLL.
  ⚠ **El error que costó una hora**: el juego es de 32 bits y sus DLL viven en `SysWOW64`, pero
  Python (64 bits) abría las de `System32` ⇒ los RVA no caían en ningún export y quedaban 224 sin
  resolver. El control ahora exige que el `SizeOfImage` del archivo sea igual al del módulo en memoria.
- ✅ **El arranque original (OEP): `0x7E3A11`**, el `__tmainCRTStartup` de Visual C++: prólogo con
  manejador de excepciones y, 0x20 bytes después, `GetVersionExA`. Se llegó por estructura, no por
  firma: es la función que llama tanto a la que crea el heap (`HeapCreate`) como a la que inicializa
  los hilos (`FlsAlloc`), y **nadie la llama** (nadie llama al punto de entrada).
- ✅ **El exe reconstruido CARGA Y CORRE**: `_trabajo/volcado/eda_1/EDA_libre.exe` (6,1 MB) arranca,
  ejecuta el CRT, resuelve sus imports y llega hasta `_mtinit`.
- ⛔ **Y ahí se muere**, en `0x03AD0004`. Medido con un depurador mínimo (ya se puede: sin ASProtect
  no hay anti-debug): `EXCEPTION C0000005 en 03AD0004`, el stub al que llama `0x7E8F88`.
- ⛔ **El obstáculo que queda: ASProtect no sólo empaqueta, también EMULA las llamadas a API.**
  Un barrido recursivo desde cada función encontró **329 sitios** donde un `call dword ptr [IAT]`
  (6 bytes) fue reemplazado por un `call` a un stub (5 bytes + 1 de relleno):
  **259** van a un despachador común (`0x4760000`, que decide por la dirección de retorno) y ~70 a
  stubs propios. Cada stub hace `inc dword ptr [esp]` (saltea el byte sobrante) y salta a una región
  de ASProtect que **empieza con los primeros bytes copiados de la API real** (`mov edi, edi`).
  Seguir la cadena de saltos no llega a la API: el final está ofuscado.
  ⇒ Para un exe 100 % libre falta saber **qué API es cada uno de esos 329 sitios**.
- ✅ **Los stubs propios SÍ se pueden identificar** (`desempacar.py api_de_stub`): cada uno copia el
  comienzo de la API y después devuelve el control con `push <dirección dentro de la API>; ret`;
  ese `push` la delata (se busca el export que empieza unos pocos bytes antes).
  **42 de 92 destinos resueltos**, con nombres que cierran: `GetModuleHandleA`, `GetStartupInfoA`,
  `LoadLibraryExA`, `GetFileSizeEx`, `CreateMutexExA`, `RegCloseKey`, `CryptDestroyKey`…
  Control: el stub donde se muere el exe (`0x03AD0004`) da `GetModuleHandleA` (+12), y una dirección
  que no es stub da vacío. ⚠ Algunos caen en el nombre INTERNO de KERNELBASE
  (`RegCreateKeyExInternalA`, `CreateProcessInternalA`): hay que mapearlos al público.
- ⛔ **El despachador común (259 sitios) no cede con ese método**: no copia bytes de ninguna API,
  es código ofuscado de verdad. Se buscó una tabla que lo guiara: se volcaron **91 MB** de la memoria
  del juego original (`_trabajo/volcado/eda_2_total/`) y **ninguna** de las direcciones de retorno de
  los call-sites aparece en ningún lado ⇒ no hay tabla por sitio: es una máquina virtual.
  Y los sitios que resolvimos por contexto son APIs distintas entre sí (`MessageBoxA` en `0x402CB2`,
  `GetModuleHandleA` en `0x7E39BD`), así que no es un atajo para una sola API.

### Estado del exe desempacado y qué falta

| | |
|---|---|
| ✅ ya está | el código desempacado y legible; el arranque original; 303 imports por nombre; el exe **carga y ejecuta** |
| ⛔ falta | decirle qué API es cada uno de los **259** sitios del despachador (y 50 destinos más) |

🟡 El camino que queda es **medirlo en vivo**, no deducirlo: con el juego original ya desempacado,
enganchar el despachador y anotar, para cada dirección de retorno, en qué DLL termina la ejecución.
Hace falta entrar temprano (la DLL proxy `d3d9`, ver la corrida 3) porque el CRT usa varios de esos
sitios antes de que se pueda enganchar nada desde afuera.

## 2026-11-08 · corrida 5 — espiar al despachador con un depurador: ⛔ no sale (todavía)

Idea: correr el juego bajo un depurador propio (`herramientas/espiar_apis.py`), atrapar el
despachador y anotar, para cada llamada, en qué API de Windows termina. Lo que se midió:

- ✅ **El anti-debug de ASProtect se pasa**: borrando del PEB `BeingDebugged`, `NtGlobalFlag` y los
  flags del heap, el juego arranca normal bajo el depurador. Sin eso se mata siempre en la misma
  dirección (`0x458ABDF7`). ⚠ Y hay que devolver las excepciones como NO manejadas: ASProtect usa
  excepciones a propósito, y tragárselas también lo rompe.
- ✅ **La dirección del despachador CAMBIA en cada corrida** (`0x4760000`, `0x47A0000`, `0x4730000`):
  ASProtect lo pone en memoria que pide al arranque. Hay que leerla del `call` en el propio juego.
- ⛔ **Un freno por hardware (registro Dr0) en el arranque del juego lo mata**: mira los registros
  de depuración.
- ⛔ **Un `int3` en el arranque del juego no sobrevive**: ASProtect lo pisa al desempacar.
- ⛔ **Un `int3` en el despachador se escribe bien** (se comprueba releyéndolo) **pero no se dispara
  nunca**, y el juego acaba saliendo.
- ⚠ **Y la razón de fondo: ASProtect descifra el código del juego POR PARTES, a medida que se
  ejecuta.** Cuando los `call` testigo aparecen ya descifrados, el proceso tiene 48 DLL cargadas:
  el arranque del juego ya ocurrió y las llamadas que queríamos ver ya pasaron.

🟡 **Conclusión**: por el lado del depurador externo no sale. El camino es entrar **dentro** del
proceso con la DLL proxy `d3d9` (Windows la carga antes que nada, ver corrida 3) y mirar desde ahí:
sin depurador, sin tocar memoria que ASProtect vigile, y con el reloj a favor.

## 2026-11-08 · corrida 6 — ¿hay desempacador hecho? No. Pero sí una idea mejor: EMULAR

El tester preguntó si, siendo ASProtect tan viejo, ya existe un desempacador general. Se buscó:

- ❌ **No hay ninguno moderno que resuelva la emulación de APIs.** El más cercano es un script de
  2019 para x64dbg ([gist de Andoryuuta](https://gist.github.com/Andoryuuta/cac94bc5ac59cd6a0fba09bc8c049027)),
  que usa **exactamente el método que ya teníamos** (el stub copia el comienzo de la API y vuelve
  con `push`/`ret`, así que restando los bytes copiados sale la API) y que **no toca el despachador
  compartido**: los sitios que no encajan los imprime como «need to resolve».
- ❌ [`pstolarz/asprext`](https://github.com/pstolarz/asprext) (extensión de WinDbg) documenta la VM
  de ASProtect **1.6/1.7**, no la 2.x, está archivado desde 2021 y tampoco resuelve qué API es cada
  llamada. Eso sí, deja un dato útil: los «opcodes» de la VM **son instrucciones x86 de verdad**,
  guardadas ofuscadas.
- ⚠ Lo que sí manejaba la emulación de APIs son los scripts de la escena para **OllyDbg**
  (ASProtect 2.xx Unpacker v1.15F, scripts de VolX), de 2008-2014: en los foros de 2023 dicen que
  ya no funcionan, piden Windows XP, y vienen de sitios de cracking (riesgo real de malware).
  **No se descargó ninguno.**

### La idea que salió de ahí: no entender la VM, hacerla correr

`herramientas/emular_stub.py`: con los 91 MB de memoria del juego ya volcados, se emula el
despachador con **Unicorn**, poniéndole en la pila la dirección de retorno del sitio que se quiere
averiguar (que es el dato con el que la VM decide). Sin juego, sin depurador, sin ASProtect vivo.

- ✅ **Corre**: la VM de ASProtect se ejecuta emulada de punta a punta.
- ✅ Para los stubs propios **da la API correcta**, y coincide con lo que `desempacar.py` resolvió
  leyendo (`0x7E8F88` → `GetModuleHandleA`): dos métodos distintos, mismo resultado.
- ✅ Para el sitio del cartel, en la traza completa **se ve pasar por `MessageBoxA`** ⇒ la VM
  emulada llega a la API de verdad. El método sirve.
- ⚠ Tres cosas hubo que darle para que no se fuera por el camino de error:
  los **segmentos** (la VM lee el TEB por `fs:`), el **TEB bueno** (el primero que encontré era una
  página cualquiera con límites de pila `FFEEFFEE`; el de verdad se identifica porque su PEB dice
  que la imagen del proceso es `0x400000`), y la **pila real del hilo**, no una inventada.
  También hay que simular los syscalls: Windows los atiende saltando a 64 bits (`jmp far`) y el
  emulador es de 32.
- ⛔ **Lo que falta**: la VM llama primero a varias APIs por su cuenta (`GetCurrentProcessId`,
  `GetActiveWindow`…) y el filtro actual se queda con la primera, que es ruido.
  🟡 Esas llamadas son las mismas en todos los sitios ⇒ emular unos cuantos, quedarse con el
  prefijo común y tomar la primera que se sale de él. Eso es lo que falta probar.

**Qué sigue**: pasar GameGuard. (1) ver si este build de prueba tiene un modo sin GG; (2) si no,
volcar el exe desempacado de la memoria y saltear el arranque de GG en una copia parcheada.

## 2026-11-09 · corrida 7 — ★ las llamadas desviadas, resueltas y CONTROLADAS

Punto de partida: la corrida 6 dejó `emular_stub.py` andando pero a medio camino. Lo de esta
corrida es, sobre todo, **descubrir que el número de la corrida 6 no valía** y por qué.

### Primero: la corrida no terminaba nunca

- ⛔ El proceso del 08-nov a la noche siguió vivo **26 horas** sin pasar de los primeros 25 sitios.
  Causa: el bucle que reanuda la emulación le regala otro tanto de ejecución cada vez que la VM
  hace un syscall o pide una DLL. Un sitio que gira en falso los pide para siempre.
  ⇒ **tope por reloj** (25 s por sitio, pasado como `timeout` a `emu_start`) y por rondas.
- ✅ Dos arreglos de velocidad: el enganche de Unicorn **por bloque** en vez de por instrucción
  (100 s → 0,2 s por sitio) y el barrido de los `call` con `bytes.find` (>15 min → 16 s).
- ⚠ Y una línea por sitio en la salida: sin eso no se podía saber **cuál** colgaba.

### El error de fondo: la VM pide memoria, y se le contestaba que no hay

- ⛔ **De 274 sitios "resueltos", 272 salían por heurística y 161 "daban" `VirtualAlloc`.** Un
  juego no llama a `VirtualAlloc` desde 161 lugares distintos: era la reserva de la **propia VM**.
- ✅ **Por qué**: la VM pide memoria para trabajar. Si se la deja ejecutar de verdad, `VirtualAlloc`
  termina en un syscall —que un emulador de 32 bits no puede hacer— y se le contestaba 0: la
  reserva **fallaba** y la VM se iba por su camino de error **antes** de llegar a la API que el
  juego pidió. ⇒ Se le contesta con memoria del emulador (`ARENA`/`ASIGNAN`).
- ⛔ **Y sólo la memoria**: probando simular también `VirtualProtect`, `VirtualFree` y
  `GetCurrentProcess` fue PEOR, porque cualquiera de ésas puede ser LA API que el juego pidió y
  contestarla por él borra la respuesta (medido: `0x40B0AE`, que es `GetCurrentProcess`, dejó de
  resolverse). Las que no tienen un dato de salida crítico pueden ejecutarse: su syscall da 0,
  que en NT es éxito.
- ✅ **Señal nueva y fuerte**: entrar en una API con **el retorno AL JUEGO en el tope de la pila**.
  Tiene que ser así —el stub arma la llamada para que la API devuelva el control al juego
  directamente, de ahí el `inc dword ptr [esp]`— y ninguna llamada que la VM haga para su propio
  trabajo puede tener eso.

### Los controles (★ y el que NO sirvió)

- ⛔ **Contar los `push` del juego NO sirve de juez** (`herramientas/contar_argumentos.py`, queda
  documentada así). La idea era: los `push` antes del `call` vs. el `ret N` de la API —leído del
  código de la DLL en el volcado, no escrito a mano—. Pasa su propio control al revés (decir que
  todos son `GetCurrentProcess` choca en el 95 %), pero da 28 % de acuerdo porque **los argumentos
  se entrelazan entre llamadas**: en `0x40B0AE` el `push 0x80` es argumento de la llamada
  SIGUIENTE (`SetPriorityClass`), no de esa.
- ⚠ **Y un error de método que costó un rato**: desensamblar hacia atrás de forma lineal **se
  desincroniza**. Hay que probar varios arranques y quedarse con el que cae EXACTAMENTE en el
  sitio. Sin eso creí que `0x40AF2F` empujaba 1 argumento (cuando empuja 4) y **tomé por buena la
  respuesta equivocada** un rato. Alineado: `0x402CB2` empuja 4 con punteros a los textos de
  GameGuard ⇒ `MessageBoxA`, que es lo que se ve en pantalla.
- ✅★ **El control que SÍ es independiente: dos volcados de dos corridas.** ASProtect pone su VM
  en una dirección distinta cada vez (`0x4760000`, `0x47A0000`, `0x4730000`), así que dos volcados
  son dos mediciones separadas del mismo dato. Herramienta nueva `volcar_todo.py` (el volcador de
  los 91 MB, que era un script suelto); segundo volcado `_trabajo/volcado/eda_3`, **687 regiones,
  56 MB**. `emular_stub.py cruzar`, muestra repartida de 40 sitios:
  **de los 25 donde los dos contestan, 24 coinciden (96 %)**, y el único que "difiere" es
  `KERNELBASE!ReleaseMutex` vs `ntdll!ZwReleaseMutant` — la misma función, la pública y la interna
  que llama acto seguido. ⇒ **La respuesta no depende de la corrida.**

### Y el desvío se deshace sin agregar nada

- ✅ El `call dword ptr [casillero]` original medía **6 bytes** (`FF 15` + dirección) y el
  `call <stub>` que lo reemplazó mide **5 + 1 de relleno**: el mismo espacio. (Por eso el stub hace
  `inc dword ptr [esp]`.) ⇒ `desempacar.py` **reescribe los 6 bytes tal cual eran** y agrega el
  casillero a la tabla de imports; no hacen falta thunks ni código nuevo.
- ✅ Control del parche: en los 6 bytes tiene que haber un `call rel32` (`0xE8`). Primera prueba con
  79 sitios: **79 parchados, 0 sin `call`**, 43 APIs nuevas de 4 DLL.

### El resultado: 310 sitios, 193 restaurados, y el exe pasa la barrera

| | |
|---|---|
| sitios desviados (barrido recursivo) | **310** |
| resueltos **emulando** la VM | 194 → menos 18 imposibles = **176** |
| resueltos **leyendo** el stub (`api_de_stub`, los individuales) | **17** |
| **restaurados en el exe** | **193** |
| sin resolver todavía | **117** |

Cómo salió cada uno de los 194 emulados: 103 «de la DLL que cargó», 80 «sin confirmar con la DLL»,
9 «entró con el retorno al juego» (la señal fuerte), 2 «pedida por nombre».
⛔ 18 contestaron algo **imposible** (`ntdll!RtlRaiseException` x12, `Basep8Bit…` x6: las tripas de
otra API, o el camino de excepción del emulador que no puede abrir una ventana). Un sitio así se
cuenta como SIN RESOLVER: mejor eso que inyectarle un import equivocado (`NUNCA_SE_IMPORTAN`).

### ⚠ Dos errores propios, anotados para no repetirlos

1. **Barrido LINEAL de `0xE8`**: dio **14.295** sitios donde hay **310**, y llegó a escribir el
   parche encima de código que no era una llamada. Está dicho desde la corrida 4 y lo repetí igual.
   ⇒ La lista la hace `emular_stub.py sitios` (recursivo) y queda en
   `_trabajo/sitios_desviados.txt`; `desempacar.py` la LEE, no la calcula.
   Control nuevo en `construir`: todo casillero al que apunte un parche tiene que caer dentro de
   una tira declarada.
2. **Los casilleros nuevos no pueden arrancar en CERO.** El cargador de Windows recorre la tabla de
   casilleros hasta encontrar un cero y lo toma como el FIN de la lista: si el primero es cero,
   decide que esa DLL no importa nada y **no escribe nada**. Las 6 tiras nuevas quedaban en cero y
   el juego saltaba a la dirección 0; las 64 viejas sí se rellenaban porque traían las direcciones
   del volcado. ⇒ El casillero arranca con el mismo puntero al nombre que la otra tabla (lo que
   pone cualquier compilador).
   ★ Cómo se encontró, que es lo que vale: el exe moría en `eip=0` con `0x7E8F8E` al tope de la
   pila (= el sitio `0x7E8F88` + 6, uno de los parchados). Marcando un casillero VIEJO con
   `DEADBEEF` y viéndolo volver con la dirección real se probó que Windows **sí** procesa la tabla;
   moviendo el descriptor nuevo al primer puesto se probó que **no es posicional**; y moviéndole
   los casilleros a un hueco de `.adata` —donde ASProtect dejó basura, o sea algo distinto de
   cero— se rellenaron solos. Ahí quedó claro qué los distinguía.

### Herramienta nueva: `probar_libre.py`

Corre el exe reconstruido bajo un depurador mínimo (sin ASProtect ya no hay anti-debug) y dice
**hasta dónde llega**: la dirección de la excepción, los retornos que hay en la pila (= quién
llamó), y el valor de los casilleros que se le pidan.

- ✅ **Antes**: moría en el 1er `call` desviado, `0x7E8F88`.
- ✅ **Ahora**: carga **43 DLL**, los casilleros nuevos traen direcciones reales, pasa `0x7E8F88`
  y muere en **`0x7E9045`** — otro sitio desviado, de los 117 que faltan (su stub no existe en
  este proceso: es exactamente el síntoma esperado, no un error nuevo).

**Qué falta para el exe 100 % libre**: los 117 sitios. 🟡 Por dónde seguir, en orden de promesa:
(1) los 80 que salieron «sin confirmar con la DLL» merecen el control cruzado completo, no una
muestra; (2) los 72 que «sólo hicieron su rutina (cargó KERNEL32.dll)» se quedan cortos — la VM
carga la DLL y la emulación se corta antes de la llamada, así que hay que darle más soga a esos;
(3) para los que no cede nada, queda medirlos en vivo con la DLL proxy `d3d9` (corrida 3).

## 2026-11-09 · corrida 8 — ★ tres caminos nuevos, y la tabla de nombres de ASProtect

Tras la corrida 7 quedaban 117 sitios sin resolver. De ahí salieron cuatro hallazgos.

### 1 · Las APIs que SIMULAMOS también pueden ser la que el juego pidió (97 de los 117)

- ✅ 97 de los 117 decían «sólo hizo su rutina». La traza COMPLETA de `0x40A6A8` (30.334 bloques)
  mostró la respuesta pasando por delante: en el bloque #30238 la VM llama a `GetModuleHandleA` y
  vuelve al juego — pero `GetModuleHandleA` es una de las que **nosotros contestamos** para no
  pagar el costo de ejecutarla (`ARGS`), así que nunca se anotaba.
- ✅ Ahora se anotan con su argumento. **La regla para elegir** sale de lo medido: la VM carga su
  DLL SIEMPRE, por nombre, con el texto en SU memoria (`LoadLibraryA("KERNEL32.dll")` desde
  `0x038412B4`); ésas se descartan y lo que queda es del juego.
- ⛔ Sin ese filtro, «quedate con la última» se equivoca: en `0x64FE4E` la única que hay es la de
  la VM. Con el filtro, ese sitio queda SIN RESOLVER, que es la respuesta honesta.
- ✅ Control en `0x40A6A8`: el contador de `push` decía 6 (y `GetModuleHandleA` lleva 1), pero el
  texto que el juego empuja ahí dice **«NTDLL.DLL»** ⇒ es `GetModuleHandleA`, y los otros 5 `push`
  son de una llamada posterior. (Van dos veces que contar `push` engaña.)

### 2 · Stubs que se copian el CUERPO de la función (y los que saltan adentro)

`herramientas/emular_stub.py bytes` / `api_por_bytes`:

- ✅ `0x7E9045` → el stub hace `push 0x3BC0000; ret`, y en `0x3BC0000` hay
  `mov eax, fs:[0x24]; ret` — **`GetCurrentThreadId` entera**. Para funciones cortas ASProtect no
  salta a la DLL: se trae el código. Por eso esos sitios no tocan ninguna API.
  ⇒ Se comparan los bytes copiados contra el comienzo de cada export del volcado.
- ✅ Y 21 sitios más cuyo stub **salta dentro de la API**, unos bytes después del comienzo: el
  export que empieza justo antes es la respuesta.
- ⛔ Lo que NO se acepta: un destino que cae en una DLL pero LEJOS de todo export. Probado: daba
  9 sitios más, con destinos a **11.032 y 18.700 bytes** del export más cercano, y uno contradecía
  a la emulación. A esa distancia ya es otra función.
- ✅ Control al revés: **0 respuestas en 300 direcciones que NO son sitios desviados**.
- ✅ Control contra la emulación validada: 8 sitios en común, **7 coinciden**; el que choca
  (`0x7D75AD`) se descarta — no se elige una a dedo.

### 3 · ★★ ASProtect guarda la tabla de nombres de imports del juego, descifrada

- ✅ En `0x05378000` (memoria privada de ASProtect) está la lista clásica del CRT de Visual C++:
  `GetCurrentThreadId`, `GetCommandLineA`, `GetVersionExA`, `ExitProcess`, `GetProcAddress`,
  `GetModuleHandleA`, `TerminateProcess`, `TlsAlloc`, `HeapAlloc`, **`SetHandleCount`**,
  `GetStdHandle`, `GetFileType`, `GetStartupInfoA`, `DeleteCriticalSection`… **192 nombres**.
  Tiene sentido: ASProtect tuvo que resolver cada API por nombre al arrancar.
- ✅ **Para qué sirvió**: `0x7EC09C` copia un cuerpo que sólo devuelve su primer argumento, y hay
  CUATRO APIs con bytes idénticos (`SetHandleCount`, `GdiGetLocalFont`,
  `WTHelperProvDataFromStateData`, `InternalCStdIdentityGetIProxyManager`). De las cuatro, **sólo
  `SetHandleCount` está en esa lista** ⇒ desempate medido, no adivinado.
- ✅ Control al revés: `GetCurrentThreadId` (que sabemos por otro camino) SÍ está; una API
  plausible pero no usada (`CreateWaitableTimerExW`) y un nombre inventado, NO.
- ⚠ **Sólo vale en POSITIVO.** El barrido muestra que la lista está incompleta: de las 206
  respuestas, sólo el 40 % tiene su nombre ahí, y faltan APIs clarísimas del juego
  (`DeleteFileA`, `CreateProcessA`, `GetUserNameA`). Que un nombre NO esté no prueba nada.
- ⛔ **No hay tabla que empareje stub con nombre**: se buscaron las direcciones de los stubs en
  los 91 MB y no aparecen (lo que sí aparece son bytes de código que coinciden por casualidad).
  Confirma la conclusión de la corrida 4.
- ⚠ Detalle que costó un rato: al barrer los nombres **no sirve cortar por bytes cero**, porque en
  la tabla de imports cada nombre viene precedido por 2 bytes de «pista» que no siempre traen un
  cero. Así no se encontraba `SetHandleCount`.

### 4 · ⚠ El arranque del CRT no estaba en la lista de sitios

- ⛔ El barrido recursivo arranca desde los destinos de llamada, y **nadie llama al punto de
  entrada**: el cuerpo de `__tmainCRTStartup` (`0x7E3A11`) nunca se recorría. El exe reconstruido
  moría en `0x7E3B16`, un `call 0x47A0000` que estaba a la vista y no figuraba en la lista.
  ⇒ El OEP se agrega como raíz del barrido: **310 → 312 sitios**, y `0x7E3B16` resuelve a
  `GetCommandLineA` (que además está en la tabla de nombres de arriba).

### Herramientas nuevas

| | |
|---|---|
| `juntar_apis.py` | junta las fuentes y **descarta lo que choca entre métodos**; deja `_trabajo/apis_finales.json`, que es lo que lee `desempacar.py` |
| `progreso.py` | una ventanita con el avance en vivo de una corrida larga (sólo lee el log) |
| `emular_stub.py cruzar … --faltantes` | modo incremental: no vuelve a pagar 1,5 h cuando se agregan sitios |

### Dónde llega el exe, paso a paso (medido con `probar_libre.py`)

| restauradas | muere en | qué era |
|---|---|---|
| 193 | `0x7E8F88` | `kernelbase!GetModuleHandleA` — casillero nuevo en cero (corrida 7) |
| 206 | `0x7E9045` | `GetCurrentThreadId`, cuerpo copiado por el stub |
| 211 | `0x7EC09C` | `SetHandleCount`, desempatado por la tabla de nombres |
| 212 | `0x7E3B16` | `GetCommandLineA` — no estaba en la lista de sitios |

## 2026-11-09 · corrida 9 — ⛔⛔ No eran 312 llamadas desviadas: son **694**

El error más grande de todo el trabajo, y lo destapó el exe reconstruido al morirse en sitios
que estaban a la vista: `0x7E3B16` (`GetCommandLineA`) y `0x7E0B1A` (`GetSystemTimeAsFileTime`),
los dos `call` desviados perfectamente legibles, **ninguno en la lista**.

- ⛔ **La causa**: la lista se armaba con un barrido **RECURSIVO** desde los destinos de llamada.
  Toda función a la que no se llega desde otra queda sin recorrer: el punto de entrada (nadie lo
  llama) y las que se invocan por puntero desde una tabla. Parchearlo agregando el OEP como raíz
  (corrida 8) tapó un agujero y dejó el resto.
- ✅ **Lo que se hace ahora: VERIFICAR cada candidato** en vez de confiar en la alcanzabilidad.
  Todo `call rel32` que apunte fuera de la imagen, a memoria propia de ASProtect, y que además
  vaya al **despachador** o caiga al **comienzo de una página** (+0 o +4), donde ASProtect pone
  los stubs individuales.
- ✅ **El despachador se descubre solo**: es el destino más llamado, `0x47A0000` con **637** de
  los 694 sitios.
- ✅ **Por qué la regla no inventa**: que 637 candidatos caigan en UNA dirección concreta no puede
  ser azar — un `0xE8` desalineado lee 4 bytes cualquiera, y acertar una dirección es ~1 en 4.000
  millones. De los 14.294 candidatos crudos, 842 apuntan a memoria de ASProtect y la regla acepta
  694.
- ✅★ **El control**: la lista verificada **contiene los 312 del barrido recursivo, sin dejar
  ninguno afuera**. Superconjunto limpio.

### Un patrón más del stub, leído sin emular

- ✅ `0x7F2DFD`: el cuerpo copiado hace
  `push 0x20 · push 0x76C31810 · push 0x76B2F8BC · push 0x76BB2F3C · ret`.
  El último es el prólogo de excepciones compartido de KERNELBASE (`__SEH_prolog4`), que no es
  export de nada — por eso la cadena terminaba «lejos de todo export». Pero el tercero,
  `0x76B2F8BC`, es **la dirección de retorno: un punto DENTRO de la API real**.
  ⇒ Regla nueva: cualquier inmediato que el cuerpo copiado empuje y que caiga justo después de un
  export, es la respuesta. Da `GetModuleFileNameA`, que es lo que el CRT llama ahí. +12 sitios.
- ⚠ Y por eso `cadena_del_stub` devuelve TODOS los escalones: lo que sirve puede estar en el medio.

### Lo que NO sale por emulación (medido, para no insistir)

- ⛔ Los sitios que dicen «sólo hizo su rutina» **no se arreglan con más tiempo**: probados con el
  tope en 150 s en vez de 25, contestan lo mismo.
- ⛔ Y **el despachador no ejecuta el cuerpo de la API en su memoria**: se emuló anotando cada
  bloque y se compararon los bytes de todos los bloques de ASProtect contra el comienzo de cada
  export — **ninguno coincide**, ni en los sitios que sí resuelven.
  🟡 Conclusión: en esos casos la VM revisa algo de su entorno, no le cierra, y vuelve al juego sin
  hacer el trabajo. Eso ya no se arregla emulando desde afuera: hay que medirlo DENTRO del proceso
  (la DLL proxy `d3d9`, corrida 3).

### Dónde llega el exe ahora

| restauradas | muere en | qué es |
|---|---|---|
| 212 | `0x7E3B16` | `GetCommandLineA` (faltaba en la lista) |
| 223 | `0x7F2DFD` | `GetModuleFileNameA` (el patrón del `push`) |
| 227 | `0x7E0B1A` | `GetSystemTimeAsFileTime` (faltaba en la lista) |
| **238** | **`0x0045BF6B`** | ★ **código propio del juego, ya no un stub**: el arranque del CRT terminó |

⇒ El exe reconstruido ya pasa toda la inicialización del CRT y entra en el código del juego.
Faltan 456 de 694 sitios, casi todos del despachador compartido.

---

## Corrida 10 — 10-nov · el exe arranca el juego: el estado de la corrida, y la trampa

### 1 · Los 488 sitios nuevos, cruzados entre dos volcados

| | |
|---|---|
| contestaron los dos volcados | 304 |
| ✅ coincidieron | 243 (80 %) |
| ⛔ chocaron ⇒ descartados | 61 (20 %) |
| uno contestó y el otro no | 184 (de ésos, 35 con respuesta: `una_corrida.py`) |

⚠ **Y un reparo honesto al método**: el despachador compartido está en **`0x047A0000` en las DOS
corridas**. La VM de ASProtect **no se muda** de una corrida a otra, así que cruzar dos volcados
no es tan independiente como creía: un error determinista del resolvedor se repite igual en los
dos. Lo que el cruce sí descarta es lo que depende del heap, de los handles o del orden de carga.

Con eso, `juntar_apis.py` mete **467 de 694** en el exe (antes 238).

### 2 ·⛔ El exe no salía del archivo: salía de un volcado del juego ANDANDO

Se moría en `0x0045BF6B` leyendo `[0x931B08] + 0x18`. El dword de `0x931B08` **no es cero**: es un
puntero al heap de la corrida que volcamos (`0x048A6E38` en un volcado, `0x04922B50` en el otro).
El juego lo ve distinto de cero, cree que el objeto ya existe y lo usa ⇒ C0000005.

★ Cómo se separa el valor inicial del estado de la corrida **sin suponer nada**: comparando los dos
volcados. Lo que viene del archivo sale igual las dos veces; un puntero del heap, un handle o un id
de hilo salen distintos. `herramientas/limpiar_datos.py`:

| sección | dwords | difieren | qué es |
|---|---|---|---|
| `0x401000` | 1.188.864 | 41 | **código**: 21 caen exactamente sobre el desplazamiento de un `call` desviado y los otros 20 son el dword de al lado (el desplazamiento cruza el límite). No se toca. |
| `0x88A000` | 133.120 | 24 | datos (punteros al heap y a DLL) → a cero |
| `0x90C000` | 66.560 | **4.668** | datos: acá vive el estado → a cero |
| `.data` | 84.992 | 13 | datos → a cero |
| `.rsrc`, `0x94E000`, `0x981000`, `.adata` | 56.320 | **0** | del archivo: no se marca ni uno |

- ★ control: `0x931B08` (el que explotaba) **está** en la lista.
- ★ control al revés: comparar un volcado **contra sí mismo** da **0** direcciones.
- 4.705 dwords a cero ⇒ el exe pasa `0x45BF6B` y sigue.

### 3 ·⛔⛔ Una respuesta EQUIVOCADA es peor que ninguna

`desempacar.py` tenía un respaldo sin control: para los sitios que `juntar_apis.py` había
**descartado por chocar**, usaba igual lo que decía la lectura del stub. En `0x7D75AD` eso puso
`CryptReleaseContext` (2 argumentos) donde iba `CryptAcquireContextA` (5): la API limpió 8 bytes de
pila en vez de 20, el `ret` se llevó como dirección de vuelta un argumento que sobraba —
**`0xF0000000`, que es `CRYPT_VERIFYCONTEXT`** — y el exe murió saltando ahí, lejos del problema.

- Se sacó el respaldo.
- ★ Y se puso **la trampa** (`BASE_TRAMPA = 0xD0000000`): el `call` de un sitio sin resolver se
  redirige a `0xD0000000 + (sitio - 0x400000)`, memoria que no existe. Entonces la dirección del
  crash **dice qué sitio fue**: «⛔ el juego llegó a un sitio SIN RESOLVER: 007d75ad». Así se
  descubre cuáles de los 227 están **de verdad en el camino del arranque**, que son los únicos que
  hacen falta para que el juego abra.
- `0x7D75AD` quedó resuelto a mano, con la prueba escrita: `documentacion/APIS_A_MANO.md`
  (los 5 argumentos, y la cadena «Microsoft Base Cryptographic Provider v1.0»).

### 4 · ✅ El `call` original medía 6 bytes: 23 a 0

Si hubiera medido 5 (un `call` a un thunk), restaurar 6 le comería un byte de código real. Se midió
sobre los 206 pares de sitios seguidos y cercanos, desensamblando desde +5 y desde +6 y mirando
cuál **cae exactamente** sobre el sitio siguiente:

| cae justo | pares |
|---|---|
| los dos (x86 se resincroniza) | 183 |
| **sólo +6** | **23** |
| sólo +5 | **0** |

⇒ Nunca hay un caso que apoye los 5 bytes y contradiga los 6. La restauración en el lugar es correcta.

### 5 · Dónde llega el exe ahora

| restauradas | muere en | qué es |
|---|---|---|
| 238 | `0x0045BF6B` | el puntero del heap de la corrida volcada (§2) |
| 467 | `0x7D75AD` | el `CryptAcquireContextA` mal resuelto (§3) |
| **467 + 1 a mano** | **`0x007CF0C6`** | ★ pasa el contexto de criptografía y sigue más adentro |

🟡 Lo que queda por entender en `0x7CF0BF` (el `call` justo antes de donde muere): los 6 bytes que
siguen al sitio son **basura segura** (`salc`, `popal`, `pop es`) — no las puede ejecutar nadie. O
sea que en el juego de verdad ese `call` **no vuelve a +5/+6**: ASProtect parece haberse **robado
6 bytes de código** y ejecutarlos en su VM. Pasa en **19 de los 694** sitios (2,7 %), así que es un
caso especial, no la regla.

---

## Corrida 11 — 10-nov · ASProtect no sólo desvía: también SE ROBA código

### 1 ·⛔ Lo que destapó el crash en `0x7CF0C6`

El sitio de antes, `0x7CF0BF`, es un `call` desviado normal a la vista. Pero los **6 bytes que
siguen** son `D6 22 2A 61 49 07` = `salc; and ch,[edx]; popal; dec ecx; pop es`: **nadie puede
ejecutar eso** en modo usuario. O sea que en el juego de verdad ese `call` **no vuelve a +6**.

★ Se midió (`herramientas/robados.py`): se emula el stub y se anota a qué dirección del **código
del juego** vuelve la VM.

| sitio | vuelve a | qué significa |
|---|---|---|
| `0x40395F` | **+6** | una llamada normal: el `call dword ptr [casillero]` medía 6 bytes |
| `0x7CF0BF` | **+12** | ★ además **se robó 6 bytes** de código, los ejecuta en su VM |

- ★ el control y su revés de una vez: el sitio normal da +6 y el robado da más. Si los dos dieran
  lo mismo, la medición no distinguiría nada.
- ⚠ el tope de APIs importa: con 4 la emulación se corta ANTES de volver al juego y **todos** los
  sitios dicen «no volvió». Con 8 ya vuelven; se dejó 12.
- Pasa en **19 de los 694** sitios (2,7 %), así que es un caso especial, no la regla.

### 2 · ✅ Y se puede averiguar QUÉ decían los bytes robados

Se emula con los registros puestos en valores marcados (`eax = 0xAAAA0000`, `ebx = 0xBBBB0000`, …)
y al volver se traducen los registros y las escrituras. Para `0x7CF0BF`:

```
escribió 4 bytes en [ebx+0x2B0C] con el valor de eax (0x00008268)
⇒ lo robado era  mov dword ptr [ebx+0x2B0C], eax  =  89 83 0C 2B 00 00  (exactamente 6 bytes)
```

Y de paso quedó resuelta la API del sitio: volvió con **`eax = 0x00008268`**, que es el **PID** del
proceso volcado (`TEB+0x20`; el id de hilo, `TEB+0x24`, es `0x7E84`, distinto) y sin argumentos
⇒ `GetCurrentProcessId`. La emulación sola decía `RtlFlsGetValue`, que lleva 1 argumento: imposible.

⇒ `documentacion/CODIGO_ROBADO.md` y `documentacion/APIS_A_MANO.md`, cada fila con su prueba.

### 3 ·★★ El juez de los argumentos (lo que sí sirve, al revés de contar `push`)

Las API de Windows son `stdcall`: las limpia la propia API. Entonces, cuando el control **vuelve
al juego**, `ESP − ESP₀ − 4` **son los bytes de argumento de la API de verdad**. Medido, no contado.

| sitio | API que dijimos | medido | |
|---|---|---|---|
| `0x40395F` | `GetThreadLocale` | 0 | ✅ |
| `0x7CF0BF` | `GetCurrentProcessId` | 0 | ✅ |
| `0x403E05` | `lstrlenA` | 4 | ✅ |

`herramientas/validar_apis.py` compara eso con el `ret N` de la API que dijimos, leído del código
de la DLL en el volcado, y **tira la respuesta si no coinciden**.
★ Su control trae el revés: a `0x40395F` se le pone a propósito `lstrlenA` (1 argumento donde van
0) y el juez tiene que decir «mal». Dice «mal». ✅
⚠ Lo que no puede: si la emulación no llega a volver (la API es `MessageBoxA` y se queda esperando
una ventana) no hay medición y el sitio queda «sin juzgar». Eso no lo condena.

### 4 · ✅ El volcado TEMPRANO: los valores iniciales de las globales

`limpiar_datos.py` sabe CUÁLES globales son estado de la corrida, pero no con qué valor arrancan;
las ponía en **cero**, y para algunas eso está mal (`0x94AE64`, el puntero de locale del CRT).

★ `volcar_todo.py --temprano` vuelca en el instante justo, **sólo leyendo**, sin depurador:

- **cómo se sabe que ASProtect terminó**: desviar los 694 `call` es lo último que hace antes de
  saltar al arranque del juego. Si los 694 ya tienen su `E8` apuntando afuera de la imagen, listo.
  ⚠ Esperar un rato fijo NO sirve: a los 0,1 s de una corrida había 612 hechos y 82 sin tocar.
- **cómo se sabe que el juego no arrancó**: los testigos `0x931B08` y `0x94AE64` siguen en cero.
- se agarró a los **0,06 s** y ahí se suspende el proceso (`NtSuspendProcess`) y se vuelca.

⚠ Y una corrección a la corrida 10: **la VM de ASProtect SÍ se muda**. En el volcado temprano el
despachador no está en `0x047A0000` sino en otra parte, así que cruzar dos corridas es más
independiente de lo que dije ahí. (Que `eda_2_total` y `eda_3` coincidieran fue casualidad.)

⚠ Lo que NO funcionó: meter las **secciones de datos enteras** del volcado temprano. El exe se
quedaba sin pila en ntdll (`C00000FD`), porque en ese instante hay cosas que ASProtect todavía no
escribió. Lo que sí: cambiar **sólo los 4.705 dwords** que `limpiar_datos.py` marcó, con el valor
que tienen en el temprano. Con eso el exe carga **46 DLL** (antes 37).

### 5 · Dónde llega el exe ahora

| restauradas | muere en | qué es |
|---|---|---|
| 467 | `0x7CF0C6` | la basura del agujero de `0x7CF0BF` (§1) |
| 467 + 2 a mano + 6 bytes repuestos | **`0x007E88A5`** | dentro del locale del CRT: lee `[eax+8]` con `eax = 0` porque `[0x94AE64]` y `[ptd+0x60]` son los dos cero |

🟡 Y una cosa importante que se midió con `probar_libre.py --seguir` (que saltea las trampas para
ver TODOS los sitios sin resolver que el juego alcanza): en `0x7E88A5` **no se alcanzó ni una sola
trampa**. O sea que ese crash **no lo causa un sitio sin resolver**: lo causa una respuesta
EQUIVOCADA, o un dato. Para eso está el juez de §3, que hay que pasarle a los 467.

---

## Corrida 12 — 10/11-nov · los datos iniciales de verdad, y el bloque virtualizado

### 1 ·⛔ El método de los dos volcados tiene un agujero, y se vio

`limpiar_datos.py` encuentra el estado de la corrida comparando dos volcados tardíos. Pero **no ve
un valor de corrida que salga IGUAL en las dos corridas**. El caso que lo destapó: `0x92BE30` es
`__tlsindex` del CRT, vale `0xFFFFFFFF` en el archivo, y en los dos volcados valía **7** las dos
veces ⇒ quedaba sin marcar, y el exe arrancaba con un índice de TLS ya asignado.

### 2 · ✅ Los valores iniciales, con el proceso suspendido y avanzado de a 2 ms

Tampoco alcanza con volcar una vez temprano, porque las dos cosas **se solapan**:

| disparador | qué pasa |
|---|---|
| «los 694 `call` ya están desviados» (0,06 s) | ⛔ demasiado temprano: faltaban **63.965** dwords en `0x88A000` y **12.296** en `0x90C000` |
| «los 1.636 dwords de dato ya están escritos» | ⛔ demasiado tarde: el juego ya arrancó y pisó sus globales |

⇒ `volcar_todo.py --valores-iniciales`: se suspende el proceso en el primer instante, se lo deja
correr **tirones de 2 ms** y se lee después de cada tirón (`NtSuspendProcess`/`NtResumeProcess` y
`ReadProcessMemory`: nunca se escribe en su memoria). Mientras los testigos digan que el CRT no
arrancó, lo leído vale y se guarda. Queda **la última lectura buena**: 7 tirones, 333 páginas,
1.633 de 1.636 datos del archivo ya escritos.

- testigos de que el juego no arrancó: `0x931B08` y `0x94AE64` en cero, **y `0x92BE30` todavía
  en `0xFFFFFFFF` o en cero** (el más sensible: es lo primero que toca el CRT).
- ⇒ el exe se arma con **el código del volcado tardío + las páginas de datos del inicial**.
- ⚠ Y la global del locale (`0x94AE64`) **arranca en cero de verdad**: se midió tirón por tirón
  (tirón 4 = 0, tirón 5 = `0x04892238`). No era un dato que faltara: era un camino que no se corría.

Con eso el exe pasa toda la inicialización del CRT y **entra en el locale** (`0x7EE2A2`), que es
donde moría antes.

### 3 ·★★ ASProtect virtualiza un BLOQUE, pero sólo sobreescribe unos bytes

Esto cambia el tamaño del problema. En `0x7EE2EE` (`GetACP`) `robados.py` dice que vuelve a **+28**:
22 bytes. Pero de esos 22, **20 son código original intacto**:

```
83 F8 FC                 cmp eax, -4
75 0F                    jne 0x7EE30A
C7 05 70AB9400 01000000  mov dword ptr [0x94AB70], 1
A1 78AC9400              mov eax, dword ptr [0x94AC78]      → cae EXACTO en 0x7EE30A
```

y `0x7EE30A` es justo a donde vuelve la VM. Lo único pisado son **2 bytes** (`EF 95`, o sea
`out dx,eax`: imposible en modo usuario). O sea que la VM **interpreta el bloque entero** —
incluido el salto condicional, que es por eso que vuelve al final del bloque— pero sólo **borra
los primeros bytes**.

⇒ El agujero a reponer es chico. Y se puede medir: el tamaño del agujero es el **menor** `h` tal
que desensamblar desde `sitio+6+h` cae exactamente en el punto de vuelta.
⇒ Y para ese sitio, los 2 bytes se repusieron como `90 90`: la medición dice que su efecto es
**nulo** (al volver, `eax` tiene el `GetACP` = `0x3B5` = cp949, ningún otro registro cambió, cero
escrituras). Marcado como DEDUCCIÓN en `documentacion/CODIGO_ROBADO.md`.

### 4 ·★★★ ASProtect guarda la TABLA DE NOMBRES de imports del juego, empacada y en orden

En `0x037E2428` hay **196 nombres** seguidos, cada uno con su `hint` de 2 bytes en cero delante:
es el formato `IMAGE_IMPORT_BY_NAME` tal cual, y están **agrupados por DLL** (primero los de
kernel32, después `GetKeyboardType/LoadStringA/MessageBoxA/CharNextA` de user32, después
`RegQueryValueExA/RegOpenKeyExA/RegCloseKey` de advapi32, después oleaut32…).

De esos nombres, **154 todavía no están asignados a ningún sitio**, y son justo los que un juego
de LithTech de 2009 usaría a lo loco: `CloseHandle`, `CreateFileA`, `ReadFile`, `WSAStartup`,
`socket`, `connect`, `EnterCriticalSection`, `GetLastError`, `GetTickCount`, `Sleep`, `HeapAlloc`,
`GetProcAddress`, `MultiByteToWideChar`, `wsprintfA`, `GetPrivateProfileStringA`, `RegOpenKeyExA`…

⚠ Lo que NO está: el arreglo de punteros a esos nombres (el `OriginalFirstThunk`). Se buscó en toda
la memoria de ASProtect **cualquier** tira de 4 o más dwords que apunte a esas estructuras:
**cero**. Así que la lista da los NOMBRES pero no dice qué casillero le toca a cada uno.

🟡 Pendiente: ver si el orden de esa lista empacada se corresponde con el orden de direcciones de
los casilleros del IAT. Si se corresponde, los huecos quedan nombrados por interpolación.

### 5 · Dónde llega el exe ahora

| restauradas | muere en | qué es |
|---|---|---|
| 467 | `0x7E88A5` | el locale del CRT con `[0x94AE64]` y `[ptd+0x60]` los dos en cero |
| +datos iniciales | `0x7EE2F4` | ★ ya ADENTRO del locale: el agujero de 2 bytes de `GetACP` (§3) |
| +los 2 bytes | `0x7D512A` | ★ un sitio SIN RESOLVER, y **la trampa lo nombró** |
| +`CopyFileA` a mano | **`0x7D4FF8`** | sigue en esa misma función, más adelante |

★ Y `probar_libre.py --seguir` ahora ve las trampas de **todos** los hilos: antes sólo guardaba el
handle del hilo principal y los crashes que importan pasan en otros hilos.

---

## Corrida 13 — 11-nov · ★★★ EL EXE DESEMPACADO ABRE EL JUEGO

`_trabajo/EDA_libre/EDA_libre.exe` · md5 `bcf8e5534803bd6fdcb86383a7f5922e` · 6.139.904 bytes

### El control, que es lo que lo hace una medición y no una impresión

Se midieron **las dos** con el mismo programa (abrir, esperar, listar las ventanas del proceso
con `EnumWindows`; sólo lectura):

| ventana | clase | tamaño | original `EDA.exe` | `EDA_libre.exe` |
|---|---|---|---|---|
| `Game guard error : 361` | `#32770` | 416×156, **visible** | sí | sí |
| `LithTech` | `LithTech` | 320×200, oculta | sí | sí |
| `MSCTFIME UI` | `MSCTFIME UI` | 0×0 | sí | sí |
| `Default IME` | `IME` | 0×0 | sí | sí |

**Las cuatro ventanas, las cuatro clases, los cuatro tamaños, a los mismos 25 s.** El exe
desempacado llega exactamente hasta donde llega el original: GameGuard lo corta con el error
361 porque no encuentra su servidor de actualización. Ese muro no tiene nada que ver con el
desempacado.

- 3 corridas seguidas: **0 excepciones**, 61–63 DLL cargadas, vivo a los 25 s.
- `inventario.py`: ✅ 57 anotados · 57 en `cliente/` · **0 diferencias** (el cliente no se tocó).

### Qué tan desempacado está

| | original | `EDA_libre.exe` |
|---|---|---|
| tamaño | 2.025.472 | 6.139.904 |
| descriptores de import | 20 | 70 |
| imports POR NOMBRE | **22** | **441** |
| cadenas legibles (≥8 ASCII) | 485 | **5.612** |
| llamadas desviadas restauradas | — | **487 de 694** |

Las 207 que faltan **no se alcanzan en el arranque**: si el juego llegara a una, el `call` va a
`0xD0000000 + (sitio − 0x400000)` y `probar_libre.py` dice qué sitio fue, con nombre y apellido.

### Los últimos siete sitios, y cómo se resolvió cada uno

Todos con su prueba en `documentacion/APIS_A_MANO.md`:

| sitio | API | qué la delató |
|---|---|---|
| `0x7D8010` | `CryptGetHashParam` | `push 2` = `HP_HASHVAL` y un `mov [esp+0x14], 0x10` ⇒ 16 bytes = MD5 |
| `0x7D2281` | `ReleaseMutex` | **no** podía ser `CloseHandle`: 6 bytes después hay otro `CloseHandle` sobre el mismo handle, y el exe moría con `C0000008 INVALID_HANDLE` |
| `0x7D527C` | `RegSetValueExA` | 6 `push` con `push 4` = `REG_DWORD`, en la función que ya tenía `RegCreateKeyExA` y `RegQueryValueExA` |
| `0x7D5287` | `RegCloseKey` | 1 argumento, lo último antes del `ret` |
| `0x7E7C3A` | `MoveFileA` | 2 argumentos, y el que llama arma los dos con el mismo ayudante y selectores 1 y 2 ⇒ son dos RUTAS |
| `0x7DFCA0` | `FileTimeToLocalFileTime` | la guarda `cmp [eax],0` + `cmp [eax+4],0` ⇒ el argumento es un `FILETIME` |
| `0x87ED47` | `GetSystemTimeAsFileTime` | `sub esp,8` + `lea eax,[esp]` + 1 `push` ⇒ 8 bytes de salida, y está en `__security_init_cookie` |

### Lo que el juego hace al arrancar (sale de resolver esas llamadas)

- un **mutex con nombre** y DACL propia para la instancia única (`RtlCreateSecurityDescriptor`,
  `RtlSetDaclSecurityDescriptor`, `CreateMutexA`, `WaitForSingleObject`, `ReleaseMutex`);
- **verifica firmas RSA de 512 bits sobre hashes MD5**: `CryptAcquireContextA` («Microsoft Base
  Cryptographic Provider v1.0», `CRYPT_VERIFYCONTEXT`) → `CryptImportKey` de un blob de 84 bytes
  → `CryptCreateHash(CALG_MD5)` → `CryptHashData` → `CryptVerifySignatureA`;
- y **deriva una clave RC4** de un hash MD5 (`CryptDeriveKey` con `CALG_RC4`);
- mueve y copia archivos con el idioma «probá `MoveFileExA`; si no, `CopyFileA` + `DeleteFileA`»,
  en bucles de hasta 99 vueltas — un actualizador/parcheador;
- guarda cosas en el registro (`RegCreateKeyExA` / `RegQueryValueExA` / `RegSetValueExA`).

🟡 La clave RC4 derivada de MD5 es la pista más concreta que apareció para el protocolo: es muy
probable que el tráfico del «Broker» vaya cifrado con RC4 y la clave salga de algo que el cliente
hashea. Eso se mira cuando se pase GameGuard.

---

## Corrida 14 — 2026-11-10 · ★★★ GameGuard pasado, y la **IP del Broker**

### 1. El muro de GameGuard era un solo `if`

Medido con `leer_exe.py` sobre el volcado:

```
0x4035F0   el arranque del juego (método virtual, lo llama el shell de LithTech)
  0x403601   call 0x4026D0   subclasa la ventana: SetWindowLongA(hwnd, GWL_WNDPROC=-4, 0x4026C0)
                             para recibir los avisos de GameGuard (mensajes 0x3E9..0x3F9, el
                             switch está en 0x402100)
  0x403606   call 0x402BB0   ★ EL MURO: devuelve AL=1 si GameGuard está bien, 0 si no
  0x40360D   test al,al / je 0x403764  ->  `mov eax,1; ret 8`: se corta el arranque
  0x403613   push 0x181 / call 0x7793C0  ->  sigue el juego
```

`0x402BB0` pide el código de error (`0x7CE840` → `0x7CEFB0`, que loguea «InitNPGameMon: %lu» y
devuelve `[0x949E30+0x10]`) y **acepta un único valor: `0x755`**. Cualquier otro —el `0` incluido—
cae en un switch de tres tablas que elige el texto y lo muestra con `MessageBoxA`; el 361 que
veíamos (`0x169`) sale por la tercera tabla. GameGuard está **estático dentro del exe** (la cadena
`--- NPGameLib.lib version %d : %hs ---` está en los datos): no es una DLL que se pueda no cargar.

Las tres recetas de `herramientas/sin_gameguard.py`, todas probadas:

| receta | qué toca | resultado medido |
|---|---|---|
| `emular` | `0x7CE840` → `mov eax,0x755; ret` | pasa; el juego recorre su camino de éxito de verdad |
| `nop` | `0x403606` → `mov al,1; nop×3` | pasa; el juez no se llama nunca |
| `fuera` | `0x7CE890` → `xor eax,eax; ret` + el `0x755` | pasa y GameGuard **no arranca**, pero muere: el camino de éxito de `0x402CCE` lee `[0x92CEAC]` sin comprobarlo |
| ★ `limpio` | `0x7CE890` → `xor eax,eax; ret` + `0x403606` → `mov al,1` | **la buena**: ni GameGuard ni juez |

★ Por qué hace falta `limpio` y no alcanza `emular`: con `ventanas.py` —que ahora anota los
**procesos nuevos**— se vio que quien abría `gameguardfaq.nprotect.com/con_02.html` era
**`GameGuard.des` corriendo como PROCESO aparte**, que el juego lanza a los 0,4 s con una línea de
comando cifrada y que a los 23 s, al no encontrar su server, abre el navegador. `0x7CE890` es el
init de NPGameLib (hace el `new` de `0x2B98` bytes y lo guarda en `0x949E30`); si devuelve 0 sin
crear nada, el objeto nunca existe y todas las demás entradas de la librería (`0x7CE840`,
`0x7CE860`, `0x7CEB30`, `0x7CEB80`) empiezan con un `test` sobre `0x949E30` y se van sin hacer nada.

### 2. Lo que hizo falta después del muro

| sitio | qué era | qué lo delató |
|---|---|---|
| `0x7792FA`, `0x622ED5`, `0x4E78EE` | `GetModuleFileNameA` | el `push eax` viene de un `GetModuleHandleA(NULL)` y la trampa midió `arg1=0x00400000` |
| `0x65091C` | `GetTempPathA` | la aritmética de la pila exige 8 bytes, y `0x154−12 = 0x148` vuelve al mismo buffer |
| `0x650941` | `GetTempFileNameA` | 16 bytes medidos = `ret 16`, y el sitio hermano `0x43A580` tiene el **mismo idioma** argumento por argumento; «cfx» mide 3 caracteres, lo único que la API usa del prefijo |
| `0x7EDC3D`, `0x7EDBCA` | `WriteFile` | `errno = 0x1C` (`ENOSPC`) en `0x7EDC80`: la función es el `_write` del CRT |
| `0x7E1A55` | `GetSystemTimeAsFileTime` | le resta `0x019DB1DED53E8000` y divide por 10.000.000: es `_time64` |

★ Y **14 huecos de código robado** repuestos (8 → 36 bytes). Todos la misma receta `mov <reg>, eax`,
y en cada uno **el código de después lee justo ese registro**. El que destapó la clase:
`0x4E5025` (`lstrlenA`). Sin el `mov esi, eax`, `esi` quedaba con basura y `MultiByteToWideChar`
recibía `0x0093E136` como largo de la cadena `"192.168.1.10"` — **leído de la pila**, no deducido:
`probar_libre.py` ahora imprime los argumentos de verdad y el módulo donde cayó la excepción.

⚠ Y dos que **no** hay que reponer (`0x423EFB`, `0x4240C2`): ahí el hueco todavía tiene el `8B C6`
original. Virtualizar un bloque no siempre pisa bytes.

### 3. ★★★ A dónde se conecta el juego

Con `herramientas/conexiones.py` (la tabla TCP del proceso con su PID dueño; **sin driver, sin
UAC, sólo lee**):

```
  1.4s  UDP escuchando en 57654
  1.6s  TCP -> 218.145.66.187:25000  (SYN_SENT)
```

`218.145.x.x` es rango coreano (KORNET). El puerto **25000**. Y de dónde sale:

- ❌ **no** está en el exe (se buscó la cadena, el dword en orden de red y al revés, y `push 25000`);
- ❌ **no** está en ningún archivo del cliente en claro (barrido byte a byte de los 57, `Data.dat`
  incluido);
- ❌ **no** está en el registro (`HKLM\SOFTWARE\WOW6432Node\Softnyx\EdaIS` sólo tiene `Location`,
  `Version` y `OperatorA`);
- ❌ **no** está en `EdaENGTest.ini`: se sacó el archivo de la copia y el juego conectó **al mismo
  lugar** (control al revés);
- ✅ **está en un XML comprimido dentro de `Data.dat`**, y se vio con `buscar_en_memoria.py`
  buscándolo en el proceso ANDANDO:

```xml
<?xml version="1.0" encoding="utf-8"?>
<SERVER>
 <ITEM IP="218.145.66.187" PORT="25000" SERVICE="12"/>
</SERVER>
```

Un solo servidor. Y alrededor, en la misma zona de memoria, está el resto de la base de contenido
descomprimida de `Data.dat`: `<MAP PATH="...">`, `<SCRIPT PATH="...">`, `MISSION="1011"`,
`BRIEFING=`, `EXP="128"`, `RANKRAT...`, `CLEAR...`. Por eso el barrido en claro no lo encontraba:
`Data.dat` usa zlib (y Lua 5.1.4).

★ Es, literal, la regla de LEEME.md: **si el exe no contesta, la respuesta está en otro archivo**.

### Cómo se conecta, en el código

```
0x74EB30   el Connect del helper TCP
  0x74EB51   socket(AF_INET=2, SOCK_STREAM=1, IPPROTO_TCP=6)
  0x74EB6D   WSACreateEvent / 0x74EB87 WSAEventSelect(s, ev, 0x33)
  0x74EBA2   connect(s, this+0x94, 0x10)      <- el sockaddr_in vive en this+0x94
0x74E420   SetAddr(this, const char* ip, u_short puerto)
  sin_family = 2 ; inet_addr(ip) -> sin_addr ; ntohs(puerto) -> sin_port
```

⚠ `connect`, `socket`, `gethostbyname` y compañía **no** son llamadas desviadas: van por el
casillero de imports de verdad (`ws2_32` es una de las 22 DLL que el exe declaraba sin empacar).
Por eso no aparecen en `apis_finales.json`.

🟡 Lo que sigue: el juego manda su primer paquete a ese host:puerto y nadie contesta. Hay que
ponerse en el medio (WinDivert, o levantar la IP en una interfaz local) y **mirar los bytes**. Ahí
se verá si el RC4 derivado de MD5 cifra el primer mensaje o si el server habla primero.

---

## Corrida 15 · 10-nov-2026 — ★★★ el primer paquete del Broker, DESCIFRADO

**Qué se hizo.** Ponerse en el medio de `218.145.66.187:25000` con WinDivert
(`herramientas/espiar_broker.py`, la opción A de `SIGUIENTE_PASO_RED.md`) y un oyente que **sólo
guarda bytes y no contesta nada**. Después, breakpoints dentro del juego andando en las funciones de
cifrado del propio exe (`herramientas/espiar_cripto.py`) para ver con qué se cifra.

### 1 · El redirector anda — con sus controles

```
✅ el filtro de WinDivert compila
✅ SIN espía, 218.145.66.187:25000 NO conecta (timed out)          <- el revés: el server está muerto
✅ CON espía, 218.145.66.187:25000 conecta
✅ los bytes mandados a mano llegan IDÉNTICOS al .bin
✅ CON espía, el puerto 25001 NO conecta, y no aparece en el oyente  <- agarra sólo lo suyo
```

Y el del juego: `conexiones.py` (dentro de `espiar_broker.py juego`) muestra la conexión del juego a
`218.145.66.187:25000` en **ESTABLECIDA** — antes quedaba en `SYN_SENT`. La redirección tomó.

### 2 · ★ El cliente habla PRIMERO: 72 bytes

```
44 00 00 0c 40 00 02 02  23 79 ee 3a 6e b6 9c d9 08 69 68 51 31 f9 3b 55 ...  (72 bytes)
```

Llega a los ~0,01 s de aceptar. Después **nada**: a los **10,0 s** el cliente cierra la conexión
(medido dos veces: 10,01 y 10,00 s). ⇒ ~~espera una respuesta del server con un timeout de 10 s~~
⛔ **FALSO, corregido en la corrida 16**: a los 10 s el juego se cerraba solo (GameGuard).
En dos corridas sin depurador los 72 bytes salieron **idénticos byte a byte**.

### 3 · Lo que NO es (dos hipótesis que se cayeron midiendo)

- ⛔ **No es la CryptoAPI de Windows.** El exe tiene la cadena entera (MD5 → `CryptDeriveKey(RC4)`,
  RSA-512, ver `APIS_A_MANO.md`), pero con breakpoints en **todas** las `Crypt*` de `cryptsp.dll`
  el juego manda el paquete **sin llamar a ninguna**: las que se ven son de Windows verificando
  firmas de DLL (no tienen ni un retorno al exe en la pila). La pista del RC4 era falsa para esto.
- ⛔ **No es «rand() sin sembrar»** (la hipótesis de por qué sale igual cada vez): el hilo
  principal se siembra con la hora a los 0,0 s. Pero midiendo eso apareció lo siguiente.

### 4 · ★ Cómo se arma, medido con breakpoints en el exe

El objeto de red (`ecx = 0x934440`) se configura en `0x4E7860..0x4E78CD`, justo antes de conectar:

```
0x4E7876  0x74C900(clave16, 0xA5C2A2B6)   crea el contexto de cifrado y le pone la clave
            0x750CA0 -> 0x6242E0(0xA5C2A2B6)     el contexto
            0x750B90 -> 0x7A99F0(clave, 16, 3, ctx)
                  el contexto queda:  04 00 00 00  0a 00 00 00  <clave>  <44 palabras más>
                                      Nk = 4       10 rondas    ⇒ AES-128 (key schedule)
0x4E789C  0x7A9840(this, 0xA8F4, 0x2A4)   un RSA DE JUGUETE: srand(0x2A4) (semilla FIJA),
            dos índices al azar entre 5 y 44 -> 0x7A96E0(i) = el i-ésimo primo < 200,
            n = p·q, φ = (p-1)(q-1), e = 0xA8F4, d = 0x7A9770(e, φ) (Euclides extendido).
            Recalculado en Python: p = 181, q = 29, n = 5249 (= 0x1481, lo que llega a 0x74C930) ✓
            0x7A98C0 cifra BYTE A BYTE, cada byte en un dword (0x7A97E0 = potencia modular)
0x4E78B7  0x74C930(n, e, d)                carga ese RSA en el objeto     (flag +0xF)
0x4E78C8  0x74C8C0(0x0202)                 la versión, que va en claro en la cabecera

al mandar:  0x7447F5 -> 0x74CD85 -> 0x750BE0(datos, 44, salida, 64)
              -> 0x624140(ctx, datos, 48, salida, 64)      48 = 44 redondeado a 12
            0x4E5C34 -> 0x7449C0 -> 0x74F464 -> 0x74F0A2 -> 0x74ED12  send(72 bytes)
```

### 5 · ★★★ El formato, comprobado descifrando con AES de verdad (pycryptodome)

```
cabecera EN CLARO (8):  u16 largo = total-4 (0x44)  ·  u16 00 0c  ·  u16 largo cifrado (0x40)
                        ·  u16 versión 0x0202
cifrado:                AES-128-ECB, clave f5dda6fb559514fb880cb360fcdfa0b2
                        cada bloque de 16 = B6 A2 C2 A5 (0xA5C2A2B6) + 12 bytes de datos
datos:                  u16 largo = datos-4 (0x28)  ·  u16 comando (0x0604)  ·  cuerpo (40)
                        y lo que sobra hasta múltiplo de 12 es basura de la pila
```

Descifrando las 6 capturas, **los 4 bloques de cada una empiezan con la magia**. El revés: con
una clave de ceros sale ruido y la magia no aparece. Y `paquete_broker.py control` comprueba
contra las capturas reales que **abrir → armar devuelve los mismos 72 bytes**, y que un bit
cambiado o una clave equivocada se rechazan.

🟡 **El cuerpo del 0x0604** (las dos corridas sin depurador, idénticas): 20 caracteres de 16 bits,
casi todos ASCII con `:` cada pocos, y algunos alterados. Contiene trozos de la MAC de uno de los
adaptadores de esta máquina ⇒ **deducción**: es una huella del equipo (un id de hardware). Los
valores no se anotan acá (son de la máquina de el tester). ⚠ Bajo el depurador el cuerpo sale
**distinto** (ceros y punteros de la pila): el juego arma otro 0x0604 si lo están depurando, o
el camino que lo llena no corre igual. Para el server sirve el de las corridas sin depurador.

🟡 **Sin medir todavía**: qué es el `00 0c` (¿el `SERVICE="12"` del XML?), si el server contesta
con la misma clave, y para qué está el RSA de juguete (el primer paquete no lo usa; candidato:
la respuesta del server, o un paso siguiente del login).

⏭ **Lo que sigue**: qué CONTESTA el server al 0x0604. Hay que encontrar dónde el cliente descifra
lo que recibe (el otro método de bloque es `0x750C30`, que redondea a 16) y el despacho por
comando. Con `espiar_broker.py` ya se le puede contestar cualquier cosa armada con
`paquete_broker.armar()` y ver con `espiar_cripto.py` por dónde la procesa.

---

## Corrida 16 · 10-nov-2026 — ★★★ LA LISTA DE SERVIDORES: el cliente llega a su primera pantalla de verdad

### 0 · ⛔ Una corrección a la corrida 15

Ahí dice que el cliente «espera una respuesta del server con un timeout de 10 s». **Es falso.** Lo
que pasaba a los 10 s era que **el juego se cerraba solo**, siempre, conectado o no: lo medido
abajo (§4). La conexión se cortaba porque moría el proceso.

### 1 · El intercambio con el Broker, mensaje por mensaje (todo medido)

Con un oyente que contesta por reglas (`espiar_broker.py contestar` / `reglas_broker.py`) y
breakpoints en el ruteador del cliente (`espiar_cripto.py`, `EXE_PUNTOS`):

```
C→B  0x0604  44 B   la huella del equipo (texto UTF-16 de 40 bytes, sale de 0x623E60()+0xF0)
B→C  0x0607   6 B   OnPktB2CNATTYPEInit: u32 IP + u16 puerto (orden de host) del «UDP label»
C→B  UDP 0x3002     cada 0,4 s, EN CLARO: [u16 largo][u16 0x3002] + huella(40) + IP:puerto local
B→C  0x0609  10 B   el tipo de NAT: [u8 tipo 1..8][3 de relleno][u32 IP pública][u16 puerto]
                    («1: public, 2: Full Cone, 3: IP Resticted, 4: Port Resticted 5:Symmetric
                    6:Unknown 8:Block» — la cadena está en el exe)
     (si en 4 s no llega el 0x0609, el cliente manda 0x060C: el camino de «NAT bloqueado», que
      espera 0x060B «RECONFIRM BROKER IP,PORT»)
C→B  0x0708   5 B   un byte 0 (pide el anuncio)
B→C  0x0709 449 B   [u8 hay anuncio] + 448: u32 · título UTF-16[40] · u32 · cuerpo UTF-16[400]
C→B  0x070A   5 B   un byte 0 (pide la lista)
B→C  0x070B         [u16 resultado = 1][u8 N] + N × 96 bytes (un registro por servidor)
```

Las pantallas registran sus manejadores por comando (`0x546080`: `COpenningScreen` con 0x0607,
0x0609, 0x060B, 0x3003; `0x549FC0`: la lista con 0x070B, 0x1010, 0x0709). El ruteador del Broker
(`0x4E5690`) manda 0x1003..0x100B a un objeto y **todo lo demás a la pantalla actual**.

### 2 · El registro de servidor (96 bytes), medido en pantalla

`0x53E300` lo copia; `0x516DD1` lo pinta; `0x549300` (ENTER) lo usa:

| offset | qué es | cómo se supo |
|---|---|---|
| `+0x03` | **el nombre**, UTF-16, 40 bytes | se ve en la lista |
| `+0x2B` u32 / `+0x2F` u16 | **IP y puerto del server de juego** | ENTER desconecta del Broker y conecta ahí (`0x744750`); con alguno en 0 no hace nada |
| `+0x33` u16 / `+0x35` u16 | **máximo / jugadores** | el estado es jugadores/máximo: < 0,3 **[Open]**, < 0,6 **[Normal]**, < lleno **[Busy]**, si no **[Full]** — las cuatro vistas en pantalla con 10, 45, 80 y 100 de 100 |
| `+0x5F` u8 | **abierto** | con 0 ENTER muestra el error 5; con 1/2 la fila sale enmarcada |
| `+0x00`, `+0x01`, `+0x31`, `+0x32`, `+0x37` | 🟡 sin saber | `+0x31` ENTER se lo pasa a la conexión |

Las cadenas del cliente se copian con **`wcscpy`** (`0x7DDBF9`): todo texto viaja en UTF-16.

### 3 · ★★ La clave AES es MD5(el exe + 0x00)

Al resolver más llamadas el exe cambió y **la clave cambió con él**. Medido con breakpoints:
`0x4E781D` `GetModuleFileNameA` → `0x624CB0` → `0x624990`, que **abre el propio exe** (visto el
`CreateFileA` de `0x624B45`), lo lee entero en un buffer de **tamaño + 1** y le saca el MD5 al
buffer completo; devuelve el hexa en mayúsculas (`95D314EB…`, visto en memoria) y `0x624CB0` lo
pasa a bytes con `"%2x"`. Si el archivo no se puede leer, usa una clave fija (`0x624D1D`).

```
md5(EDA_limpio_494.exe + 00) = f5dda6fb559514fb880cb360fcdfa0b2   = la medida en la corrida 15
md5(EDA_limpio_499.exe + 00) = 95d314eb1da27dcd01a2e81f5493833d   = la medida hoy
md5(EDA_limpio_494.exe)      = 4ee184d9…                          ≠ (el revés: sin el 00 no da)
```

⇒ un **control de integridad**: un cliente tocado no se entiende con el server. 🟡 Para el
`EDA.exe` original de 2009 sería `a57ca836788301a9aff975159cbcbe97` (deducción: la misma fórmula;
no se puede medir porque el original se corta en GameGuard). El server real conocería los hashes
de los exes publicados. El nuestro prueba los conocidos: la magia de cada bloque dice cuál anduvo.

### 4 · ★ Por qué el juego se cerraba a los 10 s: GameGuard, otra vez

Con breakpoints en `PostQuitMessage` y en `ILTClient::Shutdown()` (`0x40FC40`, la tabla de
LithTech en `0x90F898`): lo llama **`0x402ECC`**. `0x402E80` corre en cada cuadro y **cada 10 s**
(`cmp eax, 0x2710`) le pide a NPGameLib su estado (`0x7CEAD0`); si no es `0x755`, cierra. Con la
receta `limpio` NPGameLib no existe y devuelve 0 ⇒ cierre seguro. Antes, encima, el cierre caía en
destructores con llamadas sin resolver y por eso parecía un crash.
⇒ tercer parche de `limpio`: **`0x402EC4` `je` → `jmp`** (1 byte). El otro chequeo de esa
función («d3ddevice» == «d3d9.dll») no se toca. Medido: el juego queda vivo 60 s y más.

### 5 · Cinco llamadas desviadas más (`APIS_A_MANO.md`): 499 de 694

`0x77A347` y `0x77AABB` `FreeLibrary`, `0x5CE2C7` y `0x5CE347` `QueryPerformanceFrequency`,
`0x775DDD` `UnregisterClassA`. Todas en el camino de cierre (destructores) o en esperas finas.

### 6 · Lo que se ve

`herramientas/foto_juego.py` (PrintWindow, con su control): la pantalla **«E.D.A — Espada De
Alma · ANUNCIO / LISTA DE SERVIDORES»**, con el panel NOTICE y la lista «SEVER LIST | STATUS»,
ENTER y CLOSE. Con nuestro guion muestra el anuncio «EDA vuelve» y el servidor «EDA Local [Open]».
La interfaz está en **castellano** (es el cliente latino).

⏭ **Lo que sigue**: apretar ENTER. El registro apunta a `218.145.66.187:25000`, así que la
conexión al «server de juego» también pasa por el espía, y lo primero que mande el cliente queda
en `_trabajo/broker/con_NNN.bin`.

### 7 · ★★★ ENTER → el server de juego → SELECT CHARACTER (con el tester apretando ENTER)

```
C→S  0x100F  237 B  IP local (UTF-16), una MAC (UTF-16), ★ el md5 del exe EN TEXTO
                    ("1343DD9C…" = md5 de EDA_limpio.exe, sin el 00), y las direcciones del NAT.
                    ⚠ NO trae usuario ni clave: la cuenta venía del launcher (-cmdfile)
S→C  0x1010   12 B  u16 resultado (1 = OK) · u32 🟡 (→ +0x2B8) · u32 🟡 · u16 🟡   (`0x5496C0`)
                    → cambia a la pantalla SELECT CHARACTER
C→S  0x1011    8 B  u32 1 (pide la cuenta y los personajes)
S→C  0x1012         33 B: u16 resultado · 26 🟡 de la cuenta (ahí van el Gold y el Cash) ·
                    u16 N1 · u16 N2 · u8 N3, y N1×21 + N2×36 + N3×186 (🟡 los personajes)
                    (`0x544820`)
```

Dos trampas que costaron una vuelta cada una (las dos medidas):

- ⚠ **La IP del registro de servidor va en orden de RED**: ENTER le hace `inet_ntoa` directo.
  Con el orden del 0x0607 el cliente se fue a `187.66.145.218`, esperó ~28 s y dijo «Can't
  Connect to server. Refreshing Server list.» (lo vio el tester).
- ⚠ **El segundo u16 de la cabecera es `[u8 0][u8 SERVICIO]`**: con el Broker es `0x0C` = 12,
  el `SERVICE="12"` del XML de `Data.dat`; con el server de juego es el `+0x31` del registro.
  Y **el cliente TIRA todo paquete cuyo servicio no coincide** (`0x744910`, comparando con
  `[helper+0xC4]`, que ENTER llena con `+0x31`): con el registro en 1 el 0x1010 llegaba (se vio
  el `recv`) y nunca se descifraba. El oyente ahora contesta con el mismo campo que recibió.

Con 0x1012 «sin personajes» la pantalla queda lista: 5 lugares vacíos, «0 Gold · 0 Cash», y los
botones Select Server / Create Character / Delete Character / Enter Lobby.

### 8 · ★★★ CREATE CHARACTER: «Character Creation is Complete» (con el tester apretando)

```
C→S  0x1013  32 B   u32 lugar (0) · u16 clase (1 = Warrior) · nombre UTF-16
S→C  0x1014         u16 resultado (1 = OK; 0x8FD.. errores) + 1 personaje de 186 bytes
                    (`0x544A40`) → lo agrega, lo dibuja y dice «Character Creation is Complete»
C→S  0x1001   5 B   «estoy vivo», cada 20 s desde el 0x1010. Sin respuesta, al rato el cliente
                    arma solo un 0x1003 y sale «conexión inestable» (lo vio el tester). 🟡 Se
                    contesta con el mismo 0x1001 y la conexión aguanta.
C→S  0x1017   9 B   ENTER LOBBY: u32 · u8 (🟡)
S→C  0x1018         cabecera de 16 (resultado · … · N1 · N2) + N1×10 + N2×13 → pantalla 3
```

Lo que costó llegar, en orden (cada paso medido):

- **Los lugares no se podían clickear**: `0x4FA4E0` habilita los primeros N con N = el byte
  `+0x2CB` de la cuenta = **byte 0x19 del 0x1012**. Con 0 «Create» decía «no hay personaje».
- **El 0x1012 trae Cash y Gold**: `cuerpo[0x0F]` = Cash, `cuerpo[0x13]` = Gold (en pantalla).
- **Cuatro crashes del juego, y ninguno era del protocolo**:
  1. `0x40AB72` sin resolver — y era **el manejador de crashes del juego** (escribe
     `EDA_limpio.dmp`/`.rpt`): por eso el `.rpt` nunca mostraba el crash de verdad. Resuelto
     (`GetCurrentProcessId`); desde ahí el `.rpt` nombra el lugar real.
  2. `0x7C57AE` sin resolver (Lua `loadlib.c`): `GetModuleFileNameA`, y de paso `0x7C5861`
     `FormatMessageA` y `0x7C59BE` `FreeLibrary`.
  3. `0x4ED92D` con un índice −1: **la CLASE va en `+0x04` del personaje**, desde 1. Medido
     con el depurador y la pila completa (hubo que leer 32 KB: `0x57F9A0` tiene 9,5 KB de
     locales): para dibujar el modelo, `0x4F9610` arma un flujo `[+0x04][+0x1F][nombre][9
     ítems de +0x72]` y el objeto del modelo usa `+0x04 − 1` como índice. ⛔ Descartado antes:
     que faltaran campos detrás del personaje (con ellos murió igual).
  4. EIP = `0x047A0000`: ★ **ASProtect virtualizó una función ENTERA**, `__EH_prolog`
     (`0x7E4510`, 210 llamadores): en el exe había `jmp 0x47A0000` + basura. Repuesta con sus
     31 bytes de siempre (calzan al byte con la función siguiente). Lo sospechó el tester («¿no es
     un problema del exe limpio?»): tenía razón. Barrido: es la única así.

Y la pantalla muestra el personaje: retrato, «rui», el modelo del Warrior posando en el centro.
🟡 `+0x28` NO es el nivel (con 1 sale «0LV (1/0)»).

### 9 · ★★★ EL LOBBY

Con el 0x1018 OK (cabecera de 16, listas vacías) el cliente pasa a la pantalla 3: **LOBBY**, con
«rui» y el modelo del Warrior con su espada, las pestañas Shop / Inventory / Clan / Messenger /
Options / Select Character / Exit Game, la lista **Scenario** (Number · Stage Name · Room Title ·
Participants · Status), Search Stage / Create Stage / Enter, el chat y la lista de usuarios. Las
estadísticas del personaje (Strength, Constitution, Dexterity, Intelligence, Wisdom, Quit Rate,
EXP «(1/0)») salen en 0: son campos del registro de 186 bytes que todavía no se conocen.

★ Las reglas ahora mandan «rui» ya creado en el 0x1012 (N3 = 1): las reglas no tienen memoria.

⏭ **Create Stage** abre el selector («Chapter 1 · Start of the Search 1Lv~3Lv», el texto del
Proyecto Gaia) y queda en «Target search……» / «voice loading……» **sin mandarle nada al
server** (medido: después del 0x1017 sólo hay 0x1001 cada 20 s). Los datos del capítulo salen
del juego (en memoria, ya parseados: `CHAPTER … 1011`, «Start of the Search»). 🟡 Candidatos a
lo que falta, sin medir: la lista N1 del 0x1018 (registros de 10 bytes que van a un mapa con
clave u32 + dos bytes por entrada, en `+0x444` del personaje: parece progreso por misión) o
algo del propio exe armado. Hay que leer el código de esa ventana.

### 10 · ★★★ LA SALA DE ESPERA (WAITING ROOM) — todo en piloto automático

- **El selector de stages anda**: se abre una stage con **DOBLE clic en su marcador**. Antes se
  midió que no faltaba nada: `0x6209F0` («¿escenario disponible?») contesta 1 para el 1011 y 0
  para los otros 49 (cada uno exige haber terminado el anterior), y en todo el camino no se
  alcanzó ni una trampa.
- **El nivel y la EXP**: `+0x1F` y `+0x20` del personaje (`"%dLV"`, medido con un breakpoint en
  `_woutput`, `0x7F1043`). «rui» sale «1LV» y «(11/300)». ⛔ La prueba anterior que decía «no
  están en el registro» estaba mal: los valores de prueba se pisaban.
- **No hay tutorial** en el cliente (ni en el exe ni en la memoria, ASCII y UTF-16).
- **Escribir sin teclado**: el texto entra por el objeto del IME (`[0x949530]`, procedimiento
  `0x77A4D0`), que subclasea un `Edit` oculto. Un `WM_CHAR` a ese `Edit` llena su buffer
  (`obj+0x1C`), y el **Enter** lo pasa al campo — y en el título de la sala, además, **manda el
  0x101D** (Enter = Create). `clic_juego.escribir` y `piloto.py sala` lo hacen solos.
- **0x101D / 0x101E** (crear sala): la sala viaja serializada ENTERA (con el lugar de su
  vtable). ⚠ En la respuesta los 89 bytes empiezan en el +0 del objeto: con el corrimiento de 4
  bytes el escenario quedó basura y el cliente murió en `0x5367D4` (`0x4EE7D0` devolvió NULL).
- Con el 0x101E bien armado: **WAITING ROOM** «EDA vuelve» — mapa, «Start of the Search», EASY,
  la misión, el briefing, F9 Start Game, Leave Room, y las pestañas Title Change / Password /
  Inventory / Messenger / Invite. ⏭ Dice «0 Players» y el panel de jugadores está vacío: los
  miembros de la sala vienen en otro mensaje.

### 11 · ★★★ F9 START GAME → la partida CARGA el mapa (y espera la largada)

- **Lista de jugadores**: `+0x2F` de la sala = **máximo de jugadores** (con 0 decía «0 Players»
  y no había lugares; con 3, tres). El jugador local se agrega solo, como anfitrión («1LV rui
  0 ms» con la casita).
- **F9** manda `0x104E` (u8) y espera **`0x104F`** (`0x54F170`): 8 bytes (u16 · u32 → partidas
  del personaje · u8 · u8 N) + N × 68 (`[u8 índice en la sala][9 × 7 bytes: equipo]`). Con eso
  pasa a la pantalla 8, la partida.
- Dos llamadas desviadas más en el camino (505 de 694), listadas en UNA corrida con
  `EDA_SEGUIR=1 espiar_cripto.py` (anota y saltea cada trampa): `0x7E0806` `GetCurrentThreadId`
  (`_threadstartex` de la CRT) y `0x7E0AD7` `GetSystemTimeAsFileTime` (`clock()`).
- La partida **carga de verdad**: NetTrace.log dice `Thread Do Start` · `m_pLoadingScene->Start()
  Succeed` · `RunScenario Succeed` · `OnEnterWorld!!` · `LoadingEnd`; el cliente le avisa al
  server `0x105C` («Briefing_01»: el primer evento del guion Lua) y `0x105F` (u32 🟡). En
  pantalla: la ilustración de carga y «NOW LOADING».
- ⏭ **Y ahí espera**. Medido (muestreando el hilo principal): está en el `while (!this[0xE0])
  Sleep(1)` de `OnEnterWorld` (`0x500643`), y sólo lo destraba el callback `0x510D50` cuando le
  llega un paquete con comando **1** por el canal de mensajes **9** de `[0x92CF54]+4` (lo
  registra `0x515640` al armar la escena de carga). Bajo el depurador: **nunca se lo llama**. El
  TCP no ve nada parecido y el cliente no mandó UDP: es la **largada que da el server de la
  partida** (LithTech va por UDP: `SendC2RUDPConnect` = cliente → *relay*). Es el próximo frente.
- ★ Todo esto en piloto automático: `piloto.py partida` abre el juego y llega solo hasta acá
  (selector con doble clic, título por el IME + Enter, F9).

### 12 · ★★★★ LA LARGADA: el personaje EN EL MAPA

- Quien destraba el `while (!this[0xE0])` no es un mensaje de red con comando 1: ese «comando 1»
  es INTERNO. Lo arma el manejador de **`0x105E` — `OnPktS2C_Ntf_Play_Start`** (`0x5333D0`;
  cadenas `0x89A120` / `0x89A100` «… Succeed» / `0x89A0E0` «… Failed»), que el constructor de la
  escena de carga (`0x5343D0`) registra en el mapa de comandos de la escena (`+0x168`), el que
  usa el hilo de carga para despachar el TCP (`0x5345C0` → `0x534300`). Cuerpo: `u16 resultado ·
  u32 valor`; con resultado 1 le pasa `[u8 1][u32 valor]` al callback `0x510D50`. (El mismo mapa
  tiene `0x1058` «OnPktS2C_SomeOne_ChangeState» → `0x534370`.)
- **Probado** (`reglas_broker.py`: al `0x105F` se contesta `0x105E` con `1, 600`), en piloto
  automático (`piloto.py partida`, 14:28): NetTrace.log —
  `LoadingEnd` · `OnPktS2C_Ntf_Play_Start` · `OnPktS2C_Ntf_Play_Start Succeed` ·
  `OnThreadEvent` · `Thread DoEnd!!` · `NetUpdateON` · `Delete LoadingScene!!` ·
  `Briefing Time!!`. En pantalla: **rui en el mapa** (un depósito con la puerta EXIT), con la
  barra de HP/MP/TP, «Lv 1 rui», el minimapa, el reloj de la stage corriendo (0:13 → 0:32 en la
  foto siguiente) y la barra de habilidades. El juego sigue vivo.
- ★ **El control al revés** es la corrida anterior (§11): con un `0x0001` por la red en lugar del
  `0x105E`, el cliente seguía en NOW LOADING. Mismo exe, mismo camino; cambia sólo ese mensaje.
- Ya en la partida, NetTrace anota cada 3 s `TcpMsg:0` · `UdpMsgCnt:0`: no le llega nada y no
  pide nada. El movimiento va por DirectInput (`AddAction MoveForward`… en `autoexec.cfg`), así
  que los mensajes de ventana de `clic_juego.py` no lo manejan.
- ⏭ Lo que sigue: lo de ADENTRO de la stage — 🟡 los enemigos los manda el server (o los genera
  el guion Lua del escenario: hay que medirlo), y el fin de la stage.

### 13 · ★★ MANEJAR AL PERSONAJE sin teclado ni mouse (`control_partida.py`) + lo que el cliente avisa

- el tester jugó (con su teclado): el combate, los NPC y las puertas corren **adentro del cliente**
  (el guion Lua); al server sólo le avisa — `0x105C` (eventos del guion), `0x1061` (NPC muerto),
  `0x1065` (murió el jugador). Tabla en `PROTOCOLO.md` §5.11. Al morir quedó tirado en el piso
  sin menú: el cliente esperaba algo del server que todavía no se sabe (un `0x1066` con estado 1
  no lo cambió).
- **Por qué los clics por mensaje no sirven en la partida**: el juego lee DirectInput.
  ★ Medido con Frida (enganchando `GetDeviceData` / `GetDeviceState` de dinput8, cuyas
  direcciones salen de un teclado propio creado adentro del juego):
  - lee **`GetDeviceData`** (con buffer, registros de 20 B) desde `0x4450CF`, ~50 por segundo,
    teclado (buffer de 64) y mouse (de 1) — y ⚠ **sólo con la ventana activa**: sin foco, cero
    llamadas. Con `WM_ACTIVATEAPP(1)` + `WM_ACTIVATE(1)` por mensaje (el truco de R2Beat,
    `qa/ventanas.py`) vuelve a leer sin traer la ventana al frente (DirectInput contesta
    `NOTACQUIRED`, y el gancho lo cambia por DI_OK);
  - LithTech arma **su propio formato de datos** con SÓLO los objetos atados en `autoexec.cfg`
    (teclado 30 × 4 = 120 B, mouse 6 × 4 = 24 B), así que `dwOfs` NO es el código DIK sino el
    offset en ese formato (`0x445130`: `dwOfs / 4` = el índice del objeto). La tabla se ve
    UNA vez, en el `SetDataFormat` del arranque: `control_partida.py lanzar` abre el juego bajo
    Frida y la guarda en `_trabajo/entrada_formato.json` (D=0 A=4 W=8 S=12 … ESPACIO=32
    SHIFT=36; mouse: botón 0 = instancia 3 = offset 4);
  - una tecla abajo una sola vez **salta** (ESPACIO) o **pega** (clic), pero W no camina: hay
    que **repetir el «abajo» en cada lectura** mientras se mantiene.
- **Probado** (con su revés): `plan "nada:2"` → la imagen no cambia de lugar; `plan "W:3"` →
  rui **camina** hacia las cajas (fotos `_trabajo/fotos/mov_d/f.png`); `clic` + `ESPACIO` → pega
  y salta (`mov_c.png`).
- 🟡 Los casilleros vacíos de la barra de abajo: las habilidades / ítems del personaje. Por
  ahora el server no le manda ninguno (no medido de dónde salen).

### 14 · ★★★ DATA.DAT POR DENTRO (sin reversearlo) + MORIR Y REVIVIR + EL FIN DE LA STAGE

- **`volcar_inflados.py`**: el juego abierto bajo Frida con `inflate` de zlib enganchado
  (`0x788260`: la reconocen sus mensajes «incorrect header check» `0x788454` / «invalid stored
  block lengths» `0x788B41` y su chequeo de `state` +0x1C / `next_out` +0x0C). El «Softnyx File
  System» comprime en **bloques fijos de 7680 B** (cada archivo llega en trozos consecutivos,
  todos desde `0x81580B`). Del arranque a la partida: 94.114 bloques, 679 MB.
  - ★ **El guion de la stage 1011 está en TEXTO**: `-- Stage 1-1 · Mode : Easy · Monster
    Cnt : 56`, `Data = {NpcType01..12, NpcLevel.., NpcPosition.., NpcAI = TestAI.lua, Time..}` y
    las funciones `Initialize` → `Briefing_01` → `OnStart` → `OnTrigger_NN` (`CreateNpcDelayed`
    de los grupos) / `OnSwitch_NN` (`IsNpcGroupDead`) / `DoorSwitch_NN` (`IsEnterMarker`,
    `MoveMapObjectByForward`) → grupo 12 = el jefe (Mother Tarantula) → `OnEnd()` =
    `scenario:SendEvent()`. **No hay nada de muerte en el guion**: la maneja el C++.
  - La tabla de textos en inglés (1043 entradas, `<STRING INDEX VALUE>`): 6000 «Mission
    Completion Result», 6002 «Respawn Times», 6008 «Current Coin», **6010 «Do you want to use
    current coin to respawn?»**, 2015 «CBT Gift! %u Resurrection Coins has been given.».
  - (Es contenido del juego: queda en `_trabajo/`, no en el repo.)
- **Morir**: avanzando (`control_partida.py plan "W:4"` dos veces: la puerta se abre, «Enemies
  have appeared») y quedándose quieto, a los ~30 s rui muere: el cliente manda `0x1063` y
  `0x1065`. Con 3 monedas (`cuerpo[0x17]` del `0x1012`, el «● X3» del HUD) **tampoco aparece
  nada** → la pregunta la abre el SERVER: `0x1068` (`0x546920` → `0x5037D0`, el que revisa
  `+0x2C9`). Encontrado desde el «sí» (`0x500890`, manda `0x106A`): lo registra `0x515446` para
  el cuadro `0x1770`, y el único que abre ese cuadro con monedas es `0x5037D0`, llamado sólo
  desde el manejador de `0x1068`.
- Probado: `0x1068` con 10 → cuadro con la cuenta ya en 0 y Confirm muerto (El tester: «no había
  funcionado por la cuenta expirada»); con **15000** → Confirm → `0x106A 00 01 FF` →
  `0x106B (1, 1, 2)` → **rui revive** (HP lleno, X2). Regla puesta en `reglas_broker.py`, y en
  la muerte siguiente el cuadro salió solo (15:19:09: `0x1065` → `0x1068` en el mismo segundo).
- **El fin**: `SendEvent` → `0x546480` → `0x1064`. El server contesta `0x1073` PlayEnd
  (formato en `PROTOCOLO.md` §5.13). Mandado a mitad de partida lo procesa pero no termina:
  ⏭ falta limpiar la stage de verdad (56 NPC + el jefe) para ver la pantalla de resultado.
  Un bot ciego (clics + giros) no mató ninguno en 20 s: hace falta apuntar.
- **El atajo `fin`** (`volcar_inflados.py --atajo fin --sin-guardar`): al descomprimirse el
  guion, `InsertFunction("OnTrigger_01", 1000)` de `OnStart` se reescribe EN MEMORIA (mismo
  largo) por `InsertFunction("OnEnd",        1000)`. Data.dat no se toca. Medido (15:24): la
  stage termina sola a los 9 s → el cliente manda **`0x1064`** → la regla contesta `0x1073`
  → NetTrace «PlayEnd- RoomState :0 · PlayEnd End- RoomState :0». ⛔ Pero **no aparece la
  pantalla de resultado** y la partida sigue (el HUD sigue en X3 aunque el 0x1073 traía 2).
  🟡 Falta otro mensaje del server, o un estado de sala distinto de 0 (`+0x271`, lo escriben
  `0x1057` y `0x104B`, de la sala de espera). Descartados: `0x1058` (es «alguien cambió de
  estado»: tipo 3 = «%s left the stage»), caminar hasta la puerta EXIT.

### 15 · ★★★ RESULTADO, CARTAS, PREMIOS y la VUELTA AL LOBBY

- Con el atajo `fin` (la stage termina a los 9 s) y mandando cada S→C de a uno (en la respuesta
  al «estoy vivo», `0x1001`, cada 20 s), pantalla por pantalla — formatos en `PROTOCOLO.md`
  §5.14 / §5.15:
  - `0x106E` → **MISSION COMPLETION RESULT** (fotos `_trabajo/fotos/fin_5..7.png`). Un error mío
    de pila (contar mal un `push`) cruzó los campos en la 1ª foto; con valores todos distintos
    cerró: 47 muertos, 12 golpes, 1 revivida, 03:05, 1500 puntos, rango D.
  - `0x106F` → **REWARD CHOICE** (`fin_8.png`). Con 15000 la cuenta se venció antes del clic;
    con 60000, el clic en una carta mandó `0x1070 00 00`.
  - `0x1071` → los puntos bajaron a 1167 (`fin_11.png`). `0x1072` → **AWARD RESULTS**
    (`fin_12.png`: «rui · Gold 0 · Exp 0» + Confirm).
  - ⛔ `0x1075` mandado ahí: el juego se cayó (`0x752B7E`, puntero nulo; EDA_limpio.rpt 15:37:57).
- **Salir**: ESC al `Edit` oculto → «quit the stage?» → Confirm → `0x1074` → `0x1075` →
  **LOBBY** con «Quit Rate 1 / 1 (100%)» y «EXP 150/300» (`salir_3.png`, 15:40:41). El revés:
  ESC a la ventana de arriba NO abre el cuadro (`salir_1.png`).
- `piloto.py salir` hace lobby → sala → partida → ESC → Confirm. ⚠ Dos corridas: una se quedó
  en la lista de servidores (por activar la ventana en todos los pasos: ya corregido) y otra en
  el lobby (el paso del selector, de tiempo). El ESC del piloto a los 15 s de partida no abrió
  el cuadro: 🟡 a medir si es por el momento (la prueba manual fue a los 31 s).
- ★★★ **El ciclo entero, en automático** (15:48–15:50): juego con el atajo `fin` +
  `piloto.py partida` (retomado con `EDA_DESDE=lobby`: bajo Frida se quedó en SELECT CHARACTER)
  → la stage termina → `0x1064` → el guion contesta `0x1073` + `0x106E` + `0x106F` → REWARD
  CHOICE → clic en una carta plateada → `0x1070` → `0x1071` + `0x1072` → AWARD RESULTS →
  Confirm → **WAITING ROOM** (`cadena_4.png`), sin ningún mensaje del server para volver. (El
  Confirm que no andaba antes era en el juego que después se cayó con el `0x1075`.)
  🟡 El 0x106E y el 0x106F llegan en el mismo segundo y el resultado queda tapado por las cartas:
  el server original seguramente esperaba entre uno y otro.
- **Qué hay en las cartas**: `Data\StageReward.xml` (volcado) da por stage la lista de premios,
  ítems por ID de `ITEMTYPELIST`: stage 1011 → 1, 3001, 201, 3201, 26001 ×5, 40071, 31001. En el
  `0x1071` la carta va como u32 cuyo 1er byte es el NIVEL (0/1/2 = filas I/II/III, `0x5095F0`);
  ⏭ falta dónde va el ítem (con «0» no se dio vuelta).

### 16 · ★★ EL SERVER CON MEMORIA (`servidor/juego.py`)

- Las reglas fijas no pueden descontar monedas ni sumar EXP. El espía ahora, en cada mensaje,
  carga `servidor/juego.py` (de nuevo si cambió su fecha: sin reiniciar el espía = sin UAC) y le
  pide las respuestas: `responder(cmd, cuerpo, conexion)` → lista de (comando, cuerpo, ms de
  espera) — con espera el resultado y las cartas salen ESPACIADOS — o None = las reglas.
- La cuenta en `_trabajo/servidor/cuenta.json`. El nivel sale de la **tabla de EXP del juego**:
  `<EXPS>` de `Data\Player.xml` (99 valores: 0, 300, 1060, 2160, 3600, 5500…), que cierra con
  el lobby («1LV (11/300)»). 🟡 El premio por stage (EXP 50 + 5 por NPC, plata 100 + 10 por NPC)
  es nuestro: no se sabe cómo lo calculaba Softnyx.
- `py servidor\juego.py control`: 13 ✅, con el revés (sin monedas NO revive).
- **Medido en el juego** (15:58–16:02): el espía cargó el server; la stage (atajo `fin`) →
  `0x1073` + `0x106E` (300 ms) + `0x106F` (8 s) desde el server, «Earned Point 500»; carta →
  `0x1071`/`0x1072` → AWARD RESULTS → Confirm (⚠ recién anda ~20 s después de aparecer: al
  toque se pone verde y no hace nada) → WAITING ROOM. **Segunda partida** en la misma sala (F9
  ⚠ necesita la ventana activa por mensaje): cuenta en EXP 100, plata 5878, 2 partidas. Y
  **cerrando y abriendo el juego**: SELECT CHARACTER «1LV (100/300)» y «5878 Gold»
  (`piloto_160210_personajes.png`) — sale del server, no de una regla.
- Las habilidades: `Data\Skill.xml` (36 activas): se COMPRAN con plata (`COST_GOLD` 450…) y
  desde nivel 3 (`ACQUIRE_LEVEL`). La barra vacía de nivel 1 es lo correcto.
- ★★ **La progresión de stages** (16:05–16:10): el server manda en el `0x1018` las misiones
  terminadas, pero el juego no las tomaba. Llamando al buscador del propio juego (`0x620820`
  sobre la cuenta `0x937640`, desde Frida) el mapa tenía **0 entradas**: la cabecera del 0x1018
  estaba mal contada desde el principio (un `push ebx` en `0x54470E`: N1 va en +3, no en +7).
  Corregida → el mapa tiene 1011 (`+4 = 1011, +8 = 1, +9 = 1`) y `0x6209F0` contesta **1012 → 1**
  (antes 0: el revés), 1013 → 0 (pide 1012). En CREATE STAGE aparece **NORMAL** junto a EASY
  (`dific_2.png`). La cadena sale de los XML de cada escenario (`<CONDITION TYPE="0">`):
  1011 Easy → 1012 Normal → 1013 Hard → 1021 Easy 1-2. Y cada XML trae `TOTALEXP`,
  `KILL_POINT`, `RANK_POINT`, `MONSTER_CNT` y los cortes de rango (`RANKRATE` S 0.8 … D 0.1).
- **NORMAL de verdad** (16:10–16:11): el server contesta el `0x101E` con la sala QUE MANDÓ el
  cliente (antes la regla devolvía siempre 1011). CREATE STAGE → NORMAL → «Normal 1-1» → la sala
  dice **NORMAL**, el `0x101D` traía escenario **1012**, y F9 cargó la partida (Briefing_01 →
  OnStart → OnTrigger_01). El premio ahora sale del XML de cada escenario (`ESCENARIOS` en
  `servidor/juego.py`: RANK_POINT, KILL_POINT, TOTALEXP, MONSTER_CNT y los cortes de RANKRATE);
  🟡 cómo los combinaba Softnyx no se sabe (acá: proporcional a los NPC muertos).
  `juego.py control`: 15 ✅ (los esperados salen de la tabla, no escritos a mano).

### 17 · ★ GAME OVER automático (lo que pidió el tester: «al acabarse el tiempo para revivir…»)

- Al vencer la cuenta el cliente no manda nada (15:19) → el game over lo da el server.
  `0x1069` → **modo espectador** (sin HUD, «<Jump Key> pushing allow viewing of other players»,
  `gameover_2.png`); `0x1075` desde ahí → **LOBBY** sin caerse (`gameover_3.png`).
- En `servidor/juego.py`, sin tocar nada a mano (16:26): muerte 16:26:04 → `0x1068` → vence →
  16:26:24 `0x1069` (con el «estoy vivo») → 16:26:30 `0x1075` → LOBBY (`gameover_4.png`).
  «Cancel» / sin monedas (`0x106B` modo 0) hace lo mismo.
- ⚠ Aprendido: al recargar `servidor/juego.py` se perdía el estado de cada partida (una recarga a
  las 16:18 borró un game over pendiente). Ahora vive en un módulo aparte (`_eda_partidas`) que
  no se recarga. Y `_trabajo/servidor/empujar.json` = mandar algo a mano con el próximo 0x1001.
- `juego.py control`: 18 ✅ (con los reveses: recién muerto no hay game over; con respuesta al
  cuadro tampoco).

### 18 · Los botones del LOBBY (El tester: «el botón Options no funciona») y la pantalla 6

- La barra de arriba es el grupo GLOBAL del layout (`ChannelLobby_*`, controles 1–7). El lobby
  registra sus funciones con `0x4DF900(3, control, función)` (`0x4F6000…`):
  1 Shop → `0x4EB050` · 2 Inventory → `0x4EB070` (registrado con `push ebx`) · 6 Select
  Character → `0x4EB090` · 7 Exit → `0x4EB0A0`. ⛔ **3 Clan, 4 Messenger y 5 Options NO tienen
  función en el lobby**: el botón se ilumina y nada más. No falta ningún mensaje: en este build de
  la beta no están conectados ahí. (Medido: un clic en cada uno no manda nada.)
- **Select Character** manda `0x1023 (u32 0)` → `0x1024` (`0x5424A0`): `u16 1` → pantalla 2
  (SELECT CHARACTER; el cliente vuelve a pedir la cuenta, `0x1011`). ✅ en el server: anda.
- **Shop / Inventory** mandan `0x1027 (u32 · u8 4 / 5)` → `0x1028` (`0x542660`): `u16 1` →
  pantalla 6 = **INVENTORY** (equipo, grilla de 5 hojas, estadísticas, Gold/Cash, y las pestañas
  Shop / Inventory / Refinery / Skill). Ahí arriba: Lobby / Clan / Options / Messenger / Exit.
  La pestaña Shop manda `0x102B` (27 B) y espera; `0x102C` (`0x54BBB0`) = estadísticas +
  EQUIPO (18 u32 → +0x72 del personaje). Clan (en esa pantalla) manda `0x102D` (26 B).
  Las respuestas de la pantalla 6: 102C→`0x54BBB0`, 102E→`0x54CD70`, 1030→`0x54C690`,
  1034→`0x54A180`, 1036→`0x54AF20`, 1038→`0x54B070`, 103A→`0x54A7A0`, 103C→`0x54B1E0`,
  103E→`0x54CB70`, 1040→`0x54D340`, 1042→`0x54AA80` (a mapear una por una).
- Las respuestas del lobby: 101A→`0x542990`, 101B→`0x541EB0`, 101C→`0x541C50`,
  101E→`0x543500`, 1020→`0x543640`, 1024→`0x5424A0`, 1026→`0x5424E0`, 1028→`0x542660`,
  1056→`0x543BE0` (la lista de salas y de usuarios del video estarán entre éstas).
- Del video (capturas de el tester): cartas a **350 / 150 / 50** y la 1-1 completa (56 muertos) =
  **257 puntos, rango S** → el server usa esos precios y calibra los puntos con eso (🟡).

### 19 · ★★ MULTIJUGADOR, primer paso: dos clientes, dos cuentas, la lista de salas

- **Dos clientes a la vez** en la misma máquina: el segundo `EDA_limpio.exe` abre normal (el
  mutex de instancia única no lo frena). `piloto.py` maneja cada uno con `EDA_PID`.
- **El espía, reiniciado (UAC)** con: `CONEXIONES` (cada conexión con su clave y su servicio) →
  el server puede mandarle a OTRA conexión (respuestas de 4 elementos: comando, cuerpo, ms,
  destino); un **`tick`** cada segundo (el game over sale a tiempo, sin esperar el 0x1001); y
  `cerrada(n)` cuando se cierra una.
- **Una cuenta por conexión** (`servidor/juego.py`): sin launcher los dos mandan lo mismo, así
  que cada conexión de juego toma el primer nombre libre (rui, kai, mio, ren); cada cuenta en
  `_trabajo/servidor/cuentas/<nombre>.json`. Medido: SELECT CHARACTER «rui (100/300)» en uno y
  «kai (0/300)» en el otro (`dos_clientes.png`).
- **La lista de salas** = `0x101C` (`0x541C50`): u8 total · u8 índice (y u16 N en el primero),
  N × 79 B. Cada registro se copia con `rep movsd` ENCIMA de un objeto construido (`0x53E6D0`):
  +0 / +4 son sus vtables (`0x89A350` / `0x89A348`: hay que mandarlas, si no quedan en cero), y
  desde +4 va la sala desde su +0 (número, título, escenario…). De la fila (`0x4F4E21`,
  `0x4F4EEE`): sala +0x2D = estado (1 = «Waiting», si no «Playing»), +0x2E = jugadores dentro,
  +0x2F = máximo. Medido: rui crea «Sala de rui» → kai la ve en su lobby: **«1 · Start of the
  Search · Sala de rui · 1/3 · Waiting»** (`kai_fila.png`; antes de los campos: «0/3 · Playing»).
- Entrar a una sala: Enter / doble clic en la fila → `0x1019` (5 B, `0x4EC0C0` → `0x542110`). ⏭
- ★★★ **DOS JUGADORES EN LA MISMA SALA** (16:59): kai (lobby) selecciona la fila + Enter →
  `0x101F` (26 B: u32 0 · u16 número de sala · 🟡 16 B) → el server contesta a kai **`0x1020`**
  (`0x543640`: u16 1 · u8 → +0x705 · u8 → +0x706 = su número de jugador · u8 → +0x29D · vt
  0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · la sala (89 B) · u8 N · N miembros de 0x32C) y al
  anfitrión rui **`0x1057`** (`0x54F020`, 0x377 B: u8 · u8 estado · vt · u8 · u8 · el miembro
  nuevo de 0x36F). Los miembros se arman sobre los constructores del cliente
  (`servidor/juego.py: miembro()`, todas las vtables con su valor: `0x540980`, `0x53F680` = el
  personaje, `0x5404C0` × 18, `0x541230` / `0x541020` / `0x53F440` × 9 para el 0x36F).
  Medido: en la WAITING ROOM de los DOS aparecen «1LV rui» (con la casita) y «1LV kai»; kai tiene
  **«F9 Ready»** y rui «F9 Start Game» (`j_24036.png`, `j_28420.png`). El ping del otro dice
  «-1000 ms»: todavía no hay UDP entre ellos.
- 🟡 La lista de miembros del anfitrión en memoria (`0x937390+0x240`, vector de 0x36F) está VACÍA:
  el jugador local no se guarda ahí (`herramientas/miembro_sala.py` la lee).
- ★★★ **LOS DOS EN LA MISMA PARTIDA** (17:01): kai F9 Ready → `0x1047 (01 01)` → a él `0x1048`
  (`0x54E5C0`: u16 1 · u8 → +0x2DE) y al anfitrión `0x1058` tipo 1 (`0x54FC80`: u8 id · u16 tipo
  · u8 → +0x322 del miembro = listo) → la ✔ de kai en las DOS salas (`ready.png`). rui F9 Start
  → `0x104E` → `0x104F` a los dos (N = 2) → los dos cargan y mandan `0x105F` en el mismo segundo
  → el server espera a TODOS y manda `0x105E` a los dos juntos → **cada uno ve al otro en el mapa**
  (`g_ambos.png`). (`0x1058` tipo 3 = se fue, con el nuevo anfitrión; tipo 2 = +0x323.)
- ⚠ Pero `UdpMsgCnt:0`: entre ellos no viaja nada por UDP. Cada cliente abre SU puerto UDP (rui
  57654, kai 51001: el segundo no puede usar el mismo) y lo manda en el **`0x100F`**: cuerpo
  +0xDE u32 IP privada · +0xE2 u16 puerto privado · +0xE4 u32 IP pública · +0xE6 u16 puerto
  público (el del 0x0609, hoy fijo 57654 para todos). ⏭ Se le pone a cada miembro su dirección
  (127.0.0.1 + su puerto) en el +0x48 del miembro (🟡) y se mira si arranca el P2P.

### 20 · El NAT y el P2P: el mapa (PROTOCOLO.md §5.16) y lo medido

- `0x1059` «Peer Public IP» (`0x550BE0`): a cada miembro las direcciones de los OTROS. ⚠ Con la
  propia incluida los DOS clientes se cayeron (`0x550CAC`: el jugador local no está en su lista
  de miembros → nulo). Corregido: ya no se caen.
- El «[Punch UDP IP, PORT] 0.0.0.1:0» salía del `0x1010`: sus 12 B son u16 1 · u32 (+0x2B8) ·
  **u32 IP · u16 puerto del server UDP de punch** (`0x549742` → `0x6218F0`). Con 127.0.0.1:25001
  y `herramientas/udp_punch.py` escuchando: kai manda **`0x3006`** ×4 (`04 00 06 30` + u32 id
  de la cuenta = +0x2B8, que hoy queda en 0 porque lo pisa el 0x1012). El ping sigue -1000 ms.
- `multi.py`: dos clientes solos hasta la sala / partida (con reintentos del doble clic en el
  marcador, que con dos ventanas falla seguido).
- **El ruteador UDP, medido con Frida** (un datagrama `0x3007` / `0x3008` mandado a mano al puerto
  del invitado, con el gancho en `0x4E57EC` / `0x4E5819`): 0x3000–0x3007 → objeto de punch (vt
  `0x89D7FC`) → **`0x5D5BA0`**, que despacha por SU mapa de comandos (`0x5D5B30` sobre +4);
  0x3008–0x300A → la pantalla actual (vt `0x89A268`, +0x34 → `0x4DB6F0`). ⏭ Falta dónde se
  registran los manejadores del punch (no aparecen como constantes sueltas) para saber qué
  contesta el server al `0x3006`, y con eso el ping de la sala.
- `multi.py` ahora verifica en el espía que cada cliente llegó al lobby (un `0x1017` más) y si no,
  lo reintenta; `EDA_MULTI_PAUSA` para enganchar algo antes de la sala. `udp_punch.py`:
  `EDA_PUNCH_ECO=1` contesta un 0x3007 con el mismo cuerpo (para medir).

### 21 · ★★★ EL PING ENTRE JUGADORES ANDA (77 / 74 ms, ya no -1000)

Tres errores nuestros y una pieza que faltaba, medidos con Frida en `sendto` / `recvfrom`:
1. `0x1059` con IP y puerto en orden de red → el cliente imprimía «1.0.0.127» y saludaba a una
   dirección inexistente. Van como ENTEROS: el cliente les hace htonl / htons (la misma función
   `[0x88A55C]` que con la dirección del punch del 0x1010).
2. Los offsets del `0x100F` corridos en 1 (aquel volcado incluía la cabecera de 4 B): el puerto
   leído era «481» (E1 01). Bien: cuerpo +0xDD IP privada · +0xE1 puerto privado · +0xE3 IP
   pública · +0xE7 puerto pública. Con eso los dos se mandan el saludo: **`0xC354` ×185** en
   2 s (`0x74AA60`, con su identidad: u32 largo + la MAC en texto) y **`0xC351` / `0xC352`**
   en las dos direcciones = el apretón de manos P2P.
3. El ping de la sala (`0x5374A0`) lo pide la capa UDP por una CLAVE DE TEXTO (`0x748120`, mapa
   en +0x110) armada con el texto ancho de **+0xA del miembro** (`0x623070`); vacío → -1 →
   «-1000 ms». La clave es la identidad del saludo 0xC354 (la MAC). 🟡 Atajo local: los dos
   clientes de esta PC tienen la misma y el server la lee de la 1ª línea de NetTrace.log (no se
   guarda); con PCs distintas hay que sacar la de cada uno del 0x100F (va ofuscada).
- Medido (`ping.png`): **rui ve a kai a 77 ms, kai ve a rui a 74 ms**.
- ★★★★ **Y EN LA PARTIDA SE VEN MOVERSE** (17:50): con el ping andando, kai «listo» → rui F9 →
  los dos en el mapa → rui camina (W · D · W, por `control_partida.py`): en la pantalla de kai
  rui ya no está donde estaba, y en su **minimapa la flecha naranja (rui) se movió hacia
  adelante** (`minimapa_kai.png`, `multi_p_antes/despues.png`). NetTrace: **`UdpMsgCnt:151`**
  (antes siempre 0). El multijugador P2P anda en la misma PC.

### 22 · (pausa) La lista de usuarios del lobby, y el juego que dejó de arrancar

- `0x101B` (`0x541EB0`) = la LISTA DE USUARIOS del lobby: como el 0x101C (u8 total · u8 índice ·
  u16 N) + N × 92 B copiados encima de `0x53FBE0`: vt 0x89A3C4 · u32 id · u16 sala (0xFFFF) · el
  personaje (0x52 B, vt 0x89A3AC / 0x89A378). En `servidor/juego.py` (`lista_usuarios`): se
  manda al entrar al lobby y se reparte cuando alguien entra o sale. ⏭ Sin probar en vivo.
- ⛔ Desde las 17:55 el juego se cae AL ARRANCAR, dentro de `mss32.dll` (Miles: cerca de
  `_AIL_release_timer_handle`, los temporizadores), antes de hablar con el server. Descartado:
  los archivos (idénticos al cliente), el exe (el mismo de toda la tarde), un cliente solo, sin
  sonido (`ForceNoSound`, una copia que saltea `AIL_open_digital_driver`, sin `redist/`), una
  carpeta de juego nueva copiada del cliente (`_trabajo/juego_limpio`). Coincide con que el tester
  abrió el cliente de R2Beat 2013. 🟡 Algo del sistema: El tester reinicia la PC.
- Al volver: espía (`espiar_broker.py arrancar`, UAC) + `udp_punch.py`, y probar.

### 23 · ★★ LA CAUSA de que el juego dejara de arrancar: el exe arrastraba direcciones de UNA sesión

- No era el sonido ni R2Beat: después de reiniciar la PC el juego se caía TODAVÍA ANTES (0,1 s,
  `0x75C0D653`, sin NetTrace). Bajo el depurador: el CRT hace `mov edi, [0x88A2A4]; call edi`
  (GetModuleHandleA) y esa casilla **no estaba en la tabla de imports**: tenía escrito en el
  archivo `0x75C0D640`, la dirección de la función en la sesión de Windows en que se volcó el exe.
  Mientras no se reiniciara (y no se moviera esa DLL) andaba; las caídas de las 17:55 en
  `mss32.dll` serían lo mismo con otra casilla (🟡 algo movió una DLL a esa hora).
- `desempacar.py slots()` sólo reconocía `call/jmp [X]`: ahora también `mov reg, [X]`, `mov eax,
  [X]` y `push [X]`. Rearmado (`juntar_apis` → `desempacar construir` → `sin_gameguard limpio`):
  **454 imports** (antes 441: 13 casillas más tenían el mismo problema), 0x88A2A4 =
  KERNEL32!GetModuleHandleA. El juego arranca, el espía (clave nueva: md5 nuevo) y el lobby andan.
- Los exes de antes quedaron en `_trabajo/EDA_libre/EDA_libre_antes_reinicio.exe` y
  `_trabajo/juego/EDA_limpio_antes_reinicio.exe`.

### 24 · ★ La LISTA DE USUARIOS del lobby anda («LV 1 rui · LV 1 kai» en los dos)

- `0x101B` llegaba y se parseaba (Frida: `0x541EB0` y el redibujo `0x4F5CD0` corren) pero no se
  agregaba ninguna fila: `0x6109F0` agrega sólo si `[canal+0x1C] < [canal+5]`, y la CAPACIDAD
  del canal (+5) salía de los 7 B de +9 del `0x1018`, que iban en cero. 🟡 Esos 7 B: u8 número
  de canal · u16 capacidad · u16 ocupados · u16 (`0x6103F0` divide +7 por +5). Con (1, 200, n,
  0): la lista aparece en los dos clientes (`multi_usuarios.png`).

### 25 · ★ El CHAT del lobby anda («rui hola de rui» en los dos)

- C→S **`0x100D`** (medido): u8 tipo (1) · u32 destino (FFFFFFFF = todos) · u32 0 · u32 largo
  en bytes · el texto UTF-16.
- S→C **`0x1005`**: el ruteador TCP (`0x4E56BC`) manda 0x1003–0x100B a la pantalla actual
  (+0x34 = la base `0x4DB6F0`), que tiene una tabla: 1003 → `0x4DA9B0`, 1004 → `0x4D98C0`,
  **1005 → vt+0x80 de la pantalla = `0x4DF140` (chat / avisos)**, 1006–1009 → `0x61B300` (🟡 el
  Messenger). `0x4DF140` lee 37 B y después el texto (`0x742A80`: u32 largo + bytes). Medido con
  Frida que el TIPO va en B+2: la cabecera es **u16 🟡 · u8 tipo (1/3 chat, 4 aviso del sistema
  «CBT Gift…») · u32 🟡 · u32 🟡 · 26 B nombre UTF-16**. El server reparte el chat a todo el lobby
  (o a la sala, si el que habla está en una).

### 26 · ★ El INVENTARIO empieza a andar: ítems equipados con su ficha

- En el `0x1012`: **N1 (+0x1C) × 21 B = los ítems** (`0x617630` → cuenta+0x708, el mismo que
  usa el PlayEnd): +4 u32 serie · +8 u16 TIPO (ITEMTYPELIST) · +0xA u8 · +0xB u8 · +0xC u16
  (🟡 durabilidad: la ficha dice «Durability 0%») · +0xE u8 · +0xF u16 · +0x11 u32. Y **N2
  (+0x1E) × 36 B = la ficha de cada ítem** (`0x6176E0`): vt · u32 serie · 28 B 🟡.
- Medido: con los premios de la 1-1 (3001, 201, 3201, 26001×5, 40071, 31001) aparecen dos en
  los casilleros de EQUIPO (una máscara en la cabeza y el arma). ⚠ Sin las fichas, al pasar el
  mouse por el arma el juego se cayó (`0x61FDB0` con un puntero nulo, llamado desde la ficha
  `0x520336`). Con las fichas: **«Basic Short Sword · Hunter · Requires Lv2 · Durability 0% ·
  Can't equip · Melee Atk 4.00 …»** (`inv_ficha_arma.png`), sin caerse.
- ⏭ La grilla del inventario sigue vacía: falta qué es +0xA / +0xB (🟡 lugar / equipado);
  `_trabajo/servidor/inv_prueba.txt` («a,b», con «i» = índice) para medirlo sin tocar el código.
- ★★ **Dónde va cada ítem = +0xB, un casillero único** (medido con clientes nuevos, foto por
  foto; el cliente NO recarga el inventario al volver por Select Character: cada prueba pide
  abrir el juego de cero): **0–11 = EQUIPO** (la interfaz pide `0x615C40(control − 10000)`,
  `0x51C6A5`), **12–17 = la fila de 6 sobre la grilla** (🟡 la barra de ítems de la partida,
  teclas 1–6), **18… = la BOLSA** (5 páginas × 30). Con 0/1 en +0xB los ítems de Hunter
  (máscara, espada 201) aparecían «equipados» por ESO, no por tipo (El tester: «son de Hunter y rui
  es Warrior»). Con 18 + n: **los seis en la primera fila de la bolsa** (`inv_b_18.png`).
  El server: cada ítem de la cuenta es [tipo, cantidad, casillero]; sin casillero, a la bolsa.

### 27 · ★★ EQUIPAR, COMPRAR y VENDER andan (y por qué decía «Can't equip»)

- **El «Can't equip» tenía razón**: en `ItemTypeList.xml` **ningún equipo pide menos de nivel
  2** (`LEVEL_RESTRICT` mínimo = 2 en las 192 piezas) y `USECLASS` dice la clase: la máscara 3001
  es de **Warrior** (1), la espada 201 de **Hunter** (2). Rui estaba en nivel 1. Con 300 de EXP
  (nivel 2) y el set de grado 1 de Warrior (1, 1001, 3001, 4001, 5001, 6001, 7001, 8001), **clic
  derecho = equipar** (rui se lo pone en el modelo, las estadísticas suman: Def +8, HP +12…).
  ★ Control al revés: la 201 de Hunter, también con nivel 2 → «Can't equip the item.»
- El cliente equipa SOLO, sin avisar. **Al irse** (tocar «Lobby») manda **`0x102D`** con los
  ítems que movió `(serial, casillero)` y se queda esperando el **`0x102E`**; al cambiar de
  pestaña (Shop = 4, Inventory = 5) manda **`0x102B`** y espera el **`0x102C`**. Los dos llevan
  **el EQUIPO del personaje: 18 u32 = el serial de cada pieza puesta**, por PARTE (medido con
  Frida en `cuenta+0x2B0 → 0x61F8B0`: +0x72 = 1 2 3 4 5 6 7 8). El 0x102C de antes mandaba
  ceros: al cambiar de pestaña se habría desvestido.
- El equipo va también en el personaje del `0x1012` (+0x72): **un cliente nuevo entra al lobby
  ya equipado** (`eq_4.png`). Los casilleros de equipo son 0 máscara · 1 cinturón · 2 capa ·
  3 collar · 4 torso · 5 anillo · 6 piernas · 7 anillo · 8 guantes · 9 botas · 10 arma · 11
  segunda arma (izquierda/derecha alternados, de los números que mandó el cliente).
- **La TIENDA** es `Data\Product.xml` («SellList» en `Data\main.xml`): 66 `<Product ID
  Category SellGold SellCash><Item RefID Count/>` y `<BUYS><BuyItem RefID BuyGold/>` (lo que
  paga la tienda). No estaba en el volcado viejo: salió con `volcar_inflados.py` + la
  herramienta nueva **`sacar_xml.py SHOP Product`** → `_trabajo/datos/Product.xml`.
- **Comprar**: «[Basic Long Sword] 1200 Gold» → Confirm → **`0x103F`** (u8 N + N × u16 ID DE
  PRODUCTO) → **`0x1040`** → «Selected Item has been successfully purchased.», oro 5878 → 4678,
  la espada en la bolsa (`sh_c.png`, `sh_e.png`).
- **Vender**: «480 Gold» (el BuyGold del 1) → **`0x1041`** (u32 serial) → **`0x1042`** →
  «successfully sold», oro 4678 → 5158 (`sv_c.png`).
- ⚠ El serial tiene que ser FIJO (es como el cliente nombra cada ítem): los ítems de la cuenta
  pasan a `[tipo, cantidad, casillero, serial]`; las cuentas viejas toman posición + 1.

### 28 · ★★ HABILIDADES: verificar el libro y aprender (Dash)

- El arrastre por mensajes no arrastraba: el GUI (HGE) mira **`GetKeyState(1)`** en cada cuadro
  (medido con Frida: 20/s con 1 y 2). `clic_juego.arrastrar_de_verdad` lo hace devolver
  «apretado» mientras dura → el pergamino y el libro **se intercambian de lugar** (`sk_h.png`).
- El «Unknown Skill Book» de verdad no es el tipo 40061: es **un ítem de habilidad (32001 =
  Dash) con +0xE = 0** (`0x51BB40` pide tipo 31000–33999 y +0xE = 0). El objeto ítem del cliente
  nace con +0xE = 1 (`0x53F4B0`); mandábamos 0 en todos. Con el 32001 sin verificar en la bolsa:
  clic derecho en el pergamino + clic en el libro → `0x103B` → `0x103C` → **«Selected Skill has
  been verified. [Dash, 1Lv]»** (`sk_n.png`).
- Clic derecho en el verificado → «You do not have enough skill slot» (215): los lugares son el
  **byte +0x5B del personaje** (mandábamos 0). Con 12 (🟡): **«450 Gold will be used. Do you want
  to learn the skill?»** (el COST_GOLD de `Skill.xml`) → `0x103D` → `0x103E` → **«Selected Skill
  has been Learned. [Dash, 1Lv]»** y el Dash aparece en la grilla SLOT 1 (`sk_q.png`).
  ⚠ La 1ª vez el oro quedó en «0 Gold»: el ORO va en +3 del 0x103E (un `push esi` mal contado);
  corregido, con una prueba que lo controla.
- Las habilidades viajan en el **`0x1018` (N2 en +7, 13 B cada una)**: un cliente nuevo entra
  con el Dash en su grilla y 4708 de oro (`sk_r.png`).
- ⛔ +0xC del ítem NO es la durabilidad: con 10000 la ficha siguió en «Durability 0%».

### 29 · ★★ El PREMIO de la stage entra a la bolsa, y el inventario desde la sala

- Las cartas de REWARD CHOICE dan EXP/puntos (la vuelta de la carta, `0x5095F0`, es sólo la
  animación de la fila): el ÍTEM del premio va en el **PlayEnd (`0x1073`)**: N1 (+25) × 21 B,
  y si el u32 de +0x11 es −1 viene su ficha de 36 B pegada (`0x548C54`). N2 (+27) × 10 B = ítems
  GASTADOS (cantidad 0 → se borra; si no, se actualiza) — 🟡 para las pociones de la partida.
- El premio sale de **`Data\StageReward.xml`** (`sacar_xml.py STAGE_REWARDS StageReward`):
  150 stages con `GiveCount="1"` y su lista `<Present Type Data Count>`; Type 2 = ítem, el
  40071 se llama «None» (= nada), Type 0 🟡 oro. El server elige uno al azar (🟡 sin pesos: el
  XML no trae probabilidades); un libro de habilidad llega SIN verificar.
- Medido (19:20, stage cortada con `--atajo fin`): PlayEnd de 86 B (29 + una 201 con su ficha),
  el cliente lo procesa, y la espada aparece en la bolsa (casillero 19) abriendo el inventario
  desde la sala (`pr_g.png`).
- ⚠ Con 0 puntos no se puede elegir carta y la pantalla se quedaba en el reloj 0: el server
  manda ahora el `0x1072` solo, 70 s después del PlayEnd, si nadie eligió.
- Desde la **sala**, «Inventory» = **`0x104C`** → **`0x104D`** (u16 1 · u8 → cuenta+0x2DE) y al
  irse el `0x102E` va en **MODO 9**: los 0x63 B del `0x1020` sin su u16 + TODOS los miembros
  (0x32C, el propio incluido) → de vuelta en la WAITING ROOM con rui una sola vez (`pr_h.png`).

### 30 · La BARRA de habilidades de la partida, y dónde (no) viaja la identidad P2P

- Habilidad (13 B): **+0xB = casilla en la grilla de aprendidas, +0xC = ATAJO** (1…8 = F1…F8).
  Medido con un cliente nuevo: con +0xC = 1 el Dash aparece en la grilla de arriba de la
  pestaña Skill y **en la barra de abajo a la izquierda del HUD** (`hud_a.png`); F1 (Skill1 en
  `autoexec.cfg`, inyectado con `control_partida.py`) lo **marca** (recuadro rojo,
  `dash_3.png`). 🟡 Que se dispare (F1 + clic derecho) NO quedó medido: El tester estaba moviendo
  al personaje en ese momento y las fotos mezclan las dos cosas.
- Arrastrar el Dash a la grilla de arriba (con `arrastrar_de_verdad`) no lo toma. Hasta medir
  cómo, el server le da a cada habilidad nueva el primer atajo libre (🟡 comodidad nuestra).
- **La identidad P2P** (lo que va en el saludo `0xC354`/`0xC351`/`0xC352` y en +0xA del miembro)
  es la MAC en texto (std::string en +0xE8 del objeto UDP, `0x74AAC4`). ⛔ El server NO la
  recibe de forma confiable: aparece en el `0x100F` sólo en 36 de 125 capturas, como resto
  sucio de un buffer global (`0x934640`) que se copia entero. Las cadenas de la cuenta que viajan
  ahí (`+0xF0`, `+0x11A`, `+0x144` IP privada, `+0x166`, y `+0x1A6` = el MD5 del exe) las
  llenaba el LAUNCHER; sin él quedan con basura. ⏭ Medir (desde el arranque) quién escribe +0xE8;
  si no hay forma de que el server la sepa, la salida es un RELAY UDP que reescriba la identidad
  de los saludos (y sirve además para NAT simétrica / cíber).

### 31 · ★★ El RELAY anda: dos jugadores con identidades INVENTADAS, ping y movimiento

- `herramientas/relay_udp.py` + modo relay del server (`_trabajo/servidor/modo_relay`): el
  server inventa la identidad P2P de cada jugador («02:00:00:00:XX:XX»), da como dirección de
  cada par un puerto del relay (26001 + conexión) y el punch en 26000; el relay reenvía cambiando
  la MAC real del que manda por la inventada.
- Hubo que arreglar el id del punch: el `0x3006` lleva `cuenta+0x2B8`, que el **`0x1012` pisa
  con su `+6`** (lo mandábamos en 0: todos se registraban como «jugador 0»). Ahora va la conexión;
  y `relay.json` lleva además la dirección que el cliente declaró en su `0x100F`, de respaldo.
- Medido con dos clientes en esta PC (20:09): sala con **82 / 87 ms**, 0 datagramas descartados.
  ★ Control al revés (`EDA_RELAY_SIN_CAMBIO=1`: el mismo relay SIN cambiar identidades):
  **-1000 ms** en los dos. En la partida (20:21) se ven, y rui caminando (W 2,5 s) se ve
  moverse en la pantalla de kai (`multi_mov_antes.png` / `multi_mov_despues.png`).
- ⏭ Entre PCs de verdad: el relay escuchando en la IP pública del server (abrir UDP 26000–26xxx
  en el router) y su IP adentro de `modo_relay`. El otro jugador se ve SIN su equipo (el miembro
  de la sala lleva el equipo en cero: falta llenarlo).

### 32 · ★ Cartas y premios (El tester, 19:55: «la tarjeta no se volteó, no gané exp ni oro»)

- `0x1070` = u8 · u8 **CARTA numerada de corrido** (oro 0–3, plata 4–9, bronce 10–17; medido:
  la 1ª de bronce = «00 0a»); el cliente saca la fila igual (`0x500810`). Se tomaba el 1er byte
  como fila (siempre «oro»).
- `0x1071` = u8 1 · u8 FILA · u8 **JUGADOR** · u32 EXP de cartas acumulada · u32 puntos que
  quedan. Iba el número de carta donde va el jugador: el cliente lo compara con el suyo y, distinto,
  no aplica la carta. Arreglado: «Earned Point» 400 → 50 al elegir una de oro. (Las cartas no
  cambian de cara: lo que se anima es la flecha EXP de la fila.)
- `0x1072` = u32 **ÍNDICE de StageReward** · u8 N · N × (u8 jugador, u8 1). Con eso AWARD RESULTS
  (`0x612B40`) suma: la EXP de las cartas + **Σ Type 0 = ORO, Σ Type 1 = EXP, Type 2 = ÍTEMS** de
  esa stage (`0x5FEA50` / `0x5FEAA0` / `0x5FEAF0`). Medido: «Exp 350 · Basic Long Sword, Basic Short
  Sword, Basic Mask ×2, HP Recovery1 ×5» (`ct_d.png`). El server da lo mismo que se muestra (toda
  la lista; 🟡 qué hacía GiveCount no se sabe; 🟡 una carta da en EXP lo que costó).

### 33 · El otro jugador se ve CON su equipo

- Miembro de la sala, `+0xBA`: 18 × 34 B (vt 0x89A38C · **u16 TIPO del ítem** · vt 0x89A380 ·
  24 B), uno por PARTE (las mismas 18 del personaje +0x72). Iba en cero → en la partida kai veía a
  rui en musculosa (20:21). Con el tipo de cada parte (`equipo_tipos`): rui con su chaqueta negra
  en la pantalla de kai (`multi_equipo_remoto.png`, 20:33). 🟡 Los 24 B de cada uno siguen en 0.

### 34 · El crash de rui, el exe ORIGINAL corriendo, y las habilidades (sin resolver)

- **El crash de rui (20:37:54)**: el juego tira una excepción de C++ a propósito (un
  `std::locale("korean")` de un log, `0x7905D0` → `CxxThrowException`) y el CRT, al buscarle un
  manejador, llamaba a `_ValidateRead` (`0x7F46BD`) → **la TRAMPA de `0x7F46C9`** (= el EIP del
  crash, `0xD03F46C9`). Resueltas a mano 5 llamadas del CRT (`APIS_A_MANO.md`): `IsBadReadPtr`,
  `GetStringTypeA`, `LCMapStringW` ×2, `GetCurrentProcess`. Exe rearmado (trampas 189 → 184).
- **El exe ORIGINAL anda** (`lanzar_empaquetado.py`): GameGuard pasado en memoria (los 3 parches a
  los 60 ms) y llega a la partida. ★ **Con el original las habilidades TAMPOCO salen** (El tester lo
  probó todo): NO es culpa del desempacado; es algo que el server no manda (o manda mal).
- Lo DESCARTADO para las habilidades (cada uno medido): F1 sólo marca el lugar en la barra; ni
  F1 ni F1 + clic izq/der/medio ni F,F,F1 bajan el MP; el cliente no manda nada al server; ninguna
  trampa ni excepción en el camino; el juego ni consulta la lista de habilidades de la cuenta
  (`0x61EC60`… no se llaman); `SetCurSkill` (`0x560AD0`) nunca se llama. El personaje local en la
  partida: HP 126,6/126,6, MP 135/135 (alcanza para el Dash: 24). La F SÍ cambia el arma.
  🟡 Pendiente: qué arranca el lanzamiento (tu video: se gasta MP y TP, hay enfriamiento).
- La barra de la DERECHA = **pociones**, teclas 1–6 (`GameItem1–6`): el HUD lee los índices 12–17
  del equipo del personaje (`personaje+0xA2`, `0x510619`) = los casilleros 12–17. La CANTIDAD es
  `+0x11` del ítem (`0x510734`): con 0 decían «0», ahora «20».

### 35 · ★ Los puntos de ESTADÍSTICA (Bonus Stat) andan

- «Bonus Stat» = **`personaje +0x6C`** (`0x51E9F4`). `registro_personaje` escribía sólo 5
  estadísticas (la 6ª no salía). Ahora: 🟡 3 puntos por nivel (el de 2009 no se sabe) → rui nivel
  25 = «Bonus Stat : 72» y aparecen los botones «+».
- Al repartir (5 Str + 3 Con: Melee Atk 112 → 127, Max HP 114.6 → 130.8) y salir, el `0x102D` trae
  las 5 nuevas y **en la 6ª los puntos GASTADOS en la tanda** (8), no los que quedan. El server
  acepta sólo si ninguna baja, lo que subió = los gastados y no pasa de los libres. Medido: se
  guarda `[5, 3, 0, 0, 0]` y al volver dice 5 · 3 · 64. ★ Revés medido: con la validación vieja
  (mal) lo rechazó y el cliente volvió solo a «0 · 72» (el server manda).

### 36 · Refinery: Create Socket, la FICHA del ítem, la durabilidad; borrar habilidad; server sin UAC

- **Server sin UAC** (el espía con WinDivert se apagó solo a las 3 h, 21:15, y reabrirlo pide el
  clic de el tester): `espiar_broker.py sin_admin` = el mismo oyente sin WinDivert ni límite, y
  `redirigir_cliente.py` desvía el `connect` de cada cliente (Frida) a 127.0.0.1:25900. Medido:
  enganchó, desvió Broker y server de juego, lobby.
- **Borrar habilidad**: `0x1043` (u32 · u32 clave) → `0x1044` (`0x54AD80`: u16 1 · u32 clave).
  Medido: «[Dash] 1 Lv. Do you want to delete the skill?» → se va de la grilla y de la barra.
- **La FICHA del ítem (36 B)**: vt 0x89A384 · u32 serial · vt 0x89A380 · **10 × u16 = la piedra de
  cada engarce** · **u32 +0x20 = 3 bits por engarce** (el `i` en los bits 29−3i…31−3i; ≠ 0 =
  ABIERTO, `0x521346`; 0 = ni se dibuja). ⛔ 0xFFFF en el u16 como «vacío»: el cliente lo busca
  como tipo de ítem y se cae (`0x61F922`, medido 21:26).
- **Create Socket**: `0x1037` (u32 · serial del ítem · serial del taladro 40001) → `0x1038`
  (`0x54B070`, 46 B: u16 1 / 0x1F41 falló · serial del taladro · i32 quedan · la ficha nueva).
  Medido: «Congratulation. Succesfully increased Socket.», taladro 5 → 4, y la ficha de la
  espada muestra el engarce. 🟡 siempre sale bien (la probabilidad de 2009 no se sabe).
- **Durabilidad = `+0xF` del ítem** (i16; la ficha muestra +0xF / MAXSOLID × 100, `0x5201F9`):
  con 10000 → «Durability: 100%» (antes 0%).
- **Enchant Item** (poner piedras): `0x1033` (u32 · serial del ítem · u8 N · N × (u8 engarce ·
  u32 serial de la piedra)) → `0x1034` (`0x54A180`: u16 1 · serial · u8 N · los 10 u16 de piedras
  → ficha+0xC · N × u32 piedras GASTADAS, que salen de la bolsa: las piedras no se apilan,
  MAXOVERLAPCNT = 1). Medido 21:31: la 21001 queda en el engarce y la ficha de la espada muestra
  **Melee Atk 24.00 (+0.70)** — el bonus de la piedra lo calcula el cliente (`0x61FDB0`).
- **Refine Spirit Stone**: `0x1035` (u32 · u8 modo: 0 Phase, 3 piedras / 1 Level, 2 · N × u32)
  → `0x1036` (`0x54AF20`: u16 1 / 0x1B5D falló · u8 modo · la piedra NUEVA 21 B · u8 N · N × u32
  gastadas). 🟡 La regla, de los datos (2 fases × 6 niveles por familia): Phase 3 × 21001 →
  21021; Level 2 × 21001 → 21002. Medido 21:35: «Blaze SoulStone1 · Refining was Successful».
- **Repair**: `0x1039` (u32 · u16 1 = Repair All) → `0x103A` (`0x54A7A0`: u16 1 · u32 ORO · u8 N ·
  N × (u32 serial · u16 durabilidad nueva)). El precio lo calcula el cliente: Σ (MAXSOLID −
  durabilidad) × REPAIRGOLD (2500 × 1 + 5000 × 4 = 22500, medido) y el server cobra lo mismo de
  `ItemTypeList.xml`. Medido 21:39: «Item has been repaired», oro 100000 → 77500. La durabilidad
  de cada ítem la guarda la cuenta (`durabilidad[serial]`). 🟡 Que se GASTE jugando no está hecho:
  no se sabe cómo lo hacía el original (y el cliente no avisa nada).
- **Purchase All** (el carrito = arrastrar al maniquí de la tienda): el cliente rechazaba con «No
  Empty Slot Available» porque **`cuenta+0x2CC` = LUGARES LIBRES de la bolsa** venía en 0: es el
  byte **+0x1A del `0x1012`** (+6 = +0x2B8, medido; nadie más lo escribe, `0x54DCEA`). Con 150 −
  los ocupados: «Selected Item has been successfully purchased», oro 77500 → 76900 (21:42).

### 37 · ★★ Por qué en OTRAS PCs el limpio no arrancaba: `GetCPInfo` (aporte externo, PR #1)

- Un usuario del repo público (Urek-Mazinoo, PR #1) encontró que el `EDA_limpio.exe` moría antes
  del menú en la TRAMPA de **`0x7EE13C`**, y lo resolvió como **`GetCPInfo`**. Verificado: es
  `_setmbcp` de la CRT: si la página de códigos está en su tabla de 4 (932, 936, **949**, 950) no
  llama a nada; si no, `GetCPInfo(página, &cpinfo)` y lee `MaxCharSize` / `LeadByte`. ★ Esta PC
  tiene la página **949** (coreana): por eso acá nunca pasó y en las PCs en español (1252) sí.
- Control al revés (simulando 1252 con Frida, `EDA_SIMULAR_ACP=1252`): el exe anterior se cae a
  los **0,3 s con EIP `0xD03EE13C`** (la trampa de ese sitio); el nuevo sigue vivo y, con
  `jugar.py`, llega a la partida (pelea incluida) sin otra trampa.
- También aportó marcar el exe sin reubicaciones (`IMAGE_FILE_RELOCS_STRIPPED`). Se aceptó el
  código y la documentación; el binario se rearmó acá con las herramientas (para que incluya el
  4.º parche y no publicar un exe ajeno): md5 `0799387e23cadd355888bd712143f2d5`.
- `eda_original.py` ahora AVISA en la consola si el juego cae en una trampa («sitio 0x…»): así
  el próximo que encuentre una sabe qué número reportar.

### 38 · ★★ El server por MÓDULOS, el server para LINUX (Docker) y las PIEZAS contadas (11-nov)

- **`servidor/juego.py` (1695 líneas) partido en módulos** por pantalla del juego (`entrada`,
  `salas`, `inventario`, `tienda`, `habilidades`, `refineria`, `partida`, más `config`, `estado`,
  `registro`, `cuentas`, `datos`, `objetos`, `relay`, `pruebas`). El corte lo hizo un script (`ast`):
  cada función se copió TAL CUAL con sus comentarios, y cada `if cmd == …` de `responder` pasó a ser
  una función con `@maneja(cmd)`. Medido, con el viejo guardado aparte:
  · `py servidor\juego.py control`: **la misma salida, línea por línea** (100 pruebas);
  · ★ los **3374 mensajes de verdad** de las capturas (`_trabajo/broker/con_*.bin`, 431 conexiones)
    pasados por el viejo y por el nuevo, con el reloj congelado: **respuestas idénticas byte a
    byte** (md5 de cada cuerpo). **El revés**: con un solo byte cambiado en el nuevo (el `0x1001`),
    1247 respuestas salen distintas — la comparación sí ve un cambio.
- **La recarga en caliente** ahora es del paquete entero (`servidor.cargar()`, la usan el espía y
  `red.py`). ⚠ **Bug medido y arreglado**: al recargar quedaban **18 manejadores de 31**, porque
  `from servidor import tienda` devolvía el módulo VIEJO (seguía como atributo del paquete y había
  registrado sus funciones en el registro viejo). Borrando también el atributo: 31 después de cada
  recarga, y el estado vivo (`_eda_partidas`) sobrevive.
- **`servidor/red.py` = el server por la red** (lo mismo que `espiar_broker.py sin_admin`, sin nada
  de Windows): escucha en 0.0.0.0, cada conexión toma el número MÁS CHICO libre (así los puertos del
  relay, `RELAY_BASE + 1 + n`, quedan acotados) y el relay corre en un hilo. Las respuestas del
  Broker salen de `reglas_broker.guion()` en memoria. `python -m servidor.red prueba IP:PUERTO`:
  un `0x0604` con la clave del EDA.exe de 2009 → `0x0607`; **el revés**: con una clave que nadie
  conoce, silencio.
  ★ **Con el juego** (`py jugar.py --server 127.0.0.1:25950`, relay prendido, el piloto):
  `0604 → 0607 0609 · 0708 → 0709 · 070a → 070b · 100f → 1010 · 1011 → 1012 · 1017 → 1018 ·
  101d → 101e · 104e → 104f · 105f → 105e` y **rui en el mapa** con el reloj corriendo.
- **Las claves sin exes**: un server en Linux no tiene los exes para sacar md5(exe + 00), así que
  `paquete_broker.CLAVES_FIJAS` trae las dos que juega la gente (la del EDA.exe de 2009,
  `a57ca836…`, y la del limpio `0799387e`, `2921cf26…`) y `EDA_CLAVES` agrega otras. **Comprobado**:
  la fija «EDA.exe de 2009» abre las capturas reales del original (`paquete_broker.py control`).
- **Docker** (`despliegue/`): la imagen corre `juego.py control` al armarse (si falla, no se arma),
  `network_mode: host` (el relay usa un puerto UDP por jugador), las cuentas y los XML en carpetas
  de afuera. Prod = `main` (25900 / UDP 26000–26200), prueba = `develop` (35900 / 36000–36200, se
  actualiza sola cada 5 min y, si un cambio no pasa las pruebas, sigue la versión anterior).
  ★ **Medido en Linux** (GitHub Actions, Ubuntu): la imagen se arma con las pruebas adentro, y el
  server por la red contesta (y calla con la clave falsa).
- **Las PIEZAS, contadas sobre el exe** (`herramientas/contar_piezas.py`, sin pefile):
  · los mensajes que el cliente sabe RECIBIR salen de cómo los registra cada pantalla —
    `mov edi, manejador · … · push cmd · push ebx · push edi · push esi · add ecx, 4 · call`
    (el lobby, `0x5441FC`) — más la escena de carga (`mov [esp+X], cmd`: `0x105E`, `0x1058`):
    **62**. El server manda **41** de esos. Faltan: 060B 1016 101A 1026 1030 1032 1046 104A 104B
    1050 1052 1054 1056 105B 105D 1060 1062 1066 106C 106D 3003. Revés: los que manda el cliente
    (`0x100F`, `0x1011`) NO aparecen como registrados.
  · las llamadas a Windows sin resolver = los `call` que siguen yendo a la TRAMPA: **183** →
    **511 de 694** resueltas (el «505» de antes era de una versión anterior del exe). Revés: el
    EDA.exe de 2009 (empaquetado) tiene 0.
- ★★ **EL VPS** (11-nov, Ubuntu 26.04): `curl … instalar.sh | bash` desde GitHub instaló Docker y
  levantó `eda-prod` (main, 25900) y `eda-prueba` (develop, 35900); las dos imágenes se armaron con
  TODAS las pruebas adentro (los XML ya vienen en `datos/` del repo). Desde esta PC, por internet:
  `servidor.red prueba` ✅ en los dos (y el revés: con la clave falsa, silencio). ★ **Con el juego**
  (`py jugar.py --server <VPS>:25900` + el piloto): el registro del contenedor tiene
  `0604 → 0607 0609 · 0708 → 0709 · 070a → 070b · 100f → 1010 · 1011 → 1012 · 1017 → 1018 ·
  101d → 101e · 104e → 104f · 105f → 105e` y la foto: **rui en el mapa, reloj en 0:00:11**, sin un
  solo «⛔» en el registro.
- ⚠ **`multi.py` contra el VPS NO llegó a la sala** (dos clientes en el lobby, ningún `101D`): el
  piloto aprieta con TIEMPOS FIJOS medidos contra un server local; por internet las respuestas
  tardan más y los clics caen antes de tiempo (las fotos del piloto, además, salen atrasadas). No es
  el server: falta que el piloto ESPERE cada respuesta. `redirigir_cliente.py` ahora acepta
  `EDA_SERVER=IP:PUERTO` (para multi.py contra un VPS).
- ⏭ Lo que falta: **cuentas de verdad** (en un server público cada conexión toma rui / kai / mio /
  ren, la primera libre: no hay login; el plan, para más adelante: SQLite y el login / descarga desde
  el launcher web de R2Beat) y **el relay entre dos PCs** (sigue sin probarse).

### 39 · ★★★ La IDENTIDAD P2P: es la MAC, y el server SÍ la recibe (si el juego se lanza con comillas)

Paso 1 del P2P directo (sin relay en el medio): saber de dónde sale la identidad con la que cada
cliente reconoce a sus pares, y si el server puede saberla.
- **Quién la escribe** (desarmado): el objeto UDP nace con la identidad vacía (constructor
  `0x74B110`). Al arrancar, `0x4E767B` llama a **`0x6229F0`** (método de la cuenta), que pide la MAC
  a Windows (**`GetAdaptersInfo`**, el thunk `0x85900C`; el 1er adaptador), la formatea con
  `"%02X:%02X:%02X:%02X:%02X:%02X"` y la guarda en **`cuenta+0x166`** (UTF-16) y **`cuenta+0x1C7`**
  (ASCII). Enseguida `0x4E76AE` le pasa `+0x1C7` al «P2PHelper»: esa es la identidad de los saludos
  `C354` (`0x74AA60` la lee de `+0xE8` del objeto UDP).
- **El `0x100F` la lleva**: `0x549940` copia `+0x166` al mensaje. Medido en las 133 capturas viejas:
  la MAC de esta PC, entera, en el desplazamiento **126** (`+0x7E`) en 15 de 133; en las otras 118,
  basura. Revés: una MAC inventada no aparece en ninguna.
- ★ **Por qué sólo a veces — la LÍNEA DE COMANDOS** (desarmado, `0x622B2C`…): después de la MAC,
  `0x6229F0` lee `GetCommandLineA()`. Si empieza con comillas, toma lo que sigue a la ruta como el
  BLOQUE del launcher (sin bloque, no hace nada); si **no** empieza con comillas, toma **la línea
  entera** como bloque. El bloque es hexadecimal (`"%02X"`), cada byte XOR la MAC en texto (en
  ciclo), y queda `"<A> <B>"` (separador: un espacio, `0x88C328`) → A a `cuenta+0xF0`, B a
  `cuenta+0x11A` (`0x622E35`, `0x622E49`, `wcscpy`). Con la ruta sin comillas, A y B salen basura
  (la «huella» del `0x0604`, que tenía pedazos de la MAC: es la MAC XOR ceros) y la copia se pasa
  de largo y pisa la MAC de `+0x166`.
  · `frida.spawn([exe])` (lo de `jugar.py`) **pone** comillas; `subprocess.Popen([ruta])` (el piloto,
    `multi.py`, el espía) **no** (Python no las pone si la ruta no tiene espacios): de ahí vienen
    casi todas las capturas — medido leyendo `GetCommandLineA` adentro del juego (`'"C:\…exe"'` con
    Frida; sin comillas con un argumento) y con `%CMDCMDLINE%` de cmd.exe para Python.
- ★★ **Medido con el juego** (server local con `EDA_LOG_HEX=1`, mismo exe, misma PC):

  | cómo se lanzó | «huella» del `0x0604` | MAC en `+0x7E` del `0x100F` |
  |---|---|---|
  | `py jugar.py` (con comillas) | **vacía** | ✅ **la real, entera** |
  | el piloto con `Popen` (sin comillas) — el revés | 20 caracteres de basura | ⛔ basura con pedazos de la MAC |

- **Arreglado**: el piloto, `multi.py`, `espiar_broker.py juego` y `foto_juego.py` lanzan ahora con
  la ruta entre comillas.
- ★ **Lo que esto abre**:
  1. **P2P directo**: el server ya puede poner en cada miembro de la sala la MAC de verdad del
     otro (la del `0x100F`) y darle su dirección DIRECTA en el `0x1059`: los saludos `C354` se
     reconocen sin que nadie reescriba nada. El relay queda sólo de respaldo (NAT simétrico).
  2. **El login del launcher**: `"exe" <hex(XOR("<usuario> <pase>", MAC))>` llega al server en el
     `0x0604`, en el UDP `0x3002` (el 1º) y en el `0x100F` (los dos). Es la puerta que va a usar el
     launcher web de R2Beat, y `jugar.py` puede hacer lo mismo (la MAC la saca con `GetAdaptersInfo`
     igual que el juego).
- ⚠ Privacidad: la MAC ya viajaba a los OTROS jugadores en cada saludo (así está hecho el juego); ahora
  además la ve el server. No se guarda en ningún lado ni va a los registros sin `EDA_LOG_HEX=1`.

### 40 · P2P directo en el server (paso 2, a medias) y de dónde salen los «75 ms» del ping de la sala

- **El server** (`servidor/relay.py`, `EDA_P2P=directo` por defecto): identidad de cada miembro = su
  MAC del 0x100F; dirección para cada par = la pública que vio el punch (`punch.json`, lo escribe
  `relay_udp.py`), la PRIVADA si comparten IP pública, y el relay sólo para quien no mandó su MAC.
  Las pruebas (`juego.py control`) lo cubren con sus reveses.
- ⚠ **Medido con el juego (dos clientes, server local)**: el `0x3006` del punch lo manda SÓLO el que
  ENTRA a una sala, y llega en el mismo instante en que el server arma el `0x1059` (tarde); el
  ANFITRIÓN no se anota nunca. ⏭ La pública de cada uno hay que tomarla al conectarse, como el
  original: el `0x0607` («UDP label») tiene que apuntar al punch del server para que el cliente le
  mande sus `0x3002` (hoy apunta al Broker muerto de 2009).
- ★ **Los ~75 ms del ping de la sala NO son la red** (`herramientas/medir_udp.py`: `sendto` /
  `recvfrom` de los dos juegos con QueryPerformanceCounter): el que recibe un ping lo CONTESTA en
  0,1 ms (mediana), pero entre que un juego manda y el otro LEE pasan 30–39 ms de mediana (hasta
  ~75) — **en la misma PC**. El dato llega a Windows enseguida y espera a que el juego lo lea: el
  juego lee el UDP cuando su bucle principal da una vuelta (`recvfrom` sólo con datos, por
  `WSAEventSelect` FD_READ|FD_WRITE, `0x750828`), y el bucle da **~32 vueltas por segundo**
  (PeekMessage). Descartado, medido: la AFINIDAD (los dos juegos en los 16 núcleos, `0xFFFF`, y el
  exe no importa `SetThreadAffinityMask`); el FOCO (con una ventana al frente: 32 vueltas/s y 39 ms,
  igual); `ClientSleepMS`, `MaxFPS`, `LatencySim`, `DropRate` (en 0, en el archivo y en la memoria de
  los dos); `alwaysfocused` (es del mouse/teclado, `0x419B85`).
- ★ **Quién marca el ritmo: la SINCRONÍA CON EL MONITOR** (esperas contadas en 5 s con Frida): en el
  hilo principal, `nvd3dum.dll` (el driver de NVIDIA) espera de a 1 ms ~2.700 veces por segundo, y
  `mss32` da una vuelta por cuadro (~28/s). Con UN solo juego abierto el bucle da **60 vueltas/s**
  (= el refresco del monitor); con DOS en la misma PC se reparten el refresco: **30 cada uno**. O sea:
  la red se lee una vez por cuadro y cada cuadro espera al monitor. `"VSyncOnFlip" "0"` en
  `autoexec.cfg` NO cambió nada (30 vueltas/s y 30,6 ms de mediana, igual): 🟡 o no se aplica o el
  driver sincroniza igual.
  ⇒ En una partida de verdad (un juego por PC, monitor de 60 Hz) cada lado espera hasta ~16 ms: el
  ping de la sala tendría que dar ~16–33 ms MÁS la red. Los «0–3 ms» de los cíber de 2009 pedían
  muchos más cuadros (pantalla completa sin sincronía, Windows XP sin compositor). ⏭ Medir con un
  juego a pantalla completa.
- ★★ **Corregido (11-nov, `herramientas/medir_vsync.py`)**: EDA **NO pide sincronía**: su `CreateDevice`
  pide `PresentationInterval = 0x80000000` (IMMEDIATE), ventana, `SwapEffect` 3 (COPY), 1 búfer,
  `Flags` 1 (LOCKABLE_BACKBUFFER). En la LISTA DE SERVIDORES el bucle da **190–900 vueltas/s**;
  sacarle el búfer bloqueable y pasar a `SWAP_DISCARD` NO cambia nada (A/B alternado: 190 / 183 /
  196 / 182) → no es eso. Lo que pasa es que **la SALA (y la partida) gastan la placa de video**:
  `nvidia-smi pmon` con dos EDA en la sala: **31–39 % de una RTX 3090 CADA UNO** dibujando ~25
  cuadros/s; la placa al 94 % (168 W). Cerrando los dos EDA: 44 % (83 W, lo demás). Con un solo
  juego en la sala daba ~60 vueltas/s; con dos, ~25–30 cada uno — de ahí el «lag» con dos juegos
  abiertos y los ~75 ms del ping. ⏭ Encontrar QUÉ dibuja la sala que cuesta tanto (y arreglarlo
  con una d3d9.dll nuestra, como en R2Beat: el proxy y Zig 0.16 ya están en ese proyecto).
- ★ **QUÉ dibuja** (`herramientas/medir_dibujo.py`, cada pedido a Direct3D 9 y a GDI, por segundo, con
  el piloto de la lista a la partida): **NO es GDI** (27 llamadas al arrancar y nada más), **NO hay
  lecturas de la imagen** al procesador (`GetRenderTargetData`, `LockRect` = 0) ni copias
  (`StretchRect` = 0), y **NO dibuja cuadros escondidos** (un `Clear` por cada `Present`). Por cuadro:
  ~120 dibujos en la lista de servidores, ~720 en el selector de stage (que baja a **12 cuadros/s**),
  ~480 en la partida (40–108 cuadros/s). Pocos para una placa moderna.
- ★★ **Pero cada cuadro le cuesta caro a la placa**: con UN solo EDA en la lista de servidores la
  placa pasa a máxima potencia (P0, 1.695 MHz) y de **85 W a 157 W (+70 W)** para ~69 cuadros/s
  (`nvidia-smi --query-gpu=pstate,clocks.gr,power.draw`). No es el porcentaje engañoso de un reloj
  bajo: es trabajo de verdad, y la cantidad de dibujos no lo explica. ⏭ Encontrar el costo por
  descarte en memoria (sacar grupos de dibujos, cambiar el filtrado de texturas…), o probar DXVK (un
  d3d9.dll libre que traduce a Vulkan). Y aparte, para la misma DLL: **la partida no suelta el mouse**
  aunque se cambie de ventana (El tester, 11-nov: sólo lo suelta con el menú de ESC).
- 🧹 Ese rato la PC tenía además 4 `find /` huérfanos de otra sesión (25 % de CPU desde las 13:27):
  cerrados con permiso. Cuidado al medir rendimiento: mirar antes `nvidia-smi` y la CPU.
- `multi.py` lee ahora el registro del server que haya (`EDA_MULTI_LOG`, o `EDA_MULTI_SSH` para el
  de un contenedor): contra red.py/el VPS leía sólo el del espía, nunca veía avanzar nada y repetía
  clics que desarmaban la sala.

### 41 · ★★★ La causa del «lag» y del ping: EDA dibuja SIN LÍMITE (diagnosticado con DXVK)

- **DXVK 3.1.1** (`dxvk-3.1.1.tar.gz` de github.com/doitsujin/dxvk, 18.041.512 B, md5 `dfca4e1e…`;
  queda en `_trabajo/dxvk/` como herramienta de DIAGNÓSTICO, no para repartir: pide Vulkan y muchas
  PCs modestas no lo tienen). Su `d3d9.dll` (x32) va al lado de `EDA_limpio.exe` sólo mientras se
  mide; `DXVK_HUD=fps,frametimes,gpuload,drawcalls` lo dibuja arriba a la izquierda y
  `DXVK_LOG_PATH` deja el registro.
- ★ El panel en la lista de servidores: **929 cuadros/s, 58 dibujos por cuadro, 0,6–2,5 ms por
  cuadro, placa al 73 %**. No es que cada cuadro sea caro: **el juego no tiene tope** (pide
  IMMEDIATE y dibuja todo lo que puede) y eso pone CUALQUIER placa a máxima potencia (P0, ~150 W).
  Con dos juegos se pelean la placa y el que pierde cae a ~25 cuadros/s: el «lag».
- ★★ **Con tope** (`dxvk.conf`: `d3d9.maxFrameRate = 120`; la variable `DXVK_FRAME_RATE` NO se
  aplicó): exactamente 120 cuadros/s y la placa en **48–84 W** (P3/P5; sin nada abierto ~40 W).
- ★★★ **Dos clientes en la sala con el tope**: el ping de la sala **8 ms / 8 ms** (antes 75 / 78) y
  el UDP «sale de uno → lo lee el otro» **4,56 ms de mediana, máximo 5,0** (antes 30–39, hasta 80).
  ⚠ El tope de DXVK agarró en UNO solo (139 vueltas/s; el otro 397/s y 24–56 % de la placa: los
  150 W que seguían): su propio registro avisa «Built-in frame rate limiter enabled. Please enable
  an external limiter».
- También del registro: el dispositivo usa **software vertex processing** (la geometría la
  transforma el procesador).
- ⏭ **La solución, sin Vulkan**: una `d3d9.dll` NUESTRA (como en R2Beat, Zig 0.16) que reenvíe al
  d3d9 de Windows y ponga un **tope de cuadros confiable** en `Present`, para cada juego abierto. Y en
  la misma DLL: **soltar el mouse** al perder el foco en la partida.

### 42 · ★★★ NUESTRA `d3d9.dll`: tope fijo, búferes rápidos y la red inmediata (11-nov)

`herramientas/dll_d3d9/` (`eda_d3d9.c`, Zig 0.16 con la receta de R2Beat; `jugar.py` la pone sola al
lado del juego, `--sin-dll` la saca). Reenvía al d3d9 de Windows y engancha Present / Reset /
CreateVertexBuffer del dispositivo y `WSAEventSelect` del exe (por su tabla de importaciones).
- **Tope + contador**: con UN juego en la lista de servidores, 120 cuadros/s exactos (antes ~900) y
  la placa de ~155 W a 85–108 W; «FPS 120» arriba a la izquierda (rectángulos, sin fuentes).
- ★★★ **EL CULPABLE DEL «LAG»** (con dos juegos en la sala seguían a **14 cuadros/s y 164 W** aun con
  el tope, y `backbuffer_rapido` —sin LOCKABLE, DISCARD— no cambió nada): sondeando el dispositivo
  del juego andando, cada dibujo bloquea su **búfer de vértices ENTERO** (96.000 B, POOL_DEFAULT,
  WRITEONLY, FVF 0x142) con **`Lock(0, 0, …, flags 0)`: ~4.200 veces por segundo, ~290 por cuadro**;
  sin flags, cada uno hace esperar a que la placa termine con el búfer. La salida en la dll: esos
  búferes se crean `DYNAMIC` y cada `Lock(0,0,0)` pasa a `DISCARD` (el juego siempre escribe desde el
  principio lo que va a dibujar). **Dos juegos en la sala: 120 cuadros/s cada uno, la placa de 164 W a
  46 W (P5), la espera de red de 30–80 ms a 7,3**. En la partida se ve bien (sin piezas rotas).
- ★★ **La red ya no depende de los cuadros**: el juego lee el UDP una vez por cuadro (a 120 → ping 8;
  a 480 → ping 2). La dll se queda con el evento que el juego registra para su socket UDP
  (`WSAEventSelect`, FD_READ) y espera el cuadro ESCUCHANDO ese evento: si llega un mensaje, suelta al
  juego en el acto. Con tope ESTRICTO (por defecto) ese cuadro adelantado **gasta el turno siguiente**:
  el promedio queda exacto. **A 60 cuadros/s: ping de sala 1 ms / 0 ms**, 60 exactos en los dos, sin
  congelarse; en la partida (≈3.000 mensajes/s) la espera es de un cuadro como mucho (7,7 ms de
  mediana a 60) y la placa ~80 W con dos juegos.
- ⛔ **Probado y descartado: llamar al bombeo de red del juego desde la espera.** `0x74D530` (thiscall,
  objeto GLOBAL `0x948F90`: mira el evento del socket +0xAC sin esperar y llama a `0x750110` =
  WSAEnumNetworkEvents → leer) corre en el hilo principal, una vez por cuadro (medido con Frida). Pero
  llamado desde adentro del Present, **los dos juegos se CONGELARON** apenas se usó en la sala (1 y
  después 12 bombeos). Queda detrás de `bombeo_red=0`.
- ⚠ Dos errores míos en el camino, medidos y arreglados: el juego crea OTRO dispositivo al entrar a la
  partida, y la dll aplicaba el «state block» del contador del dispositivo VIEJO (glitches gráficos y
  el contador que desaparecía) → ahora cada uno el suyo. Y el piloto: a 60 cuadros/s `multi.py` creía
  que un juego no había entrado al lobby (el 0x1017 llegaba después de su plazo fijo), repetía el
  piloto entero y «Enter Lobby» caía sobre «Search User» (un diálogo abierto). Ahora
  **`herramientas/pantallas.py`** reconoce la pantalla por una huella (zona achicada a 16×6 en
  grises: 0 contra sí misma, ≥17 contra las otras) y `multi.py` espera cada pantalla antes de apretar.

### 43 · El PR #3 (Hysteria-xyz): el ciclo de la sala, el 0x106C, y la puerta rota de la dll (11-nov)

- **El PR** partía de antes de los módulos (`servidor/juego.py` de 1.773 líneas): se pasó a mano lo útil.
  ★ **Leave Room** (`0x1045` → `0x1046` u16 1; manejador del cliente `0x54E380`): medido con el juego,
  el invitado aprieta «Leave Room» y vuelve al LOBBY (sin quedarse en «Waiting for Response»), la
  lista de salas pasa a «1/3» y en la sala del anfitrión queda sólo él. **Echar** (`0x1051` → `0x1052`
  al anfitrión, `0x1054` al echado), **pasar el mando** (`0x1058` tipo 3 con el nuevo anfitrión) y
  **título/contraseña** (`0x1049` → `0x104A`) quedan con sus pruebas (y sus reveses: echar si no sos el
  anfitrión, echarte a vos mismo); en pantalla, sólo Leave Room.
- ⛔ **El `0x106C` NO hace lanzar las habilidades** (el PR decía que sí). El manejador existe (`0x547A60`:
  u8 jugador · u8; si es mi número, «CursorCenter 1» y mira el estado 0xA = espectador) pero, con un
  Warrior nivel 10 y sus habilidades en la barra (cuenta de `preparar`), F1 / F2 / F1+clic derecho no
  gastan MP con NI sin él (la barra del MP: 210 → 210 píxeles en las tres teclas, las dos veces). Como
  además agarra el mouse, queda apagado (archivo `con_106c` para prenderlo). ⚠ La 1ª medición salió
  inválida: los juegos se conectaron a OTRO server de prueba de las 17:19 (otra carpeta de cuentas: rui
  sin habilidades, y el `0x106C` salía en las dos corridas) — se cerró y se repitió.
- ★★ **La puerta rota era de NUESTRA dll** (El tester la vio): A/B con `EDA_BUFERES_RAPIDOS=0`, la puerta
  del primer mapa sale entera; con DISCARD, media negra. Medido con `EDA_MEDIR_ESCRITURA=1`: CADA Lock
  del juego escribe DESDE EL PRINCIPIO del búfer ~100 B (un cuadradito) y a veces 38 KB de una (el
  escenario), que se dibujan después entre medio de los cuadraditos: DISCARD borraba esos 38 KB.
  Volcar la copia entera en cada Unlock arregla la puerta pero la placa volvió a 153 W. ★ **El anillo**:
  el juego escribe en una COPIA, y la dll sube a la placa sólo lo que cada dibujo usa (el dibujo dice qué
  vértices), en el próximo lugar libre (NOOVERWRITE; lleno → DISCARD), corriéndole el vértice base.
  Medido: la puerta entera, ~117 B por subida, 120 cuadros/s en los dos juegos en la partida (la placa
  ~152 W con dos juegos a 120 en la partida; la versión con la puerta rota daba ~90: a afinar).

### 44 · ★★ El juego SIN PYTHON: la `d3d9.dll` lo lleva al server (12-nov)

- **Para qué**: hasta acá, conectarse pedía Python + Frida (`redirigir_cliente.py` / `eda_original.py`
  desvían el `connect` al Broker de 2009). Un jugador común no puede tener eso: el cliente para
  repartir (vía launcher) tiene que ser **una carpeta y un doble clic**.
- **Cómo**: `EDA_limpio.exe` pide `ws2_32!connect` **por nombre** (2º descriptor de WS2_32; medido con
  pefile), así que la dll cambia esa entrada de la tabla de importaciones, igual que `WSAEventSelect`
  (§42). Sólo el destino `218.145.66.187:25000` (IP y puerto exactos, IPv4) y sólo si
  `eda_d3d9.ini` tiene `[red] server=host[:puerto]` (o `EDA_SERVER`, que manda); un nombre se resuelve
  en el primer `connect` (no en `DllMain`). El server de juego que da la lista apunta al MISMO destino
  (`reglas_broker.py`), así que un solo desvío cubre las dos conexiones.
- **Medido** (EDA_limpio.exe abierto a pelo, `Popen('"ruta"')`, SIN Frida, `redirigir_cliente` cerrado):
  `EDA_SERVER=<VPS>:35900` → la LISTA DE SERVIDORES del server de prueba («EDA vuelve»), ENTER →
  **SELECT CHARACTER** con rui; en `eda_d3d9.log`, dos desvíos («connect a 218.145.66.187:25000 →
  …:35900 (1)» y «(2)»). ★ **El revés**: el mismo exe y la misma dll sin server → «Can't connect to
  server». Con `jugar.py` (Frida) también anda: `eda_original.lanzar` le pasa `EDA_SERVER` con el
  mismo destino, así un ini con otro server no lo desvía a otra parte.
- **La identidad P2P (§39)**: abrir el exe por el shell (`Invoke-Item`, lo mismo que el doble clic)
  deja la línea de comandos `"C:\…\EDA_limpio.exe"`, CON comillas: la MAC llega al server.
- **De paso, las trampas sin Frida**: un manejador de excepciones de la dll anota en `eda_d3d9.log` el
  sitio de una llamada SIN RESOLVER (salto a `0xD0000000 + sitio − 0x400000`), como hacía
  `JS_TRAMPA` de `eda_original.py`: un jugador puede mandar ese número. No cambia la caída.
- ⚠ Con el `EDA.exe` ORIGINAL (ASProtect) esto no aplica: sus importaciones las arma ASProtect; ese
  sigue con `jugar.py --original`.

### 45 · ★★ EL LOGIN: el pase del portero de R2Beat → un ticket → el 0x100F (12-nov)

- **Lo decidido** (El tester, por la sesión de R2Beat): R2Beat arma un PORTERO aparte en su VPS (Chile)
  que da un **pase** firmado (JWT Ed25519: `iss` r2beat-portero, `aud` eda, `sub` = uid, `exp` +300 s,
  `jti`) sólo a las cuentas APROBADAS para EDA. Nuestro server no le pregunta nada a Chile: comprueba
  la firma con la clave pública (JWKS) y da un **ticket** de 20 letras (`servidor/porteria.py`, HTTP
  `POST /eda/pase` en `servidor/red.py`). El contrato para el launcher: la carpeta de notas de la
  sesión, `EDA_PARA_EL_LAUNCHER.md`.
- **El bloque del launcher lo arma la dll**: `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]` →
  la dll lee la MAC como el juego (1er adaptador de `GetAdaptersInfo`, `%02X:`…), hace
  hex(XOR("usuario ticket", MAC)) y le devuelve esa línea al juego desde `GetCommandLineA` (su
  entrada en la tabla de importaciones). El 3º, el server. Medido: el log de la dll dice «el bloque
  del launcher (15 bytes)» para `12345 Tk9abcDEF`, y el server lo recibe.
- ★ **Dónde llegan A y B, medido** (antes 🟡): en el **mensaje** `0x100F`, A en `+0x08` y B en
  `+0x32` (en el cuerpo, `+0x04` y `+0x2E`), UTF-16. Después del 0 final hay basura (no se limpia el
  campo). ⚠ **Con 20 caracteres justos NO viene el 0**: el ticket de 20 llegó seguido de `9b 8d`
  (otro campo); leyendo 42 bytes salía un carácter de más y el server rechazaba el ticket bueno (el
  juego decía «Can't Connect»). Se lee hasta 40 bytes; la prueba arma el 0x100F igual que el juego
  (sin 0 con 20) y el lector viejo la falla. La MAC (`+0x7E`) llega intacta con el bloque.
- **Medido con el juego** (server local con `EDA_LOGIN=pase` y un portero de mentira con clave propia):
  el pase → `POST /eda/pase` → ticket → el juego entra a SELECT CHARACTER como **`r2b_4242`**.
  ★ **El revés**: el mismo usuario con un ticket inventado → `0x1010` con error y el juego muestra
  «Can't Connect to server. Refreshing Server list.». Con `0x66` y `0x89A` sale ese texto; con `0x899`
  no salió nada (se queda `0x66`). En modo `pase`, una conexión sin ticket no recibe nada más (ni las
  reglas fijas). En modo `abierto` (el de siempre), todo como antes: rui / kai… por orden.
- **Las pruebas** (`py servidor\juego.py control`): 21 nuevas, cada rechazo del pase con su revés
  (repetido, firma cambiada, otra clave, kid desconocido, `alg` none, otra audiencia, otro emisor,
  vencido 31 s / no vencido 29 s, `sub` que no es un uid, basura) y el 0x100F (ticket inventado, de
  otra cuenta, sin bloque, vencido, anulado por uno nuevo).
- ★ **El cliente para repartir, medido**: una carpeta con SÓLO 16 archivos (Data.dat, EDA_limpio.exe,
  EdaENGTest.ini, LTMsg.dll, d3dx9_29.dll, mss32.dll, redist/ ×7, autoexec.cfg, d3d9.dll,
  eda_d3d9.ini; 354.683.873 B) entra al server con el ticket. Sin `EDA.exe`, `GameGuard.des`, el
  Nyx launcher/patcher ni `img/`. El juego escribe `NetTrace.log`, `eda_d3d9.log` y, al cerrar,
  REESCRIBE `autoexec.cfg` (las teclas salen en otro orden): es del usuario.
- ★ **Con el portero DE VERDAD** (su clave local de prueba y un pase firmado por él, de la sesión de
  R2Beat; `sub` 999001, `iat` 1794000000, `exp` +300): con el reloj en 1794000010 → ticket. Los
  reveses: con la hora real → «vencido»; un carácter cambiado en la firma → «firma»; en el medio
  del payload → «formato» (el JSON se rompe antes); este server esperando otro `aud` → «audiencia».
  En prod, `EDA_PORTERO_CLAVES=https://r2beatlatino.com/cuentas/clave-publica`. El portero también
  da el manifest del cliente sólo a cuentas aprobadas (la descarga, del lado de R2Beat).

### 46 · ★ El cliente se reparte por Cloudflare; el VPS sólo atiende a Cloudflare (12-nov)

- **Lo decidido** (El tester): el cliente para repartir se baja SÓLO por la CDN de Cloudflare («ip directa
  no se entrega»), desde el VPS de EDA. Un dominio con la nube naranja (la web: `/eda/pase` y
  `/files-eda/`) y un subdominio sin nube para el juego (TCP directo al 25900). En todo lo técnico, el
  dominio va en PUNYCODE (el exe de 2009 resuelve en ANSI; el launcher valida `[A-Za-z0-9.-]`).
- **En el VPS** (`despliegue/caddy.sh` y `despliegue/cortafuegos.sh`, que se pueden volver a correr):
  Caddy 2.11.9 con el **certificado de origen de Cloudflare** (la clave EC P-256 se generó en el VPS y
  no salió; el CSR lo firmó Cloudflare para el dominio y su comodín, hasta 2041; verificado que es de
  esa clave). Un `route`: lo que no viene de un rango de Cloudflare → 403; `/eda/*` → el login en
  127.0.0.1:25901; `/files-eda/*` → `/opt/eda/files-eda/`, con `Cache-Control: public, max-age=31536000,
  immutable`; lo demás → 404. ufw: 22, 25900, 35900 TCP y el relay UDP (26000–26300, 36000–36300)
  abiertos; 80/443 sólo desde los rangos de Cloudflare.
- **Medido**: los 16 archivos en el VPS con el md5 del manifiesto (`md5sum -c`: 16 OK). Por Cloudflare:
  `LTMsg.dll` MISS → HIT, md5 igual; `Data.dat` 345.232.384 B en 18,8 s (~18 MB/s) MISS, y el pedido
  siguiente **HIT**. ★ El revés: a la IP del VPS directo (443) no conecta (ufw). `/` → 404.
  `/eda/salud` → 502: prod (`main`) todavía no tiene el código del login.
- ⚠ **Un 404 quedó guardado en Cloudflare**: se probó un archivo antes de que terminara la subida y la
  Cache Rule (Edge TTL de 1 año que pisa al origen) guardó el 404 (`HIT`). Pedido a la sesión de
  R2Beat (tiene el token de esa zona): TTL largo sólo para 200 y purgar el prefijo de la release. ⇒ La
  regla para las próximas: **no pedir ningún archivo de una release antes de que esté entera** (subir,
  `md5sum -c`, y recién después probar).
- ★ **Tiered Cache (Smart), medido** (lo pidió el tester: «que los espejos o zonas se pidan la cache entre
  ellos y no vayan al vps»; lo prendió la sesión de R2Beat, gratis en el plan Free, confirmado con GET;
  la regla ya no guarda errores: 300–599 sin guardar; se purgaron las 16 URLs, y `EdaENGTest.ini` volvió
  con su md5). Con el registro de Caddy (`/var/log/caddy/eda.log`, cada pedido que LLEGA al VPS): un
  archivo que nadie había pedido (`redist/mssdolby.flt`), pedido desde acá → lo atiende el centro de
  **Río (GIG)**, MISS; pero el pedido que llegó al VPS vino del centro de **Miami (MIA)**, el nivel de
  arriba. El 2º pedido: HIT en GIG, y ningún pedido más al VPS. O sea: la zona de abajo le pidió a la
  de arriba, y sólo la de arriba fue al VPS, una vez.
- ★★ **Con un pase REAL de prod** (el portero de R2Beat en prod, una cuenta aprobada para EDA, firmado con
  la clave de prod; server local con `EDA_LOGIN=pase` y `EDA_PORTERO_CLAVES` = la URL del JWKS de prod):
  1.er canje → 200 y ticket para el uid; 2.º canje del MISMO pase → 409 «repetido». El cliente para
  repartir con `<uid> <ticket> 127.0.0.1:…` → SELECT CHARACTER como `r2b_<uid>`. La cadena entera
  (portero → pase → canje → ticket → dll → 0x100F → cuenta) anda con las claves de verdad.
- **Prod con la clave del portero** (12-nov, con el OK de el tester): `EDA_PORTERO_CLAVES` = el JWKS de prod en
  `/opt/eda/prod.env`, `EDA_LOGIN` sigue `abierto` (todos entran; el canje ya anda para cuando salga el
  launcher 2.5). Verificado ADENTRO del contenedor: `porteria.claves()` → el kid de prod.
- **El panel de aprobaciones del portero también en `/admin`** del dominio (`caddy.sh … <host del panel>`:
  `/admin*` → `https://<panel>/cuentas/admin*`, dentro del filtro «sólo Cloudflare»). Medido por
  Cloudflare: `/admin` 200 («EDA · Aprobaciones»), `/admin/lista` sin sesión 401; lo demás igual
  (`/eda/salud` 200, `/files-eda/…` 200, `/otra` 404).
- ★★★ **EL LOGIN PRENDIDO EN PROD** (12-nov, con el OK de el tester, después de publicado el launcher 2.5 de
  R2Beat y de la prueba en prod con un pase real: canje 200, el 2.º 409): `EDA_LOGIN=pase` en
  `/opt/eda/prod.env` (copia `prod.env.antes_pase`). Verificado adentro del contenedor (login pase, el kid
  de prod) y por Cloudflare (`/eda/salud` → «pase»). ★ El revés, con el juego contra prod por el
  subdominio: un ticket inventado → «Can't Connect to server». Sólo entran las cuentas aprobadas en el
  portero; el server de prueba (35900) sigue abierto. Volver atrás: `EDA_LOGIN=abierto` y
  `actualizar.sh prod --forzar`.

### 47 · La 1.ª partida en prod entre dos casas: el anfitrión nunca se registra en el punch (12-nov)

- **Lo que vio el tester**: sala en prod con dos cuentas reales (`r2b_<uid>`, cada una en su casa), y el
  ping del anfitrión en **-1000 ms** (= los juegos no se hablan por UDP). Largaron la partida y a los
  6 s el juego del anfitrión se cortó (`Connection reset by peer`).
- **Medido en el VPS** (`relay.log`, `punch.json`, el log del server): el INVITADO mandó su «registrame»
  (`0x3006`) al entrar a la sala → el relay lo ubicó en su IP pública. El ANFITRIÓN **nunca** lo mandó
  (`punch.json` sólo con el invitado). Uno de los dos no había mandado su MAC en el 0x100F, así que el
  server dio el RELAY en los dos sentidos (`dir_udp`). Resultado: **187 datagramas del anfitrión
  «descartado … (origen None)»** (el relay no sabía de quién era esa dirección) y **185 del invitado
  reenviados a la dirección de respaldo 127.0.0.1** del anfitrión (inútil entre dos casas).
- **El arreglo** (`herramientas/relay_udp.py · reconocer`): a un datagrama de una dirección
  desconocida, el relay lo atribuye 1) por la IDENTIDAD que viaja en él (la MAC de su saludo, en texto
  o UTF-16, si es la de un jugador del mapa que no sea el destino) o 2) por DESCARTE (un único jugador,
  fuera del destino, sin dirección real). Desde 127.x no adivina. Con eso el anfitrión queda ubicado
  con su primer datagrama, y desde ahí el reenvío anda en los dos sentidos. Pruebas: 6 nuevas en
  `relay_udp.py control`, con sus reveses (dos candidatos sin identidad → nadie; la identidad del
  destino no cuenta; desde 127.x nada).
- 🟡 Falta medirlo con dos casas de verdad (lo que pasó acá no se reproduce en una sola PC).
- **2.ª prueba en prod (con el arreglo de arriba)**: otra vez -1000. Medido: **374 datagramas del
  anfitrión descartados**. Esta vez NINGUNO de los tres conectados había mandado su MAC en el 0x100F
  (todos con la identidad inventada `02:00…`), así que no hubo identidad que reconocer; y el descarte
  era entre TODO el server: dos sin registrar (el anfitrión y uno de otra sala) → no decidía.
  ⇒ **El server le escribe al relay la SALA de cada uno** (`relay.json` → `"sala"`, reescrito al crear,
  entrar, salir, echar y al cerrarse una conexión), y el descarte es **dentro de la sala del destino**.
  Además, `cerrada()` ahora saca al que se fue de la sala donde era invitado (antes quedaba colgado).
  Pruebas: la de prod reproducida en `relay_udp.py control` (sin sala → nadie; con sala → el anfitrión)
  y en `juego.py control` (el mapa con las salas; el que se cierra sale del mapa, con su revés).
- 🟡 **¿Por qué no llega la MAC?** (los juegos del launcher 2.5). Ahora el server anota en su registro
  los 34 bytes de +0x7A cuando no son una MAC válida («0x100F sin MAC válida»): a mirar en la próxima.
