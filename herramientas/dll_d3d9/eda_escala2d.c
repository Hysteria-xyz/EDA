/* eda_escala2d.c — ★ (Punto 5, 19-nov) EXPERIMENTAL: la interfaz de 2009 (800×600) escalada y centrada en una
 *   pantalla 16:9, con el 3D del Stage a resolución nativa. Se compila con eda_d3d9.c (#include).
 *
 *   APAGADO POR DEFECTO. Se prende con  [pantalla] escala2d=1  y  resolucion=1920x1080  en eda_d3d9.ini (sin
 *   resolución distinta de 800×600 no hace nada). Con escala2d=0, la dll hace exactamente lo de siempre.
 *
 *   Lo medido (punto5-16x9.md, 18-nov): el juego acepta cualquier backbuffer; su interfaz está diseñada en
 *   800×600 y la dibuja SIN escalar, pegada arriba a la izquierda; el 2D va por la proyección ortográfica que arma
 *   0x77B4F0 (Scaling(1,−1,1) · medio píxel · OrthoOffCenterLH(0,W,H,0)) y el mouse es la posición de Windows del
 *   WM_MOUSEMOVE, tal cual. La cámara del personaje (0x5BB9D0, selección / inventario) usa la pantalla entera y un
 *   FOV de 16:9: por eso el personaje sale ×1,8 y corrido.
 *
 *   Qué hace (todo en el dispositivo, con 1 regla: R = 800×600 × s centrado, s = min(W/800, H/600); 1920×1080 →
 *   s = 1,8 y R = 1440×1080 en x 240):
 *    · PROYECCIÓN ortográfica de pantalla entera → la misma, compuesta con «800×600 → R» (escala uniforme: nada se
 *      estira). Es la que usa toda la interfaz, el texto y el cursor dibujado del juego.
 *    · PERSPECTIVA fuera del Stage (la cámara del personaje): su viewport de pantalla entera → R y su FOV vertical
 *      con la misma regla del juego pero para 4:3 (como a 800×600). En el Stage la perspectiva NO se toca: 3D nativo.
 *    · VIEWPORT / SCISSOR de una parte de la interfaz (listas, recortes) → la misma parte dentro de R.
 *    · Dibujos XYZRHW (ya en píxeles) con coordenadas de interfaz (≤ 800×600) → dentro de R; los de pantalla entera
 *      (efectos) no se tocan.
 *    · MOUSE: la posición de Windows de cada mensaje → la de la interfaz (en mi_peek, el gancho de mensajes que ya
 *      estaba), y al revés cuando el juego mueve el cursor (SetPhysicalCursorPos, ya enganchado).
 *    · Get*: el juego lee lo que ÉL puso (no lo cambiado).
 *   Ganchos nuevos en la tabla del dispositivo (los únicos): SetTransform, GetTransform, SetViewport, GetViewport,
 *   SetScissorRect, GetScissorRect, DrawPrimitiveUP, DrawIndexedPrimitiveUP y SetFVF. Sin hilos ni temporizadores. */

static int g_e2d;                        /* [pantalla] escala2d (0 = nada de esto) */
static int g_e2d_ambiente = 1;           /* ★ (24-nov) [pantalla] ambiente: las franjas con la imagen desenfocada (eda_graficos.c) */
static int g_e2d_stage = 1;              /* [pantalla] escala2d_stage: el HUD del Stage también (1) o como hoy (0) */
static int g_e2d_activa;                 /* escala2d y un backbuffer distinto de 800×600 */
static int g_e2d_w = 800, g_e2d_h = 600; /* el backbuffer */
static float g_e2d_s = 1, g_e2d_rx, g_e2d_ry;
/* ★ (24-nov) EL LIENZO de la interfaz: 800 (×600), salvo en el LOBBY con el channellobby.xml panorámico (eda_traduccion.c
 *   · tr_abrir_ancho, g_e2d_lobby_ancho): ahí 1066 o 960 de ancho, desde el borde izquierdo. Todo lo de abajo (proyección,
 *   viewports de una parte, scissor, dibujos XYZRHW, mouse, cursor) ya usa s / rx / ry: cambia sólo cómo se calculan. */
static int g_e2d_lienzo = 800;
static volatile LONG g_e2d_lobby_ancho, g_e2d_sel_ancho, g_e2d_tie_ancho;   /* el ancho del XML servido (0 = el original) */
static long c_e2d_lienzo;                /* veces que cambió el lienzo (entrar / salir del lobby panorámico) */
static volatile LONG g_e2d_rt_fuera;     /* (diag) 1 = el render target 0 no es la pantalla (otro tamaño) */
static void e2d_geometria(void)
{
    float L = (float)g_e2d_lienzo;
    float s = (float)g_e2d_w / L < (float)g_e2d_h / 600 ? (float)g_e2d_w / L : (float)g_e2d_h / 600;
    g_e2d_s = s;
    g_e2d_rx = (g_e2d_w - L * s) / 2;
    g_e2d_ry = (g_e2d_h - 600 * s) / 2;
}
/* el lienzo de esta escena: el lobby (0x899670), Select Character (0x899740) o Shop/Inventory/Refinery/Skill (0x899F10) con su XML panorámico servido → su ancho;
 * cualquier otra → 800 */
static int e2d_lienzo_de(DWORD vt, long lobby_ancho, long sel_ancho, long tie_ancho)
{
    long a = vt == 0x00899670u ? lobby_ancho : vt == 0x00899740u ? sel_ancho : vt == 0x00899F10u ? tie_ancho : 0;
    return a > 800 ? (int)a : 800;
}
/* la COLUMNA de botones del lobby panorámico (la misma regla que herramientas/lobby_ancho.py · columna): el control n
 *   (1 Shop · 2 Inventory · 3 Clan · 4 Messenger · 5 Options · 6 Select Character · 7 Exit) en x L−91, y 12+(n−1)·80,
 *   82×64. → 1 si (x, y) de la interfaz cae en él. */
static int e2d_pan_en_boton(int L, int n, int x, int y)
{
    int x0 = L - 91, y0 = 12 + (n - 1) * 80;
    return L > 800 && x >= x0 && x < x0 + 82 && y >= y0 + 6 && y < y0 + 64;
}
static volatile LONG g_e2d_propio;      /* (lo que dibuja la dll, el contador: no se toca) */
/* ★ (Punto 6b, 20-nov 01:20) EL DESTINO DEL DIBUJO — sólo se MIRA, no cambia la escala. Probado y revertido: dejar sin
 *   escala lo que se dibuja en una textura (render target) rompió la pantalla de Capítulos/Misiones (Create Stage): el
 *   juego arma esa pantalla en un render target de 1024×1024 (0x0128E217, dibuja desde 0x0077D462) con la proyección de
 *   la PANTALLA (1920×1080) y después lo copia a la pantalla entera; sin la escala, el contenido quedaba al tamaño de
 *   800×600 dentro de la textura → la interfaz a la izquierda y el resto negro. Con la escala igual que en la pantalla
 *   (como d617fb02) se ve completa y el mouse coincide. La distorsión de la espada NO se reprodujo: el diag de
 *   SetRenderTarget queda para medirla en TEST. */
#define E2D_PASA (g_e2d_propio)
static int g_e2d_stage_ahora;            /* la escena del cuadro: ¿el Stage? (se mira en el Present) */
static float g_e2d_proj[16];             /* la proyección que puso EL JUEGO */
static int g_e2d_es_orto;                /* (Punto 6) la última proyección del juego es ortográfica (la interfaz) */
static int g_e2d_proj_hay, g_e2d_tipo;   /* 0 ? · 1 orto de pantalla · 2 orto de una parte · 3 perspectiva */
static DWORD g_e2d_vp[6];                /* el viewport que puso el juego (X, Y, W, H, MinZ, MaxZ) */
static int g_e2d_vp_hay;
static RECT g_e2d_sc;
static int g_e2d_sc_hay;
static DWORD g_e2d_fvf;
static float g_e2d_otra_m0, g_e2d_otra_m5, g_e2d_otra_m12;   /* (diag HUD) la última orto que NO se escaló */
static DWORD g_e2d_otra_vuelta;
static long c_e2d_orto, c_e2d_orto_otra, c_e2d_persp, c_e2d_persp_stage, c_e2d_vp, c_e2d_sc, c_e2d_rhw_ui,
            c_e2d_rhw_pant, c_e2d_mouse, c_e2d_setcur, c_e2d_get;
