r"""identificar -- ¿QUÉ d3d9.dll hay instalada, y es la que se esperaba? (sin conexión, sólo lee archivos)

    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado d3d9.dll.json        # el de compilar.py
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado cliente-develop.json # el canal develop
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado eda.json             # el del launcher
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado exe\d3d9.dll         # otra dll
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado LISTA --carpeta JUEGO  # + todo el cliente
    py herramientas\dll_d3d9\identificar.py ... --json                                     # para otro programa

Lee la marca «EDA-ID|v=…|c=…|s=…|f=…|b=…|» que eda_version.c deja en la dll (una dll SIN marca es anterior al
versionado: «antigua»), calcula md5 y sha256 del archivo y, con --esperado, compara con lo que el esperado
REALMENTE dice (nada se inventa: un dato que el manifiesto no trae se informa como «no disponible»):

  · d3d9.dll.json (compilar.py): identidad de la dll + md5/sha256/tam del archivo;
  · cliente-develop.json (canal.py): la identidad arriba + `files` [{path, size, md5, sha256}];
  · el manifiesto del launcher, eda.json (armar_cliente.py): {version (= la de la RELEASE, no la de la dll),
    base, servidor, canje, files: [{path, size, md5}]}; también firmado (JWS de firmar_manifiesto.py), y la
    forma vieja `archivos` [{ruta, tam, md5}]. No trae commit ni build: eso no se compara;
  · otra dll: los dos md5 y las dos identidades.
Con --carpeta, además, cada archivo de la lista en esa carpeta: que esté, su tamaño y su md5/sha256 (los del
jugador, autoexec.cfg y eda_d3d9.ini, pueden ser distintos: se avisa, no es un error).
Un manifiesto que no se puede leer, sin la d3d9.dll, sin hash o con datos que no cierran es un ERROR (1), no
una coincidencia. Sale con 0 = coincide · 1 = no se pudo leer / manifiesto incorrecto · 2 = NO COINCIDE ·
3 = dll antigua (sin identidad, sin --esperado). No cambia ni copia nada.
"""
import base64
import hashlib
import json
import os
import re
import sys

MARCA = re.compile(rb"EDA-ID\|v=([0-9.]{1,16})\|c=([0-9A-Za-z-]{1,40})\|s=([01])\|f=([^|\x00]{1,40})\|b=([0-9A-Za-z-]{1,40})\|")
CLAVES = ("version", "commit", "sucio", "fecha", "build")
DEL_JUGADOR = ("autoexec.cfg", "eda_d3d9.ini")             # el launcher los baja sólo si faltan
HEX32 = re.compile(r"[0-9a-fA-F]{32}")
HEX64 = re.compile(r"[0-9a-fA-F]{64}")
NO_DISPONIBLE = "no disponible"


class ManifiestoMalo(Exception):
    """el esperado no se puede usar: no se lee, le falta la dll o un hash, o sus datos no cierran"""


def _huellas(datos):
    return {"tam": len(datos), "md5": hashlib.md5(datos).hexdigest(), "sha256": hashlib.sha256(datos).hexdigest()}


def leer(ruta):
    datos = open(ruta, "rb").read()
    info = dict(ruta=ruta, identidad=None, **_huellas(datos))
    m = MARCA.search(datos)
    if m:
        v, c, s, f, b = (x.decode("utf-8", "replace") for x in m.groups())
        info["identidad"] = {"version": v, "commit": c, "sucio": int(s), "fecha": f, "build": b}
    return info


def _entrada(f, i):
    """una entrada de `files` (path/size/md5/sha256) o de `archivos` (ruta/tam/md5), normalizada y revisada"""
    if not isinstance(f, dict):
        raise ManifiestoMalo("la entrada %d de la lista no es un objeto" % i)
    path = f.get("path", f.get("ruta"))
    if not isinstance(path, str) or not path.strip():
        raise ManifiestoMalo("la entrada %d no tiene ruta (path)" % i)
    p = path.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
        raise ManifiestoMalo("ruta peligrosa en la lista: %r" % path)
    e = {"path": p, "size": None, "md5": None, "sha256": None, "url": f.get("url")}
    tam = f.get("size", f.get("tam"))
    if tam is not None:
        if isinstance(tam, bool) or not isinstance(tam, int) or tam < 0:
            raise ManifiestoMalo("%s: tamaño inválido %r" % (p, tam))
        e["size"] = tam
    for k, rx in (("md5", HEX32), ("sha256", HEX64)):
        v = f.get(k)
        if v is not None:
            if not isinstance(v, str) or not rx.fullmatch(v):
                raise ManifiestoMalo("%s: %s inválido %r" % (p, k, v))
            e[k] = v.lower()
    return e


def _identidad_de(j):
    """la identidad de la DLL que trae un json, sólo si de verdad la trae (commit y build): la `version` sola de
    un manifiesto del launcher es la de la RELEASE, no la de la dll"""
    if not ("commit" in j and "build" in j):
        return None
    return {k: j[k] for k in CLAVES if k in j}


