# herramientas/dll_d3d9 — el `d3d9.dll` propio de EDA

Va **al lado del juego**: la ponen `jugar.py` (en `_trabajo\juego\`) y el launcher, como parte del
cliente. Windows la carga en lugar del d3d9 del sistema; ella le pasa todo al de verdad y agrega lo
de abajo **sin tocar un byte del exe**. Se maneja entera con **`eda_d3d9.ini`**, un archivo de texto al
lado del juego. Es del jugador: el launcher no lo pisa. Lo que pasa queda en **`eda_d3d9.log`**.

## El `.ini` por BLOQUES (12-nov)

`eda_d3d9.ini` está partido en bloques separados por `#####`, y cada bloque se prende o se apaga solo.
**Por defecto: LO MÍNIMO (tope de cuadros + server) y la caja negra.** El resto, apagado.

| bloque | qué | clave | por defecto | riesgo | medido |
|---|---|---|---|---|---|
| **LO MÍNIMO** | ★ **el server**: el cliente busca el Broker de Corea de 2009 (`218.145.66.187:25000`, muerto) y la dll lo manda al nuestro | `[red] server=` (o el 3er argumento del launcher) | lo pone el launcher | bajo: un solo `connect` | §44 |
| | ★ **el login**: `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]` → el bloque que el juego espera (PROTOCOLO §5.1); y las comillas si faltan | (sólo si vienen esos argumentos) | — | bajo | §45 |
| | **tope de cuadros**: EDA no trae; dibuja ~900 cuadros/s y la placa va al máximo | `[video] tope_fps` (el launcher la escribe) | **120** | bajo: un `Sleep` en el Present | §41 |
| | **contador** «FPS» arriba a la izquierda | `[video] mostrar_fps` (el launcher la escribe) | 0 | medio: dibuja en cada cuadro | — |
| | (todo lo de arriba menos el server y el login) | `[general] mejoras=0` | 1 | — | §48 |
| **CAJA NEGRA** | si el juego se cae, dice DÓNDE: ver abajo | `[cajanegra] activo` | **1** | nulo: sólo mira | §48 |
| **P2P** (que los juegos se encuentren) | | `[p2p] activo` | **1** | | |
| | la identidad (MAC): el ticket de 20 del launcher la pisaba (`0x6229F0`, desviada en `0x4E767B`) | `[p2p] mac` | 1 | bajo: una llamada, verificada | §52 |
| | la IP de la casa = la de la red de verdad (no VMware / VirtualBox / Hyper-V / VPN) | `[p2p] ip_privada` | 1 | bajo: `gethostbyname` | §52 |
| | red inmediata (la de `[rui]`, prendida acá) | `[p2p] red_inmediata` | 1 | bajo | §42, §53 |
| **PARCHES DE RUI** (los nuestros) | | `[rui] activo` | **0** | | |
| | tope estricto: los cuadros fijos en todo el juego | `[rui] tope_estricto` | 1 | bajo | §42 |
| | red inmediata: un mensaje que llega mientras se espera el cuadro se atiende enseguida (ping de sala 1 ms a 60 cuadros/s) | `[rui] red_inmediata` | 1 | bajo | §42 |
| | anillo de vértices: los dibujos sin frenar la placa (dos juegos en una PC: sin él, 14 cuadros/s) | `[rui] anillo_vertices` | 0 | **alto**: toca CADA dibujo | §42–43 |
| **PARCHES DE HYSTERIA** (PR #6) | | `[hysteria] activo` | **0** | | |
| | letras completas: si se ven cortadas a la mitad, sus texturas empiezan en 32×32 (`0x770A64`, sólo si están los bytes originales) | `[hysteria] letras_32` | 1 | bajo: 5 bytes verificados | §49 |
| **PARCHES DE MAZINO** (PR #1, #5, #9) | (ninguno en la dll todavía: su arreglo de la región ya está ADENTRO de `EDA_limpio.exe`, §37; lo demás es del server) | `[mazino] activo` | 0 | — | §37 |

⚠ **Las claves viejas** (`[video] tope_estricto`, `red_inmediata`, `anillo_vertices` / `buferes_rapidos`,
`[compat] letras_32`) **ya no se leen**: el `.ini` es del jugador (el launcher no lo pisa) y así nadie
arrastra lo que tenía prendido. Medido: un `.ini` viejo con todo prendido carga sólo el tope y el contador.

**Cada valor** se puede pisar con una variable de entorno, para probar sin tocar el `.ini`:
`EDA_MEJORAS`, `EDA_TOPE_FPS`, `EDA_MOSTRAR_FPS`, `EDA_RED_INMEDIATA`, `EDA_TOPE_ESTRICTO`,
`EDA_BUFERES_RAPIDOS` (el anillo), `EDA_LETRAS_32`, `EDA_SERVER`.

## Si a alguien se le cae el juego

1. Que mande **`eda_d3d9.log`**, y si existen, `EDA_limpio.rpt` y `EDA_limpio.dmp` (el informe del
   propio juego). Están al lado del exe.
2. En el log, la **caja negra** dice:
   ```
   ⛔⛔ [cajanegra] EXCEPCION 0xC0000005 en NUESTRA-d3d9+0x25F3 · escribe en 0x00000010 · … · ★ ES EN NUESTRA DLL
      [cajanegra] eax=… ebx=… (los registros)
      [cajanegra] la pila (de la más cercana a la más lejana): d3d9-de-Windows+0x4BB50 · … · exe 0x0054C0D1 · …
   ```
   - **`NUESTRA-d3d9`** = la culpa es nuestra.
   - **`exe 0x…`** = el juego de 2009: se busca esa dirección en el exe.
   - **`d3d9-de-Windows`** o el nombre de otra dll = el driver o Windows.

   Guarda hasta 3 por arranque. Dice «primera oportunidad» porque puede ser una que el juego mismo
   maneja. El log no se pisa al reabrir; pasado 1 MB, el viejo pasa a `eda_d3d9.anterior.log`.
3. **Para separar «culpa de la dll» de «culpa del juego»:** `[general] mejoras=0`. Si con eso no se
   cae, es el tope o uno de los bloques: se prenden de a uno (`[rui]`, `[hysteria]`, `[mazino]`) hasta
   encontrarlo.

## Para la próxima PR (cómo se agrega algo a la dll)

★ Por qué todo va en la dll y no en el exe, y cómo se revisa un PR: `documentacion/POR_QUE_LA_DLL.md`.

- **Una mejora nueva va en el BLOQUE de su autor** (`[rui]`, `[hysteria]`, `[mazino]`, o uno nuevo con el
  nombre de quien la trae), con su clave, y el bloque arranca APAGADO hasta que esté medida en más de
  una PC. Que `mejoras=0` también la apague.
- **Si cambia lo que hace una clave que ya existe, se cambia el NOMBRE de la clave.** El `.ini` de cada
  jugador queda con el valor viejo, y el launcher no lo pisa.
- Que anote en `eda_d3d9.log` qué hizo (o por qué no), y que no haga nada pesado en `DllMain`.
- **Parches al código del exe en memoria** (como el de las letras de la PR #6): sólo con su clave, y
  verificando antes los bytes originales (si no coinciden, no se toca y se anota).
- La fila en la tabla de arriba, y la medición en `documentacion/MEDICIONES.md`.
- Probar la caída a propósito: `EDA_PROBAR_CAJA=1` hace caer a NUESTRA dll en el cuadro 60, y el log
  tiene que decir «★ ES EN NUESTRA DLL». Sin la variable, no se cae (el revés).

```bat
py herramientas\dll_d3d9\compilar.py            :: compila (Zig 0.16, la receta de R2Beat) → _trabajo\dll\ (+ el .ini por defecto)
py herramientas\dll_d3d9\compilar.py --poner    :: y la pone al lado del juego
py herramientas\dll_d3d9\compilar.py --sacar    :: la saca (el juego vuelve al d3d9 de Windows)
py jugar.py --sin-dll                           :: jugar sin ella (⚠ sin ella no hay login ni server: sólo con jugar.py)
```

Para diagnosticar Direct3D se puede usar **DXVK** (su panel en pantalla: cuadros, dibujos, uso de la
placa) en lugar de esta dll; ver MEDICIONES §41. DXVK pide Vulkan, que muchas PCs modestas no tienen:
por eso la solución es esta dll, que anda con cualquier D3D9.