static float g_e2d_k;                    /* la regla del FOV del juego: FovY = FovX × k × H/W (medida) */
static int g_e2d_medido;                 /* 0 = leer el backbuffer real en el próximo Present */
static int g_e2d_mira_antes = -1;        /* (diagnóstico) el último valor visto de «apuntar» del juego */
static long c_e2d_mirada;                /* SetPhysicalCursorPos del Stage (apuntar): en pantalla, sin convertir */
static long c_e2d_mirada_mouse;          /* mensajes del mouse entregados como (400,300) + el movimiento real (apuntando) */
static int g_e2d_cur_x = -1, g_e2d_cur_y = -1;   /* (diagnóstico) el último SetPhysicalCursorPos del juego, en el cliente */
static long g_e2d_mov_real, g_e2d_mov_ui;     /* (diagnóstico) |movimiento| apuntando: el real vs el que daría la escala */
static long g_e2d_di_x, g_e2d_di_y;           /* (diagnóstico) |lX|, |lY| del mouse de DirectInput en el Stage */
static long c_e2d_di;
static long c_e2d_prop;                  /* preguntas de la interfaz por el tamaño de pantalla contestadas 800×600 */
static int e2d_apuntando(void);
static int e2d_dword(DWORD dir);
static int entrada_ok(void);             /* (eda_d3d9.c) 0 = un panel abierto, su Esc todavía apretada u otra ventana al frente */
static volatile DWORD g_e2d_traza_hasta; /* (diagnóstico) traza por tiempo (abrir/cerrar un panel en el Stage): hasta este tick */
static DWORD g_e2d_foto, g_e2d_foto2;    /* (diag) capturas del backbuffer en REWARD y AWARD */
/* (diag fase) fotos de la memoria del juego: jugando ×2, resultados, award → qué cambia sólo en resultados */
#define E2D_FASE_N 3
static const DWORD E2D_FASE_DESDE[E2D_FASE_N] = {0x0090C000u, 0x0094E000u, 0};       /* (0 = el objeto de la escena) */
static const DWORD E2D_FASE_TAM[E2D_FASE_N] = {0x41000u, 0x33000u, 0x4000u};
static BYTE *g_e2d_fase[4][E2D_FASE_N];
static DWORD g_e2d_fase_obj;
static DWORD g_e2d_fase_t[4];
static void e2d_fase_foto(int k)
{
    BYTE *esc = leer_ptr((void *)0x934554);
    for (int r = 0; r < E2D_FASE_N; r++) {
        const BYTE *desde = r < 2 ? (const BYTE *)(ULONG_PTR)E2D_FASE_DESDE[r] : esc;
        if (r == 2 && k == 0) g_e2d_fase_obj = (DWORD)(ULONG_PTR)esc;
        if (!desde || !legible(desde, E2D_FASE_TAM[r]) || (r == 2 && (DWORD)(ULONG_PTR)esc != g_e2d_fase_obj)) continue;
        if (!g_e2d_fase[k][r]) g_e2d_fase[k][r] = (BYTE *)HeapAlloc(GetProcessHeap(), 0, E2D_FASE_TAM[r]);
        if (g_e2d_fase[k][r]) memcpy(g_e2d_fase[k][r], desde, E2D_FASE_TAM[r]);
    }
    apuntar("  (diag fase) foto %d de la memoria (%s)", k, k < 2 ? "jugando" : k == 2 ? "resultados" : "award");
}
static void e2d_fase_comparar(void)
{
    int n = 0;
    for (int r = 0; r < E2D_FASE_N && n < 120; r++) {
        if (!g_e2d_fase[0][r] || !g_e2d_fase[1][r] || !g_e2d_fase[2][r] || !g_e2d_fase[3][r]) continue;
        for (DWORD i = 0; i + 4 <= E2D_FASE_TAM[r] && n < 120; i += 4) {
            DWORD a = *(DWORD *)(g_e2d_fase[0][r] + i), b = *(DWORD *)(g_e2d_fase[1][r] + i),
                  c = *(DWORD *)(g_e2d_fase[2][r] + i), d = *(DWORD *)(g_e2d_fase[3][r] + i);
            if (a != b || c == a || c > 64 || a > 64 || d > 64) continue;   /* (fijo jugando, otro chico en resultados) */
            n++;
            if (r < 2) apuntar("  (diag fase) [0x%08lX]: jugando %lu → resultados %lu → award %lu", E2D_FASE_DESDE[r] + i, a, c, d);
            else apuntar("  (diag fase) escena+0x%04lX: jugando %lu → resultados %lu → award %lu", i, a, c, d);
        }
    }
    apuntar("  (diag fase) %d candidatos (sólo valores 0..64, fijos jugando)", n);
}
static int g_e2d_resultados;              /* ★ el mouse NO es la cámara: resultados o el juego sin «apuntar» (ejes de DirectInput fuera) */
/* ★★ (19-nov) LA FASE DEL STAGE. Medido con fotos de la memoria (15:31–15:32, 1920; jugando ×2, REWARD, AWARD): en el
 *   objeto de la escena del Stage (vtable 0x899C20), +0x248 = 4 jugando → 7 REWARD CHOICE → 8 AWARD RESULTS (también
 *   +0x230 0→1 y +0x2B0 0→8). «Apuntar» ([0x917884]) NO alcanza: en la prueba del dueño (14:56:23, 1920) volvió a 1
 *   en plena REWARD CHOICE y el juego recentraba el cursor mientras elegía cartas. Con la fase: ≥ 5 = resultados. */
static int g_e2d_fase_v = -1, g_e2d_res_fase;
/* ★ (20-nov) EL CIERRE AL CAMBIAR LA RESOLUCIÓN DESPUÉS DE UN STAGE — medido 01:24:45 y 01:32:19 (eda_d3d9.anterior.log,
 *   con 4065e923 y también con d617fb02): tras un Stage con habilidades, el cambio en vivo desde el lobby / Shop llama a
 *   RestartRender → Reset → 0x8876086C (D3DERR_INVALIDCALL: algo del Stage dejó vivo un recurso del pool DEFAULT; la
 *   sonda lo reproduce igual SIN nuestra dll) → el motor rehace el dispositivo → el primer dibujo con lo viejo se cae
 *   en d3d9+0x1451D9 (lee 0x8). Sin Stage previo, el cambio en vivo anda (medido 19-nov). Hasta encontrar quién deja
 *   el recurso vivo: después de entrar a un Stage, la resolución (y el antialias) NO se cambian en vivo: quedan para el
 *   reinicio, como antes del Punto 5. [pantalla] en_vivo_tras_stage=1 vuelve a intentarlo en vivo (bajo tu riesgo). */
static int g_e2d_stages;                    /* veces que se ENTRÓ a un Stage (fase -1 → ≥ 0) en esta sesión */
static void e2d_fase_nueva(int f)
{
    if (f >= 0 && g_e2d_fase_v < 0) g_e2d_stages++;
    g_e2d_fase_v = f;
}
static int e2d_vivo_bloqueado(int permitir_tras_stage) { return g_e2d_stages > 0 && !permitir_tras_stage; }
/* ★ (20-nov, 2) EN VIVO DESPUÉS DE UN STAGE, CON LA PROTECCIÓN DE RESPALDO. Con gr_reset_desligar (lo puesto se saca
 *   antes del Reset) el cambio en vivo tras un Stage se puede intentar con [pantalla] en_vivo_tras_stage=1 (por defecto 0: la
 *   protección validada el 20-nov 17:37–18:06, hasta confirmar el intento en el juego).
 *   Si aun así el Reset fallara, el motor rehace el dispositivo y se cae (no se puede arreglar desde la dll: pone
 *   streams e índices desde ~200 lugares, sin caché). Para que eso pase UNA sola vez: justo antes del intento se anota
 *   [pantalla] vivo_tras_stage_intento=1 y se borra al terminar (bien o vuelto atrás). Si al arrancar sigue en 1, la
 *   sesión anterior se cayó en el intento → en_vivo_tras_stage=0 (la protección: al reiniciar) de ahí en adelante. */
static int e2d_tras_stage_al_arrancar(int permitido, int intento_pendiente) { return intento_pendiente ? 0 : permitido; }
static int e2d_fase_leer(void)
{
    BYTE *esc = leer_ptr((void *)0x934554);
    if (!esc || (DWORD)(ULONG_PTR)leer_ptr(esc) != 0x00899C20u || !legible(esc + 0x248, 4)) return -1;
    return *(int *)(esc + 0x248);
}
static int e2d_trazando(void) { return g_e2d_traza_hasta && (LONG)(g_e2d_traza_hasta - GetTickCount()) > 0; }
static void e2d_trazar(DWORD ms) { g_e2d_traza_hasta = GetTickCount() + ms; if (!g_e2d_traza_hasta) g_e2d_traza_hasta = 1; }

typedef long (WINAPI *E2D_ST)(void *, DWORD, const float *);
typedef long (WINAPI *E2D_GT)(void *, DWORD, float *);
typedef long (WINAPI *E2D_VP)(void *, const DWORD *);
typedef long (WINAPI *E2D_GVP)(void *, DWORD *);
typedef long (WINAPI *E2D_SC)(void *, const RECT *);
typedef long (WINAPI *E2D_GSC)(void *, RECT *);
typedef long (WINAPI *E2D_DPUP)(void *, DWORD, UINT, const void *, UINT);
typedef long (WINAPI *E2D_DIPUP)(void *, DWORD, UINT, UINT, UINT, const void *, DWORD, const void *, UINT);
typedef long (WINAPI *E2D_FVF)(void *, DWORD);
static E2D_ST g_e2d_st_real;
static E2D_GT g_e2d_gt_real;
static E2D_VP g_e2d_vp_real;
static E2D_GVP g_e2d_gvp_real;
static E2D_SC g_e2d_sc_real;
static E2D_GSC g_e2d_gsc_real;
static E2D_DPUP g_e2d_dpup_real;
static E2D_DIPUP g_e2d_dipup_real;
static E2D_FVF g_e2d_fvf_real;
enum { E2D_SETTRANSFORM = 44, E2D_GETTRANSFORM = 45, E2D_SETVIEWPORT = 47, E2D_GETVIEWPORT = 48, E2D_SETSCISSOR = 75,
       E2D_GETSCISSOR = 76, E2D_I_DPUP = 83, E2D_I_DIPUP = 84, E2D_SETFVF = 89, E2D_SETRT = 37 };

static int e2d_activa(void) { return g_e2d_activa; }

/* el tamaño del backbuffer → s y R (y si la escala está activa) */
static void e2d_tamano(int w, int h, const char *por)
{
    if (w < 320 || h < 200 || w > 8192 || h > 8192) return;
    int activa = g_e2d && (w != 800 || h != 600);
    if (w == g_e2d_w && h == g_e2d_h && activa == g_e2d_activa) return;
    g_e2d_w = w;
    g_e2d_h = h;
    e2d_geometria();
    float s = g_e2d_s;
    g_e2d_activa = activa;
    if (g_e2d)
        apuntar("  (escala2d) %s: backbuffer %d×%d → interfaz %d×600 ×%.3f en x %.0f · y %.0f (%.0f×%.0f) · %s", por, w, h,
                g_e2d_lienzo, s, g_e2d_rx, g_e2d_ry, g_e2d_lienzo * s, 600 * s, activa ? "ACTIVA" : "nada que hacer (800×600)");
}

