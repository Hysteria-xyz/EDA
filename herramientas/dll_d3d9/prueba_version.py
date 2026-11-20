r"""prueba_version -- las pruebas del versionado de la dll, sin Windows, sin el juego y sin red.

    python herramientas/dll_d3d9/prueba_version.py                  # todo lo automático
    python herramientas/dll_d3d9/prueba_version.py RUTA/d3d9.dll    # + la dll compilada (marca, sin ventanas)

  1. la versión es la del commit compilado (el último que tocó herramientas/dll_d3d9, no HEAD)
  2. con cambios sin commitear → sucio (LOCAL); archivos nuevos también; sin git → LOCAL
  3. TEST / PROD / LOCAL salen del server (prueba_version.c, con gcc)
  4. las líneas del aviso (prueba_version.c)
  5. identificar.py: el hash de la dll y la comparación con el manifiesto
  6. una dll antigua (sin marca) o distinta → se detecta
  7. recompilar el mismo código = misma identidad; otro código = otro build
  8. todo sin conexión (sólo git local)
  9. el código nuevo no abre procesos (cmd, Python) y la dll compilada tampoco
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import identificar  # noqa: E402
import version  # noqa: E402

OK = MAL = 0


def chequear(nombre, cond, extra=""):
    global OK, MAL
    print("  %s %s%s" % ("OK " if cond else "MAL", nombre, (" — " + extra) if extra and not cond else ""))
    if cond:
        OK += 1
    else:
        MAL += 1


def git(raiz, *a):
    return subprocess.run(["git", "-C", raiz] + list(a), capture_output=True, text=True, check=True).stdout.strip()


def repo_de_prueba():
    """un repo chico con la carpeta herramientas/dll_d3d9 copiada (sólo el código)"""
    raiz = tempfile.mkdtemp(prefix="eda_ver_")
    car = os.path.join(raiz, "herramientas", "dll_d3d9")
    os.makedirs(car)
    for n in os.listdir(AQUI):
        if n.endswith((".c", ".def")) or n == "VERSION":
            shutil.copy(os.path.join(AQUI, n), car)
    os.makedirs(os.path.join(raiz, "exe"))
    open(os.path.join(raiz, ".gitignore"), "w").write("herramientas/dll_d3d9/eda_version.h\n*.dll\n")
    git(raiz, "init", "-q")
    git(raiz, "config", "user.email", "prueba@example.org")
    git(raiz, "config", "user.name", "prueba")
    git(raiz, "add", "-A")
    git(raiz, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "código", "--date", "2026-11-19T06:00:00Z")
    return raiz, car


def pruebas_git():
    print("== 1, 2, 7, 8: la identidad sale del git local ==")
    if not shutil.which("git"):
        chequear("git disponible", False, "sin git no se puede probar")
        return
    raiz, car = repo_de_prueba()
    try:
        c1 = git(raiz, "rev-parse", "HEAD")
        a = version.identidad(raiz, car)
        chequear("1. commit = el último que tocó la carpeta", a["commit_largo"] == c1 and a["commit"] == c1[:7])
        chequear("1. limpia → sucio 0", a["sucio"] == 0 and not a["cambios"], str(a["cambios"]))
        chequear("1. versión de VERSION", a["version"] == version.leer_version(AQUI))
        os.environ["GIT_COMMITTER_DATE"] = "2026-11-19T06:00:00Z"
        b = version.identidad(raiz, car, ahora=datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc))
        chequear("7. limpia: la fecha es la del commit (no la hora): reproducible", a["fecha"] == b["fecha"] and "2030" not in b["fecha"])
        chequear("7. recompilar = misma identidad y mismo eda_version.h", version.header(a) == version.header(b))
        # commitear la dll (exe/) no cambia el commit de la identidad (así el CI recompila igual)
        open(os.path.join(raiz, "exe", "LEEME.md"), "w").write("la dll\n")
        git(raiz, "add", "-A")
        git(raiz, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "exe")
        c = version.identidad(raiz, car)
        chequear("1. un commit fuera de la carpeta no cambia la identidad", c["commit"] == a["commit"] and c["sucio"] == 0)
        # una prueba, un .py o el LEEME de la carpeta: no son código de la dll → mismo commit, limpia
        open(os.path.join(car, "prueba_version.c"), "a").write("/* otra prueba */\n")
        open(os.path.join(car, "LEEME.md"), "w").write("leeme\n")
        open(os.path.join(car, "version_extra.py"), "w").write("# py\n")
        chequear("2. cambios sólo en pruebas / .py / LEEME → sigue limpia", version.identidad(raiz, car)["sucio"] == 0)
        git(raiz, "add", "-A")
        git(raiz, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pruebas")
        chequear("1. un commit sólo de pruebas / .py / LEEME no cambia el commit", version.identidad(raiz, car)["commit"] == a["commit"])
        # un cambio sin commitear → sucio, otro build
        p = os.path.join(car, "eda_version.c")
        orig = open(p, "rb").read()
        open(p, "ab").write(b"\n/* cambio */\n")
        d = version.identidad(raiz, car)
        chequear("2. cambio sin commitear → sucio (LOCAL)", d["sucio"] == 1 and d["cambios"])
        chequear("7. otro código → otro build", d["build"] != a["build"])
        chequear("2. sucio → el header lo dice", "#define EDA_SUCIO 1" in version.header(d))
        open(p, "wb").write(orig)
        e = version.identidad(raiz, car)
        chequear("7. volver al código → mismo build y limpio otra vez", e["build"] == a["build"] and e["sucio"] == 0)
        # finales de línea: CRLF (Windows) = LF (Linux) para el build
        open(p, "wb").write(orig.replace(b"\n", b"\r\n"))
        chequear("7. CRLF o LF: mismo build", version.huella_codigo(car) == a["build"])
        open(p, "wb").write(orig)
        # un archivo nuevo → sucio
        open(os.path.join(car, "eda_nuevo.c"), "w").write("/* nuevo */\n")
        chequear("2. archivo nuevo sin commitear → sucio", version.identidad(raiz, car)["sucio"] == 1)
        os.remove(os.path.join(car, "eda_nuevo.c"))
        # el header generado no ensucia
        version.escribir_header(os.path.join(car, "eda_version.h"), a)
        chequear("2. eda_version.h (generado) no cuenta como cambio", version.identidad(raiz, car)["sucio"] == 0)
        # un commit nuevo en la carpeta → otro commit
        open(p, "ab").write(b"\n/* v2 */\n")
        git(raiz, "add", "-A")
        git(raiz, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "v2")
        f = version.identidad(raiz, car)
        chequear("1. un commit en la carpeta → ese commit", f["commit_largo"] == git(raiz, "rev-parse", "HEAD") and f["commit"] != a["commit"])
        chequear("8. sin remotos → en_github falso (sin red: sólo lo local)", f["en_github"] is False)
        # sin git → LOCAL
        sin = tempfile.mkdtemp(prefix="eda_singit_")
        shutil.copytree(car, os.path.join(sin, "x"))
        g = version.identidad(sin, os.path.join(sin, "x"))
        chequear("2. sin git → LOCAL (sin-git, sucio)", g["commit"] == "sin-git" and g["sucio"] == 1)
        shutil.rmtree(sin, ignore_errors=True)
    finally:
        os.environ.pop("GIT_COMMITTER_DATE", None)
        shutil.rmtree(raiz, ignore_errors=True)


def pruebas_c():
    print("== 3, 4: entorno y aviso (prueba_version.c) ==")
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        chequear("gcc disponible", False)
        return
    for sucio in (0, 1):
        t = tempfile.mkdtemp(prefix="eda_c_")
        try:
            ident = {"version": "0.5.0", "commit": "a1b2c3d", "sucio": sucio, "fecha": "2026-11-19 06:00 UTC",
                     "build": "b0123456789"}
            open(os.path.join(t, "eda_version.h"), "w").write(version.header(ident))
            for n in ("eda_version.c", "prueba_version.c"):
                shutil.copy(os.path.join(AQUI, n), t)
            exe = os.path.join(t, "pv")
            r = subprocess.run([cc, "-std=gnu11", "-Wall", "-Werror", "-I", t, "-o", exe, os.path.join(t, "prueba_version.c")],
                               capture_output=True, text=True)
            chequear("compila (sucio=%d)" % sucio, r.returncode == 0, r.stderr[-400:])
            if r.returncode == 0:
                r = subprocess.run([exe], capture_output=True, text=True)
                print("    " + r.stdout.strip().replace("\n", "\n    "))
                chequear("prueba_version.c (sucio=%d)" % sucio, r.returncode == 0)
        finally:
            shutil.rmtree(t, ignore_errors=True)
    # sin eda_version.h: «sin-version», sucio (nunca se hace pasar por publicada)
    t = tempfile.mkdtemp(prefix="eda_c_")
    try:
        shutil.copy(os.path.join(AQUI, "eda_version.c"), t)
        open(os.path.join(t, "m.c"), "w").write('#include <stdio.h>\n#include <string.h>\n#include "eda_version.c"\n'
                                                 'int main(void){puts(g_eda_id);return 0;}\n')
        r = subprocess.run([cc, "-std=gnu11", "-o", os.path.join(t, "m"), os.path.join(t, "m.c")], capture_output=True, text=True)
        salida = subprocess.run([os.path.join(t, "m")], capture_output=True, text=True).stdout if r.returncode == 0 else ""
        chequear("sin eda_version.h → «sin-version» y sucio", "c=sin-version|s=1|" in salida, salida or r.stderr[-300:])
    finally:
        shutil.rmtree(t, ignore_errors=True)


def pruebas_identificar():
    print("== 5, 6: identificar.py (hash y comparación) ==")
    t = tempfile.mkdtemp(prefix="eda_id_")
    try:
        marca = b"EDA-ID|v=0.5.0|c=a1b2c3d|s=0|f=2026-11-19 06:00 UTC|b=b0123456789|"
        dll = os.path.join(t, "d3d9.dll")
        open(dll, "wb").write(b"MZ" + b"\0" * 100 + marca + b"\0" * 50)
        i = identificar.leer(dll)
        datos = open(dll, "rb").read()
        chequear("5. md5 y sha256 del archivo", i["md5"] == hashlib.md5(datos).hexdigest()
                 and i["sha256"] == hashlib.sha256(datos).hexdigest())
        chequear("5. lee la identidad", i["identidad"] == {"version": "0.5.0", "commit": "a1b2c3d", "sucio": 0,
                                                           "fecha": "2026-11-19 06:00 UTC", "build": "b0123456789"})
        man = os.path.join(t, "d3d9.dll.json")
        json.dump(dict(i["identidad"], md5=i["md5"], sha256=i["sha256"], tam=i["tam"]), open(man, "w"))
        chequear("5. coincide con su d3d9.dll.json (código 0)", identificar.main([dll, "--esperado", man]) == 0)
        launcher = os.path.join(t, "eda.json")
        json.dump({"version": "2026.11.19.1", "archivos": [{"ruta": "d3d9.dll", "md5": i["md5"], "tam": i["tam"]}]},
                  open(launcher, "w"))
        chequear("5. coincide con el manifiesto del launcher", identificar.main([dll, "--esperado", launcher]) == 0)
        vieja = os.path.join(t, "vieja.dll")
        open(vieja, "wb").write(b"MZ" + b"\0" * 200)
        chequear("6. dll antigua (sin marca) → código 3", identificar.main([vieja]) == 3)
        chequear("6. dll antigua contra el manifiesto → NO COINCIDE (2)", identificar.main([vieja, "--esperado", man]) == 2)
        otra = os.path.join(t, "otra.dll")
        open(otra, "wb").write(datos.replace(b"c=a1b2c3d", b"c=ffff000"))
        chequear("6. otro commit → NO COINCIDE (2)", identificar.main([otra, "--esperado", man]) == 2)
        chequear("6. la diferencia nombra el commit", any("commit" in d for d in identificar.comparar(identificar.leer(otra), identificar._esperado(man))))
        chequear("6. contra otra dll", identificar.main([otra, "--esperado", dll]) == 2 and identificar.main([dll, "--esperado", dll]) == 0)
    finally:
        shutil.rmtree(t, ignore_errors=True)


def pruebas_manifiestos():
    """★ (19-nov) los formatos REALES: el manifiesto del launcher (armar_cliente.py: version de la release, base,
    servidor, canje, files[path, size, md5]), el firmado (JWS), la lista del canal develop (canal.py: identidad +
    files con sha256) y los manifiestos incompletos o incorrectos (un error, nunca una coincidencia)."""
    import base64
    import contextlib
    import io
    print("== 5b, 6b: manifiestos del launcher, del canal develop e incorrectos ==")
    t = tempfile.mkdtemp(prefix="eda_man_")

    def correr(*a):
        sal = io.StringIO()
        with contextlib.redirect_stdout(sal):
            try:
                c = identificar.main(list(a))
            except Exception as e:                             # noqa: BLE001  (un KeyError = una prueba mala)
                c = "EXCEPCIÓN %r" % e
        return c, sal.getvalue()

    def escribir(nombre, obj):
        ruta = os.path.join(t, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))
        return ruta
    try:
        marca = b"EDA-ID|v=0.5.0|c=cce27e9|s=0|f=2026-11-19 06:13 UTC|b=bb9c5c22a0b|"
        juego = os.path.join(t, "juego")
        os.makedirs(os.path.join(juego, "redist"))
        dll = os.path.join(juego, "d3d9.dll")
        open(dll, "wb").write(b"MZ" + b"\0" * 90 + marca + b"\0" * 30)
        archivos = {"d3d9.dll": None, "eda_d3d9.ini": b"[red]\r\nserver=\r\n", "EDA_limpio.exe": b"MZ-exe",
                    "autoexec.cfg": b'"windowed" "1"\r\n', "redist/mss.flt": b"flt"}
        for n, d in archivos.items():
            if d is not None:
                open(os.path.join(juego, *n.split("/")), "wb").write(d)

        def h(n):
            d = open(os.path.join(juego, *n.split("/")), "rb").read()
            return {"path": n, "size": len(d), "md5": hashlib.md5(d).hexdigest()}
        info = identificar.leer(dll)
        launcher = {"version": "2026.11.19.1", "base": "https://cdn.example.org/files-eda/x/",
                    "servidor": "eda.example.org:25900", "canje": "https://eda.example.org/eda/pase",
                    "files": [h(n) for n in sorted(archivos)]}
        ml = escribir("eda.json", launcher)
        c, out = correr(dll, "--esperado", ml)
        chequear("launcher (files/path/size): coincide, sin KeyError", c == 0, "%s %s" % (c, out[-300:]))
        chequear("launcher: la versión de la RELEASE no se toma como la de la dll", "release 2026.11.19.1" in out
                 and "versión, commit, build): no disponible" in out and "commit: instalada" not in out, out[-400:])
        jws = "%s.%s.%s" % (base64.urlsafe_b64encode(b'{"alg":"EdDSA"}').decode().rstrip("="),
                            base64.urlsafe_b64encode(json.dumps(dict(launcher, aud="eda-launcher", iat=1)).encode())
                            .decode().rstrip("="), "firma")
        chequear("launcher firmado (JWS): coincide", correr(dll, "--esperado", escribir("m.jws", jws))[0] == 0)
        c, out = correr(dll, "--esperado", ml, "--carpeta", juego)
        chequear("launcher --carpeta: rutas, tamaños y md5 de todo el cliente", c == 0 and "5 archivos" in out, out[-300:])
        open(os.path.join(juego, "eda_d3d9.ini"), "wb").write(b"[video]\r\ntope_fps=60\r\n")
        c, out = correr(dll, "--esperado", ml, "--carpeta", juego)
        chequear("--carpeta: el .ini del jugador distinto es un aviso, no un error", c == 0 and "es del jugador" in out)
        os.remove(os.path.join(juego, "redist", "mss.flt"))
        c, out = correr(dll, "--esperado", ml, "--carpeta", juego)
        chequear("★ revés --carpeta: falta un archivo del juego → NO COINCIDE (2)", c == 2 and "redist/mss.flt: falta" in out)
        open(os.path.join(juego, "redist", "mss.flt"), "wb").write(b"flt")
        open(os.path.join(juego, "EDA_limpio.exe"), "wb").write(b"MZ-otro")
        c, out = correr(dll, "--esperado", ml, "--carpeta", juego)
        chequear("★ revés --carpeta: otro exe → NO COINCIDE (2)", c == 2 and "EDA_limpio.exe: distinto" in out)
        open(os.path.join(juego, "EDA_limpio.exe"), "wb").write(b"MZ-exe")
        mal = json.loads(json.dumps(launcher))
        idll = [f["path"] for f in launcher["files"]].index("d3d9.dll")
        mal["files"][idll]["md5"] = "0" * 32
        chequear("★ revés launcher: otro md5 de la dll → NO COINCIDE (2)", correr(dll, "--esperado", escribir("m1.json", mal))[0] == 2)
        mal = json.loads(json.dumps(launcher))
        mal["files"][idll]["size"] += 1
        chequear("★ revés launcher: otro tamaño → NO COINCIDE (2)", correr(dll, "--esperado", escribir("m2.json", mal))[0] == 2)
        viejo = {"version": "1", "archivos": [{"ruta": "d3d9.dll", "tam": info["tam"], "md5": info["md5"]}]}
        chequear("forma vieja (archivos/ruta/tam): coincide", correr(dll, "--esperado", escribir("m3.json", viejo))[0] == 0)
        # la lista del canal develop (la forma de canal.py armar)
        canal = dict(info["identidad"], canal="develop", rama_commit="b" * 40, puerto_server=35900, archivo="d3d9.dll",
                     tam=info["tam"], md5=info["md5"], sha256=info["sha256"],
                     files=[dict(h("d3d9.dll"), sha256=info["sha256"])])
        mc = escribir("cliente-develop.json", canal)
        c, out = correr(dll, "--esperado", mc)
        chequear("canal develop: coincide con identidad y sha256", c == 0 and "commit cce27e9" in out, out[-300:])
        chequear("★ revés canal: otra identidad (commit) → NO COINCIDE (2)",
                 correr(dll, "--esperado", escribir("c1.json", dict(canal, commit="ffff000")))[0] == 2)
        roto = json.loads(json.dumps(canal))
        roto["files"][0]["sha256"] = "a" * 64
        chequear("★ revés canal: arriba y files no cierran → manifiesto incorrecto (1)",
                 correr(dll, "--esperado", escribir("c2.json", roto))[0] == 1)
        # incompletos o incorrectos: un error (1), nunca una coincidencia
        malos = {
            "sin la dll": dict(launcher, files=[h("autoexec.cfg")]),
            "la dll en una subcarpeta": dict(launcher, files=[dict(h("d3d9.dll"), path="redist/d3d9.dll")]),
            "la dll sin hash": dict(launcher, files=[{"path": "d3d9.dll", "size": info["tam"]}]),
            "md5 que no es hex": dict(launcher, files=[dict(h("d3d9.dll"), md5="zz")]),
            "tamaño de texto": dict(launcher, files=[dict(h("d3d9.dll"), size="225792")]),
            "ruta con ..": dict(launcher, files=[h("d3d9.dll"), dict(h("autoexec.cfg"), path="../x.cfg")]),
            "files no es lista": dict(launcher, files={"d3d9.dll": 1}),
            "la dll dos veces": dict(launcher, files=[h("d3d9.dll"), h("d3d9.dll")]),
            "un json sin files ni hash": {"version": "0.5.0"},
            "un json que es una lista": [1, 2],
            "no es json": "esto no es json {",
        }
        for i, (nombre, obj) in enumerate(malos.items()):
            c, out = correr(dll, "--esperado", escribir("malo%d.json" % i, obj))
            chequear("★ incorrecto: %s → MANIFIESTO INCORRECTO (1)" % nombre, c == 1 and "INCORRECTO" in out, "%s %s" % (c, out[-200:]))
        c, out = correr(dll, "--esperado", ml, "--json")
        j = json.loads(out)
        chequear("--json: se lee y dice el código", j["codigo"] == 0 and j["esperada"]["identidad"] is None
                 and j["esperada"]["release"] == "2026.11.19.1")
        vieja = os.path.join(t, "vieja.dll")
        open(vieja, "wb").write(b"MZ" + b"\0" * 40)
        chequear("★ revés: dll antigua contra la lista del canal → NO COINCIDE (2)", correr(vieja, "--esperado", mc)[0] == 2)
    finally:
        shutil.rmtree(t, ignore_errors=True)


PROCESOS = re.compile(r"CreateProcess|ShellExecute|WinExec|system\s*\(|_popen|cmd\.exe|python|\.py\b", re.I)


def pruebas_sin_ventanas(dll=None):
    print("== 9: sin ventanas de cmd ni de Python ==")
    for n in ("eda_version.c", "eda_aviso.c"):
        codigo = re.sub(r"/\*.*?\*/", "", open(os.path.join(AQUI, n), encoding="utf-8").read(), flags=re.S)
        chequear("%s no abre procesos" % n, not PROCESOS.search(codigo), str(PROCESOS.findall(codigo)))
    if dll:
        datos = open(dll, "rb").read()
        chequear("la dll no tiene «cmd.exe /c start» (ni en UTF-16)",
                 b"cmd.exe /c start" not in datos and "cmd.exe /c start".encode("utf-16-le") not in datos)
        chequear("la dll no lanza EDA-Teclas.py", b"EDA-Teclas.py" not in datos and "EDA-Teclas.py".encode("utf-16-le") not in datos)
        i = identificar.leer(dll)
        chequear("la dll compilada tiene su identidad", i["identidad"] is not None, identificar.texto_identidad(i["identidad"]))
        j = dll + ".json"
        if os.path.isfile(j):
            chequear("la dll coincide con su d3d9.dll.json", identificar.main([dll, "--esperado", j]) == 0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    pruebas_git()
    pruebas_c()
    pruebas_identificar()
    pruebas_manifiestos()
    pruebas_sin_ventanas(sys.argv[1] if len(sys.argv) > 1 else None)
    print("prueba_version.py: %d bien · %d mal" % (OK, MAL))
    sys.exit(1 if MAL else 0)