def cargar(ruta):
    """lo que se espera, de un d3d9.dll.json, un cliente-develop.json, un manifiesto del launcher u otra dll"""
    if ruta.lower().endswith(".dll"):
        o = leer(ruta)
        return {"origen": "dll %s" % ruta, "tipo": "dll", "md5": o["md5"], "sha256": o["sha256"], "tam": o["tam"],
                "identidad": o["identidad"], "release": None, "files": None}
    try:
        texto = open(ruta, "rb").read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise ManifiestoMalo("no pude leer %s (%s)" % (ruta, e))
    t = texto.strip()
    if not t.startswith("{") and t.count(".") == 2:          # un JWS (manifiesto firmado): la carga
        try:
            carga = t.split(".")[1]
            t = base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)).decode("utf-8")
        except Exception as e:                               # noqa: BLE001
            raise ManifiestoMalo("%s parece firmado pero la carga no se lee (%s)" % (ruta, e))
    try:
        j = json.loads(t)
    except ValueError as e:
        raise ManifiestoMalo("%s no es JSON (%s)" % (ruta, e))
    if not isinstance(j, dict):
        raise ManifiestoMalo("%s no es un objeto JSON" % ruta)
    ident = _identidad_de(j)
    lista = j.get("files", j.get("archivos"))
    if lista is not None:                                    # el launcher o el canal develop
        if not isinstance(lista, list):
            raise ManifiestoMalo("%s: «files» no es una lista" % ruta)
        files = [_entrada(f, i) for i, f in enumerate(lista)]
        dll = [f for f in files if f["path"].lower() == "d3d9.dll"]
        if not dll:
            otra = [f["path"] for f in files if f["path"].lower().rsplit("/", 1)[-1] == "d3d9.dll"]
            raise ManifiestoMalo("%s no trae la d3d9.dll en la raíz del juego%s" % (
                ruta, " (la pone en %s)" % ", ".join(otra) if otra else ""))
        if len(dll) > 1:
            raise ManifiestoMalo("%s trae la d3d9.dll %d veces" % (ruta, len(dll)))
        d = dll[0]
        if not d["md5"] and not d["sha256"]:
            raise ManifiestoMalo("%s: la d3d9.dll no tiene md5 ni sha256: no se puede verificar" % ruta)
        # (cliente-develop.json repite arriba el md5/sha256/tam de la dll: si no cierran, la lista está rota)
        for arriba, abajo in (("md5", "md5"), ("sha256", "sha256"), ("tam", "size")):
            if j.get(arriba) is not None and d[abajo] is not None and str(j[arriba]).lower() != str(d[abajo]).lower():
                raise ManifiestoMalo("%s no cierra: arriba %s %s y en files %s" % (ruta, arriba, j[arriba], d[abajo]))
        tipo = "canal develop" if j.get("canal") else "launcher" if ident is None else "lista"
        release = j.get("version") if ident is None else None
        return {"origen": "%s %s%s" % ("manifiesto del launcher" if tipo == "launcher" else "lista del " + tipo, ruta,
                                       " (release %s)" % release if release else ""),
                "tipo": tipo, "md5": d["md5"], "sha256": d["sha256"], "tam": d["size"], "identidad": ident,
                "release": release, "files": files}
    md5, sha = j.get("md5"), j.get("sha256")                 # d3d9.dll.json de compilar.py
    if md5 is None and sha is None:
        raise ManifiestoMalo("%s no trae «files» ni el md5/sha256 de la dll: no es un manifiesto conocido" % ruta)
    e = _entrada({"path": "d3d9.dll", "md5": md5, "sha256": sha, "size": j.get("tam")}, 0)
    return {"origen": "compilación %s" % ruta, "tipo": "compilacion", "md5": e["md5"], "sha256": e["sha256"],
            "tam": e["size"], "identidad": ident, "release": None, "files": None}


def _esperado(ruta):                                         # (el nombre de antes)
    return cargar(ruta)


def comparar(info, esp):
    """las diferencias (lista vacía = coincide), sólo de lo que el esperado REALMENTE trae"""
    dif = []
    if esp.get("md5") and esp["md5"] != info["md5"]:
        dif.append("md5: instalada %s · esperada %s" % (info["md5"], esp["md5"]))
    if esp.get("sha256") and esp["sha256"] != info["sha256"]:
        dif.append("sha256: instalada %s… · esperada %s…" % (info["sha256"][:16], esp["sha256"][:16]))
    if esp.get("tam") is not None and int(esp["tam"]) != info["tam"]:
        dif.append("tamaño: instalada %d B · esperada %s B" % (info["tam"], esp["tam"]))
    a, b = info.get("identidad"), esp.get("identidad")
    if b and not a:
        dif.append("identidad: la instalada no tiene (antigua) · se esperaba EDA %s" % b.get("version", "?"))
    elif a and b:
        for k in ("version", "commit", "sucio", "build"):
            if k in b and str(a.get(k)) != str(b.get(k)):
                dif.append("%s: instalada %s · esperada %s" % (k, a.get(k), b.get(k)))
    return dif


