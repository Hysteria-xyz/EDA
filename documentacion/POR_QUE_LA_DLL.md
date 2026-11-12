# Por qué los arreglos van en la DLL (y no en el exe ni en otros archivos)

> Dos partes. La **1** es para cualquiera que juegue o quiera ayudar: en criollo, sin código.
> La **2** es para quien revisa o arma un PR (una persona o un agente): las reglas, dónde va cada
> cosa y cómo se prueba. Cada dato lleva su fuente en `documentacion/MEDICIONES.md` (§ = sección).

---

## PARTE 1 · En criollo

### La idea en una línea

El juego de 2009 queda **como está**. Al lado del juego va un archivo nuestro, **`d3d9.dll`**, que
Windows carga antes que el suyo. Esa dll le pasa todo al Windows de verdad y, en el camino, arregla
lo que haga falta. Todos los arreglos van ahí, en **un solo archivo**, y cada uno se puede prender
o apagar desde un texto: `eda_d3d9.ini`.

### ¿Por qué no arreglar el exe directamente, como se hacía antes?

1. **Cada cambio al exe cambia la "llave" del server.** El juego cifra lo que le manda al server con
   una llave que sale del propio exe (es su "huella"). Si se toca un solo byte del exe, la huella
   cambia, la llave cambia, y el server ya no lo entiende hasta que alguien le enseñe la llave
   nueva. Con diez parches de diez personas serían diez exes distintos, cada uno con su llave.
   La dll no toca el exe: la huella queda siempre igual.
2. **Un exe parchado no se puede revisar.** En un PR, un exe cambiado es "un archivo binario
   distinto". Nadie puede leer qué cambió ni si cambió algo más. Un arreglo en la dll es **código
   que se lee**, con su explicación y su prueba.
3. **Un exe parchado no tiene botón de apagado.** Si un arreglo le hace mal a una PC, con el exe
   hay que volver a bajar todo. Con la dll alcanza con cambiar un `1` por un `0` en el `.ini`.
4. **Los parches de varios se pisan.** Dos personas parchando el mismo exe es como dos personas
   escribiendo encima de la misma hoja. En la dll cada uno tiene su **bloque** (`[rui]`,
   `[hysteria]`, `[mazino]`…), separado del de los demás.
5. **Los otros archivos del juego tampoco conviene tocarlos.** `Data.dat` pesa 345 MB y es de
   Softnyx: un parche ahí obliga a repartir de nuevo un archivo gigante . El cliente original no se toca nunca.

### Lo que la dll ya arregla de Windows moderno

EDA se hizo para las PCs de 2009. En una de hoy pasan cosas que entonces no pasaban:

| lo que pasaba | por qué | lo que hace la dll | § |
|---|---|---|---|
| **La placa de video al máximo**, ruido y calor, aunque estés en un menú | el juego no tiene tope de cuadros: dibuja ~900 por segundo | un tope (120 por defecto; el launcher lo cambia) | 41–42 |
| **Dos juegos en la misma PC a 14 cuadros/s** | cada dibujo frenaba a la placa hasta que terminaba | el "anillo" (apagado por defecto: es lo más delicado) | 42–43 |
| **El ping de la sala dependía de los cuadros** | el juego miraba la red una vez por cuadro | la "red inmediata": atiende el mensaje apenas llega | 42 |
| **El server de Corea ya no existe** | el juego busca una dirección de 2009 | la dll lo manda a nuestro server | 44 |
| **Jugadores de la misma casa no se encontraban** (−1000 ms) | si la PC tiene VMware, VirtualBox, Hyper-V o una VPN, el juego daba la dirección de esa red falsa | da la dirección de la red de verdad (cable o WiFi, la que uses) | 52 |
| **El juego no sabía quién eras para el P2P** | se perdía la identidad (ver abajo, "la fuga") | la vuelve a poner en su lugar | 52 |
| **Se te cerró el juego y no sabías por qué** | el juego de 2009 no avisa dónde se cae | la "caja negra": anota en `eda_d3d9.log` si fue nuestra dll, el juego o el driver | 48 |

