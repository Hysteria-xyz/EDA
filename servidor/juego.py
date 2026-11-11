r"""servidor/juego.py -- el server de juego CON MEMORIA (la cuenta, la EXP, las monedas…).

Lo carga `herramientas/espiar_broker.py` en cada mensaje que llega (y lo RECARGA solo si este
archivo cambió: así el server crece sin reiniciar el espía, que pide UAC). Para cada mensaje,
`responder(comando, cuerpo, conexion)` devuelve:
    · una lista de (comando, cuerpo, milisegundos de espera) → eso se contesta (lista vacía = nada);
    · None → «no sé»: contestan las reglas fijas de `herramientas/reglas_broker.py`.

Los formatos de cada mensaje están en `documentacion/PROTOCOLO.md` (§ entre corchetes abajo).
El estado de la cuenta vive en `_trabajo/servidor/cuenta.json` (se puede borrar: vuelve al inicio).

    py servidor\juego.py control     # ★ prueba responder() sin el juego (con su revés)
    py servidor\juego.py estado      # muestra la cuenta
"""
import json
import os
import re
import struct
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import paquete_broker as P                                   # noqa: E402

CUENTA = os.path.join(RAIZ, "_trabajo", "servidor", "cuenta.json")
INICIO = {"nombre": "rui", "clase": 1, "monedas": 3, "plata": 5678, "cash": 1234, "exp": 0,
          "partidas": 0, "abandonos": 0, "terminadas": [],
          # ★ El set de grado 1 de Warrior (`ITEMTYPELIST`, USECLASS=1): ningún equipo de Warrior
          #   pide menos de nivel 2 (LEVEL_RESTRICT=2) → con nivel 1 dice «Can't equip» con razón.
          #   + el 201 (USECLASS=2, Hunter) como control al revés: NO se tiene que poder equipar
          #   nunca. + consumibles de USECLASS=65535 (todas las clases).
          "items": [[1, 1], [1001, 1], [3001, 1], [4001, 1], [5001, 1], [6001, 1], [7001, 1],
                    [8001, 1], [201, 1], [21001, 5], [26001, 5]]}

# ★ La EXP acumulada para pasar de nivel: `<EXPS>` de `Data\Player.xml` (dentro de Data.dat,
#   volcado con `volcar_inflados.py`). EXPS[n] = la EXP con la que se llega al nivel n+1; cierra
#   con el lobby: «1LV (11/300)». (99 niveles; acá los primeros 30 alcanzan de sobra.)
EXPS = [0, 300, 1060, 2160, 3600, 5500, 8100, 11760, 16960, 24300, 34500, 48400, 66960, 91260,
        122500, 162000, 211200, 271660, 345060, 433200, 538000, 661500, 805860, 973360, 1166400,
        1387500, 1639300, 1924560, 2246160, 2607100]


# ★ De los XML de cada escenario (`Data\Scenario\<dificultad>\Chapter1_N_X.xml`, volcados):
#   <INFO RANK_POINT KILL_POINT TOTALEXP MONSTER_CNT>. Y <RANKRATE S="0.8" A="0.6" B="0.4" C="0.2"
#   D="0.1"/> (el mismo en todos los vistos).
ESCENARIOS = {1011: (29, 120, 128, 56), 1012: (38, 168, 179, 78), 1013: (48, 240, 256, 78),
              1021: (42, 173, 184, 92)}
RANKRATE = (0.8, 0.6, 0.4, 0.2, 0.1)                       # S A B C D
# ★ De un VIDEO de la beta (capturas de el tester, 10-nov): REWARD CHOICE con las cartas a 350 / 150 /
#   50, y un resultado de la 1-1 con los 56 monstruos muertos = 257 puntos, rango S. 🟡 La fórmula
#   de los puntos no se sabe: acá, proporcional a TOTALEXP, calibrada para que 1011 completa = 257.
PRECIOS = (350, 150, 50)
PUNCH_PUERTO = 25001                                         # `herramientas/udp_punch.py`


def puntos_de(totalexp, frac):
    return int(round(totalexp * frac * 257 / 128.0))


def nivel(exp):
    n = 1
    while n < len(EXPS) and exp >= EXPS[n]:
        n += 1
    return n


# ★ MULTIJUGADOR: una cuenta por conexión de juego. Sin launcher ni login (los dos clientes mandan
#   lo mismo en el 0x100F), cada conexión toma el primer nombre libre de la lista. Cada cuenta en
#   `_trabajo/servidor/cuentas/<nombre>.json` (la vieja `cuenta.json` pasa a ser la de «rui»).
CUENTAS = os.path.join(RAIZ, "_trabajo", "servidor", "cuentas")
NOMBRES = ["rui", "kai", "mio", "ren"]


def ruta_cuenta(nombre):
    return os.path.join(CUENTAS, nombre + ".json")


def cuenta_de(conexion):
    """El nombre de la cuenta de esa conexión (le asigna el primero libre si no tiene)."""
    if conexion is None:
        return NOMBRES[0]
    if conexion not in ASIGNADAS:
        usados = set(ASIGNADAS.values())
        ASIGNADAS[conexion] = next((x for x in NOMBRES if x not in usados), NOMBRES[-1])
    return ASIGNADAS[conexion]


def leer(conexion=None):
    nombre = cuenta_de(conexion)
    if nombre == "rui" and not os.path.exists(ruta_cuenta("rui")) and os.path.exists(CUENTA):
        os.makedirs(CUENTAS, exist_ok=True)
        os.replace(CUENTA, ruta_cuenta("rui"))              # la cuenta de antes de las cuentas
    try:
        c = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return dict(INICIO, **dict(c, nombre=nombre))


def guardar(c):
    os.makedirs(CUENTAS, exist_ok=True)
    json.dump(c, open(ruta_cuenta(c["nombre"]), "w", encoding="utf-8"), indent=1)


# lo de cada conexión (una partida): se pierde al cerrar el juego, y está bien. ⚠ Pero NO al
#   recargar este archivo (el espía lo recarga cuando cambia): medido el 10-nov, una recarga a
#   mitad de partida borró el game over pendiente. Vive en un módulo aparte que no se recarga.
_vivo = sys.modules.get("_eda_partidas")
if _vivo is None:
    import types
    _vivo = types.ModuleType("_eda_partidas")
    _vivo.PARTIDAS = {}
    sys.modules["_eda_partidas"] = _vivo
if not hasattr(_vivo, "ASIGNADAS"):
    _vivo.ASIGNADAS = {}                                    # conexión → nombre de la cuenta
if not hasattr(_vivo, "SALAS"):
    _vivo.SALAS = {}                                        # número → {"sala", "anfitrion", "miembros"}
PARTIDAS = _vivo.PARTIDAS
ASIGNADAS = _vivo.ASIGNADAS
SALAS = _vivo.SALAS


def lista_salas():
    """0x101C [§ lobby]: la LISTA DE SALAS (`0x541C50`). En uno o más paquetes: u8 total · u8
    índice, y en el primero u16 N; después N × 79 B. Cada registro = 4 B (vtable, se ignora) + la
    sala desde su +0 hasta +0x31 (vtable · u16 número · título · u32 escenario · 5 B, con el
    máximo de jugadores en +0x2F) + 26 B 🟡 (participantes / estado: a medir)."""
    regs = []
    for num in sorted(SALAS):
        s = SALAS[num]
        sala = bytearray(s["sala"])
        # ⚠ el cliente copia los 79 B ENCIMA de un objeto ya construido (`rep movsd`, 0x541E06):
        #   las dos vtables (+0 y +4) van con los valores que pone su constructor (`0x53E6D0`),
        #   si no, el primer método virtual llamaría a una dirección cero
        struct.pack_into("<I", sala, 0, 0x89A348)
        # ★ medido en el código que dibuja la fila (`0x4F4E21`, `0x4F4EEE`): sala +0x2D = ESTADO
        #   (1 = «Waiting», otro = «Playing»), +0x2E = jugadores DENTRO, +0x2F = máximo («%d/%d»)
        sala[0x2D] = 2 if s.get("jugando") else 1
        sala[0x2E] = len(s["miembros"])
        regs.append(struct.pack("<I", 0x89A350) + bytes(sala[0:0x31]) + bytes(26))
    return struct.pack("<BBH", 1, 0, len(regs)) + b"".join(regs)


def identidad_p2p():
    """🟡 Atajo local (ver `miembro`): la MAC que el juego escribe en la 1ª línea de NetTrace.log."""
    import re
    try:
        with open(os.path.join(RAIZ, "_trabajo", "juego", "NetTrace.log"), "rb") as f:
            for linea in f.read(4096).splitlines():
                mm = re.search(rb"([0-9A-F]{2}(?::[0-9A-F]{2}){5})", linea)
                if mm:
                    return mm.group(1).decode()
    except OSError:
        pass
    return None


# ★★ MODO RELAY (para PCs distintas). El cliente NO le dice al server su identidad P2P (la MAC;
#   en el 0x100F aparece sólo a veces, como resto sucio de un buffer: MEDICIONES §30). Entonces el
#   server INVENTA una por jugador (con forma de MAC, 17 caracteres) y la pone en +0xA de su
#   miembro; como dirección de cada par da un puerto del RELAY (`herramientas/relay_udp.py`), que
#   reenvía cada datagrama cambiando la MAC real del que lo manda por la inventada. De paso
#   atraviesa cualquier NAT (cíber, LAN, simétrica): todo pasa por el server.
#   Se prende con el archivo `_trabajo/servidor/modo_relay` (adentro: la IP del relay; vacío =
#   127.0.0.1). Puertos: el del relay = RELAY_BASE (lo que va en el 0x1010) y RELAY_BASE + 1 +
#   conexión para cada jugador.
RELAY_BANDERA = os.path.join(RAIZ, "_trabajo", "servidor", "modo_relay")
RELAY_MAPA = os.path.join(RAIZ, "_trabajo", "servidor", "relay.json")
RELAY_BASE = 26000


def relay():
    """(IP como entero, puerto) del relay si el modo está prendido; si no, None."""
    if not os.path.exists(RELAY_BANDERA):
        return None
    ip = open(RELAY_BANDERA).read().strip() or "127.0.0.1"
    return struct.unpack(">I", bytes(int(x) for x in ip.split(".")))[0], RELAY_BASE


def identidad_falsa(conexion):
    return "02:00:00:00:%02X:%02X" % ((conexion >> 8) & 0xFF, conexion & 0xFF)


def identidad_de(conexion):
    if relay() and conexion is not None:
        return identidad_falsa(conexion)
    return identidad_p2p()


def dir_udp(conexion):
    """La dirección UDP que el server da de ese jugador: la suya, o su puerto en el relay."""
    r = relay()
    if r and conexion is not None:
        return r[0], RELAY_BASE + 1 + conexion
    return partida(conexion).get("udp") if conexion is not None else None


def escribir_relay():
    """Lo que el relay necesita saber de cada conexión: su identidad inventada."""
    if relay():
        # la identidad inventada y la dirección UDP que el cliente declaró en su 0x100F (para la
        #   misma PC / LAN, de respaldo si su 0x3006 no llega)
        json.dump({str(n): {"falsa": identidad_falsa(n), "udp": partida(n).get("udp")}
                   for n in ASIGNADAS}, open(RELAY_MAPA, "w"))


def miembro(c, indice, completo=False, conexion=None):
    """★ Un MIEMBRO de la sala, armado sobre los constructores del cliente (los bytes se leen
    ENCIMA del objeto: cada vtable va con el valor que pone su constructor):
      0x32C (`0x540980`, el del 0x1020): +0 vt 0x89A3BC · +4 u8 id · +5 u8 número de jugador ·
        +6 vt 0x89A318 (+0x48.. 🟡 ¿IP/puerto?) · +0x54 el PERSONAJE (`0x53F680`: vt 0x89A3AC,
        clase, nombre, nivel, EXP, vt 0x89A378 en +0x24…, hasta +0xA6) · +0xA6 vt 0x89A368 +
        6 u16 · +0xB6 vt 0x89A390 + 18 × 34 B (vt 0x89A38C · u16 · vt 0x89A380 · 24 B) ·
        +0x31E vt 0x89A3B8 · +0x322 u8 estado · +0x323 u8 · +0x324 u32 · +0x328 u32
      0x36F (`0x541230`, el del 0x1057) = lo mismo con vt 0x89A3C0 en +0, y en +0x32C el equipo de
        la partida: vt 0x89A398 + 9 × 7 B (vt 0x89A394 · u16 · u8)."""
    m = bytearray(0x32C)
    struct.pack_into("<I", m, 0, 0x89A3C0 if completo else 0x89A3BC)
    m[4] = m[5] = indice
    struct.pack_into("<I", m, 6, 0x89A318)
    ident = identidad_de(conexion)
    udp = dir_udp(conexion)
    if ident:
        # ★ +0xA (texto ancho, hasta +0x48): la IDENTIDAD P2P del jugador. La capa UDP guarda a
        #   cada par por el texto que él manda en su saludo `0xC354` (su MAC «XX:XX:…»), y el ping
        #   de la sala lo busca con este campo (`0x5374A0` → `0x623070` → `0x748120`): vacío →
        #   -1 → «-1000 ms». 🟡 Atajo LOCAL: los dos clientes en esta PC tienen la misma MAC y se
        #   la lee de la 1ª línea de NetTrace.log (no se guarda en ningún lado). Con clientes en
        #   otras PCs hay que sacar la de cada uno del 0x100F (va ofuscada: a descifrar).
        t = ident.encode("utf-16-le")[:0x3C]
        m[0xA:0xA + len(t)] = t
    if udp:
        # 🟡 +0x48 u32 IP · +0x4C u16 puerto · +0x4E u32 IP · +0x52 u16 puerto (el constructor
        #   los inicializa juntos): las direcciones UDP del jugador para el P2P de LithTech, en el
        #   mismo formato en que el cliente manda la suya en el 0x100F (u32 «al revés», u16)
        ip, puerto = udp
        struct.pack_into("<IHIH", m, 0x48, ip, puerto, ip, puerto)
    pj = bytearray(P.registro_personaje(c["nombre"], lugar=0, clase=c["clase"], ident=c["exp"],
                                        nivel=nivel(c["exp"]), partidas=c["partidas"],
                                        abandonos=c["abandonos"]))
    m[0x54:0xA6] = pj[0:0x52]
    struct.pack_into("<I", m, 0x54, 0x89A3AC)
    struct.pack_into("<I", m, 0x54 + 0x24, 0x89A378)
    struct.pack_into("<I", m, 0xA6, 0x89A368)
    struct.pack_into("<I", m, 0xB6, 0x89A390)
    # 🟡 +0xBA: 18 × 34 B, uno por PARTE del equipo (las mismas 18 del personaje +0x72): vt ·
    #   u16 🟡 TIPO del ítem puesto · vt · 24 B. En cero, el otro jugador se ve SIN equipo en la
    #   partida (medido 20:21, por el relay)
    tipos = equipo_tipos(c)
    for k in range(18):
        struct.pack_into("<IH", m, 0xBA + 34 * k, 0x89A38C, tipos[k])
        struct.pack_into("<I", m, 0xBA + 34 * k + 6, 0x89A380)
    struct.pack_into("<I", m, 0x31E, 0x89A3B8)
    if completo:
        ext = bytearray(0x43)
        struct.pack_into("<I", ext, 0, 0x89A398)
        for k in range(9):
            struct.pack_into("<I", ext, 4 + 7 * k, 0x89A394)
        m += ext
    return bytes(m)


