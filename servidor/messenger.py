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
import time

from servidor import config
from servidor.cuentas import leer, guardar, nivel, nombre_visible, ruta_cuenta
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO

COMANDOS = ("amigos", "amigo", "agregar", "quitar", "borrar", "m", "w", "mp", "susurro", "messenger", "clan",
            "opciones", "msn", "aceptar", "rechazar")

# ★ (17-nov, PUNTO 2) AMISTAD CON ACEPTACIÓN. Se sigue guardando lo mismo que antes (`amigos` del personaje activo,
#   nombres de CUENTA), sin migrar ni borrar nada: «A es amigo de B» = cada uno está en la lista del otro; si sólo
#   A tiene a B, eso ES la solicitud de A a B (pendiente, queda guardada aunque B esté desconectado). Así las
#   amistades de un solo lado que ya existían se ven como solicitudes enviadas, y basta con que el otro acepte.
#     ADD (/amigo X)  → la solicitud (o, si X ya me la había mandado, la amistad)
#     /aceptar X      → X pasa a mi lista: amigos los dos
#     /rechazar X     → se saca mi nombre de la lista de X (la solicitud desaparece)
#     DELETE (/quitar X) → fuera de las DOS listas (también cancela una solicitud enviada)


def aviso(texto, destino, tipo=3, nombre="[Messenger]"):
    """(`nombre` = el remitente que se ve; el panel del Coordinador manda los suyos como «[Aviso]», servidor/panel.py)"""
    b = texto.encode("utf-16-le")
    nom = nombre.encode("utf-16-le")[:24].ljust(26, b"\0")
    return (0x1005, struct.pack("<HBII", 0, tipo, 0xFF00FF00, 0) + nom + struct.pack("<I", len(b)) + b,
            0, destino)


# ★ (16-nov) EL MESSENGER DE LA DLL (d3d9.dll, Punto 2): la ventana la dibuja la dll en la PC del jugador (local y
#   multijugador, sin Python). Los datos le llegan por el MISMO chat (0x1005) con el nombre «[MSN]»: la dll los toma
#   y el juego no los muestra. Sólo los recibe una conexión que lo pidió con «/msn abrir» (un cliente sin la dll
#   nunca lo pide: para él nada cambia). Las acciones son los comandos de siempre (/amigo, /quitar, /m).
#     L\t<yo>\t<nick>\t<nivel>\t<clase>\t<dónde>        y por amigo   A\t<cuenta>\t<nick>\t<nivel>\t<clase>\t<1|0>\t<dónde>
#     H\t<de>\t<a>\t<hora>\t<texto>                      un mensaje nuevo (cuentas); h = los últimos 30, al abrir
MSN_AMIGOS_MAX = 20


def dato_msn(texto, destino):
    b = texto[:1800].encode("utf-16-le")
    nom = "[MSN]".encode("utf-16-le").ljust(26, b"\0")
    return (0x1005, struct.pack("<HBII", 0, 3, 0xFF00FF00, 0) + nom + struct.pack("<I", len(b)) + b, 0, destino)


def _limpio(x):
    return str(x).replace("\t", " ").replace("\n", " ")


def lista_msn(cuentas, yo):
    """El texto L/A/R/E de la cuenta `yo` (con el estado() de todas): A = amigos (de los dos lados), R = solicitudes
    recibidas, E = solicitudes enviadas pendientes. (Una dll vieja sólo lee L y A.)"""
    d = cuentas.get(yo, {})
    lineas = ["L\t%s\t%s\t%s\t%s\t%s" % (yo, _limpio(d.get("nick", yo)), d.get("nivel", 0), d.get("clase", 1),
                                            _limpio(d.get("donde", "")))]
    mios = d.get("amigos", [])
    mutuos = [a for a in mios if yo in cuentas.get(a, {}).get("amigos", [])]
    for a in [a for a in mios if a not in mutuos][:MSN_AMIGOS_MAX]:
        lineas.append("E\t%s\t%s" % (a, _limpio(cuentas.get(a, {}).get("nick", a))))
    for a, x in cuentas.items():
        if a != yo and yo in x.get("amigos", []) and a not in mios:
            lineas.append("R\t%s\t%s" % (a, _limpio(x.get("nick", a))))
    for a in mutuos[:MSN_AMIGOS_MAX]:
        x = cuentas.get(a, {})
        lineas.append("A\t%s\t%s\t%s\t%s\t%d\t%s" % (a, _limpio(x.get("nick", a)), x.get("nivel", 0), x.get("clase", 1),
                                                       1 if x.get("conectado") else 0, _limpio(x.get("donde", ""))))
    return "\n".join(lineas)