/* una parte de la interfaz (en sus coordenadas de 800×600) → la misma parte dentro de R, en píxeles */
static void e2d_mapear(long *x, long *y, long *w, long *h)
{
    float s = g_e2d_s;
    *x = (long)(g_e2d_rx + *x * s + 0.5f);
    *y = (long)(g_e2d_ry + *y * s + 0.5f);
    *w = (long)(*w * s + 0.5f);
    *h = (long)(*h * s + 0.5f);
}
/* ★ (19-nov noche) LOS TAMAÑOS VIEJOS DESPUÉS DE UN CAMBIO EN VIVO. Medido 19:04 (1280 → 1920 en el lobby): la cámara
 *   de la escena quedó con el rectángulo de cuando se creó; el juego (0x426FC5) y el motor (0x65FF29) siguen poniendo el
 *   viewport (0,0) 1280×720 en un backbuffer de 1920×1080 → la interfaz y la escena, en el rincón de arriba a la izquierda.
 *   Un viewport (0,0)-(ancho, alto) con un tamaño que FUE el backbuffer en esta sesión (y ya no lo es) es «la pantalla
 *   entera» de antes: se pone la de ahora. Lo mismo para los dibujos XYZRHW de pantalla entera (el «light add»). Sólo
 *   con tamaños que dejaron de ser el backbuffer por un cambio en vivo (pan_vivo); sin cambios en vivo, nada. */
static int g_e2d_viejos[6][2], g_e2d_viejos_n;
static long c_e2d_vp_viejo, c_e2d_rhw_viejo;
static void e2d_viejo_agregar(int w, int h)
{
    if (w < 320 || h < 200) return;
    for (int i = 0; i < g_e2d_viejos_n; i++)
        if (g_e2d_viejos[i][0] == w && g_e2d_viejos[i][1] == h) return;
    if (g_e2d_viejos_n < 6) { g_e2d_viejos[g_e2d_viejos_n][0] = w; g_e2d_viejos[g_e2d_viejos_n][1] = h; g_e2d_viejos_n++; }
}
static int e2d_es_viejo(long w, long h)
{
    if (w == g_e2d_w && h == g_e2d_h) return 0;
    for (int i = 0; i < g_e2d_viejos_n; i++)
        if (g_e2d_viejos[i][0] == w && g_e2d_viejos[i][1] == h) return 1;
    return 0;
}
static int e2d_vp_entero(const DWORD *v) { return v[0] == 0 && v[1] == 0 && (int)v[2] == g_e2d_w && (int)v[3] == g_e2d_h; }

/* el viewport que de verdad va al dispositivo, según lo que puso el juego y la proyección vigente */
static void e2d_vp_efectivo(DWORD *sal)
{
    memcpy(sal, g_e2d_vp, sizeof(g_e2d_vp));
    if (!g_e2d_activa || !g_e2d_vp_hay) return;
    int perspectiva_ui = g_e2d_tipo == 3 && !g_e2d_stage_ahora;
    int parte_ui = g_e2d_tipo == 2 && !e2d_vp_entero(g_e2d_vp) && (!g_e2d_stage_ahora || g_e2d_stage);
    if (!perspectiva_ui && !parte_ui) return;
    long x = (long)g_e2d_vp[0], y = (long)g_e2d_vp[1], w = (long)g_e2d_vp[2], h = (long)g_e2d_vp[3];
    if (e2d_vp_entero(g_e2d_vp)) { x = 0; y = 0; w = 800; h = 600; }   /* (pantalla entera = la interfaz entera) */
    e2d_mapear(&x, &y, &w, &h);
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x + w > g_e2d_w) w = g_e2d_w - x;
    if (y + h > g_e2d_h) h = g_e2d_h - y;
    if (w < 1 || h < 1) return;
    sal[0] = (DWORD)x; sal[1] = (DWORD)y; sal[2] = (DWORD)w; sal[3] = (DWORD)h;
}
static void e2d_aplicar_vp(void *dev)
{
    if (!g_e2d_vp_hay) return;
    DWORD v[6];
    e2d_vp_efectivo(v);
    if (memcmp(v, g_e2d_vp, sizeof(v))) InterlockedIncrement(&c_e2d_vp);
    g_e2d_vp_real(dev, v);
}

static long WINAPI e2d_settransform(void *dev, DWORD tipo, const float *m)
{
    if (tipo == 2 /* D3DTS_VIEW */ && m && g_e2d_activa && g_e2d_stage_ahora && e2d_trazando()) {
        static float mira_antes = 1000, giro_antes = 1000;   /* (diagnóstico) a dónde mira la cámara: la 3ª columna */
        static long lineas;
        float mira = asinf(fmaxf(-1, fminf(1, m[6]))) * 57.29578f, giro = atan2f(m[2], m[10]) * 57.29578f;
        if ((fabsf(mira - mira_antes) > 3 || fabsf(giro - giro_antes) > 3) && lineas++ < 600) {
            apuntar("  (escala2d) traza: CÁMARA inclinación %.0f° giro %.0f° (antes %.0f° / %.0f°) · apuntando %d · [0x917884] %d",
                    mira, giro, mira_antes, giro_antes, e2d_apuntando(), e2d_dword(0x917884));
            mira_antes = mira;
            giro_antes = giro;
        }
    }
    if (tipo == 3 && m && !g_e2d_propio)                     /* ★ (Punto 6) ¿interfaz (ortográfica)? también a 800×600 */
        g_e2d_es_orto = fabsf(m[11]) < 1e-5f && fabsf(m[15] - 1) < 1e-4f;
    if (!g_e2d_activa || tipo != 3 /* D3DTS_PROJECTION */ || !m || E2D_PASA) return g_e2d_st_real(dev, tipo, m);
    memcpy(g_e2d_proj, m, sizeof(g_e2d_proj));
    g_e2d_proj_hay = 1;
    float p[16];
    memcpy(p, m, sizeof(p));
    int orto = fabsf(m[11]) < 1e-5f && fabsf(m[15] - 1) < 1e-4f;
    int persp = fabsf(m[11] - 1) < 1e-3f && fabsf(m[15]) < 1e-4f && m[0] > 0 && m[5] > 0;
    if (orto) {
        int entera = fabsf(m[0] * g_e2d_w / 2 - 1) < 0.02f && fabsf(-m[5] * g_e2d_h / 2 - 1) < 0.02f;
        if (entera) {
            g_e2d_tipo = 1;
            if (!g_e2d_stage_ahora || g_e2d_stage) {
                /* x_ndc = x·m11 + m41 con m11 = 2/W: la interfaz (0..800) → R, el medio píxel queda igual */
                p[0] = m[0] * g_e2d_s;
                p[5] = m[5] * g_e2d_s;
                p[12] = m[12] + 2 * g_e2d_rx / g_e2d_w;
                p[13] = m[13] - 2 * g_e2d_ry / g_e2d_h;
                InterlockedIncrement(&c_e2d_orto);
            }
        } else {
            g_e2d_tipo = 2;
            InterlockedIncrement(&c_e2d_orto_otra);
            g_e2d_otra_m0 = m[0]; g_e2d_otra_m5 = m[5]; g_e2d_otra_m12 = m[12];   /* (diag HUD) */
            g_e2d_otra_vuelta = (DWORD)(ULONG_PTR)__builtin_return_address(0);
        }
    } else if (persp) {
        g_e2d_tipo = 3;
        if (!g_e2d_stage_ahora) {
            /* el FOV vertical que el juego habría puesto a 800×600 (su regla: FovY = FovX · k · H/W, k medido) */
            float fx = 2 * atanf(1 / m[0]), fy = 2 * atanf(1 / m[5]);
            float k = fy * g_e2d_w / (fx * g_e2d_h);
            if (k > 0.5f && k < 2.0f) {
                g_e2d_k = k;
                p[5] = 1 / tanf(fx * k * 0.75f / 2);
            }
            InterlockedIncrement(&c_e2d_persp);
        } else InterlockedIncrement(&c_e2d_persp_stage);
    } else g_e2d_tipo = 0;
    long hr = g_e2d_st_real(dev, tipo, p);
    e2d_aplicar_vp(dev);                                     /* (el viewport depende de la proyección vigente) */
    return hr;
}
static long WINAPI e2d_gettransform(void *dev, DWORD tipo, float *m)
{
    if (g_e2d_activa && tipo == 3 && m && g_e2d_proj_hay) {
        memcpy(m, g_e2d_proj, sizeof(g_e2d_proj));
        InterlockedIncrement(&c_e2d_get);
        return 0;
    }
    return g_e2d_gt_real(dev, tipo, m);
}
static volatile LONG g_e2d_vp_diag;                      /* (diag) viewports que pone el juego tras un cambio en vivo */
static long WINAPI e2d_setviewport(void *dev, const DWORD *v)
{
    if (g_e2d_vp_diag > 0 && v && !E2D_PASA) {
        static DWORD vistos[24][5];
        static int n;
        if (g_e2d_vp_diag == 1000) { n = 0; g_e2d_vp_diag = 999; }
        int ya = 0;
        for (int i = 0; i < n && !ya; i++)
            ya = vistos[i][0] == v[0] && vistos[i][1] == v[1] && vistos[i][2] == v[2] && vistos[i][3] == v[3] && vistos[i][4] == (DWORD)g_e2d_tipo;
        if (!ya && n < 24) {
            memcpy(vistos[n], v, 16);
            vistos[n][4] = (DWORD)g_e2d_tipo;
            n++;
            apuntar("  (diag vivo) viewport del juego (%lu,%lu) %lu×%lu · proyección %d · backbuffer %d×%d · vuelve a 0x%08lX",
                    v[0], v[1], v[2], v[3], g_e2d_tipo, g_e2d_w, g_e2d_h, (unsigned long)(ULONG_PTR)__builtin_return_address(0));
        }
        InterlockedDecrement(&g_e2d_vp_diag);
    }
    DWORD nuevo[6];
    if (v && !E2D_PASA && v[0] == 0 && v[1] == 0 && e2d_es_viejo((long)v[2], (long)v[3])) {
        memcpy(nuevo, v, sizeof(nuevo));
        nuevo[2] = (DWORD)g_e2d_w;                       /* (la pantalla entera de antes → la de ahora) */
        nuevo[3] = (DWORD)g_e2d_h;
        v = nuevo;
        InterlockedIncrement(&c_e2d_vp_viejo);
    }
    if (!g_e2d_activa || !v || E2D_PASA) return g_e2d_vp_real(dev, v);
    memcpy(g_e2d_vp, v, sizeof(g_e2d_vp));
    g_e2d_vp_hay = 1;
    DWORD e[6];
    e2d_vp_efectivo(e);
    if (memcmp(e, v, sizeof(e))) InterlockedIncrement(&c_e2d_vp);
    return g_e2d_vp_real(dev, e);
}
static long WINAPI e2d_getviewport(void *dev, DWORD *v)
{
    if (g_e2d_activa && v && g_e2d_vp_hay) {
        memcpy(v, g_e2d_vp, sizeof(g_e2d_vp));
        InterlockedIncrement(&c_e2d_get);
        return 0;
    }
    return g_e2d_gvp_real(dev, v);
}
static long WINAPI e2d_setscissor(void *dev, const RECT *r)
{
    if (!g_e2d_activa || !r || E2D_PASA || g_e2d_tipo == 3 || (g_e2d_stage_ahora && !g_e2d_stage))
        return g_e2d_sc_real(dev, r);
    g_e2d_sc = *r;
    g_e2d_sc_hay = 1;
    if (r->left == 0 && r->top == 0 && r->right >= g_e2d_w && r->bottom >= g_e2d_h) return g_e2d_sc_real(dev, r);
    long x = r->left, y = r->top, w = r->right - r->left, h = r->bottom - r->top;
    e2d_mapear(&x, &y, &w, &h);
    RECT n = {x, y, x + w, y + h};
    InterlockedIncrement(&c_e2d_sc);
    return g_e2d_sc_real(dev, &n);
}
static long WINAPI e2d_getscissor(void *dev, RECT *r)
{
    if (g_e2d_activa && r && g_e2d_sc_hay) { *r = g_e2d_sc; return 0; }
    return g_e2d_gsc_real(dev, r);
}
static long WINAPI e2d_setfvf(void *dev, DWORD fvf)
{
    g_e2d_fvf = fvf;
    return g_e2d_fvf_real(dev, fvf);
}

