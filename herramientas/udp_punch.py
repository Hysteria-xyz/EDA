r"""udp_punch -- el server UDP de «punch» que espera el cliente: escuchar y ANOTAR qué le mandan.

El server de juego le dice a cada cliente, en el `0x1010` (la respuesta al «quién soy»), a qué
IP:puerto UDP tiene que ir a hacer el *hole punching* (`0x549762` → `0x6218F0(ip, puerto)` →
`cuenta+0x740`, NetTrace «[Punch UDP IP, PORT]»). Con 0.0.0.1:0 (lo que mandábamos) nadie se
encuentra y el ping de la sala queda en -1000 ms. Este oyente (sin UAC: no es WinDivert) recibe en
127.0.0.1:25001, anota cada datagrama con su origen en `_trabajo/broker/udp.log` y, por ahora,
NO contesta (primero hay que ver qué piden).

    py herramientas\udp_punch.py [puerto=25001]
"""
import os
import socket
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(RAIZ, "_trabajo", "broker", "udp.log")


def hexa(d):
    return "\n".join("    %04x  %-48s |%s|" % (o, d[o:o + 16].hex(" "),
                                              "".join(chr(c) if 32 <= c < 127 else "." for c in d[o:o + 16]))
                     for o in range(0, len(d), 16))


def main():
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 25001
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", puerto))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s escuchando UDP 127.0.0.1:%d\n" % (time.strftime("%H:%M:%S"), puerto))
        f.flush()
        while True:
            d, quien = s.recvfrom(65536)
            f.write("%s ← %s:%d  %d bytes\n%s\n" % (time.strftime("%H:%M:%S"), quien[0], quien[1],
                                                   len(d), hexa(d)))
            f.flush()
            # 🟡 PARA MEDIR (EDA_PUNCH_ECO=1): a cada 0x3006 contestar un 0x3007 con el mismo
            #   cuerpo, para ver con Frida a qué manejador lo manda el ruteador UDP (`0x4E57EC`)
            if os.environ.get("EDA_PUNCH_ECO") and d[2:4] == b"\x06\x30":
                r = d[0:2] + b"\x07\x30" + d[4:]
                s.sendto(r, quien)
                f.write("%s → %s:%d  0x3007 (eco)\n" % (time.strftime("%H:%M:%S"), quien[0], quien[1]))
                f.flush()


if __name__ == "__main__":
    sys.exit(main())