(Hubo **un** arreglo que sí fue al exe: en Windows en español el juego moría al arrancar. No era un
error del juego de 2009, sino de **nuestro desempacado**: le faltaba una pieza (`GetCPInfo`) que en
la PC de pruebas (con Windows en coreano) nunca se usaba. Lo encontró un colaborador (PR #1) y se rearmó el exe con
las herramientas del proyecto, §37. Lo que es del juego va a la dll; lo que es del desempacado, al
armado del exe.)

### La fuga: anduvo en las pruebas y falló con el launcher

Esto pasó de verdad y es el mejor ejemplo de por qué la dll:

- El launcher le pasa al juego tu usuario y un **ticket** de 20 letras. El juego copia ese ticket en
  un lugar donde entran **justo 20 letras, sin lugar para el final**. Entonces la copia **se sigue
  derramando** sobre lo que está al lado, que es tu **identidad P2P** (la que usan los juegos para
  encontrarse), y la pisa (§52).
- En las pruebas de casa se usó un ticket de 9 letras: entraba holgado y todo anduvo (§45).
- En la **primera prueba de verdad con el launcher** (tickets de 20), los juegos llegaron al server
  **sin identidad**: ping −1000 en la sala, todo por el relay, y en esa misma prueba al anfitrión se
  le cortó el juego a los 6 segundos de largar la partida (§47). (Que ese corte venga del ticket no
  está probado; lo que sí se midió es que la identidad no llegaba.)
- **Cómo se arregló:** el launcher exige 20 letras, así que no se podía achicar el ticket. Arreglarlo
  en el exe habría cambiado su huella, y con ella la llave del server, y habría que repartir un exe
  nuevo. Se arregló en la **dll**: deja que el juego haga su copia y, apenas termina, le devuelve la
  identidad a su lugar. Resultado medido: dos PCs de la misma casa a **33 ms** directo, sin pasar por
  el server (§52). Y entre casas, por datos móviles, **70–90 ms** (§53).

### Así funciona también R2Beat

R2Beat (el otro juego del grupo) trabaja igual desde septiembre: un `d3d9.dll` propio al lado del juego,
que le da suavizado, alt+enter y le escribe **en memoria** los parches del motor al arrancar. Su
documentación lo dice así: la subida de esas mejoras **no cambió ni un byte del exe del juego**. El
launcher reparte la dll como un archivo más. EDA copió esa receta, incluso el compilador (Zig).

### Si sos jugador: lo único que tenés que saber

- La dll y su `.ini` vienen con el launcher. **El `.ini` es tuyo**: el launcher no te lo pisa.
- Si el juego se te cae, mandá **`eda_d3d9.log`** (y `EDA_limpio.rpt` / `.dmp` si están). Están al
  lado del exe.
- Para saber si la culpa es de la dll: en `eda_d3d9.ini`, `[general] mejoras=0`. Si así no se cae,
  es una de las mejoras, y se prenden de a una hasta encontrarla.

---

## PARTE 2 · Para el agente (o quien revise PRs)

### Dónde va cada cambio

| el cambio | va en | cómo se prueba |
|---|---|---|
| Lo que contesta el server (mensajes, cuentas, salas, tienda…) | `servidor/` (un módulo por pantalla, `@maneja(cmd)`) | `py servidor\juego.py control` → «TODO BIEN», cada prueba **con su revés** |
| Lo que el **juego** hace mal en una PC de hoy (video, red, línea de comandos, bytes del código) | `herramientas/dll_d3d9/eda_d3d9.c`, en el **bloque de su autor** del `.ini` | `compilar.py --poner` + el juego + su línea en `eda_d3d9.log` |
| Una llamada que el **desempacado** dejó sin resolver (la "trampa" `0xD0…` que nombra la caja negra) | el armado del exe: `herramientas/` + `documentacion/APIS_A_MANO.md` / `CODIGO_ROBADO.md`. El exe se **rearma acá**; nunca se acepta un binario de un PR | §37 (el caso de `GetCPInfo`) |
| `Data.dat`, gráficos, sonido, el cliente original | **nada** | — |

### Por qué no se acepta un exe (ni bytes del exe) parchado en un PR

- **La llave del Broker es `MD5(exe + 0x00)`** (`documentacion/PROTOCOLO.md`; LEEME.md §3). Un exe
  distinto necesita su llave en el server (`EDA_CLAVES`) y una release nueva del cliente.
- Un binario no se puede revisar ni revertir por partes; varios parches al mismo exe se mezclan.
- El exe que se reparte (`exe/EDA_limpio.exe`, md5 en `documentacion/`) se arma con las
  herramientas del repo, así se sabe exactamente qué tiene.

**Si un PR trae un parche de bytes** (como el de las letras de la PR #6, `0x770A64`): se traduce a un
**parche en memoria desde la dll**, con su clave y **verificando antes los bytes originales**. Si no
coinciden, no se toca y se anota en el log.

### Las reglas de la dll (de `herramientas/dll_d3d9/LEEME.md` § «Para la próxima PR»)

1. **Cada mejora en el bloque de su autor**, con su clave, y el bloque **APAGADO** hasta que esté
   medida en más de una PC. `[general] mejoras=0` también la apaga.
2. **Si cambia lo que hace una clave que ya existe, se cambia su NOMBRE.** El `.ini` es del jugador
   (el launcher no lo pisa): con el mismo nombre arrastraría el valor viejo.
3. **Que anote en `eda_d3d9.log`** qué hizo, o por qué no lo hizo.
4. **Nada pesado en `DllMain`.** Por ejemplo, un nombre de server se resuelve en el primer `connect`.
5. La fila en la tabla del `LEEME.md` de la dll, y la medición en `MEDICIONES.md`.
6. Probar la caída a propósito: `EDA_PROBAR_CAJA=1` → «★ ES EN NUESTRA DLL». Sin la variable, no se
   cae (el revés).

### Las cuatro formas de meterse en el juego (las que ya usa la dll; copiar el patrón)

| forma | ejemplo en `eda_d3d9.c` | cuidado |
|---|---|---|
| **Tabla de importaciones** del exe: cambiar a quién llama | `connect` (§44), `WSAEventSelect` (§42), `gethostbyname` (§52) | sólo `EDA_limpio.exe`: en el `EDA.exe` original las importaciones las arma ASProtect y no se ven (§44) |
| **Funciones del dispositivo** Direct3D | `Present` / `Reset` / `CreateVertexBuffer` (§42) | el juego crea **otro** dispositivo al entrar a la partida: cada uno con lo suyo (§42) |
| **Desviar UNA llamada** del exe (`E8 rel32`) | `0x4E767B` → `mi_cuenta_linea`, después de `0x6229F0` (la fuga, §52) | verificar que el `E8` apunte a la función esperada antes de reescribirlo |
| **Bytes del código en memoria** | `letras_32` en `0x770A64` (§49) | verificar los bytes originales; si no coinciden, nada |

⛔ Medido y descartado: **llamar al bombeo de red del juego (`0x74D530`) desde el `Present`**. Los
dos juegos se congelaron (§42).

### Cómo revisar un PR que toca la dll

- [ ] ¿Está en el bloque de su autor, con clave propia y apagada por defecto (salvo lo mínimo)?
- [ ] ¿`mejoras=0` la apaga?
- [ ] ¿Escribe en el log qué hizo? ¿Verifica los bytes antes de un parche en memoria?
- [ ] ¿Se midió en el juego, con **A/B** (prendida / apagada) y su número? (§49: un negativo con teclas
      inyectadas resultó falso; las habilidades se prueban con las manos)
- [ ] `py herramientas\dll_d3d9\compilar.py` compila sin avisos nuevos, y el `INI` por defecto de
      `compilar.py` tiene la clave nueva con su comentario.
- [ ] Una dll nueva **llega a los jugadores sólo con una release del cliente** (el manifiesto del
      launcher): el PR no basta. Avisarle al mantenedor.

### Los bloques de hoy (`eda_d3d9.ini`, ver `compilar.py`)

`[red]` el server · `[video]` tope y contador (las escribe el launcher) · `[general] mejoras` ·
`[cajanegra]` · `[p2p]` identidad, IP privada y red inmediata (prendidos: §52–53) · `[rui]` ·
`[hysteria]` · `[mazino]`.
