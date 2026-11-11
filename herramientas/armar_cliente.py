r"""armar_cliente -- el CLIENTE PARA REPARTIR (el que baja el launcher) y su manifiesto `eda.json`.

    py herramientas\armar_cliente.py                        # arma _trabajo\cliente_repartir\ (16 archivos)
    py herramientas\armar_cliente.py manifiesto VERSION BASE SERVIDOR CANJE
        # → _trabajo\eda.json:  {version, base, servidor, canje, files: [{path, size, md5}]}
        #   BASE      la URL de la CDN donde quedan los 16 (…/files-eda/<release>-<azar>/)
        #   SERVIDOR  host:puerto del server de juego (el 3er argumento del exe)
        #   CANJE     https://<dominio>/eda/pase (http sólo con 127.0.0.1, para pruebas)
    py herramientas\armar_cliente.py control                # las pruebas (con sus reveses)

Qué va (medido, MEDICIONES §45: una carpeta con SÓLO esto entra al server con el ticket):
  · de `cliente/` (el de 2009, se lee, no se toca): Data.dat, EdaENGTest.ini, LTMsg.dll,
    d3dx9_29.dll, mss32.dll, redist/ (7) y autoexec.cfg, con «"windowed" "1"» (como `jugar.py
    --preparar`; el launcher lo cambia después)
  · `_trabajo/juego/EDA_limpio.exe` (el mismo que publica `publicar.py`) y la `d3d9.dll` + su
    `eda_d3d9.ini` de `_trabajo/dll/` (`herramientas/dll_d3d9/compilar.py`)
NO van: EDA.exe, GameGuard.des, el Nyx launcher / patcher, img/, el desinstalador. Los .log que el
juego escribe no entran al manifiesto. Del usuario (el launcher los baja sólo si faltan):
autoexec.cfg y eda_d3d9.ini.
⚠ La clave del cifrado es el MD5 del exe: si cambia EDA_limpio.exe, el server tiene que conocerla.
"""
import hashlib
import json
import os
import re
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENTE = os.path.join(RAIZ, "cliente")
SALIDA = os.path.join(RAIZ, "_trabajo", "cliente_repartir")
MANIFIESTO = os.path.join(RAIZ, "_trabajo", "eda.json")
DE_2009 = ["Data.dat", "EdaENGTest.ini", "LTMsg.dll", "d3dx9_29.dll", "mss32.dll"]
NUESTROS = {"EDA_limpio.exe": os.path.join(RAIZ, "_trabajo", "juego", "EDA_limpio.exe"),
            "d3d9.dll": os.path.join(RAIZ, "_trabajo", "dll", "d3d9.dll"),
            "eda_d3d9.ini": os.path.join(RAIZ, "_trabajo", "dll", "eda_d3d9.ini")}
DEL_USUARIO = ("autoexec.cfg", "eda_d3d9.ini")
NO_VAN = re.compile(r"\.(log|dmp|rpt)$", re.I)       # los escribe el juego


def md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()                              # (en minúscula, como lo pide el launcher)


def armar(salida=SALIDA):
    if os.path.exists(salida):
        shutil.rmtree(salida)
    os.makedirs(os.path.join(salida, "redist"))
    for x in DE_2009:
        shutil.copy2(os.path.join(CLIENTE, x), salida)
    for x in sorted(os.listdir(os.path.join(CLIENTE, "redist"))):
        shutil.copy2(os.path.join(CLIENTE, "redist", x), os.path.join(salida, "redist"))
    cfg = open(os.path.join(CLIENTE, "autoexec.cfg"), encoding="latin-1").read()
    assert re.search(r'"windowed"\s+"\d"', cfg), "autoexec.cfg sin «windowed»"
    cfg = re.sub(r'"windowed"\s+"\d"', '"windowed" "1"', cfg)
    open(os.path.join(salida, "autoexec.cfg"), "w", encoding="latin-1", newline="").write(cfg)
    for nombre, origen in NUESTROS.items():
        if not os.path.exists(origen):
            raise SystemExit("⛔ falta %s (¿compilar.py / sin_gameguard.py limpio?)" % origen)
        shutil.copy2(origen, os.path.join(salida, nombre))
    return archivos(salida)


