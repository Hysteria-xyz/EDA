r"""paquete_broker -- abrir y armar los paquetes TCP del Broker de EDA. La base del server.

★ MEDIDO el 10-nov (corrida 15, `documentacion/MEDICIONES.md`), con `espiar_broker.py` (los bytes
  que llegan) y `espiar_cripto.py` (breakpoints en el objeto de cifrado del propio exe):

    ┌──────────────── cabecera, 8 bytes, EN CLARO ─────────────────┐┌── cifrado ──┐
    │ u16 largo │ u16 ?      │ u16 largo cifrado │ u16 versión     ││  AES-128    │
    │ = total-4 │ = 00 0c    │ = múltiplo de 16  │ = 0x0202        ││  ECB        │
    └───────────┴────────────┴───────────────────┴─────────────────┘└─────────────┘

    lo cifrado son bloques de 16, y CADA bloque es  [B6 A2 C2 A5] + 12 bytes de datos
    (la constante 0xA5C2A2B6 que el exe le pasa al crear el contexto, `0x6242E0`).
    Por eso el exe redondea a 12 (`0x750BE0`): 12 de datos por bloque de 16.

    los datos (el mensaje) empiezan con  [u16 largo = datos-4][u16 comando]  — el primero que
    manda el cliente es el comando 0x0604, de 44 bytes. Lo que sobra hasta múltiplo de 12 es
    basura de la pila (no se limpia): ⇒ al ARMAR da igual qué se pone ahí.

    la clave AES (16 bytes) la carga `0x4E7871 → 0x74C900 → 0x7A99F0(clave, 16, 3)`; el contexto
    queda con Nk=4 y 10 rondas = AES-128, y la expansión de la clave coincide con la de AES.

    ★★ Y LA CLAVE ES  MD5(el archivo del exe + UN byte 0x00)  (corrida 16): `0x4E781D`
       `GetModuleFileNameA` → `0x624CB0` → `0x624990`, que abre el exe, lee el archivo entero en
       un buffer de **tamaño + 1** y le saca el MD5 a todo el buffer (el byte de más queda en
       cero); devuelve el hexa en mayúsculas y `0x624CB0` lo pasa a 16 bytes con "%2x".
       Comprobado con DOS exes distintos: cada clave medida en memoria = md5(exe + 00) de su exe.
       ⇒ es un control de integridad: un cliente tocado deriva otra clave. ⇒ el server tiene que
       conocer el hash del exe de cada cliente. Si el archivo no se puede leer, usa la de
       RESPALDO (`0x624D1D`).

    ✅ El server contesta con la MISMA clave (medido: el cliente descifra lo que le mandamos).
    🟡 Sin entender: el `00 0c`. Y hay además un RSA de juguete (`srand(0x2A4)`, primos < 200,
       n = 181·29) que el exe carga en el mismo objeto pero que estos mensajes NO usan. El campo
       que llamamos «versión» es en realidad el MODO de cifrado: 0x0201 / **0x0202 = AES** /
       0x0203 = el RSA de juguete (`0x74D260`).

    py herramientas\paquete_broker.py abrir _trabajo\broker\con_002.bin
    py herramientas\paquete_broker.py control
"""
import glob
import os
import struct
import sys

from Crypto.Cipher import AES

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURAS = os.path.join(RAIZ, "_trabajo", "broker")

MAGIA = struct.pack("<I", 0xA5C2A2B6)                         # medida en 0x6242E0, arg1
VERSION = 0x0202                                              # medida en 0x74C8C0 (= modo AES)
CAMPO_2 = 0x0C00                                              # 🟡 constante, sin entender
# la que usa el exe si no puede leerse a sí mismo (`0x624D1D`, byte a byte)
CLAVE_RESPALDO = bytes.fromhex("7b210ddf49170c85857b7b67c1177b7a")


def clave_de_exe(ruta):
    """★ La clave AES que deriva ese exe: MD5(archivo + b"\\0")."""
    import hashlib
    return hashlib.md5(open(ruta, "rb").read() + b"\0").digest()


