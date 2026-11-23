r"""hoja -- la planilla de traducción (Excel .xlsx) de ida y vuelta, sin librerías externas.

    python traduccion/herramientas/hoja.py exportar [salida.xlsx] [previa.xlsx]
    python traduccion/herramientas/hoja.py importar entrada.xlsx [--idioma es]
    python traduccion/herramientas/hoja.py control

Las columnas son ID · PANTALLA · INGLÉS · ESPAÑOL · MÁX. LETRAS · OJO. Solo se lee la columna ESPAÑOL;
se busca la fila por el ID, así que da igual si se ordena o filtra la planilla. Una celda vacía = se deja el inglés.
`importar` copia el texto TAL CUAL (no corrige nada) y avisa si faltan o sobran `[TEXTO]` / `[NÚMERO]` respecto del inglés.
"""
import html
import json
import os
import re
import sys
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)                                    # traduccion/
RAIZ_REPO = os.path.dirname(BASE)                               # raíz del repo
SALIDA_ES = os.path.join(BASE, "es")


def _buscar_ruta(env_var, candidatos, es_dir=False):
    val = os.environ.get(env_var)
    if val:
        return val
    for c in candidatos:
        if (os.path.isdir(c) if es_dir else os.path.isfile(c)):
            return c
    return candidatos[0]


TEXTOS = _buscar_ruta("EDA_TRADUCCION_TEXTOS", [
    os.path.join(RAIZ_REPO, "_trabajo", "textos-en.json"),
    os.path.join(BASE, "textos-en.json"),
    os.path.normpath(os.path.join(RAIZ_REPO, "..", "..", "pruebas", "laboratorio", "traduccion", "textos-en.json")),
], es_dir=False)

DESEMPACADO = _buscar_ruta("EDA_TRADUCCION_DESEMPACADO", [
    os.path.join(RAIZ_REPO, "_trabajo", "traduccion_desempacado"),
    os.path.join(BASE, "desempacado"),
    os.path.normpath(os.path.join(RAIZ_REPO, "..", "..", "pruebas", "laboratorio", "traduccion", "desempacado")),
], es_dir=True)

XML_ES_ESPERADOS = (
    "data/scenario/string/international/chapter1_string.xml",
    "string/international/err_string.xml",
    "string/international/mapnameandexplainstring.xml",
    "string/international/nameandexplainstring.xml",
    "string/international/uistring.xml",
)

COLUMNAS = ["ID", "PANTALLA", "INGLÉS", "ESPAÑOL", "MÁX. LETRAS", "OJO"]
ANCHOS = [24, 34, 70, 70, 12, 40]
# ★ (23-nov) en la planilla solo va TEXTO para traducir: las marcas del juego se muestran como [NÚMERO] o
#   [TEXTO] y el salto de línea «\n» como un salto de línea DENTRO de la celda (Alt+Enter en Excel). `importar` las vuelve a poner.
BN = chr(92) + "n"
HUECO = re.compile(r"%\d+![a-z]+!|%[-+ 0#]*\d*(?:\.\d+)?[sdifxXcu]")
SIN_TRADUCIR = ("filtro_chat", "motor_lithtech", "exe_hardcoded")       # opcionales o aplicados en la DLL

# ★ (23-nov) rótulos que en español se pisaban con los números: versiones cortas acordadas
ACORDADOS = {"ui:21": "Atq. melé:", "ui:22": "Def. melé:", "ui:23": "Atq. dist.:", "ui:24": "Def. dist.:",
             "ui:27": "Vel. atq.:", "ui:28": "Vel. mov.:", "ui:30": "T. tensión:",
             "ui:5033": "Encantar", "ui:5034": "Refinar piedra",
             # ficha del ítem: se pisaban con «Requiere Lv.» y con «100%»
             "ui:5074": "Todas", "ui:5053": "Durab.:", "ui:5076": "No equipable"}
