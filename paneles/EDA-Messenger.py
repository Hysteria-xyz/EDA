"""EDA-Messenger (MESSENGER; antes «Buddy»): la lista de amigos al estilo de EDA, y una ventana de conversación por amigo.

El cliente de 2009 no trae pantalla de messenger. Este panel la reemplaza: F11 (EDA-Atajos) o el
botón Messenger del lobby lo abren y lo cierran, en el lobby o en una sala.

Diseño (13-nov, copiado del lobby): placa «B U D D Y», la ficha del personaje como la del lobby
(Character Name / Lv en cian), pestañas Friends · Online como «Scenario», columnas en cian y filas
con marco claro («LV 30  Mazino»). Doble clic en un amigo = su ventana de conversación (Enter
manda; también a desconectados: lo lee al volver). Un mensaje nuevo abre la ventana sola.

Habla con el server por archivos de repo\\_trabajo\\servidor:
  · messenger_estado.json   → el server: cada cuenta con nick, nivel, conectado, dónde, amigos;
  · messenger_chat.jsonl    → el server: los mensajes (de, a, texto, hora), uno por línea;
  · messenger_pedidos.jsonl ← el panel: agregar, quitar, mensaje (el server los atiende en el tick).

    pythonw EDA-Messenger.py --cuenta rui
    python  EDA-Messenger.py --prueba
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERVIDOR = RAIZ / "repo" / "_trabajo" / "servidor"
ESTADO = SERVIDOR / "messenger_estado.json"
PEDIDOS = SERVIDOR / "messenger_pedidos.jsonl"
CHAT = SERVIDOR / "messenger_chat.jsonl"
PID = SERVIDOR / "messenger_panel.pid"
LOG = SERVIDOR / "messenger_panel.log"
CLASES = {1: "Warrior", 2: "Hunter"}
sys.path.insert(0, str(RAIZ))


def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8")).get("cuentas", {})
    except (OSError, ValueError):
        return {}


def pedir(de, accion, nick, texto=""):
    SERVIDOR.mkdir(parents=True, exist_ok=True)
    with open(PEDIDOS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"de": de, "accion": accion, "nick": nick, "texto": texto},
                           ensure_ascii=False) + "\n")


def filas_de(cuentas, yo):
    """[(cuenta, nick, nivel, clase, conectado, dónde)] de los amigos de `yo`: conectados primero."""
    filas = []
    for a in cuentas.get(yo, {}).get("amigos", []):
        d = cuentas.get(a, {})
        filas.append((a, d.get("nick", a), d.get("nivel", 0), d.get("clase", 1),
                      bool(d.get("conectado")), d.get("donde", "")))
    return sorted(filas, key=lambda f: (not f[4], f[1].lower()))


class Charla:
    """Lee messenger_chat.jsonl de a pedazos: los mensajes nuevos donde está `yo`."""

    def __init__(self, yo, ruta=None):
        self.yo, self.ruta, self.pos = yo, Path(ruta or CHAT), 0

    def nuevos(self):
        try:
            with open(self.ruta, "rb") as f:
                f.seek(self.pos)
                datos = f.read()
        except OSError:
            return []
        corte = datos.rfind(b"\n") + 1                       # (una línea a medio escribir, para después)
        self.pos += corte
        r = []
        for linea in datos[:corte].decode("utf-8", "replace").splitlines():
            try:
                m = json.loads(linea)
            except ValueError:
                continue
            if self.yo in (m.get("de"), m.get("a")):
                r.append(m)
        return r


def otro_de(m, yo):
    return m["a"] if m.get("de") == yo else m.get("de")


# ── las ventanas ───────────────────────────────────────────────────────────────────────────────
def panel(yo):
    import tkinter as tk
    import eda_ui as ui

    v = ui.Ventana("Messenger", 290, 600)
    ui.una_instancia(str(PID))
    e, sc = v.e, v.escala
    estado = {"sel": None, "firma": None, "pestana": "todos", "cuentas": {}, "sin_leer": {}}
    charlas = {}                                             # cuenta → ventana de conversación
    historia = {}                                            # cuenta → [mensajes]
    lector = Charla(yo)

    # dónde: a la derecha del juego, con su alto
    dato = ui.ventana_del_juego()
    if dato:
        (x, y, w, h), area = dato
        v.ubicar(ui.al_lado((x, y, w, h), area, v.ancho), y, max(e(480), h))
    else:
        v.ubicar(e(60), e(60))
    try:
        LOG.write_text("juego=%s\n" % (dato,), encoding="utf-8")
    except OSError:
        pass

    # la ficha (como la del lobby: Character Name / Lv)
    ficha_m, ficha = ui.panel(v.cuerpo)
    ficha_m.pack(fill="x", padx=e(8), pady=(e(6), e(4)))
    tk.Label(ficha, text="Character Name", bg=ui.PANEL, fg="#5b8fd6", font=ui.CHICA, anchor="w").grid(
        row=0, column=0, sticky="w", padx=e(8), pady=(e(4), 0))
    yo_nick = tk.Label(ficha, text=yo, bg=ui.PANEL, fg=ui.TEXTO, font=ui.FUENTE_B, anchor="w")
    yo_nick.grid(row=1, column=0, sticky="w", padx=e(8))
    tk.Label(ficha, text="Lv", bg=ui.PANEL, fg="#5b8fd6", font=ui.CHICA).grid(row=0, column=1, sticky="e",
                                                                              padx=e(8))
    yo_lv = tk.Label(ficha, text="", bg=ui.PANEL, fg=ui.ORO, font=ui.FUENTE_B)
    yo_lv.grid(row=1, column=1, sticky="e", padx=e(8))
    yo_donde = tk.Label(ficha, text="", bg=ui.PANEL, fg=ui.CIAN, font=ui.CHICA, anchor="w")
    yo_donde.grid(row=2, column=0, columnspan=2, sticky="w", padx=e(8), pady=(0, e(4)))
    ficha.grid_columnconfigure(0, weight=1)

    # pestañas
    barra = tk.Frame(v.cuerpo, bg=ui.FONDO)
    barra.pack(fill="x", padx=e(8), pady=(e(4), 0))
    p_todos = ui.Pestana(barra, "Friends", lambda: pestana("todos"), 100, 26, sc)
    p_online = ui.Pestana(barra, "Online", lambda: pestana("online"), 100, 26, sc)
    p_todos.pack(side="left")
    p_online.pack(side="left", padx=(1, 0))
    contador = tk.Label(barra, text="", bg=ui.FONDO, fg=ui.GRIS, font=ui.CHICA)
    contador.pack(side="right")

    lista_m, lista_p = ui.panel(v.cuerpo)
    lista_m.pack(fill="both", expand=True, padx=e(8))
    ui.cabecera(lista_p, [("", 0), ("Level", 1), ("Character Name", 3)]).pack(fill="x")
    lista = tk.Frame(lista_p, bg=ui.PANEL)
    lista.pack(fill="both", expand=True, padx=e(3), pady=e(3))

    # agregar / quitar (sin SEND: cada amigo tiene su ventana)
    abajo = tk.Frame(v.cuerpo, bg=ui.FONDO)
    abajo.pack(fill="x", padx=e(8), pady=(e(6), 0))
    nick_e = ui.entrada(abajo)
    nick_e.pack(side="left", fill="x", expand=True, ipady=e(3))
    ui.Boton(abajo, "ADD", lambda: agregar(), "teal", 58, 24, sc).pack(side="left", padx=(e(4), 0))
    abajo2 = tk.Frame(v.cuerpo, bg=ui.FONDO)
    abajo2.pack(fill="x", padx=e(8), pady=e(4))
    ui.Boton(abajo2, "CHAT", lambda: abrir_charla(estado["sel"]) if estado["sel"] else aviso(
        "Elige un amigo."), "morado", 80, 24, sc).pack(side="left")
    ui.Boton(abajo2, "DELETE", lambda: quitar(), "granate", 80, 24, sc).pack(side="right")
    linea = tk.Label(v.cuerpo, text="", bg=ui.NEGRO, fg=ui.GRIS, font=ui.CHICA, anchor="w")
    linea.pack(fill="x", side="bottom")
    nick_e.bind("<Return>", lambda ev: agregar())

    def aviso(texto, color=ui.GRIS):
        linea.configure(text=" " + texto, fg=color)
        v.tk.after(5000, lambda: linea.cget("text") == " " + texto and linea.configure(text=""))

    def agregar():
        nick = nick_e.get().strip()
        if nick:
            pedir(yo, "amigo", nick)
            nick_e.delete(0, "end")
            aviso("Pedido: agregar a %s" % nick)

    def quitar():
        f = next((x for x in filas_de(estado["cuentas"], yo) if x[0] == estado["sel"]), None)
        if not f:
            aviso("Elige un amigo de la lista.")
            return
        pedir(yo, "quitar", f[1])
        aviso("Pedido: quitar a %s" % f[1])

    def pestana(cual):
        estado["pestana"] = cual
        p_todos.elegir(cual == "todos")
        p_online.elegir(cual == "online")
        estado["firma"] = None
        refrescar(forzar=True)

    def dibujar():
        for w in lista.winfo_children():
            w.destroy()
        filas = filas_de(estado["cuentas"], yo)
        en_linea = sum(1 for f in filas if f[4])
        contador.configure(text="%d / %d online" % (en_linea, len(filas)))
        if estado["pestana"] == "online":
            filas = [f for f in filas if f[4]]
        if not filas:
            tk.Label(lista, text="Sin amigos todavía.\nEscribe un nick y pulsa ADD." if estado["pestana"] ==
                     "todos" else "Nadie conectado.", bg=ui.PANEL, fg=ui.GRIS, font=ui.CHICA,
                     justify="center").pack(pady=e(20))
        for cuenta, nick, nv, clase, conectado, donde in filas:
            sel = cuenta == estado["sel"]
            fondo = "#3a0b0b" if sel else "#0b0c0e"
            f = tk.Frame(lista, bg=fondo, highlightthickness=1,
                         highlightbackground=ui.ROJO_LUZ if sel else ui.ACERO_CLARO, cursor="hand2")
            f.pack(fill="x", padx=e(2), pady=e(2))
            punto = tk.Canvas(f, width=e(12), height=e(12), bg=fondo, highlightthickness=0)
            punto.create_oval(2, 2, e(10), e(10), fill=ui.VERDE if conectado else "#3a3d42",
                              outline="#000000")
            punto.grid(row=0, column=0, rowspan=2, padx=(e(5), e(3)))
            tk.Label(f, text=("LV %d" % nv) if nv else "LV —", bg=fondo, fg=ui.TEXTO if conectado else ui.GRIS,
                     font=ui.FUENTE, width=6, anchor="w").grid(row=0, column=1, sticky="w")
            tk.Label(f, text=nick, bg=fondo, fg=ui.TEXTO if conectado else ui.GRIS, font=ui.FUENTE_B,
                     anchor="w").grid(row=0, column=2, sticky="w")
            n = estado["sin_leer"].get(cuenta, 0)
            if n:
                tk.Label(f, text=" %d " % n, bg=ui.ROJO_VIVO, fg="#ffffff", font=ui.CHICA).grid(
                    row=0, column=3, sticky="e", padx=e(4))
            tk.Label(f, text=(CLASES.get(clase, "") + " · " + donde) if conectado else "desconectado", bg=fondo,
                     fg=ui.CIAN if conectado else "#55595f", font=ui.CHICA, anchor="w").grid(
                row=1, column=1, columnspan=3, sticky="w")
            f.grid_columnconfigure(2, weight=1)
            for w in [f] + f.winfo_children():
                w.bind("<Button-1>", lambda ev, c=cuenta: elegir(c))
                w.bind("<Double-Button-1>", lambda ev, c=cuenta: abrir_charla(c))

    def elegir(c):
        # (redibujar recién después: si no, el 2º clic del doble clic cae en una fila ya borrada)
        estado["sel"] = c
        estado["firma"] = None
        v.tk.after(300, lambda: refrescar(forzar=True))

    # ── la ventana de conversación ──────────────────────────────────────────────────────────
    def abrir_charla(cuenta, al_frente=True):
        if cuenta in charlas:
            if al_frente:
                charlas[cuenta]["v"].tk.deiconify()
                charlas[cuenta]["v"].tk.lift()
            return charlas[cuenta]
        d = estado["cuentas"].get(cuenta, {})
        cv = ui.Ventana("Chat", 340, 300, raiz=v.tk, placa=d.get("nick", cuenta),
                        al_cerrar=lambda: cerrar_charla(cuenta))
        n = len(charlas)
        px, py = v.tk.winfo_x() - cv.ancho - e(6), v.tk.winfo_y() + e(40) + n * e(36)
        if px < 0:
            px = v.tk.winfo_x() + e(30)
        cv.ubicar(px, py)
        info = tk.Label(cv.cuerpo, text="", bg=ui.FONDO, fg=ui.CIAN, font=ui.CHICA, anchor="w")
        info.pack(fill="x", padx=e(8), pady=(e(4), e(2)))
        fila = tk.Frame(cv.cuerpo, bg=ui.FONDO)              # (abajo primero: el texto no la tapa)
        fila.pack(side="bottom", fill="x", padx=e(8), pady=e(6))
        m, adentro = ui.panel(cv.cuerpo)
        m.pack(fill="both", expand=True, padx=e(8))
        texto = tk.Text(adentro, bg="#000000", fg=ui.TEXTO, font=ui.FUENTE, wrap="word", relief="flat",
                        highlightthickness=0, padx=e(6), pady=e(4), state="disabled", cursor="arrow",
                        height=6)
        texto.pack(fill="both", expand=True)
        texto.tag_configure("yo", foreground=ui.TEXTO)
        texto.tag_configure("el", foreground=ui.VERDE_CHAT)
        texto.tag_configure("hora", foreground="#55595f", font=ui.CHICA)
        texto.tag_configure("aviso", foreground=ui.ORO, font=ui.CHICA)
        ent = ui.entrada(fila)
        ent.pack(side="left", fill="x", expand=True, ipady=e(4))
        ent.insert(0, "")

        def mandar(ev=None):
            t = ent.get().strip()
            if not t:
                return
            pedir(yo, "mensaje", d.get("nick", cuenta), t)
            ent.delete(0, "end")
        ent.bind("<Return>", mandar)
        ui.Boton(fila, "↵", mandar, "teal", 34, 26, sc).pack(side="left", padx=(e(4), 0))
        charlas[cuenta] = {"v": cv, "texto": texto, "info": info, "ent": ent}
        for msg in historia.get(cuenta, [])[-80:]:
            escribir(cuenta, msg)
        estado["sin_leer"].pop(cuenta, None)
        poner_info(cuenta)
        estado["firma"] = None
        cv.tk.after(50, ent.focus_force)

        def medir():
            try:
                with open(LOG, "a", encoding="utf-8") as fh:
                    fh.write("charla %s geo=%s cuerpo=%sx%s fila=%s@%s escala=%.2f\n" % (
                        cuenta, cv.tk.winfo_geometry(), cv.cuerpo.winfo_width(), cv.cuerpo.winfo_height(),
                        fila.winfo_height(), fila.winfo_y(), cv.escala))
            except OSError:
                pass
        cv.tk.after(800, medir)
        return charlas[cuenta]

    def cerrar_charla(cuenta):
        c = charlas.pop(cuenta, None)
        if c:
            c["v"].tk.destroy()

    def poner_info(cuenta):
        c = charlas.get(cuenta)
        if not c:
            return
        d = estado["cuentas"].get(cuenta, {})
        c["info"].configure(text=("● LV %s · %s · %s" % (d.get("nivel") or "—", CLASES.get(d.get("clase", 1), ""),
                                                          d.get("donde", "")))
                            if d.get("conectado") else "○ desconectado: lo leerá al volver",
                            fg=ui.VERDE if d.get("conectado") else ui.GRIS)

    def escribir(cuenta, msg):
        c = charlas.get(cuenta)
        if not c:
            return
        t = c["texto"]
        t.configure(state="normal")
        if msg.get("de") == "*":
            t.insert("end", msg.get("texto", "") + "\n", "aviso")
        else:
            mio = msg.get("de") == yo
            quien = estado["cuentas"].get(msg.get("de"), {}).get("nick", msg.get("de"))
            t.insert("end", "%s " % msg.get("hora", ""), "hora")
            t.insert("end", "[%s]: %s\n" % (quien, msg.get("texto", "")), "yo" if mio else "el")
        t.configure(state="disabled")
        t.see("end")

    def leer_mensajes(primera=False):
        for msg in lector.nuevos():
            otro = otro_de(msg, yo)
            historia.setdefault(otro, []).append(msg)
            if primera:
                continue
            if otro in charlas:
                escribir(otro, msg)
            elif msg.get("de") != yo:                        # uno nuevo: se abre su ventana
                estado["sin_leer"][otro] = estado["sin_leer"].get(otro, 0) + 1
                abrir_charla(otro, al_frente=True)
                estado["firma"] = None

    def refrescar(forzar=False):
        cuentas = leer_estado()
        estado["cuentas"] = cuentas
        mio = cuentas.get(yo, {})
        yo_nick.configure(text=mio.get("nick", yo))
        yo_lv.configure(text="%sLV" % (mio.get("nivel") or "—"))
        yo_donde.configure(text="%s · %s" % (CLASES.get(mio.get("clase", 1), ""), mio.get("donde") or "en línea"))
        firma = json.dumps([filas_de(cuentas, yo), estado["sel"], estado["pestana"],
                            sorted(estado["sin_leer"].items())])
        if forzar or firma != estado["firma"]:
            estado["firma"] = firma
            dibujar()
        for c in list(charlas):
            poner_info(c)

    def ciclo():
        try:
            leer_mensajes()
            refrescar()
        except Exception as error:                           # noqa: BLE001
            aviso("error: %r" % error, ui.ROJO_LUZ)
        v.tk.after(700, ciclo)

    leer_mensajes(primera=True)
    pestana("todos")
    v.tk.after(700, ciclo)
    v.tk.mainloop()


def prueba():
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(bool(c))
    cuentas = {"rui": {"nick": "Mazino", "amigos": ["kai", "mio"]},
               "kai": {"nick": "kai", "nivel": 3, "conectado": False},
               "mio": {"nick": "Mio", "nivel": 7, "clase": 2, "conectado": True, "donde": "en la sala 1"}}
    f = filas_de(cuentas, "rui")
    chequear("los amigos de rui, conectados primero", [x[0] for x in f] == ["mio", "kai"])
    chequear("cada fila con nick, nivel, clase y dónde", f[0] == ("mio", "Mio", 7, 2, True, "en la sala 1"))
    chequear("★ el revés: una cuenta sin amigos → lista vacía", filas_de(cuentas, "kai") == [])
    global PEDIDOS
    viejo = PEDIDOS
    PEDIDOS = Path("/tmp/eda_msn_prueba.jsonl")
    if PEDIDOS.exists():
        PEDIDOS.unlink()
    pedir("rui", "mensaje", "Mio", "hola ñandú")
    pedir("rui", "amigo", "ren")
    lineas = [json.loads(x) for x in PEDIDOS.read_text(encoding="utf-8").splitlines()]
    chequear("los pedidos van de a uno por línea (con acentos)",
             lineas == [{"de": "rui", "accion": "mensaje", "nick": "Mio", "texto": "hola ñandú"},
                        {"de": "rui", "accion": "amigo", "nick": "ren", "texto": ""}])
    PEDIDOS.unlink()
    PEDIDOS = viejo
    # la charla: sólo los míos, de a pedazos, y una línea a medio escribir espera
    ruta = Path("/tmp/eda_chat_prueba.jsonl")
    ruta.write_text(json.dumps({"de": "rui", "a": "kai", "texto": "hola", "hora": "19:40"}) + "\n" +
                    json.dumps({"de": "mio", "a": "kai", "texto": "no es mío"}) + "\n", encoding="utf-8")
    ch = Charla("rui", ruta)
    chequear("charla: sólo los mensajes donde estoy", [m["texto"] for m in ch.nuevos()] == ["hola"])
    with open(ruta, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"de": "kai", "a": "rui", "texto": "qué tal"}) + "\n" + '{"de": "kai", "a"')
    chequear("charla: lo nuevo, sin repetir", [m["texto"] for m in ch.nuevos()] == ["qué tal"])
    with open(ruta, "a", encoding="utf-8") as fh:
        fh.write(': "rui", "texto": "completo"}\n')
    chequear("★ el revés: la línea a medio escribir se lee cuando se completa",
             [m["texto"] for m in ch.nuevos()] == ["completo"])
    chequear("el otro de cada mensaje", otro_de({"de": "rui", "a": "kai"}, "rui") == "kai"
             and otro_de({"de": "kai", "a": "rui"}, "rui") == "kai")
    ruta.unlink()
    print("\n→ TODO BIEN" if all(ok) else "\n→ ⛔ ALGO FALLA")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        sys.exit(prueba())
    cuenta = sys.argv[sys.argv.index("--cuenta") + 1] if "--cuenta" in sys.argv else "rui"
    try:
        panel(cuenta)
    except Exception:                                         # noqa: BLE001  (pythonw no muestra errores)
        import traceback
        SERVIDOR.mkdir(parents=True, exist_ok=True)
        LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise
