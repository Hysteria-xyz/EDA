r"""servidor/salas.py -- el LOBBY y las SALAS: listas, entrar, crear, chat, listo y largar.
"""
import os
import struct
import time

from servidor import config
from servidor.config import P
from servidor.registro import maneja
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO, partida, numero, dar_numero, de_numero
from servidor.cuentas import fijar_stats_personaje, leer, nivel, nombre_visible, guardar, EXPS, INICIO
from servidor.objetos import equipo_tipos, obj_habilidad, personaje_obj
from servidor import relay
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


def miembro(c, indice, completo=False, conexion=None, para=None, listo=False):
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
    pj = bytearray(P.registro_personaje(nombre_visible(c), lugar=0, clase=c["clase"], ident=c["exp"],
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
    # ★ (Punto 3) +0x322 = LISTO, como lo sabe el server: el anfitrión sólo larga si TODOS los de su
    #   lista tienen 1 acá y 0 en +0x323 (`0x61C170`, F9 = `0x534B20`); si no, el cartel 0x191
    #   «All users must be ready to start the game»
    m[0x322] = 1 if listo else 0
    if completo:
        ext = bytearray(0x43)
        struct.pack_into("<I", ext, 0, 0x89A398)
        for k in range(9):
            struct.pack_into("<I", ext, 4 + 7 * k, 0x89A394)
        m += ext
    return bytes(m)


# ★ (22-nov) En una sala que ESPERA (`jugando` en False), cada cuántos segundos sin 0x1059 se vuelve a mandar el
#   0x1059 (`+0x2DF = 3`, mismas direcciones) para que el cliente repita su medición (`0x550D6B` → `0x534D50` →
#   `0x535000` → `0x4DC330`) y mande `0x105A` si un NAT cambió de puerto y quedó en -1000 ms.
REMEDIR_SALA = float(os.environ.get("EDA_REMEDIR_SALA") or 60)


def pares(s, espera=0, anotar=True, ahora=None):
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
        for n in s["miembros"]:
            i = numero(s, n)
            udp = dir_udp(n, dest)
            if udp and n != dest:
                # ⚠ la IP y el puerto como ENTEROS (little-endian), igual que en el 0x1010: el
                #   cliente les hace htonl/htons (`[0x88A55C]`, la misma que en `0x6218F0`). En
                #   orden de red imprimía «1.0.0.127» y saludaba (0xC354) a una dirección que no
                #   existe (medido 17:25)
                regs.append(struct.pack("<BIH", i, udp[0], udp[1]))
                # ★ (MEDICIONES §53) qué camino le tocó a cada par, en el registro del server (sin la IP)
                if dest is not None and anotar:
                    camino = ("relay" if relay.relay() and udp[1] == config.RELAY_BASE + 1 + n
                              else "casa (privada)" if udp == tuple(partida(n).get("privada") or ())
                              else "directo (pública)")
                    print("sala: a #%s le doy #%s por %s" % (dest, n, camino), flush=True)
        # ★ (22-nov) +0x2DE = listo del destinatario (para no apagarle su botón Ready), y +0x2DF = 3:
        #   en el exe (`0x550D6B` → `0x534D50` → `0x535000` → `0x4DC330`), 1 s después de saludar por UDP
        #   mide si conectó con el anfitrión (`0x748120`) y manda `0x105A` (si sigue en -1000 ms, timeouts = 2)
        listo_dest = 1 if dest in s.get("listos", ()) else 0
        cuerpo = struct.pack("<B4xBB", len(regs), listo_dest, 3) + b"".join(regs)
        s.setdefault("anunciado", {})[dest] = b"".join(regs)         # (21-nov) lo último que se le dio: ver `reanunciar`
        r.append((0x1059, cuerpo, espera, dest))
    if anotar:
        s["anunciado_en"] = time.time() if ahora is None else ahora
    return r


def reanunciar(salas, ahora=None, por_tiempo=True):
    """★ (21-nov / 22-nov) Del `tick`: sólo en una sala que ESPERA (`jugando` en False; nunca durante la carga ni
    en plena stage):
      1) si la dirección de alguien cambió (su NAT le dio otro puerto, llegó su 0x3006 de esta sesión, o un par
         pasó al relay por 0x105A), se les vuelve a dar el 0x1059 a los que les cambió;
      2) si `por_tiempo` y pasaron más de `REMEDIR_SALA` s (60 s) desde el último 0x1059 de la sala, se les vuelve
         a mandar el 0x1059 (mismas direcciones, `+0x2DF = 3`) para que el cliente repita su medición y mande
         `0x105A` si un puerto cambió y quedó en -1000 ms."""
    ahora = time.time() if ahora is None else ahora
    r = []
    for s in list(salas.values()):
        if s.get("jugando") or len(s["miembros"]) < 2 or "anunciado" not in s:
            continue
        antes = dict(s["anunciado"])
        ultimo = s.get("anunciado_en")
        if ultimo is None:
            ultimo = s["anunciado_en"] = ahora
        nuevos = pares(s, anotar=False, ahora=ahora)
        cambiados = []
        for x in nuevos:
            if antes.get(x[3]) != x[1][7:]:
                print("sala: a #%s le cambió una dirección de su sala: 0x1059 otra vez" % x[3], flush=True)
                cambiados.append(x)
        if cambiados:
            s["anunciado_en"] = ahora
            r.extend(cambiados)
        elif por_tiempo and REMEDIR_SALA > 0 and ahora - ultimo >= REMEDIR_SALA:
            s["anunciado_en"] = ahora
            r.extend(nuevos)
    return r


@maneja(0x105A)
def reporte_ping_udp(cmd, cuerpo, conexion, c, p):
    """★ (22-nov) 0x105A C→S (`0x4DC330`, 9 B: u32 id_cuenta · f32 ping_s · u8 timeouts):
    1 s después del 0x1059 (con +0x2DF = 3), el invitado mide con `0x748120` si conectó por UDP con el
    anfitrión. Si el directo falló (-1000 ms, «[UDP ERROR] PingError! PingInfo Not Collect!!!»), manda
    timeouts = 2 (`0x4DC453`). El server marca SOLO ese par sin directo y les manda el 0x1059 por el relay."""
    if len(cuerpo) >= 9:
        id_cuerpo, ping, timeouts = struct.unpack_from("<IfB", cuerpo, 0)
    elif len(cuerpo) >= 1:
        id_cuerpo, ping, timeouts = 0, -1.0, cuerpo[0]
    else:
        return []
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return []
    if timeouts >= 2 or ping < 0:
        anf = s.get("anfitrion")
        if id_cuerpo and id_cuerpo != conexion and id_cuerpo in s["miembros"]:
            otros = [id_cuerpo]
        elif anf and anf != conexion and anf in s["miembros"]:
            otros = [anf]
        else:
            otros = [m for m in s["miembros"] if m != conexion]
        for otro in otros:
            relay.marcar_sin_directo(conexion, otro)
        print("sala %s: #%s reportó fallo de UDP directo (0x105A, timeouts=%d) → pasa al relay"
              % (p.get("sala"), conexion, timeouts), flush=True)
        if not s.get("jugando") and len(s["miembros"]) >= 2:
            if "anunciado" in s:
                return reanunciar({p.get("sala"): s}, por_tiempo=False)
            return pares(s)
    return []


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
    if s is None or s.get("jugando") or len(s["miembros"]) >= s["sala"][0x2F]:
        return [(0x1020, struct.pack("<H", 0) + bytes(99), 0)]   # 🟡 «no se pudo»
    # si ya estaba en otra sala, salir limpiamente de ella primero
    vieja = p.get("sala")
    if vieja and vieja != num and vieja in SALAS and conexion in SALAS[vieja]["miembros"]:
        _sacar_de_sala(SALAS[vieja], vieja, conexion)
    if conexion not in s["miembros"]:
        s["miembros"].append(conexion)
    yo = dar_numero(s, conexion)
    s.setdefault("listos", set()).discard(conexion)     # (el que entra, todavía no está listo)
    p["sala"] = num
    p["escenario"] = struct.unpack_from("<H", s["sala"], 0x28)[0] if len(s["sala"]) >= 0x2A else 1011
    sala = bytearray(s["sala"])
    sala[0x2D], sala[0x2E] = 1, len(s["miembros"])
    # 0x1020 (`0x543640`, 101 B + N × 0x32C): u16 1 · u8 → +0x705 · u8 → +0x706 (MI número
    #   de jugador) · u8 → +0x29D · vt 0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · la sala (89 B) ·
    #   u8 N · los OTROS miembros (🟡 el propio lo agrega el cliente, como el anfitrión)
    otros = [n for n in s["miembros"] if n != conexion]
    # ★ (Punto 3) +0x29D = el número del ANFITRIÓN (antes 0 fijo: si el anfitrión no era el 0, nadie largaba)
    cab = struct.pack("<HBBBIBB", 1, yo, yo, numero(s, s["anfitrion"]), 0x89A3B8, 0, 0)
    cuerpo20 = (cab + bytes(sala) + bytes([len(otros)])
                + b"".join(miembro(leer(n), numero(s, n), conexion=n, para=conexion,
                                   listo=n in s["listos"]) for n in otros))
    # al anfitrión (y los demás de la sala): 0x1057 (`0x54F020`, 0x377 B) = u8 → +0x272 ·
    #   u8 → +0x271 (estado de la sala) · vt 0x89A3B8 · u8 → +0x2DE · u8 → +0x2DF · el
    #   miembro NUEVO completo (0x36F) — uno por destinatario (su dirección depende de quién la ve)
    #   ★ (22-nov) +0x2DF = 2: en el exe (`0x54F0EA` → `0x54F0FC`: `call 0x621980(4)`), con +0x2DF = 2 el
    #   anfitrión (y quienes ya estaban en la sala) también mandan su 0x3006 × 4 al punch del server y
    #   renuevan su puerto UDP público cada vez que entra alguien (antes iba en 0 y el anfitrión no renovaba nunca)
    def aviso(para):
        listo_para = 1 if para in s.get("listos", ()) else 0
        return (struct.pack("<BBIBB", 0, 0, 0x89A3B8, listo_para, 2)
                + miembro(c, yo, completo=True, conexion=conexion, para=para))
    return ([(0x1020, cuerpo20, 0)] + [(0x1057, aviso(n), 0, n) for n in otros]
            + pares(s, 500) + avisar_lista(salvo=conexion))


@maneja(0x1049)
def cambiar_sala(cmd, cuerpo, conexion, c, p):
    """★ CAMBIAR TÍTULO / CONTRASEÑA de la sala (aporte de Hysteria-xyz, PR #3). Cuerpo: u8 jugador ·
    u16 tipo (1 título, 2 contraseña) · texto. Respuesta 0x104A (manejador `0x54E3D0`): u16 1 · u16
    tipo · texto, a él y a los demás de la sala. 🟡 sin medir en pantalla."""
    if not (len(cuerpo) >= 3):
        return None
    tipo = struct.unpack_from("<H", cuerpo, 1)[0]
    texto = cuerpo[3:]
    s = SALAS.get(p.get("sala"))
    r = [(0x104A, struct.pack("<HH", 1, tipo) + texto, 0)]
    if s:
        if tipo == 1 and len(s["sala"]) >= 0x28:
            sala_b = bytearray(s["sala"])
            limite = min(len(texto), 0x22)
            sala_b[6:6 + limite] = texto[:limite]
            if 6 + limite < 0x28:
                sala_b[6 + limite:0x28] = bytes(0x28 - (6 + limite))
            s["sala"] = bytes(sala_b)
        r += [(0x104A, struct.pack("<HH", 1, tipo) + texto, 0, n) for n in s["miembros"] if n != conexion]
    return r


def _sacar_de_sala(s, num, conexion):
    """Saca a `conexion` de la sala; si era el anfitrión, el mando pasa al siguiente. Devuelve los
    avisos 0x1058 tipo 3 («se fue», con el número del NUEVO anfitrión) para los que quedan."""
    if conexion not in s["miembros"]:
        return []
    yo = numero(s, conexion)
    era_master_stage = bool(s.get("jugando") and s.get("largada") and s.get("anfitrion") == conexion
                            and not (PARTIDAS.get(conexion) or {}).get("resultado_guardado"))
    s["miembros"].remove(conexion)
    s.get("numeros", {}).pop(conexion, None)
    s.get("listos", set()).discard(conexion)
    if "en_stage" in s:                                 # (Punto 3: si era el último en la stage, se reabre)
        s["en_stage"].discard(conexion)
        if not s["en_stage"] and s.get("jugando"):
            s["jugando"] = False
            VIVO.LISTA_CAMBIO = True                    # (que el lobby la vea «Waiting»)
    if "cargados" in s:
        s["cargados"].discard(conexion)
    if not s["miembros"]:
        del SALAS[num]
        return []
    if s["anfitrion"] == conexion:
        # ★ (21-nov) en plena stage, el mando (el MÁSTER del escenario: el único que manda bajas y el fin, ver
        #   `partida.fin_de_stage`) pasa a uno que SIGUE en la stage; si no, el que termina queda sin máster
        en_stage = [m for m in s["miembros"] if m in s.get("en_stage", ())] if s.get("jugando") else []
        s["anfitrion"] = (en_stage or s["miembros"])[0]
        s.get("listos", set()).discard(s["anfitrion"])  # (el anfitrión no «está listo»: larga)
    nuevo = numero(s, s["anfitrion"])
    r = [(0x1058, struct.pack("<BHB", yo, 3, nuevo), 0, n) for n in s["miembros"]]
    # ★ (22-nov) si el máster se fue o se desconectó en plena stage (ya largada), la stage SIGUE con el nuevo
    #   anfitrión (0x1058 tipo 3 prende +0x168 en su cliente) y desde ahí rige la guardia de stage trabada (90 s
    #   sin bajas nuevas). Si se fue durante la pantalla de carga (antes de la largada), los que ya cargaron largan.
    from servidor.partida import activar_guardia_traspaso, largar_si_cargaron
    if era_master_stage and s.get("en_stage"):
        activar_guardia_traspaso(s, conexion)
    return r + largar_si_cargaron(s)


@maneja(0x1045)
def salir_sala(cmd, cuerpo, conexion, c, p):
    """★ LEAVE ROOM (aporte de Hysteria-xyz, PR #3): sin respuesta el cliente se quedaba en «Waiting for
    Response from Server». 0x1046 (manejador `0x54E380`): u16 1 → de vuelta al lobby. A los que
    quedan, 0x1058 tipo 3 (y si se fue el anfitrión, el mando pasa al siguiente)."""
    num = p.pop("sala", None)
    r = [(0x1046, struct.pack("<H", 1), 0)]
    s = SALAS.get(num)
    if s and conexion in s["miembros"]:
        r += _sacar_de_sala(s, num, conexion)
    return r + avisar_lista()


@maneja(0x1051)
def echar(cmd, cuerpo, conexion, c, p):
    """★ KICK (aporte de Hysteria-xyz, PR #3): el anfitrión echa al jugador del lugar cuerpo[0]. Al
    anfitrión 0x1052 (`0x550780`, cierra su cuadro de espera); al echado 0x1054 (`0x546D90`: u16 1 ·
    u8 → al lobby); a los que quedan 0x1058 tipo 3. Sólo el anfitrión puede, y no a sí mismo."""
    if not (len(cuerpo) >= 1):
        return None
    num = p.get("sala")
    s = SALAS.get(num)
    echado = de_numero(s, cuerpo[0]) if s else None   # (cuerpo[0] = su NÚMERO de jugador)
    if not s or s["anfitrion"] != conexion or echado is None:
        return [(0x1052, b"\0", 0)]
    if echado == conexion:
        return [(0x1052, b"\0", 0)]
    partida(echado).pop("sala", None)
    return ([(0x1052, b"\0", 0), (0x1054, struct.pack("<HB", 1, 0), 0, echado)]
            + _sacar_de_sala(s, num, echado) + avisar_lista())


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
        yo = numero(s, conexion)
        # ★ (Punto 3) el server RECUERDA quién está listo: lo usan el que entra después (0x1020), la
        #   vuelta del inventario (0x102E modo 9) y la largada (0x104E)
        if estado == 1 and conexion != s["anfitrion"]:
            s.setdefault("listos", set()).add(conexion)
        else:
            s.setdefault("listos", set()).discard(conexion)
        r += [(0x1058, struct.pack("<BHB", yo, 1, estado), 0, n)
              for n in s["miembros"] if n != conexion]
    return r


def cuentas_gm():
    """★ (22-nov) Las cuentas con permiso de GM (`config.GM_CUENTAS` / `EDA_GM_CUENTAS`, separadas por comas).
    Vacía por defecto = nadie es GM."""
    crudo = config.GM_CUENTAS
    if isinstance(crudo, str):
        return {x.strip() for x in crudo.split(",") if x.strip()}
    return {str(x).strip() for x in (crudo or ()) if str(x).strip()}


def es_gm(cuenta):
    if not cuenta or cuenta.startswith("_"):
        return False
    gms = cuentas_gm()
    if cuenta in gms:
        return True
    pref = config.PREFIJO_CUENTA or ""
    return bool(pref and cuenta.startswith(pref) and cuenta[len(pref):] in gms)


def log_gm(mensaje):
    print(mensaje, flush=True)


def _buscar_conectado(texto):
    """(conexión, cuenta_dict) del jugador conectado con ese nick o nombre de cuenta, o (None, None)."""
    t = (texto or "").strip().lower()
    if not t:
        return None, None
    for n in sorted(ASIGNADAS):
        nom = ASIGNADAS.get(n)
        if not nom or nom.startswith("_"):
            continue
        cn = leer(n)
        if nombre_visible(cn).lower() == t:
            return n, cn
    for n in sorted(ASIGNADAS):
        nom = ASIGNADAS.get(n)
        if nom and not nom.startswith("_") and nom.lower() == t:
            return n, leer(n)
    return None, None


@maneja(0x100D)
def chat(cmd, cuerpo, conexion, c, p):
    """★ CHAT (lobby / sala) + COMANDOS GM (/oro, /nivel, /item, /ayuda: sólo cuentas en EDA_GM_CUENTAS)"""
    if not (len(cuerpo) >= 13):
        return None
    # C→S (medido 18:19): u8 tipo (1) · u32 destino (FFFFFFFF = todos) · u32 0 · u32 largo en
    #   bytes · el texto UTF-16. S→C 0x1005 → la pantalla actual (`0x4DB6F0` → vt+0x80 =
    #   `0x4DF140`): cabecera de 37 B (`0x53FF50`): u8 tipo (1/3 = chat; 4 = aviso del sistema)
    #   · u32 color 🟡 · u32 🟡 · 28 B el NOMBRE en UTF-16 🟡 — y el texto (`0x742A80`: u32
    #   largo + UTF-16, como lo manda el cliente)
    largo = struct.unpack_from("<I", cuerpo, 9)[0]
    texto = cuerpo[13:13 + largo]

    # ★ Comandos de chat y de GM
    try:
        texto_str = texto.decode("utf-16-le").rstrip("\x00").strip()
    except Exception:
        texto_str = ""

    if texto_str.startswith("/"):
        from servidor import messenger
        r = messenger.comando(texto_str, conexion, c)
        if r is not None:
            return r

        def _aviso(txt, dest=None):
            b = txt.encode("utf-16-le")
            nom = "[Sistema]".encode("utf-16-le")[:24].ljust(26, b"\0")
            paq = (0x1005, struct.pack("<HBII", 0, 4, 0xFF00FF00, 0) + nom
                           + struct.pack("<I", len(b)) + b, 0)
            return [paq if dest is None else paq + (dest,)]

        def _avisar_cambio(mensaje, destino):
            texto = f"{mensaje}; se ve al volver a la pantalla de personajes"
            avisos = _aviso(texto)
            if destino is not None and destino != conexion:
                avisos += _aviso(texto, dest=destino)
            return avisos

        def _auditar(accion, dest_c, detalle):
            log_gm("gm: #%s (%s) · %s · a %s (%s) · %s"
                   % (conexion, c["nombre"], accion, dest_c["nombre"], nombre_visible(dest_c), detalle))

        partes = texto_str[1:].split()
        sub = partes[0].lower() if partes else ""
        gm = es_gm(c["nombre"])
        if sub in ("ayuda", "help"):
            if gm:
                return _aviso(f"Eres GM. Comandos GM: /oro [+]<n> [pj], /monedas <n>, /nivel <1-{len(EXPS)}>, "
                              f"/item <id> [cant] [pj], /stats [pj] <5 valores>, /reiniciar <pj> (/reset), /limpiar · Messenger: /messenger")
            return _aviso("Comandos: /messenger, /amigos, /amigo <nick>, /quitar <nick>, /m <nick> <mensaje>")
        if not gm:
            return _aviso(f"Comando desconocido: /{sub}. Usa /ayuda")
        if sub == "cash":                                    # ★ (Paso 6) EDA usa sólo oro
            return _aviso("El cash no existe en EDA: todo se compra con oro (/oro <cantidad>).")

        if sub in ("oro", "gold"):
            if len(partes) >= 2:
                crudo_n = partes[1]
                es_suma = crudo_n.startswith("+") and crudo_n[1:].isdigit()
                es_fijo = crudo_n.isdigit()
                if es_suma or es_fijo:
                    val = int(crudo_n[1:] if es_suma else crudo_n)
                    if len(partes) >= 3:
                        dest_n, dest_c = _buscar_conectado(partes[2])
                        if dest_c is None:
                            return _aviso(f"El jugador {partes[2]} no está conectado.")
                        if dest_n == conexion:
                            dest_c = c
                    else:
                        dest_n, dest_c = conexion, c
                    antes = dest_c.get("plata", 0)
                    nuevo = antes + val if es_suma else val
                    dest_c["plata"] = max(0, min(nuevo, 2_000_000_000))
                    guardar(dest_c)
                    _auditar(texto_str, dest_c, f"oro {antes} -> {dest_c['plata']}")
                    quien = f" de {nombre_visible(dest_c)}" if dest_n != conexion else ""
                    return _avisar_cambio(f"Oro{quien} actualizado a {dest_c['plata']}", dest_n)
            return _aviso("Uso: /oro [+]<cantidad> [personaje]")
        elif sub in ("nivel", "lvl", "level"):
            if len(partes) >= 2 and partes[1].isdigit():
                n = max(1, min(int(partes[1]), len(EXPS)))
                antes = nivel(c["exp"])
                c["exp"] = EXPS[n - 1]
                guardar(c)
                _auditar(texto_str, c, f"nivel {antes} -> {n} (EXP: {c['exp']})")
                return _aviso(f"Nivel actualizado a {n} (EXP: {c['exp']})")
            return _aviso(f"Uso: /nivel <1-{len(EXPS)}>")
        elif sub == "item":
            if len(partes) >= 2 and partes[1].isdigit():
                iid = int(partes[1])
                cant = 1
                nom_dest = None
                if len(partes) >= 3:
                    if partes[2].isdigit():
                        cant = max(1, min(int(partes[2]), 999))
                        if len(partes) >= 4:
                            nom_dest = partes[3]
                    else:
                        nom_dest = partes[2]
                if nom_dest is not None:
                    dest_n, dest_c = _buscar_conectado(nom_dest)
                    if dest_c is None:
                        return _aviso(f"El jugador {nom_dest} no está conectado.")
                    if dest_n == conexion:
                        dest_c = c
                else:
                    dest_n, dest_c = conexion, c
                from servidor.objetos import inventario, libre_en_bolsa, serial_nuevo, es_equipo
                inv = inventario(dest_c)
                it = next((x for x in inv if x[0] == iid and x[2] >= 18 and not es_equipo(iid)), None)
                if it:
                    it[1] = min(999, it[1] + cant)
                else:
                    try:
                        slot = libre_en_bolsa(inv)
                        inv.append([iid, min(999, cant) if not es_equipo(iid) else 1, slot, serial_nuevo(inv), 1])
                    except StopIteration:
                        return _aviso("La bolsa está llena")
                dest_c["items"] = inv
                guardar(dest_c)
                _auditar(texto_str, dest_c, f"item {iid} x{cant}")
                if dest_n != conexion:
                    return (_aviso(f"Item {iid} (x{cant}) agregado a {nombre_visible(dest_c)}")
                            + _aviso(f"Item {iid} (x{cant}) agregado", dest=dest_n))
                return _aviso(f"Item {iid} (x{cant}) agregado")
            return _aviso("Uso: /item <id> [cantidad] [personaje]")
        elif sub in ("moneda", "monedas"):
            if len(partes) >= 2 and partes[1].isdigit():
                antes = c.get("monedas", 0)
                c["monedas"] = max(0, min(int(partes[1]), 999))
                guardar(c)
                _auditar(texto_str, c, f"monedas {antes} -> {c['monedas']}")
                return _aviso(f"Monedas actualizadas a {c['monedas']}")
            return _aviso("Uso: /monedas <cantidad>")
        elif sub in ("stats", "reiniciar", "reset"):
            if sub == "stats":
                dirigido = len(partes) == 7
                argumentos = partes[2:] if dirigido else partes[1:]
                try:
                    if not 1 <= len(argumentos) <= 5:
                        raise ValueError
                    vals = [max(0, min(int(x), 9999)) for x in argumentos]
                except ValueError:
                    return _aviso("Uso: /stats [personaje] <str> <con> <dex> <int> <wis>")
                vals += [0] * (5 - len(vals))
                detalle = "Stats actualizados: STR %d CON %d DEX %d INT %d WIS %d" % tuple(vals)
                if not dirigido:
                    c["stats"] = vals
                    guardar(c)
                    _auditar(texto_str, c, detalle)
                    return _aviso(detalle)
            else:
                if len(partes) != 2:
                    return _aviso(f"Uso: /{sub} <personaje>")
                vals = [0] * 5
                detalle = "Puntos repartidos devueltos"
            dest_n, dest_c = fijar_stats_personaje(partes[1], vals)
            if dest_c is None:
                return _aviso(f"El personaje {partes[1]} no existe.")
            _auditar(texto_str, dest_c, detalle)
            return _avisar_cambio(f"{nombre_visible(dest_c)}: {detalle}", dest_n)
        elif sub in ("limpiar", "clear"):
            antes = len(c.get("items", []))
            c["items"] = [x for x in c.get("items", []) if len(x) > 2 and x[2] < 18]
            guardar(c)
            _auditar(texto_str, c, f"limpiar bolsa ({antes} -> {len(c['items'])} items)")
            return _aviso("Bolsa limpiada (equipo y atajos conservados)")
        return _aviso(f"Comando desconocido: /{sub}. Usa /ayuda")

    # ⚠ medido con Frida (18:23): el TIPO lo lee en B+2 (con el tipo en B+0 leía 0xFF). La
    #   cabecera es u16 🟡 · u8 tipo · u32 🟡 (¿color?) · u32 🟡 · 26 B nombre UTF-16
    nombre = nombre_visible(c).encode("utf-16-le")[:24].ljust(26, b"\0")
    msg = (struct.pack("<HBII", 0, cuerpo[0], 0xFFFFFFFF, 0) + nombre
           + struct.pack("<I", len(texto)) + texto)
    s = SALAS.get(p.get("sala"))
    destinos = s["miembros"] if s and conexion in s["miembros"] else sorted(ASIGNADAS)
    return [(0x1005, msg, 0, n) for n in destinos]


@maneja(0x1025)
def entrada_rapida(cmd, cuerpo, conexion, c, p):
    """★ QUICK JOIN (0x1025 C→S / 0x1026 S→C `0x5424E0`, aporte de Hysteria-xyz):
    Al pulsar «Quick Join» en el lobby, busca la primera sala abierta con lugar libre.
    S→C (5 B): u16 resultado (1 = OK, 0xBB9 = sin salas) · u16 sala · u8 modo (0).
    Con resultado 1, el cliente llama a entrar a la sala elegida (`0x4EBEE0` → `0x101F`)."""
    sala_id = None
    for num in sorted(SALAS):
        s = SALAS[num]
        if not s.get("jugando") and len(s["miembros"]) < s["sala"][0x2F]:
            sala_id = num
            break
    if sala_id is not None:
        return [(0x1026, struct.pack("<HHB", 1, sala_id, 0), 0)]
    return [(0x1026, struct.pack("<HHB", 0xBB9, 0xFFFF, 0), 0)]


@maneja(0x1019)
def entrar_desde_lobby(cmd, cuerpo, conexion, c, p):
    """★ 0x1019 C→S / 0x101A S→C (`0x542990`, 9 B, aporte de Hysteria-xyz):
    Entrar a una sala desde la lista del lobby al pulsar Enter o doble clic.
    cuerpo: u32 num_sala (o u16), u8 flag_password.
    0x101A: u16 resultado (1 = OK, 0x9C5 = sala llena/inexistente, 0x9C6 = en juego)
            · u8 modo (0) · u16 sala · u16 escenario · u16 dificultad."""
    if len(cuerpo) < 2:
        return [(0x101A, struct.pack("<HBH HH", 0x9C5, 0, 0, 0, 0), 0)]
    num = struct.unpack_from("<H", cuerpo, 0)[0]
    s = SALAS.get(num)
    if not s and len(cuerpo) >= 4:
        num = struct.unpack_from("<I", cuerpo, 0)[0]
        s = SALAS.get(num)
    if not s:
        return [(0x101A, struct.pack("<HBH HH", 0x9C5, 0, 0, 0, 0), 0)]
    if s.get("jugando"):
        return [(0x101A, struct.pack("<HBH HH", 0x9C6, 0, num, 0, 0), 0)]
    max_j = s["sala"][0x2F] if len(s["sala"]) > 0x2F else 3
    if len(s["miembros"]) >= max_j:
        return [(0x101A, struct.pack("<HBH HH", 0x9C5, 0, num, 0, 0), 0)]
    esc = struct.unpack_from("<H", s["sala"], 0x28)[0] if len(s["sala"]) >= 0x2A else 1011
    dif = struct.unpack_from("<H", s["sala"], 0x2C)[0] if len(s["sala"]) >= 0x2E else 0
    return [(0x101A, struct.pack("<HBH HH", 1, 0, num, esc, dif), 0)]


@maneja(0x101A)
def retransmitir_101a(cmd, cuerpo, conexion, c, p):
    """★ 0x101A (`0x542990`): confirmación de entrada a sala."""
    return [(0x101A, cuerpo, 0)]


@maneja(0x1055)
def consultar_sala_1055(cmd, cuerpo, conexion, c, p):
    """★ 0x1055 C→S / 0x1056 S→C (`0x543BE0`, 82 B, aporte de Hysteria-xyz):
    Actualización/consulta de estado de sala en lobby."""
    buf = bytearray(0x52)
    s = SALAS.get(p.get("sala"))
    if s and len(s["sala"]) >= 0x52:
        buf[:min(0x52, len(s["sala"]))] = s["sala"][:0x52]
    return [(0x1056, bytes(buf), 0)]


@maneja(0x1056)
def aviso_sala_1056(cmd, cuerpo, conexion, c, p):
    """★ 0x1056 (`0x543BE0`): retransmisión de estado de sala en lobby."""
    return [(0x1056, cuerpo, 0)]


def aviso_equipo_105b(c, yo):
    """★ 0x105B (633 B, `0x54F740`, aporte de Hysteria-xyz): actualiza el equipo y modelo 3D del miembro en sala.
    u32 yo · u8 0 · 6 u16 stats · 18 × 34 B (vt 0x89A38C · u16 tipo · vt 0x89A380 · 24 B)."""
    buf = bytearray(0x279)
    struct.pack_into("<IB", buf, 0, yo, 0)
    from servidor.objetos import stats_de
    st = stats_de(c)
    for k in range(6):
        struct.pack_into("<H", buf, 5 + 2 * k, st[k])
    tipos = equipo_tipos(c)
    for k in range(18):
        struct.pack_into("<IH", buf, 17 + 34 * k, 0x89A38C, tipos[k])
        struct.pack_into("<I", buf, 17 + 34 * k + 6, 0x89A380)
    return bytes(buf)


@maneja(0x105B)
def sincronizar_equipo_sala(cmd, cuerpo, conexion, c, p):
    """★ 0x105B (`0x54F740`, aporte de Hysteria-xyz): retransmite actualización de equipo 3D a los demás de la sala."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return None
    yo = numero(s, conexion)
    msg = aviso_equipo_105b(c, yo)
    return [(0x105B, msg, 0, n) for n in s["miembros"] if n != conexion]


@maneja(0x104B)
def actualizar_ajustes_sala(cmd, cuerpo, conexion, c, p):
    """★ ACTUALIZAR AJUSTES DE SALA (0x104B S→C `0x54F500`, aporte de Hysteria-xyz):
    Transmite cambios de escenario / dificultad / estado a los demás miembros de la sala.
    S→C: u16 tipo (1 = escenario, 2 = dificultad) · datos."""
    if len(cuerpo) < 2:
        return None
    s = SALAS.get(p.get("sala"))
    if not s:
        return None
    tipo = struct.unpack_from("<H", cuerpo, 0)[0]
    if tipo == 1 and len(cuerpo) >= 6:
        esc = struct.unpack_from("<I", cuerpo, 2)[0]
        sala_b = bytearray(s["sala"])
        struct.pack_into("<I", sala_b, 0x28, esc)
        s["sala"] = bytes(sala_b)
        p["escenario"] = esc
        for m in s["miembros"]:
            partida(m)["escenario"] = esc
    elif tipo == 2 and len(cuerpo) >= 3 and len(s["sala"]) > 0x2C:
        sala_b = bytearray(s["sala"])
        sala_b[0x2C] = cuerpo[2]
        s["sala"] = bytes(sala_b)
    return [(0x104B, cuerpo, 0, n) for n in s["miembros"] if n != conexion]


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
    # ★ (Punto 3) ese u8 = 0 le APAGA su «listo» (+0x2DE): los demás lo tienen que saber (0x1058 tipo 1
    #   en 0), si no el anfitrión lo seguía viendo listo y podía largar con él en el inventario
    r = [(0x104D, struct.pack("<HB", 1, 0), 0)]
    s = SALAS.get(p.get("sala"))
    if s and conexion in s["miembros"] and conexion in s.get("listos", ()):
        s["listos"].discard(conexion)
        r += [(0x1058, struct.pack("<BHB", numero(s, conexion), 1, 0), 0, n)
              for n in s["miembros"] if n != conexion]
    return r


@maneja(0x1017)
def entrar_lobby(cmd, cuerpo, conexion, c, p):
    """ENTER LOBBY [§5.7]"""
    # ★ N1 = las misiones TERMINADAS: cada una 10 B como el registro del PlayEnd (`0x621620`,
    #   la clave u32 en +4) — 🟡 [u32 0 · u32 escenario · u8 1 · u8 1]
    #   ⚠ la cabecera (16 B) es u16 resultado · u8 personaje (+2) · u32 N1 (+3) · u16 N2 (+7)
    #   · 7 B (+9 → `0x6103E0`): medido el 10-nov — antes se ponía N1 en +7 (mal contado un
    #   `push ebx`) y el cliente leía N1 = 0: el mapa de terminadas quedaba VACÍO
    # ★★ el PERSONAJE elegido en SELECT CHARACTER (MEDICIONES §50): el 0x1017 = u32 · u8 LUGAR. Si es
    #   otro que el activo, se cambia, y antes del 0x1018 sale la cuenta otra vez (0x1012) con ESE
    #   personaje (su inventario, su equipo), mientras el cliente sigue en esa pantalla
    previo = []
    if len(cuerpo) >= 5:
        from servidor.objetos import cuerpo_cuenta
        from servidor.personajes import elegir
        otra = elegir(conexion, c, cuerpo[4])
        if otra is not c:
            c = otra
            # ⚠ medido: al recibir la cuenta, el cliente se queda con el del LUGAR 0 → el elegido va ahí
            #   (cambiado con el que estaba). Al volver a SELECT CHARACTER pide la cuenta (0x1011) y
            #   cada uno aparece en su lugar de verdad
            previo = [(0x1012, cuerpo_cuenta(c, conexion, elegido_al_frente=True), 0)]
    n1 = c["terminadas"]
    # ★ los 7 B de +9 = el CANAL (→ `cuenta+0x220`+4, `0x6103E0`): 🟡 u8 número · u16
    #   CAPACIDAD (+5) · u16 ocupados (+7) · u16. Con capacidad 0 la lista de usuarios del lobby
    #   no agrega a nadie (`0x6109F0`: si [+0x1C] >= [+5] → no) — medido 18:18
    canal = struct.pack("<BHHH", 1, 200, len(ASIGNADAS), 0)
    # ★ N2 (+7) = las HABILIDADES aprendidas: N2 × 13 B (`0x544795` → cuenta+0x728)
    habs = c.get("habilidades", [])
    # (+2 = 🟡 el personaje elegido: ¿su POSICIÓN en la lista del 0x1012 o su lugar? — a medir, §50)
    #   (medido, §50: ni el lugar ni la posición cambian qué personaje muestra el lobby; va 0)
    cuerpo18 = (struct.pack("<HBIH", 1, 0, len(n1), len(habs)) + canal
                + b"".join(struct.pack("<IIBB", 0, m, 1, 1) for m in n1)
                + b"".join(obj_habilidad(h) for h in habs))
    # al volver al lobby sale limpiamente de cualquier sala
    avisos_salida = []
    vieja = p.pop("sala", None)
    if vieja and vieja in SALAS and conexion in SALAS[vieja]["miembros"]:
        avisos_salida = _sacar_de_sala(SALAS[vieja], vieja, conexion)
    # ★ y la lista de salas, apenas entra (cuando ya está en la pantalla del lobby)
    from servidor import messenger
    return (avisos_salida + previo + [(0x1018, cuerpo18, 0), (0x101C, lista_salas(), 1500),
             (0x101B, lista_usuarios(), 1700)]
            + [(x[0], x[1], 1700, x[3]) for x in avisar_usuarios(salvo=conexion)]
            + [(x[0], x[1], 2000, x[3]) for x in messenger.avisar_amigos(
                c["nombre"], "%s se conectó (en el lobby)." % nombre_visible(c))])


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
    # si ya estaba en otra sala (como anfitrión o invitado), salir limpiamente de ella
    avisos_salida = []
    vieja = p.get("sala")
    if vieja and vieja in SALAS and conexion in SALAS[vieja]["miembros"]:
        avisos_salida = _sacar_de_sala(SALAS[vieja], vieja, conexion)
    SALAS[num] = {"sala": bytes(sala), "anfitrion": conexion, "miembros": [conexion],
                  "numeros": {conexion: 0}, "listos": set()}
    p["sala"] = num
    return (avisos_salida + [(0x101E, struct.pack("<HBBB", 1, 0, 0, 0) + bytes(sala), 0)]
            + avisar_lista(salvo=conexion))


@maneja(0x104E)
def largar(cmd, cuerpo, conexion, c, p):
    """★ F9 START GAME (el anfitrión)"""
    # 0x104F (`0x54F170`) a TODOS los de la sala: u16 1 · u32 (+0x53: partidas) · u8 🟡 ·
    #   u8 N · N × 68 B ([u8 número de jugador][9 × 7 B: 🟡 su equipo para la partida])
    # Si no es el anfitrión o no hay sala, 0x1050 (0x54EBA0) con error 0x138A (modal 0x191)
    s = SALAS.get(p.get("sala"))
    if not s or s.get("anfitrion") != conexion or s.get("jugando"):
        return [(0x1050, struct.pack("<H", 0x138A), 0)]
    miembros = s["miembros"] if s else [conexion]
    # ★ (Punto 3) con varios, TODOS los demás tienen que estar listos (lo mismo que mira el cliente,
    #   `0x61C170`): si no, el mismo error, que el cliente muestra como «All users must be ready»
    if any(n != conexion and n not in s.get("listos", ()) for n in miembros):
        return [(0x1050, struct.pack("<H", 0x138A), 0)]
    previos = []
    if s and len(miembros) >= 2:
        # ★ (22-nov) antes de cada partida (0x104F), asegurar que todos tengan la dirección ACTUAL de los demás
        if "anunciado" in s:
            previos = reanunciar({p.get("sala"): s}, por_tiempo=False)
        elif any(relay.actual_de(n) or partida(n).get("sin_directo") for n in miembros):
            previos = pares(s)
    if s:
        s["jugando"], s["cargados"] = True, set()
        s.pop("largada", None)                          # (20-nov: la largada se da UNA vez por stage)
        s.pop("carga_desde", None)
        s.pop("traspaso_master", None)
        s.pop("ultima_baja_stage", None)
        s["bajas_stage"] = set()
        s["en_stage"] = set(miembros)                   # (Punto 3: «jugando» hasta que salgan TODOS)
        s["muertos_stage"] = 0                          # (21-nov: las bajas de la partida, del máster)
        s["listos"] = set()                             # (al volver de la stage, todos «no listo»: `0x548AF0`)
        # ★ (21-nov, diagnóstico) el ID de ESTA partida: una línea del registro con quién juega, para juntar
        #   después todo lo de la partida (herramientas/diag_partida.py). Sin IP ni nada de la cuenta salvo su nombre
        s["partida_id"] = time.strftime("P-%Y%m%d-%H%M%S", time.gmtime()) + "-s%d" % p.get("sala", 0)
        print("partida %s empieza: sala %s · %s" % (s["partida_id"], p.get("sala"), " · ".join(
            "#%s=%s" % (n, ASIGNADAS.get(n, "?")) for n in miembros)), flush=True)
    #   ⛔ probado (21:15) llenarlos con las habilidades de los atajos: NO las hace lanzar
    #   (el MP no baja con F1). Son de los OTROS (`0x61C230` los copia a su miembro). En cero.
    lista = b"".join(bytes([numero(s, n)]) + bytes(67) for n in miembros)
    r = []
    for n in miembros:
        cn = leer(n)
        r.append((0x104F, struct.pack("<HIBB", 1, cn["partidas"], 0, len(miembros)) + lista,
                  0, n))
    return previos + r + (avisar_lista(salvo=conexion) if s else [])


@maneja(0x1050)
def error_largada_1050(cmd, cuerpo, conexion, c, p):
    """★ 0x1050 (`0x54EBA0`, 2 B, aporte de Hysteria-xyz): aviso de error al iniciar partida (0x138A o 0x6C)."""
    return [(0x1050, cuerpo if len(cuerpo) >= 2 else struct.pack("<H", 0x138A), 0)]
