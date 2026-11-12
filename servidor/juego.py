r"""servidor/juego.py -- la ENTRADA del server de juego: a quién le toca cada mensaje.

Para cada mensaje del cliente, `responder(comando, cuerpo, conexion)` busca la función registrada
(`servidor/registro.py`) y devuelve lo que ella diga:
    · una lista de (comando, cuerpo, milisegundos de espera[, conexión destino]) → eso se contesta;
    · None → «no sé»: contestan las reglas fijas de `herramientas/reglas_broker.py`.
`tick` (cada segundo) y `cerrada` (se cortó una conexión) completan lo que el server necesita.

Quién atiende qué (los formatos de cada mensaje, en `documentacion/PROTOCOLO.md`):
    entrada.py      0x100F quién soy · 0x1011 elegir personaje
    salas.py        el lobby, las salas, el chat, listo / largar
    inventario.py   0x102B / 0x102D (equipar, repartir estadísticas)
    tienda.py       comprar / vender
    habilidades.py  verificar el libro / aprender / borrar
    refineria.py    engarces, piedras, reparar
    partida.py      cargar, morir y revivir, el final, las cartas, el premio
    pruebas.py      ★ `control()`: todo lo de arriba sin el juego, cada prueba con su revés

    py servidor\juego.py control                     # ★ las pruebas (sin el juego)
    py servidor\juego.py estado                      # muestra las cuentas
    py servidor\juego.py preparar <nombre> <1|2> <nivel>   # una cuenta de prueba
"""
import json
import os
import sys
import time

if __package__ in (None, ""):                              # `py servidor\juego.py …`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servidor import config                                  # noqa: E402
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO, partida   # noqa: E402
from servidor.cuentas import NOMBRES, leer, ruta_cuenta, nivel   # noqa: E402
from servidor.salas import avisar_lista, avisar_usuarios     # noqa: E402
from servidor.partida import cuerpo_1072, game_over          # noqa: E402
from servidor.registro import MANEJADORES                    # noqa: E402
# los módulos que REGISTRAN manejadores (importarlos es lo que los anota)
from servidor import entrada, inventario, tienda, habilidades, refineria   # noqa: E402,F401


def responder(cmd, cuerpo, conexion):
    if cmd < 0x1000:                                        # el Broker: no es de una cuenta
        return None
    # (la cuenta y la partida se piden SIEMPRE, aunque nadie atienda el comando: así la conexión
    #   queda con su cuenta desde el primer mensaje, como antes de partir el server en módulos)
    # ★ con login (config.LOGIN == "pase"), hasta que el 0x100F no trae un ticket válido, nada más
    #   se atiende: ni las reglas fijas (por eso [] y no None)
    if config.LOGIN == "pase" and cmd != 0x100F and conexion not in ASIGNADAS:
        return []
    c = leer(conexion)
    p = partida(conexion)
    f = MANEJADORES.get(cmd)
    return f(cmd, cuerpo, conexion, c, p) if f else None


def tick(conexiones):
    """Cada segundo (lo llama el espía): lo que el server tiene que decir por TIEMPO."""
    r = []
    forzar = os.path.join(config.ESTADO, "forzar_lista")   # (para probar a mano)
    if os.path.exists(forzar):
        os.remove(forzar)
        VIVO.LISTA_CAMBIO = True
    if getattr(VIVO, "LISTA_CAMBIO", False):
        VIVO.LISTA_CAMBIO = False
        r += avisar_lista() + avisar_usuarios()
    for n in conexiones:
        p = PARTIDAS.get(n)
        if p and p.get("game_over_en") and time.time() >= p["game_over_en"]:
            r += game_over(leer(n), p, n)
        # ★ vencido el tiempo de las cartas sin elegir (p. ej. con 0 puntos no se puede elegir
        #   ninguna: medido 19:22, el reloj llega a 0 y la pantalla se queda) → AWARD RESULTS
        if p and p.get("cartas_hasta") and time.time() >= p["cartas_hasta"]:
            p["cartas_hasta"] = None
            r.append((0x1072, cuerpo_1072(n, p), 0, n))
    return r


def cerrada(conexion):
    """El espía avisa que la conexión se cerró: olvidar su partida, su sala y soltar su cuenta.
    (Sin forma de devolver mensajes acá: la lista nueva sale con el próximo `tick`.)"""
    PARTIDAS.pop(conexion, None)
    ASIGNADAS.pop(conexion, None)
    viejas = [k for k, v in SALAS.items() if v["anfitrion"] == conexion]
    for k in viejas:
        del SALAS[k]
    VIVO.LISTA_CAMBIO = True                               # salas y usuarios: uno menos


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    from servidor import pruebas
    if sys.argv[1:2] == ["preparar"]:
        # py servidor\juego.py preparar <nombre> <1 Warrior | 2 Hunter> <nivel>
        cc = pruebas.preparar(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print("%s: clase %d, nivel %d, %d ítems, %d habilidades (atajos %s)" % (
            cc["nombre"], cc["clase"], nivel(cc["exp"]), len(cc["items"]), len(cc["habilidades"]),
            [h[2] for h in cc["habilidades"] if h[4]]))
    elif sys.argv[1:2] == ["estado"]:
        for nombre in NOMBRES:
            if os.path.exists(ruta_cuenta(nombre)) or nombre == "rui":
                print(json.dumps(dict(leer(None) if nombre == "rui" else
                                      json.load(open(ruta_cuenta(nombre), encoding="utf-8"))),
                                 indent=1, ensure_ascii=False))
    else:
        sys.exit(pruebas.control())