def pares(s, espera=0):
    """★ 0x1059 «Peer Public IP» (`0x550BE0`) a CADA miembro de la sala: las direcciones UDP de
    todos, para el P2P (el ping de la sala, la partida). 7 B: u8 N · 4 B 🟡 · u8 → +0x2DE · u8 →
    +0x2DF; y N × 7 B: u8 id · u32 IP · u16 puerto, COMO ENTEROS (el cliente les hace htonl /
    htons) → +0x4E / +0x52 del miembro; después la capa UDP (`0x74AA60`) les manda `0xC354`
    durante 2 s para conectarse. En esta máquina: 127.0.0.1 + el puerto
    privado de cada uno (del 0x100F). 🟡 Con clientes en otras redes iría la PÚBLICA (la que ve
    el server), y para dos detrás del mismo NAT (un cíber) la privada: ver §NAT de PROTOCOLO."""
    # ⚠ a cada uno SÓLO los OTROS: el cliente busca cada id en su lista de miembros (`0x61C140`)
    #   y el jugador local no está ahí → puntero nulo → se cae (medido 17:09: los DOS en 0x550CAC)
    r = []
    for dest in s["miembros"]:
        regs = []
        for i, n in enumerate(s["miembros"]):
            udp = dir_udp(n)
            if udp and n != dest:
                # ⚠ la IP y el puerto como ENTEROS (little-endian), igual que en el 0x1010: el
                #   cliente les hace htonl/htons (`[0x88A55C]`, la misma que en `0x6218F0`). En
                #   orden de red imprimía «1.0.0.127» y saludaba (0xC354) a una dirección que no
                #   existe (medido 17:25)
                regs.append(struct.pack("<BIH", i, udp[0], udp[1]))
        cuerpo = struct.pack("<B4xBB", len(regs), 0, 0) + b"".join(regs)
        r.append((0x1059, cuerpo, espera, dest))
    return r


def personaje_obj(c):
    """El objeto PERSONAJE (0x52 B, `0x53F680`) con sus vtables: va dentro del miembro de la sala
    y del usuario de la lista del lobby."""
    pj = bytearray(P.registro_personaje(c["nombre"], lugar=0, clase=c["clase"], ident=c["exp"],
                                        nivel=nivel(c["exp"]), partidas=c["partidas"],
                                        abandonos=c["abandonos"])[0:0x52])
    struct.pack_into("<I", pj, 0, 0x89A3AC)
    struct.pack_into("<I", pj, 0x24, 0x89A378)
    return bytes(pj)


def lista_usuarios():
    """★ 0x101B (`0x541EB0`): la LISTA DE USUARIOS del lobby (la columna «Level · Character Name»
    del video). Como el 0x101C: u8 total · u8 índice (y u16 N en el primero) + N × 92 B, cada
    uno copiado ENCIMA de un objeto de `0x53FBE0`: vt 0x89A3C4 · u32 id · u16 sala (0xFFFF =
    ninguna) · el personaje (0x52 B) → canal (`cuenta+0x220`, `0x6109F0`)."""
    regs = []
    for n in sorted(ASIGNADAS):
        c = leer(n)
        sala = partida(n).get("sala")
        regs.append(struct.pack("<IIH", 0x89A3C4, n, sala if sala in SALAS else 0xFFFF)
                    + personaje_obj(c))
    return struct.pack("<BBH", 1, 0, len(regs)) + b"".join(regs)


def avisar_usuarios(salvo=None):
    cuerpo = lista_usuarios()
    return [(0x101B, cuerpo, 0, n) for n in sorted(ASIGNADAS) if n != salvo]


def avisar_lista(salvo=None):
    """La lista nueva a todas las conexiones con cuenta (menos `salvo`). Las que no están en el
    lobby la ignoran: el 0x101C sólo está en el mapa de comandos del lobby."""
    cuerpo = lista_salas()
    return [(0x101C, cuerpo, 0, n) for n in sorted(ASIGNADAS) if n != salvo]
# ★ para probar a mano: lo que se deje en este archivo ([["1069", "00"], …]) sale con el próximo
#   «estoy vivo» (0x1001), y el archivo se borra
EMPUJAR = os.path.join(RAIZ, "_trabajo", "servidor", "empujar.json")


def partida(conexion):
    return PARTIDAS.setdefault(conexion, {"escenario": 1011, "muertos": 0, "golpes": 0,
                                          "revividas": 0, "inicio": None, "puntos": 0})


def casilleros_de(items):
    """El casillero de cada ítem ([tipo, cantidad, casillero]); sin casillero, el primero libre
    de la bolsa (18…)."""
    usados = {it[2] for it in items if len(it) > 2}
    libres = (x for x in range(18, 168) if x not in usados)
    return [it[2] if len(it) > 2 else next(libres) for it in items]


def inventario(c):
    """★ Los ítems de la cuenta con todo fijo: [tipo, cantidad, casillero, SERIAL]. El serial es
    la clave con la que el cliente nombra cada ítem (equipar, vender): tiene que ser FIJO —
    antes era «posición + 1» y al vender uno se habrían corrido todos. Las cuentas viejas (sin
    serial) toman posición + 1, que es lo que ya conocía su cliente."""
    items = c.get("items", [])
    cas = casilleros_de(items)
    return [[it[0], it[1], cas[i], it[3] if len(it) > 3 else i + 1, it[4] if len(it) > 4 else 1]
            for i, it in enumerate(items)]


def serial_nuevo(inv):
    return max([it[3] for it in inv] + [0]) + 1


def libre_en_bolsa(inv):
    usados = {it[2] for it in inv}
    return next(k for k in range(18, 168) if k not in usados)


# ★ EL EQUIPO DEL PERSONAJE (+0x6E: vt 0x89A388 + 18 u32 = el SERIAL de cada pieza puesta, 0 =
#   nada). Medido con Frida el 10-nov (`pj.py`, 18:45): con las 8 piezas de Warrior puestas,
#   +0x72.. = 1 2 3 4 5 6 7 8 → el ÍNDICE es la PARTE, no el casillero (la máscara, serial 3, está
#   en el casillero 0 y en el índice 2). 🟡 La parte sale de la familia del tipo (tipo // 1000:
#   0 arma, 1 segunda arma, 3 máscara, 4 torso, 5 piernas, 6 guantes, 7 cinturón, 8 botas; no hay
#   familia 2 en ITEMTYPELIST) en ese orden. Los índices 8–17 no se vieron usados.
PARTE = {0: 0, 1: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}


