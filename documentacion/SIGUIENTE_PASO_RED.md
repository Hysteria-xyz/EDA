# ★ El siguiente paso: ponerse en el medio y mirar los bytes

> **Esto es la hoja de ruta de la tarea que sigue**, escrita el 2026-11-10 para que se pueda
> retomar sin tener en la cabeza nada de la sesión anterior. Lo que ya está medido está en
> `documentacion/MEDICIONES.md` (corrida 14); acá va **dónde estamos, cómo reproducirlo y qué
> hacer**, en ese orden.

---

## 000 · ★★★ ACTUALIZACIÓN 10-nov (13 h): EL CLIENTE LLEGA AL LOBBY

ENTER → server de juego → SELECT CHARACTER → crear personaje → LOBBY, todo con el oyente
contestando por reglas. ★ **El protocolo entero: `documentacion/PROTOCOLO.md`.** Cómo se llegó,
con cada crash y su causa: MEDICIONES corrida 16 §7–§9.

### ⏭ La tarea que sigue: el selector de stages

Create Stage abre «Chapter 1 · Start of the Search 1Lv~3Lv» y queda en «Target search……» sin
mandarle nada al server. Los datos del capítulo los tiene el cliente (en memoria, parseados).
Candidatos (🟡, sin medir): la lista N1 del 0x1018 (registros de 10 bytes, mapa con clave u32 +
dos bytes: ¿progreso por misión?) o código de esa ventana que el exe armado no corre bien. Hay
que encontrar la clase de esa ventana y ver qué lee para poblar el mapa.

---

## 00 · ★★★ ACTUALIZACIÓN 10-nov (noche): EL CLIENTE LLEGA A LA LISTA DE SERVIDORES

Todo lo de §0 está hecho y algo más (MEDICIONES **corrida 16**):

- ✅ El intercambio entero con el Broker hasta la lista: `0604 → 0607+0609 → 0708 → 0709 →
  070A → 070B`. El oyente lo contesta solo con **`py herramientas\reglas_broker.py`** (escribe
  `_trabajo/broker/reglas.json`, que `espiar_broker.py` relee en cada mensaje).
- ✅ La clave AES **no es fija**: es **MD5(exe + 0x00)**. `paquete_broker.py` la recalcula sola.
- ✅ El juego ya no se cierra a los 10 s (tercer parche de `sin_gameguard.py limpio`).
- ✅ `herramientas/foto_juego.py` le saca foto a la ventana: anuncio + «EDA Local [Open]».

### ⏭ La tarea que sigue: ENTER → el server de juego

```
py herramientas\sin_gameguard.py limpio      # si se rearmó el exe
py herramientas\reglas_broker.py             # el guion hasta la lista
py herramientas\espiar_broker.py control     # el espía (UAC una vez; dura una hora)
cd _trabajo\juego && EDA_limpio.exe          # elegir «EDA Local» y apretar ENTER
```

ENTER (`0x549300`) desconecta del Broker y conecta a la IP:puerto del registro elegido
(`0x744750`, con `+0x31` como tercer dato). El guion pone `218.145.66.187:25000`, así que esa
conexión también cae en el oyente: lo que llegue después del ENTER es **el primer mensaje al
server de juego**. Mirar `_trabajo/broker/espia.log`, y si no se puede abrir con las claves
conocidas, puede ser otro protocolo (o el UDP de LithTech: el espía anota el UDP a esa IP).

🟡 También pendiente: el `+0x31` del registro, el `00 0c` de la cabecera, el comando `0x3003`
(`OnPktRBC2NATTypeSort`), y el `0x1010` que registra la pantalla de la lista.

---

## 0 · ★★★ ACTUALIZACIÓN 10-nov (tarde): §3 está HECHO, y el primer paquete está descifrado

- ✅ **El redirector y el oyente andan** — `herramientas/espiar_broker.py`, con sus controles al
  revés en verde (MEDICIONES corrida 15, §1).
- ✅ **El cliente habla primero**: 72 bytes al conectar. (⛔ lo de «cierra a los 10 s» era GameGuard cerrando el juego: corrida 16)
- ✅ **Descifrado**: cabecera de 8 en claro + **AES-128-ECB** con una clave fija; cada bloque de 16
  es la magia `B6 A2 C2 A5` + 12 bytes de datos. El mensaje es el **comando `0x0604`**, de 44
  bytes. `herramientas/paquete_broker.py` abre y arma, y su control lo prueba contra las capturas
  reales byte a byte.
