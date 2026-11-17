/* eda_messenger.c — ★ EL MESSENGER DE EDA, ADENTRO DE LA DLL (Punto 2, 16-nov). Se compila con eda_d3d9.c (#include,
 *  DESPUÉS de eda_opciones.c: usa su dibujo, su GDI, sus letras y su manejo del cursor).
 *
 *  Es paneles/EDA-Messenger.py (Tk) pasado a la dll, para que ande IGUAL en local y en multijugador sin Python:
 *   · la ficha (Character Name / Lv / clase · dónde), las pestañas Friends · Online con el contador, la lista con el
 *     punto verde, «LV n  Nick», la clase y dónde está, y el globo rojo de mensajes sin leer;
 *   · ADD (teal), CHAT (morado), DELETE (granate) y la línea de estado;
 *   · la conversación con el amigo elegido (en el panel de Python era otra ventana; acá es la mitad derecha de la
 *     MISMA ventana: una sola ventana, un solo foco, nada que pueda quedar suelto detrás del juego).
 *  Cómo se maneja (lo de Options, que ya funciona): ventana DEL juego (su dueño es EDA, sin TOPMOST), el juego no
 *  recibe teclado ni mouse mientras está abierta (g_panel_abierto), el cursor se ve sobre ella y vuelve a su lugar
 *  al cerrar, F11 es su interruptor (también con ella al frente), y sólo hay un panel a la vez (Options o Messenger).
 *  Los datos: el server los manda por el chat (0x1005) con el nombre «[MSN]» (servidor/messenger.py: L/A = la
 *  lista, h/H = mensajes) y la dll se los queda (el juego no los muestra); las acciones salen como los comandos de
 *  chat de siempre (/amigo, /quitar, /m), mandados desde el hilo del juego (la cola, desde PeekMessageA). */

#define MSN_ANCHO 640
#define MSN_ALTO 500
#define MSN_AMIGOS 24
#define MSN_HIST 200
#define MSN_COLA 8

typedef struct { WCHAR cuenta[24], nick[24], donde[48]; int nivel, clase, conectado, sin_leer; } MSN_AMIGO;
typedef struct { WCHAR de[24], a[24], hora[8], texto[160]; } MSN_MSG;

static CRITICAL_SECTION g_msn_cs;
static int g_msn_cs_lista;
static MSN_AMIGO g_msn_am[MSN_AMIGOS];
static int g_msn_nam, g_msn_hay_lista;
static WCHAR g_msn_yo[24], g_msn_yo_nick[24], g_msn_yo_donde[48];
static int g_msn_yo_nivel, g_msn_yo_clase;
static MSN_MSG g_msn_h[MSN_HIST];
static int g_msn_nh;
static WCHAR g_msn_sel[24];                       /* la cuenta elegida ("" = ninguna) */
static WCHAR g_msn_aviso[160];                    /* la línea de estado (lo último de «[Messenger]» o un pedido) */
static int g_msn_pestana, g_msn_scroll, g_msn_scroll_chat;
static HWND g_msn_nick_e, g_msn_texto_e;
static HBRUSH g_msn_pincel;
static WCHAR g_msn_cola[MSN_COLA][176];
static int g_msn_ncola;

static void msn_listo(void)
{
    if (!g_msn_cs_lista) { InitializeCriticalSection(&g_msn_cs); g_msn_cs_lista = 1; }
}
static void msn_repintar(void)
{
    HWND v = g_msn_ventana;
    if (v) PostMessageW(v, WM_APP + 7, 0, 0);
}
static void msn_avisar(const WCHAR *t)
{
    if (!g_msn_cs_lista) return;
    EnterCriticalSection(&g_msn_cs);
    lstrcpynW(g_msn_aviso, t, 160);
    LeaveCriticalSection(&g_msn_cs);
    msn_repintar();
}

/* ── lo que se manda al server: en la cola, y desde el hilo del juego (como la consola de Options) ── */
static void msn_encolar(const WCHAR *t)
{
    if (!g_msn_cs_lista) return;
    EnterCriticalSection(&g_msn_cs);
    if (g_msn_ncola < MSN_COLA) lstrcpynW(g_msn_cola[g_msn_ncola++], t, 176);
    LeaveCriticalSection(&g_msn_cs);
}
static void msn_correr_cola(void)                 /* (hilo del juego: mi_peek) */
{
    WCHAR lista[MSN_COLA][176];
    int n;
    if (!g_msn_cs_lista || !g_msn_ncola) return;
    EnterCriticalSection(&g_msn_cs);
    n = g_msn_ncola;
    memcpy(lista, g_msn_cola, sizeof(lista));
    g_msn_ncola = 0;
    LeaveCriticalSection(&g_msn_cs);
    for (int i = 0; i < n; i++) chat_w(lista[i]);
}

