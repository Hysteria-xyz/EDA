r"""servidor/messenger.py -- el MESSENGER por chat: amigos, dónde están y mensajes privados.

★ Medido en el exe (13-nov): en el lobby los botones 3, 4 y 5 de la barra (Clan, Messenger, Options)
NO tienen función asociada (`0x4DF900` sólo une 1 Shop, 2 Inventory, 6 Select Character, 7 Exit) y
ninguno de los 85 mensajes C→S del cliente es de amigos o clan: en la beta de 2009 esas pantallas no
estaban. El chat SÍ anda (0x100D → 0x1005), así que el messenger va por comandos:

    /amigos              la lista, con quién está conectado y dónde (lobby, sala, stage)
    /amigo <nick>        agregar (y al otro le llega el aviso, si está conectado)
    /quitar <nick>       quitar
    /m <nick> <mensaje>  mensaje privado (también /w, /mp, /susurro)
    /messenger           los amigos y la ayuda (el botón Messenger del lobby)
    /clan, /opciones     los botones Clan y Options del lobby (ver herramientas/eda_original.py)

Un aviso = 0x1005 con TIPO 3 (una línea en el chat, medido: en verde con «[Messenger]»); el tipo 4
abre una ventana con Confirm (medido), mejor para los comandos GM que para cada conexión.
Los amigos se guardan en el personaje activo (`amigos`: nombres de CUENTA).
"""
import json
import os
import struct

from servidor.cuentas import NOMBRES, leer, guardar, nombre_visible, ruta_cuenta
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO

COMANDOS = ("amigos", "amigo", "agregar", "quitar", "borrar", "m", "w", "mp", "susurro", "messenger", "clan",
            "opciones")


def aviso(texto, destino, tipo=3):
    b = texto.encode("utf-16-le")
    nom = "[Messenger]".encode("utf-16-le")[:24].ljust(26, b"\0")
    return (0x1005, struct.pack("<HBII", 0, tipo, 0xFF00FF00, 0) + nom + struct.pack("<I", len(b)) + b,
            0, destino)


def _nick_guardado(nombre):
    try:
        crudo = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
    except (OSError, ValueError):
        return nombre
    pjs = crudo.get("pjs") or [crudo]
    activo = min(crudo.get("activo", 0), len(pjs) - 1) if pjs else 0
    return (pjs[activo].get("nick") if pjs else None) or crudo.get("nick") or nombre


def buscar(texto):
    """(nombre de la cuenta, conexión o None) del jugador con ese nick o nombre, o (None, None)."""
    t = texto.lower()
    for n, nombre in list(ASIGNADAS.items()):
        if t in (nombre.lower(), nombre_visible(leer(n)).lower()):
            return nombre, n
    for nombre in NOMBRES:
        if t in (nombre.lower(), _nick_guardado(nombre).lower()) and os.path.exists(ruta_cuenta(nombre)):
            return nombre, None
    return None, None


def conexion_de(nombre):
    return next((n for n, x in ASIGNADAS.items() if x == nombre), None)


def donde_esta(n):
    p = PARTIDAS.get(n) or {}
    s = SALAS.get(p.get("sala"))
    if s and n in s.get("miembros", []):
        if p.get("inicio") and not p.get("resultado_guardado"):
            return "jugando la stage %s" % p.get("escenario")
        return "en la sala %s" % p.get("sala")
    return "en el lobby"


def avisar_amigos(nombre, texto):
    """`texto` a los conectados que tienen a `nombre` entre sus amigos."""
    return [aviso(texto, n) for n, otro in list(ASIGNADAS.items())
            if otro != nombre and nombre in leer(n).get("amigos", [])]


