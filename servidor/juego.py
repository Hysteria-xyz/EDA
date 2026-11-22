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
from servidor.salas import avisar_lista, avisar_usuarios, _sacar_de_sala, reanunciar     # noqa: E402
from servidor.partida import (cerrar_por_bajas, cuerpo_1072, fin_de_stage, game_over,    # noqa: E402
                              vigilar_cargas, vigilar_master)
from servidor.registro import MANEJADORES                    # noqa: E402
from servidor.relay import escribir_relay                    # noqa: E402
# los módulos que REGISTRAN manejadores (importarlos es lo que los anota)
from servidor import entrada, inventario, tienda, habilidades, refineria, personajes   # noqa: E402,F401
from servidor import nat                                     # noqa: E402
from servidor import messenger                               # noqa: E402
from servidor import salida                                  # noqa: E402
from servidor import CANDADO as _CANDADO                     # noqa: E402


def responder(cmd, cuerpo, conexion):
    """★ (20-nov) de a uno: ver `servidor.CANDADO`."""
    with _CANDADO:
        return _responder(cmd, cuerpo, conexion)


def _responder(cmd, cuerpo, conexion):
    if cmd == 0x070A:                                       # ★ la lista de servidores, con los jugadores reales
        return [(0x070B, entrada.lista_servidores(), 0)]
    if cmd == 0x0604 and nat.prendido():                    # ★ P2P entre casas: que se presente al relay (§53)
        return nat.al_conectar(cuerpo, conexion)
    if cmd == 0x060C:                                       # ★ NAT bloqueado: reconfirmar Broker IP/Puerto
        return nat.nat_bloqueado(cuerpo, conexion)
    if cmd in (0x3002, 0x3003):                             # ★ NAT Type sort
        return nat.nat_tipo_sort(cuerpo, conexion)
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
    ahora = time.time()
    p.setdefault("desde", ahora)                             # (21-nov) el comienzo de ESTA sesión (red.py ya lo pone)
    p["ultimo_mensaje"] = ahora                              # (22-nov) para detectar un máster colgado en plena stage
    f = MANEJADORES.get(cmd)
    antes = ASIGNADAS.get(conexion)
    r = f(cmd, cuerpo, conexion, c, p) if f else None
    if cmd == 0x100F and ASIGNADAS.get(conexion) and ASIGNADAS.get(conexion) != antes:
        # (21-nov, sólo registro) qué conexión es qué cuenta: para cruzar las pruebas entre casas
        print("#%s es la cuenta %s" % (conexion, ASIGNADAS[conexion]), flush=True)
    if cmd in CAMBIAN_SALAS:
        escribir_relay()                                    # ★ el relay sabe quién está con quién (§47)
    return r


# crear, entrar, salir, echar, abandonar la stage, fallo de ping UDP: se reescribe el mapa del relay
CAMBIAN_SALAS = (0x101D, 0x101F, 0x1045, 0x1051, 0x105A, 0x1074)   # (0x1074: sale de la sala, Punto 3)


def segundos_fin_rapido():
    """🧪 ATAJO DE PRUEBA (apagado si no existe el archivo): con <EDA_ESTADO>/fin_rapido la stage
    termina sola a los N segundos de cargar (N = el número dentro; vacío = 10) → resultado →
    REWARD CHOICE, sin jugarla entera. Con `puntos_extra` da puntos para las cartas."""
    ruta = os.path.join(config.ESTADO, "fin_rapido")
    if not os.path.exists(ruta):
        return None
    try:
        v = float(open(ruta, encoding="utf-8").read().strip() or 10)
    except (OSError, ValueError):
        v = 10.0
    return v if v > 0 else None                         # con 0 adentro: apagado


def tick(conexiones):
    """Cada segundo (lo llama el espía): lo que el server tiene que decir por TIEMPO."""
    with _CANDADO:
        return _tick(conexiones)