/* ── lo que llega del server («[MSN]»): se llama en el hilo del juego, desde el puente del chat ── */
static MSN_AMIGO *msn_amigo(const WCHAR *cuenta)
{
    for (int i = 0; i < g_msn_nam; i++)
        if (!lstrcmpiW(g_msn_am[i].cuenta, cuenta)) return &g_msn_am[i];
    return NULL;
}
static int msn_campos(WCHAR *linea, WCHAR **f, int max)
{
    int n = 0;
    f[n++] = linea;
    for (WCHAR *p = linea; *p && n < max; p++)
        if (*p == L'\t') { *p = 0; f[n++] = p + 1; }
    return n;
}
static void msn_recibir(WCHAR *t)
{
    if (!g_msn_cs_lista) return;
    EnterCriticalSection(&g_msn_cs);
    WCHAR *linea = t;
    while (linea && *linea) {
        WCHAR *fin = linea;
        while (*fin && *fin != L'\n') fin++;
        WCHAR *sig = *fin ? fin + 1 : NULL;
        *fin = 0;
        WCHAR *f[7];
        int n = msn_campos(linea, f, 7);
        if (f[0][0] == L'L' && n >= 6) {                         /* yo: cuenta, nick, nivel, clase, dónde */
            MSN_AMIGO viejos[MSN_AMIGOS];
            int nv = g_msn_nam;
            memcpy(viejos, g_msn_am, sizeof(viejos));
            g_msn_nam = 0;
            lstrcpynW(g_msn_yo, f[1], 24);
            lstrcpynW(g_msn_yo_nick, f[2], 24);
            g_msn_yo_nivel = _wtoi(f[3]);
            g_msn_yo_clase = _wtoi(f[4]);
            lstrcpynW(g_msn_yo_donde, f[5], 48);
            g_msn_hay_lista = 1;
            for (WCHAR *l2 = sig; l2 && *l2; ) {                 /* las A que siguen, en el mismo paquete */
                WCHAR *fin2 = l2;
                while (*fin2 && *fin2 != L'\n') fin2++;
                WCHAR *sig2 = *fin2 ? fin2 + 1 : NULL;
                *fin2 = 0;
                WCHAR *a[7];
                if (msn_campos(l2, a, 7) >= 7 && a[0][0] == L'A' && g_msn_nam < MSN_AMIGOS) {
                    MSN_AMIGO *x = &g_msn_am[g_msn_nam++];
                    lstrcpynW(x->cuenta, a[1], 24);
                    lstrcpynW(x->nick, a[2], 24);
                    x->nivel = _wtoi(a[3]);
                    x->clase = _wtoi(a[4]);
                    x->conectado = _wtoi(a[5]);
                    lstrcpynW(x->donde, a[6], 48);
                    x->sin_leer = 0;
                    for (int k = 0; k < nv; k++)
                        if (!lstrcmpiW(viejos[k].cuenta, x->cuenta)) x->sin_leer = viejos[k].sin_leer;
                }
                l2 = sig2;
            }
            sig = NULL;                                          /* (ya se leyó todo el paquete) */
        } else if ((f[0][0] == L'H' || f[0][0] == L'h') && n >= 5) {   /* un mensaje: de, a, hora, texto */
            if (g_msn_nh == MSN_HIST) { memmove(g_msn_h, g_msn_h + 1, sizeof(MSN_MSG) * (MSN_HIST - 1)); g_msn_nh--; }
            MSN_MSG *m = &g_msn_h[g_msn_nh++];
            lstrcpynW(m->de, f[1], 24);
            lstrcpynW(m->a, f[2], 24);
            lstrcpynW(m->hora, f[3], 8);
            lstrcpynW(m->texto, f[4], 160);
            /* (h = de la historia, al abrir: no cuenta como nuevo) */
            if (f[0][0] == L'H' && lstrcmpiW(m->de, g_msn_yo) && (!g_msn_ventana || lstrcmpiW(g_msn_sel, m->de))) {
                MSN_AMIGO *x = msn_amigo(m->de);
                if (x) x->sin_leer++;
            }
            if (!lstrcmpiW(g_msn_sel, m->de) || !lstrcmpiW(g_msn_sel, m->a)) g_msn_scroll_chat = 0;
        }
        linea = sig;
    }
    LeaveCriticalSection(&g_msn_cs);
    msn_repintar();
}

