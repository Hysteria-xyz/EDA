r"""version -- la IDENTIDAD de cada compilación de la d3d9.dll, calculada sola (sin editar el código).

    py herramientas\dll_d3d9\version.py                    # muestra la identidad (JSON)
    py herramientas\dll_d3d9\version.py --header SALIDA.h  # escribe eda_version.h (lo usa compilar.py y el CI)

Lo que entra en la dll (eda_version.h → eda_version.c):
  version  el número de VERSION (al lado de este archivo). Es lo ÚNICO que se cambia a mano, y sólo al
           sacar una versión nueva; todo lo demás sale solo.
  commit   el ÚLTIMO commit que tocó el CÓDIGO que se compila (los .c/.h/.def y VERSION de
           herramientas/dll_d3d9/, sin las pruebas), no HEAD. Así, commitear exe/d3d9.dll después de compilarla,
           o tocar una prueba, un .py o el LEEME, no cambia el commit: el CI recompila exactamente la misma dll.
  sucio    1 si ese código tiene cambios sin commitear (o archivos nuevos, o no hay git):
           la compilación es LOCAL y nunca se confunde con una publicada.
  fecha    limpia: la fecha del commit (UTC) → la compilación es reproducible. Sucia: la hora real.
  build    «b» + 10 hex del sha256 del CÓDIGO que se compila (finales de línea normalizados): mismo código =
           mismo build en cualquier PC; un cambio de una letra = otro build.

⚠ El hash del archivo FINAL no puede estar adentro de la dll (escribirlo cambiaría el hash): ese lo anota
compilar.py en d3d9.dll.json, al lado, y lo comprueba identificar.py.

Todo funciona sin conexión: sólo lee el git local.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
CARPETA = "herramientas/dll_d3d9"
# lo que NO es código de la dll (lo genera la compilación, o son las pruebas)
NO_ENTRA = {"eda_version.h", "eda_traduccion_datos.h", "d3d9.dll.json"}
EXT_CODIGO = (".c", ".h", ".def")


def _git():
    """git, aunque no esté en el PATH (ENTORNOS §2.4: los .bat lo buscan en los mismos lugares)."""
    g = shutil.which("git")
    if g:
        return g
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        p = os.path.join(base, "Git", "cmd", "git.exe")
        if base and os.path.isfile(p):
            return p
    return None


def _correr(git, *args, raiz=RAIZ):
    r = subprocess.run([git, "-C", raiz] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else None


def leer_version(carpeta=AQUI):
    try:
        v = open(os.path.join(carpeta, "VERSION"), encoding="utf-8").read().strip()
    except OSError:
        return "0.0.0"
    ok = v and all(p.isdigit() for p in v.split(".")) and len(v) <= 16
    return v if ok else "0.0.0"


def huella_codigo(carpeta=AQUI):
    """sha256 del código que se compila: los .c/.h/.def + VERSION + traduccion/<idioma>/** (si existe), con LF."""
    h = hashlib.sha256()
    nombres = sorted(n for n in os.listdir(carpeta)
                     if (n.endswith(EXT_CODIGO) or n == "VERSION") and n not in NO_ENTRA
                     and not n.startswith("prueba_"))
    for n in nombres:
        datos = open(os.path.join(carpeta, n), "rb").read().replace(b"\r\n", b"\n")
        h.update(n.encode() + b"\0" + str(len(datos)).encode() + b"\0" + datos)
    trad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(carpeta))), "traduccion")
    if os.path.isdir(trad):
        entradas = []
        for idi in sorted(os.listdir(trad)):
            if idi == "herramientas" or idi.startswith((".", "_")):
                continue
            carp_idi = os.path.join(trad, idi)
            if not os.path.isdir(carp_idi):
                continue
            for base, dirs, files in os.walk(carp_idi):
                dirs.sort()
                for fn in sorted(files):
                    p = os.path.join(base, fn)
                    rel_p = os.path.relpath(p, os.path.dirname(trad)).replace("\\", "/")
                    entradas.append((rel_p, p))
        for rel_p, p in sorted(entradas):
            datos = open(p, "rb").read().replace(b"\r\n", b"\n")
            h.update(rel_p.encode("utf-8") + b"\0" + str(len(datos)).encode() + b"\0" + datos)
    return "b" + h.hexdigest()[:10]


def _codigo(rel, raiz=None):
    """el código que entra en la dll, como pathspecs de git (lo mismo que huella_codigo)"""
    specs = ([":(glob)%s/*%s" % (rel, e) for e in EXT_CODIGO] + [":(glob)%s/VERSION" % rel,
             ":(exclude,glob)%s/prueba_*" % rel] + [":(exclude)%s/%s" % (rel, n) for n in sorted(NO_ENTRA)])
    if raiz and os.path.isdir(os.path.join(raiz, "traduccion")):
        specs += [":(glob)traduccion/*/**", ":(exclude,glob)traduccion/herramientas/**",
                  ":(exclude)traduccion/LEEME.md"]
    return specs


def identidad(raiz=RAIZ, carpeta=AQUI, ahora=None):
    """La identidad de una compilación hecha AHORA desde `carpeta` (dentro del repo `raiz`)."""
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    ident = {"version": leer_version(carpeta), "commit": "sin-git", "commit_largo": "", "sucio": 1,
             "fecha": ahora.strftime("%Y-%m-%d %H:%M UTC"), "build": huella_codigo(carpeta),
             "cambios": [], "en_github": None}
    git = _git()
    rel = os.path.relpath(carpeta, raiz).replace("\\", "/")
    if not git or _correr(git, "rev-parse", "--is-inside-work-tree", raiz=raiz) != "true":
        ident["cambios"] = ["(no hay git: compilación LOCAL)"]
        return ident
    specs = _codigo(rel, raiz)
    largo = _correr(git, "log", "-1", "--format=%H", "--", *specs, raiz=raiz)
    if not largo:
        ident["cambios"] = ["(la carpeta no tiene commits: compilación LOCAL)"]
        return ident
    ident["commit_largo"] = largo
    ident["commit"] = largo[:7]
    estado = _correr(git, "status", "--porcelain", "--untracked-files=all", "--", *specs, raiz=raiz) or ""
    cambios = [l for l in estado.splitlines() if l.strip()
               and os.path.basename(l[3:].strip().strip('"')) not in NO_ENTRA]
    ident["cambios"] = cambios
    ident["sucio"] = 1 if cambios else 0
    if not cambios:                                  # limpia: la fecha del commit (reproducible)
        f = _correr(git, "log", "-1", "--format=%ct", largo, raiz=raiz)
        if f and f.isdigit():
            ident["fecha"] = datetime.datetime.fromtimestamp(int(f), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    remotas = _correr(git, "branch", "-r", "--contains", largo, raiz=raiz)   # (informativo, sin red)
    ident["en_github"] = bool(remotas) if remotas is not None else None
    return ident


def _c(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def header(ident):
    """eda_version.h: SÓLO lo reproducible (nada de en_github ni la lista de cambios)."""
    return ("/* eda_version.h -- GENERADO por version.py al compilar: no editar ni commitear */\n"
            "#define EDA_VERSION %s\n#define EDA_COMMIT %s\n#define EDA_SUCIO %d\n"
            "#define EDA_FECHA %s\n#define EDA_BUILD %s\n" %
            (_c(ident["version"]), _c(ident["commit"]), ident["sucio"], _c(ident["fecha"]), _c(ident["build"])))


def escribir_header(ruta, ident=None):
    ident = ident or identidad()
    open(ruta, "w", encoding="utf-8", newline="\n").write(header(ident))
    return ident


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    if "--header" in sys.argv:
        i = sys.argv.index("--header")
        ruta = sys.argv[i + 1] if i + 1 < len(sys.argv) else os.path.join(AQUI, "eda_version.h")
        idt = escribir_header(ruta)
        print("%s → EDA %s · commit %s%s · build %s · %s" % (ruta, idt["version"], idt["commit"],
              "-dirty (LOCAL)" if idt["sucio"] else "", idt["build"], idt["fecha"]))
    else:
        print(json.dumps(identidad(), ensure_ascii=False, indent=2))