# las filas de stats que se pisaban con el número (ui:21…30): a lo sumo 2 letras más que el inglés
RÓTULOS = {"ui:%d" % n for n in range(21, 31)} | {"ui:5053", "ui:5074", "ui:5076"}
DESCRIPCION_MAX = 45          # la descripción de un ítem: una línea corta, para que no tape los stats
# ★ el juego corta por LETRAS, no por palabras («enemi / gos»): para estos cuadros medidos en capturas, la herramienta mete
#   saltos de línea entre palabras (a lo sumo N letras por renglón)
AJUSTE = {"map_objetivo": 25, "map_historia": 25, "ui:3053": 46, "ui:3054": 46, "ui:3055": 46}


def ajustar(texto, ancho):
    """Saltos de línea entre palabras para que ningún renglón pase de `ancho` letras (respeta los saltos que ya haya)."""
    renglones = []
    for parrafo in texto.split(BN):
        actual = ""
        for palabra in parrafo.split(" "):
            if actual and len(actual) + 1 + len(palabra) > ancho:
                renglones.append(actual)
                actual = palabra
            else:
                actual = (actual + " " + palabra) if actual else palabra
        renglones.append(actual)
    return BN.join(renglones)


def limite(c):
    if c["id"] in RÓTULOS:
        return len(c["texto_en"]) + 2
    if c["bloque"] == "item_descripcion":
        return DESCRIPCION_MAX
    return c.get("largo_max") or ""


MARCAS = re.compile(r"%[-+ 0#]*\d*(?:\.\d+)?[sdifxXcu]|\\n")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                               # noqa: BLE001
    pass


def cadenas():
    with open(TEXTOS, encoding="utf-8") as f:
        d = json.load(f)
    return [c for c in d["cadenas"] if c.get("idioma_origen", "en") == "en"]


def para_traducir():
    """Solo lo que tiene texto para traducir: sin el filtro de chat, el motor ni el exe, y sin las filas que son solo
    marcas o teclas (por ejemplo «%d ms» o «TAB + 1»)."""
    fuera = []
    for c in cadenas():
        if c["bloque"] in SIN_TRADUCIR:
            continue
        resto = HUECO.sub("", c["texto_en"]).replace(BN, " ")
        if not re.search(r"[A-Za-z]{2,}", resto) or re.fullmatch(r"\s*TAB\s*\+\s*\d+\s*", c["texto_en"]):
            continue
        fuera.append(c)
    return fuera


def _nombre_hueco(marca):
    return "[TEXTO]" if marca.endswith("s") or marca.endswith("s!") else "[NÚMERO]"


def a_planilla(texto):
    """«%s user has %d.\\nOK» → «[TEXTO] user has [NÚMERO].» + salto de línea real + «OK»."""
    return HUECO.sub(lambda m: _nombre_hueco(m.group(0)), texto).replace(BN, "\n")


def de_planilla(texto_es, texto_en):
    """La vuelta: cada [TEXTO]/[NÚMERO] se cambia, EN ORDEN, por la marca original del inglés; el salto de línea, por «\\n».
    Devuelve (texto para el juego, aviso o None)."""
    marcas = HUECO.findall(texto_en)
    huecos = re.findall(r"\[(?:TEXTO|N[ÚU]MERO)\]", texto_es, flags=re.I)
    aviso = None
    if [_nombre_hueco(m) for m in marcas] != [h.upper().replace("NUMERO", "NÚMERO") for h in huecos]:
        aviso = "los [ ] no coinciden con el inglés: tiene %s y el español %s" % (
            [_nombre_hueco(m) for m in marcas] or "ninguno", huecos or "ninguno")
    it = iter(marcas)
    salida = re.sub(r"\[(?:TEXTO|N[ÚU]MERO)\]", lambda m: next(it, m.group(0)), texto_es, flags=re.I)
    return salida.replace("\r\n", "\n").replace("\n", BN), aviso


def _col(i):
    return chr(ord("A") + i)


def _celda(ref, valor, estilo=1):
    """estilo 1 = texto con ajuste de línea arriba a la izquierda; 2 = encabezado; 3 = la columna ESPAÑOL (fondo amarillo)."""
    if valor is None or valor == "":
        return '<c r="%s" s="%d"/>' % (ref, estilo)
    if isinstance(valor, (int, float)):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, estilo, valor)
    texto = escape(str(valor))
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, estilo, texto)


