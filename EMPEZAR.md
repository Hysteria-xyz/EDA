# Empezar de cero (Windows)

Esta guía es para alguien que **nunca programó**: se copian y pegan unos pocos comandos.
Al final vas a tener EDA andando contra tu propia computadora.

---

## Lo que necesitás tener antes

**1. El cliente de EDA de 2009.** Este repositorio no lo trae (no es nuestro). Necesitás la
carpeta donde está `EDA.exe` (junto a `Data.dat`, `LTMsg.dll`, `autoexec.cfg`…). El `EDA.exe` que
conocemos tiene md5 `f0b12e6cddf3efdd0676b6491efe46be`; si el tuyo es otro, puede que no ande.

**2. Python.** Bajalo de [python.org/downloads](https://www.python.org/downloads/) e instalalo.

> ⚠ Cuando el instalador te pregunte, **marcá la casilla "Add Python to PATH"**. Si no la marcás,
> los comandos de abajo no van a andar.

**3. Este repositorio.** Arriba en GitHub: botón verde **Code → Download ZIP**, y descomprimilo
donde quieras (por ejemplo `C:\EDA-servidor`).

---

## Paso 0 — Abrir una consola en la carpeta correcta

Abrí la carpeta de este proyecto en el Explorador. Hacé clic en la barra de dirección de arriba,
escribí `cmd` y apretá Enter. Se abre una ventana negra: ahí van los comandos.

Para comprobar que Python quedó bien:

```bat
py --version
```

Tiene que responder algo como `Python 3.12.1`.

## Paso 1 — Instalar lo que usa el server

```bat
py -m pip install -r requirements.txt
```

Instala **Frida** (para abrir el juego y ajustarlo en memoria) y **pycryptodome** (el cifrado de
la red del juego). Se hace una sola vez.

## Paso 2 — Preparar el juego (una sola vez)

```bat
py jugar.py --preparar "C:\Juegos\EDA"
```

(cambiá `C:\Juegos\EDA` por la carpeta donde está tu `EDA.exe`).

Copia el juego a `_trabajo\juego\` dentro de esta carpeta y lo pone en modo ventana. **Tu carpeta
original no se toca**: el juego crea archivos al correr (logs, la carpeta de GameGuard) y por eso se
juega siempre desde la copia.

## Paso 3 — Jugar

```bat
py jugar.py
```

Eso levanta el server y abre el juego. La primera vez:

1. Aparece el **NOTICE** y la lista de servidores con **«EDA Local [Open]»**: elegilo y **ENTER**.
2. **SELECT CHARACTER**: el server ya te da un personaje (un Warrior llamado **rui**; si abrís
   varios juegos a la vez, el segundo es **kai**, el tercero **mio**…). Hacé clic en él y
   **Enter Lobby**.
3. Desde el lobby: **Create Stage** → **doble clic** en el marcador de la stage → un título → la
   sala → **F9 Start Game**.

Los precios de la tienda, las habilidades y los premios salen de las tablas del juego que trae el
repo ([datos/](datos/LEEME.md)).

Cuando cerrás el juego, el server se apaga solo. Tu cuenta (nivel, oro, ítems) queda guardada en
`_trabajo\servidor\cuentas\`.

### Los controles

W A S D para moverse, clic para pegar, Espacio para saltar, **F** cambia de arma, **1–6** las
pociones de la barra derecha, **ESC** para salir de la stage.

---

## Si algo sale mal

- **«no se puede conectar al servidor»** → el server no arrancó. Mirá `_trabajo\server.txt` y
  `_trabajo\broker\espia.log`. Si otro programa usa el puerto 25900, cerralo.
- **«Game guard error : …»** (por ejemplo 45) → el juego se abrió **sin** `jugar.py` (doble
  clic en el exe, o el launcher de Softnyx), o con `--original` en una PC donde GameGuard ganó la
  carrera. Abrilo siempre con `py jugar.py` (usa `exe\EDA_limpio.exe`, que ya no trae GameGuard:
  ver [exe/LEEME.md](exe/LEEME.md)). La consola dice qué exe abrió («· exe: …»). Si igual
  falla, abrí un issue con una foto del mensaje y lo que dice la consola.
- **«GameGuard: no se pudieron poner todos los parches»** (en la consola) → tu `EDA.exe` no es el
  de 2009 que conocemos (comparalo con el md5 de arriba): usá `py jugar.py` sin `--original`.
- **El antivirus se queja de Frida** → Frida es una herramienta conocida de análisis que se mete en
  otros programas; es lo que permite no modificar el exe. Si no querés usarla, este proyecto no
  tiene otra forma de abrir el juego original.

## Jugar en un server (con otros)

Si alguien tiene el server andando en un VPS ([despliegue/LEEME.md](despliegue/LEEME.md)), en
vez del Paso 3:

```bat
py jugar.py --server IP_DEL_SERVER:25900
```

(`:35900` es el server de prueba, con lo último). El multijugador entre PCs pasa por un *relay*
UDP del server ([documentacion/PROTOCOLO.md](documentacion/PROTOCOLO.md) §5.16, MEDICIONES §30–31 y
§38).

### ★ Sin Python (lo que va a usar el launcher)

Para jugar en un server de otra PC no hace falta Python: alcanza con la carpeta del juego,
`EDA_limpio.exe` y nuestra `d3d9.dll` (las dos están en `exe\`) al lado, y en `eda_d3d9.ini`:

```ini
[red]
server=IP_DEL_SERVER:25900
```

Después, doble clic en `EDA_limpio.exe`. La dll lleva al juego a ese server (el de Corea de 2009 ya
no existe); si algo falla, `eda_d3d9.log` dice qué pasó (MEDICIONES §44).

En una misma PC, varios juegos a la vez: ver [LEEME.md](LEEME.md) (`herramientas\multi.py`).
