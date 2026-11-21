/* eda_rojo.c — ★ (19-nov noche, diagnóstico) EL DESTELLO ROJO. Sólo mira: no cambia ningún dibujo.
 *   El dueño ve un destello rojo de pantalla entera al golpear (a 800, 1280 y 1920). Para saber si es del juego o
 *   nuestro, en el Stage (con EDA_DIAGNOSTICO) cada cuadro:
 *     1. se achica el backbuffer a 16×12 (StretchRect + GetRenderTargetData) y se mide cuánto rojo tiene;
 *     2. se anota QUIÉN dibujó (la dirección de vuelta de cada DrawPrimitive / DrawIndexedPrimitive / …UP) y los
 *        dibujos XYZRHW que tapan la pantalla entera (con su color, si traen DIFFUSE).
 *   Cuando aparece un cuadro rojo: lo que se dibujó en ese cuadro y NO en el anterior normal, con sus direcciones
 *   (dentro de EDA.exe = el juego; otra = otro programa o la dll), y una captura (las dos primeras veces).
 * ★ MEDIDO 19-nov 18:13 / 18:16 / 18:20 (server local, 1280×720): el destello es del MOTOR del juego. EDA.exe 0x660E60
 *   (llamado al final del render de la escena, 0x6612F3) dibuja un cuadrado XYZRHW de pantalla entera (0,0)-(1280,720)
 *   con mezcla ADITIVA (SRCBLEND = DESTBLEND = ONE) y el color «light add» de la escena (0xFFFF552A … 0xFFFF955F),
 *   si la variable del motor «LightAddPoly» vale 1 (lo normal). Lo pide el juego en algunos ataques; dura ~60 ms
 *   (9 cuadros a 120/s). La dll no lo cambia (pasa sin tocar: sus vértices pasan de 800×600). Es original: se conserva.
 *   Apagado por defecto (cada medición lee el backbuffer); EDA_ROJO=1 lo vuelve a prender. */

#define RJ_N 128
typedef struct { DWORD dir, n, clase; } RJ_E;
static RJ_E g_rj_ahora[RJ_N], g_rj_antes[RJ_N];
static int g_rj_ahora_n, g_rj_antes_n, g_rj_lleno;
static int g_rojo_on;                              /* (el diagnóstico prendido y en el Stage: se anotan dibujos) */
static int g_rojo_hab = -1;                        /* -1: sin leer · 0 apagado · 1 prendido */
typedef struct { DWORD dir, color, n, fvf; float x0, y0, x1, y1; } RJ_P;
static RJ_P g_rj_pant[8];
static int g_rj_pant_n;
static void *g_rj_rt, *g_rj_sys;
static DWORD g_rj_fmt;
static const char *const RJ_CLASE[] = {"DrawPrimitive", "DrawIndexedPrimitive", "DrawPrimitiveUP", "DrawIndexedPrimitiveUP"};

static void rojo_dibujo(DWORD dir, int clase)
{
    if (!g_rojo_on) return;
    for (int i = 0; i < g_rj_ahora_n; i++)
        if (g_rj_ahora[i].dir == dir && g_rj_ahora[i].clase == (DWORD)clase) { g_rj_ahora[i].n++; return; }
    if (g_rj_ahora_n >= RJ_N) { g_rj_lleno = 1; return; }
    g_rj_ahora[g_rj_ahora_n].dir = dir;
    g_rj_ahora[g_rj_ahora_n].clase = (DWORD)clase;
    g_rj_ahora[g_rj_ahora_n].n = 1;
    g_rj_ahora_n++;
}
/* los XYZRHW que tapan (casi) toda la pantalla: en píxeles de 800×600 o del backbuffer real */
static void rojo_rhw(DWORD dir, DWORD fvf, const void *v, UINT n, UINT paso)
{
    if (!g_rojo_on || !v || !n || n > 4096 || paso < 16 || (fvf & 0x00E) != 0x004) return;
    const BYTE *b = (const BYTE *)v;
    float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
    for (UINT i = 0; i < n; i++) {
        const float *q = (const float *)(b + i * paso);
        if (q[0] < x0) x0 = q[0];
        if (q[0] > x1) x1 = q[0];
        if (q[1] < y0) y0 = q[1];
        if (q[1] > y1) y1 = q[1];
    }
    if (x0 > 8 || y0 > 8 || x1 - x0 < 700 || y1 - y0 < 520) return;      /* (no tapa la pantalla) */
    for (int i = 0; i < g_rj_pant_n; i++)
        if (g_rj_pant[i].dir == dir) { g_rj_pant[i].n++; return; }
    if (g_rj_pant_n >= 8) return;
    RJ_P *p = &g_rj_pant[g_rj_pant_n++];
    p->dir = dir;
    p->fvf = fvf;
    p->color = (fvf & 0x040) && paso >= 20 ? *(const DWORD *)(b + 16) : 0;   /* (DIFFUSE va después de XYZRHW) */
    p->n = 1;
    p->x0 = x0; p->y0 = y0; p->x1 = x1; p->y1 = y1;
}

