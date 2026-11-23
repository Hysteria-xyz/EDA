r"""relay_udp -- el RELAY UDP del multijugador: que se encuentren clientes en PCs distintas.

★ El problema (MEDICIONES §30): cada cliente reconoce a sus pares por la IDENTIDAD P2P que va en
  sus saludos (`0xC354` / `0xC351` / `0xC352`: la MAC en texto, 17 caracteres) y la compara con la
  que el server puso en +0xA de cada miembro de la sala. Pero el cliente NO le dice al server su
  MAC (la mandaba el launcher). Y entre PCs, además, está el NAT (cíber, LAN, simétrica).

★ La salida (todo del lado del server, el exe no se toca):
  · el server inventa una identidad por jugador («02:00:00:00:00:NN») y la pone en su miembro;
  · como dirección de cada par da un puerto de ESTE relay (RELAY_BASE + 1 + conexión);
  · el relay reenvía cada datagrama al jugador dueño de ese puerto, saliendo por el puerto del que
    lo mandó (así el que recibe ve llegar al par desde la dirección que conoce), y en el camino
    cambia la MAC real del que manda por su identidad inventada (y la inventada del que recibe
    por su MAC real, por si la nombra).
  Como todo pasa por acá, no importa el tipo de NAT de nadie.

  A quién pertenece cada dirección lo aprende de los «registrame» del punch (`0x3006`: u32 = la
  conexión, que el server le dio en el 0x1010) — por eso este relay atiende también el puerto de
  punch (RELAY_BASE). Las identidades inventadas las lee de `_trabajo/servidor/relay.json` (las
  escribe `servidor/juego.py`). Se prende en el server con el archivo `_trabajo/servidor/modo_relay`.

    py herramientas\relay_udp.py [IP de escucha=0.0.0.0]
    py herramientas\relay_udp.py control          # el cambio de identidades (con su revés)
"""
import json
import os
import re
import select
import socket
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (con EDA_ESTADO / EDA_RELAY_BASE: los mismos que lee `servidor/config.py`; así anda en Docker)
_ESTADO = os.environ.get("EDA_ESTADO") or os.path.join(RAIZ, "_trabajo", "servidor")
MAPA = os.path.join(_ESTADO, "relay.json")
# ★ lo que vio el PUNCH: conexión → [IP, puerto] PÚBLICOS de su 0x3006. Lo lee el server para darle a
#   cada par la dirección DIRECTA del otro (P2P sin relay, `servidor/relay.dir_udp`, MEDICIONES §40)
PUNCH = os.path.join(_ESTADO, "punch.json")
NAT = os.path.join(_ESTADO, "nat.json")      # ★ lo que vio de los 0x3002 (servidor/nat.py, MEDICIONES §53)
LOG = (os.path.join(_ESTADO, "relay.log") if os.environ.get("EDA_ESTADO")
       else os.path.join(RAIZ, "_trabajo", "broker", "relay.log"))
RELAY_BASE = int(os.environ.get("EDA_RELAY_BASE") or 26000)
MAC = re.compile(rb"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")
MAC16 = re.compile(rb"(?:[0-9A-F]\x00){2}(?::\x00(?:[0-9A-F]\x00){2}){5}")


def cambiar(datos, real_de, falsa_de, origen, destino):
    """El datagrama de `origen` para `destino`, con las identidades cambiadas: la MAC REAL del que
    manda → su identidad inventada; la inventada del que recibe → su MAC real. En texto y en
    UTF-16. Devuelve (datos, MAC vista del que manda o None)."""
    vista = None
    fo, fd = falsa_de.get(origen), falsa_de.get(destino)
    encontradas = [m.group(0) for m in MAC.finditer(datos)] + [
        m.group(0).decode("utf-16-le").encode() for m in MAC16.finditer(datos)]
    for t in encontradas:
        if fo and t.decode() not in falsa_de.values():
            vista = t
            break
    if vista and fo:
        datos = datos.replace(vista, fo.encode())
        datos = datos.replace(vista.decode().encode("utf-16-le"), fo.encode("utf-16-le"))
    rd = real_de.get(destino)
    if fd and rd:
        datos = datos.replace(fd.encode(), rd)
        datos = datos.replace(fd.encode("utf-16-le"), rd.decode().encode("utf-16-le"))
    return datos, vista