- ⛔ La pista del **RC4 derivado de MD5 era falsa** para el Broker: el juego no llama a ninguna
  `Crypt*` al mandar. El cifrado es una AES propia del exe (`0x624140`).

### ⏭ La tarea que sigue: qué CONTESTA el server al 0x0604

```
py herramientas\espiar_broker.py control        # arranca el espía (UAC) y prueba los controles
py herramientas\espiar_broker.py juego          # el juego manda su 0x0604 al oyente
py herramientas\espiar_cripto.py --segundos 18  # mismo, con breakpoints en el cifrado
py herramientas\paquete_broker.py abrir _trabajo\broker\con_002.bin
py herramientas\espiar_broker.py parar
```

1. **Encontrar dónde descifra el cliente**: el otro método de bloque del objeto de cifrado es
   **`0x750C30`** (redondea a **16**, o sea que recibe bloques enteros → muy probablemente el de
   descifrar), que llama a **`0x624200`**. Ya están en `EXE_FUNCIONES` de `espiar_cripto.py`: en
   cuanto llegue algo del «server», se va a ver.
2. **Darle algo para descifrar**: que el oyente conteste un paquete armado con
   `paquete_broker.armar(mensaje(<cmd>, <cuerpo>))`. Para eso hay que agregarle a
   `espiar_broker.py` un modo que conteste (hoy, a propósito, no contesta nada). Con un comando
   cualquiera alcanza para la primera vez: lo que importa es **ver el despacho** — el `switch` por
   comando que viene después de descifrar, y qué comando espera el cliente como respuesta al 0x0604.
3. 🟡 El **RSA de juguete** (`n = 5249`, semilla fija `0x2A4`) está cargado en el mismo objeto y el
   primer paquete no lo usa: es candidato para la respuesta del server o para el paso siguiente.
4. ⚠ El `00 0c` de la cabecera no se entiende todavía (¿`SERVICE="12"`?). Al contestar, copiar el
   que mande el cliente.

---

## 1 · Dónde estamos, en cinco líneas

- ✅ El exe está **desempacado** (`_trabajo/EDA_libre/EDA_libre.exe`), y 494 de las 694 llamadas
  que ASProtect desvió están restauradas.
- ✅ **GameGuard pasado.** La copia parchada que hay que usar es **`_trabajo/juego/EDA_limpio.exe`**.
- ✅ El juego **abre su ventana de 800×600**, renderiza (`D3DProxyWindow`, `DIEmWin`) y llega a la
  red. El tester vio en pantalla **«no se puede conectar al servidor»**.
- ✅ **Sabemos a dónde quiere conectarse: `218.145.66.187:25000`** (TCP), y abre un socket **UDP en
  57654**. El dato sale de un XML comprimido dentro de `Data.dat`.
- ⚠ El exe parchado **se muere solo a los ~12 s**. No es GameGuard: son llamadas desviadas sin
  resolver (ver §5).

---

## 2 · Cómo reproducir todo esto desde cero

```
py herramientas\inventario.py                      # control: el cliente de 2009 está sano (57/57)
py herramientas\desempacar.py construir            # arma _trabajo/volcado/eda_1/EDA_libre.exe
copy _trabajo\volcado\eda_1\EDA_libre.exe _trabajo\EDA_libre\EDA_libre.exe
py herramientas\sin_gameguard.py control           # control de los parches
py herramientas\sin_gameguard.py limpio            # -> _trabajo/juego/EDA_limpio.exe
py herramientas\conexiones.py control              # control de la herramienta de red
py herramientas\conexiones.py --exe EDA_limpio.exe --segundos 45
```

La última línea tiene que imprimir, a los ~1,6 s:

```
  TCP -> 218.145.66.187:25000  (SYN_SENT)
```

El modo ventana es `"windowed" "1"` en **`_trabajo/juego/autoexec.cfg`** (variable de consola de
LithTech, **no** un argumento de línea de comandos). El original quedó como `autoexec.cfg.bak`.