/* los dibujos XYZRHW (ya en píxeles): los de la interfaz (≤ 800×600) → R; los de pantalla entera, igual */
static BYTE *g_e2d_copia;
static UINT g_e2d_copia_tam;
static const void *e2d_rhw(const void *v, UINT n, UINT paso)
{
    if (g_e2d_viejos_n && !E2D_PASA && (g_e2d_fvf & 0x00E) == 0x004 && v && n && n <= 8 && paso >= 16) {
        const BYTE *b0 = (const BYTE *)v;
        float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
        for (UINT i = 0; i < n; i++) {
            const float *q = (const float *)(b0 + i * paso);
            x0 = fminf(x0, q[0]); y0 = fminf(y0, q[1]); x1 = fmaxf(x1, q[0]); y1 = fmaxf(y1, q[1]);
        }
        for (int k = 0; k < g_e2d_viejos_n; k++) {
            float wv = (float)g_e2d_viejos[k][0], hv = (float)g_e2d_viejos[k][1];
            if (!e2d_es_viejo(g_e2d_viejos[k][0], g_e2d_viejos[k][1]) || fabsf(x0) > 1.5f || fabsf(y0) > 1.5f
                || fabsf(x1 - wv) > 1.5f || fabsf(y1 - hv) > 1.5f) continue;
            UINT tam = n * paso;
            if (tam > g_e2d_copia_tam) {
                BYTE *nueva = (BYTE *)HeapAlloc(GetProcessHeap(), 0, tam + 4096);
                if (!nueva) break;
                if (g_e2d_copia) HeapFree(GetProcessHeap(), 0, g_e2d_copia);
                g_e2d_copia = nueva;
                g_e2d_copia_tam = tam + 4096;
            }
            memcpy(g_e2d_copia, v, tam);
            for (UINT i = 0; i < n; i++) {
                float *q = (float *)(g_e2d_copia + i * paso);
                q[0] = q[0] * (float)g_e2d_w / wv;
                q[1] = q[1] * (float)g_e2d_h / hv;
            }
            InterlockedIncrement(&c_e2d_rhw_viejo);
            return g_e2d_copia;
        }
    }
    if (!g_e2d_activa || E2D_PASA || (g_e2d_fvf & 0x00E) != 0x004 /* D3DFVF_XYZRHW */ || !v || !n || paso < 16
        || (g_e2d_stage_ahora && !g_e2d_stage) || n > 65536)
        return v;
    const BYTE *b = (const BYTE *)v;
    for (UINT i = 0; i < n; i++) {
        const float *q = (const float *)(b + i * paso);
        if (q[0] < -2 || q[1] < -2 || q[0] > g_e2d_lienzo + 2 || q[1] > 602) { InterlockedIncrement(&c_e2d_rhw_pant); return v; }
    }
    UINT tam = n * paso;
    if (tam > g_e2d_copia_tam) {
        BYTE *nueva = (BYTE *)HeapAlloc(GetProcessHeap(), 0, tam + 4096);
        if (!nueva) return v;
        if (g_e2d_copia) HeapFree(GetProcessHeap(), 0, g_e2d_copia);
        g_e2d_copia = nueva;
        g_e2d_copia_tam = tam + 4096;
    }
    memcpy(g_e2d_copia, v, tam);
    for (UINT i = 0; i < n; i++) {
        float *q = (float *)(g_e2d_copia + i * paso);
        q[0] = g_e2d_rx + q[0] * g_e2d_s;
        q[1] = g_e2d_ry + q[1] * g_e2d_s;
    }
    InterlockedIncrement(&c_e2d_rhw_ui);
    return g_e2d_copia;
}
static UINT e2d_vertices(DWORD tipo, UINT prims)
{
    switch (tipo) {
    case 1: return prims;               /* POINTLIST */
    case 2: return prims * 2;           /* LINELIST */
    case 3: return prims + 1;           /* LINESTRIP */
    case 4: return prims * 3;           /* TRIANGLELIST */
    case 5: case 6: return prims + 2;   /* STRIP / FAN */
    }
    return 0;
}
static void rojo_dibujo(DWORD dir, int clase);                       /* (eda_rojo.c: diagnóstico, sólo mira) */
static void rojo_rhw(DWORD dir, DWORD fvf, const void *v, UINT n, UINT paso);
static long WINAPI e2d_dpup(void *dev, DWORD tipo, UINT prims, const void *v, UINT paso)
{
    DWORD dir = (DWORD)(ULONG_PTR)__builtin_return_address(0);
    rojo_dibujo(dir, 2);
    rojo_rhw(dir, g_e2d_fvf, v, e2d_vertices(tipo, prims), paso);
    return g_e2d_dpup_real(dev, tipo, prims, e2d_rhw(v, e2d_vertices(tipo, prims), paso), paso);
}
static long WINAPI e2d_dipup(void *dev, DWORD tipo, UINT minimo, UINT nv, UINT prims, const void *idx, DWORD fmt,
                             const void *v, UINT paso)
{
    const void *nuevo = v;
    DWORD dir = (DWORD)(ULONG_PTR)__builtin_return_address(0);
    rojo_dibujo(dir, 3);
    if (v && nv && minimo < 65536) rojo_rhw(dir, g_e2d_fvf, (const BYTE *)v + minimo * paso, nv, paso);
    if (v && nv && minimo < 65536) {
        const BYTE *b = (const BYTE *)v;
        const void *t = e2d_rhw(b + minimo * paso, nv, paso);
        if (t != b + minimo * paso) nuevo = (const BYTE *)t - minimo * paso;   /* (los índices siguen valiendo) */
    }
    return g_e2d_dipup_real(dev, tipo, minimo, nv, prims, idx, fmt, nuevo, paso);
}

/* ── el mouse ── la posición de Windows (cliente) → la de la interfaz, y al revés */
static void e2d_cliente(HWND h, int *cw, int *ch)
{
    RECT r;
    *cw = g_e2d_w;
    *ch = g_e2d_h;
    if (h && GetClientRect(h, &r) && r.right > 0 && r.bottom > 0) { *cw = r.right; *ch = r.bottom; }
}
/* ★ (19-nov noche) EL MOUSE TAMBIÉN SIN ESCALA SI LA VENTANA ESTIRA: medido 19:08, 800×600 en «Sin bordes» (backbuffer
 *   800×600 en una ventana de 1920×1080): los clics caían en otro lado (el juego recibe píxeles de la ventana y los toma
 *   como suyos de 800×600). Sin escala (s = 1, R = 0) la misma conversión es sólo ventana → backbuffer. */
