r"""lobby_ancho -- ★ (24-nov, EXPERIMENTAL) EL LOBBY PANORÁMICO: el lobby de 2009 rearmado para pantallas anchas.

    py herramientas\lobby_ancho.py generar [--batalla]        # → %USERPROFILE%\EDA_pvp\ancho\<ancho>\… (1066 y 960)
    py herramientas\lobby_ancho.py instalar [carpeta_del_juego …]   # copia ancho\ junto al exe (por defecto: _trabajo\juego,
                                                                  #   y A / B de dos_clientes si existen)
    py herramientas\lobby_ancho.py quitar [carpeta_del_juego …]
    py herramientas\lobby_ancho.py control                    # las pruebas (cada una con su revés)

Qué hace (documentacion/LOBBY_PANORAMICO.md). El lobby es `menu/international/channellobby.xml` (posiciones absolutas en
un lienzo de 800×600) + un FONDO de una pieza (`ChannelLobby/lobby_bg.tga`) con los marcos metálicos pintados. La dll
(eda_traduccion.c · tr_abrir_ancho) sirve, sólo en pantallas anchas, un XML y un fondo para un lienzo de ANCHO×600
(1066 = 16:9, 960 = 16:10), y eda_escala2d.c usa ese lienzo mientras la escena es el lobby. Medido (24-nov, 1600×900):
el juego dibuja y hace clic con x > 800, NO con x < 0 → el lienzo ancho empieza en el borde izquierdo.

  · panel izquierdo (personaje, LOBBY, estadísticas, el 3D): igual, pegado a la izquierda (x 0–214);
  · columna derecha: los 7 botones de arriba en vertical (Shop, Inventory, Clan, Messenger, Options, Select Character,
    Exit), las MISMAS texturas y controles (mismo INDEX: mismos eventos, sonidos y estados);
  · centro: sube 58 (donde estaban los botones) y se ensancha hasta la columna. El fondo se arma por SEGMENTOS: las
    esquinas y uniones de los marcos quedan tal cual, sólo se estiran los tramos lisos (tipo nine-slice). Todas las
    posiciones del centro pasan por la misma función que el fondo (f para x, g para y): el dibujo y el clic coinciden;
  · barra de abajo: sus puntas tal cual, el tramo del medio estirado al ancho;
  · las ventanas emergentes del lobby: centradas en el lienzo.

El XML y el fondo son de Softnyx: NO se copian al repo. Se leen de TU Data.dat; si algo no está EXACTAMENTE como en el
Data.dat conocido, no se genera nada (como battle_ui.py).
"""
import io
import os
import re
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(AQUI, "pvp"))
sys.path.insert(0, os.path.join(RAIZ, "traduccion", "herramientas"))

XML = "menu/international/channellobby.xml"
FONDO = "image/ui_image/international/channellobby/lobby_bg.tga"
FONDO_NUEVO = "ancho_lobby_bg.tga"                           # (la dll sólo sirve channellobby\ancho_*)
ANCHOS = (1066, 960)                                         # = TR_ANCHOS de eda_traduccion.c
IZQ = 214            # el panel izquierdo (x < 214) queda igual
COL = 100            # la columna de botones de la derecha
SUBE = 58            # cuánto sube el centro (el lugar de los botones de arriba)
# los tramos del centro que se ESTIRAN (lisos en el fondo): el resto (esquinas, la unión chat / usuarios) queda igual
TRAMOS = ((250, 590), (625, 765))


def base():
    return os.environ.get("EDA_PVP_DIR") or os.path.join(os.path.expanduser("~"), "EDA_pvp")


def salida_por_defecto():
    return os.path.join(base(), "ancho")


# ── la geometría ── (una sola regla para el fondo y para el XML)
def extra(L):
    """lo que se ensancha el centro: el lienzo menos 800 y la columna"""
    return L - 800 - COL


def repartir(L):
    d = extra(L)
    largos = [b - a for a, b in TRAMOS]
    d0 = round(d * largos[0] / sum(largos))
    return (d0, d - d0)