/* ════════════════════════════════ LA VENTANA ════════════════════════════════ */
enum { M_X = 1, M_PESTANA, M_FILA, M_ADD, M_CHAT, M_DEL, M_ENVIAR };
typedef struct { RECT r; int tipo, id; } MCTL;
static MCTL g_mctl[48];
static int g_nmctl, g_mencima = -1;
static int m_registrar(int x0, int y0, int x1, int y1, int tipo, int id)
{
    if (g_nmctl >= 48) return -1;
    SetRect(&g_mctl[g_nmctl].r, x0, y0, x1, y1);
    g_mctl[g_nmctl].tipo = tipo;
    g_mctl[g_nmctl].id = id;
    return g_nmctl++;
}
static int m_ctl_en(int x, int y)
{
    POINT p = {x, y};
    for (int i = g_nmctl - 1; i >= 0; i--)
        if (PtInRect(&g_mctl[i].r, p)) return i;
    return -1;
}
/* el Boton de eda_ui.py (el de Options, con el registro del Messenger) */
static void m_boton(HDC d, int x, int y, int w, int h, const WCHAR *t, int estilo, int tipo, int id)
{
    int k = m_registrar(x, y, x + w, y + h, tipo, id), sobre = k >= 0 && k == g_mencima;
    DWORD arriba = ESTILO_ARRIBA[estilo], abajo = ESTILO_ABAJO[estilo];
    caja(d, x, y, x + w, y + h, 0x0a0a0a);
    degrade(d, x + 2, y + 2, x + w - 2, y + h - 2, sobre ? mezcla(arriba, 0xffffff, 31) : arriba, abajo);
    linea(d, x + 2, y + 2, x + w - 2, y + 2, mezcla(arriba, 0xffffff, 115), 1);
    borde(d, x + 1, y + 1, x + w - 2, y + h - 2, sobre ? ROJO_LUZ : ACERO_CLARO);
    texto(d, x + w / 2 + 1, y + h / 2 + 1, t, 0x000000, F_BOLD, 1);
    texto(d, x + w / 2, y + h / 2, t, TEXTO, F_BOLD, 1);
}
/* la Pestana de eda_ui.py: la elegida en acero claro con la línea roja */
static void m_pestana(HDC d, int x, int y, int w, int h, const WCHAR *t, int elegida, int id)
{
    m_registrar(x, y, x + w, y + h, M_PESTANA, id);
    degrade(d, x + 1, y + 1, x + w - 1, y + h, elegida ? 0x3a3e44 : 0x16181b, elegida ? 0x16181b : 0x0b0c0e);
    borde(d, x, y, x + w - 1, y + h - 1, elegida ? ACERO_CLARO : ACERO_OSCURO);
    if (elegida) caja(d, x + 1, y + h - 2, x + w - 1, y + h, ROJO_LUZ);
    texto(d, x + w / 2, y + h / 2, t, elegida ? TEXTO : GRIS, elegida ? F_BOLD : F_NORMAL, 1);
}
static const WCHAR *m_clase(int c) { return c == 2 ? L"Hunter" : L"Warrior"; }

/* el tamaño y lugar de cada cosa (los EDIT se ubican con lo mismo) */
#define ML0 17
#define ML1 249
#define MR0 257
#define MR1 (MSN_ANCHO - 17)
#define MT0 60
#define MLISTA0 150
#define MLISTA1 (MSN_ALTO - 17 - 22 - 8 - 26 - 6 - 26 - 6)
#define MENTRADA_Y (MLISTA1 + 6)
#define MBOTONES_Y (MENTRADA_Y + 26 + 6)
#define MCHAT1 (MSN_ALTO - 17 - 28 - 8)

