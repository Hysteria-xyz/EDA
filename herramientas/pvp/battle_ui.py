r"""battle_ui -- ★ PvP, la pestaña «Battle» del lobby (documentacion/PVP_BATTLE_UI.md §9, paso 3). EXPERIMENTAL.

    py herramientas\pvp\battle_ui.py generar      # → %USERPROFILE%\EDA_pvp\battle_ui\menu\international\channellobby.xml
    py herramientas\pvp\battle_ui.py control      # el control (y su revés), con el Data.dat de _trabajo\juego

El layout del lobby es de Softnyx: NO se copia al repo. Se lee de TU Data.dat (traduccion/herramientas/
desempacar_data_dat.py) y se cambia UNA cosa: el `STRID="0"` del control 103 (`ChannelLobby_BattleModeBtn`,
channellobby.xml:126) por `STRID="40"`, el texto que el propio juego trae para eso («~PVP Battle~»; en la traducción
«Batalla PvP»). Si la línea no está EXACTAMENTE como en el Data.dat conocido, no genera nada.

Se instala con: py herramientas\pvp\dos_clientes.py recursos instalar <la carpeta> [herramientas\pvp\arena]
⚠ Sólo para las instalaciones de prueba: la pestaña con nombre todavía NO hace nada (paso 4), y la regla es no
mostrar a los jugadores algo que aparente funcionar.
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, "traduccion", "herramientas"))
import dos_clientes as D                                     # noqa: E402

RUTA = "menu/international/channellobby.xml"
ANTES = (b'<BUTTONEX INDEX="103" TEXID="43" X="0" Y="0" W="0" H="0" STRID="0" FONTSIZE="14" TXTOFFX="59" TXTOFFY="8" '
         b'FONTCOLOR="0xff64e4ff" CHECK="1" ALIGN="2"  EXPLAIN="ChannelLobby_BattleModeBtn" >')
DESPUES = ANTES.replace(b'STRID="0"', b'STRID="40"')
SALIDA = os.path.join(D.BASE, "battle_ui")


def leer_original(cliente=D.ORIGEN, ruta=RUTA):
    from pathlib import Path
    from desempacar_data_dat import SolFS
    with SolFS(Path(cliente) / "Data.dat", Path(cliente) / "LTMsg.dll") as sfs:
        for p, ino, _, _ in sfs.walk():
            if p.lower() == ruta:
                return sfs.read_file(ino)
    raise SystemExit("⛔ %s no está en el Data.dat de %s" % (ruta, cliente))


# ★ (24-nov) PASO 5: la sala con EQUIPOS. Medido (sesión 20261124-083333): la FILA de la sala es el NÚMERO de jugador
#   (rui, número 0, volvió a entrar después de kai y quedó arriba, en los dos juegos). El equipo = número % 2 (el
#   mismo que usa la arena para los grupos): filas 301/303/305/307 rojas, 302/304/306/308 azules. Las barras son la
#   del juego (waitroom_bar_userlist.tga) teñidas: mismo relieve y transparencia.
SALA = "menu/international/waitroom_mission.xml"
BARRA = "image/ui_image/international/waitroom_mission/waitroom_bar_userlist.tga"
TEX_11 = b'<TEXTURE ID="11" PATH="WaitRoom_Mission\\\\waitroom_bar_userlist.tga" TEXW="341" TEXH="93"'
TEX_NUEVAS = {32: ("pvp_bar_rojo.tga", (1.55, 0.5, 0.45)), 33: ("pvp_bar_azul.tga", (0.45, 0.7, 1.6))}


def tenir(img, mult):
    """La barra gris del juego, teñida: cada píxel toma su brillo y lo multiplica por el color; el alfa queda."""
    from PIL import Image
    r, g, b, a = img.convert("RGBA").split()
    luz = Image.merge("RGB", (r, g, b)).convert("L")
    canales = [luz.point(lambda v, m=m: min(255, int(v * m + (8 if m > 1 else 0)))) for m in mult]
    return Image.merge("RGBA", canales + [a])


def sala_con_equipos(original):
    """El layout de la sala con las texturas 32/33 y las filas alternadas, o None si no es el conocido."""
    if original.count(TEX_11) != 1 or b'TEXTURE ID="32"' in original or b'TEXTURE ID="33"' in original:
        return None
    filas = [b'<BUTTONEX INDEX="%d" TEXID="11"' % n for n in range(301, 309)]
    if any(original.count(f) != 1 for f in filas):
        return None
    # ⚠ MEDIDO (24-nov, sesión 20261124-083639): las texturas se toman por ORDEN en la lista, no por su ID. Insertadas
    #   después de la 11 corrieron las 12–31 (un botón de arriba quedó gris y las filas mostraron otra textura).
    #   Van al FINAL, después de la última <TEXTURE> activa (la 31): así 32 y 33 son también su lugar en la lista.
    import re
    ultimas = list(re.finditer(rb'\n[ \t]*<TEXTURE ID="(\d+)"[^\n]*\n', original))
    if not ultimas or int(ultimas[-1].group(1)) != 31:
        return None
    fin_tex = ultimas[-1].end()
    nuevas = b"".join(b'\t\t<TEXTURE ID="%d" PATH="WaitRoom_Mission\\\\%s" TEXW="341" TEXH="93" EXPLAIN="PvP: %s"/>\r\n'
                      % (i, n.encode(), b"rojo" if i == 32 else b"azul") for i, (n, _) in TEX_NUEVAS.items())
    t = original[:fin_tex] + nuevas + original[fin_tex:]
    for n, f in zip(range(301, 309), filas):
        t = t.replace(f, f.replace(b'TEXID="11"', b'TEXID="%d"' % (32 if n % 2 else 33)), 1)
    return t


def generar_sala(cliente=D.ORIGEN, salida=SALIDA):
    import io
    from PIL import Image
    nuevo = sala_con_equipos(leer_original(cliente, SALA))
    if nuevo is None:
        raise SystemExit("⛔ %s no es el conocido: no se genera la sala con equipos" % SALA)
    dst = os.path.join(salida, *SALA.split("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(nuevo)
    barra = Image.open(io.BytesIO(leer_original(cliente, BARRA)))
    carpeta = os.path.join(salida, *BARRA.split("/")[:-1])
    os.makedirs(carpeta, exist_ok=True)
    for _, (nombre, mult) in TEX_NUEVAS.items():
        tenir(barra, mult).save(os.path.join(carpeta, nombre))
    print("· %s (texturas 32/33 + filas alternadas) y las barras roja / azul → %s" % (SALA, salida))
    return salida


def con_nombre(original):
    """El layout con la pestaña nombrada, o None si la línea no está exactamente una vez."""
    if original.count(ANTES) != 1:
        return None
    return original.replace(ANTES, DESPUES, 1)


def generar(cliente=D.ORIGEN, salida=SALIDA):
    nuevo = con_nombre(leer_original(cliente))
    if nuevo is None:
        raise SystemExit("⛔ el control 103 de %s no es el conocido: no se genera nada" % RUTA)
    dst = os.path.join(salida, *RUTA.split("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(nuevo)
    print("· %s (sólo STRID 0 → 40 en el control 103) → %s" % (RUTA, dst))
    return salida


def _sin_equipos(t):
    import re
    t = re.sub(rb'\t\t<TEXTURE ID="3[23]" [^\n]*\n', b"", t)
    return re.sub(rb'(<BUTTONEX INDEX="30[1-8]" TEXID=")3[23]"', rb'\g<1>11"', t)


def control():
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    original = leer_original()
    nuevo = con_nombre(original)
    chequear("el Data.dat tiene el control 103 conocido, una sola vez", nuevo is not None)
    chequear("el generado cambia SÓLO ese STRID (mismo largo + 1, el resto idéntico)",
             nuevo is not None and len(nuevo) == len(original) + 1
             and nuevo.replace(DESPUES, ANTES) == original)
    chequear("★ el revés: Scenario (102, STRID 3008) queda igual", nuevo is not None and b'STRID="3008"' in nuevo)
    chequear("★ el revés: un layout de otra versión (sin esa línea) no se toca", con_nombre(original.replace(
        b"ChannelLobby_BattleModeBtn", b"OtroBoton")) is None)
    sala = leer_original(ruta=SALA)
    nueva = sala_con_equipos(sala)
    chequear("sala: el layout conocido se acepta", nueva is not None)
    chequear("sala: filas impares (301…) con la textura 32 y pares (302…) con la 33",
             nueva is not None and all((b'<BUTTONEX INDEX="%d" TEXID="%d"' % (n, 32 if n % 2 else 33)) in nueva
                                       for n in range(301, 309)))
    chequear("sala: ★ el revés: nada más cambia (sin las 2 texturas nuevas y con TEXID 11, es el original)",
             nueva is not None and _sin_equipos(nueva) == sala)
    chequear("sala: ★ el revés: un layout que ya tiene la textura 32 no se toca",
             sala_con_equipos(nueva or b"") is None)
    import re
    orden = [int(x) for x in re.findall(rb'\n[ \t]*<TEXTURE ID="(\d+)"', nueva or b"")]
    chequear("sala: las texturas quedan EN ORDEN (0…33: el juego las toma por su lugar en la lista)",
             orden == list(range(34)))
    from PIL import Image
    gris = Image.new("RGBA", (4, 4), (100, 100, 100, 77))
    roja, azul = tenir(gris, TEX_NUEVAS[32][1]), tenir(gris, TEX_NUEVAS[33][1])
    chequear("barras: la roja es roja y la azul azul, con el mismo alfa",
             roja.getpixel((0, 0))[0] > roja.getpixel((0, 0))[2] and azul.getpixel((0, 0))[2] > azul.getpixel((0, 0))[0]
             and roja.getpixel((0, 0))[3] == azul.getpixel((0, 0))[3] == 77)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    if a[:1] == ["generar"]:
        generar()
        generar_sala()
        return 0
    if a[:1] == ["control"]:
        return control()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
