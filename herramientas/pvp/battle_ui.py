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


def leer_original(cliente=D.ORIGEN):
    from pathlib import Path
    from desempacar_data_dat import SolFS
    with SolFS(Path(cliente) / "Data.dat", Path(cliente) / "LTMsg.dll") as sfs:
        for p, ino, _, _ in sfs.walk():
            if p.lower() == RUTA:
                return sfs.read_file(ino)
    raise SystemExit("⛔ %s no está en el Data.dat de %s" % (RUTA, cliente))


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
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    if a[:1] == ["generar"]:
        generar()
        return 0
    if a[:1] == ["control"]:
        return control()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