def f(x, L):
    """x del lienzo de 800 → x del lienzo ancho (sólo para el centro: x ≥ IZQ)"""
    if x <= TRAMOS[0][0]:
        return x
    corrido = 0
    for (a, b), d in zip(TRAMOS, repartir(L)):
        if x <= a:
            return x + corrido
        if x <= b:
            return a + corrido + (x - a) * (b - a + d) / (b - a)
        corrido += d
    return x + corrido


def g(y):
    """y del centro: [58, 130] sube 58; [130, 330] se estira (la lista de salas, más alta); de 330 para abajo igual"""
    if y <= 130:
        return y - SUBE
    if y <= 330:
        return 130 - SUBE + (y - 130) * (200 + SUBE) / 200
    return y


def r(v):
    return int(round(v))


def columna(L, n):
    """el botón n (1..7) de la columna derecha: (x, y) — la misma regla que eda_escala2d.c · e2d_pan_en_boton"""
    return L - 91, 12 + (n - 1) * 80


# ── el XML ──
class NoConocido(Exception):
    pass


def _etiqueta(t, tag, index):
    """el comienzo de la etiqueta <tag … INDEX="index" …>: tiene que estar UNA vez"""
    pat = re.compile(r'<%s\s+(?:TYPE="\d+"\s+)?INDEX="%d"\s[^>]*>' % (tag, index))
    m = list(pat.finditer(t))
    if len(m) != 1:
        raise NoConocido("%s INDEX=%d: %d veces" % (tag, index, len(m)))
    return m[0]


def _attr(s, nombre):
    m = re.search(r'\s%s="([^"]*)"' % nombre, s)
    if not m:
        raise NoConocido("falta %s en %s" % (nombre, s[:60]))
    return m.group(1)


def _poner(s, **valores):
    for k, v in valores.items():
        s2, n = re.subn(r'(\s%s=")[^"]*(")' % k, lambda m, v=v: m.group(1) + str(v) + m.group(2), s, count=1)
        if not n:
            raise NoConocido("falta %s" % k)
        s = s2
    return s


def _cambiar(t, tag, index, fn):
    m = _etiqueta(t, tag, index)
    nuevo = fn(m.group(0))
    return t[:m.start()] + nuevo + t[m.end():]


def _num(s, k):
    return float(_attr(s, k))


def lobby_ancho(original, L, batalla=False):
    """El channellobby.xml para el lienzo L×600, o None si el original no es el conocido."""
    try:
        return _lobby_ancho(original.decode("utf-8"), L, batalla).encode("utf-8")
    except (NoConocido, UnicodeDecodeError) as e:
        print("  ⛔ %s" % e)
        return None