def equipo(c):
    """Los 18 u32 del equipo: el serial de cada ítem en un casillero de equipo."""
    e = [0] * 18
    for tipo, _, cas, serial, _ in inventario(c):
        parte = PARTE.get(tipo // 1000)
        if cas < 12 and parte is not None:
            e[parte] = serial
        elif 12 <= cas < 18:
            # ★ la BARRA de la partida (los 6 de la derecha del HUD, teclas 1–6 = GameItem1–6):
            #   el HUD lee personaje +0xA2 + 4·i = índices 12–17 (`0x510619`) = casilleros 12–17
            e[cas] = serial
    return e


PRODUCTOS_XML = os.path.join(RAIZ, "_trabajo", "datos", "Product.xml")


def productos():
    """★ La TIENDA: `Data\\Product.xml` (sacado con `herramientas/sacar_xml.py SHOP Product`).
    {ID de producto: (oro, cash, [(tipo de ítem, cantidad)])}. Sin el archivo, la tienda no
    vende (vacío)."""
    try:
        x = open(PRODUCTOS_XML, "rb").read()
    except OSError:
        return {}
    r = {}
    for a, cuerpo in re.findall(rb"<Product ([^>]*)>(.*?)</Product>", x, re.S):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        r[int(v[b"ID"])] = (int(v[b"SellGold"]), int(v[b"SellCash"]),
                            [(int(t), int(n)) for t, n in
                             re.findall(rb'RefID="(\d+)" Count="(\d+)"', cuerpo)])
    return r


def precios_venta():
    """{tipo de ítem: oro que da la tienda} — `<BUYS><BuyItem RefID BuyGold/>` de Product.xml."""
    try:
        x = open(PRODUCTOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(t): int(g) for t, g in re.findall(rb'<BuyItem RefID="(\d+)" BuyGold="(\d+)"', x)}


HABILIDADES_XML = os.path.join(RAIZ, "_trabajo", "datos", "Skill.xml")


def tabla_habilidades():
    """★ `Data\\Skill.xml` (`sacar_xml.py SKILLXML Skill`): {tipo del ítem-libro (REFID): (1 activa
    / 2 pasiva, ID, CLASS (65535 = todas), COST_GOLD, ACQUIRE_LEVEL)}."""
    try:
        x = open(HABILIDADES_XML, "rb").read()
    except OSError:
        return {}
    r = {}
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        r[int(v[b"REFID"])] = (1 if clase_xml == b"ACTIVE" else 2, int(v[b"ID"]),
                               int(v[b"CLASS"]), int(v[b"COST_GOLD"]), int(v[b"ACQUIRE_LEVEL"]))
    return r


PREMIOS_XML = os.path.join(RAIZ, "_trabajo", "datos", "StageReward.xml")
NADA = 40071                                                 # el ítem «None» (NameAndExplainString)


def tabla_premios():
    """★ `Data\\StageReward.xml` (`sacar_xml.py STAGE_REWARDS StageReward`): {escenario:
    (GiveCount, [(Type, Data, Count)])}. Type 2 = ítem (Data = tipo); Type 0 = 🟡 oro (Data)."""
    try:
        x = open(PREMIOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(i): (int(g), [tuple(map(int, t)) for t in re.findall(
                rb'Type="(\d+)" Data="(\d+)" Count="(\d+)"', cuerpo)])
            for i, g, cuerpo in re.findall(
                rb'<REWARD Present_Index="(\d+)" GiveCount="(\d+)">(.*?)</REWARD>', x, re.S)}


def dar_premio(c, escenario, elegir=None):
    """★ El premio de la stage = TODA su lista de StageReward.xml, como la suma el cliente en
    AWARD RESULTS (`0x612B40`: con el 0x1072 [índice, (jugador, 1)] llama a `0x5FEA50` = Σ Data de
    Type 0 → ORO, `0x5FEAA0` = Σ Type 1 → EXP, `0x5FEAF0` = lista los Type 2 → ÍTEMS, sin filtrar por
    clase). 🟡 Qué hacía GiveCount no se sabe; así lo que se ve es lo que se recibe. Devuelve los
    ítems nuevos (ya en c) para el PlayEnd. `elegir` (pruebas): dar sólo ese presente."""
    _, lista = tabla_premios().get(escenario, (0, []))
    nuevos = []
    inv = inventario(c)
    for tipo_p, dato, cant in ([elegir] if elegir else lista):
        if tipo_p == 0:
            c["plata"] += dato
        elif tipo_p == 1:
            c["exp"] += dato
        elif tipo_p == 2 and dato != NADA:
            # un libro de habilidad llega SIN verificar (para eso está el Skill Check Scroll)
            it = [dato, max(1, cant), libre_en_bolsa(inv), serial_nuevo(inv),
                  0 if 31000 <= dato <= 33999 else 1]
            inv.append(it)
            nuevos.append(it)
    c["items"] = inv
    return nuevos


def obj_habilidad(h):
    """Una habilidad aprendida (13 B, `0x53F530`, → cuenta+0x728): vt 0x89A3A4 · u32 CLAVE · u8
    1 activa / 2 pasiva (`0x523D89`) · u16 ID de Skill.xml · u8 +0xB = la casilla en la grilla de
    APRENDIDAS (SLOT 1–3, 0…; nace 0xFF) · u8 +0xC = el ATAJO de la partida (1…8 = F1…F8, la grilla
    de arriba; 0 = ninguno). Medido 19:30: con +0xC = 1 el Dash aparece en la grilla de arriba y en
    la barra del HUD, y F1 lo marca. (Lo cambian las listas de 0x102D/0x103D, `0x61ECB0`.)"""
    clave, tipo, ident, b, cc = h
    return struct.pack("<IIBHBB", 0x89A3A4, clave, tipo, ident, b, cc)


def es_equipo(tipo):
    return 1 <= tipo <= 19999                               # `0x5177C0`


TIPOS_XML = os.path.join(RAIZ, "_trabajo", "datos", "ItemTypeList.xml")


def tipos_item():
    """{tipo: (MAXSOLID, REPAIRGOLD)} de `ItemTypeList.xml` (`sacar_xml.py ITEMTYPELIST ItemTypeList`)."""
    try:
        x = open(TIPOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(i): (int(m), int(g)) for i, m, g in re.findall(
        rb'<ITEMTYPE ID="(\d+)"[^>]*?MAXSOLID="(\d+)" REPAIRGOLD="(\d+)"', x)}


def nivel_engarce(niveles, i):
    """Los 3 bits del engarce i en +0x20 de la ficha (`0x521332`): 0 = cerrado (no se dibuja)."""
    return (niveles >> (29 - 3 * i)) & 7


def ficha(c, serial):
    """★ La FICHA de un ítem (36 B, `0x540400` / `0x61FDB0`): vt 0x89A384 · u32 serial · vt
    0x89A380 · **10 × u16 = la piedra espiritual de cada ENGARCE** (tipo de ítem 21xxx–25xxx;
    0 = no hay engarce) · u32 = el NIVEL de cada engarce, 3 bits cada uno (`(x >> (29 − 3i)) & 7`,
    `0x61FE33`). Lo que tiene cada ítem lo guarda la cuenta en c["fichas"][serial]."""
    f = c.get("fichas", {}).get(str(serial), {})
    engarces = (list(f.get("engarces", [])) + [0] * 10)[:10]
    return struct.pack("<III10HI", 0x89A384, serial, 0x89A380, *engarces, f.get("niveles", 0))


def registro_item(serial, tipo, cant, casillero, verificado=1, pegada=False, c=None):
    """Un ítem como lo lee `0x617630` (21 B) y, si es equipo, su ficha (36 B, `ficha`).
    vt 0x89A39C (el objeto, `0x53F4B0`) · u32 serial · u16 tipo · u8 🟡 (iba la cantidad) · u8
    CASILLERO · u16 +0xC 🟡 (nace con 0xFFFF) · u8 +0xE VERIFICADO (nace con 1; un ítem de
    habilidad 31000–33999 con 0 es un «Unknown Skill Book») · i16 +0xF ★ DURABILIDAD (la ficha
    muestra +0xF / MAXSOLID × 100, `0x5201F9`: con 0 decía «Durability 0%») · u32 +0x11 ★ la
    CANTIDAD (la barra de pociones lee [ítem+0x11], `0x510734`); en el PlayEnd, −1 = equipo con
    su ficha PEGADA detrás (`0x548C77`)."""
    r = struct.pack("<IIHBBHBhI", 0x89A39C, serial, tipo, cant, casillero, 0, verificado,
                    # 🟡 MAXSOLID (10000 en casi todo el equipo) o lo que guarde la cuenta
                    (c or {}).get("durabilidad", {}).get(str(serial), 10000) if es_equipo(tipo) else 0,
                    0xFFFFFFFF if pegada and es_equipo(tipo) else cant)
    return r, (ficha(c or {}, serial) if es_equipo(tipo) else b"")


def equipo_tipos(c):
    """Como `equipo`, pero con el TIPO de ítem de cada parte en vez del serial."""
    por_serial = {it[3]: it[0] for it in inventario(c)}
    return [por_serial.get(s, 0) for s in equipo(c)]


def obj_equipo(c):
    return struct.pack("<I18I", 0x89A388, *equipo(c))


PUNTOS_POR_NIVEL = 3          # 🟡 los de 2009 no se saben


def stats_de(c):
    """Las 6 u16 del personaje (+0x62): Strength Constitution Dexterity Intelligence Wisdom y
    ★ +0x6C = los PUNTOS SIN REPARTIR («Bonus Stat», `0x51E9F4`). Los repartidos los guarda la
    cuenta; los libres = PUNTOS_POR_NIVEL × (nivel − 1) − los repartidos."""
    repartidos = list((c.get("stats") or [0] * 5)[:5])
    libres = max(0, PUNTOS_POR_NIVEL * (nivel(c["exp"]) - 1) - sum(repartidos))
    return repartidos + [libres]


def obj_stats(c):
    """+0x5E: vt 0x89A368 + las 6 u16 de `stats_de`."""
    return struct.pack("<I6H", 0x89A368, *stats_de(c))


def pj_cuenta(c):
    """El personaje (0xBA B) de la cuenta, con sus estadísticas y su EQUIPO puesto."""
    return P.registro_personaje(c["nombre"], lugar=0, clase=c["clase"], ident=c["exp"],
                                nivel=nivel(c["exp"]), partidas=c["partidas"],
                                abandonos=c["abandonos"], stats=tuple(stats_de(c)),
                                extra={0x72: struct.pack("<18I", *equipo(c)),
                                       # ★ +0x6C = Bonus Stat (registro_personaje escribe sólo 5)
                                       0x6C: struct.pack("<H", stats_de(c)[5]),
                                       # ★ +0x5B = LUGARES DE HABILIDAD: `0x523E41` lo compara con
                                       #   cuántas tiene (cuenta+0x728); con 0 → «You do not have
                                       #   enough skill slot» (19:11). 🟡 12 = una página SLOT de
                                       #   3×4 (el valor de 2009 no se sabe)
                                       0x5B: bytes([c.get("lugares_habilidad", 12)]),
                                       # 🟡 PARA MEDIR: {"0x5c": "4d"} pisa esos bytes del personaje
                                       **{int(k, 16): bytes.fromhex(v)
                                          for k, v in c.get("extra_pj", {}).items()}})


def cuerpo_cuenta(c, conexion=0):
    """0x1012 [§5.4]: la cuenta (cash, plata, monedas, lugares) + el personaje."""
    b = bytearray(struct.pack("<H", 1) + bytes(26) + struct.pack("<HHB", 0, 0, 0))
    # ★ +6 u32 → cuenta+0x2B8 = el ID con que el cliente se registra en el punch (`0x3006`). Pisa
    #   el del 0x1010: en 0 los dos clientes se anotaban como «jugador 0» (relay, 20:03)
    struct.pack_into("<I", b, 6, conexion or 0)
    struct.pack_into("<I", b, 0x0F, c["cash"])
    struct.pack_into("<I", b, 0x13, c["plata"])
    struct.pack_into("<H", b, 0x17, c["monedas"])          # monedas de revivir (+0x2C9)
    b[0x19] = 5                                             # lugares habilitados
    # ★ +0x1A → cuenta+0x2CC = LUGARES LIBRES en la bolsa (+6 = +0x2B8, medido; nadie más lo
    #   escribe). Con 0, «Purchase All» decía «No Empty Slot Available» (`0x54DCEA`, 21:41)
    b[0x1A] = max(0, 150 - sum(1 for it in inventario(c) if it[2] >= 18))
    b[0x20] = 1                                             # un personaje
    # ★ N1 (+0x1C) × 21 B = el INVENTARIO (`0x617630` → cuenta+0x708; el mismo del PlayEnd): +4 u32
    #   🟡 serie · +8 u16 TIPO DE ÍTEM (ITEMTYPELIST) · +0xA u8 🟡 · +0xB u8 🟡 · +0xC u16 🟡 ·
    #   +0xE u8 🟡 · +0xF u16 🟡 · +0x11 u32 (−1 → vienen 36 B más, `0x6176E0`). Se copia campo
    #   por campo (la vtable de +0 no se pisa).
    #   (+0xA = la CANTIDAD, `0x615D90`)
    # ★ +0xB = EL CASILLERO (medido 18:30–18:40, foto por foto): 0–11 = EQUIPO (control − 10000,
    #   `0x51C6A5`), 12–17 = la fila de 6 de arriba (🟡 la barra de ítems de la partida, teclas
    #   1–6), 18… = la BOLSA (5 páginas de 30). Cada ítem de la cuenta: `inventario()`.
    inv = inventario(c)
    struct.pack_into("<H", b, 0x1C, len(inv))
    regs = b"".join(registro_item(serial, tipo, cant, cas, ver, c=c)[0]
                    for tipo, cant, cas, serial, ver in inv)
    # ★ N2 (+0x1E) × 36 B = la FICHA de cada ítem (`0x6176E0`): vt (no se copia) · u32 clave (🟡 la
    #   serie del ítem) · 28 B 🟡 (opciones / refinado). Sin ella, al pasar el mouse por un ítem
    #   EQUIPADO la ficha (`0x520336` → `0x61FDB0`) lee un puntero nulo y el juego se cae (18:24)
    struct.pack_into("<H", b, 0x1E, len(inv))
    fichas = b"".join(ficha(c, it[3]) for it in inv)
    return bytes(b) + regs + fichas + pj_cuenta(c)


def game_over(c, p, conexion):
    """★ GAME OVER (medido 16:20–16:26): 0x1069 = modo espectador («<Jump Key> pushing allow
    viewing of other players», sin HUD); con todos muertos (acá: uno solo) no hay a quién mirar
    → 6 s después 0x1075 → el LOBBY (sin caerse). 🟡 Con varios jugadores no se sabe."""
    p["game_over_en"] = None
    c["partidas"] += 1
    guardar(c)
    salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                         c["exp"], 0, 0)
    return [(0x1069, b"\x00", 0, conexion), (0x1075, salida, 6000, conexion)]


def numero_jugador(conexion):
    """El número de jugador en su sala (el que el cliente tiene en cuenta+0x705); solo = 0."""
    s = SALAS.get(partida(conexion).get("sala"))
    return s["miembros"].index(conexion) if s and conexion in s["miembros"] else 0


def cuerpo_1072(conexion, p):
    """★ 0x1072 AWARD RESULTS (`0x546CA0`): u32 ÍNDICE de StageReward (→ sala+0x148) · u8 N · N ×
    (u8 jugador · u8 1 = «cobra el premio de la stage»). Con [0, 0] (lo de antes) el cliente
    mostraba Gold 0 / Exp 0. Cada jugador de la sala con su 1."""
    s = SALAS.get(p.get("sala"))
    jugadores = (range(len(s["miembros"])) if s and conexion in s["miembros"]
                 else [numero_jugador(conexion)])
    return struct.pack("<IB", p.get("escenario", 0), len(jugadores)) + b"".join(
        struct.pack("<BB", j, 1) for j in jugadores)


def tick(conexiones):
    """Cada segundo (lo llama el espía): lo que el server tiene que decir por TIEMPO."""
    r = []
    forzar = os.path.join(RAIZ, "_trabajo", "servidor", "forzar_lista")   # (para probar a mano)
    if os.path.exists(forzar):
        os.remove(forzar)
        _vivo.LISTA_CAMBIO = True
    if getattr(_vivo, "LISTA_CAMBIO", False):
        _vivo.LISTA_CAMBIO = False
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
    _vivo.LISTA_CAMBIO = True                               # salas y usuarios: uno menos