def es_local(d):
    """¿Es la dirección de respaldo «declarada» en el 0x100F (127.x: sólo sirve en la misma PC)?"""
    return d is None or d[0].startswith("127.")


def reconocer(datos, quien, destino, falsa_de, dir_de, sala_de=None):
    """★ (MEDICIONES §47) Un datagrama llega al puerto de `destino` desde una dirección que el relay no
    conoce: ¿de quién es? El ANFITRIÓN de la sala nunca manda su «registrame» (0x3006), sólo el que
    entra — medido en prod el 12-nov: 187 datagramas del anfitrión descartados y la partida cortada.
      1) por su IDENTIDAD: en sus saludos viaja su MAC (o la inventada); si es la de un jugador del
         mapa (que no sea el destino), es él;
      2) si no, por DESCARTE: si en la SALA del destino (`sala_de`, la escribe el server en relay.json;
         sin ella, todo el mapa) hay UN SOLO jugador (fuera del destino) sin dirección real (nunca
         registrado o sólo con la 127.x declarada), es él. ⚠ Medido en prod (2.ª prueba): sin la sala,
         con dos sin registrar en todo el server, el descarte no decidía y se perdió todo otra vez.
    Devuelve la conexión, o None (y el datagrama se sigue descartando)."""
    if es_local(quien):
        return None                                  # (en la misma PC, el 0x100F ya alcanza)
    ids = {m.group(0).decode() for m in MAC.finditer(datos)} | {
        m.group(0).decode("utf-16-le") for m in MAC16.finditer(datos)}
    for n, f in falsa_de.items():
        if n != destino and f in ids:
            return n
    en_sala = (sala_de or {}).get(destino) or []
    misma_ip = [n for n in en_sala if n != destino and n in falsa_de
                and not es_local(dir_de.get(n)) and dir_de[n][0] == quien[0]]
    if len(misma_ip) == 1:
        return misma_ip[0]
    juntos = en_sala or list(falsa_de)
    sin_dir = [n for n in juntos if n != destino and n in falsa_de and es_local(dir_de.get(n))]
    return sin_dir[0] if len(sin_dir) == 1 else None


def desde_misma_direccion(origen, destino, sala_de, socks):
    """★ (MEDICIONES §52) DOS PCs de la misma casa pueden salir por la MISMA IP y el MISMO puerto públicos
    (medido en prod: las dos en `x.x.x.x:57654`; el router reusa el puerto porque cada una le habla a
    otro puerto del relay). Entonces la dirección no dice de quién es el datagrama, y el relay lo tomaba
    por del DESTINO: se lo reenviaba a sí mismo (`1→1: 45.000` cada 30 s) y la sala quedaba en -1000.
    Lo que sí lo dice es el PUERTO del relay al que llegó: nadie le manda a su propio puerto. Si la
    dirección da el destino, el que manda es el otro de su sala (si hay uno solo)."""
    if origen is None or origen != destino:
        return origen
    otros = [n for n in (sala_de or {}).get(destino, []) if n != destino and n in socks]
    return otros[0] if len(otros) == 1 else None


def viejas(conocidos, nuevos, desde_de, cuando_de):
    """★ (21-nov) De las conexiones de las que el relay sabe algo (`conocidos`), las que hay que OLVIDAR al leer
    un relay.json nuevo (`nuevos`: conexión → «desde», el comienzo de su sesión en el server):
      · la que ya no está en el mapa: su sesión se cerró;
      · la que tiene OTRO «desde» que el que se conocía y cuya dirección se aprendió ANTES de ese «desde»: es
        una sesión nueva que reusa el número (lo aprendido después se queda: su 0x3006 puede llegar antes que
        el mapa). → [(conexión, motivo)]"""
    r = []
    for n in sorted(conocidos):
        if n not in nuevos:
            r.append((n, "se cerró su sesión"))
        elif nuevos[n] and nuevos[n] != desde_de.get(n) and cuando_de.get(n, 0) < nuevos[n] - 1:
            r.append((n, "sesión nueva con el mismo número"))
    return r