⛔ El juego **nunca** se corre desde `cliente/`.

---

## 3 · La tarea: ponerse en el medio de `218.145.66.187:25000`

El cliente manda su primer paquete y nadie contesta. Hay que **recibir esa conexión y guardar los
bytes crudos**, que es el primer dato real del protocolo del Broker. Dos piezas:

### 3a. El redirector

Cuatro maneras, con lo que cuesta cada una. **La elegida es la (A)**, que es la que el tester pidió y
la que además deja la puerta abierta a modificar el tráfico después:

| # | cómo | necesita | a favor | en contra |
|---|---|---|---|---|
| **A** ★ | **WinDivert**: interceptar el TCP saliente a `218.145.66.187:25000` y reescribirlo a `127.0.0.1:25000`, reescribiendo la vuelta para que el cliente crea que habla con el server real | admin (UAC) | no se toca ni el exe ni `Data.dat`; sirve igual para **editar** paquetes más adelante; es el camino ya andado en R2Beat | driver, y el proceso elevado abre su propia consola (su salida va a archivos, no al que lo lanzó) |
| B | levantar `218.145.66.187/32` como **IP secundaria** en una interfaz local (`netsh interface ipv4 add address`) y escuchar en `0.0.0.0:25000` | admin, una vez | sin driver; reversible con `netsh ... delete address` | cambia la configuración de red de la máquina (⚠ hay que acordarse de deshacerlo); no permite editar nada |
| C | cambiar el XML **dentro de `Data.dat`** a `127.0.0.1` | entender el formato «Softnyx File System» + zlib y rearmar el paquete | el cliente va solo a donde queramos, sin nada corriendo al lado | es un proyecto aparte, y el paquete está firmado (ver §6) |
| D | parchear el exe para que `0x74E420` reciba otra IP | nada | trivial de hacer | ensucia el exe desempacado, que es el entregable limpio; y oculta el dato real |