static void rojo_soltar(void)                      /* (antes del Reset: lo del pool DEFAULT no puede quedar) */
{
    if (g_rj_rt) { ((ULONG (WINAPI *)(void *))VT(g_rj_rt)[2])(g_rj_rt); g_rj_rt = NULL; }
    if (g_rj_sys) { ((ULONG (WINAPI *)(void *))VT(g_rj_sys)[2])(g_rj_sys); g_rj_sys = NULL; }
}

static int rojo_medir(void *dev, int *r, int *g, int *bl, int *frac)
{
    void **vt = VT(dev);
    void *bb = NULL;
    if (((long (WINAPI *)(void *, UINT, UINT, UINT, void **))vt[18])(dev, 0, 0, 0, &bb) != 0 || !bb) return 0;
    DWORD d[8] = {0};
    ((long (WINAPI *)(void *, DWORD *))VT(bb)[12])(bb, d);
    if (!g_rj_rt || g_rj_fmt != d[0]) {
        rojo_soltar();
        g_rj_fmt = d[0];
        if (((long (WINAPI *)(void *, UINT, UINT, DWORD, DWORD, DWORD, BOOL, void **, void *))vt[28])(
                dev, 16, 12, d[0], 0, 0, FALSE, &g_rj_rt, NULL) != 0
            || ((long (WINAPI *)(void *, UINT, UINT, DWORD, DWORD, void **, void *))vt[36])(
                dev, 16, 12, d[0], 2 /* SYSTEMMEM */, &g_rj_sys, NULL) != 0) {
            apuntar("  (diag rojo) ⚠ no pude crear la superficie de medición (formato %lu): sin medición", d[0]);
            rojo_soltar();
            g_rojo_hab = 0;
            ((ULONG (WINAPI *)(void *))VT(bb)[2])(bb);
            return 0;
        }
    }
    long hr = ((long (WINAPI *)(void *, void *, const RECT *, void *, const RECT *, DWORD))vt[34])(
        dev, bb, NULL, g_rj_rt, NULL, 2 /* LINEAR */);
    ((ULONG (WINAPI *)(void *))VT(bb)[2])(bb);
    if (hr != 0) return 0;
    if (((long (WINAPI *)(void *, void *, void *))vt[32])(dev, g_rj_rt, g_rj_sys) != 0) return 0;
    struct { INT pitch; BYTE *bits; } lr;
    if (((long (WINAPI *)(void *, void *, const RECT *, DWORD))VT(g_rj_sys)[13])(g_rj_sys, &lr, NULL, 0x10 /* READONLY */) != 0)
        return 0;
    long sr = 0, sg = 0, sb = 0;
    int rojos = 0;
    for (int y = 0; y < 12; y++)
        for (int x = 0; x < 16; x++) {
            const BYTE *p = lr.bits + y * lr.pitch + x * 4;              /* (X8R8G8B8 / A8R8G8B8: B G R A) */
            int pb = p[0], pg = p[1], pr = p[2];
            sr += pr; sg += pg; sb += pb;
            int mx = pg > pb ? pg : pb;
            if (pr > mx * 14 / 10 + 12) rojos++;
        }
    ((long (WINAPI *)(void *))VT(g_rj_sys)[14])(g_rj_sys);
    *r = (int)(sr / 192); *g = (int)(sg / 192); *bl = (int)(sb / 192);
    *frac = rojos * 100 / 192;
    return 1;
}