def _tick(conexiones):
    r = nat.tick(conexiones)                                # los 0x0609 pendientes (P2P entre casas, §53)
    r += messenger.tick()                                   # «X se desconectó» a sus amigos
    forzar = os.path.join(config.ESTADO, "forzar_lista")   # (para probar a mano)
    if os.path.exists(forzar):
        os.remove(forzar)
        VIVO.LISTA_CAMBIO = True
    avisos, VIVO.AVISOS_SALA = getattr(VIVO, "AVISOS_SALA", []), []
    r += [x for x in avisos if x[3] in conexiones]          # (el «se fue» de los desconectados, ver `cerrada`)
    if getattr(VIVO, "LISTA_CAMBIO", False):
        VIVO.LISTA_CAMBIO = False
        r += avisar_lista() + avisar_usuarios()
    r += [x for x in vigilar_cargas(SALAS) if x[3] in conexiones]   # (20-nov: nadie queda cargando para siempre)
    r += [x for x in vigilar_master(SALAS) if x[3] in conexiones]   # (22-nov: máster colgado → traspaso; stage trabada → cierre)
    r += [x for x in reanunciar(SALAS) if x[3] in conexiones]      # (21-nov: una dirección que cambió, otra vez)
    for n in conexiones:
        p = PARTIDAS.get(n)
        if p and p.get("game_over_en") and time.time() >= p["game_over_en"]:
            r += game_over(leer(n), p, n)
        if p:                                               # el cierre por bajas, al segundo
            r += [x if len(x) > 3 else x + (n,) for x in cerrar_por_bajas(p, n)]
        espera = segundos_fin_rapido() if p and p.get("inicio") else None
        if (espera is not None and not p.get("resultado_guardado") and not p.get("game_over_en")
                and time.time() - p["inicio"] >= espera):
            print("🧪 fin_rapido: la stage %s termina a los %g s (atajo de prueba)"
                  % (p.get("escenario"), espera), flush=True)
            r += [x if len(x) > 3 else x + (n,) for x in fin_de_stage(0x1064, b"", n, leer(n), p)]
        # ★ vencido el tiempo de las cartas sin elegir (p. ej. con 0 puntos no se puede elegir
        #   ninguna: medido 19:22, el reloj llega a 0 y la pantalla se queda) → AWARD RESULTS
        if p and p.get("cartas_hasta") and time.time() >= p["cartas_hasta"]:
            p["cartas_hasta"] = None
            r.append((0x1072, cuerpo_1072(n, p), 0, n))
    return r


def ordenar_salida(n, resp):
    """★ (21-nov) lo que sale, en orden, sin cortar la carga de la stage (servidor/salida.py)"""
    with _CANDADO:
        return salida.ordenar(n, resp)


def cerrada(conexion):
    with _CANDADO:
        _cerrada(conexion)


def _cerrada(conexion):
    """El espía avisa que la conexión se cerró: olvidar su partida, su sala y soltar su cuenta.
    (Sin forma de devolver mensajes acá: la lista nueva sale con el próximo `tick`.)"""
    nombre = ASIGNADAS.pop(conexion, None)
    if nombre:                                              # el aviso a sus amigos, con el tick
        messenger.al_salir(nombre)
    # ★ (Punto 3) los que quedan en la sala se ENTERAN (0x1058 tipo 3, con el nuevo anfitrión), con el
    #   próximo tick. Antes se lo sacaba sólo en el server: el cliente de los demás lo seguía teniendo en
    #   la lista, «no listo», y el anfitrión —solo de verdad— no podía largar (cartel 0x191)
    for k in list(SALAS.keys()):
        if conexion in SALAS[k]["miembros"]:
            VIVO.AVISOS_SALA = getattr(VIVO, "AVISOS_SALA", []) + _sacar_de_sala(SALAS[k], k, conexion)
    PARTIDAS.pop(conexion, None)
    escribir_relay()
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