**Qué hay que mirar del `proxy_mitm.py` de R2Beat** (las herramientas de red de R2Beatproxy_mitm.py`): el
mecanismo de redirección ya está resuelto ahí y es **genérico**; lo específico de R2Beat son los
puertos (`28004`/`28008`), el encuadre y el cifrado. Para EDA:

- el puerto es **25000** (y el local, p. ej. `127.0.0.1:9000`);
- ⚠ **la IP de EDA está clavada, no hace falta el modo `SERVER=auto`**: es `218.145.66.187`;
- ⚠ **el truco para no hacer un bucle**: la conexión *propia* del proxy al server real se distingue
  por su **puerto de origen** (un POOL reservado) y se deja pasar sin tocar. Acá, encima, el server
  real **está muerto**, así que lo más simple es que el proxy **no reenvíe nada** y sólo registre.
- ⚠ `proxy_mitm.py DESCUBRIR=1` **sólo ve TCP**. El UDP de LithTech (puerto 57654 del lado del
  cliente) no lo anota — y para la partida el UDP es lo que importa. Si se adapta, agregarle UDP.

### 3b. El oyente

Un `socket` que escuche en el puerto redirigido, acepte, y **guarde a archivo todo lo que llegue**
(hexa + ASCII, con el tiempo de cada trozo). Nada más: **no** contestar nada en la primera corrida.

★ **Por qué no contestar nada la primera vez**: hay dos posibilidades y conviene saber cuál es
antes de inventar una respuesta —

1. **el cliente habla primero** ⇒ vamos a tener sus bytes, y ahí empieza el trabajo de protocolo;
2. **el server habla primero** ⇒ no va a llegar nada y el cliente va a cortar por timeout. Eso
   también es un dato, y **hay que distinguirlo de «el redirector no funciona»**.

### 3c. Los controles que no se pueden saltear

- ★ **El control al revés del redirector**: con el redirector corriendo, una conexión a
  `218.145.66.187:25000` hecha **a mano** (un `socket` de Python) tiene que caer en el oyente. Si
  no cae, lo que no ande es el redirector, no el juego.
- ★ **Y el control de que el oyente ve algo**: mandarle unos bytes conocidos a mano y comprobar que
  aparecen en el archivo. Sin esto, «el cliente no mandó nada» no significa nada
  (*un negativo necesita un barrido*).
- ★ **Y el de que el juego sigue llegando ahí**: `conexiones.py` tiene que seguir mostrando el
  intento. Si con el redirector puesto el destino pasa a ser `127.0.0.1`, mejor: es la prueba de
  que la redirección tomó.

---

## 4 · Lo que ya se sabe del camino de red, en el código

```
0x74EB30   el Connect del helper TCP (método virtual: nadie lo llama por nombre)
  0x74EB40   call 0x7E1A4C                  time(0)  -- para el timeout
  0x74EB51   socket(AF_INET=2, SOCK_STREAM=1, IPPROTO_TCP=6)      [0x88A540]
  0x74EB6D   WSACreateEvent                                        [0x88A4FC]
  0x74EB87   WSAEventSelect(s, ev, 0x33)                           [0x88A514]
  0x74EBA2   connect(s, this+0x94, 0x10)                           [0x88A578]
  0x74EBB3   cmp eax, 0x2733                WSAEWOULDBLOCK (10035): es no bloqueante

0x74E420   SetAddr(this, const char* ip, u_short puerto)
  mov word [esi+0x10], 2       sin_family = AF_INET
  inet_addr(ip)  -> [esi+0x14] sin_addr
  ntohs(puerto)  -> [esi+0x12] sin_port
  ⇒ el sockaddr_in está en this+0x10 de ese sub-objeto, que vive en +0x84 del helper TCP

0x74C026.. un Connect(ip, puerto, ...) genérico que recibe la IP COMO PARÁMETRO
0x54598C   imprime «[RECONFIRM BROKER IP,PORT] IP:%s,addrPort:%u,Port:%u»
0x4FFDFF   imprime «Broker ConnectFail»
0x819582   el OTRO connect (hay dos): mirar qué es
```

⚠ **Los `socket*` NO son llamadas desviadas**: van por el casillero de imports de verdad (`ws2_32`
es una de las 22 DLL que el exe empacado declaraba). Por eso **no** aparecen en
`_trabajo/apis_finales.json` y por eso funcionan sin que las hayamos resuelto. Los casilleros
útiles, leídos del volcado:

| casillero | API | casillero | API |
|---|---|---|---|
| `0x88A540` | `socket` | `0x88A578` | `connect` |
| `0x88A524` | `inet_addr` | `0x88A544` | `inet_ntoa` |
| `0x88A528`, `0x88A51C` | `ntohs` | `0x88A50C`, `0x88A55C` | `ntohl` |
| `0x88A510` | `gethostbyname` | `0x88A560` | `gethostname` |
| `0x88A554` | `sendto` | `0x88A558` | `recvfrom` |
| `0x88A56C` | `send` | `0x88A538` | `closesocket` |
| `0x88A530` | `bind` | `0x88A534` | `setsockopt` |
| `0x88A508` | `WSASend` | `0x88A520` | `WSAGetLastError` |

---

## 5 · El otro frente: el exe se muere a los ~12 s

Independiente de la red, y conviene arreglarlo **antes o en paralelo**, porque un cliente que se
muere a los 12 s no llega a terminar un login.

```
py herramientas\probar_libre.py --exe _trabajo\juego\EDA_limpio.exe --segundos 30 --seguir
```

Hoy alcanza tres sitios desviados **sin resolver**: **`0x5CE2C7`**, **`0x5CE347`** y **`0x77A347`**.
Quedan 200 sin resolver en total, pero sólo esos tres se tocan.

**La receta que funcionó siete veces seguidas** (ver `documentacion/APIS_A_MANO.md`):

1. correr `probar_libre.py` sin `--seguir`: imprime **los argumentos de verdad** del sitio (con el
   texto que apuntan) y **en qué DLL** cayó la excepción;
2. `leer_exe.py dis <VA-0x20> 0x50` para ver los `push` — ⚠ **el desensamblado lineal se desalinea**
   porque el `call` desviado mide 5 bytes y el original 6: el byte de relleno rompe el stream.
   Empezar en un límite de instrucción conocido, o buscar el comienzo de la función con el relleno
   de `int3`;
3. `emular_stub.secuencia_de(mem, sitio, E.TOPE_PASOS, tope=12, marcas=True)` → `bytes_de_argumento`
   (si sale entre 0 y 40 y múltiplo de 4, el dato sirve; si sale 124 o 504, la VM no devolvió la
   pila y **no opina**);
4. buscar un **sitio hermano ya resuelto** con el mismo idioma: es la prueba más fuerte que hay
   (así salieron `GetTempPathA`/`GetTempFileNameA` y los `GetModuleFileNameA`);
5. escribir la fila en `documentacion/APIS_A_MANO.md` **con la prueba**, y después
   `juntar_apis.py` → `desempacar.py construir` → `sin_gameguard.py limpio` → probar de nuevo.

Y si el crash **no** cae en una trampa (`0xD0000000+algo`) sino dentro de una DLL, mirar si es
**código robado**: `_trabajo/robados_resueltos.json` tiene los 22 sitios donde la VM vuelve a más
de +6, con qué registro quedó con el valor de la API. La regla, que costó aprender:
**antes de reponer, mirar si el hueco ya desensambla en la instrucción que la medición describe; si
ya está, no se toca** (`documentacion/CODIGO_ROBADO.md`).

---

## 6 · Lo que vendrá después, anotado para no perderlo

- 🟡 **El cifrado.** El cliente, al arrancar, **verifica firmas RSA de 512 bits sobre hashes MD5** y
  **deriva una clave RC4 de un hash MD5**. Es muy probable que el tráfico del Broker vaya con RC4.
  Cuando tengamos los primeros bytes: si no se parecen a nada, probar RC4.
- 🟡 **`Data.dat`.** Dentro hay XML sin comprimir en memoria: además del `<SERVER>`, se vieron
  `<MAP PATH="...">`, `<SCRIPT PATH="...">`, `MISSION="1011"`, `BRIEFING=`, `EXP="128"`,
  `RANKRAT...`, `CLEAR...`. Con `buscar_en_memoria.py` se pueden ir sacando de a uno sin entender
  el formato del paquete. Es la base de contenido del juego.
- 🟡 **`EdaENGTest.ini`** (332 B) es un contenedor firmado: datos cifrados + el nombre
  `EdaENGTest.ini` en claro en `+0xE5` + **64 bytes** (= una firma RSA-512) + un trailer
  `0f 00 00 00 40 00 00 00 21 26 81 32` (15 = el largo del nombre, 64 = el de la firma). Quien lo
  lee empuja la cadena `EdaENGTest` desde `0x87DED1`. **No** contiene la IP del Broker (probado
  sacándolo: el juego conecta al mismo lugar igual).
- 🟡 **`-cmdfile`**: el launcher le pasaba datos al juego por un archivo. El parser está en
  `0x40A2C1` (compara los tokens con `0x7E35B9`). Para el login va a hacer falta fabricarlo.
- 🟡 **`GameGuard.des`** sigue en la carpeta sin usarse. Si alguna vez hace falta que GameGuard
  arranque de verdad, la línea de comando con la que el juego lo lanza está cifrada y se puede
  leer con `ventanas.py` (anota la línea de comando de cada proceso nuevo).

---

## 7 · Las herramientas que hay para esto

| herramienta | para qué, en esta tarea |
|---|---|
| `conexiones.py` | a qué IP:puerto va el juego y qué UDP abre. **Sin driver ni UAC.** ⚠ Deja medido que la caché de DNS de esta máquina está **vacía** (`Get-DnsClientCache` = 0): para ver **nombres** hace falta `mirar_dns.py` |
| `buscar_en_memoria.py` | buscar bytes en el proceso vivo y ver qué hay alrededor. Es como se encontró la IP. ⚠ Su control corre contra **otro** proceso a propósito |
| `ventanas.py` | qué ventanas abre y **qué procesos nuevos lanza**, con su línea de comando |
| `probar_libre.py` | hasta dónde llega, los argumentos de verdad en la trampa, y en qué DLL cayó |
| `sin_gameguard.py` | las copias parchadas (`limpio` es la buena) |
| `mirar_dns.py` | los nombres por DNS (WinDivert, se eleva) |
| `proxy_mitm.py` de R2Beat | el mecanismo de redirección con WinDivert, ya resuelto (§3a) |