def msn_dll():
    """{conexión: último texto L mandado} de los que abrieron el Messenger de la dll."""
    return VIVO.__dict__.setdefault("MSN_DLL", {})


# ★ (17-nov, PUNTO 2) LAS CONVERSACIONES DURAN SÓLO LA SESIÓN. Antes cada /m quedaba para siempre en
#   messenger_chat.jsonl y al abrir el Messenger volvían las de sesiones anteriores. Ahora viven en la memoria del
#   server: cada mensaje lo «ven» sus dos jugadores (`para`); cuando uno se desconecta deja de verlo (al_salir), y el
#   mensaje se borra cuando ya no lo ve nadie. Así una sesión nueva empieza sin historial, y el otro (si sigue
#   jugando) conserva la conversación hasta que él también se vaya. A un desconectado no se le guarda nada.
#   messenger_chat.jsonl NO se borra ni se toca (queda como estaba); la lista de amigos sigue en la cuenta.
MSN_SESION_MAX = 300                                        # (en memoria, todos los jugadores juntos)


def mensajes_sesion():
    return VIVO.__dict__.setdefault("MSN_SESION", [])


def olvidar_sesion(nombre):
    """`nombre` se desconectó: deja de ver sus mensajes; los que ya no ve nadie, fuera."""
    todos = mensajes_sesion()
    for m in todos:
        m["para"].discard(nombre)
    todos[:] = [m for m in todos if m["para"]]


def historia_msn(yo, cuantos=30):
    """Los mensajes de ESTA sesión de `yo` (los que todavía ve), como líneas «h»."""
    mios = [m for m in mensajes_sesion() if yo in m["para"]][-cuantos:]
    return ["h\t%s\t%s\t%s\t%s" % (m.get("de"), m.get("a"), m.get("hora", ""), _limpio(m.get("texto", "")))
            for m in mios]                                  # (h = de la historia: la dll no lo cuenta como nuevo)


def amigos_de(nombre):
    """La lista guardada de `nombre` (conectado o no)."""
    c = _cuenta_por_nombre(nombre)
    return list(c.get("amigos", [])) if c else []


def son_amigos(a, b):
    return b in amigos_de(a) and a in amigos_de(b)


def cambiar_amigos(nombre, quitar=None, poner=None):
    """Saca / agrega `quitar` / `poner` en la lista de `nombre`, esté conectado o no (sin tocar nada más)."""
    from servidor.cuentas import escribir
    n = conexion_de(nombre)
    if n is not None:
        c = leer(n)
        lista = c.setdefault("amigos", [])
    else:
        try:
            crudo = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
        except (OSError, ValueError):
            return False
        pjs = crudo.get("pjs")
        destino = pjs[min(crudo.get("activo", 0), len(pjs) - 1)] if pjs else crudo
        if "amigos" not in destino:                         # (como _cuenta_por_nombre: la de la cuenta vieja)
            destino["amigos"] = list(crudo.get("amigos", []))
        lista = destino["amigos"]
    if quitar in lista:
        lista.remove(quitar)
    if poner and poner not in lista:
        lista.append(poner)
    if n is not None:
        guardar(c)
    else:
        escribir(nombre, crudo)
    return True


def listas_ya(*nombres):
    """La lista nueva, ya, a los Messenger de la dll de esas cuentas (no esperar al tick)."""
    activos = msn_dll()
    cuentas = estado()["cuentas"]
    r = []
    for n in list(activos):
        if ASIGNADAS.get(n) in nombres:
            activos[n] = lista_msn(cuentas, ASIGNADAS[n])
            r.append(dato_msn(activos[n], n))
    return r


def msn_abrir(conexion, c):
    """«/msn abrir»: la lista (siempre) y, la primera vez de esta conexión, los últimos mensajes."""
    activos = msn_dll()
    primera = conexion not in activos
    texto = lista_msn(estado()["cuentas"], c["nombre"])
    activos[conexion] = texto
    r = [dato_msn(texto, conexion)]
    if primera:
        r += [dato_msn(h, conexion) for h in historia_msn(c["nombre"])]
    return r