def verificar_carpeta(esp, carpeta):
    """cada archivo de la lista en `carpeta`: (errores, avisos). Sólo lo que la lista trae (tamaño, md5, sha256)."""
    errores, avisos = [], []
    if not esp.get("files"):
        return ["el esperado no es una lista de archivos: --carpeta necesita un manifiesto con «files»"], avisos
    for f in esp["files"]:
        ruta = os.path.join(carpeta, *f["path"].split("/"))
        del_jugador = f["path"].lower() in DEL_JUGADOR
        if not os.path.isfile(ruta):
            (avisos if del_jugador else errores).append("%s: falta" % f["path"])
            continue
        h = _huellas(open(ruta, "rb").read())
        mal = [k for k, kk in (("size", "tam"), ("md5", "md5"), ("sha256", "sha256"))
               if f[k] is not None and str(f[k]) != str(h[kk])]
        if mal:
            texto = "%s: distinto (%s)" % (f["path"], ", ".join(mal))
            if del_jugador:
                avisos.append(texto + " — es del jugador: normal si lo cambió")
            else:
                errores.append(texto)
        if f["md5"] is None and f["sha256"] is None:
            avisos.append("%s: la lista no trae hash (sólo se miró %s)" % (
                f["path"], "el tamaño" if f["size"] is not None else "que esté"))
    return errores, avisos


def texto_identidad(i):
    if not i:
        return "SIN IDENTIDAD: dll anterior al versionado (antigua) o de otro origen"
    return "EDA %s · commit %s%s · build %s · compilada %s" % (
        i.get("version", NO_DISPONIBLE), i.get("commit", NO_DISPONIBLE),
        "-dirty (LOCAL, no publicada)" if i.get("sucio") else "", i.get("build", NO_DISPONIBLE),
        i.get("fecha", NO_DISPONIBLE))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    ruta = argv[0]
    if not os.path.isfile(ruta):
        print("⛔ no existe %s" % ruta)
        return 1
    info = leer(ruta)
    esp, err_man, carp = None, None, ([], [])
    if "--esperado" in argv:
        i = argv.index("--esperado")
        if i + 1 >= len(argv) or not os.path.isfile(argv[i + 1]):
            print("⛔ falta el archivo de --esperado")
            return 1
        try:
            esp = cargar(argv[i + 1])
        except ManifiestoMalo as e:
            err_man = str(e)
    if esp and "--carpeta" in argv:
        i = argv.index("--carpeta")
        carp = verificar_carpeta(esp, argv[i + 1]) if i + 1 < len(argv) else (["falta la carpeta de --carpeta"], [])
    dif = comparar(info, esp) if esp else []
    if err_man:
        codigo = 1
    elif esp:
        codigo = 2 if (dif or carp[0]) else 0
    else:
        codigo = 3 if not info["identidad"] else 0
    if "--json" in argv:
        print(json.dumps({"instalada": info, "esperada": esp, "manifiesto_incorrecto": err_man, "diferencias": dif,
                          "carpeta_errores": carp[0], "carpeta_avisos": carp[1], "codigo": codigo},
                         ensure_ascii=False, indent=2))
        return codigo
    print("dll:       %s (%d B)" % (ruta, info["tam"]))
    print("md5:       %s" % info["md5"])
    print("sha256:    %s" % info["sha256"])
    print("identidad: %s" % texto_identidad(info["identidad"]))
    if err_man:
        print("⛔ MANIFIESTO INCORRECTO: %s" % err_man)
        return codigo
    if esp:
        print("esperada:  %s" % esp["origen"])
        print("           md5 %s · sha256 %s · tamaño %s" % (
            esp["md5"] or NO_DISPONIBLE, (esp["sha256"][:16] + "…") if esp["sha256"] else NO_DISPONIBLE,
            "%s B" % esp["tam"] if esp["tam"] is not None else NO_DISPONIBLE))
        if esp.get("identidad"):
            print("           %s" % texto_identidad(esp["identidad"]))
        else:
            print("           identidad de la dll (versión, commit, build): %s en este manifiesto — se comparan "
                  "los hashes" % NO_DISPONIBLE)
        if dif:
            print("⛔ NO COINCIDE:")
            for d in dif:
                print("   · " + d)
        if "--carpeta" in argv:
            for e in carp[0]:
                print("   ⛔ carpeta: " + e)
            for a in carp[1]:
                print("   ⚠ carpeta: " + a)
            if not carp[0]:
                print("   carpeta: %d archivos de la lista revisados" % len(esp.get("files") or []))
        if not dif and not carp[0]:
            print("✅ COINCIDE")
    elif not info["identidad"]:
        print("⚠ dll antigua: no dice qué versión es")
    return codigo


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
