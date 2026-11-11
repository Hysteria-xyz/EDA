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