def _nick_guardado(nombre):
    try:
        crudo = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
    except (OSError, ValueError):
        return nombre
    pjs = crudo.get("pjs") or [crudo]
    activo = min(crudo.get("activo", 0), len(pjs) - 1) if pjs else 0
    return (pjs[activo].get("nick") if pjs else None) or crudo.get("nick") or nombre


# ★ (18-nov, PUNTO 2) LAS CUENTAS DE VERDAD. Antes el Messenger sólo conocía las 4 cuentas del login «abierto»
#   (NOMBRES: rui, kai, mio, ren): con el login «pase» (prod) las cuentas son `r2b_<uid>` y no salían en la lista
#   ni se podían buscar desconectadas. Ahora: TODAS las cuentas que existen (los archivos de config.CUENTAS, más
#   las conectadas). El IDENTIFICADOR es siempre el nombre de la cuenta (lo que guarda `amigos` y lo que manda la
#   dll en /aceptar, /rechazar, /quitar, /m); el nick es sólo para mostrar y para buscar con ADD.
def nombres_de_cuentas():
    """Todas las cuentas (abierto: rui/kai/…; pase: r2b_<uid>), sin las internas (`_…`)."""
    try:
        archivos = os.listdir(config.CUENTAS)
    except OSError:
        archivos = []
    nombres = {f[:-5] for f in archivos if f.endswith(".json") and not f.startswith(("_", "."))}
    nombres = {x for x in nombres if _cuenta_por_nombre(x) is not None}       # (sólo lo que ES una cuenta)
    nombres.update(x for x in ASIGNADAS.values() if x and not x.startswith("_"))
    return sorted(nombres)


def buscar(texto):
    """(nombre de la cuenta, conexión o None) de lo que escribió el jugador, o (None, None). Primero el
    identificador EXACTO (la cuenta: lo que manda la dll), después el nick (único: lo controla el server al
    crear el personaje); si dos nicks coincidieran, no se elige ninguno."""
    t = texto.strip().lower()
    if not t:
        return None, None
    for nombre in nombres_de_cuentas():
        if nombre.lower() == t:
            return nombre, conexion_de(nombre)
    hallados = []
    for nombre in nombres_de_cuentas():
        c = _cuenta_por_nombre(nombre)
        if c is not None and (c.get("nick") or "").lower() == t:
            hallados.append(nombre)
    if len(hallados) == 1:
        return hallados[0], conexion_de(hallados[0])
    return None, None


def conexion_de(nombre):
    return next((n for n, x in ASIGNADAS.items() if x == nombre), None)