# ★ Las claves de los dos exes que juega la gente, FIJAS: así un server SIN los exes (Linux, Docker)
#   abre igual sus paquetes. Son md5(exe + 00) de:
#     · el EDA.exe de 2009 (md5 f0b12e6cddf3efdd0676b6491efe46be): `jugar.py --original`
#     · exe/EDA_limpio.exe (md5 0799387e23cadd355888bd712143f2d5): `jugar.py` (por defecto)
#     · ★ el limpio NUEVO, sin ASProtect en código vivo (md5 ba6f91dbb89faf400bc73612295ae5ef,
#       MEDICIONES §56): ya se acepta, para probarlo antes de la mudanza (el launcher sigue con 0799387e)
#   ⚠ Si se rearma el limpio, cambia su clave: se agrega acá (o en EDA_CLAVES, sin tocar el código).
CLAVES_FIJAS = {
    "EDA.exe de 2009": bytes.fromhex("a57ca836788301a9aff975159cbcbe97"),
    "EDA_limpio.exe (0799387e)": bytes.fromhex("2921cf268c0d66325864aec9ab4fc7f4"),
    "EDA_limpio.exe (ba6f91db, sin ASProtect)": bytes.fromhex("e43b8a4f9664e4145c14d16eec99de0e"),
}
_CACHE_CLAVES = {}


def claves_conocidas():
    """{nombre: clave}: las FIJAS, las de EDA_CLAVES (hex separadas por coma), las de los exes que
    haya a mano (el original, `exe/` y las copias de `_trabajo/juego`) y la de respaldo. El server
    prueba con todas: la magia dice cuál es la buena. (El md5 de cada exe se calcula UNA vez por
    fecha de archivo: antes se releían ~10 exes de 2 MB por paquete.)"""
    out = dict(CLAVES_FIJAS)
    for i, h in enumerate(x.strip() for x in os.environ.get("EDA_CLAVES", "").split(",") if x.strip()):
        out["EDA_CLAVES[%d]" % i] = bytes.fromhex(h)
    for ruta in [os.path.join(RAIZ, "cliente", "EDA.exe")] + sorted(
            glob.glob(os.path.join(RAIZ, "exe", "*.exe"))
            + glob.glob(os.path.join(RAIZ, "_trabajo", "juego", "*.exe"))):
        try:
            t = os.path.getmtime(ruta)
        except OSError:
            continue
        if _CACHE_CLAVES.get(ruta, (None,))[0] != t:
            _CACHE_CLAVES[ruta] = (t, clave_de_exe(ruta))
        out[os.path.relpath(ruta, RAIZ)] = _CACHE_CLAVES[ruta][1]
    out["(respaldo)"] = CLAVE_RESPALDO
    return out


class PaqueteMalo(ValueError):
    pass