static int e2d_raton(void)
{
    if (g_e2d_activa) return 1;
    if (!g_e2d || !g_ventana_juego) return 0;
    RECT r;
    return GetClientRect(g_ventana_juego, &r) && r.right > 0 && r.bottom > 0 && (r.right != g_e2d_w || r.bottom != g_e2d_h);
}
static void e2d_ventana_a_ui(HWND h, int *x, int *y)
{
    int cw, ch;
    e2d_cliente(h, &cw, &ch);
    float bx = (float)*x * g_e2d_w / cw, by = (float)*y * g_e2d_h / ch;     /* (Windows puede estirar un poco) */
    *x = (int)floorf((bx - g_e2d_rx) / g_e2d_s + 0.5f);
    *y = (int)floorf((by - g_e2d_ry) / g_e2d_s + 0.5f);
}
static void e2d_ui_a_ventana(HWND h, int *x, int *y)
{
    int cw, ch;
    e2d_cliente(h, &cw, &ch);
    *x = (int)((g_e2d_rx + *x * g_e2d_s) * cw / g_e2d_w + 0.5f);
    *y = (int)((g_e2d_ry + *y * g_e2d_s) * ch / g_e2d_h + 0.5f);
}
/* ★★ (19-nov) APUNTANDO = LO QUE DICE EL JUEGO, NO UNA ADIVINANZA. Medido en el exe: el bucle principal centra el
 *   cursor físico (0x40B10B: SetPhysicalCursorPos(GetWindowRect.left + W/2, .top + H/2), vuelve a 0x40B13B) SÓLO si
 *   [0x917884] ≠ 0 y [0x90DE80] = 0 (0x90DE80 = la aplicación inactiva, 0x409B4F/0x409C66). En ese modo la cámara
 *   mira cuánto se aleja el cursor del juego de (400,300). Los demás SetPhysicalCursorPos del juego vienen de su
 *   «poner el cursor en la interfaz» (0x780BA0 → vuelve a 0x780BE1), en coordenadas de 800×600.
 *   ⛔ 41a393f3 (medido 13:15–13:19 por el dueño, AWARD RESULTS a 1920): tomaba TODO SetPhysicalCursorPos del Stage
 *   por «apuntar» (250 ms). Pero REWARD CHOICE / AWARD RESULTS son de la MISMA escena (0x899C20) y ahí el juego mueve
 *   el cursor por la interfaz (a 800×600 también se ve moverse solo): esos puntos de interfaz iban sin convertir y los
 *   mensajes como «(400,300) + movimiento» → el cursor saltaba de un lado a otro y los clics no caían en las cartas.
 *   Ahora: el centrado del bucle (por su dirección de vuelta) va tal cual; con [0x917884] prendido los mensajes llevan
 *   (400,300) + el movimiento real (la sensibilidad que el dueño aprobó); todo lo demás se convierte como en el lobby. */
static int e2d_dword(DWORD dir) { return (int)(ULONG_PTR)leer_ptr((const void *)(ULONG_PTR)dir); }
static int e2d_apuntando(void)
{
    return g_e2d_stage_ahora && !g_e2d_res_fase && e2d_dword(0x917884) != 0 && e2d_dword(0x90DE80) == 0;
}
/* (diagnóstico) el mouse de DirectInput que recibe el juego en el Stage (desde mi_diestado) */
static void e2d_di_mouse(long dx, long dy)
{
    if ((dx || dy) && e2d_trazando())
        apuntar("  (escala2d) traza: DirectInput mouse (%ld, %ld) · apuntando %d", dx, dy, e2d_apuntando());
    if (!g_e2d_activa || !g_e2d_stage_ahora || (!dx && !dy)) return;
    g_e2d_di_x += dx < 0 ? -dx : dx;
    g_e2d_di_y += dy < 0 ? -dy : dy;
    c_e2d_di++;
}
/* desde mi_peek, justo antes de que el mensaje le llegue al juego */
static void e2d_mouse(MSG *m)
{
    if (!e2d_raton() || !m || m->message < WM_MOUSEFIRST || m->message > WM_MOUSELAST
        || m->message == WM_MOUSEWHEEL || m->message == 0x020E /* WM_MOUSEHWHEEL: pantalla */
        || (g_e2d_stage_ahora && !g_e2d_stage))
        return;
    int x = (short)LOWORD(m->lParam), y = (short)HIWORD(m->lParam), x0 = x, y0 = y;
    static long trazados;
    if (e2d_trazando() && trazados++ < 300)
        apuntar("  (escala2d) traza: mensaje 0x%04X en (%d, %d) · apuntando %d · centro (%d, %d)", m->message, x0, y0,
                e2d_apuntando(), g_e2d_cur_x, g_e2d_cur_y);
    if (e2d_apuntando() && g_e2d_cur_x >= 0) {               /* apuntando: (400,300) + el movimiento real */
        int dx = x - g_e2d_cur_x, dy = y - g_e2d_cur_y, ux = x, uy = y, cx = g_e2d_cur_x, cy = g_e2d_cur_y;
        e2d_ventana_a_ui(m->hwnd, &ux, &uy);
        e2d_ventana_a_ui(m->hwnd, &cx, &cy);
        g_e2d_mov_real += abs(dx) + abs(dy);
        g_e2d_mov_ui += abs(ux - cx) + abs(uy - cy);
        static int saltos;                                   /* (diagnóstico) un movimiento enorme apuntando: de dónde */
        if (abs(dx) + abs(dy) > 300 && saltos < 20) {
            saltos++;
            apuntar("  (escala2d) ⚠ salto apuntando: mensaje 0x%04X en (%d, %d) · centro (%d, %d) → (%d, %d)",
                    m->message, x, y, g_e2d_cur_x, g_e2d_cur_y, 400 + dx, 300 + dy);
        }
        x = 400 + dx;
        y = 300 + dy;
        InterlockedIncrement(&c_e2d_mirada_mouse);
    } else
        e2d_ventana_a_ui(m->hwnd, &x, &y);
    m->lParam = MAKELPARAM((WORD)(short)x, (WORD)(short)y);
    InterlockedIncrement(&c_e2d_mouse);
}
/* cuando el juego pone el cursor de Windows (SetPhysicalCursorPos, en pantalla = cliente + SU posición);
 * vuelta = la dirección de vuelta del llamado (0x40B13B = el centrado del bucle principal) */
#define E2D_VUELTA_CENTRADO 0x0040B13Bu
static void e2d_setcur(int *x, int *y, DWORD vuelta)
{
    if (!e2d_raton() || !g_ventana_juego || (g_e2d_stage_ahora && !g_e2d_stage)) return;
    POINT o = {0, 0};
    if (!ClientToScreen(g_ventana_juego, &o)) return;
    int cx = *x - o.x, cy = *y - o.y;
    if (vuelta == E2D_VUELTA_CENTRADO) {                     /* el centrado del bucle: el medio de SU ventana, tal cual */
        g_e2d_cur_x = cx;
        g_e2d_cur_y = cy;
        InterlockedIncrement(&c_e2d_mirada);
        return;
    }
    e2d_ui_a_ventana(g_ventana_juego, &cx, &cy);
    /* ★ (19-nov) el último punto donde quedó el cursor de Windows, SIEMPRE en píxeles de la ventana. Medido (prueba del
     *   dueño, 14:55–14:56, 1920): cuando el juego ponía el cursor desde la interfaz (p. ej. (400,300)) se guardaba ese
     *   número de 800×600 como «centro» y el siguiente mensaje en (957,514) se leía como un salto de (+557,+214). */
    g_e2d_cur_x = cx;
    g_e2d_cur_y = cy;
    *x = o.x + cx;
    *y = o.y + cy;
    InterlockedIncrement(&c_e2d_setcur);
}

/* ★★ (19-nov) EL JUEGO TAMBIÉN LEE EL CURSOR FÍSICO. Medido 13:58 (9bdf69a8, 1920): cerrar Options con Esc en el
 *   Stage → la cámara al piso, SIN ningún mensaje de mouse raro (el registro de «saltos» quedó vacío). En el exe:
 *   0x780CD0 (al volver el foco / reiniciar la entrada) hace GetPhysicalCursorPos → ScreenToClient → cursor del juego
 *   (+0x27DC/+0x27E0) TAL CUAL, en píxeles de la ventana. A 800×600 eso es casi (400,300) (en ventana (397,274): un
 *   saltito); a 1920 es (957,514) = «+557,+214» desde (400,300) → la cámara salta. (0x780D20 también lo lee, para
 *   saber si el mouse está adentro.) Se le contesta en las MISMAS coordenadas que los mensajes: apuntando,
 *   (400,300) + lo que el mouse se alejó del centro; si no, la posición en la interfaz de 800×600. */
typedef BOOL (WINAPI *E2D_GETCUR)(POINT *);
static E2D_GETCUR g_e2d_getcur_real;
static long c_e2d_getcur;
static BOOL WINAPI e2d_getcur(POINT *p)
{
    BOOL r = g_e2d_getcur_real(p);
    if (!r || !p || !e2d_raton() || !g_ventana_juego || (g_e2d_stage_ahora && !g_e2d_stage)) return r;
    POINT o = {0, 0};
    if (!ClientToScreen(g_ventana_juego, &o)) return r;
    int x = p->x - o.x, y = p->y - o.y, ax = x, ay = y;
    if (e2d_apuntando() && g_e2d_cur_x >= 0 && !entrada_ok()) {
        /* ★ (19-nov, medido 14:16:35 con la cámara en la matriz de vista) con Options abierta el juego SIGUE leyendo el
         *   mouse físico (0x780D20, cada cuadro) y no lo recentra: el mouse en la X de Options (1498,167) se leía
         *   como (941,-47) → la cámara al piso (−80°) al cerrar. Mientras el juego no tiene la entrada (panel abierto,
         *   su Esc apretada, otra ventana al frente), apuntando, el mouse «no se movió»: el centro. */
        x = 400;
        y = 300;
    } else if (e2d_apuntando() && g_e2d_cur_x >= 0) {
        x = 400 + (x - g_e2d_cur_x);
        y = 300 + (y - g_e2d_cur_y);
    } else
        e2d_ventana_a_ui(g_ventana_juego, &x, &y);
    p->x = o.x + x;
    p->y = o.y + y;
    static int vistas;
    if (vistas < 12 || (e2d_trazando() && (x != 400 || y != 300 || __builtin_return_address(0) != (void *)0x00780D31))) {
        vistas++;
        apuntar("  (escala2d) el juego lee el cursor físico (vuelve a 0x%08lX): ventana (%d, %d) → %s (%d, %d)",
                (unsigned long)(ULONG_PTR)__builtin_return_address(0), ax, ay,
                e2d_apuntando() ? (entrada_ok() ? "apuntando" : "apuntando, sin la entrada → centro") : "interfaz", x, y);
    }
    InterlockedIncrement(&c_e2d_getcur);
    return r;
}

