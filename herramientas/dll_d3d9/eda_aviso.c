/* eda_aviso.c — ★ EL AVISO DE ARRANQUE: qué dll cargó el juego y a qué server va (19-nov).
 *
 * Una placa chica con el look de Options (eda_ui.py), arriba a la derecha del juego, unos segundos.
 * Sin hilos, ganchos ni temporizadores nuevos:
 *   · se crea en el Present (mi_present, que ya existe), UNA vez por proceso, en el hilo del juego: sus
 *     mensajes los atiende el mismo bucle del juego (PeekMessage);
 *   · se cierra en un Present posterior, cuando pasaron AVISO_MS (GetTickCount, una resta por cuadro);
 *   · no se activa ni toma el foco (WS_EX_NOACTIVATE + SW_SHOWNOACTIVATE) y los clics la atraviesan
 *     (HTTRANSPARENT): el login, el teclado, el mouse y el cursor siguen siendo del juego.
 *   · ventana DEL juego (su dueño es la ventana de EDA, como Options): arriba de EDA, baja con EDA.
 * Si el Present no corre en el hilo de la ventana del juego, no se muestra (queda en el registro y en Options).
 * [version] aviso=0 en eda_d3d9.ini lo apaga. */

#define AVISO_MS 8000
#define AVISO_ANCHO 400
#define AVISO_ALTO 124
static int g_aviso_activo = 1;                       /* [version] aviso */
static HWND g_aviso;
static DWORD g_aviso_desde;
static int g_aviso_hecho;                            /* 1 = ya se mostró (o no se puede): nunca otra vez */
static WCHAR g_aviso_txt[VER_LINEAS][VER_LARGO];
static int g_aviso_ent;
static HFONT g_aviso_f[2];

static void aviso_pintar(HDC d)
{
    const int w = AVISO_ANCHO, h = AVISO_ALTO;
    static const DWORD BANDAS[4] = {0x5c6168, 0xb9bdc3, 0x4a4e54, 0x0d0e10};
    G.fondo(d, TRANSPARENT);
    caja(d, 0, 0, w, h, NEGRO);
    for (int i = 0; i < 4; i++) borde(d, i, i, w - 1 - i, h - 1 - i, BANDAS[i]);
    caja(d, 4, 4, w - 4, h - 4, FONDO);
    /* la luz roja de Options bajo el título; verde/amarilla/roja según el entorno a la izquierda */
    DWORD luz = g_aviso_ent == ENT_PROD ? VERDE : g_aviso_ent == ENT_TEST ? ORO : g_aviso_ent == ENT_LOCAL ? CIAN : ROJO_LUZ;
    caja(d, 4, 4, 9, h - 4, luz);
    texto(d, 18, 10, g_aviso_txt[0], CIAN_BRILLO, g_aviso_f[1], 0);
    static const DWORD LUZ[3] = {0x7a0d0d, ROJO_LUZ, 0x7a0d0d};
    for (int i = 0; i < 3; i++) caja(d, 18, 31 + i, w - 14, 32 + i, LUZ[i]);
    for (int i = 1; i < VER_LINEAS; i++) {
        DWORD c = TEXTO;
        if (i == 2 && EDA_SUCIO) c = ORO;                                   /* LOCAL: no es una publicada */
        if (i == 4) c = g_aviso_txt[4][8] == L'D' ? VERDE : ROJO_LUZ;      /* «Estado: DLL cargada…» */
        texto(d, 18, 40 + (i - 1) * 19, g_aviso_txt[i], c, g_aviso_f[0], 0);
    }
}

static LRESULT CALLBACK aviso_proc(HWND v, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_NCHITTEST: return HTTRANSPARENT;          /* los clics son del juego */
    case WM_MOUSEACTIVATE: return MA_NOACTIVATE;
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC d = BeginPaint(v, &ps), b = G.dc(d);
        HBITMAP bm = G.mapa(d, AVISO_ANCHO, AVISO_ALTO);
        HGDIOBJ viejo = G.usar(b, bm);
        aviso_pintar(b);
        G.copiar(d, 0, 0, AVISO_ANCHO, AVISO_ALTO, b, 0, 0, SRCCOPY);
        G.usar(b, viejo);
        G.borrar(bm);
        G.borrar_dc(b);
        EndPaint(v, &ps);
        return 0;
    }
    case WM_DESTROY:
        if (g_aviso == v) g_aviso = NULL;
        return 0;
    }
    return DefWindowProcW(v, m, w, l);
}

/* el estado que se muestra: lo que pueda haber salido mal al cargar (NULL = todo bien) */
static const char *aviso_estado(void);

/* ★ desde mi_present, en cada cuadro: crea el aviso la primera vez que se puede y lo cierra a los AVISO_MS */
static void aviso_cuadro(HWND w_present)
{
    if (g_aviso) {
        if (GetTickCount() - g_aviso_desde >= AVISO_MS) {
            DestroyWindow(g_aviso);
            g_aviso = NULL;
            apuntar("  [version] aviso de arranque: cerrado");
        }
        return;
    }
    if (g_aviso_hecho || !g_aviso_activo) return;
    HWND juego = g_ventana_juego ? g_ventana_juego : w_present;
    if (!juego) return;                              /* (todavía no se sabe cuál es la ventana del juego) */
    g_aviso_hecho = 1;                               /* ★ un solo intento: nunca dos avisos */
    if (GetWindowThreadProcessId(juego, NULL) != GetCurrentThreadId()) {
        apuntar("  [version] aviso de arranque: no se muestra (el Present corre en otro hilo); la versión está en Options");
        return;
    }
    if (!gdi_listo()) { apuntar("  [version] aviso de arranque: ⚠ no pude cargar gdi32"); return; }
    char lin[VER_LINEAS][VER_LARGO];
    g_aviso_ent = ver_lineas(g_server, aviso_estado(), lin);
    for (int i = 0; i < VER_LINEAS; i++)
        if (!MultiByteToWideChar(CP_UTF8, 0, lin[i], -1, g_aviso_txt[i], VER_LARGO)) g_aviso_txt[i][0] = 0;
    if (!g_aviso_f[0]) {
        g_aviso_f[0] = G.fuente(-12, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Tahoma");
        g_aviso_f[1] = G.fuente(-15, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Trebuchet MS");
    }
    HINSTANCE yo = GetModuleHandleW(NULL);
    WNDCLASSW c = {0};
    c.lpfnWndProc = aviso_proc;
    c.hInstance = yo;
    c.lpszClassName = L"EDA_Aviso";
    RegisterClassW(&c);
    RECT r;
    POINT p = {0, 0};
    int x = 40, y = 40;
    if (GetClientRect(juego, &r) && ClientToScreen(juego, &p)) {
        x = p.x + r.right - AVISO_ANCHO - 12;
        y = p.y + 12;
    }
    HWND v = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, L"EDA_Aviso", L"EDA", WS_POPUP,
                             x, y, AVISO_ANCHO, AVISO_ALTO, juego, NULL, yo, NULL);
    if (!v) { apuntar("  [version] aviso de arranque: ⚠ no se pudo crear (%lu)", GetLastError()); return; }
    g_aviso = v;
    g_aviso_desde = GetTickCount();
    ShowWindow(v, SW_SHOWNOACTIVATE);
    apuntar("  [version] aviso de arranque: mostrado %d s · %s · %s", AVISO_MS / 1000, lin[1], lin[3]);
}