def visible(cuenta):
    """★ (18-nov) El nick de una cuenta para los avisos: la dll manda la CUENTA (`r2b_<uid>` con «pase») en
    /aceptar, /rechazar, /quitar y /m, y el aviso la repetía tal cual («r2b_123 y tú ahora son amigos»)."""
    n = conexion_de(cuenta)
    return nombre_visible(leer(n)) if n else _nick_guardado(cuenta)


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
    suyos = amigos_de(nombre)
    return [aviso(texto, n) for n, otro in list(ASIGNADAS.items())
            if otro != nombre and otro in suyos and nombre in leer(n).get("amigos", [])]


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
        suyos = amigos_de(otro)
        quien = visible(otro)
        if otro in amigos and c["nombre"] in suyos:
            return [aviso("%s ya es tu amigo." % quien, conexion)]
        if otro in amigos:
            return [aviso("Ya le enviaste una solicitud a %s (pendiente)." % quien, conexion)]
        amigos.append(otro)
        guardar(c)
        if c["nombre"] in suyos:                            # (el otro ya me la había mandado: amigos los dos)
            r = [aviso("%s y tú ahora son amigos." % quien, conexion)]
            if n:
                r.append(aviso("%s aceptó: ahora son amigos." % yo, n))
        else:
            r = [aviso("Solicitud de amistad enviada a %s." % quien, conexion)]
            if n:
                r.append(aviso("%s te envió una solicitud de amistad (Messenger → Requests)." % yo, n))
        return r + listas_ya(c["nombre"], otro)
    if sub in ("aceptar", "rechazar"):
        otro = buscar(partes[1])[0] if len(partes) >= 2 else None
        if not otro or c["nombre"] not in amigos_de(otro) or otro in c.get("amigos", []):
            return [aviso("No tienes una solicitud de %s." % (partes[1] if len(partes) >= 2 else "nadie"), conexion)]
        n, quien = conexion_de(otro), visible(otro)
        if sub == "aceptar":
            c.setdefault("amigos", []).append(otro)
            guardar(c)
            r = [aviso("%s y tú ahora son amigos." % quien, conexion)]
            if n:
                r.append(aviso("%s aceptó tu solicitud: ahora son amigos." % yo, n))
        else:
            cambiar_amigos(otro, quitar=c["nombre"])
            r = [aviso("Rechazaste la solicitud de %s." % quien, conexion)]
            if n:
                r.append(aviso("%s rechazó tu solicitud de amistad." % yo, n))
        return r + listas_ya(c["nombre"], otro)
    if sub in ("quitar", "borrar"):
        otro = buscar(partes[1])[0] if len(partes) >= 2 else None
        mio = otro in c.get("amigos", [])
        if not otro or not (mio or c["nombre"] in amigos_de(otro)):
            return [aviso("Uso: /quitar <nick de un amigo>", conexion)]
        era_amigo = mio and c["nombre"] in amigos_de(otro)
        if mio:
            c["amigos"].remove(otro)
            guardar(c)
        cambiar_amigos(otro, quitar=c["nombre"])            # (la amistad, de los DOS lados)
        n = conexion_de(otro)
        r = [aviso(("%s quitado de tus amigos." if era_amigo else "Solicitud con %s cancelada.") % visible(otro),
                   conexion)]
        if n and era_amigo:
            r.append(aviso("%s te quitó de sus amigos." % yo, n))
        return r + listas_ya(c["nombre"], otro)
    if sub in ("m", "w", "mp", "susurro"):
        if len(partes) < 3:
            return [aviso("Uso: /m <nick> <mensaje>", conexion)]
        otro, n = buscar(partes[1])
        al_msn = []
        if not n:                                           # ★ (17-nov) a un desconectado no se le guarda nada
            if otro and otro != c["nombre"]:
                return [aviso("%s no está conectado: el mensaje no se envió (las conversaciones duran sólo la sesión)."
                              % visible(otro), conexion)]
            return [aviso("%s no está conectado." % partes[1], conexion)]
        # ★ (17-nov) entre AMIGOS (de los dos lados) el mensaje es del Messenger: en memoria (la sesión) y como H a
        #   cada lado que tiene la dll; a ese lado NO va además al chat del juego (antes llegaba dos veces). Entre
        #   no amigos, o a un cliente sin la dll, el mensaje privado del chat de siempre (compatibilidad).
        dll = msn_dll()
        if otro and otro != c["nombre"] and son_amigos(c["nombre"], otro):
            registrar_mensaje(c["nombre"], otro, partes[2])  # ★ la conversación del Messenger (F11), en memoria
            h = "H\t%s\t%s\t%s\t%s" % (c["nombre"], otro, time.strftime("%H:%M"), _limpio(partes[2]))
            al_msn = [dato_msn(h, x) for x in (conexion, n) if x is not None and x in dll]
        b = partes[2].encode("utf-16-le")

        def privado(nombre, destino):
            nom = nombre.encode("utf-16-le")[:24].ljust(26, b"\0")
            return (0x1005, struct.pack("<HBII", 0, 1, 0xFFFFFFFF, 0) + nom + struct.pack("<I", len(b)) + b,
                    0, destino)
        r = list(al_msn)
        if not al_msn or n not in dll:
            r.append(privado("[de %s]" % yo, n))
        if not al_msn or conexion not in dll:
            r.append(privado("[a %s]" % (visible(otro) if otro else partes[1]), conexion))
        return r
    if sub == "msn":                                        # ★ el Messenger de la dll (no lo escribe una persona)
        # «hola»: la dll avisa al entrar al lobby que está (así los mensajes y las solicitudes le llegan aunque el
        #   Messenger no se haya abierto todavía); «abrir»: al abrir la ventana. Las dos: la lista (y la historia).
        return msn_abrir(conexion, c) if len(partes) >= 2 and partes[1].lower() in ("abrir", "hola") else []
    ayuda = aviso("Messenger: /amigos · /amigo <nick> · /quitar <nick> · /m <nick> <mensaje>", conexion)
    if sub == "clan":                                       # ★ el botón Clan del lobby
        return [aviso("Clan: en la beta de 2009 no existía (el cliente no trae sus pantallas). "
                      "Usa /amigos y /m para tu grupo.", conexion)]
    if sub == "opciones":                                   # ★ el botón Options del lobby
        return [aviso(abrir_opciones(), conexion)]
    hecho = abrir_panel(c["nombre"])                        # ★ el botón Messenger: el PANEL (EDA-Messenger.py)
    if hecho == "cerrado":
        return [aviso("Messenger cerrado.", conexion)]
    if hecho:
        return [aviso("Messenger abierto (al lado del juego). F11 lo abre y lo cierra.", conexion)]
    return comando("/amigos", conexion, c) + [ayuda]        # (sin panel: los amigos y la ayuda)


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
    return "Opciones abiertas en otra ventana: se aplican al instante."