def _lobby_ancho(t, L, batalla):
    tex0 = 'TEXTURE ID="0" PATH="ChannelLobby\\\\lobby_bg.tga" TEXW="800" TEXH="600"'
    if t.count(tex0) != 1:
        raise NoConocido("la textura 0 (lobby_bg.tga) no es la conocida")
    t = t.replace(tex0, 'TEXTURE ID="0" PATH="ChannelLobby\\\\%s" TEXW="%d" TEXH="600"' % (FONDO_NUEVO, L))
    if batalla:                                              # (como battle_ui.py: el nombre de la pestaña Battle)
        viejo = 'INDEX="103" TEXID="43" X="0" Y="0" W="0" H="0" STRID="0"'
        if t.count(viejo) != 1:
            raise NoConocido("el control 103 no es el conocido")
        t = t.replace(viejo, viejo.replace('STRID="0"', 'STRID="40"'))

    # GLOBAL: el fondo, la columna de botones y el texto que corre abajo
    t = _cambiar(t, "BOARD", 0, lambda s: _poner(s, W=L))
    for n in range(1, 8):
        x, y = columna(L, n)
        t = _cambiar(t, "BUTTON", n, lambda s, x=x, y=y: _poner(s, X=x, Y=y))
    t = _cambiar(t, "ROLLINGTEXT", 8, lambda s: _poner(s, W=L))

    def mover(s, ancho=False, fin=None):
        x, y = _num(s, "X"), _num(s, "Y")
        v = {"X": r(f(x, L)), "Y": r(g(y))}
        if ancho:
            w = _num(s, "W")
            v["W"] = r(f(x + w if fin is None else fin, L)) - v["X"]
        return _poner(s, **v)

    # ROOMLIST: la lista (más ancha y más alta), sus columnas, los títulos, la pestaña, «Disponible» y los 3 botones
    m = _etiqueta(t, "LISTBOX", 100)
    fin_lista = t.index("</LISTBOX>", m.end())
    cab = m.group(0)
    x0, y0, w0, h0 = (_num(cab, k) for k in ("X", "Y", "W", "H"))
    if (x0, y0, w0, h0) != (236, 129, 536, 203) or _attr(cab, "ROWS") != "8":
        raise NoConocido("la lista de salas no es la conocida")
    nx, ny = r(f(x0, L)), r(g(y0))
    nw, nh = r(f(x0 + w0, L)) - nx, r(g(y0 + h0)) - r(g(y0))
    filas = r(8 * nh / h0)
    cab2 = _poner(cab, X=nx, Y=ny, W=nw, H=nh, ROWS=filas, SCRX=nw - 11, SCRH=nh)
    cuerpo = t[m.end():fin_lista]
    items = list(re.finditer(r'<ITEM [^>]*/>', cuerpo))
    if len(items) != 6:
        raise NoConocido("la lista de salas no tiene 6 columnas")
    borde, nuevos = x0, []
    for it in items:
        s = it.group(0)
        clave = "COLW" if ' COLW="' in s else "W"
        w = _num(s, clave)
        a, b = r(f(borde, L)), r(f(borde + w, L))
        nuevos.append(_poner(s, **{clave: b - a, "X": r(_num(s, "X") * (b - a) / w)}))
        borde += w
    for it, n in zip(reversed(items), reversed(nuevos)):
        cuerpo = cuerpo[:it.start()] + n + cuerpo[it.end():]
    t = t[:m.start()] + cab2 + cuerpo + t[fin_lista:]

    t = _cambiar(t, "BUTTONEXLIST", 101, mover)
    for n in range(104, 110):
        t = _cambiar(t, "BOARD", n, mover)
    t = _cambiar(t, "BUTTON", 110, mover)
    izq, der = r(f(x0, L)), r(f(x0 + w0, L))
    for i, n in enumerate((111, 112, 113)):
        centro = izq + (der - izq) * (2 * i + 1) / 6
        t = _cambiar(t, "BUTTON", n, lambda s, c=centro: _poner(s, X=r(c - _num(s, "W") / 2)))

    # CHAT: el texto y la escritura más anchos; las pestañas de canal y el combo, en su lugar
    t = _cambiar(t, "TEXT", 300, lambda s: _poner(mover(s, ancho=True), SCRX=r(f(_num(s, "X") + _num(s, "W"), L))
                                                  - r(f(_num(s, "X"), L)) - 11))
    t = _cambiar(t, "EDITBOX", 301, lambda s: mover(s, ancho=True))
    t = _cambiar(t, "BUTTONEXLIST", 302, mover)
    t = _cambiar(t, "EDITCOMBO", 311, mover)

    # USUARIOS: títulos, «Buscar usuario» (centrado donde estaba) y la lista (más ancha: la 2ª columna)
    t = _cambiar(t, "BUTTON", 400, mover)
    t = _cambiar(t, "BUTTON", 401, mover)
    t = _cambiar(t, "BUTTON", 402, lambda s: _poner(s, X=r(f(_num(s, "X") + _num(s, "W") / 2, L) - _num(s, "W") / 2)))
    m = _etiqueta(t, "LISTBOX", 403)
    cab = m.group(0)
    xu, wu = _num(cab, "X"), _num(cab, "W")
    nxu = r(f(xu, L))
    nwu = r(f(xu + wu, L)) - nxu
    cab2 = _poner(cab, X=nxu, W=nwu, SCRX=nwu - 11)
    fin = t.index("</LISTBOX>", m.end())
    cuerpo = t[m.end():fin]
    its = list(re.finditer(r'<ITEM [^>]*/>', cuerpo))
    if len(its) != 2:
        raise NoConocido("la lista de usuarios no tiene 2 columnas")
    ult = its[-1]
    cuerpo = cuerpo[:ult.start()] + _poner(ult.group(0), W=r(_num(ult.group(0), "W") + nwu - wu)) + cuerpo[ult.end():]
    t = t[:m.start()] + cab2 + cuerpo + t[fin:]

    # LAS VENTANAS EMERGENTES: centradas en el lienzo (sus controles son relativos a la ventana). Tres quedan donde
    # estaban (medido 24-nov, 1600×900, con la prueba de punto del mapa en eda_d3d9.c · selector_punto):
    #   · 500 (la búsqueda del mapa, Roadmap_Serch_bg) y 530 (el mapa de capítulos de «Crear Stage»): el juego ubica los
    #     STAGES del mapa respecto de la 500, en coordenadas absolutas de 800. Corrida 133, el stage «Inicio de la
    #     búsqueda» quedaba en x −116..−76 (original 17..57) y el doble clic no lo encontraba. En su lugar, el mapa es
    #     idéntico al original (tapa el panel izquierdo y el centro; la columna sigue a la vista);
    #   · 620 (el detalle de una sala): la pone el juego donde está el mouse.
    dx = (L - 800) // 2
    for n in (560, 590, 650, 680, 710, 740, 770, 800, 900, 920):
        t = _cambiar(t, "POPUP", n, lambda s: _poner(s, X=r(_num(s, "X") + dx)))
    return t