ESTILOS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/'
           'spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/>'
           '<name val="Calibri"/></font></fonts><fills count="5"><fill><patternFill patternType="none"/></fill><fill>'
           '<patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9E1F2"/>'
           '</patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/></patternFill></fill><fill><patternFill patternType="solid">'
           '<fgColor rgb="FFF8CBAD"/></patternFill></fill></fills>'
           '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="5"><xf/>'
           '<xf applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
           '<xf fontId="1" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf>'
           '<xf fillId="3" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
           '<xf fontId="1" fillId="4" applyFont="1" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
           '</cellXfs></styleSheet>')


def escribir_xlsx(ruta, filas):
    hoja = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews>', '<cols>']
    hoja += ['<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w) for i, w in enumerate(ANCHOS)]
    hoja.append('</cols><sheetData>')
    for r, fila in enumerate([COLUMNAS] + filas, start=1):
        hoja.append('<row r="%d">%s</row>' % (r, "".join(
            _celda("%s%d" % (_col(i), r), v, 2 if r == 1 else 3 if COLUMNAS[i] == "ESPAÑOL"
                   else 4 if COLUMNAS[i] == "OJO" and str(v).startswith("⛔") else 1)
            for i, v in enumerate(fila))))
    hoja.append('</sheetData><autoFilter ref="A1:%s%d"/></worksheet>' % (_col(len(COLUMNAS) - 1), len(filas) + 1))
    partes = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
        'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/'
        'workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override '
        'PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.'
        'worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
        'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.'
        'openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships"><sheets><sheet name="Traduccion" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http:'
        '//schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship '
        'Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>',
        "xl/worksheets/sheet1.xml": "".join(hoja),
        "xl/styles.xml": ESTILOS,
    }
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in partes.items():
            z.writestr(nombre, contenido.encode("utf-8"))