static void rojo_listar(const char *que)
{
    int k = 0;
    for (int i = 0; i < g_rj_ahora_n && k < 14; i++) {
        DWORD antes = 0;
        for (int j = 0; j < g_rj_antes_n; j++)
            if (g_rj_antes[j].dir == g_rj_ahora[i].dir && g_rj_antes[j].clase == g_rj_ahora[i].clase) { antes = g_rj_antes[j].n; break; }
        if (antes && g_rj_ahora[i].n < antes * 2 + 2) continue;
        DWORD d = g_rj_ahora[i].dir;
        apuntar("  (diag rojo)     %s: %s desde 0x%08lX (%s) · %lu veces (el cuadro normal anterior: %lu)", que,
                RJ_CLASE[g_rj_ahora[i].clase & 3], (unsigned long)d,
                d >= 0x400000 && d < 0x9A0000 ? "EDA.exe" : "OTRO módulo", (unsigned long)g_rj_ahora[i].n, (unsigned long)antes);
        k++;
    }
    if (!k) apuntar("  (diag rojo)     %s: ningún dibujo nuevo respecto del cuadro anterior", que);
    for (int i = 0; i < g_rj_pant_n; i++)
        apuntar("  (diag rojo)     pantalla entera XYZRHW desde 0x%08lX (%s) · FVF 0x%03lX · color 0x%08lX · (%.0f,%.0f)-(%.0f,%.0f) · %lu veces",
                (unsigned long)g_rj_pant[i].dir, g_rj_pant[i].dir >= 0x400000 && g_rj_pant[i].dir < 0x9A0000 ? "EDA.exe" : "OTRO módulo",
                (unsigned long)g_rj_pant[i].fvf, (unsigned long)g_rj_pant[i].color, g_rj_pant[i].x0, g_rj_pant[i].y0,
                g_rj_pant[i].x1, g_rj_pant[i].y1, (unsigned long)g_rj_pant[i].n);
}

/* desde el Present (antes del real) */
static void rojo_cuadro(void *dev, int stage)
{
    static int en_rojo, eventos, fotos;
    static DWORD rojo_desde, rojo_cuadros, cuadro, ult_resumen, c_cuadros, c_rojos, max_frac;
    static float base = -1;
    if (g_rojo_hab < 0) {
        char v[8];
        g_rojo_hab = 0;                                   /* (sólo con EDA_ROJO=1: medido 19-nov, ver abajo) */
        if (GetEnvironmentVariableA("EDA_ROJO", v, sizeof(v))) g_rojo_hab = atoi(v);
        if (g_rojo_hab) apuntar("  (diag rojo) ★ medición del destello rojo en el Stage: prendida (sólo mira)");
    }
    int on = g_rojo_hab > 0 && stage && dev;
    if (!on) {
        if (g_rojo_on) { g_rojo_on = 0; en_rojo = 0; }
        return;
    }
    if (!g_rojo_on) {                                         /* (primer cuadro del Stage: todavía nada que comparar) */
        g_rojo_on = 1;
        g_rj_ahora_n = g_rj_antes_n = g_rj_pant_n = 0;
        base = -1;
        return;
    }
    cuadro++;
    int r, g, b, frac;
    if (rojo_medir(dev, &r, &g, &b, &frac)) {
        float ratio = (float)r / (1.0f + (g + b) * 0.5f);
        if (base < 0) base = ratio;
        int es = frac >= 35 || (ratio > base * 1.6f + 0.15f && r > 45);
        c_cuadros++;
        if (es) c_rojos++;
        if ((DWORD)frac > max_frac) max_frac = (DWORD)frac;
        if (es && !en_rojo) {
            en_rojo = 1;
            rojo_desde = GetTickCount();
            rojo_cuadros = 0;
            eventos++;
            apuntar("  (diag rojo) ⚠ CUADRO ROJO #%d (cuadro %lu): medio R %d G %d B %d · %d%% de la pantalla roja · "
                    "rojo/resto %.2f (normal %.2f)%s", eventos, (unsigned long)cuadro, r, g, b, frac, ratio, base,
                    g_rj_lleno ? " · (lista de dibujos llena)" : "");
            if (eventos <= 6) rojo_listar("nuevo en el rojo");
            if (fotos < 2) { fotos++; medir5_guardar(dev, 0xF00000u + (DWORD)eventos); }
        } else if (!es && en_rojo) {
            en_rojo = 0;
            apuntar("  (diag rojo)   fin del rojo #%d: %lu cuadros · %lu ms", eventos, (unsigned long)rojo_cuadros + 1,
                    (unsigned long)(GetTickCount() - rojo_desde));
        }
        if (en_rojo) rojo_cuadros++;
        else {
            base = base * 0.95f + ratio * 0.05f;
            memcpy(g_rj_antes, g_rj_ahora, sizeof(RJ_E) * (size_t)g_rj_ahora_n);
            g_rj_antes_n = g_rj_ahora_n;
        }
    }
    DWORD ahora = GetTickCount();
    if (ahora - ult_resumen >= 10000) {
        if (ult_resumen)
            apuntar("  (diag rojo) 10 s: %lu cuadros medidos · %lu rojos · máximo %lu%% de pantalla roja · eventos %d · "
                    "pantalla entera XYZRHW en el último cuadro: %d", (unsigned long)c_cuadros, (unsigned long)c_rojos,
                    (unsigned long)max_frac, eventos, g_rj_pant_n);
        ult_resumen = ahora;
        c_cuadros = c_rojos = max_frac = 0;
    }
    g_rj_ahora_n = 0;
    g_rj_pant_n = 0;
    g_rj_lleno = 0;
}