static void msn_pintar(HDC d)
{
    const int w = MSN_ANCHO, h = MSN_ALTO;
    static const DWORD BANDAS[7] = {0x1b1d20, 0x5c6168, 0xb9bdc3, 0x8d939b, 0x4a4e54, 0x24272b, 0x0d0e10};
    g_nmctl = 0;
    G.fondo(d, TRANSPARENT);
    caja(d, 0, 0, w, h, NEGRO);
    for (int i = 0; i < 7; i++) borde(d, i, i, w - 1 - i, h - 1 - i, BANDAS[i]);
    caja(d, 9, 52, w - 9, h - 9, FONDO);
    const int RX[4] = {12, w - 12, 12, w - 12}, RY[4] = {12, 12, h - 12, h - 12};
    for (int i = 0; i < 4; i++) {
        ovalo(d, RX[i] - 3, RY[i] - 3, RX[i] + 3, RY[i] + 3, 0x9aa0a8, 0x2a2d31);
        ovalo(d, RX[i] - 1, RY[i] - 1, RX[i] + 1, RY[i] + 1, 0xe8eaee, -1);
    }
    /* la placa (la misma de Options) */
    int pw = 230, px0 = (w - pw) / 2, py0 = 8, px1 = (w + pw) / 2, py1 = 40, c = 10;
    POINT forma[8] = {{px0 + c, py0}, {px1 - c, py0}, {px1, py0 + c}, {px1, py1 - c}, {px1 - c, py1}, {px0 + c, py1},
                      {px0, py1 - c}, {px0, py0 + c}};
    poligono(d, forma, 8, 0x0a0b0d, ACERO_CLARO, 2);
    static const DWORD LUZ[5] = {0x3a0606, 0x7a0d0d, ROJO_LUZ, 0x7a0d0d, 0x3a0606};
    for (int i = 0; i < 5; i++) caja(d, px0 + c + 10, py1 + 3 + i, px1 - c - 10, py1 + 4 + i, LUZ[i]);
    texto(d, (px0 + px1) / 2 + 1, (py0 + py1) / 2 + 1, L"M E S S E N G E R", 0x1f6f8f, F_TITULO, 1);
    texto(d, (px0 + px1) / 2, (py0 + py1) / 2, L"M E S S E N G E R", CIAN_BRILLO, F_TITULO, 1);
    int xx = w - 24, yy = 22, k = m_registrar(xx - 9, yy - 9, xx + 10, yy + 10, M_X, 0);
    ovalo(d, xx - 9, yy - 9, xx + 9, yy + 9, 0x1a1c1f, ACERO);
    DWORD cx = k >= 0 && k == g_mencima ? ROJO_LUZ : GRIS;
    linea(d, xx - 4, yy - 4, xx + 5, yy + 5, cx, 2);
    linea(d, xx + 4, yy - 4, xx - 5, yy + 5, cx, 2);

    EnterCriticalSection(&g_msn_cs);
    /* ── izquierda: la ficha ── */
    caja(d, ML0, MT0, ML1, MT0 + 56, ACERO);
    caja(d, ML0 + 1, MT0 + 1, ML1 - 1, MT0 + 55, PANEL);
    texto(d, ML0 + 8, MT0 + 5, L"Character Name", 0x5b8fd6, F_CHICA, 0);
    texto(d, ML0 + 8, MT0 + 19, g_msn_hay_lista ? g_msn_yo_nick : L"…", TEXTO, F_BOLD, 0);
    WCHAR lv[16];
    wsprintfW(lv, g_msn_yo_nivel ? L"%dLV" : L"—", g_msn_yo_nivel);
    texto(d, ML1 - 30, MT0 + 5, L"Lv", 0x5b8fd6, F_CHICA, 0);
    texto(d, ML1 - 46, MT0 + 19, lv, ORO, F_BOLD, 0);
    WCHAR donde[96];
    wsprintfW(donde, L"%s · %s", m_clase(g_msn_yo_clase), g_msn_yo_donde[0] ? g_msn_yo_donde : L"en línea");
    texto(d, ML0 + 8, MT0 + 37, g_msn_hay_lista ? donde : L"pidiendo la lista al server…", CIAN, F_CHICA, 0);
    /* las pestañas y el contador */
    m_pestana(d, ML0, MT0 + 62, 90, 24, L"Friends", g_msn_pestana == 0, 0);
    m_pestana(d, ML0 + 91, MT0 + 62, 90, 24, L"Online", g_msn_pestana == 1, 1);
    int conectados = 0;
    for (int i = 0; i < g_msn_nam; i++) conectados += g_msn_am[i].conectado != 0;
    WCHAR cont[24];
    wsprintfW(cont, L"%d / %d", conectados, g_msn_nam);
    texto(d, ML1 - 4 - 40, MT0 + 67, cont, GRIS, F_CHICA, 0);
    /* la lista (conectados primero) */
    caja(d, ML0, MLISTA0 - 4, ML1, MLISTA1, ACERO);
    caja(d, ML0 + 1, MLISTA0 - 3, ML1 - 1, MLISTA1 - 1, PANEL);
    int y = MLISTA0, mostrados = 0, saltar = g_msn_scroll;
    for (int pasada = 0; pasada < 2; pasada++)
        for (int i = 0; i < g_msn_nam; i++) {
            MSN_AMIGO *a = &g_msn_am[i];
            if ((pasada == 0) != (a->conectado != 0)) continue;
            if (g_msn_pestana == 1 && !a->conectado) continue;
            if (saltar > 0) { saltar--; continue; }
            if (y + 32 > MLISTA1 - 2) continue;
            int sel = !lstrcmpiW(a->cuenta, g_msn_sel);
            DWORD fondo = sel ? 0x3a0b0b : 0x0b0c0e;
            m_registrar(ML0 + 4, y, ML1 - 4, y + 32, M_FILA, i);
            caja(d, ML0 + 4, y, ML1 - 4, y + 32, fondo);
            borde(d, ML0 + 4, y, ML1 - 5, y + 31, sel ? ROJO_LUZ : ACERO_OSCURO);
            ovalo(d, ML0 + 10, y + 7, ML0 + 18, y + 15, a->conectado ? VERDE : 0x3a3d42, 0x000000);
            WCHAR t[40];
            wsprintfW(t, a->nivel ? L"LV %d" : L"LV —", a->nivel);
            texto(d, ML0 + 24, y + 3, t, a->conectado ? TEXTO : GRIS, F_NORMAL, 0);
            texto(d, ML0 + 74, y + 3, a->nick, a->conectado ? TEXTO : GRIS, F_BOLD, 0);
            WCHAR t2[96];
            if (a->conectado) wsprintfW(t2, L"%s · %s", m_clase(a->clase), a->donde);
            else lstrcpyW(t2, L"desconectado");
            texto(d, ML0 + 24, y + 17, t2, a->conectado ? CIAN : 0x55595f, F_CHICA, 0);
            if (a->sin_leer) {
                WCHAR nl[8];
                wsprintfW(nl, L" %d ", a->sin_leer);
                caja(d, ML1 - 30, y + 4, ML1 - 8, y + 18, 0xd21f1f);
                texto(d, ML1 - 19, y + 11, nl, 0xffffff, F_CHICA, 1);
            }
            y += 34;
            mostrados++;
        }
    if (!mostrados && !g_msn_scroll)
        parrafo(d, ML0 + 14, MLISTA0 + 16, ML1 - ML0 - 28,
                !g_msn_hay_lista ? L"Esperando la lista del server…"
                : g_msn_pestana == 0 ? L"Sin amigos todavía.\nEscribe un nick y pulsa ADD." : L"Nadie conectado.",
                GRIS, F_CHICA);
    /* agregar / chat / quitar */
    caja(d, ML0 + 4, MENTRADA_Y, ML1 - 4 - 62, MENTRADA_Y + 26, ACERO);
    caja(d, ML0 + 5, MENTRADA_Y + 1, ML1 - 5 - 62, MENTRADA_Y + 25, 0x000000);
    m_boton(d, ML1 - 4 - 58, MENTRADA_Y + 1, 58, 24, L"ADD", TEAL, M_ADD, 0);
    m_boton(d, ML0 + 4, MBOTONES_Y, 90, 24, L"CHAT", MORADO, M_CHAT, 0);
    m_boton(d, ML1 - 4 - 90, MBOTONES_Y, 90, 24, L"DELETE", GRANATE, M_DEL, 0);
    if (g_msn_aviso[0]) texto(d, ML0 + 4, MSN_ALTO - 17 - 16, g_msn_aviso, GRIS, F_CHICA, 0);

    /* ── derecha: la conversación ── */
    MSN_AMIGO *a = g_msn_sel[0] ? msn_amigo(g_msn_sel) : NULL;
    caja(d, MR0, MT0, MR1, MCHAT1, ACERO);
    caja(d, MR0 + 1, MT0 + 1, MR1 - 1, MCHAT1 - 1, PANEL);
    if (!g_msn_sel[0]) {
        parrafo(d, MR0 + 30, MT0 + 150, MR1 - MR0 - 60, L"Elige un amigo de la lista (clic, o doble clic para "
                L"escribirle).\nLos mensajes también le llegan si está desconectado: los lee al volver.", GRIS, F_CHICA);
    } else {
        texto(d, MR0 + 10, MT0 + 6, a ? a->nick : g_msn_sel, TEXTO, F_BOLD, 0);
        WCHAR info[120];
        if (a && a->conectado) wsprintfW(info, L"● LV %d · %s · %s", a->nivel, m_clase(a->clase), a->donde);
        else lstrcpyW(info, L"○ desconectado: lo leerá al volver");
        texto(d, MR0 + 10, MT0 + 22, info, a && a->conectado ? VERDE : GRIS, F_CHICA, 0);
        caja(d, MR0 + 8, MT0 + 40, MR1 - 8, MT0 + 41, ROJO);
        /* los mensajes, de abajo hacia arriba (la rueda del mouse sube) */
        int abajo = MCHAT1 - 8, arriba = MT0 + 46, saltar2 = g_msn_scroll_chat;
        HGDIOBJ viejo = G.usar(d, F_NORMAL);
        for (int i = g_msn_nh - 1; i >= 0 && abajo > arriba; i--) {
            MSN_MSG *m = &g_msn_h[i];
            int mio = !lstrcmpiW(m->de, g_msn_yo);
            if (!((mio && !lstrcmpiW(m->a, g_msn_sel)) || (!lstrcmpiW(m->de, g_msn_sel) && !lstrcmpiW(m->a, g_msn_yo))))
                continue;
            if (saltar2 > 0) { saltar2--; continue; }
            WCHAR t[220];
            wsprintfW(t, L"%s  [%s]: %s", m->hora, mio ? g_msn_yo_nick : (a ? a->nick : m->de), m->texto);
            RECT r = {MR0 + 10, 0, MR1 - 10, 0};
            DrawTextW(d, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX | DT_CALCRECT);
            int alto = r.bottom - r.top;
            r.left = MR0 + 10; r.right = MR1 - 10; r.bottom = abajo; r.top = abajo - alto;
            if (r.top < arriba) break;
            G.color_texto(d, CR(mio ? TEXTO : 0x8fe08f));
            DrawTextW(d, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX);
            abajo = r.top - 4;
        }
        G.usar(d, viejo);
    }
    LeaveCriticalSection(&g_msn_cs);
    caja(d, MR0, MCHAT1 + 6, MR1 - 44, MCHAT1 + 32, ACERO);
    caja(d, MR0 + 1, MCHAT1 + 7, MR1 - 45, MCHAT1 + 31, 0x000000);
    m_boton(d, MR1 - 38, MCHAT1 + 6, 38, 26, L"↵", TEAL, M_ENVIAR, 0);
}