# ── el fondo ──
def _tramos_x(img, cortes, ancho_nuevo, L):
    """estira en x sólo los tramos de TRAMOS (en coordenadas del lienzo de 800, desde IZQ)"""
    from PIL import Image
    out = Image.new("RGBA", (ancho_nuevo, img.height))
    x = IZQ
    for a, b in cortes:
        dst0, dst1 = r(f(a, L)) - IZQ, r(f(b, L)) - IZQ
        pieza = img.crop((a - IZQ, 0, b - IZQ, img.height))
        if dst1 - dst0 != b - a:
            pieza = pieza.resize((dst1 - dst0, img.height), Image.LANCZOS)
        out.paste(pieza, (dst0, 0))
        x = b
    return out


def fondo_ancho(png_original, L):
    """El fondo de L×600 dentro de una textura de 2048×1024 (potencia de 2, como la original de 1024×1024)."""
    from PIL import Image, ImageEnhance, ImageFilter
    src = png_original.convert("RGBA").crop((0, 0, 800, 600))
    out = Image.new("RGBA", (L, 600), (0, 0, 0, 255))
    # la columna derecha: el pasillo del fondo, desenfocado y oscuro (sin marcos), como fondo de los botones
    col = src.crop((600, 0, 800, 566)).resize((COL, 566), Image.LANCZOS).filter(ImageFilter.GaussianBlur(5))
    col = ImageEnhance.Brightness(col.convert("RGB")).enhance(0.55).convert("RGBA")
    out.paste(col, (L - COL, 0))
    # el centro: primero en y (sube y la lista se estira), después en x (los tramos lisos)
    centro = src.crop((IZQ, 0, 800, 566))
    alto = Image.new("RGBA", centro.size)
    alto.paste(centro.crop((0, SUBE, centro.width, 130)), (0, 0))
    medio = centro.crop((0, 130, centro.width, 330)).resize((centro.width, r(g(330)) - r(g(130))), Image.LANCZOS)
    alto.paste(medio, (0, r(g(130))))
    alto.paste(centro.crop((0, 330, centro.width, 566)), (0, 330))
    cortes = [(IZQ, TRAMOS[0][0]), TRAMOS[0], (TRAMOS[0][1], TRAMOS[1][0]), TRAMOS[1], (TRAMOS[1][1], 800)]
    ancho = _tramos_x(alto, cortes, 800 + extra(L) - IZQ, L)
    out.paste(ancho, (IZQ, 0))
    # el panel izquierdo, igual
    izq = src.crop((0, 0, IZQ, 566))
    out.paste(izq, (0, 0))
    # la barra de abajo: sus puntas iguales, el medio estirado
    barra = src.crop((0, 566, 800, 600))
    nueva = Image.new("RGBA", (L, 34))
    nueva.paste(barra.crop((0, 0, 60, 34)), (0, 0))
    nueva.paste(barra.crop((60, 0, 740, 34)).resize((L - 120, 34), Image.LANCZOS), (60, 0))
    nueva.paste(barra.crop((740, 0, 800, 34)), (L - 60, 0))
    out.paste(nueva, (0, 566))
    tex = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    tex.paste(out, (0, 0))
    return tex, out


