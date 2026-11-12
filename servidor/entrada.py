r"""servidor/entrada.py -- la ENTRADA al server de juego: «quién soy» (0x100F) y la cuenta
con su personaje (0x1011 → 0x1012).
"""
import re
import struct

from servidor import config
from servidor.estado import ASIGNADAS
from servidor.registro import maneja
from servidor.objetos import cuerpo_cuenta
from servidor.relay import escribir_relay, relay


def lista_servidores():
    """★ 0x070B (la LISTA DE SERVIDORES, PROTOCOLO §4.5) con los JUGADORES DE VERDAD (12-nov, el tester: «para
    mandar el real»). Antes salía fija de las reglas (`reglas_broker.py`: 7 de 500 → siempre [Open]).
    El cliente saca el estado de jugadores / máximo (`0x516DD1`): < 30 % [Open] · < 60 % [Normal] ·
    < lleno [Busy] · [Full]. La IP:puerto es la del Broker de 2009: la dll / jugar.py la desvía igual
    que la primera conexión."""
    from servidor.config import P
    import reglas_broker as R
    return P.cuerpo_servidores([
        P.registro_servidor(config.NOMBRE_SERVER, ip=R.BROKER_IP, puerto=R.BROKER_PUERTO, idx=1, estado=12,
                            usuarios=min(len(ASIGNADAS), 0xFFFF), maximo=config.MAX_JUGADORES)])


# 0x1010 con resultado ≠ 1: el cliente no entra (§5.2: 0x66, 0x899, 0x89A son errores). Medido
#   (MEDICIONES §45): 0x66 y 0x89A → «Can't Connect to server. Refreshing Server list.»; 0x899 → nada
LOGIN_RECHAZADO = 0x66


def dato_launcher(cuerpo, desde):
    """Un dato del bloque del launcher en el 0x100F: UTF-16, hasta 20 caracteres, hasta el primer 0.
    ⚠ Con 20 justos NO viene el 0: lo que sigue es otro campo (medido con un ticket de 20, MEDICIONES §45)."""
    crudo = cuerpo[desde:desde + 40]
    for i in range(0, len(crudo) - 1, 2):
        if crudo[i] == 0 and crudo[i + 1] == 0:
            crudo = crudo[:i]
            break
    return crudo.decode("utf-16-le", "replace")


@maneja(0x100F)
def quien_soy(cmd, cuerpo, conexion, c, p):
    """«quién soy» [§5.1]"""
    if not (len(cuerpo) >= 0xE9):
        # (con login, uno corto no pasa: sin esto contestaban las reglas fijas con un «OK»)
        return [(0x1010, struct.pack("<HIIH", LOGIN_RECHAZADO, 0, 0, 0), 0)] if config.LOGIN == "pase" else None
    # ★ cerca del final viaja su UDP (medido con dos clientes, 17:02): +0xDD u32 IP privada
    #   (192.168.1.10 como entero 0xC0A8010A) · +0xE1 u16 PUERTO PRIVADO (57654 / 51001: cada
    #   cliente el suyo) · +0xE3 u32 IP pública · +0xE7 u16 puerto público (el que le dijo el
    #   0x0609). En esta máquina los dos se hablan por 127.0.0.1 con su puerto privado.
    #   ⚠ (antes +0xDE/+0xE2: corrido en 1 → puerto «481» = E1 01, medido 17:40)
    p["udp"] = (0x7F000001, struct.unpack_from("<H", cuerpo, 0xE1)[0])
    # ★ la dirección PRIVADA tal cual (IP como entero, como la quiere el 0x1059): para los que
    #   comparten IP pública (el mismo cíber, la misma casa)
    p["privada"] = struct.unpack_from("<IH", cuerpo, 0xDD)
    # ★ y la PÚBLICA que le dijimos en el 0x0609 (servidor/nat.py, MEDICIONES §53): con P2P entre casas
    #   es la de verdad (la vio el relay); si no, la 127.0.0.1 de siempre (y `relay.publica_de` no la usa)
    p["publica"] = struct.unpack_from("<IH", cuerpo, 0xE3)
    # ★★ la MAC = la IDENTIDAD P2P (cuenta+0x166, `0x6229F0`), en el cuerpo +0x7A (MEDICIONES §39).
    #   Llega bien si el juego se lanzó con la ruta entre comillas; si no, es basura y no se usa
    mac = cuerpo[0x7A:0x7A + 34].decode("utf-16-le", "replace")
    p["mac"] = mac if re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", mac) else None
    if p["mac"] is None:
        # 🟡 (MEDICIONES §47) en prod, juegos abiertos por el launcher llegaron SIN MAC: se anota lo que
        #   vino en su lugar (el registro del server, en el VPS), para saber por qué
        print("#%s 0x100F sin MAC válida en +0x7A: %s" % (conexion, cuerpo[0x7A:0x7A + 34].hex(" ")), flush=True)
    # ★★ EL LOGIN (servidor/porteria.py, MEDICIONES §45): el bloque del launcher trae «usuario
    #   ticket» → +0x04 y +0x2E del cuerpo (cuenta+0xF0 / +0x11A), UTF-16 hasta el 0 (después hay basura)
    if config.LOGIN == "pase":
        from servidor import porteria
        usuario, ticket = dato_launcher(cuerpo, 0x04), dato_launcher(cuerpo, 0x2E)
        if not (re.fullmatch(r"[0-9]{1,20}", usuario) and porteria.ticket_valido(usuario, ticket)):
            ASIGNADAS.pop(conexion, None)
            return [(0x1010, struct.pack("<HIIH", LOGIN_RECHAZADO, 0, 0, 0), 0)]
        ASIGNADAS[conexion] = "r2b_" + usuario
        # ★ el apodo de R2Beat (claim «nombre» del pase) al personaje que todavía se llama r2b_<uid>
        from servidor.personajes import bautizar
        if bautizar("r2b_" + usuario, porteria.nombre_de(usuario, ticket)):
            print("#%s cuenta r2b_%s: su personaje toma el nombre del pase" % (conexion, usuario), flush=True)
    # ★ 0x1010 (`0x549742`, 12 B): u16 1 · u32 → cuenta+0x2B8 (🟡 id de la cuenta) · u32 IP y
    #   u16 puerto del SERVER UDP DE PUNCH (→ `0x6218F0`, «[Punch UDP IP, PORT]»): con
    #   0.0.0.1:0 nadie se encuentra. La IP va como entero (el cliente le hace htonl).
    escribir_relay()
    return [(0x1010, struct.pack("<HIIH", 1, conexion, *(relay() or (0x7F000001, config.PUNCH_PUERTO))),
             0)]


@maneja(0x1011)
def elegir_personaje(cmd, cuerpo, conexion, c, p):
    """SELECT CHARACTER"""
    return [(0x1012, cuerpo_cuenta(c, conexion), 0)]