def responder(cmd, cuerpo, conexion):
    if cmd < 0x1000:                                        # el Broker: no es de una cuenta
        return None
    c = leer(conexion)
    p = partida(conexion)
    if cmd == 0x100F and len(cuerpo) >= 0xE9:               # «quién soy» [§5.1]
        # ★ cerca del final viaja su UDP (medido con dos clientes, 17:02): +0xDD u32 IP privada
        #   (192.168.1.10 como entero 0xC0A8010A) · +0xE1 u16 PUERTO PRIVADO (57654 / 51001: cada
        #   cliente el suyo) · +0xE3 u32 IP pública · +0xE7 u16 puerto público (el que le dijo el
        #   0x0609). En esta máquina los dos se hablan por 127.0.0.1 con su puerto privado.
        #   ⚠ (antes +0xDE/+0xE2: corrido en 1 → puerto «481» = E1 01, medido 17:40)
        p["udp"] = (0x7F000001, struct.unpack_from("<H", cuerpo, 0xE1)[0])
        # ★ 0x1010 (`0x549742`, 12 B): u16 1 · u32 → cuenta+0x2B8 (🟡 id de la cuenta) · u32 IP y
        #   u16 puerto del SERVER UDP DE PUNCH (→ `0x6218F0`, «[Punch UDP IP, PORT]»): con
        #   0.0.0.1:0 nadie se encuentra. La IP va como entero (el cliente le hace htonl).
        escribir_relay()
        return [(0x1010, struct.pack("<HIIH", 1, conexion, *(relay() or (0x7F000001, PUNCH_PUERTO))),
                 0)]
    if cmd == 0x1011:                                       # SELECT CHARACTER
        return [(0x1012, cuerpo_cuenta(c, conexion), 0)]
    if cmd == 0x101F and len(cuerpo) >= 6:                  # ★ ENTRAR a una sala (Enter)
        # cuerpo (26 B): u32 0 · u16 número de sala · 🟡 (16 B: ¿la clave?)
        num = struct.unpack_from("<H", cuerpo, 4)[0]
        s = SALAS.get(num)
        if s is None or len(s["miembros"]) >= s["sala"][0x2F]:
            return [(0x1020, struct.pack("<H", 0) + bytes(99), 0)]   # 🟡 «no se pudo»
        s["miembros"].append(conexion)
        p["sala"] = num
        yo = s["miembros"].index(conexion)
        sala = bytearray(s["sala"])
        sala[0x2D], sala[0x2E] = 1, len(s["miembros"])
        # 0x1020 (`0x543640`, 101 B + N × 0x32C): u16 1 · u8 → +0x705 · u8 → +0x706 (MI número
        #   de jugador) · u8 → +0x29D · vt 0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · la sala (89 B) ·
        #   u8 N · los OTROS miembros (🟡 el propio lo agrega el cliente, como el anfitrión)
        otros = [n for n in s["miembros"] if n != conexion]
        cab = struct.pack("<HBBBIBB", 1, yo, yo, 0, 0x89A3B8, 0, 0)
        cuerpo20 = (cab + bytes(sala) + bytes([len(otros)])
                    + b"".join(miembro(leer(n), s["miembros"].index(n), conexion=n)
                                for n in otros))
        # al anfitrión (y los demás de la sala): 0x1057 (`0x54F020`, 0x377 B) = u8 → +0x272 ·
        #   u8 → +0x271 (estado de la sala) · vt 0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · el
        #   miembro NUEVO completo (0x36F)
        aviso = (struct.pack("<BBIBB", 0, 0, 0x89A3B8, 0, 0)
                 + miembro(c, yo, completo=True, conexion=conexion))
        return ([(0x1020, cuerpo20, 0)] + [(0x1057, aviso, 0, n) for n in otros]
                + pares(s, 500) + avisar_lista(salvo=conexion))
    if cmd == 0x1047 and len(cuerpo) >= 1:                  # ★ F9 READY (el que no es anfitrión)
        # cuerpo: u8 estado (1 = listo) · u8 🟡. A él: 0x1048 (`0x54E5C0`: u16 1 · u8 → +0x2DE,
        #   el botón). A los demás de la sala: 0x1058 «SomeOne_ChangeState» (`0x54FC80`: u8 id ·
        #   u16 tipo · u8 valor; tipo 1 = +0x322 del miembro = listo, y refresca; tipo 2 = +0x323;
        #   tipo 3 = SE FUE, con el valor = el nuevo anfitrión → +0x29D)
        s = SALAS.get(p.get("sala"))
        # ⚠ el cuerpo es u8 NÚMERO DE JUGADOR · u8 ESTADO (medido 21:58 con 3: kai «01 01», mio «02
        #   01»). Antes se tomaba el 1er byte como estado: con 2 jugadores coincidía (el invitado es
        #   el 1), con 3 mio quedaba en «2» (otro ícono) y el anfitrión no podía largar
        estado = cuerpo[1] if len(cuerpo) >= 2 else cuerpo[0]
        r = [(0x1048, struct.pack("<HB", 1, estado), 0)]
        if s and conexion in s["miembros"]:
            yo = s["miembros"].index(conexion)
            r += [(0x1058, struct.pack("<BHB", yo, 1, estado), 0, n)
                  for n in s["miembros"] if n != conexion]
        return r
    if cmd == 0x1049 and len(cuerpo) >= 3:                  # ★ CAMBIAR TÍTULO / PASSWORD DE SALA
        # cuerpo: u8 jugador · u16 tipo (1 Title, 2 Password) · texto
        tipo = struct.unpack_from("<H", cuerpo, 1)[0]
        texto = cuerpo[3:]
        num = p.get("sala")
        s = SALAS.get(num) if num else None
        r = [(0x104A, struct.pack("<HH", 1, tipo) + texto, 0)]
        if s:
            for n in s["miembros"]:
                if n != conexion:
                    r.append((0x104A, struct.pack("<HH", 1, tipo) + texto, 0, n))
        return r
    if cmd == 0x1045:                                       # ★ SALIR DE LA SALA (Leave Room)
        # El cliente tocó «Leave Room»: espera 0x1046 (u16 1) para volver al lobby (pantalla 3)
        num = p.pop("sala", None)
        r = [(0x1046, struct.pack("<H", 1), 0)]
        s = SALAS.get(num) if num else None
        if s and conexion in s["miembros"]:
            yo = s["miembros"].index(conexion)
            s["miembros"].remove(conexion)
            otros = list(s["miembros"])
            if otros:
                if s["anfitrion"] == conexion:
                    s["anfitrion"] = otros[0]
                nuevo_anf = s["miembros"].index(s["anfitrion"])
                r += [(0x1058, struct.pack("<BHB", yo, 3, nuevo_anf), 0, n) for n in otros]
            else:
                del SALAS[num]
        return r + avisar_lista()
    if cmd == 0x1051 and len(cuerpo) >= 1:                  # ★ EXPULSIÓN DE LA SALA (Kick)
        # El anfitrión expulsa a un jugador: cuerpo[0] = slot del expulsado (0..3)
        slot_kicked = cuerpo[0]
        num = p.get("sala")
        s = SALAS.get(num) if num else None
        r = []
        if s and s["anfitrion"] == conexion and slot_kicked < len(s["miembros"]):
            kicked_conn = s["miembros"][slot_kicked]
            if kicked_conn != conexion:
                # 1. Al anfitrión que pateó: 0x1052 para cerrar cuadro de espera (b"\0")
                r.append((0x1052, b"\0", 0))
                # 2. Al expulsado: 0x1054 para mandarlo de vuelta al lobby (pantalla 3)
                p_kicked = PARTIDAS.get(kicked_conn, {})
                p_kicked.pop("sala", None)
                r.append((0x1054, struct.pack("<HB", 1, 0), 0, kicked_conn))
                # 3. Remover de la sala
                s["miembros"].remove(kicked_conn)
                nuevo_anf = s["miembros"].index(s["anfitrion"])
                # 4. Avisar a los restantes que el jugador se fue (tipo 3)
                r += [(0x1058, struct.pack("<BHB", slot_kicked, 3, nuevo_anf), 0, n)
                      for n in s["miembros"]]
                r += avisar_lista()
        return r
    if cmd == 0x100D and len(cuerpo) >= 13:                 # ★ CHAT (lobby / sala)
        # C→S (medido 18:19): u8 tipo (1) · u32 destino (FFFFFFFF = todos) · u32 0 · u32 largo en
        #   bytes · el texto UTF-16. S→C 0x1005 → la pantalla actual (`0x4DB6F0` → vt+0x80 =
        #   `0x4DF140`): cabecera de 37 B (`0x53FF50`): u8 tipo (1/3 = chat; 4 = aviso del sistema)
        #   · u32 color 🟡 · u32 🟡 · 28 B el NOMBRE en UTF-16 🟡 — y el texto (`0x742A80`: u32
        #   largo + UTF-16, como lo manda el cliente)
        largo = struct.unpack_from("<I", cuerpo, 9)[0]
        texto = cuerpo[13:13 + largo]
        # ⚠ medido con Frida (18:23): el TIPO lo lee en B+2 (con el tipo en B+0 leía 0xFF). La
        #   cabecera es u16 🟡 · u8 tipo · u32 🟡 (¿color?) · u32 🟡 · 26 B nombre UTF-16
        nombre = c["nombre"].encode("utf-16-le")[:24].ljust(26, b"\0")
        msg = (struct.pack("<HBII", 0, cuerpo[0], 0xFFFFFFFF, 0) + nombre
               + struct.pack("<I", len(texto)) + texto)
        s = SALAS.get(p.get("sala"))
        destinos = s["miembros"] if s and conexion in s["miembros"] else sorted(ASIGNADAS)
        return [(0x1005, msg, 0, n) for n in destinos]
    if cmd == 0x1023:                                       # lobby → «Select Character»
        # ★ el cliente espera 0x1024 (`0x5424A0`): u16 1 → pantalla 2 = SELECT CHARACTER
        return [(0x1024, struct.pack("<H", 1), 0)]
    if cmd == 0x1027:                                       # lobby → «Shop» (u32 · u8)
        # ★ 0x1028 (`0x542660`): u16 1 → pantalla 6 (🟡 la tienda)
        return [(0x1028, struct.pack("<H", 1), 0)]
    if cmd == 0x103F and len(cuerpo) >= 5:
        # ★ COMPRAR (medido el 10-nov 18:48: «[Basic Long Sword] 1200 Gold» → Confirm):
        #   0x103F (`0x54DA47` uno, `0x54DB2C` «Purchase All»): u32 (cuenta+0x2B8) · u8 N · N × u16
        #   ID DE PRODUCTO (Product.xml; el 1 = 1200 oro → ítem 1).
        #   0x1040 (`0x54D340`): u16 1 · u32 ORO (→ cuenta+0x2C5) · u32 CASH (→ +0x2C1) · u8 nA ·
        #   u16 nB · u16 nC · nA × u16 (productos que salen del carrito) · nB × ítem (21 B + ficha
        #   de 36 B si es equipo) · nC × 🟡 (`0x61FA90` sobre el personaje).
        #   🟡 sin oro (o sin el producto) → resultado 0: el cliente no hace nada.
        tabla = productos()
        n = cuerpo[4]
        pedidos = [struct.unpack_from("<H", cuerpo, 5 + 2 * k)[0] for k in range(n)
                   if 5 + 2 * k + 2 <= len(cuerpo)]
        costo = sum(tabla[x][0] for x in pedidos if x in tabla)
        if not pedidos or any(x not in tabla for x in pedidos) or costo > c["plata"]:
            return [(0x1040, struct.pack("<HIIBHH", 0, c["plata"], c["cash"], 0, 0, 0), 0)]
        inv = inventario(c)
        nuevos = []
        for x in pedidos:
            for tipo, cant in tabla[x][2]:
                it = [tipo, cant, libre_en_bolsa(inv), serial_nuevo(inv)]
                inv.append(it)
                nuevos.append(registro_item(it[3], tipo, cant, it[2]))
        c["items"] = inv
        c["plata"] -= costo
        guardar(c)
        return [(0x1040, struct.pack("<HIIBHH", 1, c["plata"], c["cash"], len(pedidos),
                                     len(nuevos), 0)
                 + b"".join(struct.pack("<H", x) for x in pedidos)
                 + b"".join(r + f for r, f in nuevos), 0)]
    if cmd == 0x103B and len(cuerpo) >= 12:
        # ★ VERIFICAR UN LIBRO (medido 19:09): pantalla Skill → clic derecho en el «Skill Check
        #   Scroll» (40051) → clic en el libro = un ítem de habilidad (31000–33999, `0x51BB40`) con
        #   +0xE = 0. 0x103B (`0x54A850`): u32 · u32 serial del LIBRO · u32 serial del PERGAMINO.
        #   0x103C (`0x54B1E0`, 31 B): u16 1 · u32 serial del pergamino · i32 pergaminos que
        #   quedan (≤ 0 → se borra) · el ítem nuevo (21 B: reemplaza al de su serial) → «Selected
        #   Skill has been verified. [Dash, 1Lv]» (`0x527070`).
        libro_s, perg_s = struct.unpack_from("<II", cuerpo, 4)
        inv = inventario(c)
        libro = next((x for x in inv if x[3] == libro_s), None)
        perg = next((x for x in inv if x[3] == perg_s), None)
        if (libro is None or perg is None or not 31000 <= libro[0] <= 33999 or libro[4]
                or perg[0] != 40051 or perg[1] < 1):
            return [(0x103C, struct.pack("<HII", 0, perg_s, 0), 0)]
        libro[4] = 1
        perg[1] -= 1
        if perg[1] <= 0:
            inv.remove(perg)
        c["items"] = inv
        guardar(c)
        return [(0x103C, struct.pack("<HIi", 1, perg_s, perg[1])
                 + registro_item(libro[3], libro[0], libro[1], libro[2], 1)[0], 0)]
    if cmd == 0x103D and len(cuerpo) >= 8:
        # ★ APRENDER (medido 19:12: clic derecho en el libro VERIFICADO → «450 Gold will be used.
        #   Do you want to learn the skill?» → Confirm): 0x103D (`0x54C9B0`) = u32 · u32 serial
        #   del libro · u16 N2 · u16 N3 · listas (u32 · u8) de la grilla (🟡).
        #   0x103E (`0x54CB70`): u16 1 · u8 MODO (0 = agregar; 1 = antes borrar la de clave
        #   [+0xB], 🟡 subir de nivel) · u32 ORO (+3 → cuenta+0x2C5) · u32 serial del libro (+7,
        #   sale de la bolsa) · u32 clave a borrar (+0xB, modo 1) · la habilidad (13 B, +0xF)
        #   ⚠ el oro va en +3: contado al revés (un push esi en 0x54CBFE) el cliente mostró «0 Gold» · u16 N × (u32 clave · u8 · u8) → «Selected Skill has
        #   been Learned» (`0x527380`).
        serial = struct.unpack_from("<I", cuerpo, 4)[0]
        inv = inventario(c)
        libro = next((x for x in inv if x[3] == serial), None)
        dato = tabla_habilidades().get(libro[0]) if libro else None
        habs = c.get("habilidades", [])
        no = (libro is None or dato is None or not libro[4] or dato[2] not in (c["clase"], 65535)
              or nivel(c["exp"]) < dato[4] or c["plata"] < dato[3]
              or any(h[2] == dato[1] and h[1] == dato[0] for h in habs)
              or len(habs) >= c.get("lugares_habilidad", 12))
        if no:
            return [(0x103E, struct.pack("<HBIII", 0, 0, c["plata"], serial, 0) + bytes(13)
                     + struct.pack("<H", 0), 0)]
        usadas = {h[3] for h in habs}
        # 🟡 al primer ATAJO libre (1–8): comodidad nuestra mientras arrastrar a la grilla de
        #   arriba no anda (con 0 la habilidad no queda en la barra de la partida)
        atajos = {x[4] for x in habs}
        h = [serial, dato[0], dato[1], next(k for k in range(36) if k not in usadas),
             next((k for k in range(1, 9) if k not in atajos), 0)]
        habs.append(h)
        inv.remove(libro)
        c["items"], c["habilidades"] = inv, habs
        c["plata"] -= dato[3]
        guardar(c)
        return [(0x103E, struct.pack("<HBIII", 1, 0, c["plata"], serial, 0) + obj_habilidad(h)
                 + struct.pack("<H", 0), 0)]
    if cmd == 0x1039 and len(cuerpo) >= 6:
        # ★ REPAIR (medido 21:37: «Repair All» → «22500 Gold will be used» → Confirm): 0x1039 =
        #   u32 · u16 1 = TODO (0 = «Repair Each»: le siguen los seriales, 🟡). El precio lo calcula
        #   el cliente igual: Σ (MAXSOLID − durabilidad) × REPAIRGOLD de ItemTypeList.xml (2500 × 1
        #   + 5000 × 4 = 22500, medido).
        #   0x103A (`0x54A7A0`): u16 1 · u32 ORO (→ +0x2C5) · u8 N · N × (u32 serial · u16 la
        #   durabilidad nueva, `0x615D40`) → «Item has been repaired».
        todo = struct.unpack_from("<H", cuerpo, 4)[0] == 1
        pedidos = {struct.unpack_from("<I", cuerpo, o)[0] for o in range(6, len(cuerpo) - 3, 4)}
        tabla = tipos_item()
        durab = c.setdefault("durabilidad", {})
        arreglar, costo = [], 0
        for tipo, _, _, serial, _ in inventario(c):
            if not es_equipo(tipo) or (not todo and serial not in pedidos):
                continue
            maximo, oro = tabla.get(tipo, (10000, 1))
            d = durab.get(str(serial), maximo)
            if d < maximo:
                arreglar.append((serial, maximo))
                costo += (maximo - d) * oro
        if not arreglar or costo > c["plata"]:
            return [(0x103A, struct.pack("<HIB", 0, c["plata"], 0), 0)]
        c["plata"] -= costo
        for serial, maximo in arreglar:
            durab[str(serial)] = maximo
        guardar(c)
        return [(0x103A, struct.pack("<HIB", 1, c["plata"], len(arreglar))
                 + b"".join(struct.pack("<IH", s_, m) for s_, m in arreglar), 0)]
    if cmd == 0x1035 and len(cuerpo) >= 13:
        # ★ REFINE SPIRIT STONE (medido 21:33: tres 21001 en «Phase» → Refine): 0x1035 = u32 · u8
        #   MODO (0 = Phase, 3 piedras; 1 = Level, 2 piedras) · N × u32 serial de cada piedra.
        #   0x1036 (`0x54AF20`, 25 B + lista): u16 resultado (1 = bien; 0x1B5D = «Refining has
        #   failed», las piedras se pierden) · u8 modo · la piedra NUEVA (21 B) · u8 N · N × u32
        #   las gastadas. 🟡 La regla no está en ningún archivo; de los datos: cada familia tiene 2
        #   FASES (21001–21006 / 21021–21026) × 6 NIVELES (el último dígito) → Phase: 3 iguales de
        #   fase 1 → fase 2 (21001 → 21021); Level: 2 iguales → nivel + 1 (21001 → 21002).
        #   Siempre sale bien.
        modo = cuerpo[4]
        cuantas = 3 if modo == 0 else 2
        seriales = [struct.unpack_from("<I", cuerpo, 5 + 4 * k)[0] for k in range(cuantas)
                    if 5 + 4 * k + 4 <= len(cuerpo)]
        inv = inventario(c)
        piedras = [next((x for x in inv if x[3] == s_), None) for s_ in seriales]
        tipos = {p[0] for p in piedras if p}
        nuevo = None
        if len(seriales) == cuantas and all(piedras) and len(tipos) == 1 and len(set(seriales)) == cuantas:
            t = tipos.pop()
            fam, resto = t // 1000, t % 1000             # 21 · 001
            if 21 <= fam <= 25:
                if modo == 0 and 1 <= resto <= 6:
                    nuevo = fam * 1000 + 20 + resto        # fase 1 → fase 2
                elif modo == 1 and resto % 20 in range(1, 6):
                    nuevo = t + 1                          # nivel + 1
        if nuevo is None:
            return [(0x1036, struct.pack("<HB", 0, modo) + bytes(21) + b"\0", 0)]
        for p in piedras:
            inv.remove(p)
        it = [nuevo, 1, libre_en_bolsa(inv), serial_nuevo(inventario(c)), 1]
        inv.append(it)
        c["items"] = inv
        guardar(c)
        return [(0x1036, struct.pack("<HB", 1, modo) + registro_item(it[3], nuevo, 1, it[2])[0]
                 + struct.pack("<B", cuantas) + b"".join(struct.pack("<I", s_) for s_ in seriales), 0)]
    if cmd == 0x1033 and len(cuerpo) >= 9:
        # ★ ENCHANT ITEM = poner piedras espirituales en los engarces (medido 21:29: espada con 1
        #   engarce + la 21001 soltada en el círculo → Refine): 0x1033 = u32 · u32 serial del ÍTEM
        #   · u8 N · N × (u8 engarce · u32 serial de la PIEDRA).
        #   0x1034 (`0x54A180`): u16 1 · u32 serial del ítem · u8 N · los 10 u16 de las piedras (→
        #   ficha+0xC) · N × u32 serial de cada piedra GASTADA (sale de la bolsa: no se apilan,
        #   MAXOVERLAPCNT = 1). 🟡 siempre sale bien.
        it_s, n = struct.unpack_from("<IB", cuerpo, 4)
        inv = inventario(c)
        it = next((x for x in inv if x[3] == it_s), None)
        f = c.setdefault("fichas", {}).setdefault(str(it_s), {"engarces": [0] * 10, "niveles": 0})
        gastadas, bien = [], it is not None
        for k in range(n):
            o = 9 + 5 * k
            if o + 5 > len(cuerpo):
                bien = False
                break
            i, piedra_s = struct.unpack_from("<BI", cuerpo, o)
            piedra = next((x for x in inv if x[3] == piedra_s), None)
            if (piedra is None or not 21000 <= piedra[0] <= 25999 or i >= 10
                    or not nivel_engarce(f["niveles"], i) or f["engarces"][i]):
                bien = False
                break
            gastadas.append((i, piedra))
        if not bien or not gastadas:
            return [(0x1034, struct.pack("<HIB", 0, it_s, 0) + bytes(20), 0)]
        for i, piedra in gastadas:
            f["engarces"][i] = piedra[0]
            inv.remove(piedra)
        c["items"] = inv
        guardar(c)
        return [(0x1034, struct.pack("<HIB", 1, it_s, len(gastadas))
                 + struct.pack("<10H", *f["engarces"])
                 + b"".join(struct.pack("<I", p[3]) for _, p in gastadas), 0)]
    if cmd == 0x1037 and len(cuerpo) >= 12:
        # ★ CREATE SOCKET (Refinery, medido 21:22: espada + «Add Socket Drill» → Create): 0x1037 =
        #   u32 · u32 serial del ÍTEM · u32 serial del TALADRO (40001).
        #   0x1038 (`0x54B070`, 46 B): u16 resultado (1 = «Congratulation. Succesfully increased
        #   Socket», 0x1F41 = «Increasing Socket has Failed», el taladro igual se gasta) · u32
        #   serial del taladro · i32 los que quedan (≤ 0 → se borra) · la FICHA nueva (36 B).
        #   🟡 Siempre sale bien (la probabilidad de 2009 no se sabe) y hasta 10 engarces.
        it_s, tal_s = struct.unpack_from("<II", cuerpo, 4)
        inv = inventario(c)
        it = next((x for x in inv if x[3] == it_s), None)
        tal = next((x for x in inv if x[3] == tal_s), None)
        fichas = c.setdefault("fichas", {})
        f = fichas.setdefault(str(it_s), {"engarces": [0] * 10, "niveles": 0})
        cerrado = next((i for i in range(10) if not nivel_engarce(f["niveles"], i)), None)
        if (it is None or tal is None or tal[0] != 40001 or tal[1] < 1 or not es_equipo(it[0])
                or cerrado is None):
            return [(0x1038, struct.pack("<HIi", 0, tal_s, tal[1] if tal else 0) + ficha(c, it_s), 0)]
        # ★ abrir = poner ≠ 0 en sus 3 bits de +0x20 (`0x521346`: con 0 el engarce ni se dibuja).
        #   ⛔ NO 0xFFFF en el u16: el cliente lo busca como tipo de ítem y se cae (0x61F922, 21:26)
        f["niveles"] |= 1 << (29 - 3 * cerrado)
        tal[1] -= 1
        if tal[1] <= 0:
            inv.remove(tal)
        c["items"] = inv
        guardar(c)
        return [(0x1038, struct.pack("<HIi", 1, tal_s, tal[1]) + ficha(c, it_s), 0)]
    if cmd == 0x1043 and len(cuerpo) >= 8:
        # ★ BORRAR HABILIDAD (medido 21:15: «[Dash] 1 Lv. Do you want to delete the skill?» →
        #   Confirm): 0x1043 = u32 · u32 CLAVE. 0x1044 (`0x54AD80`, 6 B): u16 1 · u32 clave → la
        #   saca de cuenta+0x728 (`0x61F1E0`). 🟡 no devuelve oro ni el libro.
        clave = struct.unpack_from("<I", cuerpo, 4)[0]
        habs = c.get("habilidades", [])
        if not any(h[0] == clave for h in habs):
            return [(0x1044, struct.pack("<HI", 0, clave), 0)]
        c["habilidades"] = [h for h in habs if h[0] != clave]
        guardar(c)
        return [(0x1044, struct.pack("<HI", 1, clave), 0)]
    if cmd == 0x1041 and len(cuerpo) >= 8:
        # ★ VENDER (medido 18:59: «[Basic Long Sword] 480 Gold» → Confirm): 0x1041 = u32
        #   (cuenta+0x2B8) · u32 SERIAL. El precio es el `<BuyItem RefID BuyGold>` de Product.xml
        #   (el 1 → 480, el mismo número que mostró el cliente).
        #   0x1042 (`0x54AA80`): u16 1 · u32 serial (sale de cuenta+0x708, `0x616CC0`) · u32 ORO
        #   (→ +0x2C5) · u8 1 = borrar también su ficha (`0x616D50`).
        serial = struct.unpack_from("<I", cuerpo, 4)[0]
        inv = inventario(c)
        it = next((x for x in inv if x[3] == serial), None)
        precio = precios_venta().get(it[0]) if it else None
        if it is None or precio is None or it[2] < 12:      # 🟡 lo puesto no se vende
            return [(0x1042, struct.pack("<HIIB", 0, serial, c["plata"], 0), 0)]
        inv.remove(it)
        c["items"] = inv
        c["plata"] += precio
        guardar(c)
        return [(0x1042, struct.pack("<HIIB", 1, serial, c["plata"], 1 if it[0] <= 19999 else 0), 0)]
    if cmd in (0x102B, 0x102D) and len(cuerpo) >= 0x1A:
        # ★ INVENTARIO (pantalla 6), medido el 10-nov 18:40: el cliente mueve los ítems SOLO (clic
        #   derecho = equipar; no avisa nada) y recién al irse manda lo que cambió:
        #     0x102D (`0x54BE70`, al tocar «Lobby»): u32 (cuenta+0x2B8) · 16 B estadísticas (vt
        #       0x89A368 + 6 u16) · u16 N movidos · u16 N2 · u16 N3 (🟡 sólo con [pantalla+0xDC]
        #       = 7) · N × (u32 serial · u8 casillero) · …
        #     0x102B (cambiar de pestaña, 27 B): lo mismo con un u8 PESTAÑA en +4
        #   y espera, con la misma forma (`0x54BBB0` / `0x54CD70`): u16 1 · u8 MODO · [0x102E: 8 B
        #   = u8 → cuenta+0x21C + el canal (7 B, como el 0x1018)] · 16 B estadísticas · 76 B EQUIPO
        #   (vt + 18 u32 → personaje+0x72) · u16 N × (u32 serial · u8 CANTIDAD (+0xA) · u8
        #   CASILLERO (+0xB), `0x615D90`) · u16 M × (u32 · u8 · u8 → cuenta+0x728, 🟡).
        #   0x102C: MODO → [pantalla+0xDC] (la pestaña). 0x102E: MODO 3 → pantalla 3 = el LOBBY;
        #   9 → la sala (con 0x63 B de sala + miembros: 🟡 no se arma todavía).
        off = 5 if cmd == 0x102B else 4
        stats = list(struct.unpack_from("<6H", cuerpo, off + 4))
        n1 = struct.unpack_from("<H", cuerpo, off + 16)[0]
        inv = inventario(c)                                # se fijan TODOS antes de mover
        por_serial = {it[3]: it for it in inv}
        movidos = []
        for k in range(n1):
            o = off + 22 + 5 * k
            if o + 5 > len(cuerpo):
                break
            serial, casillero = struct.unpack_from("<IB", cuerpo, o)
            if serial in por_serial:
                por_serial[serial][2] = casillero
                movidos.append(por_serial[serial])
        c["items"] = inv
        # ★ el REPARTO de puntos: el cliente manda las 5 nuevas + en la 6ª los puntos GASTADOS en
        #   esta tanda (medido 21:10: 5 Str + 3 Con → «… 05 00 03 00 … 08 00», mientras la pantalla
        #   decía «Bonus Stat : 64»). Se acepta sólo si ninguna baja, lo que subió = los gastados y no
        #   pasa de los libres; si no, queda lo de antes (y la respuesta le devuelve lo guardado:
        #   medido, el cliente vuelve a «0 · 72»)
        antes = stats_de(c)
        subio = sum(stats[:5]) - sum(antes[:5])
        if (all(n >= v for n, v in zip(stats[:5], antes[:5])) and subio == stats[5]
                and subio <= antes[5]):
            c["stats"] = list(stats[:5])
        guardar(c)
        cola = (obj_stats(c) + obj_equipo(c) + struct.pack("<H", len(movidos))
                + b"".join(struct.pack("<IBB", it[3], it[1], it[2]) for it in movidos)
                + struct.pack("<H", 0))
        if cmd == 0x102B:
            return [(0x102C, struct.pack("<HB", 1, cuerpo[4]) + cola, 0)]
        s = SALAS.get(p.get("sala"))
        if s and conexion in s["miembros"]:
            # ★ vino de la SALA (0x104C): MODO 9 (`0x54D096`) = los 0x63 B del 0x1020 sin su u16
            #   (u8 +0x705 · u8 +0x706 · u8 · vt · u8 · u8 · la sala · u8 N) + N miembros de 0x32C
            #   (🟡 todos, el propio incluido: `0x61C9E0` vacía la lista antes) → pantalla 5
            yo = s["miembros"].index(conexion)
            sala = bytearray(s["sala"])
            sala[0x2D], sala[0x2E] = 1, len(s["miembros"])
            datos = (struct.pack("<BBBIBB", yo, yo, 0, 0x89A3B8, 0, 0) + bytes(sala)
                     + bytes([len(s["miembros"])])
                     + b"".join(miembro(leer(n), s["miembros"].index(n), conexion=n)
                                for n in s["miembros"]))
            return [(0x102E, struct.pack("<HB", 1, 9) + datos + cola, 0)]
        canal = struct.pack("<BHHH", 1, 200, len(ASIGNADAS), 0)
        return [(0x102E, struct.pack("<HBB", 1, 3, 0) + canal + cola, 0)]
    if cmd == 0x104C:                                       # sala → «Inventory» (u8)
        # ★ 0x104D (`0x54ECF0`): u16 1 · u8 → cuenta+0x2DE → pantalla 6 (medido 19:24: sin
        #   respuesta, «Waiting for Response from Server»)
        return [(0x104D, struct.pack("<HB", 1, 0), 0)]
    if cmd == 0x1017:                                       # ENTER LOBBY [§5.7]
        # ★ N1 = las misiones TERMINADAS: cada una 10 B como el registro del PlayEnd (`0x621620`,
        #   la clave u32 en +4) — 🟡 [u32 0 · u32 escenario · u8 1 · u8 1]
        #   ⚠ la cabecera (16 B) es u16 resultado · u8 personaje (+2) · u32 N1 (+3) · u16 N2 (+7)
        #   · 7 B (+9 → `0x6103E0`): medido el 10-nov — antes se ponía N1 en +7 (mal contado un
        #   `push ebx`) y el cliente leía N1 = 0: el mapa de terminadas quedaba VACÍO
        n1 = c["terminadas"]
        # ★ los 7 B de +9 = el CANAL (→ `cuenta+0x220`+4, `0x6103E0`): 🟡 u8 número · u16
        #   CAPACIDAD (+5) · u16 ocupados (+7) · u16. Con capacidad 0 la lista de usuarios del lobby
        #   no agrega a nadie (`0x6109F0`: si [+0x1C] >= [+5] → no) — medido 18:18
        canal = struct.pack("<BHHH", 1, 200, len(ASIGNADAS), 0)
        # ★ N2 (+7) = las HABILIDADES aprendidas: N2 × 13 B (`0x544795` → cuenta+0x728)
        habs = c.get("habilidades", [])
        cuerpo18 = (struct.pack("<HBIH", 1, 0, len(n1), len(habs)) + canal
                    + b"".join(struct.pack("<IIBB", 0, m, 1, 1) for m in n1)
                    + b"".join(obj_habilidad(h) for h in habs))
        # al volver al lobby deja de ser anfitrión de su sala
        for viejo in [k for k, v in SALAS.items() if v["anfitrion"] == conexion]:
            del SALAS[viejo]
        # ★ y la lista de salas, apenas entra (cuando ya está en la pantalla del lobby)
        return ([(0x1018, cuerpo18, 0), (0x101C, lista_salas(), 1500),
                 (0x101B, lista_usuarios(), 1700)]
                + [(x[0], x[1], 1700, x[3]) for x in avisar_usuarios(salvo=conexion)])
    if cmd == 0x101D and len(cuerpo) >= 4 + 0x59:           # crear sala [§5.8]
        # ★ contestar con la sala QUE MANDÓ el cliente (su escenario y dificultad: 1011 Easy,
        #   1012 Normal…); la regla fija devolvía siempre 1011
        sala = bytearray(cuerpo[4:4 + 0x59])
        p["escenario"] = struct.unpack_from("<I", sala, 0x28)[0]
        # ★ el número: el más chico libre (lo que se ve en la columna «Number» del lobby)
        num = next(i for i in range(1, 1000) if i not in SALAS)
        struct.pack_into("<H", sala, 4, num)                # número de sala (el cliente: 0xFFFF)
        if sala[0x2F] == 0:
            sala[0x2F] = 3                                  # máximo de jugadores
        for viejo in [k for k, v in SALAS.items() if v["anfitrion"] == conexion]:
            del SALAS[viejo]                                # una sala por anfitrión
        SALAS[num] = {"sala": bytes(sala), "anfitrion": conexion, "miembros": [conexion]}
        p["sala"] = num
        return ([(0x101E, struct.pack("<HBBB", 1, 0, 0, 0) + bytes(sala), 0)]
                + avisar_lista(salvo=conexion))
    if cmd == 0x104E:                                       # ★ F9 START GAME (el anfitrión)
        # 0x104F (`0x54F170`) a TODOS los de la sala: u16 1 · u32 (+0x53: partidas) · u8 🟡 ·
        #   u8 N · N × 68 B ([u8 número de jugador][9 × 7 B: 🟡 su equipo para la partida])
        s = SALAS.get(p.get("sala"))
        miembros = s["miembros"] if s else [conexion]
        if s:
            s["jugando"], s["cargados"] = True, set()
        #   ⛔ probado (21:15) llenarlos con las habilidades de los atajos: NO las hace lanzar
        #   (el MP no baja con F1). Son de los OTROS (`0x61C230` los copia a su miembro). En cero.
        lista = b"".join(bytes([i]) + bytes(67) for i in range(len(miembros)))
        r = []
        for n in miembros:
            cn = leer(n)
            r.append((0x104F, struct.pack("<HIBB", 1, cn["partidas"], 0, len(miembros)) + lista,
                      0, n))
        return r + (avisar_lista(salvo=conexion) if s else [])
    if cmd == 0x105F:                                       # terminó de cargar: corre el reloj
        p.update(inicio=time.time(), muertos=0, golpes=0, revividas=0)
        # ★ con varios: la largada (0x105E) recién cuando cargaron TODOS, y a todos juntos
        s = SALAS.get(p.get("sala"))
        if s and len(s["miembros"]) > 1:
            s.setdefault("cargados", set()).add(conexion)
            if set(s["miembros"]) <= s["cargados"]:
                return [(0x105E, struct.pack("<HI", 1, 600), 0, n) for n in s["miembros"]]
            return []
        return [(0x105E, struct.pack("<HI", 1, 600), 0)]
    if cmd == 0x1061:                                       # un NPC muerto [§5.11]
        p["muertos"] += 1
        return []
    if cmd == 0x1063:                                       # 🟡 le pegaron (sale en la pelea)
        p["golpes"] += 1
        return []
    if cmd == 0x1001:                                       # «estoy vivo», cada 20 s [§5.3]
        # ★ el único momento en que el server puede hablar sin que le pregunten (el espía sólo
        #   contesta): acá sale lo que quedó pendiente por TIEMPO, p. ej. el game over
        r = [(0x1001, b"\x80", 0)]
        if p.get("game_over_en") and time.time() >= p["game_over_en"]:
            # (con un espía viejo, sin `tick`: sale con el «estoy vivo», hasta 20 s tarde)
            r += [x[:3] for x in game_over(c, p, conexion)]
        if os.path.exists(EMPUJAR):
            try:
                for c_hex, cuerpo_hex in json.load(open(EMPUJAR, encoding="utf-8")):
                    r.append((int(c_hex, 16), bytes.fromhex(cuerpo_hex), 0))
            finally:
                os.remove(EMPUJAR)
        return r
    if cmd == 0x1065:                                       # murió [§5.12]
        # al vencer el tiempo para revivir el cliente NO manda nada (medido 15:19): el game over
        # lo da el server (0x1069, 🟡) si no llegó el «sí» (0x106A) a tiempo
        p["game_over_en"] = time.time() + 15.5
        return [(0x1068, struct.pack("<I", 15000), 0)]
    if cmd == 0x106A:                                       # ¿usar moneda?
        p["game_over_en"] = None
        si = len(cuerpo) >= 2 and cuerpo[1] == 1 and c["monedas"] > 0
        if si:
            c["monedas"] -= 1
            p["revividas"] += 1
            guardar(c)
        r = [(0x106B, struct.pack("<HBHB", 1, 1 if si else 0, c["monedas"], 0), 0)]
        if not si:
            # «Cancel» o sin monedas: modo 0 = espectador (estado 0xA) → como el game over, al
            # lobby a los 6 s (🟡 con un solo jugador; con más, seguiría mirando)
            c["partidas"] += 1
            guardar(c)
            r.append((0x1075, struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"],
                                          nivel(c["exp"]), c["exp"], 0, 0), 6000))
        return r
    if cmd == 0x1064:                                       # ★ la stage terminó [§5.13, §5.14]
        ms = int((time.time() - (p["inicio"] or time.time())) * 1000)
        # ★ el premio sale del XML del escenario (RANK_POINT, KILL_POINT, TOTALEXP, MONSTER_CNT,
        #   RANKRATE). 🟡 CÓMO los combinaba Softnyx no se sabe: acá, proporcional a los NPC muertos
        rp, kp, te, mc = ESCENARIOS.get(p["escenario"], ESCENARIOS[1011])
        frac = min(1.0, p["muertos"] / float(mc))
        exp_ganada = max(1, int(round(te * frac)))
        plata_ganada = 100 + 10 * p["muertos"]              # 🟡 la plata: inventada
        rango_xml = next((5 - i for i, corte in enumerate(RANKRATE) if frac >= corte), 1)
        antes = nivel(c["exp"])
        c["exp"] += exp_ganada
        c["plata"] += plata_ganada
        c["partidas"] += 1
        if p["escenario"] not in c["terminadas"]:
            c["terminadas"].append(p["escenario"])
        # ★ el PREMIO de StageReward.xml: va en el PlayEnd (N1 × ítem de 21 B, con la ficha
        #   pegada si es equipo: +0x11 = −1, `0x548C54`) y entra a la bolsa
        nuevos = dar_premio(c, p["escenario"])
        p["premio"] = [it[0] for it in nuevos]
        guardar(c)
        n = nivel(c["exp"])
        p["puntos"] = puntos_de(te, frac)
        extra = os.path.join(RAIZ, "_trabajo", "servidor", "puntos_extra")   # (para probar a mano)
        if os.path.exists(extra):
            p["puntos"] += int(open(extra).read().strip() or 0)
        rango = rango_xml                                   # 1 = D (medido) … 5 = S (supuesto)
        regs = b"".join(b"".join(registro_item(it[3], it[0], it[1], it[2], it[4], pegada=True))
                        for it in nuevos)
        fin = (struct.pack("<HHIIHB", 1, c["monedas"], c["plata"], c["exp"], 0, n)
               + struct.pack("<IIBB", 0, p["escenario"], 1, 1) + bytes([len(nuevos), 0, 0])
               + regs + bytes([0]))
        resultado = struct.pack("<IHHHIIB", 0, p["muertos"], p["golpes"], p["revividas"], ms,
                                p["puntos"], rango)
        cartas = struct.pack("<IIII", 60000, *PRECIOS)
        p["cartas_hasta"] = time.time() + 8 + 60 + 2          # 0x106F a los 8 s + 60 s + margen
        p["exp_cartas"] = 0
        if n > antes:
            print("sube de nivel", antes, "→", n)
        # ★ el resultado y las cartas ESPACIADOS (juntos, las cartas tapaban el resultado)
        return [(0x1073, fin, 0), (0x106E, resultado, 300), (0x106F, cartas, 8000)]
    if cmd == 0x1070 and len(cuerpo) >= 2:                  # eligió una carta: u8 fila · u8 carta
        # ★ 0x1071 (`0x546B70`, 11 B): u8 1 · u8 FILA (la animación, `0x5095F0`) · u8 JUGADOR ·
        #   u32 EXP ganada con cartas (acumulada → `0x612AC0`; la carta muestra la diferencia) ·
        #   u32 puntos que QUEDAN (→ +0x251). ⚠ Antes iba el número de CARTA donde va el jugador:
        #   el cliente lo compara con el suyo (cuenta+0x705) y, distinto, NO da vuelta la carta
        #   (El tester, 19:55: «la tarjeta no se volteó»).
        #   🟡 Cuánta EXP da una carta no se sabe: acá, lo que costó (350 / 150 / 50).
        # ⚠ el 0x1070 es u8 · u8 CARTA numerada de corrido (oro 0–3, plata 4–9, bronce 10–17;
        #   medido 20:00: la 1ª de oro = «00 00», la 1ª de bronce = «00 0a») → la fila como la
        #   saca el cliente (`0x500810`). Antes se tomaba el 1er byte como fila: siempre «oro».
        carta_n = cuerpo[1]
        fila = 0 if carta_n < 4 else (1 if carta_n < 10 else 2)
        precio = PRECIOS[fila]
        if p.get("puntos", 0) >= precio:
            p["puntos"] -= precio
            p["exp_cartas"] = p.get("exp_cartas", 0) + precio
            c["exp"] += precio
            guardar(c)
        carta = struct.pack("<BBBII", 1, fila, numero_jugador(conexion), p.get("exp_cartas", 0),
                            p.get("puntos", 0))
        r = [(0x1071, carta, 0)]
        if p.get("puntos", 0) < min(PRECIOS):               # ya no alcanza para otra carta
            p["cartas_hasta"] = None
            r.append((0x1072, cuerpo_1072(conexion, p), 1500))
        return r
    if cmd == 0x1074:                                       # salió de la stage [§5.15]
        c["abandonos"] += 1
        c["partidas"] += 1
        guardar(c)
        salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                             c["exp"], 0, 0)
        return [(0x1075, salida, 0)]
    return None