# ── ★ SELECT CHARACTER (characterselect.xml, escena 0x899740) ──
# Un solo marco grande pintado en el fondo: el encabezado «SELECT CHARACTER» centrado arriba, el panel del pasillo, la caja
# de oro/cash abajo a la derecha del panel y la franja violeta de abajo con las uniones entre los 4 botones.
SEL_XML = "menu/international/characterselect.xml"
SEL_FONDO = "image/ui_image/international/characterselect/eda_characterselect_bg.tga"
SEL_FONDO_NUEVO = "ancho_characterselect_bg.tga"
SEL_SLOTS_DER = 302      # la lista de slots: a 302 del borde derecho (como en 800: 498 + 259 + 43)
SEL_PJ_CENTRO = 291      # el centro del personaje y sus flechas en 800 (las flechas 150 + 311 + 122 → 150..433)
SEL_AVATAR_K = 1.5       # (medido) cuánto se corre el personaje en la interfaz por cada unidad de AVATAR X (al revés)


def sel_k(L):
    """la franja de abajo y sus botones se estiran parejo entre x 40 y L−40"""
    return (L - 80) / 720


def sel_fb(x, L):
    return 40 + (x - 40) * sel_k(L)


def sel_corrida(L):
    """cuánto se corre el personaje: al centro del lugar libre a la izquierda de los slots"""
    libre_fin = L - SEL_SLOTS_DER - 15
    return r((22 + libre_fin) / 2 - SEL_PJ_CENTRO)


def sel_ancho(original, L):
    """El characterselect.xml para el lienzo L×600, o None si el original no es el conocido."""
    try:
        return _sel_ancho(original.decode("utf-8"), L).encode("utf-8")
    except (NoConocido, UnicodeDecodeError) as e:
        print("  ⛔ %s" % e)
        return None


def _sel_ancho(t, L):
    tex0 = 'TEXTURE ID="0" PATH="CharacterSelect\\\\EDA_characterselect_bg.tga" TEXW="800" TEXH="600"'
    if t.count(tex0) != 1:
        raise NoConocido("la textura 0 (EDA_characterselect_bg.tga) no es la conocida")
    t = t.replace(tex0, 'TEXTURE ID="0" PATH="CharacterSelect\\\\%s" TEXW="%d" TEXH="600"' % (SEL_FONDO_NUEVO, L))
    t = _cambiar(t, "BOARD", 0, lambda s: _poner(s, W=L))
    for n in (1, 2):                                          # oro / cash (alineados a la derecha, en la caja)
        t = _cambiar(t, "BOARD", n, lambda s: _poner(s, X=r(_num(s, "X") + L - 800)))
    for n in (3, 4, 5, 6):                                    # los 4 botones de abajo, repartidos parejo
        t = _cambiar(t, "BUTTON", n, lambda s: _poner(s, X=r(sel_fb(_num(s, "X") + _num(s, "W") / 2, L) - _num(s, "W") / 2)))
    d = sel_corrida(L)
    for n in (7, 8):                                          # las flechas, con el personaje
        t = _cambiar(t, "BUTTON", n, lambda s: _poner(s, X=r(_num(s, "X") + d)))
    t = _cambiar(t, "AVATAR", 199, lambda s: _poner(s, X=r(_num(s, "X") - d / SEL_AVATAR_K)))
    t = _cambiar(t, "BUTTONEXLIST", 100, lambda s: _poner(s, X=L - SEL_SLOTS_DER))
    dx = (L - 800) // 2
    for n in (200, 300, 400, 500):                            # crear personaje (800×600) y los avisos: centrados
        t = _cambiar(t, "POPUP", n, lambda s: _poner(s, X=r(_num(s, "X") + dx)))
    return t