def main(ip="0.0.0.0"):
    punch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    punch.bind((ip, RELAY_BASE))
    socks = {}                       # conexión → su socket en el relay (RELAY_BASE + 1 + n)
    dir_de = {}                      # conexión → (IP, puerto) real del cliente
    de_dir = {}                      # (IP, puerto) → conexión
    real_de = {}                     # conexión → su MAC real (aprendida de sus saludos)
    falsa_de = {}
    sala_de = {}                     # conexión → los de su sala (del server)
    log = open(LOG, "a", encoding="utf-8")

    def anotar(t):
        log.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), t))   # (21-nov: con la fecha)
        log.flush()

    anotar("relay escuchando %s:%d (+1+n por jugador)" % (ip, RELAY_BASE))
    ultimo_mapa = 0
    desde_de = {}                    # ★ (21-nov) conexión → desde cuándo es ESA sesión (relay.json, «desde»)
    cuando_de = {}                   # conexión → cuándo se aprendió su dirección (dir_de)

    def olvidar(n, motivo):
        """★ (21-nov) la dirección aprendida de `n` era de OTRA sesión con el mismo número: fuera (memoria y
        punch.json). Medido en el server de prueba: punch.json tenía para la conexión 1 el puerto de una sesión
        de una hora antes, y el server se lo dio al invitado como dirección del anfitrión."""
        viejo = dir_de.pop(n, None)
        for d in [d for d, k in de_dir.items() if k == n]:
            del de_dir[d]
        real_de.pop(n, None)
        cuando_de.pop(n, None)
        if punch_vio.pop(n, None) is not None or viejo:
            anotar("jugador %d: %s → se olvida su dirección vieja%s" % (n, motivo, " (%s:%d)" % viejo if viejo else ""))
            escribir_punch()

    def escribir_punch():
        try:
            json.dump({str(k): [v[0], v[1], v[2]] for k, v in punch_vio.items()}, open(PUNCH, "w"))
        except OSError:
            pass
    # ★ cuántos datagramas de PARTIDA pasan por acá (con P2P directo tienen que ser 0): se anota
    #   un resumen cada 30 s, si hubo alguno
    reenviados, desde = {}, time.time()
    punch_vio = {}                   # conexión → (IP, puerto) de su último 0x3006 (sólo eso: punch.json)
    nat_vio, nat_escrito = {}, [0.0]  # huella del 0x3002 → [IP, puerto, cuándo] (nat.json, §53)
    try:
        json.dump({}, open(PUNCH, "w"))  # lo de una corrida anterior no vale (los números se reusan)
    except OSError:
        pass
    while True:
        if reenviados and time.time() - desde >= 30:
            anotar("reenviados en %d s: %s" % (time.time() - desde, ", ".join(
                "%d→%d: %d" % (o, d, k) for (o, d), k in sorted(reenviados.items()))))
            reenviados, desde = {}, time.time()
        try:
            if os.path.getmtime(MAPA) != ultimo_mapa:
                ultimo_mapa = os.path.getmtime(MAPA)
                mapa = {int(k): v for k, v in json.load(open(MAPA)).items()}
                falsa_de = {n: (v["falsa"] if isinstance(v, dict) else v) for n, v in mapa.items()}
                sala_de = {n: v.get("sala") or [] for n, v in mapa.items() if isinstance(v, dict)}
                # ★ (21-nov) las sesiones: la que se cerró y la que reusa un número se olvidan (lo aprendido
                #   DESPUÉS de que empezó la sesión nueva se queda: su 0x3006 puede llegar antes que el mapa)
                nuevos = {n: (v.get("desde") if isinstance(v, dict) else None) for n, v in mapa.items()}
                for n, motivo in viejas(set(dir_de) | set(punch_vio) | set(real_de), nuevos, desde_de, cuando_de):
                    olvidar(n, motivo)
                desde_de = nuevos
                for n, v in mapa.items():
                    # de respaldo (misma PC, o pública conocida del server): si todavía no tenemos una real
                    if isinstance(v, dict) and v.get("udp") and (n not in dir_de or es_local(dir_de.get(n))):
                        ip_n, puerto_n = v["udp"]
                        d = (socket.inet_ntoa(ip_n.to_bytes(4, "big")), puerto_n)
                        if dir_de.get(n) != d:
                            viejo = dir_de.get(n)
                            if viejo:
                                de_dir.pop(viejo, None)
                            dir_de[n], de_dir[d] = d, n
                            cuando_de[n] = time.time()
                            anotar("jugador %d declaró %s:%d" % (n, d[0], d[1]))
                for n in falsa_de:
                    if n not in socks:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.bind((ip, RELAY_BASE + 1 + n))
                        socks[n] = s
                anotar("mapa: %s" % sorted(falsa_de))
        except (OSError, ValueError):
            pass
        listos, _, _ = select.select([punch] + list(socks.values()), [], [], 0.5)
        for s in listos:
            datos, quien = s.recvfrom(65536)
            if s is punch and len(datos) >= 44 and datos[2:4] == b"\x02\x30":
                # ★ 0x3002 (MEDICIONES §53, `servidor/nat.py`): u16 largo · u16 0x3002 · la huella (40) ·
                #   u32 IP local · u16 puerto local, cada 0,4 s desde que el server le mandó el 0x0607 →
                #   de dónde llega = su dirección PÚBLICA (la de su NAT). Se anota por huella.
                h = datos[4:44].hex()
                if nat_vio.get(h, [None])[:2] != [quien[0], quien[1]]:
                    anotar("0x3002 de %s:%d (su dirección pública)" % quien)
                nat_vio[h] = [quien[0], quien[1], time.time()]
                if time.time() - nat_escrito[0] > 0.3:
                    nat_escrito[0] = time.time()
                    for k in [k for k, v in nat_vio.items() if time.time() - v[2] > 300]:
                        del nat_vio[k]
                    try:
                        json.dump(nat_vio, open(NAT, "w"))
                    except OSError:
                        pass
                continue
            if s is punch:
                # 0x3006: u16 largo · u16 0x3006 · u32 conexión → de dónde viene ese jugador
                if len(datos) >= 8 and datos[2:4] == b"\x06\x30":
                    n = int.from_bytes(datos[4:8], "little")
                    if dir_de.get(n) != quien:
                        anotar("jugador %d está en %s:%d" % (n, quien[0], quien[1]))
                        # ⚠ el server REUSA los números de conexión (`servidor/red.py`): uno nuevo
                        #   en el mismo número no tiene la MAC del anterior
                        real_de.pop(n, None)
                    viejo = dir_de.get(n)
                    if viejo and viejo != quien:
                        de_dir.pop(viejo, None)
                    dir_de[n], de_dir[quien] = quien, n
                    ahora_p = time.time()
                    cuando_de[n] = ahora_p
                    prev_p = punch_vio.get(n)
                    if not prev_p or prev_p[:2] != quien or ahora_p - prev_p[2] >= 5:
                        punch_vio[n] = (quien[0], quien[1], ahora_p)   # ★ (21-nov / 22-nov) con su hora y renueva vigencia
                        escribir_punch()
                continue
            destino = next(k for k, v in socks.items() if v is s)
            origen = desde_misma_direccion(de_dir.get(quien), destino, sala_de, socks)
            if origen is None:
                n = reconocer(datos, quien, destino, falsa_de, dir_de, sala_de)
                if n is not None and n in socks:
                    anotar("jugador %d reconocido en %s:%d (sin 0x3006: el anfitrión)" % (n, quien[0], quien[1]))
                    viejo = dir_de.get(n)
                    if viejo:
                        de_dir.pop(viejo, None)
                    dir_de[n], de_dir[quien], origen = quien, n, n
                    cuando_de[n] = time.time()
                    if not es_local(quien) and (punch_vio.get(n) or (None, None))[:2] != quien:
                        punch_vio[n] = (quien[0], quien[1], time.time())
                        escribir_punch()
            if origen is None or destino not in dir_de or origen not in socks:
                anotar("descartado: de %s:%d para %d (origen %s)" % (quien[0], quien[1], destino, origen))
                continue
            nuevo, vista = cambiar(datos, real_de, falsa_de, origen, destino)
            if os.environ.get("EDA_RELAY_SIN_CAMBIO"):       # ★ el control al revés
                nuevo = datos
            if vista and origen not in real_de:
                real_de[origen] = vista
                anotar("jugador %d: su MAC real aprendida (no se anota)" % origen)
            socks[origen].sendto(nuevo, dir_de[destino])
            reenviados[(origen, destino)] = reenviados.get((origen, destino), 0) + 1