def leer_xlsx(ruta):
    """Devuelve {ID: texto de la columna ESPAÑOL}. Lee inlineStr y sharedStrings (Excel guarda con sharedStrings)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(ruta) as z:
        compartidas = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                compartidas.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        hojas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        raiz = ET.fromstring(z.read(hojas[0]))
    filas = []
    for row in raiz.iter("{%s}row" % ns["m"]):
        fila = {}
        for c in row.findall("m:c", ns):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            if c.get("t") == "inlineStr":
                v = "".join(t.text or "" for t in c.iter("{%s}t" % ns["m"]))
            elif c.get("t") == "s":
                v = compartidas[int(c.find("m:v", ns).text)]
            else:
                v = c.find("m:v", ns).text if c.find("m:v", ns) is not None else ""
            fila[col] = v
        filas.append(fila)
    cab = {v: k for k, v in filas[0].items()}
    cid, ces = cab["ID"], cab["ESPAÑOL"]
    return {f.get(cid): f.get(ces, "") for f in filas[1:] if f.get(cid)}


def exportar(salida, desde=None):
    """`desde` = una planilla ya llena: se conserva su ESPAÑOL (y se aplican los rótulos ACORDADOS)."""
    previo = leer_xlsx(desde) if desde else {}
    filas, rojas = [], 0
    for c in para_traducir():
        es = ACORDADOS.get(c["id"]) or previo.get(c["id"]) or a_planilla(c.get("texto_es") or "")
        ojo = []
        if HUECO.search(c["texto_en"]):
            ojo.append("Deja los [ ] en el MISMO orden: el juego pone ahí un número o un nombre")
        if BN in c["texto_en"]:
            ojo.append("Tiene saltos de línea (Alt+Enter en la celda)")
        tope = limite(c)
        if c["id"] in ACORDADOS:
            ojo.append("Versión corta acordada (la larga se pisaba con el número)")
        if tope and es and len(es.replace(chr(10), "")) > tope:
            ojo.insert(0, "⛔ NO ENTRA: %d letras, máximo %d" % (len(es.replace(chr(10), "")), tope))
            rojas += 1
        if c["id"] in AJUSTE or c["bloque"] in AJUSTE:
            ojo.append("Los saltos de línea entre palabras los pone la herramienta")
        filas.append([c["id"], c.get("pantalla") or "", a_planilla(c["texto_en"]), es, tope, " · ".join(ojo)])
    escribir_xlsx(salida, filas)
    print("✅ %s · %d textos · %d que NO ENTRAN (columna OJO)" % (salida, len(filas), rojas))


def importar(entrada, con_ajuste=True, salida_dir=None):
    """Solo los textos de Data.dat (XML <STRING INDEX="n" VALUE="..."/>): se copia el ESPAÑOL tal cual."""
    destino_base = salida_dir or SALIDA_ES
    es = leer_xlsx(entrada)
    por_id = {c["id"]: c for c in cadenas()}
    avisos, por_archivo = [], {}
    for i, texto in es.items():
        c = por_id.get(i)
        if not c or not (texto or "").strip():
            continue
        texto, aviso = de_planilla(texto, c["texto_en"])
        ancho = AJUSTE.get(c["id"]) or AJUSTE.get(c["bloque"])
        if con_ajuste and ancho and BN not in texto:
            texto = ajustar(texto, ancho)
        if aviso:
            avisos.append("⚠ %s: %s" % (i, aviso))
        if c["origen"].startswith("Data.dat:"):
            por_archivo.setdefault(c["origen"][len("Data.dat:"):], []).append((c, texto))
        else:
            avisos.append("· %s (%s): no está en Data.dat, va en la DLL" % (i, c["origen"]))
    for ruta, lista in por_archivo.items():
        with open(os.path.join(DESEMPACADO, *ruta.split("/")), encoding="utf-8-sig") as f:
            orig = f.read()
        for c, texto in lista:
            # ⚠ en mapnameandexplainstring.xml el mismo INDEX se repite en 5 bloques (nombre, historia, objetivo, nivel,
            #   coreano): se reemplaza el que tiene ese INDEX Y todavía dice el inglés original de esta fila
            #   · y en nameandexplainstring.xml hay INDEX repetidos a propósito: el id trae «#k» = la k-ésima aparición
            indice = c["id"].rsplit(":", 1)[-1]
            indice, _, k = indice.partition("#")
            patron = re.compile(r'(<STRING\s+INDEX="\s*%s\s*"\s+VALUE=")([^"]*)(")' % re.escape(str(indice)))
            nuevo = escape(texto, {'"': "&quot;"})
            hecho = False
            for n, m in enumerate(patron.finditer(orig), start=1):
                if (n == int(k)) if k else (html.unescape(m.group(2)) == c["texto_en"]):
                    orig = orig[:m.start(2)] + nuevo + orig[m.end(2):]
                    hecho = True
                    break
            if not hecho:
                avisos.append("⚠ %s: no encontré INDEX=%s con el inglés original en %s" % (c["id"], indice, ruta))
        destino = os.path.join(destino_base, *ruta.split("/"))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8-sig", newline="") as f:
            f.write(orig)
        print("✅ %s · %d textos" % (destino, len(lista)))
    for a in avisos:
        print(a)
    print("→ %d textos en español aplicados · %d avisos" % (sum(len(v) for v in por_archivo.values()), len(avisos)))


def _validar_xmls_repo():
    """Comprueba que los 5 XML en traduccion/es/ existen, son UTF-8 y XML válidos."""
    ok = True
    total_strings = 0
    for rel in XML_ES_ESPERADOS:
        p = os.path.join(SALIDA_ES, *rel.split("/"))
        if not os.path.isfile(p):
            print("⛔ falta XML traducido en el repo: %s" % rel)
            ok = False
            continue
        try:
            raw = open(p, encoding="utf-8-sig").read()
            raiz = ET.fromstring(raw)
            n = len(raiz.findall(".//STRING"))
            total_strings += n
            if n == 0:
                print("⛔ XML sin nodos <STRING>: %s" % rel)
                ok = False
        except Exception as e:                                    # noqa: BLE001
            print("⛔ XML inválido %s: %s" % (rel, e))
            ok = False
    print(("✅" if ok else "⛔") + " repo traduccion/es/: %d XML válidos (%d cadenas <STRING>)" % (
        len(XML_ES_ESPERADOS), total_strings))
    return ok


def _control_sintetico():
    """Prueba autocontenida (funciona en CI sin Data.dat): exportar, leer, huecos, ajuste, importar y revés."""
    import contextlib
    import io
    import shutil
    global TEXTOS, DESEMPACADO, SALIDA_ES
    t = tempfile.mkdtemp(prefix="eda_hoja_")
    antes = (TEXTOS, DESEMPACADO, SALIDA_ES)
    try:
        des = os.path.join(t, "des")
        sal = os.path.join(t, "es")
        os.makedirs(os.path.join(des, "string", "international"))
        xml_orig = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<STRINGINFO>\r\n'
            '  <STRING INDEX="10" VALUE="%s gained %d gold.\\nCheck &quot;Bag&quot;." />\r\n'
            '  <STRING INDEX="10" VALUE="Second entry" />\r\n'
            '  <STRING INDEX="21" VALUE="Melee Atk:" />\r\n'
            '</STRINGINFO>\r\n'
        )
        with open(os.path.join(des, "string", "international", "uistring.xml"), "w", encoding="utf-8-sig", newline="") as f:
            f.write(xml_orig)
        datos = {
            "cadenas": [
                {"id": "ui:10", "origen": "Data.dat:string/international/uistring.xml", "bloque": "ui",
                 "pantalla": "General", "idioma_origen": "en", "texto_en": "%s gained %d gold.\\nCheck \"Bag\"."},
                {"id": "ui:10#2", "origen": "Data.dat:string/international/uistring.xml", "bloque": "ui",
                 "pantalla": "General", "idioma_origen": "en", "texto_en": "Second entry"},
                {"id": "ui:21", "origen": "Data.dat:string/international/uistring.xml", "bloque": "ui",
                 "pantalla": "Stats", "idioma_origen": "en", "texto_en": "Melee Atk:"},
            ]
        }
        txt_json = os.path.join(t, "textos-en.json")
        with open(txt_json, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        TEXTOS, DESEMPACADO, SALIDA_ES = txt_json, des, sal

        xlsx = os.path.join(t, "hoja.xlsx")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exportar(xlsx)
        leido = leer_xlsx(xlsx)
        ok_exp = list(leido) == ["ui:10", "ui:10#2", "ui:21"] and leido["ui:21"] == ACORDADOS["ui:21"]

        # Revés: si faltan o cambian los [TEXTO]/[NÚMERO], de_planilla debe avisar
        _, aviso_mal = de_planilla("Ganaste [NÚMERO] oro", "%s gained %d gold.")
        ok_reves = aviso_mal is not None

        # Ajuste de línea por palabras
        ok_aj = ajustar("uno dos tres cuatro cinco", 10) == "uno dos" + BN + "tres" + BN + "cuatro" + BN + "cinco"

        # Importar traducción en español con huecos, salto de línea, comillas y duplicado #2
        filas = [
            ["ui:10", "General", a_planilla(datos["cadenas"][0]["texto_en"]),
             '[TEXTO] ganó [NÚMERO] de oro.\nMira "Bolsa".', "", ""],
            ["ui:10#2", "General", "Second entry", "Segunda entrada ñó", "", ""],
            ["ui:21", "Stats", "Melee Atk:", ACORDADOS["ui:21"], "", ""],
        ]
        escribir_xlsx(xlsx, filas)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            importar(xlsx, con_ajuste=False)
        out_xml = os.path.join(sal, "string", "international", "uistring.xml")
        raiz = ET.parse(out_xml).getroot()
        vals = [n.attrib["VALUE"] for n in raiz.findall("STRING")]
        ok_imp = vals == [
            '%s ganó %d de oro.\\nMira "Bolsa".',
            "Segunda entrada ñó",
            ACORDADOS["ui:21"],
        ]
        ok = ok_exp and ok_reves and ok_aj and ok_imp
        print(("✅" if ok else "⛔") + " control autocontenido (exportar/importar/huecos/duplicados/revés)")
        return ok
    finally:
        TEXTOS, DESEMPACADO, SALIDA_ES = antes
        shutil.rmtree(t, ignore_errors=True)


def control():
    import contextlib
    import io
    import shutil
    ok_repo = _validar_xmls_repo()
    ok_sint = _control_sintetico()
    if not (os.path.isfile(TEXTOS) and os.path.isdir(DESEMPACADO)):
        print("· textos-en.json / desempacado no están en este entorno (CI sin Data.dat): se omitió la ida y vuelta completa")
        return ok_repo and ok_sint

    tdir = tempfile.mkdtemp(prefix="eda_hoja_full_")
    global SALIDA_ES
    antes = SALIDA_ES
    try:
        tmp = os.path.join(tdir, "control.xlsx")
        exportar(tmp)
        leido = leer_xlsx(tmp)
        ids = [c["id"] for c in para_traducir()]
        ok = list(leido) == ids and all(v == ACORDADOS.get(k, "") for k, v in leido.items())
        print(("✅" if ok else "⛔") + " ida y vuelta: %d ids iguales y columna ESPAÑOL vacía (salvo los %d rótulos acordados)"
              % (len(ids), len(ACORDADOS)))
        # ★ importar: TODAS las filas de Data.dat con un texto marcado se tienen que encontrar (también los INDEX repetidos del
        #   archivo de mapas), y el XML resultante tiene que seguir siendo XML válido
        SALIDA_ES = os.path.join(tdir, "es")
        filas = []
        for c in para_traducir():
            filas.append([c["id"], "", a_planilla(c["texto_en"]), a_planilla(c["texto_en"]), "", ""])   # ES = EN
        # ★ y los [ ] vuelven a ser EXACTAMENTE las marcas del inglés (y los saltos de línea de la celda, la marca BN)
        malas = [c["id"] for c in para_traducir() if de_planilla(a_planilla(c["texto_en"]), c["texto_en"]) != (c["texto_en"], None)]
        print(("✅" if not malas else "⛔") + " [NÚMERO]/[TEXTO] y saltos de línea vuelven idénticos al original"
              + ("" if not malas else ": %s" % malas[:5]))
        escribir_xlsx(tmp, filas)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            importar(tmp, con_ajuste=False)
        salida = buf.getvalue()
        faltan = [x for x in salida.splitlines() if "no encontré" in x]
        validos = True
        for raiz, _, archivos in os.walk(SALIDA_ES):
            for a in archivos:
                try:
                    ET.parse(os.path.join(raiz, a))
                except ET.ParseError as e:
                    validos = False
                    print("⛔ XML inválido %s: %s" % (a, e))
        # con ES = EN, los XML generados tienen que quedar IGUALES al original (salvo entidades equivalentes y BOM)
        distintos = []
        for raiz, _, archivos in os.walk(SALIDA_ES):
            for a in archivos:
                rel = os.path.relpath(os.path.join(raiz, a), SALIDA_ES)
                leer_vals = lambda r: [(i.strip(), html.unescape(v)) for i, v in re.findall(
                    r'<STRING\s+INDEX="([^"]*)"\s+VALUE="([^"]*)"', open(r, encoding="utf-8-sig").read())]
                if leer_vals(os.path.join(raiz, a)) != leer_vals(os.path.join(DESEMPACADO, rel)):
                    distintos.append(rel)
        print(("✅" if not distintos else "⛔") + " con el español = inglés, los XML salen idénticos al original"
              + ("" if not distintos else ": %s" % distintos))
        ok2 = not faltan and validos and not malas and not distintos
        print(("✅" if ok2 else "⛔") + " importar: todos los textos de Data.dat encontrados y los XML siguen válidos"
              + ("" if not faltan else " · faltan %d: %s" % (len(faltan), faltan[:3])))
        return ok_repo and ok_sint and ok and ok2
    finally:
        SALIDA_ES = antes
        shutil.rmtree(tdir, ignore_errors=True)


if __name__ == "__main__":
    a = sys.argv[1:] or ["control"]
    idioma = None
    if "--idioma" in a:
        idx = a.index("--idioma")
        if idx + 1 < len(a):
            idioma = a[idx + 1]
            a = a[:idx] + a[idx + 2:]
    if a[0] == "exportar":
        exportar(a[1] if len(a) > 1 else os.path.join(RAIZ_REPO, "_trabajo", "EDA-traduccion.xlsx"),
                 a[2] if len(a) > 2 else None)
    elif a[0] == "importar":
        destino = os.path.join(BASE, idioma) if idioma else SALIDA_ES
        importar(a[1], salida_dir=destino)
    else:
        sys.exit(0 if control() else 1)