def _rebanar_x(img, cortes, L, ancho_orig=800):
    """[(a, b, estira)] en x del original → una tira de L de ancho: lo que no se estira queda igual, lo que se estira
    se reparte el sobrante en partes iguales"""
    from PIL import Image
    fijo = sum(b - a for a, b, e in cortes if not e)
    estiran = [(b - a) for a, b, e in cortes if e]
    sobra = L - fijo
    out = Image.new("RGBA", (L, img.height))
    x = 0
    total_est = sum(estiran)
    for a, b, e in cortes:
        p = img.crop((a, 0, b, img.height))
        if e:
            w = r(sobra * (b - a) / total_est)
            p = p.resize((max(1, w), img.height), Image.LANCZOS)
        out.paste(p, (x, 0))
        x += p.width
    return out


def sel_fondo(png_original, L):
    from PIL import Image
    src = png_original.convert("RGBA").crop((0, 0, 800, 600))
    out = Image.new("RGBA", (L, 600), (0, 0, 0, 255))
    arriba = _rebanar_x(src.crop((0, 0, 800, 52)), [(0, 60, 0), (60, 280, 1), (280, 520, 0), (520, 740, 1), (740, 800, 0)], L)
    out.paste(arriba, (0, 0))
    medio = _rebanar_x(src.crop((0, 52, 800, 490)), [(0, 40, 0), (40, 760, 1), (760, 800, 0)], L)
    out.paste(medio, (0, 52))
    abajo = _rebanar_x(src.crop((0, 490, 800, 600)), [(0, 40, 0), (40, 760, 1), (760, 800, 0)], L)
    out.paste(abajo, (0, 490))
    # las uniones entre los botones (una raya fina en y ~539, de botón a botón como en el original: x 17–43, 199–229 …)
    raya = src.crop((210, 533, 211, 546))
    xs = sorted(r(sel_fb(x + 79, L)) - 79 for x in (42, 228, 414, 600))
    tramos = [(17, xs[0] + 1)] + [(xs[i] + 157, xs[i + 1] + 1) for i in range(3)] + [(xs[-1] + 157, L - 17)]
    for a, b in tramos:
        if b > a:
            out.paste(raya.resize((b - a, raya.height)), (a, 533))
    # el pasillo: agrandado PAREJO (sin deformar) hasta cubrir el panel más ancho, recortado arriba y abajo por igual
    x0, y0, x1, y1 = 28, 58, 772, 484
    arte = src.crop((x0, y0, x1, y1))
    nw = L - 2 * x0
    nh = r(arte.height * nw / arte.width)
    arte = arte.resize((nw, nh), Image.LANCZOS)
    corte = (nh - (y1 - y0)) // 2
    out.paste(arte.crop((0, corte, nw, corte + y1 - y0)), (x0, y0))
    # la caja de oro / cash, a la derecha (como en 800)
    caja = src.crop((618, 434, 762, 480))
    out.paste(caja, (618 + L - 800, 434))
    tex = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    tex.paste(out, (0, 0))
    return tex, out


# ── generar / instalar ──
def leer(ruta, cliente=None):
    import battle_ui as B
    import dos_clientes as D
    return B.leer_original(cliente or D.ORIGEN, ruta)