# ★ EL PANEL DEL MESSENGER (EDA-Messenger.py, una ventana aparte al estilo del juego: el cliente de 2009
#   no trae pantalla de messenger). Server y panel corren en esta PC y hablan por dos archivos: el
#   server escribe el ESTADO (cada cuenta: nick, nivel, clase, conectado, dónde, amigos) y el panel
#   deja PEDIDOS (agregar, quitar, mensaje) que el server atiende en el tick. Probado en el juego el
#   13-nov: ADD, SEND (a un desconectado: el aviso) y DELETE.
def ruta_estado():
    return os.path.join(config.ESTADO, "messenger_estado.json")


def ruta_pedidos():
    return os.path.join(config.ESTADO, "messenger_pedidos.jsonl")


def ruta_chat():
    return os.path.join(config.ESTADO, "messenger_chat.jsonl")


def ruta_inventario(nombre):
    return os.path.join(config.ESTADO, "inventario_%s.json" % nombre)


def registrar_mensaje(de, a, texto):
    """★ (17-nov) Cada mensaje privado queda EN MEMORIA, sólo para la sesión (ver mensajes_sesion)."""
    todos = mensajes_sesion()
    todos.append({"de": de, "a": a, "texto": texto, "hora": time.strftime("%H:%M"), "para": {de, a}})
    del todos[:-MSN_SESION_MAX]


def estado_inventario(c):
    """El oro y cada ítem (serial, tipo, cantidad, casillero, precio de venta) de una cuenta."""
    from servidor.datos import precios_venta
    from servidor.objetos import inventario
    precios = precios_venta()
    return {"plata": c["plata"], "items": [
        {"serial": it[3], "tipo": it[0], "cant": it[1], "cas": it[2], "precio": precios.get(it[0])}
        for it in inventario(c)]}


def escribir_inventarios():
    """inventario_<cuenta>.json de cada conectado, sólo si cambió."""
    ult = VIVO.__dict__.setdefault("INV_ULTIMO", {})
    for n, nombre in list(ASIGNADAS.items()):
        texto = json.dumps(estado_inventario(leer(n)), sort_keys=True)
        if ult.get(nombre) != texto:
            ult[nombre] = texto
            os.makedirs(config.ESTADO, exist_ok=True)
            with open(ruta_inventario(nombre) + ".tmp", "w", encoding="utf-8") as f:
                f.write(texto)
            os.replace(ruta_inventario(nombre) + ".tmp", ruta_inventario(nombre))


def vender_varios(n, seriales, vender=True):
    """★ VENTA / ELIMINACIÓN EN GRUPO: cada ítem como el 0x1041 (lo PUESTO, casilleros < 12, no se
    toca) y al cliente un 0x1042 por ítem — el mismo que contesta a «Sell», sin que él lo pida."""
    from servidor.datos import precios_venta
    from servidor.objetos import inventario
    c = leer(n)
    inv = inventario(c)
    precios = precios_venta()
    r, cuantos, oro = [], 0, 0
    for serial in seriales:
        it = next((x for x in inv if x[3] == serial), None)
        if it is None or it[2] < 12:
            continue
        precio = precios.get(it[0]) if vender else 0
        if vender and precio is None:
            continue
        inv.remove(it)
        c["plata"] += precio
        oro += precio
        cuantos += 1
        r.append((0x1042, struct.pack("<HIIB", 1, serial, c["plata"], 1 if it[0] <= 19999 else 0), 0, n))
    if cuantos:
        c["items"] = inv
        guardar(c)
    texto = ("Vendidos %d ítems: +%d de oro." % (cuantos, oro)) if vender else ("Eliminados %d ítems." % cuantos)
    return r + [aviso(texto if cuantos else "Nada que %s." % ("vender" if vender else "eliminar"), n)]