def archivos(carpeta=SALIDA):
    """[(ruta con /, tamaño, md5)] de lo que va en el manifiesto (sin los .log del juego)."""
    r = []
    for base, _, fs in os.walk(carpeta):
        for f in fs:
            p = os.path.join(base, f)
            rel = os.path.relpath(p, carpeta).replace(os.sep, "/")
            if not NO_VAN.search(rel):
                r.append((rel, os.path.getsize(p), md5(p)))
    return sorted(r)


def manifiesto(version, base, servidor, canje, carpeta=SALIDA):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", version):
        raise SystemExit("⛔ versión rara: %r" % version)
    if not re.fullmatch(r"[A-Za-z0-9.-]+:\d{1,5}", servidor):
        raise SystemExit("⛔ el servidor va como host:puerto: %r" % servidor)
    if not (canje.startswith("https://") or re.match(r"^http://127\.0\.0\.1(:\d+)?/", canje)):
        raise SystemExit("⛔ el canje tiene que ser https (http sólo con 127.0.0.1): %r" % canje)
    if not base.endswith("/"):
        base += "/"
    return {"version": version, "base": base, "servidor": servidor, "canje": canje,
            "files": [{"path": p, "size": s, "md5": m} for p, s, m in archivos(carpeta)]}


def control():
    import tempfile
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))
    t = tempfile.mkdtemp()
    os.makedirs(os.path.join(t, "redist"))
    for rel, cont in (("a.dll", b"1"), ("redist/b.flt", b"22"), ("eda_d3d9.log", b"x"), ("EDA_limpio.dmp", b"y")):
        open(os.path.join(t, rel), "wb").write(cont)
    m = manifiesto("2026.11.12", "https://cdn/x", "eda.ejemplo:25900", "https://eda.ejemplo/eda/pase", t)
    chequear("las rutas con / y el md5 en minúscula",
             [f["path"] for f in m["files"]] == ["a.dll", "redist/b.flt"]
             and m["files"][1]["md5"] == hashlib.md5(b"22").hexdigest(), m["files"])
    chequear("★ el revés: los .log / .dmp del juego NO entran", all(not NO_VAN.search(f["path"]) for f in m["files"]))
    chequear("servidor, canje y la base con «/» al final",
             m["servidor"] == "eda.ejemplo:25900" and m["canje"].startswith("https://") and m["base"].endswith("/"))
    for canje, que in (("http://eda.ejemplo/eda/pase", "http a un dominio"), ("ftp://x", "otro esquema")):
        try:
            manifiesto("1", "https://cdn/x", "h:1", canje, t)
            chequear("★ el revés: %s se rechaza" % que, False)
        except SystemExit:
            chequear("★ el revés: %s se rechaza" % que, True)
    chequear("…y http con 127.0.0.1 sí (para probar)",
             manifiesto("1", "https://cdn/x", "h:1", "http://127.0.0.1:25901/eda/pase", t)["canje"].startswith("http://127"))
    try:
        manifiesto("1", "https://cdn/x", "sin-puerto", "https://e/eda/pase", t)
        chequear("★ el revés: un servidor sin puerto se rechaza", False)
    except SystemExit:
        chequear("★ el revés: un servidor sin puerto se rechaza", True)
    shutil.rmtree(t)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    a = sys.argv[1:]
    if a[:1] == ["control"]:
        sys.exit(control())
    if a[:1] == ["manifiesto"]:
        if len(a) != 5:
            raise SystemExit(__doc__)
        m = manifiesto(*a[1:])
        json.dump(m, open(MANIFIESTO, "w", encoding="utf-8"), indent=1)
        print("★ %s: %d archivos, %d B" % (MANIFIESTO, len(m["files"]), sum(f["size"] for f in m["files"])))
        sys.exit(0)
    fs = armar()
    for p, s, m in fs:
        print("  %-22s %12d  %s" % (p, s, m))
    print("★ %s: %d archivos, %d B (del usuario: %s)" % (SALIDA, len(fs), sum(s for _, s, _ in fs),
                                                          ", ".join(DEL_USUARIO)))
