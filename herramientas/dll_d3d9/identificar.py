r"""identificar -- ¿QUÉ d3d9.dll hay instalada, y es la que se esperaba? (sin conexión, sólo lee archivos)

    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado d3d9.dll.json     # el de compilar.py
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado eda.json          # el del launcher
    py herramientas\dll_d3d9\identificar.py RUTA\d3d9.dll --esperado exe\d3d9.dll      # otra dll
    py herramientas\dll_d3d9\identificar.py ... --json                                  # para otro programa

Lee la marca «EDA-ID|v=…|c=…|s=…|f=…|b=…|» que eda_version.c deja en la dll (una dll SIN marca es anterior al
versionado: «antigua»), calcula md5 y sha256 del archivo y, con --esperado, compara:
  · un d3d9.dll.json (compilar.py): md5/sha256 y la identidad;
  · un eda.json o manifiesto del launcher (version, archivos[{ruta, md5, tam}]): el md5 de la entrada d3d9.dll;
  · otra dll: los dos md5 y las dos identidades.
Sale con 0 = coincide · 1 = no se pudo leer · 2 = NO COINCIDE · 3 = dll antigua (sin identidad).
No cambia ni copia nada.
"""
import hashlib
import json
import os
import re
import sys

MARCA = re.compile(rb"EDA-ID\|v=([0-9.]{1,16})\|c=([0-9A-Za-z-]{1,40})\|s=([01])\|f=([^|\x00]{1,40})\|b=([0-9A-Za-z-]{1,40})\|")


def leer(ruta):
    datos = open(ruta, "rb").read()
    info = {"ruta": ruta, "tam": len(datos), "md5": hashlib.md5(datos).hexdigest(),
            "sha256": hashlib.sha256(datos).hexdigest(), "identidad": None}
    m = MARCA.search(datos)
    if m:
        v, c, s, f, b = (x.decode("utf-8", "replace") for x in m.groups())
        info["identidad"] = {"version": v, "commit": c, "sucio": int(s), "fecha": f, "build": b}
    return info


def _esperado(ruta):
    """lo que se espera, de un d3d9.dll.json, de un manifiesto del launcher o de otra dll"""
    if ruta.lower().endswith(".dll"):
        o = leer(ruta)
        return {"origen": "dll %s" % ruta, "md5": o["md5"], "sha256": o["sha256"], "identidad": o["identidad"],
                "tam": o["tam"]}
    texto = open(ruta, encoding="utf-8-sig").read()
    if texto.count(".") >= 2 and not texto.lstrip().startswith("{"):     # un JWS (manifiesto firmado): la carga
        import base64
        carga = texto.strip().split(".")[1]
        texto = base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)).decode("utf-8")
    j = json.loads(texto)
    if "archivos" in j:                                                  # el manifiesto del launcher
        for a in j["archivos"]:
            if os.path.basename(str(a.get("ruta", "")).replace("\\", "/")).lower() == "d3d9.dll":
                return {"origen": "manifiesto del paquete %s (versión %s)" % (ruta, j.get("version", "?")),
                        "md5": str(a.get("md5", "")).lower(), "sha256": None, "identidad": None, "tam": a.get("tam")}
        raise SystemExit("⛔ el manifiesto %s no tiene una entrada d3d9.dll" % ruta)
    ident = {k: j[k] for k in ("version", "commit", "sucio", "fecha", "build") if k in j}
    return {"origen": "compilación %s" % ruta, "md5": str(j.get("md5", "")).lower(), "sha256": j.get("sha256"),
            "identidad": ident or None, "tam": j.get("tam")}


def comparar(info, esp):
    """las diferencias (lista vacía = coincide)"""
    dif = []
    if esp.get("md5") and esp["md5"] != info["md5"]:
        dif.append("md5: instalada %s · esperada %s" % (info["md5"], esp["md5"]))
    if esp.get("sha256") and esp["sha256"] != info["sha256"]:
        dif.append("sha256 distinto")
    if esp.get("tam") is not None and int(esp["tam"]) != info["tam"]:
        dif.append("tamaño: instalada %d B · esperada %s B" % (info["tam"], esp["tam"]))
    a, b = info.get("identidad"), esp.get("identidad")
    if a and b:
        for k in ("version", "commit", "sucio", "build"):
            if k in b and str(a.get(k)) != str(b.get(k)):
                dif.append("%s: instalada %s · esperada %s" % (k, a.get(k), b.get(k)))
    return dif


def texto_identidad(i):
    if not i:
        return "SIN IDENTIDAD: dll anterior al versionado (antigua) o de otro origen"
    return "EDA %s · commit %s%s · build %s · compilada %s" % (i["version"], i["commit"],
                                                                "-dirty (LOCAL, no publicada)" if i["sucio"] else "",
                                                                i["build"], i["fecha"])


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    ruta = argv[0]
    if not os.path.isfile(ruta):
        print("⛔ no existe %s" % ruta)
        return 1
    info = leer(ruta)
    esp = _esperado(argv[argv.index("--esperado") + 1]) if "--esperado" in argv else None
    dif = comparar(info, esp) if esp else []
    codigo = 2 if dif else 3 if not info["identidad"] else 0
    if "--json" in argv:
        print(json.dumps({"instalada": info, "esperada": esp, "diferencias": dif, "codigo": codigo},
                         ensure_ascii=False, indent=2))
        return codigo
    print("dll:       %s (%d B)" % (ruta, info["tam"]))
    print("md5:       %s" % info["md5"])
    print("sha256:    %s" % info["sha256"])
    print("identidad: %s" % texto_identidad(info["identidad"]))
    if esp:
        print("esperada:  %s · md5 %s" % (esp["origen"], esp["md5"] or "?"))
        if esp.get("identidad"):
            print("           %s" % texto_identidad(esp["identidad"]))
        if dif:
            print("⛔ NO COINCIDE:")
            for d in dif:
                print("   · " + d)
        else:
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