static void msn_texto_de(HWND e, WCHAR *t, int n)
{
    t[0] = 0;
    if (e) GetWindowTextW(e, t, n);
    while (*t == L' ') memmove(t, t + 1, lstrlenW(t) * sizeof(WCHAR));
    for (int k = lstrlenW(t); k > 0 && t[k - 1] == L' '; k--) t[k - 1] = 0;
}
static void msn_agregar(void)
{
    WCHAR nick[32], cmd[64];
    msn_texto_de(g_msn_nick_e, nick, 24);
    if (!nick[0]) { msn_avisar(L"Escribe un nick y pulsa ADD."); return; }
    wsprintfW(cmd, L"/amigo %s", nick);
    msn_encolar(cmd);
    SetWindowTextW(g_msn_nick_e, L"");
    WCHAR a[80];
    wsprintfW(a, L"Pedido: agregar a %s", nick);
    msn_avisar(a);
}
static void msn_quitar(void)
{
    WCHAR cmd[64], a[80];
    if (!g_msn_sel[0]) { msn_avisar(L"Elige un amigo de la lista."); return; }
    wsprintfW(cmd, L"/quitar %s", g_msn_sel);
    msn_encolar(cmd);
    wsprintfW(a, L"Pedido: quitar a %s", g_msn_sel);
    msn_avisar(a);
}
static void msn_enviar(void)
{
    WCHAR t[160], cmd[176];
    if (!g_msn_sel[0]) { msn_avisar(L"Elige un amigo de la lista."); return; }
    msn_texto_de(g_msn_texto_e, t, 140);
    if (!t[0]) return;
    wsprintfW(cmd, L"/m %s %s", g_msn_sel, t);
    msn_encolar(cmd);
    SetWindowTextW(g_msn_texto_e, L"");
}
static void msn_elegir(int i)
{
    EnterCriticalSection(&g_msn_cs);
    if (i >= 0 && i < g_msn_nam) {
        lstrcpynW(g_msn_sel, g_msn_am[i].cuenta, 24);
        g_msn_am[i].sin_leer = 0;
        g_msn_scroll_chat = 0;
    }
    LeaveCriticalSection(&g_msn_cs);
}

