# herramientas/dll_d3d9 — el `d3d9.dll` propio de EDA

Va **al lado del juego** (`jugar.py` la pone sola en `_trabajo\juego\`). Windows la carga en lugar del
d3d9 del sistema; ella reenvía todo al de verdad y arregla cuatro cosas del juego de 2009, **sin
tocar un byte del exe**:

| qué | por qué | medido |
|---|---|---|
| **tope de cuadros** (`tope_fps`, `tope_estricto`) | EDA no trae tope: dibuja ~900 cuadros/s y pone cualquier placa a máxima potencia | MEDICIONES §41 |
| **búferes rápidos** (`buferes_rapidos`) | en cada dibujo bloqueaba su búfer de vértices ENTERO sin flags (~290 veces por cuadro): la placa paraba cada vez; con dos juegos caían a 14 cuadros/s y 164 W | §42: 120 cuadros/s y 46 W |
| **red inmediata** (`red_inmediata`) | el juego lee la red una vez por cuadro: el ping dependía de los cuadros | §42: ping de sala 1 ms a 60 cuadros/s |
| **contador** (`mostrar_fps`) | «FPS 60» arriba a la izquierda | — |
| ★ **el server** (`[red] server=host[:puerto]`, o `EDA_SERVER`) | el cliente busca el Broker de Corea de 2009 (`218.145.66.187:25000`, muerto): la dll lo manda a nuestro server. **Con esto el juego se juega SIN Python**: carpeta + doble clic. Vacío = no desvía | §44: lista → SELECT CHARACTER del VPS, sin Frida; sin server, «Can't connect» |
| ★ **el login del launcher** | el launcher abre `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]` en texto plano; la dll arma el bloque que el juego espera (hex de XOR con la MAC, PROTOCOLO §5.1) y se lo da por `GetCommandLineA`. Y si el juego se abrió sin comillas, le muestra la línea con comillas (si no, pisaba la MAC) | §45: entra como `r2b_<uid>`; con un ticket inventado, «Can't Connect» |
| **trampas** | una llamada sin resolver del desempacado anota su sitio en `eda_d3d9.log` (para mandarlo en un issue) | §44 |

Ajustes: `eda_d3d9.ini` al lado del juego. Registro: `eda_d3d9.log`.

```bat
py herramientas\dll_d3d9\compilar.py            :: compila (Zig 0.16, la receta de R2Beat) → _trabajo\dll\
py herramientas\dll_d3d9\compilar.py --poner    :: y la pone al lado del juego
py herramientas\dll_d3d9\compilar.py --sacar    :: la saca (el juego vuelve al d3d9 de Windows)
py jugar.py --sin-dll                           :: jugar sin ella
```

Para diagnosticar Direct3D se puede usar **DXVK** (su panel en pantalla: cuadros, dibujos, uso de la
placa) en lugar de esta dll; ver MEDICIONES §41. DXVK pide Vulkan, que muchas PCs modestas no
tienen: por eso la solución es esta dll, que anda con cualquier D3D9.
