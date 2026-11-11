"""mirar_dns.py — anota cada NOMBRE que la máquina sale a buscar por DNS.

Para qué: el juego seguramente busca un nombre de softnyx.net que ya no existe; como la búsqueda
falla, nunca abre un TCP y `proxy_mitm.py DESCUBRIR=1` no ve nada. Esto ve la PREGUNTA al DNS.

Sólo mira: WinDivert en modo SNIFF (copia los paquetes, no los retiene ni los puede perder).
Mira la máquina ENTERA (no hay proceso a nivel de red): va a salir también el ruido del resto.
Se ELEVA solo (UAC). Se corta cerrando su ventana o con Ctrl+C.

Salida: _trabajo/descubrir/dns_vistos.txt  (hora, nombre, tipo) — una línea por nombre nuevo.
Control al revés: con la herramienta corriendo, `Resolve-DnsName eda.softnyx.net` TIENE que
aparecer en la salida; si no aparece, la máquina resuelve por otro lado (DoH) y esto no sirve.
"""
import ctypes
import os
import struct
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA_DIR = os.path.join(RAIZ, "_trabajo", "descubrir")
SALIDA = os.path.join(SALIDA_DIR, "dns_vistos.txt")
TIPOS = {1: "A", 28: "AAAA", 5: "CNAME", 33: "SRV", 16: "TXT", 15: "MX", 12: "PTR", 65: "HTTPS"}


def leer_pregunta(dns):
    """(nombre, tipo) de la 1ª pregunta de un paquete DNS, o None."""
    if len(dns) < 12 or struct.unpack(">H", dns[4:6])[0] < 1:
        return None
    i, partes = 12, []
    while i < len(dns):
        n = dns[i]
        if n == 0:
            i += 1
            break
        if n & 0xC0 or i + 1 + n > len(dns):
            return None
        partes.append(dns[i + 1:i + 1 + n].decode("ascii", "replace"))
        i += 1 + n
    if i + 2 > len(dns):
        return None
    tipo = struct.unpack(">H", dns[i:i + 2])[0]
    return ".".join(partes), TIPOS.get(tipo, str(tipo))


def mirar():
    import pydivert
    os.makedirs(SALIDA_DIR, exist_ok=True)
    filtro = "outbound and udp.DstPort == 53"
    vistos = set()
    with open(SALIDA, "a", encoding="utf-8", buffering=1) as f, \
            pydivert.WinDivert(filtro, flags=pydivert.Flag.SNIFF) as w:
        f.write("=== %s  arranca (filtro: %s)\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), filtro))
        print("[dns] mirando. Cerrá esta ventana para terminar. Salida:", SALIDA, flush=True)
        for pkt in w:
            try:
                q = leer_pregunta(bytes(pkt.payload or b""))
                if q and q not in vistos:
                    vistos.add(q)
                    linea = "%s  %-5s %s" % (time.strftime("%H:%M:%S"), q[1], q[0])
                    f.write(linea + "\n")
                    print(linea, flush=True)
            except Exception:
                pass


def main():
    if ctypes.windll.shell32.IsUserAnAdmin():
        try:
            mirar()
        except KeyboardInterrupt:
            pass
        return
    params = '"%s"' % os.path.abspath(__file__)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, RAIZ, 1)
    print("[uac] %s" % ("corriendo en una ventana nueva y elevada" if rc > 32
                        else "NO se elevó (código %d)" % rc))


if __name__ == "__main__":
    main()