static LRESULT CALLBACK msn_proc(HWND v, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_NCHITTEST: {
        POINT p = {(short)LOWORD(l), (short)HIWORD(l)};
        ScreenToClient(v, &p);
        if (p.y < 52 && !(p.x > MSN_ANCHO - 36 && p.y < 34)) return HTCAPTION;   /* se arrastra por arriba */
        return HTCLIENT;
    }
    case WM_SETCURSOR:                                        /* (lo mismo que Options) */
        if (LOWORD(l) == HTCLIENT || LOWORD(l) == HTCAPTION) {
            POINT p;
            opc_cursor_visible();
            GetCursorPos(&p);
            ScreenToClient(v, &p);
            int k = LOWORD(l) == HTCLIENT ? m_ctl_en(p.x, p.y) : -1;
            SetCursor(LoadCursorW(NULL, (LPCWSTR)((HWND)w != v ? IDC_IBEAM : k >= 0 ? IDC_HAND : IDC_ARROW)));
            return TRUE;
        }
        break;
    case WM_ERASEBKGND: return 1;
    case WM_APP + 7: InvalidateRect(v, NULL, FALSE); return 0;
    case WM_CTLCOLOREDIT: {
        if (!g_msn_pincel) g_msn_pincel = G.solido(RGB(0, 0, 0));
        G.color_texto((HDC)w, CR(TEXTO));
        G.color_fondo((HDC)w, RGB(0, 0, 0));
        return (LRESULT)g_msn_pincel;
    }
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC d = BeginPaint(v, &ps), b = G.dc(d);
        HBITMAP bm = G.mapa(d, MSN_ANCHO, MSN_ALTO);
        HGDIOBJ viejo = G.usar(b, bm);
        msn_pintar(b);
        G.copiar(d, 0, 0, MSN_ANCHO, MSN_ALTO, b, 0, 0, SRCCOPY);
        G.usar(b, viejo);
        G.borrar(bm);
        G.borrar_dc(b);
        EndPaint(v, &ps);
        return 0;
    }
    case WM_MOUSEMOVE: {
        int k = m_ctl_en((short)LOWORD(l), (short)HIWORD(l));
        if (k >= 0 && g_mctl[k].tipo == M_FILA) k = -1;      /* (hover: sólo botones) */
        if (k != g_mencima) {
            g_mencima = k;
            TRACKMOUSEEVENT t = {sizeof(t), TME_LEAVE, v, 0};
            TrackMouseEvent(&t);
            InvalidateRect(v, NULL, FALSE);
        }
        return 0;
    }
    case WM_MOUSELEAVE:
        if (g_mencima >= 0) { g_mencima = -1; InvalidateRect(v, NULL, FALSE); }
        return 0;
    case WM_LBUTTONDOWN: case WM_LBUTTONDBLCLK: {
        int k = m_ctl_en((short)LOWORD(l), (short)HIWORD(l));
        SetFocus(v);
        if (k < 0) return 0;
        MCTL c = g_mctl[k];
        switch (c.tipo) {
        case M_X: DestroyWindow(v); return 0;
        case M_PESTANA: g_msn_pestana = c.id; g_msn_scroll = 0; break;
        case M_FILA:
            msn_elegir(c.id);
            if (m == WM_LBUTTONDBLCLK && g_msn_texto_e) SetFocus(g_msn_texto_e);
            break;
        case M_ADD: msn_agregar(); break;
        case M_CHAT: if (g_msn_sel[0] && g_msn_texto_e) SetFocus(g_msn_texto_e); else msn_avisar(L"Elige un amigo."); break;
        case M_DEL: msn_quitar(); break;
        case M_ENVIAR: msn_enviar(); break;
        }
        InvalidateRect(v, NULL, FALSE);
        return 0;
    }
    case WM_MOUSEWHEEL: {
        POINT p = {(short)LOWORD(l), (short)HIWORD(l)};
        ScreenToClient(v, &p);
        int paso = GET_WHEEL_DELTA_WPARAM(w) > 0 ? 1 : -1;
        if (p.x < ML1) { g_msn_scroll -= paso; if (g_msn_scroll < 0) g_msn_scroll = 0; if (g_msn_scroll > MSN_AMIGOS) g_msn_scroll = MSN_AMIGOS; }
        else { g_msn_scroll_chat += paso; if (g_msn_scroll_chat < 0) g_msn_scroll_chat = 0; if (g_msn_scroll_chat > MSN_HIST) g_msn_scroll_chat = MSN_HIST; }
        InvalidateRect(v, NULL, FALSE);
        return 0;
    }
    case WM_CLOSE: DestroyWindow(v); return 0;
    case WM_DESTROY:
        panel_al_cerrar("Messenger");
        g_msn_ventana = NULL;
        g_msn_nick_e = g_msn_texto_e = NULL;
        g_mencima = -1;
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(v, m, w, l);
}