def control():
    """Sin el juego: cada respuesta tiene que tener el largo que el cliente lee, y el estado
    tiene que cambiar como se espera. Con una cuenta aparte (no toca la de verdad)."""
    global CUENTAS, CUENTA
    import shutil
    ok = []

    def chequear(n, cond, d=""):
        print("  %s %s %s" % ("✅" if cond else "⛔", n, d))
        ok.append(bool(cond))
    CUENTAS = os.path.join(RAIZ, "_trabajo", "servidor", "cuentas_control")
    CUENTA = os.path.join(CUENTAS, "no_existe.json")
    shutil.rmtree(CUENTAS, ignore_errors=True)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    r = responder(0x1011, b"\1\0\0\0", 99)
    n_items = len(leer(99)["items"])
    chequear("0x1012 = 33 + (21 + 36) × %d ítems + 186 bytes" % n_items,
             len(r[0][1]) == 33 + 57 * n_items + 186, len(r[0][1]))
    chequear("N1 (cuántos ítems) en +0x1C", struct.unpack_from("<H", r[0][1], 0x1C)[0] == n_items)
    chequear("las monedas en cuerpo[0x17]", struct.unpack_from("<H", r[0][1], 0x17)[0] == 3)
    r = responder(0x106A, b"\0\1\xff", 99)
    chequear("revivir descuenta una moneda", leer(99)["monedas"] == 2 and r[0][0] == 0x106B)
    chequear("0x106B = 6 bytes, modo 1, quedan 2", r[0][1] == struct.pack("<HBHB", 1, 1, 2, 0))
    responder(0x106A, b"\0\1\xff", 99)
    responder(0x106A, b"\0\1\xff", 99)
    r = responder(0x106A, b"\0\1\xff", 99)
    chequear("★ el revés: sin monedas NO revive (modo 0)", r[0][1][2] == 0 and leer(99)["monedas"] == 0)
    responder(0x105F, b"\0" * 4, 99)
    for _ in range(10):
        responder(0x1061, b"\0" * 8, 99)
    r = responder(0x1064, b"\0", 99)
    cmds = [x[0] for x in r]
    chequear("0x1064 → 1073 + 106E + 106F", cmds == [0x1073, 0x106E, 0x106F], cmds)
    premio = partida(99).get("premio", [])
    largo = 29 + sum(21 + (36 if es_equipo(t) else 0) for t in premio)
    chequear("largos %d / 19 / 16 (29 + el premio %s)" % (largo, premio),
             [len(x[1]) for x in r] == [largo, 19, 16])
    chequear("N1 del PlayEnd (+25) = los ítems del premio", r[0][1][25] == len(premio))
    # el premio sale de StageReward.xml (si está): cada presente posible, de a uno
    tp = tabla_premios()
    if tp:
        for pres in tp[1011][1]:
            cc = {"items": [], "plata": 0}
            nuevos = dar_premio(cc, 1011, elegir=pres)
            bien = (nuevos == [] if pres[0] != 2 or pres[1] == NADA else
                    [n[:2] for n in nuevos] == [[pres[1], max(1, pres[2])]]
                    and nuevos[0][4] == (0 if 31000 <= pres[1] <= 33999 else 1))
            chequear("premio %s → %s" % (pres, [n[:2] + n[4:] for n in nuevos] or "nada"), bien)
    chequear("10 NPC muertos en el resultado", struct.unpack_from("<H", r[1][1], 4)[0] == 10)
    rp, kp, te, mc = ESCENARIOS[1011]
    esperada = max(1, int(round(te * 10 / float(mc))))        # del generador: la tabla del XML
    chequear("EXP = TOTALEXP × 10/56 = %d" % esperada, leer(99)["exp"] == esperada, leer(99)["exp"])
    chequear("la misión 1011 terminada", 1011 in leer(99)["terminadas"])
    chequear("nivel(299) = 1, nivel(300) = 2", nivel(299) == 1 and nivel(300) == 2)
    puntos = puntos_de(te, 10 / float(mc))
    chequear("con 10 de 56 NPC: %d puntos (proporcional, calibrado con el video)" % puntos,
             partida(99)["puntos"] == puntos)
    puntos = PRECIOS[2] + 30                                # alcanza para el bronce, no para otra
    partida(99)["puntos"] = puntos
    r = responder(0x1070, bytes.fromhex("000a"), 99)           # la 1ª de bronce, medida (20:00)
    chequear("carta de bronce: %d − %d puntos" % (puntos, PRECIOS[2]),
             struct.unpack_from("<I", r[0][1], 7)[0] == max(0, puntos - PRECIOS[2]))
    chequear("0x1071: u8 1 · FILA 2 · JUGADOR 0 (no la carta) · EXP de cartas %d" % PRECIOS[2],
             r[0][1][:3] == b"\1\2\0" and struct.unpack_from("<I", r[0][1], 3)[0] == PRECIOS[2])
    quedan = max(0, puntos - PRECIOS[2])
    hay_1072 = [x for x in r if x[0] == 0x1072]
    chequear("con %d puntos %s otra carta → %s 0x1072" % (
        quedan, "no alcanza para" if quedan < min(PRECIOS) else "alcanza para",
        "sale el" if quedan < min(PRECIOS) else "todavía no sale el"),
             bool(hay_1072) == (quedan < min(PRECIOS)))
    c1072 = cuerpo_1072(99, partida(99))
    chequear("0x1072 = el índice de la stage (1011) + (jugador 0, 1)",
             c1072 == struct.pack("<IBBB", 1011, 1, 0, 1), c1072.hex())
    for carta_n, fila_esperada in ((0, 0), (3, 0), (4, 1), (9, 1), (10, 2), (17, 2)):
        partida(99)["puntos"], partida(99)["exp_cartas"] = 1000, 0
        r = responder(0x1070, bytes([0, carta_n]), 99)
        chequear("carta %d → fila %d (cobra %d)" % (carta_n, fila_esperada, PRECIOS[fila_esperada]),
                 r[0][1][1] == fila_esperada
                 and struct.unpack_from("<I", r[0][1], 7)[0] == 1000 - PRECIOS[fila_esperada])
    antes_exp = leer(99)["exp"]
    partida(99)["puntos"] = PRECIOS[0] - 1
    r = responder(0x1070, b"\0\3", 99)
    chequear("★ el revés: sin puntos para la carta de oro NO da EXP",
             leer(99)["exp"] == antes_exp and struct.unpack_from("<I", r[0][1], 7)[0] == PRECIOS[0] - 1)
    tp2 = tabla_premios()
    if tp2:
        cc = {"items": [], "plata": 0, "exp": 0}
        dar_premio(cc, 1013)
        oro = sum(d for t_, d, _ in tp2[1013][1] if t_ == 0)
        exp_ = sum(d for t_, d, _ in tp2[1013][1] if t_ == 1)
        chequear("premio 1013 = Σ Type 0 → oro (%d), Σ Type 1 → EXP (%d), como `0x5FEA50/AA0`" % (oro, exp_),
                 cc["plata"] == oro and cc["exp"] == exp_)
    chequear("calibrado con el video: 1011 completa = 257 puntos", puntos_de(128, 1.0) == 257)
    sala = bytearray(0x59)
    struct.pack_into("<H", sala, 4, 0xFFFF)
    struct.pack_into("<I", sala, 0x28, 1012)
    r = responder(0x101D, b"\0\0\0\0" + bytes(sala), 98)
    chequear("0x101E = 94 B con la sala del cliente (1012) y número 1",
             len(r[0][1]) == 94 and struct.unpack_from("<I", r[0][1], 5 + 0x28)[0] == 1012
             and struct.unpack_from("<H", r[0][1], 5 + 4)[0] == 1, r[0][1][5 + 0x28:5 + 0x2C].hex())
    chequear("★ el revés: sin 0x101D, la partida queda en 1011", partida(97)["escenario"] == 1011)
    chequear("un comando desconocido → None (contestan las reglas)", responder(0x9999, b"", 99) is None)
    responder(0x1065, b"\0" * 5, 96)
    chequear("★ el revés: recién muerto, el «estoy vivo» NO trae game over",
             [x[0] for x in responder(0x1001, b"\xf0", 96)] == [0x1001])
    partida(96)["game_over_en"] = time.time() - 1
    r = responder(0x1001, b"\xf0", 96)
    chequear("vencido: 1001 + 1069 + 1075 (a los 6 s)",
             [(x[0], x[2]) for x in r] == [(0x1001, 0), (0x1069, 0), (0x1075, 6000)], r)
    responder(0x1065, b"\0" * 5, 95)
    responder(0x106A, b"\0\0\xff", 95)
    chequear("con respuesta al cuadro (aunque sea «no»), no hay game over por tiempo",
             partida(95)["game_over_en"] is None)
    # ★ multijugador: cada conexión su cuenta; al cerrarse, la cuenta queda libre
    PARTIDAS.clear()
    ASIGNADAS.clear()
    a, b = cuenta_de(201), cuenta_de(202)
    chequear("dos conexiones → dos cuentas distintas", (a, b) == ("rui", "kai"), (a, b))
    chequear("la misma conexión → la misma cuenta", cuenta_de(201) == "rui")
    cerrada(201)
    chequear("★ cerrada la 1ª, la conexión nueva toma «rui» (libre)", cuenta_de(203) == "rui")
    r = responder(0x1011, b"\1\0\0\0", 202)
    chequear("el personaje de la 2ª conexión se llama «kai»", b"k\0a\0i\0" in r[0][1] or b"kai" in r[0][1])
    # ★ INVENTARIO: el 0x102D que mandó el cliente de verdad (18:40, las 8 piezas de Warrior
    #   equipadas con clic derecho), + un serial que no existe (99) que se tiene que ignorar
    real = bytes.fromhex("0000000068a38900000000000000000000000000080000000000010000000a02000000"
                         "0b030000000004000000040500000006060000000807000000010800000009")
    medido = dict(struct.unpack_from("<IB", real, 26 + 5 * k) for k in range(8))
    falso = bytearray(real) + struct.pack("<IB", 99, 3)
    struct.pack_into("<H", falso, 20, 9)
    antes = leer(203)
    r = responder(0x102D, bytes(falso), 203)
    d = leer(203)
    chequear("0x102D → 0x102E, modo 3 (lobby)", r[0][0] == 0x102E and r[0][1][:3] == b"\1\0\3")
    chequear("0x102E = 3 + 8 + 16 + 76 + 2 + 8 × 6 + 2", len(r[0][1]) == 3 + 8 + 16 + 76 + 2 + 48 + 2,
             len(r[0][1]))
    chequear("cada serial quedó en el casillero que mandó el cliente",
             all(d["items"][s - 1][2] == k for s, k in medido.items()))
    chequear("★ el revés: el 201 (Hunter, serial 9) no se movió: sigue en la bolsa",
             d["items"][8][2] == casilleros_de(antes["items"])[8] >= 18)
    chequear("★ el revés: el serial 99 no existe → ignorado (8 confirmados, no 9)",
             struct.unpack_from("<H", r[0][1], 3 + 8 + 16 + 76)[0] == 8)
    # el equipo (18 u32) del generador = el que midió Frida en el cliente: 1..8 y nada más
    chequear("el EQUIPO = lo medido en el cliente (1 2 3 4 5 6 7 8 0…)",
             equipo(d) == list(range(1, 9)) + [0] * 10, equipo(d))
    chequear("y va en el personaje del 0x1012 (+0x72)",
             responder(0x1011, b"\1\0\0\0", 203)[0][1][-0xBA + 0x72:][:8] == struct.pack("<2I", 1, 2))
    # ★ TIENDA: el 0x103F de verdad (18:48, «Basic Long Sword» = producto 1). El precio y el ítem
    #   salen de Product.xml (el generador), no se escriben acá
    tabla = productos()
    if not tabla:
        chequear("Product.xml (py herramientas\\sacar_xml.py SHOP Product)", False, PRODUCTOS_XML)
    else:
        precio, _, dan = tabla[1]
        antes = leer(203)
        r = responder(0x103F, bytes.fromhex("00000000010100"), 203)
        d = leer(203)
        chequear("0x103F producto 1 → 0x1040 resultado 1", r[0][0] == 0x1040 and r[0][1][:2] == b"\1\0")
        chequear("se cobra el precio de Product.xml (%d)" % precio,
                 d["plata"] == antes["plata"] - precio and
                 struct.unpack_from("<I", r[0][1], 2)[0] == d["plata"])
        chequear("y da su ítem %s en la bolsa" % (dan,),
                 [it[:2] for it in d["items"][len(antes["items"]):]] == [list(x) for x in dan]
                 and d["items"][-1][2] >= 18)
        chequear("0x1040 = 15 + 2 + 21 + 36 (equipo: con ficha)", len(r[0][1]) == 15 + 2 + 21 + 36,
                 len(r[0][1]))
        d["plata"] = precio - 1
        guardar(d)
        r = responder(0x103F, bytes.fromhex("00000000010100"), 203)
        chequear("★ el revés: sin oro → resultado 0 y no cobra", r[0][1][:2] == b"\0\0"
                 and leer(203)["plata"] == precio - 1)
        r = responder(0x103F, bytes.fromhex("000000000134ff"), 203)
        chequear("★ el revés: un producto que no existe → resultado 0", r[0][1][:2] == b"\0\0")
        # ★ VENDER: la espada comprada (último serial). Precio del generador (BuyItem)
        d = leer(203)
        inv = inventario(d)
        vendida = inv[-1]
        venta = precios_venta()[vendida[0]]
        r = responder(0x1041, struct.pack("<II", 0, vendida[3]), 203)
        d2 = leer(203)
        chequear("0x1041 → 0x1042 = u16 1 · serial · oro · 1 (11 B)",
                 r[0][1] == struct.pack("<HIIB", 1, vendida[3], d["plata"] + venta, 1), r[0][1].hex())
        chequear("paga %d (BuyGold) y el ítem ya no está" % venta,
                 d2["plata"] == d["plata"] + venta and vendida[3] not in [x[3] for x in inventario(d2)])
        # vender uno del MEDIO (el 201 de Hunter, serial 9): los de después NO cambian de serial
        despues = [x for x in inventario(d2) if x[3] > 9]
        responder(0x1041, struct.pack("<II", 0, 9), 203)
        d3 = leer(203)
        chequear("★ vendido uno del medio, los demás conservan su serial",
                 [x for x in inventario(d3) if x[3] > 9] == despues and despues)
        equipado = next(x for x in inventario(d3) if x[2] < 12)
        r = responder(0x1041, struct.pack("<II", 0, equipado[3]), 203)
        chequear("★ el revés: lo que está PUESTO no se vende", r[0][1][:2] == b"\0\0"
                 and leer(203)["plata"] == d3["plata"])
        r = responder(0x1041, struct.pack("<II", 0, 777), 203)
        chequear("★ el revés: un serial que no existe → resultado 0", r[0][1][:2] == b"\0\0")
    # ★ MODO RELAY: con la bandera, identidad inventada + dirección del relay; sin ella, lo de antes
    global RELAY_BANDERA, RELAY_MAPA
    bandera_real, mapa_real = RELAY_BANDERA, RELAY_MAPA
    RELAY_BANDERA = os.path.join(CUENTAS, "modo_relay")
    RELAY_MAPA = os.path.join(CUENTAS, "relay.json")
    chequear("★ el revés: sin bandera, sin relay (identidad = la local)", relay() is None
             and identidad_de(5) != identidad_falsa(5) and dir_udp(5) == partida(5).get("udp"))
    open(RELAY_BANDERA, "w").close()
    m = miembro(leer(203), 0, conexion=203)
    chequear("con bandera: identidad inventada en +0xA del miembro",
             m[0xA:0xA + 34] == identidad_falsa(203).encode("utf-16-le"))
    chequear("y la dirección = su puerto en el relay (127.0.0.1:%d)" % (RELAY_BASE + 1 + 203),
             struct.unpack_from("<IH", m, 0x48) == (0x7F000001, RELAY_BASE + 1 + 203))
    r = responder(0x100F, bytes(0xE9), 203)
    chequear("el 0x1010 manda el punch al RELAY", r[0][1][-6:] == struct.pack("<IH", 0x7F000001, RELAY_BASE))
    chequear("y escribe relay.json para el relay",
             json.load(open(RELAY_MAPA)).get("203", {}).get("falsa") == identidad_falsa(203))
    chequear("el 0x1012 lleva la conexión en +6 (el id del 0x3006)",
             struct.unpack_from("<I", responder(0x1011, b"\1\0\0\0", 203)[0][1], 6)[0] == 203)
    RELAY_BANDERA, RELAY_MAPA = bandera_real, mapa_real
    # ★ CREATE SOCKET (el 0x1037 de verdad: ítem 11, taladro 12)
    d = leer(203)
    inv = inventario(d)
    s = serial_nuevo(inv)
    inv += [[2, 1, libre_en_bolsa(inv), s, 1]]
    inv += [[40001, 2, libre_en_bolsa(inv), s + 1, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    chequear("0x1037 → 0x1038 de 46 B, resultado 1, queda 1 taladro",
             len(r[0][1]) == 46 and struct.unpack_from("<HIi", r[0][1]) == (1, s + 1, 1))
    niv = struct.unpack_from("<I", r[0][1], 10 + 0x20)[0]
    chequear("la ficha nueva: el ítem %d con el engarce 0 ABIERTO (3 bits ≠ 0) y sin piedra" % s,
             struct.unpack_from("<I", r[0][1], 10 + 4)[0] == s and nivel_engarce(niv, 0) == 1
             and nivel_engarce(niv, 1) == 0
             and struct.unpack_from("<10H", r[0][1], 10 + 12) == (0,) * 10)
    responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    niv = leer(203)["fichas"][str(s)]["niveles"]
    chequear("un 2º taladro: 2 engarces abiertos, y el taladro se acaba",
             [nivel_engarce(niv, i) for i in range(3)] == [1, 1, 0]
             and not any(x[3] == s + 1 for x in inventario(leer(203))))
    r = responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    chequear("★ el revés: sin taladro → resultado 0 y sin engarce nuevo", r[0][1][:2] == b"\0\0"
             and nivel_engarce(leer(203)["fichas"][str(s)]["niveles"], 2) == 0)
    # ★ ENCHANT: una piedra (21001) en el engarce 0 (el 0x1033 medido: ítem, N 1, engarce 0, piedra)
    d = leer(203)
    inv = inventario(d)
    ps = serial_nuevo(inv)
    inv += [[21001, 1, libre_en_bolsa(inv), ps, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 0, ps), 203)
    chequear("0x1033 → 0x1034 = 7 + 20 + 4 B: la piedra 21001 en el engarce 0, y se gasta",
             len(r[0][1]) == 31 and struct.unpack_from("<HIB", r[0][1]) == (1, s, 1)
             and struct.unpack_from("<H", r[0][1], 7)[0] == 21001
             and struct.unpack_from("<I", r[0][1], 27)[0] == ps
             and not any(x[3] == ps for x in inventario(leer(203))))
    inv = inventario(leer(203))
    d = leer(203)
    d["items"] = inv + [[21002, 1, libre_en_bolsa(inv), ps + 1, 1]]
    guardar(d)
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 0, ps + 1), 203)
    chequear("★ el revés: un engarce YA ocupado no se pisa (y la piedra no se gasta)",
             r[0][1][:2] == b"\0\0" and any(x[3] == ps + 1 for x in inventario(leer(203))))
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 5, ps + 1), 203)
    chequear("★ el revés: un engarce CERRADO (el 5) no acepta piedra", r[0][1][:2] == b"\0\0")
    # ★ REPAIR: los dos ítems gastados de la medición (75 % del tipo 1, 50 % del tipo 2) → 22500
    tt = tipos_item()
    if tt:
        d = leer(203)
        inv = inventario(d)
        w = serial_nuevo(inv)
        inv += [[1, 1, libre_en_bolsa(inv), w, 1]]
        inv += [[2, 1, libre_en_bolsa(inv), w + 1, 1]]
        d["items"], d["plata"] = inv, 30000
        d["durabilidad"] = {str(w): 7500, str(w + 1): 5000}
        guardar(d)
        esperado = (tt[1][0] - 7500) * tt[1][1] + (tt[2][0] - 5000) * tt[2][1]
        r = responder(0x1039, struct.pack("<IH", 0x186, 1), 203)
        chequear("Repair All cobra %d (como el cliente) y deja las dos al 100 %%" % esperado,
                 esperado == 22500 and struct.unpack_from("<HIB", r[0][1]) == (1, 30000 - esperado, 2)
                 and leer(203)["durabilidad"] == {str(w): 10000, str(w + 1): 10000})
        r = responder(0x1039, struct.pack("<IH", 0x186, 1), 203)
        chequear("★ el revés: con todo sano no hay nada que arreglar → resultado 0",
                 r[0][1][:2] == b"\0\0" and leer(203)["plata"] == 30000 - esperado)
    # ★ REFINE SPIRIT STONE: Phase (3 × 21001 → 21021) y Level (2 × 21001 → 21002)
    d = leer(203)
    inv = inventario(d)
    q = serial_nuevo(inv)
    for k in range(5):
        inv += [[21001, 1, libre_en_bolsa(inv), q + k, 1]]
    d["items"] = inv
    guardar(d)
    habia = [x[0] for x in inv].count(21001)
    r = responder(0x1035, struct.pack("<IB3I", 0x182, 0, q, q + 1, q + 2), 203)
    chequear("Phase: 3 × 21001 → 0x1036 con una 21021 nueva y las 3 gastadas (25 + 12 B)",
             len(r[0][1]) == 37 and r[0][1][:3] == b"\1\0\0"
             and struct.unpack_from("<H", r[0][1], 3 + 8)[0] == 21021
             and [x[0] for x in inventario(leer(203))].count(21001) == habia - 3)
    r = responder(0x1035, struct.pack("<IB2I", 0x182, 1, q + 3, q + 4), 203)
    chequear("Level: 2 × 21001 → una 21002", struct.unpack_from("<H", r[0][1], 3 + 8)[0] == 21002
             and [x[0] for x in inventario(leer(203))].count(21001) == habia - 5)
    nueva = next(x for x in inventario(leer(203)) if x[0] == 21002)
    otra = next(x for x in inventario(leer(203)) if x[0] == 21021)
    r = responder(0x1035, struct.pack("<IB2I", 0x182, 1, nueva[3], otra[3]), 203)
    chequear("★ el revés: dos piedras DISTINTAS no se refinan (y no se gastan)",
             r[0][1][:2] == b"\0\0" and any(x[3] == nueva[3] for x in inventario(leer(203))))
    chequear("y la ficha va en el 0x1012 con sus engarces",
             ficha(leer(203), s) in responder(0x1011, b"\1\0\0\0", 203)[0][1])
    # ★ BORRAR HABILIDAD
    d = leer(203)
    d["habilidades"] = [[1000, 1, 1, 0, 1], [1001, 1, 3, 1, 2]]
    guardar(d)
    r = responder(0x1043, struct.pack("<II", 0x174, 1000), 203)
    chequear("0x1043 clave 1000 → 0x1044 (1, 1000) y queda sólo la otra",
             r[0] == (0x1044, struct.pack("<HI", 1, 1000), 0)
             and [h[0] for h in leer(203)["habilidades"]] == [1001])
    r = responder(0x1043, struct.pack("<II", 0x174, 1000), 203)
    chequear("★ el revés: una clave que no tiene → resultado 0", r[0][1][:2] == b"\0\0")
    d = leer(203)
    d["habilidades"] = []                                   # (las pruebas de aprender empiezan sin)
    guardar(d)
    # ★ PUNTOS DE ESTADÍSTICA: los libres salen del nivel; el reparto vuelve en el 0x102D
    d = leer(203)
    d["exp"], d["stats"] = EXPS[9], [0, 0, 0, 0, 0]          # nivel 10
    guardar(d)
    libres = PUNTOS_POR_NIVEL * 9
    chequear("nivel 10 → %d puntos libres en +0x6C del personaje" % libres,
             struct.unpack_from("<H", pj_cuenta(leer(203)), 0x6C)[0] == libres)

    def reparto(st):
        return (b"\0" * 4 + struct.pack("<I6H", 0x89A368, *st) + struct.pack("<HHH", 0, 0, 0))
    # el 0x102D de verdad (21:10): 5 Str, 3 Con, y 8 = los gastados en la tanda
    responder(0x102D, reparto([5, 3, 0, 0, 0, 8]), 203)
    chequear("un reparto que cuadra se guarda (5 Str, 3 Con; 8 gastados)",
             leer(203)["stats"] == [5, 3, 0, 0, 0] and stats_de(leer(203))[5] == libres - 8)
    responder(0x102D, reparto([5, 3, 2, 0, 0, 2]), 203)
    chequear("una 2ª tanda (+2 Dex) suma", leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([50, 3, 2, 0, 0, 45]), 203)
    chequear("★ el revés: pedir más puntos de los que hay NO se guarda",
             leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([0, 3, 7, 0, 0, 0]), 203)
    chequear("★ el revés: BAJAR uno ya repartido no se guarda", leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([6, 3, 2, 0, 0, 5]), 203)
    chequear("★ el revés: los gastados no coinciden con lo que subió → no se guarda",
             leer(203)["stats"] == [5, 3, 2, 0, 0])
    # ★ READY con 3: el 0x1047 de mio (jugador 2) es «02 01» → estado 1 para los demás
    SALAS[77] = {"sala": bytes(0x59), "anfitrion": 301, "miembros": [301, 302, 303]}
    partida(303)["sala"] = 77
    r = responder(0x1047, b"\2\1", 303)
    chequear("0x1047 «02 01» (jugador 2, listo) → 0x1058 (2, tipo 1, estado 1) a los otros dos",
             sorted(x[3] for x in r if x[0] == 0x1058) == [301, 302]
             and all(x[1] == struct.pack("<BHB", 2, 1, 1) for x in r if x[0] == 0x1058))
    del SALAS[77]
    # ★ SALIR DE SALA Y MIGRACIÓN DE ANFITRIÓN
    SALAS[77] = {"sala": bytes(0x59), "anfitrion": 301, "miembros": [301, 302, 303]}
    partida(301)["sala"] = 77
    partida(302)["sala"] = 77
    partida(303)["sala"] = 77
    r = responder(0x1045, b"", 301)
    chequear("0x1045 devuelve 0x1046 al saliente", any(x[0] == 0x1046 for x in r))
    chequear("el anfitrión migra a 302 y 0x1058 (tipo 3, nuevo anfitrión 0) se envía a los otros",
             SALAS[77]["anfitrion"] == 302 and
             any(x[0] == 0x1058 and x[1] == struct.pack("<BHB", 0, 3, 0) and x[3] == 302 for x in r))
    # ★ EXPULSIÓN DE LA SALA (Kick 0x1051)
    r = responder(0x1051, b"\x01", 302)
    chequear("0x1051 envía 0x1052 al anfitrión", any(x[0] == 0x1052 for x in r))
    chequear("0x1051 envía 0x1054 al expulsado 303", any(x[0] == 0x1054 and x[3] == 303 for x in r))
    chequear("303 queda sin sala y SALAS[77] sólo tiene [302]",
             partida(303).get("sala") is None and SALAS[77]["miembros"] == [302])
    del SALAS[77]
    chequear("sala → Inventory: 0x104C → 0x104D (u16 1 · u8)",
             responder(0x104C, b"\0", 203) == [(0x104D, b"\1\0\0", 0)])
    # ★ VERIFICAR un libro de habilidad (el 0x103B de verdad: libro 14, pergamino 13)
    d = leer(203)
    inv = inventario(d)
    s = serial_nuevo(inv)
    inv += [[32001, 1, libre_en_bolsa(inv), s, 0]]
    inv += [[40051, 2, libre_en_bolsa(inv), s + 1, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x103B, struct.pack("<III", 0, s, s + 1), 203)
    d = leer(203)
    libro = next(x for x in inventario(d) if x[3] == s)
    chequear("0x103B → 0x103C de 31 B, resultado 1, queda 1 pergamino",
             len(r[0][1]) == 31 and struct.unpack_from("<HIi", r[0][1]) == (1, s + 1, 1))
    chequear("el libro queda VERIFICADO (+0xE = 1, en la cuenta y en el registro)",
             libro[4] == 1 and r[0][1][10 + 0xE] == 1 and struct.unpack_from("<H", r[0][1], 18)[0] == 32001)
    r = responder(0x103B, struct.pack("<III", 0, s, s + 1), 203)
    chequear("★ el revés: un libro YA verificado no se vuelve a verificar (ni gasta pergamino)",
             r[0][1][:2] == b"\0\0" and next(x for x in inventario(leer(203)) if x[3] == s + 1)[1] == 1)
    # ★ APRENDER: el libro verificado (Dash). Precio y nivel salen de Skill.xml (el generador)
    th = tabla_habilidades()
    if not th:
        chequear("Skill.xml (py herramientas\\sacar_xml.py SKILLXML Skill)", False, HABILIDADES_XML)
    else:
        tipo_h, ident, _, costo, nivel_min = th[32001]
        d = leer(203)
        d["exp"], d["plata"] = EXPS[nivel_min - 2], 100000             # un nivel MENOS que el pedido
        guardar(d)
        r = responder(0x103D, struct.pack("<IIHH", 0, s, 0, 0), 203)
        chequear("★ el revés: con nivel %d (< %d) NO aprende" % (nivel_min - 1, nivel_min),
                 r[0][1][:2] == b"\0\0" and not leer(203).get("habilidades"))
        d = leer(203)
        d["exp"] = EXPS[nivel_min - 1]
        guardar(d)
        r = responder(0x103D, struct.pack("<IIHH", 0, s, 0, 0), 203)
        d = leer(203)
        chequear("0x103D → 0x103E de 15 + 13 + 2 B, resultado 1", len(r[0][1]) == 30
                 and r[0][1][:2] == b"\1\0", len(r[0][1]))
        chequear("cobra %d (COST_GOLD) y el libro sale de la bolsa" % costo,
                 d["plata"] == 100000 - costo and s not in [x[3] for x in inventario(d)])
        chequear("el ORO en +3 y el serial del libro en +7 (como los lee 0x54CCC1 / 0x54CCD0)",
                 struct.unpack_from("<II", r[0][1], 3) == (d["plata"], s))
        chequear("la habilidad: activa, ID %d" % ident,
                 struct.unpack_from("<IBH", r[0][1], 15 + 4) == (s, tipo_h, ident))
        r = responder(0x1017, b"", 203)
        chequear("y viene en el 0x1018 (N2 = 1, 13 B al final)",
                 struct.unpack_from("<H", r[0][1], 7)[0] == 1 and r[0][1][-13:] == obj_habilidad(d["habilidades"][0]))
    PARTIDAS.clear()
    ASIGNADAS.clear()
    shutil.rmtree(CUENTAS, ignore_errors=True)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


# El casillero de EQUIPO de cada familia de ítem (medido con el 0x102D, MEDICIONES §27)
CASILLERO_PARTE = {0: 10, 1: 11, 3: 0, 4: 4, 5: 6, 6: 8, 7: 1, 8: 9}


def preparar(nombre, clase, nivel_pedido):
    """🟡 Una cuenta DE PRUEBA: nivel pedido, el set de grado 1 de su clase PUESTO (Warrior 1, 1001,
    3001…; Hunter 201, 1201, 3201…), todas las habilidades de su clase (y las de todas) que su nivel
    permite, con las de ESPADA (WEAPON 0) en los atajos F1–F8. Pisa la cuenta."""
    os.makedirs(CUENTAS, exist_ok=True)
    c = dict(INICIO, nombre=nombre, clase=clase, exp=EXPS[nivel_pedido - 1], plata=100000)
    base = 0 if clase == 1 else 200
    items = []
    for familia, cas in CASILLERO_PARTE.items():
        tipo = familia * 1000 + base + 1 if familia else base + 1
        items.append([tipo, 1, cas, len(items) + 1, 1])
    items.append([26001, 20, 18, len(items) + 1, 1])
    c["items"] = items
    x = open(HABILIDADES_XML, "rb").read()
    habs, atajo = [], 1
    filas = []
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        if int(v[b"CLASS"]) in (clase, 65535) and int(v[b"ACQUIRE_LEVEL"]) <= nivel_pedido:
            filas.append((clase_xml == b"ACTIVE", int(v.get(b"WEAPON", b"9")), int(v[b"ACQUIRE_LEVEL"]),
                          int(v[b"ID"])))
    for activa, arma, _, ident in sorted(filas, key=lambda f: (not f[0], f[1], f[2])):
        a = atajo if activa and atajo <= 8 else 0
        atajo += 1 if a else 0
        habs.append([1000 + len(habs), 1 if activa else 2, ident, len(habs), a])
    c["habilidades"] = habs
    c["lugares_habilidad"] = max(12, len(habs))
    guardar(c)
    return c


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    if sys.argv[1:2] == ["preparar"]:
        # py servidor\juego.py preparar <nombre> <1 Warrior | 2 Hunter> <nivel>
        cc = preparar(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
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
        sys.exit(control())
