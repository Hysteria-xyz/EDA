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
    pruebas_sin_ventanas(sys.argv[1] if len(sys.argv) > 1 else None)
    print("prueba_version.py: %d bien · %d mal" % (OK, MAL))
    sys.exit(1 if MAL else 0)