def generar(salida=None, batalla=False, cliente=None):
    from PIL import Image
    salida = salida or salida_por_defecto()
    xml = leer(XML, cliente)
    fondo = Image.open(io.BytesIO(leer(FONDO, cliente)))
    sel_xml = leer(SEL_XML, cliente)
    sel_png = Image.open(io.BytesIO(leer(SEL_FONDO, cliente)))
    for L in ANCHOS:
        nuevo = lobby_ancho(xml, L, batalla)
        if nuevo is None:
            raise SystemExit("⛔ %s no es el conocido: no se genera nada" % XML)
        d = os.path.join(salida, str(L))
        dx = os.path.join(d, *XML.split("/"))
        os.makedirs(os.path.dirname(dx), exist_ok=True)
        open(dx, "wb").write(nuevo)
        tex, vista = fondo_ancho(fondo, L)
        dt = os.path.join(d, "image", "ui_image", "international", "channellobby", FONDO_NUEVO)
        os.makedirs(os.path.dirname(dt), exist_ok=True)
        tex.save(dt)
        vista.save(os.path.join(salida, "vista_%d.png" % L))
        # Select Character
        nuevo = sel_ancho(sel_xml, L)
        if nuevo is None:
            raise SystemExit("⛔ %s no es el conocido: no se genera nada" % SEL_XML)
        dx = os.path.join(d, *SEL_XML.split("/"))
        open(dx, "wb").write(nuevo)
        tex, vista = sel_fondo(sel_png, L)
        dt = os.path.join(d, "image", "ui_image", "international", "characterselect", SEL_FONDO_NUEVO)
        os.makedirs(os.path.dirname(dt), exist_ok=True)
        tex.save(dt)
        vista.save(os.path.join(salida, "vista_sel_%d.png" % L))
        print("· %d×600 → %s (lobby y Select Character)" % (L, d))
    return salida


def carpetas_por_defecto():
    import dos_clientes as D
    c = [os.path.join(RAIZ, "_trabajo", "juego")]
    c += [os.path.join(D.BASE, i) for i in "ABCDEFGH" if os.path.isdir(os.path.join(D.BASE, i))]
    return [x for x in c if os.path.exists(os.path.join(x, "EDA_limpio.exe"))]


def instalar(carpetas, salida=None):
    salida = salida or salida_por_defecto()
    if not all(os.path.exists(os.path.join(salida, str(L), *XML.split("/"))) for L in ANCHOS):
        raise SystemExit("⛔ primero: py herramientas\\lobby_ancho.py generar")
    for c in carpetas:
        dst = os.path.join(c, "ancho")
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        for L in ANCHOS:
            shutil.copytree(os.path.join(salida, str(L)), os.path.join(dst, str(L)))
        print("· %s" % dst)


def quitar(carpetas):
    for c in carpetas:
        dst = os.path.join(c, "ancho")
        if os.path.isdir(dst):
            shutil.rmtree(dst)
            print("· quitado %s" % dst)


