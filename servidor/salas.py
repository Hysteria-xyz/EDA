r"""servidor/salas.py -- el LOBBY y las SALAS: listas, entrar, crear, chat, listo y largar.
"""
import struct

from servidor.config import P
from servidor.registro import maneja
from servidor.estado import ASIGNADAS, SALAS, partida
from servidor.cuentas import leer, nivel
from servidor.objetos import equipo_tipos, obj_habilidad, personaje_obj
from servidor.relay import dir_udp, identidad_de


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


def miembro(c, indice, completo=False, conexion=None, para=None):
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
    udp = dir_udp(conexion, para)                          # (la dirección depende de QUIÉN la recibe)
    if ident:
        # ★ +0xA (texto ancho, hasta +0x48): la IDENTIDAD P2P del jugador. La capa UDP guarda a
        #   cada par por el texto que él manda en su saludo `0xC354` (su MAC «XX:XX:…»), y el ping
        #   de la sala lo busca con este campo (`0x5374A0` → `0x623070` → `0x748120`): vacío →
        #   -1 → «-1000 ms». ★ Es la MAC que mandó en su 0x100F (MEDICIONES §39); sin ella, la
        #   inventada del relay (`relay.identidad_de`).
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
    durante 2 s para conectarse. ★ Cada dirección se elige PARA quien la recibe (`relay.dir_udp`):
    la pública que vio el punch, la privada si comparten IP pública, o el relay."""
    # ⚠ a cada uno SÓLO los OTROS: el cliente busca cada id en su lista de miembros (`0x61C140`)
    #   y el jugador local no está ahí → puntero nulo → se cae (medido 17:09: los DOS en 0x550CAC)
    r = []
    for dest in s["miembros"]:
        regs = []
        for i, n in enumerate(s["miembros"]):
            udp = dir_udp(n, dest)
            if udp and n != dest:
                # ⚠ la IP y el puerto como ENTEROS (little-endian), igual que en el 0x1010: el
                #   cliente les hace htonl/htons (`[0x88A55C]`, la misma que en `0x6218F0`). En
                #   orden de red imprimía «1.0.0.127» y saludaba (0xC354) a una dirección que no
                #   existe (medido 17:25)
                regs.append(struct.pack("<BIH", i, udp[0], udp[1]))
        cuerpo = struct.pack("<B4xBB", len(regs), 0, 0) + b"".join(regs)
        r.append((0x1059, cuerpo, espera, dest))
    return r


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


@maneja(0x101F)
def entrar_sala(cmd, cuerpo, conexion, c, p):
    """★ ENTRAR a una sala (Enter)"""
    if not (len(cuerpo) >= 6):
        return None
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
                + b"".join(miembro(leer(n), s["miembros"].index(n), conexion=n, para=conexion)
                            for n in otros))
    # al anfitrión (y los demás de la sala): 0x1057 (`0x54F020`, 0x377 B) = u8 → +0x272 ·
    #   u8 → +0x271 (estado de la sala) · vt 0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · el
    #   miembro NUEVO completo (0x36F) — uno por destinatario (su dirección depende de quién la ve)
    def aviso(para):
        return (struct.pack("<BBIBB", 0, 0, 0x89A3B8, 0, 0)
                + miembro(c, yo, completo=True, conexion=conexion, para=para))
    return ([(0x1020, cuerpo20, 0)] + [(0x1057, aviso(n), 0, n) for n in otros]
            + pares(s, 500) + avisar_lista(salvo=conexion))


@maneja(0x1047)
def listo(cmd, cuerpo, conexion, c, p):
    """★ F9 READY (el que no es anfitrión)"""
    if not (len(cuerpo) >= 1):
        return None
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


@maneja(0x100D)
def chat(cmd, cuerpo, conexion, c, p):
    """★ CHAT (lobby / sala)"""
    if not (len(cuerpo) >= 13):
        return None
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


@maneja(0x1023)
def a_seleccion(cmd, cuerpo, conexion, c, p):
    """lobby → «Select Character»"""
    # ★ el cliente espera 0x1024 (`0x5424A0`): u16 1 → pantalla 2 = SELECT CHARACTER
    return [(0x1024, struct.pack("<H", 1), 0)]


@maneja(0x1027)
def a_tienda(cmd, cuerpo, conexion, c, p):
    """lobby → «Shop» (u32 · u8)"""
    # ★ 0x1028 (`0x542660`): u16 1 → pantalla 6 (🟡 la tienda)
    return [(0x1028, struct.pack("<H", 1), 0)]


@maneja(0x104C)
def sala_a_inventario(cmd, cuerpo, conexion, c, p):
    """sala → «Inventory» (u8)"""
    # ★ 0x104D (`0x54ECF0`): u16 1 · u8 → cuenta+0x2DE → pantalla 6 (medido 19:24: sin
    #   respuesta, «Waiting for Response from Server»)
    return [(0x104D, struct.pack("<HB", 1, 0), 0)]


@maneja(0x1017)
def entrar_lobby(cmd, cuerpo, conexion, c, p):
    """ENTER LOBBY [§5.7]"""
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


@maneja(0x101D)
def crear_sala(cmd, cuerpo, conexion, c, p):
    """crear sala [§5.8]"""
    if not (len(cuerpo) >= 4 + 0x59):
        return None
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


@maneja(0x104E)
def largar(cmd, cuerpo, conexion, c, p):
    """★ F9 START GAME (el anfitrión)"""
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