def abrir(p, clave=None):
    """bytes del cable -> dict con la cabecera y los DATOS (sin la magia). Valida todo.
    Sin `clave`, prueba las conocidas y dice cuál anduvo (`r["clave"]`, `r["de"]`)."""
    if clave is None:
        for nombre, c in claves_conocidas().items():
            try:
                r = abrir(p, c)
                r["de"] = nombre
                return r
            except PaqueteMalo:
                continue
        raise PaqueteMalo("ninguna clave conocida lo abre (¿un exe que no está a mano?)")
    if len(p) < 8:
        raise PaqueteMalo("menos de 8 bytes")
    largo, campo2, largo_c, version = struct.unpack_from("<HHHH", p, 0)
    if largo != len(p) - 4:
        raise PaqueteMalo("largo %d y el paquete mide %d" % (largo, len(p)))
    if largo_c != len(p) - 8 or largo_c % 16:
        raise PaqueteMalo("largo cifrado %d no cuadra" % largo_c)
    claro = AES.new(clave, AES.MODE_ECB).decrypt(p[8:])
    datos = b""
    for i in range(0, len(claro), 16):
        if claro[i:i + 4] != MAGIA:
            raise PaqueteMalo("el bloque %d no empieza con la magia (¿otra clave?)" % (i // 16))
        datos += claro[i + 4:i + 16]
    msj_largo, comando = struct.unpack_from("<HH", datos, 0)
    return {"campo2": campo2, "version": version, "datos": datos, "clave": clave,
            "comando": comando, "mensaje": datos[:msj_largo + 4]}


def armar(datos, clave, campo2=CAMPO_2, version=VERSION, relleno=b"\0"):
    """DATOS -> bytes del cable. `datos` se completa a múltiplo de 12 con `relleno`."""
    if len(datos) % 12:
        datos += (relleno * 12)[:12 - len(datos) % 12]
    claro = b"".join(MAGIA + datos[i:i + 12] for i in range(0, len(datos), 12))
    cif = AES.new(clave, AES.MODE_ECB).encrypt(claro)
    return struct.pack("<HHHH", len(cif) + 4, campo2, len(cif), version) + cif


def wtexto(s, bytes_):
    """Texto UTF-16 de ancho fijo con su 0 al final (el exe copia con `wcscpy`, `0x7DDBF9`)."""
    b = s.encode("utf-16-le")[:bytes_ - 2]
    return b + b"\0" * (bytes_ - len(b))


def cuerpo_anuncio(titulo, texto, a=0, b=0):
    """★ El 0x0709: [u8 hay anuncio][448 bytes] (`0x549820` lee 0x1C1 y, si el primero es 1,
    se lo pasa a `0x53DDB0`). Lo de adentro, medido en `0x53DDB0`:
        +0x00 u32 🟡 ?        +0x04 texto[40 bytes] (🟡 el título)
        +0x2C u32 🟡 ?        +0x30 texto[400 bytes] (🟡 el cuerpo)"""
    d = struct.pack("<I", a) + wtexto(titulo, 40) + struct.pack("<I", b) + wtexto(texto, 400)
    assert len(d) == 448
    return b"\x01" + d


def registro_servidor(nombre, ip="127.0.0.1", puerto=25001, idx=1, b1=1, estado=1, b2=0,
                      usuarios=0, maximo=500, texto2="", abierto=1):
    """★ Un registro de 96 bytes del 0x070B, con el orden en que lo copia `0x53E300`:
        +0x00 u8  🟡 (idx)        +0x01 u16 🟡           +0x03 texto[40] = el NOMBRE (visto)
        +0x2B u32 = IP del server de juego  ┐ ENTER (`0x549300`) desconecta del Broker y
        +0x2F u16 = su puerto               ┘ conecta ahí; si alguno es 0, no hace nada
        +0x31 u8  🟡 (ENTER se lo pasa a esa conexión)
        +0x32 u8  🟡              +0x33 u16 = MÁXIMO     +0x35 u16 = JUGADORES
                                  (`0x516DD1`: jugadores/máximo < 0,3 / < 0,6 / < lleno / [Full])
        +0x37 texto[40] 🟡        +0x5F u8 = ABIERTO (con 0, ENTER muestra el error 5)
    ⚠⚠ La IP va en orden de RED (los bytes como se leen: 218,145,66,187), NO como en el 0x0607:
       ENTER (`0x744750`) le hace `inet_ntoa` directo. Con el orden de host, el tester apretó ENTER y
       el cliente se fue a 187.66.145.218, esperó ~28 s y dijo «Can't Connect to server» (medido).
       El puerto sí va en orden de host: después le hacen `ntohs`.
    ⚠ Al principio +0x33/+0x35 estaban al revés: 500 de máximo y 7 jugadores salía [Full]."""
    ip_n = struct.unpack("<I", bytes(int(x) for x in ip.split(".")))[0]   # orden de RED
    d = (struct.pack("<BH", idx, b1) + wtexto(nombre, 40) + struct.pack("<IHBBHH", ip_n, puerto,
         estado, b2, maximo, usuarios) + wtexto(texto2, 40) + struct.pack("<B", abierto))
    assert len(d) == 96, len(d)
    return d


def registro_personaje(nombre, lugar=0, clase=1, ident=1, nivel=1, marcas=False, extra=None,
                       partidas=0, abandonos=0, stats=(0, 0, 0, 0, 0, 0)):
    """★ Un personaje: 186 bytes (0xBA), con los offsets en que lo copian `0x53F740` (hasta
    +0x51) y `0x53F850` (el resto). +0x00/+0x24/+0x5E/+0x6E son vtables del objeto: en el
    mensaje se ignoran.
        +0x04 u8  ★ CLASE (desde 1)   +0x05 texto[26] NOMBRE   +0x1F u8 ★ NIVEL
        +0x20 u32 🟡 id               +0x28 u16 🟡             +0x2A texto[40] 🟡
        +0x52 u8 ★ LUGAR   +0x53 u32 ★ partidas   +0x57 u32 ★ abandonos   +0x5B/5C/5D u8 🟡
        +0x62 +0x64 +0x66 +0x68 +0x6A u16 ★ Strength Constitution Dexterity Intelligence Wisdom
        +0x6C u16 🟡   +0x72.. 9×u32 = el EQUIPO (cada uno se busca en la base de ítems)
    ★ NIVEL: el lobby y la pantalla de personajes hacen `movzx eax, byte [pj+0x1F]` → "%dLV"
      (`0x4EF93E`, `0x4F9888`; medido con un breakpoint en `_woutput`, `0x7F1043`).
    ⚠ `extra` se aplica AL FINAL: antes se aplicaba primero y los campos fijos lo pisaban (así
      se midió mal que +0x1F, +0x20 y +0x28 «no cambiaban nada»).
    ★ Medido con el depurador (corrida 16 §8): para dibujar el modelo, `0x4F9610` arma un flujo
      con [+0x04][+0x1F][nombre][9 ítems] y el objeto del modelo (`0x57F9A0`) usa
      **+0x04 − 1** como índice en una tabla. Con +0x04 = 0 el índice es -1 y el juego muere
      en `0x4ED92D` (dos veces, con ECX = la cabecera de un bloque del heap)."""
    d = bytearray(0xBA)
    if marcas:
        # 🟡 para identificar campos EN PANTALLA: cada uno con un valor reconocible
        d[0x2A:0x52] = wtexto("TXT2A", 40)
        d[0x52] = 33
        struct.pack_into("<II", d, 0x53, 4444, 5555)
        d[0x5B], d[0x5C], d[0x5D] = 66, 77, 88
        struct.pack_into("<6H", d, 0x62, 101, 102, 103, 104, 105, 106)
        ident = 11
    d[0x04] = clase
    d[0x05:0x1F] = wtexto(nombre, 26)
    d[0x1F] = nivel
    struct.pack_into("<I", d, 0x20, ident)
    if not marcas:
        d[0x52] = lugar
        struct.pack_into("<II", d, 0x53, partidas, abandonos)
        struct.pack_into("<5H", d, 0x62, *stats[:5])
    for off, val in (extra or {}).items():          # para medir un campo por vez: AL FINAL
        d[off:off + len(val)] = val
    return bytes(d)


def cuerpo_servidores(registros):
    """★ El 0x070B: [u16 resultado = 1][u8 cuántos] + cuántos × 96 (`0x5494C0`)."""
    return struct.pack("<HB", 1, len(registros)) + b"".join(registros)


def trozos(stream):
    """Corta un stream TCP en paquetes (cada uno mide su u16 + 4)."""
    out, i = [], 0
    while i + 2 <= len(stream):
        n = struct.unpack_from("<H", stream, i)[0] + 4
        out.append(stream[i:i + n])
        i += n
    return out


def mensaje(comando, cuerpo):
    """[u16 largo del cuerpo][u16 comando][cuerpo] — el formato de los datos."""
    return struct.pack("<HH", len(cuerpo), comando) + cuerpo


def hexa(d):
    return "\n".join("    %04x  %-48s |%s|" % (i, " ".join("%02x" % c for c in d[i:i + 16]),
                                              "".join(chr(c) if 32 <= c < 127 else "."
                                                      for c in d[i:i + 16]))
                     for i in range(0, len(d), 16))


def control():
    """★ El control y su revés, contra las capturas REALES del juego (no contra ejemplos hechos a
    mano): abrir y volver a armar cada una tiene que dar los MISMOS bytes, y con otra clave tiene
    que rechazarse."""
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))

    # ★ la fórmula de la clave contra las claves MEDIDAS en memoria (`espiar_cripto.py`, en
    #   `0x7A99F0`): dos exes distintos, dos claves distintas. El esperado no sale de la fórmula.
    medidas = {"EDA_limpio_494.exe": "f5dda6fb559514fb880cb360fcdfa0b2",   # corrida 15
               "EDA_limpio_499.exe": "95d314eb1da27dcd01a2e81f5493833d"}  # corrida 16
    for exe, medida in medidas.items():
        ruta = os.path.join(RAIZ, "_trabajo", "juego", exe)
        if medida and os.path.exists(ruta):
            chequear("md5(%s + 00) = la clave medida en memoria" % exe,
                     clave_de_exe(ruta).hex() == medida, medida[:12] + "…")
    # el revés de la fórmula: SIN el byte de más no da
    ruta = os.path.join(RAIZ, "_trabajo", "juego", "EDA_limpio_494.exe")
    if os.path.exists(ruta):
        import hashlib
        chequear("…y sin el 00 del final NO da (el revés)",
                 hashlib.md5(open(ruta, "rb").read()).hexdigest() != medidas["EDA_limpio_494.exe"])

    caps = sorted(glob.glob(os.path.join(CAPTURAS, "con_*.bin")))
    reales = []
    for f in caps:
        for p in trozos(open(f, "rb").read()):
            try:
                abrir(p)
                reales.append((os.path.basename(f), p))
            except PaqueteMalo:
                pass                   # p. ej. la marca del control de espiar_broker.py
    chequear("hay mensajes del juego para probar", reales, "(%d, de %d capturas)"
             % (len(reales), len(caps)))
    bien = 0
    for nombre, p in reales:
        a = abrir(p)
        if armar(a["datos"], a["clave"], a["campo2"], a["version"]) == p:
            bien += 1
        else:
            chequear("%s: abrir → armar devuelve los mismos bytes" % nombre, False)
    chequear("abrir → armar devuelve los MISMOS bytes en todos", bien == len(reales),
             "(%d de %d; claves: %s)" % (bien, len(reales),
                                         ", ".join(sorted(set(abrir(p)["de"] for _, p in reales)))))
    # el revés
    if reales:
        p = reales[0][1]
        try:
            abrir(p, clave=bytes(16))
            chequear("con OTRA clave se rechaza", False, "(¡lo aceptó!)")
        except PaqueteMalo as e:
            chequear("con OTRA clave se rechaza", True, "(%s)" % e)
        roto = p[:20] + bytes([p[20] ^ 1]) + p[21:]
        try:
            abrir(roto)
            chequear("un bit cambiado en lo cifrado se rechaza", False)
        except PaqueteMalo as e:
            chequear("un bit cambiado en lo cifrado se rechaza", True, "(%s)" % e)
    # y uno armado por nosotros, de ida y vuelta
    m = mensaje(0x1234, b"hola EDA")
    chequear("armar → abrir de un mensaje nuestro",
             abrir(armar(m, CLAVE_RESPALDO))["mensaje"] == m)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    if not a or a[0] == "control":
        return control()
    if a[0] == "abrir":
        for f in a[1:]:
            for p in trozos(open(f, "rb").read()):
                r = abrir(p)
                print("%s  %d bytes  clave de %s  campo2 %04x  modo %04x  comando %04x  "
                      "mensaje %d bytes" % (os.path.basename(f), len(p), r["de"], r["campo2"],
                                            r["version"], r["comando"], len(r["mensaje"])))
                print(hexa(r["mensaje"]))
        return 0
    if a[0] == "claves":
        for n, c in claves_conocidas().items():
            print("  %-24s %s" % (n, c.hex()))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