# ── control ──
def control(cliente=None):
    bien = mal = 0

    def chequear(que, ok):
        nonlocal bien, mal
        print("  %s %s" % ("✅" if ok else "❌", que))
        if ok:
            bien += 1
        else:
            mal += 1

    for L in ANCHOS:
        chequear("f(%d): el panel izquierdo y el borde del centro no se mueven" % L, f(IZQ, L) == IZQ and f(250, L) == 250)
        chequear("f(%d): el borde derecho del centro llega a la columna (%d)" % (L, L - COL), r(f(800, L)) == L - COL)
        chequear("f(%d): crece siempre (nada se cruza)" % L, all(f(x + 1, L) > f(x, L) for x in range(IZQ, 800)))
        a = [columna(L, n) for n in range(1, 8)]
        chequear("columna %d: 7 botones dentro del lienzo y sin pisarse" % L,
                 all(x >= 0 and x + 82 <= L and y + 64 <= 566 for x, y in a) and all(a[i + 1][1] - a[i][1] >= 64 for i in range(6)))
    chequear("g: sube 58 arriba, igual desde 330", g(66) == 8 and g(330) == 330 and g(600) == 600)
    # el revés: un XML que no es el conocido → None
    chequear("el revés: un XML cualquiera → nada", lobby_ancho(b"<MENUCONTROLS></MENUCONTROLS>", 1066) is None)
    try:
        xml = leer(XML, cliente)
    except SystemExit as e:
        print("  (sin Data.dat: %s)" % e)
        xml = None
    if xml is not None:
        for L in ANCHOS:
            n = lobby_ancho(xml, L)
            chequear("con el Data.dat: el XML de %d se genera" % L, n is not None)
            if n is None:
                continue
            t = n.decode("utf-8")
            import xml.etree.ElementTree as ET
            try:
                raiz = ET.fromstring(t.encode("utf-8"))
                chequear("%d: el XML sigue bien formado" % L, True)
            except ET.ParseError as e:
                chequear("%d: el XML sigue bien formado (%s)" % (L, e), False)
                continue
            fuera = []
            for grupo in raiz.iter("GROUP"):
                for e in grupo:
                    for c in e:
                        if c.tag in ("POPUP",) or "X" not in c.attrib or "W" not in c.attrib:
                            continue
                        x, w = float(c.get("X")), float(c.get("W"))
                        if x < 0 or x + w > L:
                            fuera.append("%s %s" % (c.tag, c.get("INDEX")))
            chequear("%d: ningún control fuera del lienzo (x ≥ 0, x+W ≤ %d) %s" % (L, L, fuera or ""), not fuera)
            pops = [p for p in raiz.iter("POPUP") if p.get("INDEX") != "620"]
            chequear("%d: las ventanas emergentes dentro del lienzo" % L,
                     all(0 <= float(p.get("X")) and float(p.get("X")) + float(p.get("W")) <= L for p in pops))
            bot = sorted((float(b.get("X")), float(b.get("W"))) for b in raiz.iter("BUTTON") if b.get("INDEX") in ("111", "112", "113"))
            chequear("%d: Buscar / Crear / Entrar sin pisarse" % L, all(bot[i][0] + bot[i][1] < bot[i + 1][0] for i in range(2)))
            chequear("%d: el control 103 queda sin nombre (sin --batalla)" % L, 'INDEX="103" TEXID="43" X="0" Y="0" W="0" H="0" STRID="0"' in t)
        chequear("con --batalla: la pestaña nombrada", b'STRID="40"' in (lobby_ancho(xml, 1066, batalla=True) or b""))
        import xml.etree.ElementTree as ET
        sx = leer(SEL_XML, cliente)
        for L in ANCHOS:
            n = sel_ancho(sx, L)
            chequear("Select Character %d: se genera" % L, n is not None)
            if n is None:
                continue
            raiz = ET.fromstring(n)
            bots = {b.get("INDEX"): b for b in raiz.iter("BUTTON")}
            abajo = sorted(float(bots[i].get("X")) for i in ("3", "4", "5", "6"))
            gaps = [abajo[i + 1] - abajo[i] for i in range(3)]
            chequear("Select Character %d: los 4 botones de abajo parejos y dentro (%s)" % (L, abajo),
                     abajo[0] >= 0 and abajo[-1] + 158 <= L and max(gaps) - min(gaps) <= 1 and min(gaps) > 158)
            lista = next(raiz.iter("BUTTONEXLIST"))
            chequear("Select Character %d: los slots pegados a la derecha (x %s)" % (L, lista.get("X")),
                     float(lista.get("X")) + 259 == L - 43)
            fl = [float(bots[i].get("X")) for i in ("7", "8")]
            chequear("Select Character %d: las flechas a la izquierda de los slots" % L,
                     fl[0] >= 22 and fl[1] + 122 < float(lista.get("X")))
            pops = list(raiz.iter("POPUP"))
            chequear("Select Character %d: las ventanas dentro del lienzo" % L,
                     all(0 <= float(p.get("X")) and float(p.get("X")) + float(p.get("W")) <= L for p in pops))
        chequear("Select Character: el revés (un XML cualquiera → nada)", sel_ancho(b"<MENUCONTROLS/>", 1066) is None)
    print("\n→ %s (%d bien · %d mal)" % ("TODO BIEN" if not mal else "HAY ERRORES", bien, mal))
    return mal == 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "generar":
        generar(batalla="--batalla" in a)
    elif a[0] == "instalar":
        instalar([x for x in a[1:] if not x.startswith("--")] or carpetas_por_defecto())
    elif a[0] == "quitar":
        quitar([x for x in a[1:] if not x.startswith("--")] or carpetas_por_defecto())
    elif a[0] == "control":
        sys.exit(0 if control() else 1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