def proceso_vivo(archivo_pid):
    """¿Sigue corriendo el proceso cuyo pid está en `archivo_pid`? (Windows)"""
    try:
        pid = int(open(archivo_pid).read().strip())
    except (OSError, ValueError):
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        codigo = ctypes.c_ulong(0)
        k32.GetExitCodeProcess(h, ctypes.byref(codigo))
        k32.CloseHandle(h)
        return codigo.value == 259                          # STILL_ACTIVE
    except Exception:                                       # noqa: BLE001
        return False


def abrir_atajos():
    """EDA-Atajos.py (F10 Options, F11 Messenger, F12 Clan; al lado de la carpeta del repo) si no está
    corriendo, o si cambió desde que se abrió."""
    import subprocess
    import sys
    # ★ (15-nov) con la d3d9.dll nueva, F10/F11/F12 los hace la dll (lee el teclado de DirectInput del juego). Si
    #   además corría EDA-Atajos.py, F10 abría DOS Options (la de la dll, en vivo, y la de Python, que pide reabrir).
    if os.environ.get("EDA_ATAJOS") == "1":
        return False
    ruta = os.path.join(os.path.dirname(config.RAIZ), "EDA-Atajos.py")
    pid = os.path.join(config.ESTADO, "atajos.pid")
    if sys.platform != "win32" or not os.path.exists(ruta):
        return False
    if proceso_vivo(pid) and os.path.getmtime(ruta) <= os.path.getmtime(pid):
        return False
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    try:
        subprocess.Popen([py if os.path.exists(py) else sys.executable, ruta], cwd=os.path.dirname(ruta),
                         close_fds=True)
    except OSError:
        return False
    return True


def _cuenta_por_nombre(nombre):
    """La cuenta `nombre` (conectada o no), como `leer`; None si no existe."""
    n = conexion_de(nombre)
    if n is not None:
        return leer(n)
    # (desconectada: del archivo, y sólo se vuelve a leer si cambió — el tick pide la lista de todas)
    ruta = ruta_cuenta(nombre)
    try:
        cuando = os.stat(ruta).st_mtime_ns
    except OSError:
        return None
    guardadas = VIVO.__dict__.setdefault("MSN_GUARDADAS", {})
    if nombre in guardadas and guardadas[nombre][0] == cuando:
        return guardadas[nombre][1]
    try:
        crudo = json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(crudo, dict) or not ("pjs" in crudo or "nombre" in crudo):
        return None                                         # (otro .json que no es una cuenta)
    pjs = crudo.get("pjs") or [crudo]
    pj = pjs[min(crudo.get("activo", 0), len(pjs) - 1)] if pjs else {}
    c = dict(pj, nombre=nombre, amigos=list(pj.get("amigos", crudo.get("amigos", []))))
    guardadas[nombre] = (cuando, c)
    return c


def estado():
    cuentas = {}
    for nombre in nombres_de_cuentas():
        c = _cuenta_por_nombre(nombre)
        if c is None:
            continue
        n = conexion_de(nombre)
        cuentas[nombre] = {"nick": c.get("nick") or nombre, "nivel": nivel(c.get("exp", 0)) if c.get("exp") is not None
                           else 0, "clase": c.get("clase", 1), "conectado": n is not None,
                           "donde": donde_esta(n) if n is not None else "", "amigos": list(c.get("amigos", []))}
    return {"cuentas": cuentas}


def escribir_estado(forzar=False):
    """Escribe el estado del panel sólo si cambió (o con `forzar`). True si lo escribió."""
    texto = json.dumps(estado(), ensure_ascii=False, sort_keys=True)
    if not forzar and getattr(VIVO, "MSN_ULTIMO", None) == texto:
        return False
    VIVO.MSN_ULTIMO = texto
    os.makedirs(os.path.dirname(ruta_estado()), exist_ok=True)
    temporal = ruta_estado() + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(temporal, ruta_estado())
    return True


