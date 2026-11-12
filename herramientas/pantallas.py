r"""pantallas -- ¿en qué pantalla está el juego? Mira una foto de su ventana (sin tocarlo) y la compara con la
«huella» de cada pantalla: una zona que la distingue (el cartel del título, la ventana del centro),
achicada a 16×6 en grises. Así el piloto ESPERA cada pantalla antes de apretar, en vez de apretar con
tiempos fijos (con tiempos fijos, a 60 cuadros/s el piloto apretaba «Enter Lobby» cuando el juego ya
estaba en el lobby, y ahí ese lugar es «Search User»: quedaba un diálogo abierto. 11-nov).

    py herramientas\pantallas.py <pid>          # dice la pantalla de ese juego (y las distancias)

Las huellas salen de fotos de cada pantalla (medidas el 11-nov): cada una da 0 contra sí misma y 17 o
más contra las otras; «crear» y «selector» comparten el fondo y los separa el cartel «CREATE STAGE».
Las zonas esquivan el contador de cuadros de nuestra d3d9.dll (arriba a la izquierda).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pantalla: (zona en el área de cliente 800×600, huella 16×6 en grises)
HUELLAS = {
    'lobby': ((70, 32, 170, 50),
        [55, 161, 78, 196, 184, 204, 202, 177, 223, 106, 204, 41, 0, 0, 0, 0, 47, 195, 105, 203, 174, 194, 207, 172, 229, 89, 165, 23, 0, 0, 0, 0, 21, 116, 71, 95, 73, 101, 102, 85, 118, 34, 69, 8, 0, 0, 0, 0, 11, 21, 18, 16, 15, 21, 22, 25, 23, 15, 22, 7, 2, 2, 3, 8, 166, 169, 149, 136, 148, 165, 164, 168, 154, 130, 141, 159, 147, 132, 120, 130, 201, 182, 163, 162, 174, 191, 160, 190, 182, 157, 140, 178, 180, 160, 154, 158]),
    'sala': ((40, 35, 190, 58),
        [26, 193, 207, 204, 146, 166, 206, 212, 117, 75, 208, 199, 195, 202, 171, 6, 6, 50, 51, 49, 32, 38, 48, 52, 25, 14, 53, 49, 45, 49, 46, 0, 75, 79, 83, 89, 113, 100, 91, 109, 113, 103, 94, 104, 90, 81, 80, 87, 100, 127, 151, 163, 188, 161, 162, 179, 173, 176, 144, 168, 165, 151, 119, 121, 35, 27, 22, 22, 25, 23, 22, 24, 24, 23, 23, 23, 21, 20, 27, 39, 3, 13, 15, 13, 12, 13, 12, 11, 11, 11, 11, 9, 10, 9, 11, 8]),
    # (el botón redondo «Close» de arriba a la derecha: el círculo «Chapter 1» de la izquierda lo tapa
    #  nuestro contador de cuadros — medido 11-nov, la pantalla salía «otra»)
    'selector': ((690, 5, 790, 60),
        [116, 82, 62, 97, 90, 89, 58, 53, 49, 50, 60, 85, 92, 84, 70, 116, 90, 74, 101, 77, 55, 75, 107, 117, 119, 112, 96, 62, 59, 84, 99, 87, 65, 106, 67, 57, 112, 116, 68, 53, 51, 53, 74, 116, 89, 54, 80, 97, 102, 85, 54, 108, 98, 20, 51, 76, 82, 73, 43, 26, 103, 84, 56, 102, 116, 60, 70, 101, 25, 17, 38, 39, 40, 37, 37, 11, 41, 84, 62, 74, 113, 54, 66, 89, 23, 3, 20, 23, 20, 20, 15, 1, 33, 73, 64, 71]),
    'crear': ((330, 10, 490, 30),
        [59, 19, 21, 47, 14, 25, 31, 32, 30, 30, 31, 30, 31, 31, 30, 30, 92, 87, 87, 91, 83, 86, 88, 88, 88, 88, 88, 88, 87, 88, 93, 93, 93, 90, 90, 90, 91, 89, 92, 93, 90, 90, 91, 90, 93, 85, 73, 82, 52, 83, 88, 78, 76, 93, 59, 53, 88, 80, 72, 86, 63, 44, 60, 70, 51, 99, 129, 110, 101, 106, 60, 53, 108, 98, 116, 119, 64, 38, 54, 55, 37, 97, 95, 108, 80, 87, 52, 40, 91, 75, 106, 111, 55, 26, 50, 44]),
    'partida': ((125, 15, 240, 45),
        [2, 10, 15, 16, 8, 7, 37, 42, 59, 49, 51, 42, 33, 34, 34, 68, 26, 107, 137, 125, 57, 21, 47, 34, 81, 56, 36, 34, 26, 27, 27, 72, 99, 174, 186, 123, 89, 56, 62, 62, 65, 62, 62, 63, 65, 63, 64, 65, 33, 84, 94, 79, 105, 110, 84, 85, 85, 86, 87, 88, 89, 90, 91, 94, 50, 24, 25, 20, 61, 54, 44, 46, 47, 47, 48, 48, 49, 50, 51, 51, 185, 178, 121, 14, 4, 22, 23, 23, 23, 23, 23, 32, 35, 32, 38, 70]),
    'dialogo': ((265, 250, 530, 300),
        [29, 28, 30, 32, 33, 34, 34, 34, 34, 34, 31, 31, 30, 28, 26, 24, 37, 35, 37, 38, 39, 40, 40, 40, 40, 39, 74, 76, 68, 67, 66, 74, 29, 19, 22, 23, 24, 25, 25, 25, 24, 30, 64, 23, 63, 84, 54, 19, 35, 29, 30, 32, 32, 33, 33, 33, 33, 36, 56, 26, 35, 37, 29, 31, 33, 35, 37, 39, 40, 41, 41, 40, 41, 41, 38, 39, 34, 32, 31, 33, 26, 28, 31, 33, 34, 35, 35, 35, 35, 35, 34, 32, 30, 29, 27, 26]),
}
UMBRAL = 8.0          # 0 contra sí misma, ≥ 17 contra las otras (medido)
# dónde cerrar el diálogo de «Search User» (su botón Cancel) — y dónde está «Search User» en el lobby,
#   que es lo que lo abre por error
CANCEL_DIALOGO = (400, 358)


def foto(pid):
    """La imagen del área de cliente de ese juego (800×600), o None."""
    import foto_juego as F
    v = F.ventanas_de(pid)
    if not v:
        return None
    h, _, _, w, hh = v[0]
    return F.foto(h, w, hh).convert("RGB").crop((0, 0, 800, 600))


def distancias(im):
    g = im.convert("L")
    out = {}
    for n, (zona, ref) in HUELLAS.items():
        h = list(g.crop(zona).resize((16, 6)).getdata())
        out[n] = sum(abs(a - b) for a, b in zip(h, ref)) / len(ref)
    return out


def cual(pid=None, im=None):
    """'lobby', 'dialogo' (lobby con el diálogo de Search User), 'selector', 'crear', 'sala',
    'partida' o 'otra'."""
    im = im or foto(pid)
    if im is None:
        return "sin ventana"
    d = distancias(im)
    if d["dialogo"] < UMBRAL and d["lobby"] < UMBRAL:
        return "dialogo"
    if d["crear"] < UMBRAL:
        return "crear"
    for n in ("lobby", "sala", "selector", "partida"):
        if d[n] < UMBRAL:
            return n
    return "otra"


def esperar(pid, quiero, segundos=15.0, cada=0.4):
    """Espera hasta que el juego esté en alguna de las pantallas `quiero` (str o tupla). Devuelve la
    pantalla en la que está al final (sea o no la pedida)."""
    if isinstance(quiero, str):
        quiero = (quiero,)
    t0 = time.time()
    p = cual(pid)
    while p not in quiero and time.time() - t0 < segundos:
        time.sleep(cada)
        p = cual(pid)
    return p


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    pid = int(sys.argv[1])
    im = foto(pid)
    print("pantalla:", cual(im=im))
    print({k: round(v, 1) for k, v in distancias(im).items()})