def control():
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(bool(c))
    real = b"AA:BB:CC:DD:EE:01"
    falsa = {1: "02:00:00:00:00:01", 2: "02:00:00:00:00:02"}
    hola = b"\x15\x00\x54\xc3\x11\x00\x00\x00" + real
    nuevo, vista = cambiar(hola, {}, falsa, 1, 2)
    chequear("el saludo de 1 sale con SU identidad inventada", nuevo.endswith(falsa[1].encode()))
    chequear("el largo no cambia (17 caracteres por 17)", len(nuevo) == len(hola))
    chequear("y se aprende su MAC real", vista == real)
    otro = b"xx" + falsa[2].encode() + b"yy"
    nuevo, _ = cambiar(otro, {2: b"AA:BB:CC:DD:EE:02"}, falsa, 1, 2)
    chequear("la inventada del que RECIBE vuelve a ser su MAC real", nuevo == b"xxAA:BB:CC:DD:EE:02yy")
    u16 = b"\0" + real.decode().encode("utf-16-le")
    nuevo, _ = cambiar(u16, {}, falsa, 1, 2)
    chequear("también en UTF-16", falsa[1].encode("utf-16-le") in nuevo)
    nada = b"\x10\x00\x99\x99sin identidad"
    chequear("★ el revés: un datagrama sin MAC pasa IGUAL", cambiar(nada, {}, falsa, 1, 2)[0] == nada)
    nuevo, vista = cambiar(b"..." + falsa[2].encode(), {}, falsa, 1, 2)
    chequear("★ el revés: una identidad inventada no se toma por MAC real", vista is None)
    # ★ reconocer al anfitrión que nunca mandó su 0x3006 (MEDICIONES §47)
    # (la «real» es del rango que el RFC 7042 reserva para documentación: no es la MAC de nadie)
    mapa = {1: "02:00:00:00:00:01", 2: "00:00:5E:00:53:01", 3: "02:00:00:00:00:03"}
    dirs = {1: ("192.0.2.10", 57654), 2: ("127.0.0.1", 57654), 3: ("198.51.100.7", 51001)}
    afuera = ("203.0.113.5", 3228)
    saludo = b"\x15\x00\x54\xc3\x11\x00\x00\x00" + mapa[2].encode()
    chequear("anfitrión reconocido por la MAC de su saludo",
             reconocer(saludo, afuera, 1, mapa, dirs) == 2)
    chequear("…también en UTF-16", reconocer(b"\0" + mapa[2].encode("utf-16-le"), afuera, 1, mapa, dirs) == 2)
    chequear("sin identidad conocida: por descarte (el único sin dirección real)",
             reconocer(b"\x10\x00nada", afuera, 1, mapa, dirs) == 2)
    dos_sin = {1: dirs[1], 2: dirs[2], 3: None}
    chequear("★ el revés: dos sin dirección y sin identidad → nadie (se sigue descartando)",
             reconocer(b"\x10\x00nada", afuera, 1, mapa, dos_sin) is None)
    chequear("★ el revés: la identidad del DESTINO no cuenta como la del que manda",
             reconocer(b"..." + mapa[1].encode(), afuera, 1, mapa, dos_sin) is None)
    chequear("★ el revés: desde 127.x no se adivina (misma PC: alcanza lo declarado)",
             reconocer(saludo, ("127.0.0.1", 9), 1, mapa, dirs) is None)
    # ★ lo de la 2.ª prueba en prod: todos con identidad inventada y DOS sin registrar en el server
    #   (el anfitrión de esta sala y uno de OTRA sala) → con la sala, se decide
    sin_mac = {1: "02:00:00:00:00:01", 2: "02:00:00:00:00:02", 3: "02:00:00:00:00:03"}
    prod = {1: ("127.0.0.1", 57654), 2: ("127.0.0.1", 57654), 3: ("200.0.0.17", 57654)}
    salas = {2: [2, 3], 3: [2, 3], 1: []}
    otro = ("192.0.2.251", 57654)
    chequear("★ el revés (lo de prod): sin la sala, con dos sin registrar → nadie",
             reconocer(b"\x10\x00nada", otro, 3, sin_mac, prod) is None)
    chequear("con la sala del destino: el anfitrión de ESA sala (el 2)",
             reconocer(b"\x10\x00nada", otro, 3, sin_mac, prod, salas) == 2)
    chequear("★ cambio de puerto en vivo en la sala: misma IP pública que el compañero → se lo reconoce sin MAC",
             reconocer(b"\x10\x00movimiento", ("198.51.100.7", 52999), 1, mapa, dirs, {1: [1, 3], 3: [1, 3]}) == 3)
    chequear("★ el revés: desde otra IP que no es la de nadie de la sala y todos ya registrados → nadie",
             reconocer(b"\x10\x00movimiento", ("203.0.113.88", 52999), 1, mapa,
                       {1: dirs[1], 3: dirs[3]}, {1: [1, 3], 3: [1, 3]}) is None)
    # ★ dos PCs de la misma casa con la MISMA dirección pública (lo de prod, MEDICIONES §52)
    socks = {1: object(), 2: object()}
    chequear("misma dirección: lo que llega al puerto del 1 es del 2 (nadie se manda a sí mismo)",
             desde_misma_direccion(1, 1, {1: [1, 2], 2: [1, 2]}, socks) == 2)
    chequear("…y lo que llega al puerto del 2, del 1 (como siempre)",
             desde_misma_direccion(1, 2, {1: [1, 2], 2: [1, 2]}, socks) == 1)
    chequear("★ el revés: sin sala no se adivina (y no se reenvía a sí mismo)",
             desde_misma_direccion(1, 1, {}, socks) is None)
    chequear("★ el revés: con dos candidatos en la sala, tampoco",
             desde_misma_direccion(1, 1, {1: [1, 2, 3]}, {1: 0, 2: 0, 3: 0}) is None)
    # ★ (21-nov) las sesiones: lo aprendido de un número de conexión no pasa a la sesión siguiente
    t = 1_800_000_000.0
    chequear("viejas: la conexión que ya no está en el mapa se olvida (se cerró)",
             viejas({1, 2}, {2: t}, {2: t}, {2: t - 50}) == [(1, "se cerró su sesión")])
    chequear("viejas: OTRO «desde» y la dirección aprendida antes → se olvida (sesión nueva, mismo número)",
             viejas({1}, {1: t}, {1: t - 3600}, {1: t - 3000}) == [(1, "sesión nueva con el mismo número")])
    chequear("★ el revés: su 0x3006 llegó DESPUÉS del comienzo de la sesión nueva → se queda",
             viejas({1}, {1: t}, {1: t - 3600}, {1: t + 2}) == [])
    chequear("★ el revés: el mismo «desde» de siempre → no se toca nada",
             viejas({1}, {1: t}, {1: t}, {1: t - 3000}) == [])
    chequear("★ el revés: un mapa viejo sin «desde» → no se olvida por sesión", viejas({1}, {1: None}, {}, {}) == [])
    ok.append(control_sesiones(chequear))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def control_sesiones(chequear):
    """★ (21-nov) Con el relay DE VERDAD (otro proceso, UDP por 127.0.0.1, su estado en una carpeta temporal):
    lo del server de prueba (punch.json con el puerto de una sesión anterior del mismo número) no se repite."""
    import random
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp(prefix="relay_ctl_")
    base = random.randint(41000, 59000)
    mapa_f, punch_f, log_f = (os.path.join(tmp, x) for x in ("relay.json", "punch.json", "relay.log"))

    def mapa(d):
        json.dump(d, open(mapa_f + ".tmp", "w"))
        os.replace(mapa_f + ".tmp", mapa_f)
        os.utime(mapa_f, (time.time() + 0.01 * random.random(), time.time() + 0.01 * random.random()))

    def punch():
        try:
            return json.load(open(punch_f))
        except (OSError, ValueError):
            return None

    def esperar(cond, s=4.0):
        fin = time.time() + s
        while time.time() < fin:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def p3006(sock, n):
        sock.sendto(b"\x08\x00\x06\x30" + n.to_bytes(4, "little"), ("127.0.0.1", base))
    d1 = time.time()
    otro = {"falsa": "02:00:00:00:00:02", "sala": [], "desde": d1}
    mapa({"1": {"falsa": "02:00:00:00:00:01", "sala": [], "desde": d1}, "2": otro})
    env = dict(os.environ, EDA_ESTADO=tmp, EDA_RELAY_BASE=str(base))
    pr = subprocess.Popen([sys.executable, os.path.abspath(__file__), "127.0.0.1"], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    a, b, c = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3))
    for x in (a, b, c):
        x.bind(("127.0.0.1", 0))
    bien = []
    try:
        time.sleep(0.6)
        p3006(a, 1)
        p3006(c, 2)
        e = esperar(lambda: (punch() or {}).get("1") and (punch() or {}).get("2"))
        v = (punch() or {}).get("1")
        bien.append(bool(e and v[:2] == ["127.0.0.1", a.getsockname()[1]] and len(v) > 2 and v[2] >= d1 - 1))
        chequear("relay real: el 0x3006 queda en punch.json CON SU HORA (de esta sesión)", bien[-1])
        time.sleep(1.3)
        mapa({"1": {"falsa": "02:00:00:00:00:01", "sala": [], "desde": time.time()}, "2": otro})
        e = esperar(lambda: punch() is not None and "1" not in punch())
        txt = open(log_f, encoding="utf-8").read() if os.path.exists(log_f) else ""
        bien.append(bool(e and "sesión nueva con el mismo número" in txt and "2" in punch()))
        chequear("relay real: otra sesión con el número 1 → su dirección vieja se olvida (punch.json y log); la del 2 no", bien[-1])
        p3006(b, 1)
        e = esperar(lambda: ((punch() or {}).get("1") or [0, 0])[1] == b.getsockname()[1])
        bien.append(e)
        chequear("relay real: el 0x3006 de la sesión nueva (otro puerto) es el que queda", e)
        mapa({"1": {"falsa": "02:00:00:00:00:01", "sala": [], "desde": json.load(open(mapa_f))["1"]["desde"]}, "2": otro})
        time.sleep(1.0)
        bien.append(((punch() or {}).get("1") or [0, 0])[1] == b.getsockname()[1])
        chequear("★ el revés: el mismo mapa otra vez (misma sesión) → no se olvida nada", bien[-1])
        mapa({"2": otro})
        e = esperar(lambda: punch() is not None and "1" not in punch())
        txt = open(log_f, encoding="utf-8").read()
        bien.append(bool(e and "se cerró su sesión" in txt
                         and (punch().get("2") or [0, 0])[1] == c.getsockname()[1]))
        chequear("relay real: al cerrarse la sesión (fuera del mapa) se borra SÓLO la suya", bien[-1])
    finally:
        pr.kill()
        pr.wait()
        for x in (a, b, c):
            x.close()
    return all(bien)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "control":
        sys.exit(control())
    sys.exit(main(*a))
