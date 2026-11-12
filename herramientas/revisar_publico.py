r"""revisar_publico -- que en el repo PÚBLICO no entre nada privado (corre en GitHub en cada PR, 13-nov).

No sabe cuáles son los datos privados de nadie (este archivo es público): busca lo que TIENE FORMA de
privado y no está en la lista de lo permitido.

  · una IP PÚBLICA que no sea de las conocidas: los servers de Softnyx de 2009, las de documentación
    (192.0.2.x, 198.51.100.x, 203.0.113.x) y las de prueba que ya usan las pruebas. Así cae la IP de
    un VPS o la de una casa sin tener que escribirla acá.
  · una IP de una red de CASA (192.168.N.x con N distinto de 0 y 1, 172.16–31.x): en los textos se
    escribe 192.168.x.x.
  · una MAC de VERDAD (las inventadas tienen prendido el bit de «local»: 02:…, AA:…; y la de
    documentación, 00:00:5E:00:53:xx).
  · una ruta de la carpeta de un usuario de Windows o de Linux, y un correo (salvo los noreply).

    python herramientas/revisar_publico.py [carpeta]   # revisa (sale 1 si encuentra algo)
    python herramientas/revisar_publico.py control     # ★ con su revés

Si te marca algo: para una IP de prueba usá 192.0.2.x / 198.51.100.x / 203.0.113.x; para la de tu casa,
192.168.x.x; para una MAC, 02:00:00:00:00:0N; para una ruta, una relativa al proyecto.
"""
import ipaddress
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# las IP públicas que SÍ pueden aparecer
PERMITIDAS = {
    "218.145.66.187", "187.66.145.218",       # el Broker de Softnyx de 2009 (y al revés, como entero)
    "211.233.43.45",                          # otro server de Softnyx de 2009
    "1.1.1.1", "8.8.8.8",                     # DNS públicos conocidos
    "1.0.0.127",                              # 127.0.0.1 escrito al revés (orden de red)
    "200.1.1.1", "190.2.2.2", "181.4.4.4", "190.9.9.9", "200.0.0.17",   # inventadas de las pruebas
}
DOCUMENTACION = [ipaddress.ip_network(r) for r in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
_US = "Us" + "ers"            # (armado por partes: entero, el control de publicar.py frenaría este archivo)
RUTAS = re.compile(r"(?i)\b[A-Z]:\\" + _US + r"\\|/c/" + _US + "/|/home/[a-z]")
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
IP = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
BINARIOS = (".exe", ".dll", ".png", ".jpg", ".dat", ".zip", ".pdb", ".xml")


def ip_mala(texto):
    """Por qué esa IP no puede ir (None = puede)."""
    try:
        ip = ipaddress.ip_address(texto)
    except ValueError:
        return None                                           # (una versión 2026.11.13.2, etc.)
    if texto in PERMITIDAS or any(ip in r for r in DOCUMENTACION):
        return None
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved or str(ip).startswith("0."):
        return None
    if ip.is_private:
        a, b, c, _ = (int(x) for x in texto.split("."))
        if a == 192 and b == 168 and c in (0, 1):
            return None                                       # las genéricas de los ejemplos
        if a == 10:
            return None
        return "una IP de una red de casa (escribí 192.168.x.x)"
    return "una IP pública que no está entre las conocidas"


def mac_mala(texto):
    primero = int(texto[:2], 16)
    if primero & 0x02 or texto.upper().replace("-", ":").startswith("00:00:5E:00:53"):
        return None                                           # inventada (local) o de documentación
    return "una MAC de verdad (usá 02:00:00:00:00:0N)"


def revisar_texto(t):
    """[(número de línea, qué)] de lo que tiene forma de privado."""
    malo = []
    for n, linea in enumerate(t.splitlines(), 1):
        if RUTAS.search(linea):
            malo.append((n, "una ruta de la carpeta de un usuario"))
        for m in CORREO.finditer(linea):
            if "noreply" not in m.group(0) and "example" not in m.group(0):
                malo.append((n, "un correo"))
        for m in IP.finditer(linea):
            q = ip_mala(m.group(0))
            if q:
                malo.append((n, q))
        for m in MAC.finditer(linea):
            q = mac_mala(m.group(0))
            if q:
                malo.append((n, q))
    return malo


def revisar(raiz=RAIZ):
    malos = []
    for base, dirs, archivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in (".git", "_trabajo", "__pycache__")]
        for a in archivos:
            if a.lower().endswith(BINARIOS) or a == "revisar_publico.py":   # (sus ejemplos del control)
                continue
            ruta = os.path.join(base, a)
            try:
                t = open(ruta, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for n, que in revisar_texto(t):
                malos.append("%s:%d  %s" % (os.path.relpath(ruta, raiz), n, que))
    return malos


def control():
    casos = [
        ("server en 127.0.0.1:25900, prueba con 192.0.2.10 y 192.168.x.x", 0),
        ("el Broker de 2009 en 218.145.66.187, versión 2026.11.13.2", 0),
        ("MAC inventada 02:00:00:00:00:01 y la de documentación 00:00:5E:00:53:01", 0),
        ("★ revés: el VPS en 203.0.114.9", 1),
        ("★ revés: mi casa 192.168.44.20", 1),
        ("★ revés: mi MAC B0:12:34:56:78:9A", 1),
        ("★ revés: C:\\%s\\alguien\\juego" % _US, 1),
        ("★ revés: escribime a alguien@correo.com", 1),
    ]
    ok = True
    for texto, esperado in casos:
        hay = len(revisar_texto(texto))
        bien = hay == esperado
        ok &= bien
        print("  %s %s → %d" % ("✅" if bien else "⛔", texto, hay))
    print("→ TODO BIEN" if ok else "→ ⛔ algo falló")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "control":
        sys.exit(0 if control() else 1)
    m = revisar(sys.argv[1] if len(sys.argv) > 1 else RAIZ)
    for x in m:
        print("⛔", x)
    print("✅ nada privado" if not m else "⛔ %d datos con forma de privados: sacalos antes de fusionar" % len(m))
    sys.exit(1 if m else 0)