def atender_pedidos():
    """Los pedidos del panel: {"de": cuenta, "accion": "amigo"|"quitar"|"mensaje", "nick", "texto"}."""
    ruta = ruta_pedidos()
    if not os.path.exists(ruta):
        return []
    tomado = ruta + ".tomado"
    try:
        os.replace(ruta, tomado)
        lineas = open(tomado, encoding="utf-8").read().splitlines()
    finally:
        if os.path.exists(tomado):
            os.remove(tomado)
    r = []
    for linea in lineas:
        try:
            ped = json.loads(linea)
        except ValueError:
            continue
        nombre = str(ped.get("de", ""))
        n = conexion_de(nombre)
        if n is None:                                       # (el panel es del que está jugando)
            continue
        accion = ped.get("accion")
        if accion in ("vender", "eliminar"):
            seriales = [int(x) for x in ped.get("seriales", []) if str(x).isdigit()]
            r += vender_varios(n, seriales, accion == "vender")
            continue
        if accion == "salir":                               # (destrabar un cliente que pidió salir)
            r.append((0x1030, struct.pack("<H", 1), 0, n))
            continue
        if accion == "aviso":                               # (F12 de EDA-Atajos: el aviso del Clan)
            r.append(aviso(str(ped.get("texto", ""))[:200], n))
            continue
        nick = str(ped.get("nick", "")).strip()
        texto = {"amigo": "/amigo %s" % nick, "quitar": "/quitar %s" % nick,
                 "mensaje": "/m %s %s" % (nick, str(ped.get("texto", "")).strip())}.get(ped.get("accion"))
        if texto:
            r += comando(texto, n, leer(n)) or []
    return r


def abrir_panel(nombre):
    """Abre EDA-Messenger.py (al lado de la carpeta del repo) para la cuenta `nombre`. Un panel viejo
    lo cierra el nuevo (messenger_panel.pid)."""
    import subprocess
    import sys
    ruta = os.path.join(os.path.dirname(config.RAIZ), "EDA-Messenger.py")
    if sys.platform != "win32" or not os.path.exists(ruta):
        return False
    pid = os.path.join(config.ESTADO, "messenger_panel.pid")
    if proceso_vivo(pid):                                   # ★ 14-nov: el botón abre Y cierra
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x0001, False, int(open(pid).read().strip()))
            if h:
                k32.TerminateProcess(h, 0)
                k32.CloseHandle(h)
                return "cerrado"
        except (OSError, ValueError):
            pass
    escribir_estado(forzar=True)
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    try:
        subprocess.Popen([py if os.path.exists(py) else sys.executable, ruta, "--cuenta", nombre],
                         cwd=os.path.dirname(ruta), close_fds=True)
    except OSError:
        return False
    return True


def al_salir(nombre):
    """Lo llama `cerrada`: el aviso sale con el próximo tick (cerrada no puede contestar). Su sesión terminó:
    sus conversaciones dejan de estar para él."""
    VIVO.__dict__.setdefault("SALIDAS", []).append(nombre)
    olvidar_sesion(nombre)


def tick_msn():
    """A cada Messenger de la dll abierto alguna vez: la lista, sólo si cambió (amigos que entran, salen, se mueven)."""
    activos = msn_dll()
    for n in [x for x in activos if x not in ASIGNADAS]:
        del activos[n]
    if not activos:
        return []
    cuentas = estado()["cuentas"]
    r = []
    for n in list(activos):
        texto = lista_msn(cuentas, ASIGNADAS[n])
        if texto != activos[n]:
            activos[n] = texto
            r.append(dato_msn(texto, n))
    return r


def tick():
    r = []
    for nombre in VIVO.__dict__.pop("SALIDAS", []):
        r += avisar_amigos(nombre, "%s se desconectó." % _nick_guardado(nombre))
    r += tick_msn()
    r += atender_pedidos()                                  # lo que pidió el panel
    escribir_estado()                                       # y lo que el panel muestra
    escribir_inventarios()
    if ASIGNADAS and time.time() - VIVO.__dict__.get("ATAJOS_VISTO", 0) > 10:
        VIVO.ATAJOS_VISTO = time.time()
        abrir_atajos()                                      # (F10 / F11 / F12, si está al lado)
    return r