/* desde el Present: la escena del cuadro, el backbuffer real (una vez) y el registro (sólo si cambió, ≤ 1 cada 5 s) */
/* ★ (19-nov, Punto 5) LOS RESULTADOS EN SU 4:3, CON BANDAS NEGRAS. Medido (capturas del backbuffer 15:20:53 y 15:21:19,
 *   1920): MISSION COMPLETION / REWARD / AWARD tienen un fondo 2D que a 800×600 tapa toda la pantalla; a 16:9 ese fondo
 *   cubre sólo el 4:3 del medio y a los costados quedaban el Stage 3D y los paneles que a 800×600 están FUERA de la
 *   pantalla (REWARD deslizado a x −133…0 a la izquierda; AWARD esperando a la derecha). En resultados se pintan de
 *   negro las bandas fuera del 4:3 (como en el lobby): queda exactamente lo que se ve a 800×600, escalado. Un Clear
 *   antes del Present (con el viewport entero y el del juego devuelto). */
static long c_e2d_barras;
/* ★ (diag 19-nov tarde) LOS PRIMEROS CUADROS DEL STAGE: qué proyecciones 2D llegan (escaladas / otras), si los ganchos
 *   están puestos y una captura del backbuffer en cuadros elegidos (destello del HUD a 1920 reportado por el dueño). */
static int g_e2d_hud_n = -1;
static long g_e2d_hud_orto0, g_e2d_hud_otra0;
static void e2d_hud_diag(void *dev, int stage)
{
    static int stage_antes;
    if (stage && !stage_antes && g_diagnostico && g_e2d_activa) {
        g_e2d_hud_n = 0;
        g_e2d_hud_orto0 = c_e2d_orto;
        g_e2d_hud_otra0 = c_e2d_orto_otra;
    }
    stage_antes = stage;
    if (g_e2d_hud_n < 0) return;
    g_e2d_hud_n++;
    void **vt = dev ? VT(dev) : NULL;
    int st_ok = vt && vt[E2D_SETTRANSFORM] == (void *)e2d_settransform;
    long a = c_e2d_orto - g_e2d_hud_orto0, b = c_e2d_orto_otra - g_e2d_hud_otra0;
    g_e2d_hud_orto0 = c_e2d_orto;
    g_e2d_hud_otra0 = c_e2d_orto_otra;
    if (g_e2d_hud_n <= 40 || b || !st_ok)
        apuntar("  (escala2d) diag HUD cuadro %d: orto escaladas %ld · NO escaladas %ld%s · gancho SetTransform %s · fase %d",
                g_e2d_hud_n, a, b, "", st_ok ? "puesto" : "⚠ AJENO", g_e2d_fase_v);
    if (b) apuntar("  (escala2d)   la última NO escalada: m11 %.6f m22 %.6f m41 %.4f (vuelve a 0x%08lX) · backbuffer %d×%d",
                   g_e2d_otra_m0, g_e2d_otra_m5, g_e2d_otra_m12, (unsigned long)g_e2d_otra_vuelta, g_e2d_w, g_e2d_h);
    /* (las fotos de esos cuadros, sólo con medir5: cada una frena el juego ~0,8 s; medido 19-nov: el primer cuadro
     *   del Stage ya sale escalado a 1920×1080) */
    if (g_medir5 && g_e2d_hud_n >= 4 && g_e2d_hud_n <= 10) medir5_guardar(dev, 0xB000u + (DWORD)g_e2d_hud_n);
    if (g_e2d_hud_n >= 300) g_e2d_hud_n = -1;
}
static void e2d_barras(void *dev)
{
    if (!g_e2d_res_fase || !g_e2d_activa || !g_e2d_gvp_real || !g_e2d_vp_real || (g_e2d_rx < 1 && g_e2d_ry < 1)) return;
    DWORD antes[6], todo[6] = {0, 0, (DWORD)g_e2d_w, (DWORD)g_e2d_h, 0, 0x3F800000u /* 1.0f */};
    if (g_e2d_gvp_real(dev, antes) != 0) return;
    LONG x0 = (LONG)(g_e2d_rx + 0.5f), y0 = (LONG)(g_e2d_ry + 0.5f);
    LONG x1 = (LONG)(g_e2d_rx + 800 * g_e2d_s + 0.5f), y1 = (LONG)(g_e2d_ry + 600 * g_e2d_s + 0.5f);
    LONG r[4][4] = {{0, 0, x0, g_e2d_h}, {x1, 0, g_e2d_w, g_e2d_h}, {x0, 0, x1, y0}, {x0, y1, x1, g_e2d_h}};
    LONG usar[4][4];
    DWORD n = 0;
    for (int i = 0; i < 4; i++)
        if (r[i][2] > r[i][0] && r[i][3] > r[i][1]) { memcpy(usar[n], r[i], sizeof(r[i])); n++; }
    if (!n) return;
    g_e2d_vp_real(dev, todo);
    ((long (WINAPI *)(void *, DWORD, const void *, DWORD, DWORD, float, DWORD))VT(dev)[43])(dev, n, usar, 1 /* TARGET */,
                                                                                           0xFF000000u, 1.0f, 0);
    g_e2d_vp_real(dev, antes);
    InterlockedIncrement(&c_e2d_barras);
}
static void e2d_confirmar(void);
static void e2d_cuadro(void *dev)
{
    static DWORD ultimo;
    static char antes[640];
    {                                                        /* ★ la fase del Stage: con o sin escala */
        int f = e2d_fase_leer();
        if (f != g_e2d_fase_v) {
            if (g_diagnostico && (f >= 0 || g_e2d_fase_v >= 0)) apuntar("  (escala2d) fase del Stage: %d → %d", g_e2d_fase_v, f);
            e2d_fase_nueva(f);
        }
        g_e2d_res_fase = f >= 5 && f < 64;
        int stage = f >= 0;
        g_e2d_resultados = stage && (g_e2d_res_fase || e2d_dword(0x917884) == 0);
        e2d_confirmar();
    }
    if (!g_e2d_medido) {
        g_e2d_medido = 1;
        void *sup = NULL;
        if (((long (WINAPI *)(void *, UINT, UINT, UINT, void **))VT(dev)[18])(dev, 0, 0, 0, &sup) == 0 && sup) {
            DWORD d[8] = {0};
            ((long (WINAPI *)(void *, DWORD *))VT(sup)[12])(sup, d);
            ((ULONG (WINAPI *)(void *))VT(sup)[2])(sup);
            e2d_tamano((int)d[6], (int)d[7], "backbuffer real");
        }
    }
    if (!g_e2d) return;
    BYTE *esc = leer_ptr((void *)0x934554);
    DWORD vt = esc ? (DWORD)(ULONG_PTR)leer_ptr(esc) : 0;
    g_e2d_stage_ahora = vt == 0x00899C20;
    {                                                        /* ★ (24-nov) el lienzo del lobby panorámico */
        int L = e2d_lienzo_de(vt, g_e2d_lobby_ancho, g_e2d_sel_ancho, g_e2d_tie_ancho);
        if (L != g_e2d_lienzo) {
            g_e2d_lienzo = L;
            e2d_geometria();
            c_e2d_lienzo++;
            apuntar("  (panorámico) escena 0x%08lX → lienzo %d×600 ×%.3f en x %.0f · y %.0f", (unsigned long)vt, L,
                    g_e2d_s, g_e2d_rx, g_e2d_ry);
        }
    }
    if (e2d_trazando() && g_e2d_stage_ahora) {               /* (diagnóstico) el cursor del juego, cuando cambia */
        BYTE *o = leer_ptr((void *)0x94952C);
        static char antes[96];
        char ahora[96];
        if (o && legible(o + 0x27DC, 8)) {
            snprintf(ahora, sizeof(ahora), "%.0f,%.0f,%d,%d,%d", *(float *)(o + 0x27DC), *(float *)(o + 0x27E0),
                     e2d_apuntando(), e2d_dword(0x917884), e2d_dword(0x90DE80));
            if (strcmp(ahora, antes)) {
                strcpy(antes, ahora);
                apuntar("  (escala2d) traza: cuadro · cursor del juego (%.0f, %.0f) · apuntando %d · [0x917884] %d · inactiva %d",
                    *(float *)(o + 0x27DC), *(float *)(o + 0x27E0), e2d_apuntando(), e2d_dword(0x917884), e2d_dword(0x90DE80));
            }
        }
    }
    DWORD ahora_t = GetTickCount();
    if (g_e2d_activa) {                                      /* (diagnóstico) cuándo el juego prende / apaga «apuntar» */
        int mira = e2d_apuntando();
        if (mira != g_e2d_mira_antes) {
            if (g_e2d_mira_antes >= 0)
                apuntar("  (escala2d) apuntar del juego → %s (escena 0x%08lX · [0x917884] %d · inactiva %d · último centro %d,%d)",
                        mira ? "SÍ: (400,300)+movimiento" : "no: el mouse se convierte a la interfaz", (unsigned long)vt,
                        e2d_dword(0x917884), e2d_dword(0x90DE80), g_e2d_cur_x, g_e2d_cur_y);
            if (mira && g_e2d_stage_ahora && g_diagnostico && !g_e2d_fase_t[0]) {
                g_e2d_fase_t[0] = ahora_t + 4000;            /* (diag fase) dos fotos jugando */
                g_e2d_fase_t[1] = ahora_t + 8000;
            }
            if (g_e2d_mira_antes >= 0 && !mira && g_e2d_stage_ahora && g_diagnostico && g_e2d_fase_t[1] && !g_e2d_fase_t[2]) {
                g_e2d_fase_t[2] = ahora_t + 9000;            /* (diag fase) resultados (REWARD) y award */
                g_e2d_fase_t[3] = ahora_t + 32000;
            }
            if (g_e2d_mira_antes >= 0 && !mira && g_e2d_stage_ahora && g_diagnostico) {
                e2d_trazar(45000);                           /* (diag) REWARD / AWARD: 45 s de traza y capturas */
                g_e2d_foto = ahora_t + 4000;
                g_e2d_foto2 = ahora_t + 30000;
            }
            g_e2d_mira_antes = mira;
        }
    }
    for (int k = 0; k < 4; k++)
        if (g_e2d_fase_t[k] > 1 && (LONG)(ahora_t - g_e2d_fase_t[k]) >= 0 && g_e2d_stage_ahora) {
            g_e2d_fase_t[k] = 1;
            e2d_fase_foto(k);
            if (k == 3) e2d_fase_comparar();
        }
    if (!g_e2d_stage_ahora && g_e2d_fase_t[3] == 1) memset(g_e2d_fase_t, 0, sizeof(g_e2d_fase_t));   /* (otra vez en el próximo Stage) */
    e2d_barras(dev);
    e2d_hud_diag(dev, g_e2d_stage_ahora);
    if (g_e2d_foto && (LONG)(ahora_t - g_e2d_foto) >= 0) { g_e2d_foto = 0; medir5_guardar(dev, 0xA0001); }
    if (g_e2d_foto2 && (LONG)(ahora_t - g_e2d_foto2) >= 0) { g_e2d_foto2 = 0; medir5_guardar(dev, 0xA0002); }
    DWORD ahora = GetTickCount();
    if (!g_e2d_activa || ahora - ultimo < 5000) return;
    ultimo = ahora;
    char l[640];
    sprintf(l, "orto→R %ld · orto de una parte %ld · perspectiva fuera del Stage %ld (k %.2f) · en el Stage %ld · viewports %ld · "
               "scissor %ld · RHW interfaz %ld / pantalla %ld · mouse %ld · cursor %ld (último del juego %d,%d) · "
               "apuntar: centrado %ld, mensajes (400,300)+movimiento real %ld, movimiento real %ld (convertido sería %ld) · DirectInput mouse %ld |x| %ld |y| %ld · Get %ld · pantalla 800×600 a la interfaz %ld · tamaño viejo: viewports %ld / XYZRHW %ld",
            c_e2d_orto, c_e2d_orto_otra, c_e2d_persp, g_e2d_k, c_e2d_persp_stage, c_e2d_vp, c_e2d_sc, c_e2d_rhw_ui,
            c_e2d_rhw_pant, c_e2d_mouse, c_e2d_setcur, g_e2d_cur_x, g_e2d_cur_y, c_e2d_mirada, c_e2d_mirada_mouse,
            g_e2d_mov_real, g_e2d_mov_ui, c_e2d_di, g_e2d_di_x, g_e2d_di_y, c_e2d_get, c_e2d_prop, c_e2d_vp_viejo, c_e2d_rhw_viejo);
    if (strcmp(l, antes)) { lstrcpynA(antes, l, sizeof(antes)); apuntar("  (escala2d) escena 0x%08lX · %s", (unsigned long)vt, l); }
}

