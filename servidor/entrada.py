r"""servidor/entrada.py -- la ENTRADA al server de juego: «quién soy» (0x100F) y la cuenta
con su personaje (0x1011 → 0x1012).
"""
import re
import struct

from servidor import config
from servidor.registro import maneja
from servidor.objetos import cuerpo_cuenta
from servidor.relay import escribir_relay, relay


@maneja(0x100F)
def quien_soy(cmd, cuerpo, conexion, c, p):
    """«quién soy» [§5.1]"""
    if not (len(cuerpo) >= 0xE9):
        return None
    # ★ cerca del final viaja su UDP (medido con dos clientes, 17:02): +0xDD u32 IP privada
    #   (192.168.1.10 como entero 0xC0A8010A) · +0xE1 u16 PUERTO PRIVADO (57654 / 51001: cada
    #   cliente el suyo) · +0xE3 u32 IP pública · +0xE7 u16 puerto público (el que le dijo el
    #   0x0609). En esta máquina los dos se hablan por 127.0.0.1 con su puerto privado.
    #   ⚠ (antes +0xDE/+0xE2: corrido en 1 → puerto «481» = E1 01, medido 17:40)
    p["udp"] = (0x7F000001, struct.unpack_from("<H", cuerpo, 0xE1)[0])
    # ★ la dirección PRIVADA tal cual (IP como entero, como la quiere el 0x1059): para los que
    #   comparten IP pública (el mismo cíber, la misma casa)
    p["privada"] = struct.unpack_from("<IH", cuerpo, 0xDD)
    # ★★ la MAC = la IDENTIDAD P2P (cuenta+0x166, `0x6229F0`), en el cuerpo +0x7A (MEDICIONES §39).
    #   Llega bien si el juego se lanzó con la ruta entre comillas; si no, es basura y no se usa
    mac = cuerpo[0x7A:0x7A + 34].decode("utf-16-le", "replace")
    p["mac"] = mac if re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", mac) else None
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
