r"""servidor/salida.py -- ★ (21-nov) LO QUE SALE MIENTRAS UN JUEGO CARGA LA STAGE.

Medido en la prueba entre dos casas del 21-nov (server de prueba, 05:35 UTC) y en el exe:
  · mientras carga, el cliente atiende el TCP desde el HILO DE CARGA (`0x5345C0`): por cada mensaje, si el
    comando está entre 0x1003 y 0x100B llama a `+0x10` de la escena de carga = «Thread DoEnd!!» (0x530980 →
    0x74E150: pone la bandera de fin del hilo). El 0x1005 (el chat, y los «[MSN]» del Messenger) cae ahí.
  · la largada (0x105E) la atiende SÓLO ese hilo (PROTOCOLO §5.10). Si el hilo ya terminó, el 0x105E no se
    procesa nunca y el hilo principal queda para siempre en `while (!this[0xE0]) Sleep(1)` (0x500643):
    «NOW LOADING», sin mandar ni el «estoy vivo».
  · Al anfitrión le llegó un 0x1005 (261 B) a las 05:35:52, ENTRE su 0x105F y el 0x105E de las 05:35:53 (el
    invitado tardó 1 s más en cargar). Al invitado, el 0x105E antes que el 0x1005: entró. En las partidas de
    dos del 18-nov que anduvieron, el 0x1005 llegó siempre DESPUÉS del 0x105E.
Entonces: desde el 0x104F (empieza a cargar) hasta su 0x105E, a ese jugador no se le manda nada de 0x1003 a
0x100B: se guarda y sale, en el mismo orden, justo después de su 0x105E (o si vuelve al lobby).
"""
import time

from servidor.estado import PARTIDAS

PELIGROSOS = range(0x1003, 0x100C)             # los que terminan el hilo de carga (0x5345C0)
TOPE = 200                                      # mensajes guardados como mucho por jugador
VENCE = 180.0                                   # s: si la carga no termina en esto, se sueltan igual


def ordenar(n_defecto, resp, ahora=None):
    """resp = [(comando, cuerpo, ms de espera[, destino])] → lo que se manda YA, en orden (con su destino).
    Los mensajes con espera no se tocan acá: se vuelven a pasar por acá cuando vence su espera."""
    ahora = time.monotonic() if ahora is None else ahora
    sale = []
    for r in resp:
        c, cuerpo, espera = r[0], r[1], r[2]
        d = r[3] if len(r) > 3 else n_defecto
        if espera:
            sale.append((c, cuerpo, espera, d))
            continue
        p = PARTIDAS.get(d)
        if p is None:
            sale.append((c, cuerpo, 0, d))
            continue
        if p.get("cargando") and ahora - p["cargando"] > VENCE:
            sale += _soltar(p, d, "la carga pasó de %d s" % VENCE)
        if p.get("cargando") and c in PELIGROSOS:
            g = p.setdefault("diferidos", [])
            if len(g) >= TOPE:
                g.pop(0)
            g.append((c, cuerpo))
            continue
        sale.append((c, cuerpo, 0, d))
        if c == 0x104F:
            p["cargando"] = ahora
        elif c in (0x105E, 0x1075, 0x1069) and p.get("cargando"):
            sale += _soltar(p, d, "largada" if c == 0x105E else "salió de la stage")
    return sale


def _soltar(p, d, motivo):
    p.pop("cargando", None)
    g = p.pop("diferidos", [])
    if g:
        print("#%s carga: %d mensaje(s) 0x1003–0x100B guardados durante la carga, enviados después (%s)"
              % (d, len(g), motivo), flush=True)
    return [(c, cuerpo, 0, d) for c, cuerpo in g]