/* ★★ (19-nov) EL TAMAÑO DE PANTALLA QUE VE LA INTERFAZ. Medido en el exe: la interfaz del juego pregunta el ancho / alto
 *   de la pantalla al renderer (vtable 0x8ADEF0, ranura +0x4C = 0x776520: propiedad 0x11 = ancho [obj+0x330], 0x12 =
 *   alto) para ENCERRAR sus ventanas en la pantalla (0x4F2554, 0x527AB6, 0x527F6E, 0x528218, 0x535412) y para el
 *   deslizamiento de los paneles (0x5159E0 ancho, 0x51284F alto: «arranca en el borde de la pantalla»). A 800×600 da
 *   800: el panel de AWARD RESULTS entra desde el borde y queda en x≈50. A 1920 daba 1920 → quedaba en x≈W−750 de SU
 *   interfaz: 1280 → 530 (cortado a la derecha, las capturas del dueño), 1920 → 1170 (fuera de la pantalla). Con
 *   escala2d la interfaz ES de 800×600: a esas preguntas (sólo desde el código del juego, < 0x600000; el motor —el
 *   armado de la ortográfica 0x77BFBE, la cámara— sigue viendo la pantalla real) se contesta 800×600. */
typedef int (__attribute__((stdcall)) *E2D_PROP)(void *, int);
static E2D_PROP g_e2d_prop_real;
static int __attribute__((stdcall)) e2d_prop(void *obj, int id)
{
    int r = g_e2d_prop_real(obj, id);
    DWORD vuelta = (DWORD)(ULONG_PTR)__builtin_return_address(0);
    if (g_e2d_activa && (id == 0x11 || id == 0x12) && vuelta >= 0x00401000u && vuelta < 0x00600000u) {
        InterlockedIncrement(&c_e2d_prop);
        {                                                   /* (diag, Punto 6) a quién se le contesta 800×600, una vez cada uno */
            static DWORD vistos[32];
            static int n;
            int ya = 0;
            for (int i = 0; i < n; i++) if (vistos[i] == vuelta) ya = 1;
            if (!ya && n < 32 && g_diagnostico) {
                vistos[n++] = vuelta;
                apuntar("  (diag escala2d) %s 800×600 contestado a 0x%08lX (backbuffer %d×%d · %s)", id == 0x11 ? "ancho" : "alto",
                        (unsigned long)vuelta, g_e2d_w, g_e2d_h, g_e2d_stage_ahora ? "en el Stage" : "fuera del Stage");
            }
        }
        return id == 0x11 ? 800 : 600;
    }
    return r;
}
static void e2d_prop_enganchar(void)
{
    void **ranura = (void **)(ULONG_PTR)0x008ADF3C;
    if (g_e2d_prop_real || !legible(ranura, 4)) return;
    if ((DWORD)(ULONG_PTR)*ranura != 0x00776520u) {
        apuntar("  (escala2d) ⚠ el tamaño de pantalla de la interfaz NO se toca: la ranura 0x8ADF3C tiene 0x%08lX (se esperaba 0x776520)",
                (unsigned long)(ULONG_PTR)*ranura);
        return;
    }
    DWORD prot;
    if (!VirtualProtect(ranura, 4, PAGE_EXECUTE_READWRITE, &prot)) return;
    g_e2d_prop_real = (E2D_PROP)*ranura;
    *ranura = (void *)e2d_prop;
    VirtualProtect(ranura, 4, prot, &prot);
    apuntar("  (escala2d) la interfaz del juego ve una pantalla de 800×600 (ancho/alto del renderer, sólo para su código)");
}

/* ★ (Punto 6) SetRenderTarget: ¿el juego dibuja en la pantalla o en una textura? (por el tamaño: una textura del tamaño
 *   del backbuffer se trata como la pantalla, que es lo mismo para la escala). (diag) cada lugar del juego que pone un
 *   destino fuera de la pantalla, UNA vez, con su tamaño y el viewport que tenía. */
typedef long (WINAPI *E2D_SETRT_F)(void *, DWORD, void *);
static E2D_SETRT_F g_e2d_rt_real;
static long c_e2d_rt_fuera;
static long WINAPI e2d_setrt(void *dev, DWORD i, void *sup)
{
    long hr = g_e2d_rt_real(dev, i, sup);
    if (i != 0 || hr != 0) return hr;
    DWORD d[8] = {0};
    int w = 0, h = 0;
    if (sup && ((long (WINAPI *)(void *, void *))VT(sup)[12])(sup, d) == 0) { w = (int)d[6]; h = (int)d[7]; }
    LONG fuera = sup && w > 0 && (w != g_e2d_w || h != g_e2d_h);
    InterlockedExchange(&g_e2d_rt_fuera, fuera);
    if (fuera) {
        InterlockedIncrement(&c_e2d_rt_fuera);
        static DWORD vistos[16];
        static int n;
        DWORD dir = (DWORD)(ULONG_PTR)__builtin_return_address(0);
        int ya = 0;
        for (int k = 0; k < n; k++) if (vistos[k] == dir) ya = 1;
        if (!ya && n < 16 && g_diagnostico) {
            vistos[n++] = dir;
            apuntar("  (diag escala2d) el juego dibuja en una TEXTURA %d×%d (formato %lu · msaa %lu) desde 0x%08lX · backbuffer %d×%d · "
                    "escala %s · %s (la escala sigue igual que en la pantalla)", w, h, (unsigned long)d[0], (unsigned long)d[4],
                    (unsigned long)dir, g_e2d_w, g_e2d_h, g_e2d_activa ? "ACTIVA" : "×1", g_e2d_stage_ahora ? "en el Stage" : "fuera del Stage");
        }
    }
    return hr;
}

