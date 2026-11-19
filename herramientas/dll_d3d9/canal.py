r"""canal -- EL CLIENTE DE DEVELOP: los archivos del cliente que salen de la rama develop, con su lista.

    python herramientas/dll_d3d9/canal.py armar DLL SALIDA [--repo dueño/nombre] [--commit SHA]   # lo corre el CI
    py herramientas\dll_d3d9\canal.py bajar [CARPETA]       # baja lo publicado y lo verifica
    py herramientas\dll_d3d9\canal.py verificar LISTA CARPETA
    py herramientas\dll_d3d9\canal.py control               # las pruebas (cada una con su revés)

Para qué: el server de PRUEBA se actualiza solo con cada fusión en develop, pero la `d3d9.dll` que sale de
ese mismo código no estaba en ningún lado (exe/d3d9.dll es la de la última release). Ahora, en cada push a
develop, el CI la compila y la deja en la release «cliente-develop» del repositorio (trabajo
«cliente-develop» de .github/workflows/pruebas.yml), con `eda_d3d9.ini` y la lista `cliente-develop.json`:

    https://github.com/<dueño>/<repo>/releases/download/cliente-develop/cliente-develop.json
    https://github.com/<dueño>/<repo>/releases/download/cliente-develop/d3d9.dll
    https://github.com/<dueño>/<repo>/releases/download/cliente-develop/eda_d3d9.ini

La lista tiene la forma del manifiesto del launcher (`files`: path, size, md5; acá también sha256) y arriba
la identidad de la dll (la de d3d9.dll.json: `identificar.py --esperado cliente-develop.json` la entiende).
`EDA_limpio.exe` no se copia a la release: la lista da su md5 y la dirección del que está en el repositorio,
en ese mismo commit. El resto del cliente (Data.dat y demás) es el de siempre: no cambia con develop.

`bajar` sin CARPETA deja la dll y el .ini en _trabajo\dll\, que es de donde `jugar.py` toma la dll más
nueva; con CARPETA (una copia del juego) baja también el exe. El .ini es del jugador: si ya está, no se pisa.

⚠ Es un canal de PRUEBA para quien desarrolla: la lista NO está firmada (la de los jugadores sí, y la
verifica el launcher). Los sha256 protegen de una descarga rota o a medias, no de otra cosa.
⚠ Mientras el CI sube los archivos puede haber unos segundos con la dll nueva y la lista vieja: `bajar`
verifica y avisa; se vuelve a correr.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))               # ⚠ herramientas/dll_d3d9 → la raíz
sys.path.insert(0, AQUI)

REPO = "r2beatlatino/EDA"
ETIQUETA = "cliente-develop"
LISTA = ETIQUETA + ".json"
DEL_JUGADOR = ("eda_d3d9.ini",)                              # si ya está, no se pisa (como el launcher)


def _huellas(datos):
    return {"size": len(datos), "md5": hashlib.md5(datos).hexdigest(), "sha256": hashlib.sha256(datos).hexdigest()}


def base(repo=REPO):
    return "https://github.com/%s/releases/download/%s/" % (repo, ETIQUETA)


def armar(dll, salida, repo=REPO, commit="", exe=None):
    """Arma en `salida` lo que se publica: d3d9.dll, eda_d3d9.ini y cliente-develop.json (+ notas.md)."""
    import compilar
    import identificar
    info = identificar.leer(dll)
    ident = info["identidad"]
    if not ident:
        raise SystemExit("⛔ %s no tiene identidad (EDA-ID): no es una dll compilada con version.py; no se publica" % dll)
    if ident["sucio"]:
        raise SystemExit("⛔ %s es una compilación LOCAL (-dirty): no se publica" % dll)
    os.makedirs(salida, exist_ok=True)
    destino = os.path.join(salida, "d3d9.dll")
    if os.path.abspath(dll) != os.path.abspath(destino):
        shutil.copyfile(dll, destino)
    ini = compilar.INI.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")   # CRLF: lo lee Windows
    open(os.path.join(salida, "eda_d3d9.ini"), "wb").write(ini)
    exe = exe or os.path.join(RAIZ, "exe", "EDA_limpio.exe")
    files = [dict(path="d3d9.dll", **_huellas(open(destino, "rb").read())),
             dict(path="eda_d3d9.ini", **_huellas(ini))]
    if os.path.isfile(exe) and commit:
        files.append(dict(path="EDA_limpio.exe", url="https://raw.githubusercontent.com/%s/%s/exe/EDA_limpio.exe"
                          % (repo, commit), **_huellas(open(exe, "rb").read())))
    lista = dict(ident, canal="develop", rama_commit=commit, base=base(repo), puerto_server=35900,
                 archivo="d3d9.dll", tam=info["tam"], md5=info["md5"], sha256=info["sha256"], files=files)
    open(os.path.join(salida, LISTA), "w", encoding="utf-8", newline="\n").write(
        json.dumps(lista, ensure_ascii=False, indent=2) + "\n")
    notas = ["El cliente que sale de la rama `develop`, compilado por el CI en cada fusión. Es para **probar**",
             "contra el server de prueba (puerto 35900); los jugadores reciben el suyo por el launcher.", "",
             "- dll: **EDA %s** · commit `%s` · build `%s` · %s" % (ident["version"], ident["commit"], ident["build"],
                                                                 ident["fecha"]),
             "- develop: `%s`" % (commit or "?"), "", "| archivo | bytes | md5 |", "|---|---|---|"]
    notas += ["| `%s` | %d | `%s` |" % (f["path"], f["size"], f["md5"]) for f in files]
    notas += ["", "Bajar y verificar: `py herramientas\\dll_d3d9\\canal.py bajar` (ver ese archivo)."]
    open(os.path.join(salida, "notas.md"), "w", encoding="utf-8", newline="\n").write("\n".join(notas) + "\n")
    return lista


def verificar(lista, carpeta, nombres=None):
    """Los archivos de `lista` que en `carpeta` faltan o no son los de la lista: [(path, por qué)]."""
    mal = []
    for f in lista["files"]:
        if nombres is not None and f["path"] not in nombres:
            continue
        ruta = os.path.join(carpeta, f["path"])
        if not os.path.isfile(ruta):
            mal.append((f["path"], "falta"))
            continue
        h = _huellas(open(ruta, "rb").read())
        if h["sha256"] != f["sha256"]:
            mal.append((f["path"], "sha256 %s… y la lista dice %s…" % (h["sha256"][:12], f["sha256"][:12])))
    return mal


def _traer(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "eda-canal"}), timeout=60) as r:
        return r.read()


def bajar(carpeta=None, repo=REPO, traer=_traer):
    """Baja lo publicado a `carpeta` (sin carpeta: _trabajo/dll, sólo la dll y el .ini). Devuelve la lista."""
    todo = carpeta is not None
    carpeta = carpeta or os.path.join(RAIZ, "_trabajo", "dll")
    os.makedirs(carpeta, exist_ok=True)
    lista = json.loads(traer(base(repo) + LISTA).decode("utf-8"))
    print("cliente de develop: EDA %s · commit %s · build %s · %s" % (
        lista.get("version"), lista.get("commit"), lista.get("build"), lista.get("fecha")))
    for f in lista["files"]:
        nombre = os.path.basename(f["path"])                # (nunca una ruta: la lista no elige carpetas)
        if nombre != f["path"] or (not todo and nombre == "EDA_limpio.exe"):
            continue
        ruta = os.path.join(carpeta, nombre)
        if os.path.isfile(ruta):
            if _huellas(open(ruta, "rb").read())["sha256"] == f["sha256"]:
                os.utime(ruta, None)                        # jugar.py toma la dll MÁS NUEVA (_trabajo/dll o exe/)
                print("  igual    %s" % nombre)
                continue
            if nombre in DEL_JUGADOR:
                print("  se deja  %s (es tuyo: ya estaba y es distinto del publicado)" % nombre)
                continue
        datos = traer(f.get("url") or lista["base"] + nombre)
        h = _huellas(datos)
        if h["sha256"] != f["sha256"]:
            raise SystemExit("⛔ %s: lo bajado (md5 %s) no es lo de la lista (md5 %s). Si el CI está subiendo, "
                             "probá de nuevo en un minuto" % (nombre, h["md5"], f["md5"]))
        tmp = ruta + ".bajando"
        open(tmp, "wb").write(datos)
        os.replace(tmp, ruta)
        print("  bajado   %s (%d B · md5 %s)" % (nombre, h["size"], h["md5"]))
    print("→ en %s" % carpeta)
    return lista


def control():
    ok = []

    def chequear(nombre, c):
        print("  %s %s" % ("✅" if c else "⛔", nombre))
        ok.append(bool(c))

    def negado(f):
        try:
            f()
        except SystemExit:
            return True
        return False
    import compilar
    marca = b"EDA-ID|v=9.8.7|c=abc1234|s=%d|f=2026-01-02 03:04 UTC|b=b0123456789|"
    with tempfile.TemporaryDirectory() as t:
        buena, sucia, vieja = (os.path.join(t, n) for n in ("buena.dll", "sucia.dll", "vieja.dll"))
        open(buena, "wb").write(b"MZ\0\0" + marca % 0 + b"\0" * 64)
        open(sucia, "wb").write(b"MZ\0\0" + marca % 1 + b"\0" * 64)
        open(vieja, "wb").write(b"MZ\0\0" + b"\0" * 64)
        exe = os.path.join(t, "EDA_limpio.exe")
        open(exe, "wb").write(b"MZ-el-exe")
        sal = os.path.join(t, "salida")
        lista = armar(buena, sal, repo="alguien/juego", commit="c0ffee", exe=exe)
        leida = json.load(open(os.path.join(sal, LISTA), encoding="utf-8"))
        chequear("la lista se arma con la identidad de la dll", leida == lista and leida["version"] == "9.8.7"
                 and leida["commit"] == "abc1234" and leida["build"] == "b0123456789" and leida["sucio"] == 0)
        chequear("trae la dll, el .ini y el exe, con la forma del launcher (path, size, md5)",
                 [f["path"] for f in leida["files"]] == ["d3d9.dll", "eda_d3d9.ini", "EDA_limpio.exe"]
                 and all(len(f["md5"]) == 32 and f["size"] > 0 for f in leida["files"]))
        chequear("el md5 de arriba es el de la dll (lo que lee identificar.py)",
                 leida["md5"] == hashlib.md5(open(buena, "rb").read()).hexdigest() == leida["files"][0]["md5"])
        ini = open(os.path.join(sal, "eda_d3d9.ini"), "rb").read()
        chequear("el .ini es el de compilar.py, en CRLF", ini.replace(b"\r\n", b"\n").decode("utf-8")
                 == compilar.INI.replace("\r\n", "\n") and b"\r\n" in ini and b"\r\r" not in ini
                 and ini.count(b"\n") == ini.count(b"\r\n"))
        chequear("el exe va por su dirección en el repositorio, en ESE commit",
                 leida["files"][2]["url"] == "https://raw.githubusercontent.com/alguien/juego/c0ffee/exe/EDA_limpio.exe")
        chequear("★ el revés: una dll sin identidad no se publica", negado(lambda: armar(vieja, sal + "2")))
        chequear("★ el revés: una compilación LOCAL (-dirty) no se publica", negado(lambda: armar(sucia, sal + "3")))
        chequear("lo armado verifica contra su lista", verificar(leida, sal, ("d3d9.dll", "eda_d3d9.ini")) == [])
        # bajar, con una «red» de mentira: las direcciones de la lista → los archivos armados
        red = {leida["base"] + n: open(os.path.join(sal, n), "rb").read() for n in (LISTA, "d3d9.dll", "eda_d3d9.ini")}
        red[leida["files"][2]["url"]] = open(exe, "rb").read()
        pedidos = []

        def traer(url):
            pedidos.append(url)
            return red[url]
        juego = os.path.join(t, "juego")
        bajar(juego, repo="alguien/juego", traer=traer)
        chequear("bajar deja los tres archivos, iguales a la lista", verificar(leida, juego) == [])
        pedidos.clear()
        bajar(juego, repo="alguien/juego", traer=traer)
        chequear("la segunda vez no baja nada (sólo la lista)", pedidos == [leida["base"] + LISTA])
        open(os.path.join(juego, "eda_d3d9.ini"), "wb").write(b"[video]\r\ntope_fps=60\r\n")
        open(os.path.join(juego, "d3d9.dll"), "wb").write(b"otra")
        bajar(juego, repo="alguien/juego", traer=traer)
        chequear("una dll distinta se reemplaza", verificar(leida, juego, ("d3d9.dll",)) == [])
        chequear("★ el revés: el .ini del jugador NO se pisa",
                 open(os.path.join(juego, "eda_d3d9.ini"), "rb").read() == b"[video]\r\ntope_fps=60\r\n")
        chequear("★ el revés: verificar SÍ ve un archivo cambiado", [m[0] for m in verificar(leida, juego)] == ["eda_d3d9.ini"])
        red[leida["base"] + "d3d9.dll"] = b"a medio subir"
        os.remove(os.path.join(juego, "d3d9.dll"))
        chequear("★ el revés: una descarga que no es la de la lista se rechaza (y no queda el archivo)",
                 negado(lambda: bajar(juego, repo="alguien/juego", traer=traer))
                 and not os.path.exists(os.path.join(juego, "d3d9.dll")))
        red[leida["base"] + "d3d9.dll"] = open(os.path.join(sal, "d3d9.dll"), "rb").read()
        global RAIZ
        raiz, RAIZ = RAIZ, t
        try:
            os.makedirs(os.path.join(t, "_trabajo"))
            bajar(repo="alguien/juego", traer=traer)
        finally:
            RAIZ = raiz
        chequear("sin carpeta: a _trabajo/dll, sin el exe",
                 sorted(os.listdir(os.path.join(t, "_trabajo", "dll"))) == ["d3d9.dll", "eda_d3d9.ini"])
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main(a):
    def opcion(nombre, defecto):
        return a[a.index(nombre) + 1] if nombre in a and a.index(nombre) + 1 < len(a) else defecto
    if a[:1] == ["control"]:
        return control()
    if a[:1] == ["armar"] and len(a) >= 3:
        lista = armar(a[1], a[2], repo=opcion("--repo", REPO), commit=opcion("--commit", ""))
        print("★ %s: EDA %s · commit %s · build %s" % (os.path.join(a[2], LISTA), lista["version"], lista["commit"],
                                                      lista["build"]))
        for f in lista["files"]:
            print("  %-16s %8d B · md5 %s" % (f["path"], f["size"], f["md5"]))
        return 0
    if a[:1] == ["bajar"]:
        resto = [x for x in a[1:] if x != opcion("--repo", None) and x != "--repo"]
        bajar(resto[0] if resto else None, repo=opcion("--repo", REPO))
        return 0
    if a[:1] == ["verificar"] and len(a) >= 3:
        mal = verificar(json.load(open(a[1], encoding="utf-8-sig")), a[2])
        for path, por in mal:
            print("  ⛔ %s: %s" % (path, por))
        print("→ %s" % ("NO COINCIDE" if mal else "coincide con la lista"))
        return 2 if mal else 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