def comando(texto, conexion, c):
    """Lo que contesta un comando del messenger, o None si `texto` no es uno."""
    partes = texto[1:].split(None, 2)
    sub = partes[0].lower() if partes else ""
    if sub not in COMANDOS:
        return None
    yo = nombre_visible(c)
    if sub == "amigos":
        amigos = c.get("amigos", [])
        if not amigos:
            return [aviso("No tienes amigos agregados. Usa /amigo <nick>.", conexion)]
        lineas = []
        for a in amigos:
            n = conexion_de(a)
            nick = nombre_visible(leer(n)) if n else _nick_guardado(a)
            lineas.append("%s: %s" % (nick, ("conectado, " + donde_esta(n)) if n else "desconectado"))
        return [aviso("Amigos — " + " | ".join(lineas), conexion)]
    if sub in ("amigo", "agregar"):
        if len(partes) < 2:
            return [aviso("Uso: /amigo <nick>", conexion)]
        otro, n = buscar(partes[1])
        if not otro or otro == c["nombre"]:
            return [aviso("No existe el jugador %s." % partes[1], conexion)]
        amigos = c.setdefault("amigos", [])
        if otro in amigos:
            return [aviso("%s ya es tu amigo." % partes[1], conexion)]
        amigos.append(otro)
        guardar(c)
        r = [aviso("%s agregado a tus amigos." % partes[1], conexion)]
        if n:
            r.append(aviso("%s te agregó como amigo." % yo, n))
        return r
    if sub in ("quitar", "borrar"):
        otro = buscar(partes[1])[0] if len(partes) >= 2 else None
        if not otro or otro not in c.get("amigos", []):
            return [aviso("Uso: /quitar <nick de un amigo>", conexion)]
        c["amigos"].remove(otro)
        guardar(c)
        return [aviso("%s quitado de tus amigos." % partes[1], conexion)]
    if sub in ("m", "w", "mp", "susurro"):
        if len(partes) < 3:
            return [aviso("Uso: /m <nick> <mensaje>", conexion)]
        n = buscar(partes[1])[1]
        if not n:
            return [aviso("%s no está conectado." % partes[1], conexion)]
        b = partes[2].encode("utf-16-le")

        def privado(nombre, destino):
            nom = nombre.encode("utf-16-le")[:24].ljust(26, b"\0")
            return (0x1005, struct.pack("<HBII", 0, 1, 0xFFFFFFFF, 0) + nom + struct.pack("<I", len(b)) + b,
                    0, destino)
        return [privado("[de %s]" % yo, n), privado("[a %s]" % partes[1], conexion)]
    ayuda = aviso("Messenger: /amigos · /amigo <nick> · /quitar <nick> · /m <nick> <mensaje>", conexion)
    if sub == "clan":                                       # ★ el botón Clan del lobby
        return [aviso("Clan: en la beta de 2009 no existía (el cliente no trae sus pantallas). "
                      "Usa /amigos y /m para tu grupo.", conexion)]
    if sub == "opciones":                                   # ★ el botón Options del lobby
        return [aviso(abrir_opciones(), conexion)]
    return comando("/amigos", conexion, c) + [ayuda]        # ★ el botón Messenger (/messenger)


def abrir_opciones():
    """★ El botón Options: con el server en ESTA PC (jugar.py), abre EDA-Opciones.py (si está al
    lado de la carpeta del repo). En un VPS no hay qué abrir: sólo el aviso."""
    import subprocess
    import sys
    from servidor import config
    ruta = os.path.join(os.path.dirname(config.RAIZ), "EDA-Opciones.py")
    if sys.platform != "win32" or not os.path.exists(ruta):
        return "Opciones: abre EDA-Opciones en tu PC."
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    try:
        subprocess.Popen([py if os.path.exists(py) else sys.executable, ruta], cwd=os.path.dirname(ruta))
    except OSError as error:
        return "Opciones: no se pudo abrir (%s)." % error
    return "Opciones abiertas en otra ventana: se aplican la próxima vez que abras EDA."


def al_salir(nombre):
    """Lo llama `cerrada`: el aviso sale con el próximo tick (cerrada no puede contestar)."""
    VIVO.__dict__.setdefault("SALIDAS", []).append(nombre)


def tick():
    r = []
    for nombre in VIVO.__dict__.pop("SALIDAS", []):
        r += avisar_amigos(nombre, "%s se desconectó." % _nick_guardado(nombre))
    return r