/* al crear el dispositivo y en cada Reset: el tamaño, y los ganchos (sólo con escala2d=1) */
static void e2d_dispositivo(void **vt, const void *pp)
{
    if (!g_e2d) return;
    InterlockedExchange(&g_e2d_rt_fuera, 0);                 /* (tras un Reset el destino es la pantalla) */
    const DWORD *p = (const DWORD *)pp;
    if (p && p[0] && p[1]) e2d_tamano((int)p[0], (int)p[1], "dispositivo");
    g_e2d_medido = 0;                                        /* (y el real, en el próximo Present) */
    e2d_prop_enganchar();
    if (vt && !g_e2d_rt_real) poner(vt, E2D_SETRT, (void *)e2d_setrt, (void **)&g_e2d_rt_real);
    if (!vt || g_e2d_st_real) return;
    poner(vt, E2D_SETTRANSFORM, (void *)e2d_settransform, (void **)&g_e2d_st_real);
    poner(vt, E2D_GETTRANSFORM, (void *)e2d_gettransform, (void **)&g_e2d_gt_real);
    poner(vt, E2D_SETVIEWPORT, (void *)e2d_setviewport, (void **)&g_e2d_vp_real);
    poner(vt, E2D_GETVIEWPORT, (void *)e2d_getviewport, (void **)&g_e2d_gvp_real);
    poner(vt, E2D_SETSCISSOR, (void *)e2d_setscissor, (void **)&g_e2d_sc_real);
    poner(vt, E2D_GETSCISSOR, (void *)e2d_getscissor, (void **)&g_e2d_gsc_real);
    poner(vt, E2D_I_DPUP, (void *)e2d_dpup, (void **)&g_e2d_dpup_real);
    poner(vt, E2D_I_DIPUP, (void *)e2d_dipup, (void **)&g_e2d_dipup_real);
    poner(vt, E2D_SETFVF, (void *)e2d_setfvf, (void **)&g_e2d_fvf_real);
    apuntar("  (escala2d) ★ EXPERIMENTAL: enganchados Set/GetTransform, Set/GetViewport, Set/GetScissorRect, "
            "DrawPrimitiveUP, DrawIndexedPrimitiveUP y SetFVF · HUD del Stage %s", g_e2d_stage ? "también" : "como hoy");
}
static void e2d_reafirmar(void **vt, int (*reafirmar_fn)(void **, int, void *, void **, const char *))
{
    if (!g_e2d_st_real) return;
    reafirmar_fn(vt, E2D_SETTRANSFORM, (void *)e2d_settransform, (void **)&g_e2d_st_real, "SetTransform");
    reafirmar_fn(vt, E2D_GETTRANSFORM, (void *)e2d_gettransform, (void **)&g_e2d_gt_real, "GetTransform");
    reafirmar_fn(vt, E2D_SETVIEWPORT, (void *)e2d_setviewport, (void **)&g_e2d_vp_real, "SetViewport");
    reafirmar_fn(vt, E2D_GETVIEWPORT, (void *)e2d_getviewport, (void **)&g_e2d_gvp_real, "GetViewport");
    reafirmar_fn(vt, E2D_SETSCISSOR, (void *)e2d_setscissor, (void **)&g_e2d_sc_real, "SetScissorRect");
    reafirmar_fn(vt, E2D_GETSCISSOR, (void *)e2d_getscissor, (void **)&g_e2d_gsc_real, "GetScissorRect");
    reafirmar_fn(vt, E2D_I_DPUP, (void *)e2d_dpup, (void **)&g_e2d_dpup_real, "DrawPrimitiveUP");
    reafirmar_fn(vt, E2D_I_DIPUP, (void *)e2d_dipup, (void **)&g_e2d_dipup_real, "DrawIndexedPrimitiveUP");
    reafirmar_fn(vt, E2D_SETFVF, (void *)e2d_setfvf, (void **)&g_e2d_fvf_real, "SetFVF");
    reafirmar_fn(vt, E2D_SETRT, (void *)e2d_setrt, (void **)&g_e2d_rt_real, "SetRenderTarget");
}

/* [pantalla] escala2d / escala2d_stage / resolucion (del eda_d3d9.ini) */
/* ★ (19-nov, Punto 5) RESOLUCIÓN DESDE OPTIONS, CON VUELTA ATRÁS. Options → Pantalla guarda [pantalla] resolucion /
 *   escala2d y, si cambiaron, resolucion_anterior / escala2d_anterior y confirmar=1. Al arrancar: si confirmar=1 y
 *   ya hubo un intento (intentos=1) que no llegó a confirmarse (el juego se cerró o se colgó antes de 8 s dibujando
 *   una escena), se vuelve a lo anterior. Si arranca bien, e2d_confirmar() lo da por bueno. */
static char g_e2d_ini[MAX_PATH];
static int g_e2d_confirmar_pend;
static DWORD g_e2d_confirmar_desde;
static char g_e2d_revertida[96];
static int g_e2d_ini_e2d = 0, g_e2d_ini_w = 800, g_e2d_ini_h = 600;   /* (lo que dice el ini: lo que pide Options) */
static void e2d_confirmar(void)
{
    if (!g_e2d_confirmar_pend || !g_e2d_ini[0]) return;
    DWORD ahora = GetTickCount();
    BYTE *esc = leer_ptr((void *)0x934554);
    if (!esc) { g_e2d_confirmar_desde = 0; return; }
    if (!g_e2d_confirmar_desde) { g_e2d_confirmar_desde = ahora ? ahora : 1; return; }
    if (ahora - g_e2d_confirmar_desde < 8000) return;
    g_e2d_confirmar_pend = 0;
    WritePrivateProfileStringA("pantalla", "confirmar", "0", g_e2d_ini);
    WritePrivateProfileStringA("pantalla", "intentos", "0", g_e2d_ini);
    apuntar("  (escala2d) ✅ resolución %d×%d confirmada (8 s dibujando): queda guardada", g_res_w, g_res_h);
}
static int e2d_res_valida(const char *v, int *w, int *h)
{
    return sscanf(v, "%dx%d", w, h) == 2 && *w >= 800 && *h >= 600 && *w <= 7680 && *h <= 4320;
}
static void e2d_leer_ini(const char *ini)
{
    char v[32], a[32];
    lstrcpynA(g_e2d_ini, ini, MAX_PATH);
    if (GetPrivateProfileIntA("pantalla", "confirmar", 0, ini)) {
        if (GetPrivateProfileIntA("pantalla", "intentos", 0, ini) >= 1) {     /* ★ el intento anterior no arrancó */
            GetPrivateProfileStringA("pantalla", "resolucion", "", v, sizeof(v), ini);
            GetPrivateProfileStringA("pantalla", "resolucion_anterior", "800x600", a, sizeof(a), ini);
            int ew = GetPrivateProfileIntA("pantalla", "escala2d_anterior", 1, ini);
            int w, h;
            if (!e2d_res_valida(a, &w, &h)) lstrcpyA(a, "800x600");
            WritePrivateProfileStringA("pantalla", "resolucion", a, ini);
            WritePrivateProfileStringA("pantalla", "escala2d", ew ? "1" : "0", ini);
            WritePrivateProfileStringA("pantalla", "confirmar", "0", ini);
            WritePrivateProfileStringA("pantalla", "intentos", "0", ini);
            wsprintfA(g_e2d_revertida, "%s no arrancó: volvió a %s", v, a);
            WritePrivateProfileStringA("pantalla", "revertida", g_e2d_revertida, ini);
            apuntar("  (escala2d) ⚠ la resolución %s no se confirmó en el intento anterior: se vuelve a %s", v, a);
        } else {
            WritePrivateProfileStringA("pantalla", "intentos", "1", ini);
            g_e2d_confirmar_pend = 1;
        }
    }
    /* ★ (Punto 6, 20-nov) LA ADAPTACIÓN 2D, SIEMPRE: ya no es una opción del jugador. A 800×600 no hace nada (escala
     *   ×1) y a cualquier otro tamaño es lo que mantiene menús, HUD, mouse y resultados en su lugar; sin ella un cambio
     *   de resolución pedía reiniciar. (EDA_ESCALA2D=0 la apaga, sólo para medir.) */
    g_e2d = 1;
    g_e2d_stage = GetPrivateProfileIntA("pantalla", "escala2d_stage", 1, ini);
    g_e2d_ambiente = GetPrivateProfileIntA("pantalla", "ambiente", 1, ini);
    g_e2d_ini_e2d = g_e2d;
    if (GetEnvironmentVariableA("EDA_ESCALA2D", v, sizeof(v))) g_e2d = atoi(v);
    int w = 0, h = 0;
    GetPrivateProfileStringA("pantalla", "resolucion", "", v, sizeof(v), ini);
    if (e2d_res_valida(v, &w, &h)) { g_e2d_ini_w = w; g_e2d_ini_h = h; }
    if (!g_medir5 && e2d_res_valida(v, &w, &h)) {
        g_res_w = w;                     /* (lo que va al autoexec.cfg: screenwidth / screenheight; también sin escala) */
        g_res_h = h;
    }
    if (!g_e2d) {
        if (g_res_w != 800 || g_res_h != 600)
            apuntar("  (escala2d) resolución %d×%d SIN adaptación 2D (la interfaz queda en 800×600 arriba a la izquierda)",
                    g_res_w, g_res_h);
        return;
    }
    {                                                        /* ★ (20-nov) ¿la sesión anterior se cayó en un intento? */
        int perm = GetPrivateProfileIntA("pantalla", "en_vivo_tras_stage", 0, ini);
        int pend = GetPrivateProfileIntA("pantalla", "vivo_tras_stage_intento", 0, ini);
        if (pend) {
            int nuevo = e2d_tras_stage_al_arrancar(perm, pend);
            WritePrivateProfileStringA("pantalla", "en_vivo_tras_stage", nuevo ? "1" : "0", ini);
            WritePrivateProfileStringA("pantalla", "vivo_tras_stage_intento", "0", ini);
            apuntar("  (escala2d) ⚠ la sesión anterior se cerró durante un cambio EN VIVO después de un Stage: de ahora en "
                    "adelante, después de un Stage la resolución se aplica al reiniciar ([pantalla] en_vivo_tras_stage=0)");
        }
    }
    if (GetEnvironmentVariableA("EDA_CAPTURAS", v, sizeof(v)) && v[0] == '1') g_medir5 = 1;   /* (capturas: sólo la prueba) */
    apuntar("  (escala2d) Adaptación 2D interna (siempre): resolución %d×%d · HUD del Stage %s%s", g_res_w, g_res_h,
            g_e2d_stage ? "escalado" : "como hoy", g_medir5 ? " · capturas del backbuffer" : "");
}