static DWORD WINAPI msn_hilo(LPVOID nada)
{
    (void)nada;
    HINSTANCE yo = GetModuleHandleW(NULL);
    if (!gdi_listo()) {
        apuntar("  [mazino] messenger: ⚠ no pude cargar gdi32");
        InterlockedExchange(&g_msn_abriendo, 0);
        return 0;
    }
    if (!F_NORMAL) {                                          /* (las mismas letras de Options) */
        F_NORMAL = G.fuente(-12, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_BOLD = G.fuente(-12, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_CHICA = G.fuente(-11, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_SECCION = G.fuente(-13, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        F_TITULO = G.fuente(-16, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Trebuchet MS");
    }
    WNDCLASSW c = {0};
    c.style = CS_DBLCLKS;
    c.lpfnWndProc = msn_proc;
    c.hInstance = yo;
    c.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    c.lpszClassName = L"EDA_Messenger";
    RegisterClassW(&c);
    int x = 80, y = 60;
    RECT j;
    if (g_ventana_juego && GetWindowRect(g_ventana_juego, &j)) {     /* centrada en el juego */
        x = (j.left + j.right - MSN_ANCHO) / 2;
        y = (j.top + j.bottom - MSN_ALTO) / 2;
    }
    /* (como Options: su dueño es EDA, sin «siempre encima») */
    HWND v = CreateWindowExW(WS_EX_TOOLWINDOW, L"EDA_Messenger", L"Messenger", WS_POPUP | WS_CLIPCHILDREN,
                             x, y, MSN_ANCHO, MSN_ALTO, g_ventana_juego, NULL, yo, NULL);
    if (!v) { InterlockedExchange(&g_msn_abriendo, 0); apuntar("  [mazino] messenger: ⚠ no se pudo crear la ventana (%lu)", GetLastError()); return 0; }
    g_msn_nick_e = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
                                   ML0 + 9, MENTRADA_Y + 6, ML1 - 62 - ML0 - 18, 16, v, NULL, yo, NULL);
    g_msn_texto_e = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
                                    MR0 + 6, MCHAT1 + 11, MR1 - 44 - MR0 - 12, 16, v, NULL, yo, NULL);
    if (g_msn_nick_e) { SendMessageW(g_msn_nick_e, WM_SETFONT, (WPARAM)F_NORMAL, 0); SendMessageW(g_msn_nick_e, EM_LIMITTEXT, 22, 0); }
    if (g_msn_texto_e) { SendMessageW(g_msn_texto_e, WM_SETFONT, (WPARAM)F_NORMAL, 0); SendMessageW(g_msn_texto_e, EM_LIMITTEXT, 140, 0); }
    g_msn_ventana = v;
    InterlockedExchange(&g_msn_abriendo, 0);
    InterlockedExchange(&g_panel_abierto, 1);
    cursor_juego_esconder("Messenger");                       /* (un solo cursor: el de Windows) */
    if (g_clip_real) g_clip_real(NULL);
    ShowWindow(v, SW_SHOWNORMAL);
    DWORD hilo_juego = g_ventana_juego ? GetWindowThreadProcessId(g_ventana_juego, NULL) : 0, yo_h = GetCurrentThreadId();
    if (hilo_juego && hilo_juego != yo_h) AttachThreadInput(yo_h, hilo_juego, TRUE);
    SetForegroundWindow(v);
    SetActiveWindow(v);
    SetFocus(v);
    if (hilo_juego && hilo_juego != yo_h) AttachThreadInput(yo_h, hilo_juego, FALSE);
    opc_cursor_visible();                                    /* (la flecha aparece donde estaba el cursor de EDA) */
    apuntar("  [mazino] messenger: ventana abierta por %s", g_msn_por);
    if (g_diagnostico)
        apuntar("  (diag) Messenger abierto: al frente %s · %s",
                GetForegroundWindow() == v ? "MESSENGER" : GetForegroundWindow() == g_ventana_juego ? "EL JUEGO" : "otra ventana",
                g_sin_bordes ? "pantalla completa sin bordes" : "ventana");
    g_msn_por = "?";
    MSG mm;
    while (GetMessageW(&mm, NULL, 0, 0) > 0) {
        /* ★ las teclas de la ventana (también con el cursor en un EDIT, que se las quedaría): F11 = el interruptor,
         *   F10 = Options (cierra el Messenger: un panel a la vez), Esc = cerrar, Enter = ADD o mandar */
        if (mm.message == WM_KEYDOWN || mm.message == WM_SYSKEYDOWN) {
            diag_tecla("Messenger (su ventana)", mm.message, mm.wParam, mm.lParam, 1);
            int repetida = (mm.lParam & (1L << 30)) != 0;
            if (mm.wParam == VK_F11) { if (!repetida) atajo(1, "Messenger al frente"); continue; }
            if (mm.wParam == VK_F10) { if (!repetida) atajo(0, "Messenger al frente"); continue; }
            if (mm.wParam == VK_ESCAPE) { DestroyWindow(v); continue; }
            if (mm.wParam == VK_RETURN && mm.hwnd == g_msn_texto_e) { msn_enviar(); continue; }
            if (mm.wParam == VK_RETURN && mm.hwnd == g_msn_nick_e) { msn_agregar(); continue; }
        }
        if ((mm.message == WM_SYSKEYUP && mm.wParam == VK_F10) || (mm.message == WM_CHAR && mm.wParam == L'\r')) continue;
        TranslateMessage(&mm);
        DispatchMessageW(&mm);
    }
    for (int i = 0; i < 3; i++) g_dik_antes[i] = 1;            /* (F10/F11 sostenidas no cuentan de nuevo) */
    if (g_diagnostico) apuntar("  (diag) Messenger cerrado: al frente %s",
                               GetForegroundWindow() == g_ventana_juego ? "EL JUEGO" : "otra ventana");
    UnregisterClassW(L"EDA_Messenger", yo);
    if (!g_panel_siguiente && g_ventana_juego) SetForegroundWindow(g_ventana_juego);   /* (cambio de panel: el otro toma el frente) */
    return 0;
}

/* F11, el botón Messenger del lobby y el de la barra: abre la ventana, o la cierra si ya estaba (un panel a la vez) */
static void msn_alternar(void)
{
    static DWORD ultimo;
    DWORD ahora = GetTickCount();
    if (ahora - ultimo < 300) { apuntar("  [mazino] messenger: pedido repetido (%s) → ignorado", g_msn_por); return; }
    ultimo = ahora;
    if (g_msn_ventana) { apuntar("  [mazino] messenger: ya estaba abierto → se cierra"); PostMessageW(g_msn_ventana, WM_CLOSE, 0, 0); return; }
    if (g_opc_ventana || g_opc_abriendo) {
        apuntar("  [mazino] messenger: Options está abierta → se cierra Options y después se abre el Messenger");
        panel_despues(2);
        if (g_opc_ventana) PostMessageW(g_opc_ventana, WM_CLOSE, 0, 0);
        return;
    }
    if (g_panel_siguiente == 1) { InterlockedExchange(&g_panel_siguiente, 0); apuntar("  [mazino] messenger: se cancela la Options pedida"); }
    msn_abrir();
}
/* (en el hilo del juego: msn_alternar o panel_siguiente_tick) */
static void msn_abrir(void)
{
    if (InterlockedExchange(&g_msn_abriendo, 1)) { apuntar("  [mazino] messenger: ya se está abriendo (pedido ignorado)"); return; }
    msn_listo();
    msn_encolar(L"/msn abrir");                                /* (la lista llega mientras se abre la ventana) */
    if (!panel_lanzar(msn_hilo)) { InterlockedExchange(&g_msn_abriendo, 0); apuntar("  [mazino] messenger: ⚠ no se pudo crear su hilo (%lu)", GetLastError()); }
}
