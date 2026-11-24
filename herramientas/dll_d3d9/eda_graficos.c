/* eda_graficos.c — ★ (Punto 6, 19/20-nov) CALIDAD GRÁFICA, BRILLO REAL Y EL DESTELLO ROJO.
 *
 *  1. EL DESTELLO ROJO (medido 19-nov 18:13–18:20 y en el exe): EDA.exe 0x660E60 es la ÚNICA función que dibuja el
 *     «light add» de la escena: un cuadrado XYZRHW de pantalla entera con mezcla aditiva y el color «light add»
 *     (rojo-anaranjado en algunos ataques). La llama sólo 0x6612F3 (el final del render de la escena) y no recibe
 *     argumentos por la pila (thiscall, `ret` simple en 0x661244): no comparte código con luces, partículas ni
 *     auras. Se anula ESE llamado (5 NOP) con la firma comprobada; nada más. `LightAddPoly 0` no se usa: es la
 *     variable que la habilita, pero el motor la lee también en otros lados. [graficos] destello_rojo=1 lo devuelve.
 *
 *  2. EL BRILLO (medido en el exe): Options mandaba GammaR/G/B → 0x6604C0 → IDirect3DDevice9::SetGammaRamp, que en
 *     MODO VENTANA no hace nada (y EDA está siempre en ventana: la pantalla completa es sin bordes). Por eso el
 *     control no cambiaba la imagen. Ahora el brillo lo pone la dll en el Present: un cuadrado de pantalla entera que
 *     MULTIPLICA el color (DESTCOLOR·k + dst), sólo dentro del juego: ni la gamma de Windows ni el monitor se tocan.
 *     Las variables Gamma del autoexec.cfg ya no se escriben (quedan como estén).
 *
 *  3. LA CALIDAD: el motor trae «Anisotropic» / «Trilinear» / «MipMapBias», pero los pone sólo al armar sus estados
 *     (no en vivo). La dll los aplica en SetSamplerState (vt 69), según lo que la placa dice que puede (GetDeviceCaps):
 *       · anisotrópico ×N: MINFILTER LINEAR → ANISOTROPIC y MAXANISOTROPY N (las 2D de la interfaz, alineadas a la
 *         pantalla, se ven igual: el anisotrópico sólo cambia las superficies en ángulo — el piso, las paredes);
 *       · trilineal: MIPFILTER POINT → LINEAR (sin «escalones» entre mipmaps);
 *       · nitidez: MIPMAPLODBIAS −0,5 (texturas algo más nítidas a distancia);
 *       · antialiasing ×N (MSAA): en los parámetros del CreateDevice/Reset, sólo si CheckDeviceMultiSampleType lo
 *         acepta para el formato del backbuffer y el de profundidad; si el dispositivo no se crea así, se reintenta
 *         sin él. Cambiarlo rehace el dispositivo en vivo (RestartRender, ~1 s), sin cerrar EDA.
 *     Las sombras de los personajes: ModelShadow_Proj_TextureRes 128 / 256 / 512 (el motor rehace sus texturas
 *     cuando cambia: 0x6D6532; tope 512 en 0x6D655B). */

static int g_gr_aniso = 1;            /* 1 = apagado; 2..16 */
static int g_gr_tri = 0;
static int g_gr_nitidez = 0;          /* 1 = MIPMAPLODBIAS −0,5 */
static int g_gr_aa = 0;               /* 0, 2, 4, 8 (lo pedido) */
static int g_gr_aa_puesto = -1;       /* lo que se le pasó al último CreateDevice / Reset */
static int g_gr_sombras_res = 128;    /* 128 / 256 / 512 */
static int g_gr_perfil = 2;           /* 0 bajo · 1 medio · 2 alto · 3 máximo · 4 personalizado */
static int g_gr_destello = 0;         /* 0 = el destello rojo quitado (por defecto) */
static volatile LONG g_gr_brillo = 100; /* 50..150 (100 = como el juego) */
static volatile LONG g_gr_rehacer;
static int g_gr_volcar;               /* (EDA_VOLCAR_TEXTURAS=1: las texturas de la interfaz a .tga; sólo para medir) */
static int g_gr_desligar = 1;
static int g_gr_ui_clamp = 1;          /* ★ (20-nov) [graficos] interfaz_clamp: imágenes de la interfaz agrandadas con CLAMP (0 = como antes) */          /* ★ (20-nov) [graficos] reset_desligar: 1 = sacar lo puesto antes del Reset · 0 = como antes */
static int g_gr_letras = 1;           /* (Punto 6) letras: 1 = el atlas del juego dibujado al doble (GDI) · 2 = los gemelos de prueba · 0 = como en 2009 */
static void *g_gr_rt_tex[16];         /* (diag) las texturas que se usan como render target */
static int g_gr_rt_tex_n;
static int g_gr_creando;              /* (la dll creando un gemelo: CreateTexture no lo cuenta) */
typedef BOOL (WINAPI *M_TOUTW)(HDC, int, int, LPCWSTR, int);
static M_TOUTW g_gr_toutw_real;
typedef BOOL (WINAPI *M_TOUTA)(HDC, int, int, const char *, int);
static M_TOUTA g_gr_touta_real;
static BOOL WINAPI gr_textouta(HDC dc, int x, int y, const char *t, int n);
static const BYTE *gr_vf_buscar(const BYTE *a4, int w, int h);   /* (el atlas de una fuente del motor, dibujado al doble) */
static volatile DWORD g_gr_texto_hilo;        /* el hilo que acaba de hacer TextOutW (0 = nada pendiente) */
static BOOL WINAPI gr_textoutw(HDC dc, int x, int y, LPCWSTR t, int n);
static void gr_tx_nueva(void *tex, DWORD fmt, DWORD pool);    /* Options pidió otro antialias: el dispositivo se rehace en vivo (pan_vivo_tick) */
/* lo que la placa puede (al crear el dispositivo) */
static int g_gr_aniso_max = 16, g_gr_aniso_ok = 1, g_gr_aa_max = 8, g_gr_caps_leidas;
static char g_gr_placa[96];
static void *g_gr_d3d;                /* el IDirect3D9 del último CreateDevice (RestartRender crea otro) */
static UINT g_gr_adaptador;
static long c_gr_aniso, c_gr_tri;     /* (diag) conversiones */
typedef long (WINAPI *M_SAMPLER)(void *, DWORD, DWORD, DWORD);
static M_SAMPLER g_gr_sss_real;
enum { GR_I_SETSAMPLER = 69, GR_I_GETCAPS = 7 };

/* (Options → Pantalla) ¿una ventana con cliente w×h (más fw×fh de bordes y título) entra en un área de trabajo tw×th? */
static int pan_cabe(int w, int h, int fw, int fh, int tw, int th) { return w + fw <= tw && h + fh <= th; }

/* ── la configuración ── */
static const char *const GR_PERFILES[5] = {"bajo", "medio", "alto", "maximo", "personalizado"};
typedef struct { int aniso, tri, nitidez, aa, sombras, sombras_res, detalle, reflejos; } GR_PERFIL;
static const GR_PERFIL GR_P[4] = {
    {1, 0, 0, 0, 0, 128, 0, 0},       /* bajo: lo de 2009 sin sombras */
    {4, 1, 0, 0, 1, 128, 1, 0},       /* medio */
    {8, 1, 0, 2, 1, 256, 1, 1},       /* alto */
    {16, 1, 1, 4, 1, 512, 1, 1},      /* máximo */
};
static int gr_aa_valido(int aa) { return aa == 0 || aa == 2 || aa == 4 || aa == 8; }
static int gr_limitar_aniso(int a)
{
    if (a < 2) return 1;
    if (!g_gr_aniso_ok) return 1;
    if (a > g_gr_aniso_max) a = g_gr_aniso_max;
    return a < 2 ? 1 : a;
}
static int gr_limitar_aa(int aa)
{
    while (aa > g_gr_aa_max) aa /= 2;
    return aa < 2 ? 0 : aa;
}
static void gr_leer_ini(const char *ini)
{
    char v[24];
    GetPrivateProfileStringA("graficos", "perfil", "alto", v, sizeof(v), ini);
    g_gr_perfil = 2;
    for (int i = 0; i < 5; i++) if (!lstrcmpiA(v, GR_PERFILES[i])) g_gr_perfil = i;
    const GR_PERFIL *p = &GR_P[g_gr_perfil < 4 ? g_gr_perfil : 2];
    g_gr_aniso = GetPrivateProfileIntA("graficos", "anisotropico", p->aniso, ini);
    g_gr_tri = GetPrivateProfileIntA("graficos", "trilineal", p->tri, ini) != 0;
    g_gr_nitidez = GetPrivateProfileIntA("graficos", "nitidez", p->nitidez, ini) != 0;
    g_gr_aa = GetPrivateProfileIntA("graficos", "antialias", p->aa, ini);
    if (!gr_aa_valido(g_gr_aa)) g_gr_aa = 0;
    g_gr_sombras_res = GetPrivateProfileIntA("graficos", "sombras_calidad", p->sombras_res, ini);
    if (g_gr_sombras_res != 256 && g_gr_sombras_res != 512) g_gr_sombras_res = 128;
    g_gr_destello = GetPrivateProfileIntA("graficos", "destello_rojo", 0, ini) != 0;
    g_gr_desligar = GetPrivateProfileIntA("graficos", "reset_desligar", 1, ini) != 0;
    g_gr_ui_clamp = GetPrivateProfileIntA("graficos", "interfaz_clamp", 1, ini) != 0;
    g_gr_letras = GetPrivateProfileIntA("graficos", "letras", 1, ini);
    if (g_gr_letras < 0 || g_gr_letras > 2) g_gr_letras = 1;
    { char v[8]; g_gr_volcar = GetEnvironmentVariableA("EDA_VOLCAR_TEXTURAS", v, sizeof v) && v[0] == '1'; }
    if (g_gr_letras && !g_gr_toutw_real) g_gr_toutw_real = (M_TOUTW)parchear_iat("GDI32.dll", "TextOutW", (void *)gr_textoutw);
    if (g_gr_letras == 1 && !g_gr_touta_real) g_gr_touta_real = (M_TOUTA)parchear_iat("GDI32.dll", "TextOutA", (void *)gr_textouta);
    if (g_gr_letras) apuntar("  (gráficos) letras %d · TextOutW %s · TextOutA %s", g_gr_letras, g_gr_toutw_real ? "enganchado" : "NO enganchado",
                             g_gr_touta_real ? "enganchado" : "NO enganchado");
    int b = GetPrivateProfileIntA("opciones", "brillo_pantalla", 100, ini);
    g_gr_brillo = b < 50 ? 50 : b > 150 ? 150 : b;
    if (GetEnvironmentVariableA("EDA_AA", v, sizeof(v))) g_gr_aa = atoi(v);          /* (para medir sin tocar el ini) */
    if (GetEnvironmentVariableA("EDA_ANISO", v, sizeof(v))) g_gr_aniso = atoi(v);
    apuntar("  (gráficos) perfil %s · anisotrópico %d · trilineal %d · nitidez %d · antialias %d · sombras %d · destello rojo %s",
            GR_PERFILES[g_gr_perfil], g_gr_aniso, g_gr_tri, g_gr_nitidez, g_gr_aa, g_gr_sombras_res,
            g_gr_destello ? "como el motor" : "QUITADO");
}
static int gr_guardar_ini(const char *ini)
{
    char v[16];
    int ok = 1;
    ok &= WritePrivateProfileStringA("graficos", "perfil", GR_PERFILES[g_gr_perfil], ini) != 0;
    wsprintfA(v, "%d", g_gr_aniso);
    ok &= WritePrivateProfileStringA("graficos", "anisotropico", v, ini) != 0;
    ok &= WritePrivateProfileStringA("graficos", "trilineal", g_gr_tri ? "1" : "0", ini) != 0;
    ok &= WritePrivateProfileStringA("graficos", "nitidez", g_gr_nitidez ? "1" : "0", ini) != 0;
    wsprintfA(v, "%d", g_gr_aa);
    ok &= WritePrivateProfileStringA("graficos", "antialias", v, ini) != 0;
    wsprintfA(v, "%d", g_gr_sombras_res);
    ok &= WritePrivateProfileStringA("graficos", "sombras_calidad", v, ini) != 0;
    return ok;
}

/* ── 1. el destello rojo: el llamado 0x6612F3 → 0x660E60 ── */
static void gr_destello_aplicar(void)
{
    static const BYTE LLAMADO[5] = {0xE8, 0x68, 0xFB, 0xFF, 0xFF};          /* call 0x660E60 */
    static const BYTE NADA[5] = {0x0F, 0x1F, 0x44, 0x00, 0x00};             /* nop (5 bytes) */
    static int ultimo = -1;
    BYTE *p = (BYTE *)(ULONG_PTR)0x006612F3;
    int quitar = !g_gr_destello;
    if (ultimo == quitar) return;
    if (!legible(p, 5)) return;
    const BYTE *esperado = quitar ? LLAMADO : NADA, *nuevo = quitar ? NADA : LLAMADO;
    if (memcmp(p, nuevo, 5) == 0) { ultimo = quitar; return; }
    if (memcmp(p, esperado, 5) != 0) {
        if (ultimo != -2) apuntar("  (gráficos) ⚠ el destello rojo NO se toca: 0x6612F3 no tiene el llamado medido");
        ultimo = -2;
        return;
    }
    DWORD prot;
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) return;
    memcpy(p, nuevo, 5);
    VirtualProtect(p, 5, prot, &prot);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    ultimo = quitar;
    apuntar("  (gráficos) destello rojo de pantalla entera (light add, 0x660E60): %s", quitar ? "QUITADO" : "como el motor");
}

/* ── 3. el filtrado, en SetSamplerState ── */
/* ★ (Punto 6) LAS RAYITAS BAJO LAS LETRAS — medido (volcado de texturas 00:35): cada letra es una textura suelta
 *   (16×16, 8×8) con la letra pegada ARRIBA a la izquierda (tinta en la fila 0 y la columna 0). El juego dibuja con
 *   las direcciones en WRAP: a 800×600 cada píxel cae justo en su texel, pero agrandado ×1,8 el borde de abajo del
 *   cuadro lee la fila 0 del otro lado (WRAP) → una raya con la parte de arriba de la letra, debajo de cada letra
 *   (y lo mismo a la derecha con la columna 0). Arreglo: mientras está puesta una letra suelta, CLAMP en U y V y
 *   filtro lineal (sin el «escalonado» del punto a ×1,8); con cualquier otra textura, lo que el juego pidió. */
static int g_gr_glifo_et[8];                  /* la etapa tiene una letra suelta (su gemelo): CLAMP + LINEAL */
static DWORD g_gr_ss_juego[8][7];             /* lo último que pidió el juego en 1 ADDRESSU, 2 ADDRESSV, 5 MAG, 6 MIN */
static BYTE g_gr_ss_sabido[8][7];
static long c_gr_glifos, c_gr_ui_clamp;
/* ★ (20-nov) LA RAYA DE «Shop|», DEBAJO DE «Inventory» → Refinery, etc. Medido en la sesión de 18:2x (diag interfaz, 96
 *   imágenes): TODAS las imágenes de la interfaz se dibujan desde la rutina 2D del motor (SetTexture vuelve a 0x0077C7C5)
 *   con borde WRAP y filtro LINEAR (las de 2×2, colores lisos, en POINT). Agrandadas ×1,8, el borde del cuadro mezcla el
 *   texel del OTRO lado de la textura (WRAP) → una línea en el borde de la imagen: la misma causa que las letras. Arreglo:
 *   sólo esa rutina, sólo con la escala activa, etapa 0, no letras: borde CLAMP; el filtro, el que pide el juego. A 800×600
 *   (sin escala) nada cambia. [graficos] interfaz_clamp=0 lo apaga. */
#define GR_UI_DESDE 0x0077C7C5u
static int gr_ui_es_imagen(void *tex, DWORD etapa, int es_glifo, DWORD desde)
{
    return g_gr_ui_clamp && tex && etapa == 0 && !es_glifo && g_e2d_es_orto && g_e2d_activa && desde == GR_UI_DESDE;
}
static long WINAPI gr_sss(void *dev, DWORD s, DWORD tipo, DWORD v);
static void gr_glifo_poner(void *dev, DWORD s, int si)
{
    if (s >= 8 || !g_gr_sss_real || si == g_gr_glifo_et[s]) return;
    if (si && g_gr_glifo_et[s]) gr_glifo_poner(dev, s, 0);         /* (de letra a imagen o al revés: primero lo del juego) */
    if (si == 2) {                                                 /* ★ (20-nov) imagen de la interfaz: sólo el borde */
        g_gr_sss_real(dev, s, 1, 3 /* CLAMP */);
        g_gr_sss_real(dev, s, 2, 3);
        g_gr_glifo_et[s] = 2;
        InterlockedIncrement(&c_gr_ui_clamp);
        return;
    }
    if (si) {
        g_gr_sss_real(dev, s, 1, 3 /* CLAMP */);
        g_gr_sss_real(dev, s, 2, 3);
        g_gr_sss_real(dev, s, 5, 2 /* LINEAR */);
        g_gr_sss_real(dev, s, 6, 2);
        g_gr_glifo_et[s] = 1;
        InterlockedIncrement(&c_gr_glifos);
        return;
    }
    g_gr_glifo_et[s] = 0;
    static const DWORD tipos[4] = {1, 2, 5, 6}, pordefecto[4] = {1 /* WRAP */, 1, 1 /* POINT */, 1};
    for (int i = 0; i < 4; i++)
        gr_sss(dev, s, tipos[i], g_gr_ss_sabido[s][tipos[i]] ? g_gr_ss_juego[s][tipos[i]] : pordefecto[i]);
}
static long WINAPI gr_sss(void *dev, DWORD s, DWORD tipo, DWORD v)
{
    if (s < 8 && (tipo == 1 || tipo == 2 || tipo == 5 || tipo == 6)) {
        g_gr_ss_juego[s][tipo] = v;
        g_gr_ss_sabido[s][tipo] = 1;
        if (g_gr_glifo_et[s] == 1) return 0;             /* (con una letra puesta queda CLAMP/LINEAL; lo pedido vuelve después) */
        if (g_gr_glifo_et[s] == 2 && (tipo == 1 || tipo == 2)) return 0;   /* (imagen: el borde queda CLAMP; el filtro, el del juego) */
    }
    int an = gr_limitar_aniso(g_gr_aniso);
    if (tipo == 6 /* MINFILTER */ && v == 2 /* LINEAR */ && an > 1) {
        long hr = g_gr_sss_real(dev, s, 6, 3 /* ANISOTROPIC */);
        g_gr_sss_real(dev, s, 10 /* MAXANISOTROPY */, (DWORD)an);
        if (g_gr_nitidez) { float b = -0.5f; DWORD d; memcpy(&d, &b, 4); g_gr_sss_real(dev, s, 8 /* MIPMAPLODBIAS */, d); }
        InterlockedIncrement(&c_gr_aniso);
        return hr;
    }
    if (tipo == 6 && g_gr_nitidez && v == 2) { float b = -0.5f; DWORD d; memcpy(&d, &b, 4); g_gr_sss_real(dev, s, 8, d); }
    if (tipo == 10 /* MAXANISOTROPY */ && an > 1 && v < (DWORD)an) v = (DWORD)an;
    if (tipo == 7 /* MIPFILTER */ && v == 1 /* POINT */ && g_gr_tri) { v = 2; InterlockedIncrement(&c_gr_tri); }
    return g_gr_sss_real(dev, s, tipo, v);
}

/* lo que la placa puede: anisotrópico (D3DCAPS9 +64 TextureFilterCaps bit 0x400, +108 MaxAnisotropy) y MSAA */
static void gr_caps(void *dev)
{
    DWORD caps[128];                      /* D3DCAPS9 = 304 B (con margen) */
    memset(caps, 0, sizeof(caps));
    if (((long (WINAPI *)(void *, void *))VT(dev)[GR_I_GETCAPS])(dev, caps) != 0) return;
    g_gr_aniso_ok = (caps[64 / 4] & 0x400) != 0;
    g_gr_aniso_max = (int)caps[108 / 4];
    if (g_gr_aniso_max < 1) g_gr_aniso_max = 1;
    if (g_gr_aniso_max > 16) g_gr_aniso_max = 16;
    if (!g_gr_caps_leidas++)
        apuntar("  (gráficos) la placa: %s · anisotrópico %s (máx %d×) · antialias máx %d×", g_gr_placa[0] ? g_gr_placa : "?",
                g_gr_aniso_ok ? "sí" : "NO", g_gr_aniso_max, g_gr_aa_max);
}
/* MSAA: el más alto ≤ lo pedido que acepten el backbuffer y la profundidad (CheckDeviceMultiSampleType, vt 11) */
static int gr_aa_soportado(void *d3d, UINT ad, DWORD fmt, DWORD prof, int ventana, int aa)
{
    typedef long (WINAPI *M_CMS)(void *, UINT, DWORD, DWORD, BOOL, DWORD, DWORD *);
    if (!d3d) return 0;
    M_CMS cms = (M_CMS)VT(d3d)[11];
    for (; aa >= 2; aa /= 2) {
        DWORD q = 0;
        if (cms(d3d, ad, 1 /* HAL */, fmt, ventana, (DWORD)aa, &q) != 0) continue;
        if (prof && cms(d3d, ad, 1, prof, ventana, (DWORD)aa, &q) != 0) continue;
        return aa;
    }
    return 0;
}
static void gr_placa(void *d3d, UINT ad)
{
    /* GetAdapterIdentifier (vt 5): Driver[512] Description[512] … → la descripción */
    static BYTE id[1200];
    if (!d3d || g_gr_placa[0]) return;
    if (((long (WINAPI *)(void *, UINT, DWORD, void *))VT(d3d)[5])(d3d, ad, 0, id) == 0) {
        lstrcpynA(g_gr_placa, (const char *)id + 512, sizeof(g_gr_placa));
    }
    /* el máximo de MSAA con el formato del escritorio (X8R8G8B8) y profundidad D24S8 */
    g_gr_aa_max = gr_aa_soportado(d3d, ad, 22 /* X8R8G8B8 */, 75 /* D24S8 */, 1, 8);
}
/* los parámetros de presentación (D3DPRESENT_PARAMETERS: [4] MultiSampleType [5] Quality [6] SwapEffect [8] Windowed
 *   [9] EnableAutoDepthStencil [10] AutoDepthStencilFormat [11] Flags) */
static void gr_ajustar_pp(void *pp)
{
    if (!pp) return;
    DWORD *p = (DWORD *)pp;
    int aa = gr_limitar_aa(g_gr_aa);
    if (aa) {
        DWORD fmt = p[2] ? p[2] : 22;
        aa = gr_aa_soportado(g_gr_d3d, g_gr_adaptador, fmt, p[9] ? p[10] : 0, (int)p[8], aa);
    }
    p[4] = (DWORD)aa;
    p[5] = 0;
    if (aa) {
        p[6] = 1;                          /* SwapEffect DISCARD (lo exige el MSAA) */
        p[11] &= ~1u;                      /* sin LOCKABLE_BACKBUFFER */
    }
    if (aa != g_gr_aa_puesto) apuntar("  (gráficos) antialias del dispositivo: %s", aa ? (aa == 2 ? "2×" : aa == 4 ? "4×" : "8×") : "no");
    g_gr_aa_puesto = aa;
}

/* ── 2. el brillo, en el Present ── */
static void *g_gr_bloque, *g_gr_bloque_dev;
static void gr_soltar(void)                 /* (antes del Reset) */
{
    if (g_gr_bloque && g_gr_bloque_dev) ((M_SB)VT(g_gr_bloque)[2])(g_gr_bloque);
    g_gr_bloque = NULL;
    g_gr_bloque_dev = NULL;
}
/* el color del cuadrado y la mezcla: k > 1 → dst·(1 + (k−1)) con DESTCOLOR / ONE; k < 1 → dst·k con ZERO / SRCCOLOR */
static void gr_brillo_mezcla(int brillo, DWORD *color, DWORD *src, DWORD *dst)
{
    int c = brillo > 100 ? (brillo - 100) * 255 / 100 : brillo * 255 / 100;
    if (c < 0) c = 0;
    if (c > 255) c = 255;
    *color = 0xFF000000u | ((DWORD)c << 16) | ((DWORD)c << 8) | (DWORD)c;
    if (brillo > 100) { *src = 9 /* DESTCOLOR */; *dst = 2 /* ONE */; }
    else { *src = 1 /* ZERO */; *dst = 3 /* SRCCOLOR */; }
}
static void gr_brillo_dibujar(void *dev)
{
    g_gr_texto_hilo = 0;                                  /* (un TextOutW sólo marca la textura de ESTE cuadro) */
    int brillo = (int)g_gr_brillo;
    if (brillo == 100 || !dev) return;
    void **vt = VT(dev);
    DWORD color, src, dst;
    gr_brillo_mezcla(brillo, &color, &src, &dst);
    float w = (float)g_e2d_w, h = (float)g_e2d_h;
    struct { float x, y, z, rhw; DWORD c; } q[4] = {
        {-0.5f, -0.5f, 0, 1, color}, {w - 0.5f, -0.5f, 0, 1, color}, {-0.5f, h - 0.5f, 0, 1, color}, {w - 0.5f, h - 0.5f, 0, 1, color}};
    if (g_gr_bloque && g_gr_bloque_dev != dev) g_gr_bloque = NULL;   /* (de otro dispositivo: ni tocarlo) */
    if (!g_gr_bloque && ((M_CSB)vt[I_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_gr_bloque) != 0) g_gr_bloque = NULL;
    g_gr_bloque_dev = dev;
    if (!g_gr_bloque) return;
    ((M_SB)VT(g_gr_bloque)[4])(g_gr_bloque);                        /* Capture */
    InterlockedExchange(&g_e2d_propio, 1);
    ((M_SIN)vt[I_BEGINSCENE])(dev);
    DWORD vp[6] = {0, 0, (DWORD)g_e2d_w, (DWORD)g_e2d_h, 0, 0};
    float uno = 1.0f;
    memcpy(&vp[5], &uno, 4);
    ((long (WINAPI *)(void *, const void *))vt[47])(dev, vp);        /* el viewport: el backbuffer entero */
    ((M_UNO)vt[I_SETVS])(dev, NULL);
    ((M_UNO)vt[I_SETPS])(dev, NULL);
    ((M_PTR)vt[I_SETTEXTURE])(dev, 0, NULL);
    ((long (WINAPI *)(void *, DWORD))vt[I_SETFVF])(dev, 0x044);                            /* XYZRHW | DIFFUSE */
    const DWORD estados[][2] = {{7, 0} /* ZENABLE */, {14, 0} /* ZWRITE */, {15, 0} /* ALPHATEST */,
        {27, 1} /* ALPHABLEND */, {19, src} /* SRCBLEND */, {20, dst} /* DESTBLEND */, {171, 1} /* BLENDOP ADD */,
        {206, 0} /* SEPARATEALPHA */, {22, 1} /* CULL NONE */, {137, 0} /* LIGHTING */, {28, 0} /* FOG */,
        {52, 0} /* STENCIL */, {174, 0} /* SCISSOR */, {168, 0x7} /* COLORWRITE RGB */, {8, 3} /* SOLID */,
        {161, 0} /* MULTISAMPLEANTIALIAS: el cuadrado entero, sin bordes */};
    for (unsigned i = 0; i < sizeof(estados) / sizeof(estados[0]); i++)
        ((M_RS)vt[I_SETRS])(dev, estados[i][0], estados[i][1]);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 1, 2);        /* COLOROP = SELECTARG1 */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 2, 0);        /* COLORARG1 = DIFFUSE */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 4, 2);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 5, 0);
    ((M_TSS)vt[I_SETTSS])(dev, 1, 1, 1);        /* etapa 1: DISABLE */
    ((M_DPUP)vt[I_DPUP])(dev, 5 /* TRIANGLESTRIP */, 2, q, sizeof(q[0]));
    ((M_SIN)vt[I_ENDSCENE])(dev);
    ((M_SB)VT(g_gr_bloque)[5])(g_gr_bloque);                        /* Apply: todo como estaba */
    InterlockedExchange(&g_e2d_propio, 0);
}

/* ── (diag, Punto 6) LA DISTORSIÓN DE LA ESPADA A 1920: quién crea texturas que se dibujan (render targets), quién
 *   copia la pantalla (StretchRect: la «foto» del cuadro que usan las refracciones, 0x45D070 SnapshotCurrentFrame) y
 *   con qué tamaños. Sólo mira y anota (con EDA_DIAGNOSTICO / [general] diagnostico=1). */
typedef long (WINAPI *M_CTEX)(void *, UINT, UINT, UINT, DWORD, DWORD, DWORD, void **, void *);
typedef long (WINAPI *M_STRETCH)(void *, void *, const RECT *, void *, const RECT *, DWORD);
static M_CTEX g_gr_ctex_real;
static M_STRETCH g_gr_stretch_real;
static int g_gr_diag_rt;
static DWORD g_gr_sr_dir[24];
static int g_gr_sr_n;
static void gr_desc(void *sup, int *w, int *h, DWORD *ms)
{
    DWORD d[8] = {0};
    *w = *h = 0;
    *ms = 0;
    if (sup && ((long (WINAPI *)(void *, void *))VT(sup)[12])(sup, d) == 0) { *w = (int)d[6]; *h = (int)d[7]; *ms = d[4]; }
}

/* ★ (24-nov) LAS FRANJAS CON «AMBIENTE» ([pantalla] ambiente=1, prendido; 0 = negras como antes). Con la adaptación 2D,
 *   en una pantalla más ancha que 4:3 la interfaz de 800×600 queda centrada (R) y a los costados quedaban franjas negras
 *   (pedido del dueño: «esos bordes negros están feos»). Estirar la interfaz la deformaría; acá, al final del cuadro (en el
 *   Present, fuera de una escena), la zona R se achica por pasos a la mitad (StretchRect lineal: un desenfoque barato en la
 *   placa), se estira otra vez SÓLO sobre las franjas como «cubrir pantalla» (el color sigue al centro) y se oscurece un
 *   poco. No toca lo que dibuja el juego. Fuera del Stage 3D (lobby, sala, menús, resultados); en el Stage el 3D ya llena
 *   la pantalla. Superficies del pool DEFAULT: se sueltan antes de cada Reset (gr_ambiente_soltar, mi_reset). Si algo
 *   falla, las franjas quedan negras (como antes) y se anota una vez. */
typedef long (WINAPI *M_CRT)(void *, UINT, UINT, DWORD, DWORD, DWORD, BOOL, void **, void *);
#define GR_AMB_N 8
static void *g_amb_dev, *g_amb_full, *g_amb_niv[GR_AMB_N];
static int g_amb_nw[GR_AMB_N], g_amb_nh[GR_AMB_N], g_amb_n, g_amb_mal, g_amb_bw, g_amb_bh, g_amb_rw;
static DWORD g_amb_fmt;
static volatile LONG c_amb;
static void gr_ambiente_soltar(void)
{
    for (int i = 0; i < g_amb_n; i++)
        if (g_amb_niv[i]) ((M_SB)VT(g_amb_niv[i])[2])(g_amb_niv[i]);
    if (g_amb_full) ((M_SB)VT(g_amb_full)[2])(g_amb_full);
    memset(g_amb_niv, 0, sizeof(g_amb_niv));
    g_amb_full = NULL;
    g_amb_n = 0;
    g_amb_dev = NULL;
}
static long gr_sr(void *dev, void *s, const RECT *a, void *d, const RECT *b, DWORD filtro)
{
    M_STRETCH sr = g_gr_stretch_real ? g_gr_stretch_real : (M_STRETCH)VT(dev)[34];
    return sr(dev, s, a, d, b, filtro);
}
/* las franjas, un poco más oscuras que el centro (cuadrados negros con alfa, como el brillo) */
static void gr_oscurecer(void *dev, const RECT *r, int n, DWORD alfa)
{
    void **vt = VT(dev);
    if (g_gr_bloque && g_gr_bloque_dev != dev) g_gr_bloque = NULL;
    if (!g_gr_bloque && ((M_CSB)vt[I_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_gr_bloque) != 0) g_gr_bloque = NULL;
    g_gr_bloque_dev = dev;
    if (!g_gr_bloque || n <= 0) return;
    ((M_SB)VT(g_gr_bloque)[4])(g_gr_bloque);                        /* Capture */
    InterlockedExchange(&g_e2d_propio, 1);
    ((M_SIN)vt[I_BEGINSCENE])(dev);
    DWORD vp[6] = {0, 0, (DWORD)g_amb_bw, (DWORD)g_amb_bh, 0, 0};
    float uno = 1.0f;
    memcpy(&vp[5], &uno, 4);
    ((long (WINAPI *)(void *, const void *))vt[47])(dev, vp);
    ((M_UNO)vt[I_SETVS])(dev, NULL);
    ((M_UNO)vt[I_SETPS])(dev, NULL);
    ((M_PTR)vt[I_SETTEXTURE])(dev, 0, NULL);
    ((long (WINAPI *)(void *, DWORD))vt[I_SETFVF])(dev, 0x044);                            /* XYZRHW | DIFFUSE */
    const DWORD estados[][2] = {{7, 0}, {14, 0}, {15, 0}, {27, 1} /* ALPHABLEND */, {19, 5} /* SRCALPHA */,
        {20, 6} /* INVSRCALPHA */, {171, 1}, {206, 0}, {22, 1}, {137, 0}, {28, 0}, {52, 0}, {174, 0}, {168, 0x7}, {8, 3},
        {161, 0}};
    for (unsigned i = 0; i < sizeof(estados) / sizeof(estados[0]); i++)
        ((M_RS)vt[I_SETRS])(dev, estados[i][0], estados[i][1]);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 1, 2);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 2, 0);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 4, 2);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 5, 0);
    ((M_TSS)vt[I_SETTSS])(dev, 1, 1, 1);
    DWORD color = alfa << 24;
    for (int k = 0; k < n; k++) {
        float x0 = (float)r[k].left - 0.5f, y0 = (float)r[k].top - 0.5f, x1 = (float)r[k].right - 0.5f, y1 = (float)r[k].bottom - 0.5f;
        struct { float x, y, z, rhw; DWORD c; } q[4] = {{x0, y0, 0, 1, color}, {x1, y0, 0, 1, color}, {x0, y1, 0, 1, color},
                                                         {x1, y1, 0, 1, color}};
        ((M_DPUP)vt[I_DPUP])(dev, 5 /* TRIANGLESTRIP */, 2, q, sizeof(q[0]));
    }
    ((M_SIN)vt[I_ENDSCENE])(dev);
    ((M_SB)VT(g_gr_bloque)[5])(g_gr_bloque);                        /* Apply */
    InterlockedExchange(&g_e2d_propio, 0);
}
/* qué parte de la imagen chica (tw×th, la interfaz R entera achicada) va en la franja b de una pantalla W×H, como «cubrir
 *   pantalla»: la interfaz agrandada c = max(W/rw, H/rh) y centrada. Devuelve el rectángulo (al menos 1×1, dentro). */
static void gr_amb_fuente(const RECT *b, int W, int H, int rw, int rh, int tw, int th, RECT *s)
{
    float c = (float)W / rw > (float)H / rh ? (float)W / rw : (float)H / rh;
    float u0 = 0.5f + (b->left - W / 2.0f) / (rw * c), u1 = 0.5f + (b->right - W / 2.0f) / (rw * c);
    float v0 = 0.5f + (b->top - H / 2.0f) / (rh * c), v1 = 0.5f + (b->bottom - H / 2.0f) / (rh * c);
    s->left = (LONG)(u0 * tw);
    s->top = (LONG)(v0 * th);
    s->right = (LONG)(u1 * tw + 0.999f);
    s->bottom = (LONG)(v1 * th + 0.999f);
    if (s->left < 0) s->left = 0;
    if (s->top < 0) s->top = 0;
    if (s->right > tw) s->right = tw;
    if (s->bottom > th) s->bottom = th;
    if (s->right <= s->left) { if (s->left + 1 <= tw) s->right = s->left + 1; else s->left = s->right - 1; }
    if (s->bottom <= s->top) { if (s->top + 1 <= th) s->bottom = s->top + 1; else s->top = s->bottom - 1; }
}
static void gr_ambiente(void *dev)
{
    if (!g_e2d_ambiente || g_amb_mal || !dev || !g_e2d_activa) return;
    if (g_e2d_stage_ahora && !g_e2d_res_fase) return;            /* (jugando: el 3D llena la pantalla) */
    int rw = (int)(800 * g_e2d_s + 0.5f), rh = (int)(600 * g_e2d_s + 0.5f);
    LONG x0 = (LONG)(g_e2d_rx + 0.5f), y0 = (LONG)(g_e2d_ry + 0.5f), x1 = x0 + rw, y1 = y0 + rh;
    if (x0 < 2 && y0 < 2) return;                                /* (4:3: no hay franjas) */
    void **vt = VT(dev);
    void *bb = NULL;
    if (((long (WINAPI *)(void *, UINT, UINT, UINT, void **))vt[18])(dev, 0, 0, 0, &bb) != 0 || !bb) return;
    DWORD d[8] = {0};
    ((long (WINAPI *)(void *, DWORD *))VT(bb)[12])(bb, d);
    int W = (int)d[6], H = (int)d[7];
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;
    if (dev != g_amb_dev || d[0] != g_amb_fmt || W != g_amb_bw || H != g_amb_bh || rw != g_amb_rw || !g_amb_n) {
        gr_ambiente_soltar();
        g_amb_dev = dev;
        g_amb_fmt = d[0];
        g_amb_bw = W;
        g_amb_bh = H;
        g_amb_rw = rw;
        M_CRT crt = (M_CRT)vt[28];                               /* CreateRenderTarget */
        int ok = !d[4] || crt(dev, (UINT)W, (UINT)H, d[0], 0, 0, FALSE, &g_amb_full, NULL) == 0;
        int w = rw / 2, h = rh / 2;
        while (ok && g_amb_n < GR_AMB_N && w >= 24 && h >= 16) {
            ok = crt(dev, (UINT)w, (UINT)h, d[0], 0, 0, FALSE, &g_amb_niv[g_amb_n], NULL) == 0;
            if (ok) { g_amb_nw[g_amb_n] = w; g_amb_nh[g_amb_n] = h; g_amb_n++; }
            w /= 2;
            h /= 2;
        }
        if (!ok || !g_amb_n) {
            g_amb_mal = 1;
            apuntar("  (pantalla) ⚠ franjas con ambiente: no se pudieron crear las superficies (formato %lu, msaa %lu): quedan negras",
                    (unsigned long)d[0], (unsigned long)d[4]);
            gr_ambiente_soltar();
            ((M_SB)VT(bb)[2])(bb);
            return;
        }
        apuntar("  (pantalla) franjas con ambiente: %d×%d, interfaz %d×%d en x %ld · y %ld, %d niveles hasta %d×%d%s", W, H, rw, rh,
                (long)x0, (long)y0, g_amb_n, g_amb_nw[g_amb_n - 1], g_amb_nh[g_amb_n - 1], d[4] ? " (con antialias: pasa por una copia)" : "");
    }
    long hr = 0;
    void *src = bb;
    if (g_amb_full) { hr = gr_sr(dev, bb, NULL, g_amb_full, NULL, 0 /* NONE */); src = g_amb_full; }
    RECT rr = {x0, y0, x1, y1};
    if (!hr) hr = gr_sr(dev, src, &rr, g_amb_niv[0], NULL, 2 /* LINEAR */);
    for (int i = 1; !hr && i < g_amb_n; i++) hr = gr_sr(dev, g_amb_niv[i - 1], NULL, g_amb_niv[i], NULL, 2);
    void *t = g_amb_niv[g_amb_n - 1];
    RECT b[4] = {{0, 0, x0, H}, {x1, 0, W, H}, {x0, 0, x1, y0}, {x0, y1, x1, H}}, usar[4];
    int n = 0;
    for (int k = 0; k < 4 && !hr; k++) {
        if (b[k].right <= b[k].left || b[k].bottom <= b[k].top) continue;
        RECT s;
        gr_amb_fuente(&b[k], W, H, rw, rh, g_amb_nw[g_amb_n - 1], g_amb_nh[g_amb_n - 1], &s);
        hr = gr_sr(dev, t, &s, bb, &b[k], 2);
        usar[n++] = b[k];
    }
    if (hr) {
        g_amb_mal = 1;
        apuntar("  (pantalla) ⚠ franjas con ambiente: StretchRect → 0x%08lx: quedan negras", (unsigned long)hr);
    } else {
        gr_oscurecer(dev, usar, n, 0x70);                     /* (44 %: el centro resalta y los costados conservan su color) */
        InterlockedIncrement(&c_amb);
    }
    ((M_SB)VT(bb)[2])(bb);
}
static long WINAPI gr_ctex(void *dev, UINT w, UINT h, UINT niv, DWORD uso, DWORD fmt, DWORD pool, void **t, void *c)
{
    long hr = g_gr_ctex_real(dev, w, h, niv, uso, fmt, pool, t, c);
    if (hr == 0 && t && *t && !(uso & 1)) gr_tx_nueva(*t, fmt, pool);
    if ((uso & 1 /* RENDERTARGET */) && hr == 0 && t && *t && g_gr_rt_tex_n < 16) g_gr_rt_tex[g_gr_rt_tex_n++] = *t;
    if ((uso & 1 /* RENDERTARGET */) && g_gr_diag_rt < 40) {
        g_gr_diag_rt++;
        apuntar("  (diag gráficos) textura RENDER TARGET %u×%u · formato %lu · niveles %u · backbuffer %d×%d · pide 0x%08lX → 0x%08lx",
                w, h, (unsigned long)fmt, niv, g_e2d_w, g_e2d_h, (unsigned long)(ULONG_PTR)__builtin_return_address(0),
                (unsigned long)hr);
    }
    return hr;
}
static long WINAPI gr_stretch(void *dev, void *src, const RECT *rs, void *dst, const RECT *rd, DWORD filtro)
{
    DWORD dir = (DWORD)(ULONG_PTR)__builtin_return_address(0);
    int nuevo = 1;
    for (int i = 0; i < g_gr_sr_n; i++) if (g_gr_sr_dir[i] == dir) nuevo = 0;
    long hr = g_gr_stretch_real(dev, src, rs, dst, rd, filtro);
    if (nuevo && g_gr_sr_n < 24) {
        int sw, sh, dw, dh;
        DWORD sms, dms;
        g_gr_sr_dir[g_gr_sr_n++] = dir;
        gr_desc(src, &sw, &sh, &sms);
        gr_desc(dst, &dw, &dh, &dms);
        apuntar("  (diag gráficos) StretchRect desde 0x%08lX: %d×%d (msaa %lu)%s → %d×%d%s · filtro %lu · → 0x%08lx", (unsigned long)dir,
                sw, sh, (unsigned long)sms, rs ? " (una parte)" : "", dw, dh, rd ? " (una parte)" : "", (unsigned long)filtro,
                (unsigned long)hr);
    }
    return hr;
}

/* ══ ★ (Punto 6, 20-nov) LAS LETRAS: un «gemelo» al doble de resolución de cada textura de fuente ══
 *  Medido en el exe (CUIVectorFont::CreateFontTextureAndTable, 0x735FA0–0x736720): cada letra se dibuja con GDI
 *  (TextOutA / GetGlyphOutlineA) y se copia a una textura A4R4G4B4 —16 niveles de transparencia, color blanco 0x0FFF—
 *  con 2 px entre letras; la interfaz la muestra a 800×600 y la escala 2D la agranda ×1,8 a 1080. Con sólo 16 niveles
 *  y el filtro bilineal agrandando, el borde sale en «escalones» (pixelado) y los niveles más bajos (1/15) quedan como
 *  rayitas sueltas. Arreglo LOCALIZADO, sin tocar posiciones ni coordenadas: la primera vez que el juego usa una textura
 *  A4R4G4B4 cuyo color es TODO blanco (= un atlas de letras), la dll arma otra A8R8G8B8 al doble de tamaño (Catmull-Rom
 *  sobre la transparencia, sin el ruido de 1/15 y con el borde un poco más firme) y, en SetTexture, pone ésa en su
 *  lugar. Las coordenadas UV son relativas: cada letra cae en el mismo lugar. Nada más cambia (ni filtros ni otras
 *  texturas). [graficos] letras=0 lo apaga. */
typedef long (WINAPI *M_SETTEX)(void *, DWORD, void *);
static M_SETTEX g_gr_settex_real;
#define GR_FUENTES 2048                       /* (atlas, o una textura por letra: CreateGlyphTexture 0x4A720D) */
#define GR_HASH 8192                              /* (las texturas ya miradas: puntero → gemelo o nada) */
static struct { void *orig, *gemelo; int w, h; } g_gr_fu[GR_FUENTES];
static int g_gr_fu_n;
static struct { void *tex, *gemelo; int glifo; } g_gr_h[GR_HASH];
static int g_gr_h_n;
static int gr_h_lugar(void *tex)
{
    DWORD k = ((DWORD)(ULONG_PTR)tex >> 4) * 2654435761u;
    int i = (int)(k >> 20) & (GR_HASH - 1);
    while (g_gr_h[i].tex && g_gr_h[i].tex != tex) i = (i + 1) & (GR_HASH - 1);
    return i;
}
static long c_gr_letras;
static int g_gr_vf_n;                 /* atlas de fuentes del motor ya dibujados al doble (letras=1) */
/* los 4 pesos de Catmull-Rom para t ∈ [0,1) */
static void gr_cr(float t, float *w)
{
    float t2 = t * t, t3 = t2 * t;
    w[0] = -0.5f * t3 + t2 - 0.5f * t;
    w[1] = 1.5f * t3 - 2.5f * t2 + 1.0f;
    w[2] = -1.5f * t3 + 2.0f * t2 + 0.5f * t;
    w[3] = 0.5f * t3 - 0.5f * t2;
}
/* la transparencia de un atlas A4 (w×h, 0..15) → 2w×2h, 0..255: interpolada, sin el ruido de 1/15, borde algo más firme */
static float g_gr_contraste = 1.2f;
static int g_gr_escala_max = 15;         /* (los valores de entrada: 0..15 o 0..255) */      /* (borde: 1,2 los gemelos de prueba · 1,35 las letras sueltas) */
static void gr_letras_escalar(const BYTE *a4, int w, int h, BYTE *a8)
{
    for (int Y = 0; Y < 2 * h; Y++) {
        float sy = (Y + 0.5f) / 2.0f - 0.5f;
        int y0 = (int)(sy < 0 ? sy - 1 : sy);
        float wy[4];
        gr_cr(sy - (float)y0, wy);
        for (int X = 0; X < 2 * w; X++) {
            float sx = (X + 0.5f) / 2.0f - 0.5f;
            int x0 = (int)(sx < 0 ? sx - 1 : sx);
            float wx[4], v = 0;
            gr_cr(sx - (float)x0, wx);
            for (int j = 0; j < 4; j++) {
                int yy = y0 - 1 + j;
                if (yy < 0) yy = 0;
                if (yy >= h) yy = h - 1;
                float fila = 0;
                for (int i = 0; i < 4; i++) {
                    int xx = x0 - 1 + i;
                    if (xx < 0) xx = 0;
                    if (xx >= w) xx = w - 1;
                    int s = a4[yy * w + xx];
                    fila += wx[i] * (float)(s * 15 <= g_gr_escala_max ? 0 : s);   /* (1/15: el ruido de las rayitas) */
                }
                v += wy[j] * fila;
            }
            v /= (float)g_gr_escala_max;
            v = (v - 0.5f) * g_gr_contraste + 0.5f;                    /* borde algo más firme, el trazo igual */
            if (v < 0.03f) v = 0;
            if (v > 1) v = 1;
            a8[Y * 2 * w + X] = (BYTE)(v * 255.0f + 0.5f);
        }
    }
}
/* ¿es un atlas de letras? 1 nivel, se puede leer, color TODO blanco, con algo transparente y algo no. Formatos que
 *   sabe leer: A4R4G4B4 (26), A8R8G8B8 (21), A8 (28), A8L8 (51) → la transparencia en 0..255 */
static int gr_alfa_de(DWORD fmt, const BYTE *f, int x, int *blanco)
{
    switch (fmt) {
    case 26: { WORD p = ((const WORD *)f)[x]; *blanco = (p & 0x0FFF) == 0x0FFF; return (p >> 12) * 17; }
    case 21: { DWORD p = ((const DWORD *)f)[x]; *blanco = (p & 0xFFFFFF) == 0xFFFFFF; return (int)(p >> 24); }
    case 28: *blanco = 1; return f[x];
    case 51: { WORD p = ((const WORD *)f)[x]; *blanco = (p & 0xFF) == 0xFF; return p >> 8; }
    }
    *blanco = 0;
    return 0;
}
static void *gr_letras_gemelo(void *dev, void *tex)
{
    int lugar = gr_h_lugar(tex);
    if (g_gr_h[lugar].tex) return g_gr_h[lugar].gemelo;
    if (g_gr_h_n >= GR_HASH * 3 / 4 || g_gr_fu_n >= GR_FUENTES) return NULL;
    void **vt = VT(tex);
    DWORD d[8] = {0}, tipo = 0, niveles = 0;
    int letras = 0, con = 0, sin = 0, blancos = 0, leida = 0, glifo_final = 0;
    BYTE *a8f = NULL;                                              /* (la transparencia entera 0..255, para las letras sueltas) */
    const char *por = "";
    tipo = ((DWORD (WINAPI *)(void *))vt[10])(tex);
    if (tipo == 3) niveles = ((DWORD (WINAPI *)(void *))vt[13])(tex);
    int desc = tipo == 3 && ((long (WINAPI *)(void *, UINT, void *))vt[17])(tex, 0, d) == 0;
    int fmt_ok = d[0] == 26 || d[0] == 21 || d[0] == 28 || d[0] == 51;
    if (tipo != 3) por = "no es 2D";
    else if (!desc) por = "sin descripción";
    else if (!fmt_ok) por = "formato";
    else if (d[3] == 0) por = "pool DEFAULT (no se puede leer)";
    else if (d[6] < 4 || d[7] < 4 || d[6] > 2048 || d[7] > 2048) por = "tamaño";
    else {
        int w = (int)d[6], h = (int)d[7];
        DWORD lr[2] = {0, 0};                                        /* D3DLOCKED_RECT: Pitch, pBits */
        BYTE *a8s = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h);
        a8f = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h);
        if (a8s && a8f && ((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))vt[19])(tex, 0, lr, NULL, 0x10 /* READONLY */) == 0) {
            leida = 1;
            blancos = 1;
            for (int y = 0; y < h && blancos; y++) {
                const BYTE *f = (const BYTE *)(ULONG_PTR)lr[1] + (SIZE_T)y * lr[0];
                for (int x = 0; x < w; x++) {
                    int b, a = gr_alfa_de(d[0], f, x, &b);
                    if (!b && a) { blancos = 0; break; }             /* (color ≠ blanco donde hay tinta) */
                    a8s[y * w + x] = (BYTE)((a * 15 + 127) / 255);  /* (a 0..15: lo que usa el escalado) */
                    a8f[y * w + x] = (BYTE)a;
                    if (a > 8) con++; else sin++;
                }
            }
            ((long (WINAPI *)(void *, UINT))vt[20])(tex, 0);
        } else por = "no se pudo leer";
        letras = leida && blancos && con >= 2 && sin >= 2;
        if (leida && !letras) por = !blancos ? "tiene color" : "sin tinta o lleno";
        const BYTE *redibujada = letras && g_gr_letras == 1 ? gr_vf_buscar(a8s, w, h) : NULL;
        int glifo = letras && g_gr_letras == 1 && !redibujada && w <= 64 && h <= 64;   /* ★ una letra suelta (16×16, 8×8…) */
        if (letras && g_gr_letras == 1 && !redibujada && !glifo) { letras = 0; por = "ni letra suelta ni atlas medido"; }
        glifo_final = glifo;
        if (letras) {
            void *g = NULL;
            g_gr_creando = 1;
            long hrg = ((long (WINAPI *)(void *, UINT, UINT, UINT, DWORD, DWORD, DWORD, void **, void *))VT(dev)[23])(
                    dev, (UINT)(2 * w), (UINT)(2 * h), 1, 0, 21 /* A8R8G8B8 */, 1 /* MANAGED */, &g, NULL);
            g_gr_creando = 0;
            if (hrg == 0 && g) {
                BYTE *a8 = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)4 * w * h);
                DWORD lg[2] = {0, 0};
                if (a8 && ((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))VT(g)[19])(g, 0, lg, NULL, 0) == 0) {
                    if (redibujada) memcpy(a8, redibujada, (SIZE_T)4 * w * h);   /* (letras=1: dibujadas al doble con GDI) */
                    else if (glifo) { g_gr_contraste = 1.35f; g_gr_escala_max = 255; gr_letras_escalar(a8f, w, h, a8); g_gr_contraste = 1.2f; g_gr_escala_max = 15; }
                    else gr_letras_escalar(a8s, w, h, a8);
                    for (int y = 0; y < 2 * h; y++) {
                        DWORD *f = (DWORD *)((BYTE *)(ULONG_PTR)lg[1] + (SIZE_T)y * lg[0]);
                        for (int x = 0; x < 2 * w; x++) f[x] = ((DWORD)a8[y * 2 * w + x] << 24) | 0x00FFFFFFu;
                    }
                    ((long (WINAPI *)(void *, UINT))VT(g)[20])(g, 0);
                    ((ULONG (WINAPI *)(void *))vt[1])(tex);               /* (la original queda fija: no se reusa su dirección) */
                    g_gr_fu[g_gr_fu_n].orig = tex;
                    g_gr_fu[g_gr_fu_n].gemelo = g;
                    g_gr_fu[g_gr_fu_n].w = w;
                    g_gr_fu[g_gr_fu_n].h = h;
                    g_gr_fu_n++;
                    if (g_gr_fu_n <= 12 || (g_gr_fu_n & 127) == 0)
                        apuntar("  (gráficos) letras: nº %d · %d×%d formato %lu → gemelo %d×%d A8R8G8B8 (%d con tinta) · %s", g_gr_fu_n, w, h,
                                (unsigned long)d[0], 2 * w, 2 * h, con, redibujada ? "redibujado con la fuente al doble" : "agrandado");
                } else {
                    ((ULONG (WINAPI *)(void *))VT(g)[2])(g);
                    letras = 0;
                    por = "no se pudo escribir el gemelo";
                }
                if (a8) HeapFree(GetProcessHeap(), 0, a8);
            } else { letras = 0; por = "no se pudo crear el gemelo"; }
        }
        if (a8s) HeapFree(GetProcessHeap(), 0, a8s);
        if (a8f) HeapFree(GetProcessHeap(), 0, a8f);
    }
    if (!letras && g_diagnostico && fmt_ok) {                      /* (diag: por qué no, una vez por formato/pool/motivo) */
        static int n;
        if (n < 60) {
            n++;
            apuntar("  (diag gráficos) letras: textura %lu×%lu formato %lu pool %lu niveles %lu: no (%s · %d con tinta, %d sin)",
                    d[6], d[7], (unsigned long)d[0], (unsigned long)d[3], (unsigned long)niveles, por, con, sin);
        }
    }
    g_gr_h[lugar].tex = tex;
    g_gr_h[lugar].gemelo = letras ? g_gr_fu[g_gr_fu_n - 1].gemelo : NULL;
    g_gr_h[lugar].glifo = letras && glifo_final;
    g_gr_h_n++;
    return g_gr_h[lugar].gemelo;
}
/* ══ ★ (Punto 6) LOS TEXTOS DE COLOR (login, avisos, listas): otro camino del juego (0x4A6xxx) dibuja cada texto con
 *  TextOutW YA CON SU COLOR en un DIB del tamaño de 800×600 y lo sube a una textura A8R8G8B8 (pool MANAGED); la escala 2D
 *  la agranda ×1,8. Una textura trae también el borde de la línea vecina: con el bilineal agrandando, el borde de abajo
 *  toma un poco de la otra línea → las «rayitas» bajo las letras. El gemelo al doble (Catmull-Rom con alfa premultiplicado
 *  y transparencia más firme) achica ese contagio a la mitad y lo que queda, muy tenue, desaparece con el umbral.
 *  Cuáles son: las texturas que el juego crea JUSTO después de un TextOutW suyo (en el mismo hilo y cuadro). Si el juego
 *  vuelve a escribir esa textura (UnlockRect) el gemelo se rehace; si la suelta (Release → 0), el gemelo se suelta. ══ */
#define GR_TX 1024
static struct { void *tex, *gemelo; int sucio; } g_gr_tx[GR_TX];
static int g_gr_tx_n;
static long c_gr_textos;
typedef ULONG (WINAPI *M_TREL)(void *);
typedef long (WINAPI *M_TUNLOCK)(void *, UINT);
static M_TREL g_gr_trel_real;
static M_TUNLOCK g_gr_tunlock_real;
static void gr_atlas_enganchar(void);
static void extern_contar_toutw(void);
static BOOL WINAPI gr_textoutw(HDC dc, int x, int y, LPCWSTR t, int n)
{
    if (g_gr_letras == 1) gr_atlas_enganchar();          /* (el atlas se arma con TextOutW justo antes de crearse) */
    extern_contar_toutw();
    g_gr_texto_hilo = GetCurrentThreadId();
    return g_gr_toutw_real(dc, x, y, t, n);
}
static int gr_tx_buscar(void *tex)
{
    for (int i = 0; i < g_gr_tx_n; i++) if (g_gr_tx[i].tex == tex) return i;
    return -1;
}
static ULONG WINAPI gr_tx_release(void *t)
{
    ULONG r = g_gr_trel_real(t);
    if (r == 0 && g_gr_tx_n) {
        int i = gr_tx_buscar(t);
        if (i >= 0) {
            void *g = g_gr_tx[i].gemelo;
            g_gr_tx[i] = g_gr_tx[--g_gr_tx_n];
            if (g) g_gr_trel_real(g);
        }
    }
    return r;
}
static long WINAPI gr_tx_unlock(void *t, UINT nivel)
{
    long r = g_gr_tunlock_real(t, nivel);
    if (nivel == 0 && g_gr_tx_n) {
        int i = gr_tx_buscar(t);
        if (i >= 0) g_gr_tx[i].sucio = 1;
    }
    return r;
}
/* una textura de texto (A8R8G8B8 o A4R4G4B4) → otra al doble A8R8G8B8; NULL si no se pudo */
static void gr_tx_escalar(const BYTE *rgba, int w, int h, BYTE *sal)
{
    for (int Y = 0; Y < 2 * h; Y++) {
        float sy = (Y + 0.5f) / 2.0f - 0.5f;
        int y0 = (int)(sy < 0 ? sy - 1 : sy);
        float wy[4];
        gr_cr(sy - (float)y0, wy);
        for (int X = 0; X < 2 * w; X++) {
            float sx = (X + 0.5f) / 2.0f - 0.5f;
            int x0 = (int)(sx < 0 ? sx - 1 : sx);
            float wx[4], acc[4] = {0, 0, 0, 0};
            gr_cr(sx - (float)x0, wx);
            for (int j = 0; j < 4; j++) {
                int yy = y0 - 1 + j;
                if (yy < 0) yy = 0;
                if (yy >= h) yy = h - 1;
                for (int i = 0; i < 4; i++) {
                    int xx = x0 - 1 + i;
                    if (xx < 0) xx = 0;
                    if (xx >= w) xx = w - 1;
                    const BYTE *p = rgba + ((SIZE_T)yy * w + xx) * 4;      /* B G R A */
                    float k = wx[i] * wy[j], a = p[3] / 255.0f;
                    acc[0] += k * p[0] * a; acc[1] += k * p[1] * a; acc[2] += k * p[2] * a; acc[3] += k * a;
                }
            }
            float a = acc[3];
            BYTE *q = sal + ((SIZE_T)Y * 2 * w + X) * 4;
            float af = (a - 0.5f) * 1.2f + 0.5f;
            if (a < 0.06f || af < 0.04f) af = 0;
            if (af > 1) af = 1;
            for (int c = 0; c < 3; c++) {
                float v = a > 0.004f ? acc[c] / a : 0;
                q[c] = (BYTE)(v < 0 ? 0 : v > 255 ? 255 : v + 0.5f);
            }
            q[3] = (BYTE)(af * 255.0f + 0.5f);
        }
    }
}
static void *gr_tx_gemelo(void *dev, void *tex)
{
    void **vt = VT(tex);
    DWORD d[8] = {0};
    if (((long (WINAPI *)(void *, UINT, void *))vt[17])(tex, 0, d) != 0 || (d[0] != 21 && d[0] != 26) || d[3] == 0
        || d[6] < 4 || d[7] < 4 || d[6] > 1024 || d[7] > 1024) return NULL;
    int w = (int)d[6], h = (int)d[7];
    BYTE *rgba = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4);
    BYTE *sal = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 16);
    void *g = NULL;
    DWORD lr[2] = {0, 0}, lg[2] = {0, 0};
    if (rgba && sal && ((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))vt[19])(tex, 0, lr, NULL, 0x10) == 0) {
        for (int y = 0; y < h; y++) {
            const BYTE *f = (const BYTE *)(ULONG_PTR)lr[1] + (SIZE_T)y * lr[0];
            for (int x = 0; x < w; x++) {
                BYTE *q = rgba + ((SIZE_T)y * w + x) * 4;
                if (d[0] == 21) memcpy(q, f + x * 4, 4);
                else {
                    WORD p = ((const WORD *)f)[x];
                    q[0] = (BYTE)((p & 0xF) * 17); q[1] = (BYTE)(((p >> 4) & 0xF) * 17);
                    q[2] = (BYTE)(((p >> 8) & 0xF) * 17); q[3] = (BYTE)((p >> 12) * 17);
                }
            }
        }
        g_gr_tunlock_real ? g_gr_tunlock_real(tex, 0) : ((long (WINAPI *)(void *, UINT))vt[20])(tex, 0);
        gr_tx_escalar(rgba, w, h, sal);
        g_gr_creando = 1;
        long hr = ((long (WINAPI *)(void *, UINT, UINT, UINT, DWORD, DWORD, DWORD, void **, void *))VT(dev)[23])(
            dev, (UINT)(2 * w), (UINT)(2 * h), 1, 0, 21, 1 /* MANAGED */, &g, NULL);
        g_gr_creando = 0;
        if (hr == 0 && g && ((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))VT(g)[19])(g, 0, lg, NULL, 0) == 0) {
            for (int y = 0; y < 2 * h; y++)
                memcpy((BYTE *)(ULONG_PTR)lg[1] + (SIZE_T)y * lg[0], sal + (SIZE_T)y * 2 * w * 4, (SIZE_T)2 * w * 4);
            g_gr_tunlock_real ? g_gr_tunlock_real(g, 0) : ((long (WINAPI *)(void *, UINT))VT(g)[20])(g, 0);
        } else if (g) {
            (g_gr_trel_real ? g_gr_trel_real : (M_TREL)VT(g)[2])(g);
            g = NULL;
        }
    }
    if (rgba) HeapFree(GetProcessHeap(), 0, rgba);
    if (sal) HeapFree(GetProcessHeap(), 0, sal);
    return g;
}
/* (en SetTexture) si es un texto: su gemelo, rehecho si el juego lo cambió */
static void *gr_tx_usar(void *dev, void *tex)
{
    int i = gr_tx_buscar(tex);
    if (i < 0) return NULL;
    if (!g_gr_tx[i].gemelo || g_gr_tx[i].sucio) {
        if (g_gr_tx[i].gemelo) { (g_gr_trel_real ? g_gr_trel_real : (M_TREL)VT(g_gr_tx[i].gemelo)[2])(g_gr_tx[i].gemelo); g_gr_tx[i].gemelo = NULL; }
        g_gr_tx[i].gemelo = gr_tx_gemelo(dev, tex);
        g_gr_tx[i].sucio = 0;
        if (g_gr_tx[i].gemelo && c_gr_textos++ < 6) {
            DWORD d[8] = {0};
            ((long (WINAPI *)(void *, UINT, void *))VT(tex)[17])(tex, 0, d);
            apuntar("  (gráficos) textos: %lu×%lu formato %lu → gemelo %lu×%lu (los %d textos del juego, al doble)", d[6], d[7],
                    (unsigned long)d[0], d[6] * 2, d[7] * 2, g_gr_tx_n);
        }
    }
    return g_gr_tx[i].gemelo;
}
/* (en CreateTexture) ¿la crea el texto que se acaba de dibujar? */
static void gr_tx_nueva(void *tex, DWORD fmt, DWORD pool)
{
    if (g_gr_creando || g_gr_letras != 2 || !tex) return;
    if (g_gr_texto_hilo != GetCurrentThreadId()) return;
    g_gr_texto_hilo = 0;
    if ((fmt != 21 && fmt != 26) || pool != 1 || g_gr_tx_n >= GR_TX) return;
    if (!g_gr_trel_real) {                                     /* (la tabla de las texturas: Release y UnlockRect) */
        poner(VT(tex), 2, (void *)gr_tx_release, (void **)&g_gr_trel_real);
        poner(VT(tex), 20, (void *)gr_tx_unlock, (void **)&g_gr_tunlock_real);
    }
    g_gr_tx[g_gr_tx_n].tex = tex;
    g_gr_tx[g_gr_tx_n].gemelo = NULL;
    g_gr_tx[g_gr_tx_n].sucio = 1;
    g_gr_tx_n++;
}
/* (al crear otro dispositivo: los gemelos y las originales fijadas se sueltan; lo mirado se olvida) */
static void gr_letras_soltar(void)
{
    for (int i = 0; i < g_gr_fu_n; i++) {
        if (g_gr_fu[i].gemelo) ((ULONG (WINAPI *)(void *))VT(g_gr_fu[i].gemelo)[2])(g_gr_fu[i].gemelo);
        if (g_gr_fu[i].orig) ((ULONG (WINAPI *)(void *))VT(g_gr_fu[i].orig)[2])(g_gr_fu[i].orig);
    }
    g_gr_fu_n = 0;
    for (int i = 0; i < g_gr_tx_n; i++)
        if (g_gr_tx[i].gemelo) (g_gr_trel_real ? g_gr_trel_real : (M_TREL)VT(g_gr_tx[i].gemelo)[2])(g_gr_tx[i].gemelo);
    g_gr_tx_n = 0;
    memset(g_gr_glifo_et, 0, sizeof(g_gr_glifo_et));          /* (dispositivo nuevo: sus estados son los de fábrica) */
    memset(g_gr_ss_sabido, 0, sizeof(g_gr_ss_sabido));
    memset(g_gr_h, 0, sizeof(g_gr_h));
    g_gr_h_n = 0;
}
/* (diag) las texturas que se dibujan (render targets): quién las usa, una vez por lugar */
static long c_gr_rt_usada;
/* (medir, EDA_VOLCAR_TEXTURAS=1) ★ qué texturas dibuja la INTERFAZ: hasta 120 distintas (≥32 px) se guardan como .tga al lado del registro, con
 *   tamaño, formato y quién las pone (para saber de dónde salen las letras: GDI, FreeType o un .fnt de HGE) */
static void gr_diag_volcar(void *tex, DWORD dir)
{
    static void *vistas[400];
    static int n, guardadas;
    for (int i = 0; i < n; i++) if (vistas[i] == tex) return;
    if (n >= 400 || guardadas >= 120) return;
    vistas[n++] = tex;
    void **vt = VT(tex);
    DWORD d[8] = {0};
    if (((DWORD (WINAPI *)(void *))vt[10])(tex) != 3 || ((long (WINAPI *)(void *, UINT, void *))vt[17])(tex, 0, d) != 0) return;
    if (d[6] < 32 && d[7] < 32) return;                    /* (los iconitos no: las letras van en algo más grande) */
    guardadas++;
    DWORD niveles = ((DWORD (WINAPI *)(void *))vt[13])(tex);
    int w = (int)d[6], h = (int)d[7];
    apuntar("  (diag gráficos) interfaz: textura nº %d %d×%d formato %lu pool %lu niveles %lu · desde 0x%08lX", n, w, h,
            (unsigned long)d[0], (unsigned long)d[3], (unsigned long)niveles, (unsigned long)dir);
    if (d[3] == 0 || w > 1024 || h > 1024 || (d[0] != 21 && d[0] != 26 && d[0] != 22 && d[0] != 28)) return;
    DWORD lr[2] = {0, 0};
    if (((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))vt[19])(tex, 0, lr, NULL, 0x10) != 0) return;
    char ruta[MAX_PATH];
    lstrcpynA(ruta, g_log, MAX_PATH - 40);
    char *b = ruta + lstrlenA(ruta);
    while (b > ruta && b[-1] != '\\' && b[-1] != '/') b--;
    wsprintfA(b, "eda_tex_%02d_%dx%d_f%lu.tga", n, w, h, (unsigned long)d[0]);
    FILE *f = fopen(ruta, "wb");
    if (f) {
        BYTE cab[18] = {0, 0, 2};
        cab[12] = (BYTE)w; cab[13] = (BYTE)(w >> 8); cab[14] = (BYTE)h; cab[15] = (BYTE)(h >> 8); cab[16] = 32; cab[17] = 0x28;
        fwrite(cab, 1, 18, f);
        for (int y = 0; y < h; y++) {
            const BYTE *fi = (const BYTE *)(ULONG_PTR)lr[1] + (SIZE_T)y * lr[0];
            for (int x = 0; x < w; x++) {
                BYTE px[4];
                if (d[0] == 21 || d[0] == 22) { memcpy(px, fi + x * 4, 4); if (d[0] == 22) px[3] = 255; }
                else if (d[0] == 26) { WORD v = ((const WORD *)fi)[x]; px[0] = (BYTE)((v & 15) * 17); px[1] = (BYTE)(((v >> 4) & 15) * 17); px[2] = (BYTE)(((v >> 8) & 15) * 17); px[3] = (BYTE)((v >> 12) * 17); }
                else { px[0] = px[1] = px[2] = 255; px[3] = fi[x]; }
                fwrite(px, 1, 4, f);
            }
        }
        fclose(f);
    }
    ((long (WINAPI *)(void *, UINT))vt[20])(tex, 0);
}
static long WINAPI gr_settex(void *dev, DWORD etapa, void *tex)
{
    if (tex && g_gr_volcar && g_e2d_es_orto) gr_diag_volcar(tex, (DWORD)(ULONG_PTR)__builtin_return_address(0));
    if (tex && g_gr_letras == 2 && g_gr_tx_n) {
        void *g = gr_tx_usar(dev, tex);
        if (g) { InterlockedIncrement(&c_gr_letras); return g_gr_settex_real(dev, etapa, g); }
    }
    int es_glifo = 0;
    if (tex && g_gr_letras) {
        /* (sólo se DECIDE con la interfaz dibujándose —proyección ortográfica—, nunca en la escena 3D: una partícula
         *   blanca con transparencia no se confunde con letras; lo ya decidido vale siempre) */
        int lugar = gr_h_lugar(tex);
        void *g = g_gr_h[lugar].tex ? g_gr_h[lugar].gemelo : g_e2d_es_orto ? gr_letras_gemelo(dev, tex) : NULL;
        if (g && g_gr_letras == 1 && !g_e2d_activa) g = NULL;            /* (a 800×600 el original: el gemelo achicado se vería peor) */
        if (g) { InterlockedIncrement(&c_gr_letras); tex = g; es_glifo = g_gr_h[lugar].glifo; }
    }
    if (g_gr_sss_real && (g_gr_letras == 1 || g_gr_ui_clamp)) {
        int modo = g_gr_letras == 1 && es_glifo ? 1
                 : gr_ui_es_imagen(tex, etapa, es_glifo, (DWORD)(ULONG_PTR)__builtin_return_address(0)) ? 2 : 0;
        gr_glifo_poner(dev, etapa, modo);
    }
    /* ★ (20-nov) MEDICIÓN para los textos pixelados y la raya de «Shop|» (imágenes de 800×600 agrandadas ×1,8): cada
     *   imagen de la interfaz (ortográfica, escala activa, etapa 0, no letra) UNA vez: tamaño, formato, pool y lo que el
     *   juego pidió de borde (WRAP/CLAMP) y filtro (POINT/LINEAR). Con eso se decide un arreglo que no toque mosaicos. */
    if (tex && etapa == 0 && !es_glifo && g_e2d_es_orto && g_e2d_activa && g_diagnostico) {
        static void *vistas[96];
        static int nv;
        int ya = 0;
        for (int i = 0; i < nv; i++) if (vistas[i] == tex) ya = 1;
        if (!ya && nv < 96) {
            DWORD d[8] = {0};
            vistas[nv++] = tex;
            if (((DWORD (WINAPI *)(void *))VT(tex)[10])(tex) == 3 && ((long (WINAPI *)(void *, UINT, DWORD *))VT(tex)[17])(tex, 0, d) == 0) {
                static const char *dir[6] = {"?", "WRAP", "MIRROR", "CLAMP", "BORDER", "MIRRORONCE"}, *fil[4] = {"NONE", "POINT", "LINEAR", "ANISO"};
                DWORD u = g_gr_ss_sabido[0][1] ? g_gr_ss_juego[0][1] : 1, v = g_gr_ss_sabido[0][2] ? g_gr_ss_juego[0][2] : 1;
                DWORD ma = g_gr_ss_sabido[0][5] ? g_gr_ss_juego[0][5] : 1, mi = g_gr_ss_sabido[0][6] ? g_gr_ss_juego[0][6] : 1;
                apuntar("  (diag interfaz) imagen nº %d %lux%lu formato %lu pool %lu · el juego pide borde %s/%s · filtro mag %s min %s · desde 0x%08lX",
                        nv, d[6], d[7], d[0], d[3], dir[u < 6 ? u : 0], dir[v < 6 ? v : 0], fil[ma < 4 ? ma : 0], fil[mi < 4 ? mi : 0],
                        (unsigned long)(ULONG_PTR)__builtin_return_address(0));
            }
        }
    }
    if (tex && g_gr_rt_tex_n && g_diagnostico) {
        for (int i = 0; i < g_gr_rt_tex_n; i++)
            if (g_gr_rt_tex[i] == tex) {
                InterlockedIncrement(&c_gr_rt_usada);
                static DWORD vistos[16];
                static int n;
                DWORD dir = (DWORD)(ULONG_PTR)__builtin_return_address(0);
                int ya = 0;
                for (int k = 0; k < n; k++) if (vistos[k] == dir) ya = 1;
                if (!ya && n < 16) {
                    DWORD vp[6] = {0};
                    vistos[n++] = dir;
                    ((long (WINAPI *)(void *, DWORD *))VT(dev)[48])(dev, vp);
                    apuntar("  (diag gráficos) la textura-render-target nº %d se USA (etapa %lu) desde 0x%08lX · destino %s · viewport (%lu,%lu) %lu×%lu · backbuffer %d×%d · escala %s",
                            i, (unsigned long)etapa, (unsigned long)dir, g_e2d_rt_fuera ? "otra textura" : "la pantalla", vp[0], vp[1], vp[2], vp[3],
                            g_e2d_w, g_e2d_h, g_e2d_activa ? "activa" : "×1");
                }
                break;
            }
    }
    return g_gr_settex_real(dev, etapa, tex);
}

/* ★ (20-nov) LA CAUSA DEL CIERRE AL CAMBIAR LA RESOLUCIÓN DESPUÉS DE UN STAGE. Direct3D9 no borra un recurso del pool
 *   DEFAULT mientras siga PUESTO en el dispositivo (SetTexture, SetStreamSource, SetIndices, SetRenderTarget,
 *   SetDepthStencilSurface), aunque su dueño ya lo haya soltado: queda vivo y el Reset da D3DERR_INVALIDCALL
 *   (lo mismo comprueban las pruebas de Wine contra Windows: «DEFAULT pool resources bound but otherwise not
 *   referenced» → Reset INVALIDCALL). El motor tiene una caché de texturas por etapa ([0x939128 + etapa·8], 0x6C9EC1):
 *   un efecto que usó otra etapa (o un render target, p. ej. el de Capítulos al entrar al Stage, medido 01:20:55 y
 *   01:30:59) queda puesto al volver al lobby. Reset igual deja todo sin poner: hacerlo JUSTO ANTES es lo mismo para el
 *   motor (no cambia lo que dibuja) y deja que esos recursos se borren. Devuelve cuántos del pool DEFAULT estaban puestos
 *   y deja en «diag» cuáles. sss_real / rt_real: los de verdad de SetStreamSource / SetRenderTarget (NULL = la tabla).
 *   Revisado (20-nov): (1) la caché del motor ([0x939128]) sólo se escribe en 0x6C9E60 / 0x6C9F10 / 0x6CB3E0, nunca en un
 *   Reset: después de CUALQUIER Reset queda vieja igual (el Reset saca todo); sacarlo antes deja el mismo estado.
 *   (2) Sólo se sueltan las referencias que se piden aquí (Get* → Release): ninguna del juego. (3) Lo que el juego sigue
 *   teniendo (un Get* sin Release, un render target suyo, un state block) no se toca: el Reset falla y se anota. */
typedef long (WINAPI *GR_M_GET2)(void *, DWORD, void **);
typedef long (WINAPI *GR_M_SET2)(void *, DWORD, void *);
static int gr_desc_pool(void *r, int idx_desc, int nivel, DWORD *d)      /* (desc de textura/búfer/superficie: d[3] = pool) */
{
    memset(d, 0, 8 * sizeof(DWORD));
    if (nivel) return ((long (WINAPI *)(void *, UINT, DWORD *))VT(r)[idx_desc])(r, 0, d) == 0;
    return ((long (WINAPI *)(void *, DWORD *))VT(r)[idx_desc])(r, d) == 0;
}
static int gr_reset_desligar(void *dev, void *sss_real, void *rt_real, char *diag, int tam)
{
    void **vt = VT(dev);
    int def = 0, k = 0;
    DWORD d[8];
    if (diag && tam) diag[0] = 0;
#define GR_ANOTAR(...) do { if (diag && k < tam - 48) k += wsprintfA(diag + k, __VA_ARGS__); } while (0)
    /* texturas: etapas 0..15, el mapa de desplazamiento (256) y las 4 de vértices (257..260) */
    GR_M_SET2 settex = g_gr_settex_real ? (GR_M_SET2)g_gr_settex_real : (GR_M_SET2)vt[65];
    for (DWORD i = 0; i < 21; i++) {
        DWORD s = i < 16 ? i : 256 + (i - 16);
        void *t = NULL;
        if (((GR_M_GET2)vt[64])(dev, s, &t) != 0 || !t) continue;
        DWORD tipo = ((DWORD (WINAPI *)(void *))VT(t)[10])(t);              /* 3 textura · 4 volumen · 5 cubo */
        if ((tipo == 3 || tipo == 4 || tipo == 5) && gr_desc_pool(t, 17, 1, d) && d[3] == 0) {
            def++;
            GR_ANOTAR(" textura etapa %lu %lux%lu uso 0x%lX;", (unsigned long)s, d[4 + (tipo == 4 ? 0 : 2)], d[5 + (tipo == 4 ? 0 : 2)], d[2]);
        }
        ((ULONG (WINAPI *)(void *))VT(t)[2])(t);
        settex(dev, s, NULL);
    }
    /* búferes de vértices */
    for (UINT i = 0; i < 16; i++) {
        void *vb = NULL;
        UINT desde = 0, paso = 0;
        if (((long (WINAPI *)(void *, UINT, void **, UINT *, UINT *))vt[101])(dev, i, &vb, &desde, &paso) != 0 || !vb) continue;
        if (gr_desc_pool(vb, 13, 0, d) && d[3] == 0) { def++; GR_ANOTAR(" vértices stream %u %lu B;", i, d[4]); }
        ((ULONG (WINAPI *)(void *))VT(vb)[2])(vb);
        ((long (WINAPI *)(void *, UINT, void *, UINT, UINT))(sss_real ? sss_real : vt[100]))(dev, i, NULL, 0, 0);
    }
    /* índices */
    {
        void *ib = NULL;
        if (((long (WINAPI *)(void *, void **))vt[105])(dev, &ib) == 0 && ib) {
            if (gr_desc_pool(ib, 13, 0, d) && d[3] == 0) { def++; GR_ANOTAR(" índices %lu B;", d[4]); }
            ((ULONG (WINAPI *)(void *))VT(ib)[2])(ib);
            ((long (WINAPI *)(void *, void *))vt[104])(dev, NULL);
        }
    }
    /* destinos: 1..3 sin nada; el 0 otra vez el backbuffer (si quedó una textura) */
    GR_M_SET2 setrt = rt_real ? (GR_M_SET2)rt_real : (GR_M_SET2)vt[37];
    for (DWORD i = 1; i < 4; i++) {
        void *sup = NULL;
        if (((GR_M_GET2)vt[38])(dev, i, &sup) != 0 || !sup) continue;
        if (gr_desc_pool(sup, 12, 0, d)) { def++; GR_ANOTAR(" destino %lu %lux%lu;", (unsigned long)i, d[6], d[7]); }
        ((ULONG (WINAPI *)(void *))VT(sup)[2])(sup);
        setrt(dev, i, NULL);
    }
    {
        void *rt0 = NULL, *bb = NULL;
        ((GR_M_GET2)vt[38])(dev, 0, &rt0);
        ((long (WINAPI *)(void *, UINT, UINT, DWORD, void **))vt[18])(dev, 0, 0, 0, &bb);
        if (rt0 && bb && rt0 != bb) {
            if (gr_desc_pool(rt0, 12, 0, d)) { def++; GR_ANOTAR(" destino 0 era una textura %lux%lu;", d[6], d[7]); }
            setrt(dev, 0, bb);
        }
        if (rt0) ((ULONG (WINAPI *)(void *))VT(rt0)[2])(rt0);
        if (bb) ((ULONG (WINAPI *)(void *))VT(bb)[2])(bb);
    }
    /* profundidad: el Reset vuelve a poner la automática */
    {
        void *ds = NULL;
        if (((long (WINAPI *)(void *, void **))vt[40])(dev, &ds) == 0 && ds) {
            if (gr_desc_pool(ds, 12, 0, d)) GR_ANOTAR(" profundidad %lux%lu;", d[6], d[7]);
            ((ULONG (WINAPI *)(void *))VT(ds)[2])(ds);
            ((long (WINAPI *)(void *, void *))vt[39])(dev, NULL);
        }
    }
#undef GR_ANOTAR
    for (int i = 0; i < 8; i++) g_gr_glifo_et[i] = 0;           /* (sin letra puesta en ninguna etapa) */
    return def;
}

static void gr_diag_enganchar(void **vt)
{
    if (vt && !g_gr_settex_real && (g_gr_letras || g_diagnostico)) poner(vt, 65 /* SetTexture */, (void *)gr_settex, (void **)&g_gr_settex_real);
    if (vt && !g_gr_ctex_real && (g_gr_letras || g_diagnostico)) poner(vt, 23 /* CreateTexture */, (void *)gr_ctex, (void **)&g_gr_ctex_real);
    if (!g_diagnostico || !vt || g_gr_stretch_real) return;
    poner(vt, 34 /* StretchRect */, (void *)gr_stretch, (void **)&g_gr_stretch_real);
    apuntar("  (diag gráficos) mirando CreateTexture (render targets) y StretchRect");
}

/* ── al crear el dispositivo / en el Present ── */
static void gr_dispositivo(void **vt, void *dev)
{
    if (!vt) return;
    gr_letras_soltar();                                      /* (los gemelos eran del dispositivo anterior) */
    gr_diag_enganchar(vt);
    gr_caps(dev);
    poner(vt, GR_I_SETSAMPLER, (void *)gr_sss, (void **)&g_gr_sss_real);
    gr_destello_aplicar();
}
static void gr_reafirmar(void **vt, int (*reafirmar_fn)(void **, int, void *, void **, const char *))
{
    if (g_gr_sss_real) reafirmar_fn(vt, GR_I_SETSAMPLER, (void *)gr_sss, (void **)&g_gr_sss_real, "SetSamplerState");
    /* ★ (Punto 6) también los del diag y las letras: tras el primer ataque otro programa devuelve la tabla entera a la
     *   original (medido 23:21:55 y 23:38:24) y el diag se quedaba mudo justo en el combate */
    if (g_gr_settex_real) reafirmar_fn(vt, 65, (void *)gr_settex, (void **)&g_gr_settex_real, "SetTexture");
    if (g_gr_ctex_real) reafirmar_fn(vt, 23, (void *)gr_ctex, (void **)&g_gr_ctex_real, "CreateTexture");
    if (g_gr_stretch_real) reafirmar_fn(vt, 34, (void *)gr_stretch, (void **)&g_gr_stretch_real, "StretchRect");
}
/* ── ★ (Punto 6) LAS LETRAS DEL JUEGO AL DOBLE ─────────────────────────────────────────────────────────
 * Medido (registro 00:16, capturas antes/después iguales): el texto del juego (avisos, lista de servers, títulos)
 * NO son texturas sueltas: el exe arma UN ATLAS por fuente (0x4A6FA0): por cada letra TextOutW(dc, −L, −T, &c, 1)
 * en un DIB, la copia a un búfer ARGB4444 (relleno 0x0FFF, 2 px entre letras) y guarda su caja (L,T,R,B en
 * píxeles) y sus UV normalizadas; al final ILTTexInterface::CreateTextureFromData(&h, 2, 0x82, datos, W, H, 1)
 * (0x4A71FB, interfaz en 0x933044). Las letras se rasterizan al tamaño de 800×600 y escala2d las estira ×1,8 con
 * filtro bilineal: borrosas/pixeladas, y el filtro alcanza la letra de la fila de abajo (las rayitas).
 * Arreglo: en ESA llamada (sólo desde 0x4A71FE) se vuelve a dibujar cada letra con la MISMA fuente al doble de
 * alto, en el mismo lugar ×2 de un atlas 2W×2H. Las cajas y las UV del juego no cambian (UV normalizadas: valen
 * igual), así que las posiciones y los tamaños en pantalla son idénticos; sólo hay el doble de detalle.
 * La caja de cada letra se recorta exacta (nada se sale al vecino) y queda 4 px de margen. */
#define GR_AT_RET 0x004A71FEu
#define GR_AT_IFACE 0x00933044u
typedef long (__fastcall *M_CTFD)(void *self, void *edx, void **h, DWORD tipo, DWORD flags, BYTE *datos, DWORD w, DWORD hh, DWORD mips);
static M_CTFD g_gr_ctfd_real;
static void **g_gr_ctfd_vt;
static long c_gr_atlas, c_gr_atlas_letras;
static int g_gr_atlas_aviso;
/* el búfer 2W×2H con las letras redibujadas (NULL = no se pudo: se usa el del juego) */
static WORD *gr_atlas_doble(HDC dc, const BYTE *tabla, DWORD n, DWORD w, DWORD h)
{
    if (!dc || !tabla || !n || n > 4096 || w < 8 || h < 8 || w > 1024 || h > 1024) return NULL;
    HFONT fo = (HFONT)GetCurrentObject(dc, OBJ_FONT);
    LOGFONTW lf;
    if (!fo || GetObjectW(fo, sizeof lf, &lf) != sizeof lf) return NULL;
    int altomax = 0, anchomax = 0;
    for (DWORD i = 0; i < n; i++) {
        const int *c = (const int *)(tabla + i * 0x28 + 4);
        if (c[2] - c[0] > anchomax) anchomax = c[2] - c[0];
        if (c[3] - c[1] > altomax) altomax = c[3] - c[1];
    }
    if (anchomax <= 0 || altomax <= 0 || anchomax > 512 || altomax > 512) return NULL;
    lf.lfHeight *= 2;
    lf.lfWidth *= 2;
    if (lf.lfQuality == 5 /* CLEARTYPE */ || lf.lfQuality == 6) lf.lfQuality = 4; /* ANTIALIASED: gris, sin color */
    HFONT f2 = CreateFontIndirectW(&lf);
    HDC d2 = CreateCompatibleDC(dc);
    int dw = anchomax * 2 + 8, dh = altomax * 2 + 8;
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = dw;
    bi.bmiHeader.biHeight = -dh;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP bm = d2 ? CreateDIBSection(d2, &bi, 0, &bits, NULL, 0) : NULL;
    WORD *out = (WORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4 * 2);
    if (!f2 || !d2 || !bm || !bits || !out) {
        if (out) HeapFree(GetProcessHeap(), 0, out);
        if (bm) DeleteObject(bm);
        if (d2) DeleteDC(d2);
        if (f2) DeleteObject(f2);
        return NULL;
    }
    DWORD W = w * 2, H = h * 2;
    for (DWORD i = 0; i < W * H; i++) out[i] = 0x0FFF;
    HGDIOBJ vb = SelectObject(d2, bm), vf = SelectObject(d2, f2);
    SetTextAlign(d2, GetTextAlign(dc));
    SetTextColor(d2, RGB(255, 255, 255));
    SetBkMode(d2, TRANSPARENT);
    for (DWORD i = 0; i < n; i++) {
        const BYTE *e = tabla + i * 0x28;
        WCHAR ch = *(const WCHAR *)e;
        const int *c = (const int *)(e + 4);
        const float *uv = (const float *)(e + 0x18);
        int gw = c[2] - c[0], gh = c[3] - c[1];
        if (gw <= 0 || gh <= 0) continue;
        int x0 = (int)(uv[0] * (float)w - 0.5f + 0.5f), y0 = (int)(uv[1] * (float)h - 0.5f + 0.5f);   /* (UV = (x+0,5)/W) */
        if (x0 < 0 || y0 < 0 || x0 + gw > (int)w || y0 + gh > (int)h) continue;
        memset(bits, 0, (SIZE_T)dw * dh * 4);
        TextOutW(d2, -2 * c[0], -2 * c[1], &ch, 1);
        GdiFlush();
        for (int y = 0; y < gh * 2; y++) {
            const BYTE *f = (const BYTE *)bits + (SIZE_T)y * dw * 4;
            WORD *o = out + (SIZE_T)(y0 * 2 + y) * W + x0 * 2;
            for (int x = 0; x < gw * 2; x++) {
                int a = f[x * 4];
                if (f[x * 4 + 1] > a) a = f[x * 4 + 1];
                if (f[x * 4 + 2] > a) a = f[x * 4 + 2];
                o[x] = (WORD)((((a * 15 + 127) / 255) << 12) | 0x0FFF);
            }
        }
        c_gr_atlas_letras++;
    }
    SelectObject(d2, vf);
    SelectObject(d2, vb);
    DeleteObject(bm);
    DeleteDC(d2);
    DeleteObject(f2);
    return out;
}
/* ── las fuentes del MOTOR (CUIVectorFont, 0x735FA0): los textos de la interfaz que se ven (avisos, listas, títulos) ──
 * Medido (registro 00:25 con efa1181: el atlas del exe 0x4A6FA0 nunca se arma en el login): el texto visible sale de
 * CUIVectorFont::CreateFontTextureAndTable: TextOutA letra por letra (0x7363FA) en un DIB, copia a un búfer ARGB4444
 * (0x0FFF, 2 px entre letras) y CreateTextureFromData(&this->tex, 2, 0x82, datos, W, H, 1) (0x736683, interfaz 0x947428).
 * El motor calcula las UV con las cajas en PÍXELES del atlas, así que el atlas no puede cambiar de tamaño: se le deja el
 * suyo y se dibuja aparte el mismo atlas al doble (cada letra con la misma fuente ×2 en su lugar ×2). Cuando esa textura
 * llega a SetTexture en la interfaz (mismo tamaño y mismas letras, comparadas píxel a píxel) se pone el gemelo 2W×2H:
 * en D3D las UV son normalizadas, así que cada letra cae exacta en su versión nítida. */
#define GR_VF_RET 0x00736686u
#define GR_VF_IFACE 0x00947428u
#define GR_VF 64
static struct { int w, h; BYTE *a4, *a8; } g_gr_vf[GR_VF];
static HDC g_gr_touta_dc;                  /* (el DC del último TextOutA: el del atlas que se está armando) */
static long c_gr_touta, c_gr_toutw;
static void extern_contar_toutw(void) { c_gr_toutw++; }
static BOOL WINAPI gr_textouta(HDC dc, int x, int y, const char *t, int n)
{
    c_gr_touta++;
    g_gr_touta_dc = dc;
    gr_atlas_enganchar();
    return g_gr_touta_real(dc, x, y, t, n);
}
static const BYTE *gr_vf_buscar(const BYTE *a4, int w, int h)
{
    for (int i = 0; i < g_gr_vf_n; i++)
        if (g_gr_vf[i].w == w && g_gr_vf[i].h == h && !memcmp(g_gr_vf[i].a4, a4, (size_t)w * h)) return g_gr_vf[i].a8;
    return NULL;
}
/* (pura: el atlas 2W×2H de transparencias 0..255; marco = la pila del motor en 0x73665B; NULL si algo no cuadra) */
static BYTE *gr_vf_doble(HDC dc, const BYTE *marco, const WORD *tabla, int w, int h)
{
    int n = *(const int *)(marco + 0x18), alto = *(const int *)(marco + 0x50);
    const BYTE *letras = *(const BYTE *const *)(marco + 0x16CC);
    const int *gm = (const int *)(marco + 0x2C4);                  /* GLYPHMETRICS de cada letra (0x14 B) */
    if (!dc || !tabla || !letras || n <= 0 || n > 256 || alto <= 0 || alto > 256 || w < 8 || h < 8 || w > 1024 || h > 1024) return NULL;
    HFONT fo = (HFONT)GetCurrentObject(dc, OBJ_FONT);
    LOGFONTW lf;
    if (!fo || GetObjectW(fo, sizeof lf, &lf) != sizeof lf) return NULL;
    lf.lfHeight *= 2;
    lf.lfWidth *= 2;
    if (lf.lfQuality == 5 || lf.lfQuality == 6) lf.lfQuality = 4;
    int anchomax = 0;
    for (int i = 0; i < n; i++) if (tabla[i * 3] > anchomax) anchomax = tabla[i * 3];
    if (anchomax <= 0 || anchomax > 512) return NULL;
    HFONT f2 = CreateFontIndirectW(&lf);
    HDC d2 = CreateCompatibleDC(dc);
    int dw = anchomax * 2 + 8, dh = alto * 2 + 8;
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = dw;
    bi.bmiHeader.biHeight = -dh;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP bm = d2 ? CreateDIBSection(d2, &bi, 0, &bits, NULL, 0) : NULL;
    BYTE *out = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4);
    if (!f2 || !d2 || !bm || !bits || !out) {
        if (out) HeapFree(GetProcessHeap(), 0, out);
        if (bm) DeleteObject(bm);
        if (d2) DeleteDC(d2);
        if (f2) DeleteObject(f2);
        return NULL;
    }
    memset(out, 0, (SIZE_T)w * h * 4);
    HGDIOBJ vb = SelectObject(d2, bm), vf = SelectObject(d2, f2);
    SetTextAlign(d2, 0);                                   /* (TA_TOP: como lo cuenta el motor) */
    SetTextColor(d2, RGB(255, 255, 255));
    SetBkMode(d2, TRANSPARENT);
    TEXTMETRICW tm2;
    int asc1 = *(const int *)(marco + 0x5C), asc2 = GetTextMetricsW(d2, &tm2) ? tm2.tmAscent : 2 * asc1;
    int W = 2 * w, hechas = 0;
    for (int i = 0; i < n; i++) {
        int cw = tabla[i * 3] - 1, cx = tabla[i * 3 + 1], cy = tabla[i * 3 + 2];   /* (ancho+2 en la tabla: 1 px de aire) */
        const int *g = gm + i * 5;
        if (cw <= 0 || cx + cw > w || cy + alto > h) continue;
        char c = (char)letras[i];
        memset(bits, 0, (SIZE_T)dw * dh * 4);
        /* (el motor copia la caja negra con su línea de base en «ascent» de la celda: acá, la celda entera al doble,
         *   con la línea de base en 2×ascent y la caja empezando en x = 0) */
        TextOutA(d2, -2 * g[2], 2 * asc1 - asc2, &c, 1);
        GdiFlush();
        for (int y = 0; y < 2 * alto; y++) {
            const BYTE *f = (const BYTE *)bits + (SIZE_T)y * dw * 4;
            BYTE *o = out + (SIZE_T)(2 * cy + y) * W + 2 * cx;
            for (int x = 0; x < 2 * cw; x++) {
                int a = f[x * 4];
                if (f[x * 4 + 1] > a) a = f[x * 4 + 1];
                if (f[x * 4 + 2] > a) a = f[x * 4 + 2];
                o[x] = (BYTE)a;
            }
        }
        hechas++;
    }
    SelectObject(d2, vf);
    SelectObject(d2, vb);
    DeleteObject(bm);
    DeleteDC(d2);
    DeleteObject(f2);
    c_gr_atlas_letras += hechas;
    if (!hechas) { HeapFree(GetProcessHeap(), 0, out); return NULL; }
    return out;
}
static void gr_vf_registrar(HDC dc, const BYTE *marco, const WORD *tabla, const WORD *datos, int w, int h)
{
    if (g_gr_vf_n >= GR_VF || !datos) return;
    BYTE *a8 = gr_vf_doble(dc, marco, tabla, w, h);
    BYTE *a4 = a8 ? (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h) : NULL;
    if (!a4) {
        if (a8) HeapFree(GetProcessHeap(), 0, a8);
        if (g_gr_atlas_aviso++ < 12) apuntar("  (gráficos) letras: fuente del motor %d×%d: no se pudo redibujar (queda la del juego)", w, h);
        return;
    }
    for (int i = 0; i < w * h; i++) a4[i] = (BYTE)(datos[i] >> 12);
    g_gr_vf[g_gr_vf_n].w = w;
    g_gr_vf[g_gr_vf_n].h = h;
    g_gr_vf[g_gr_vf_n].a4 = a4;
    g_gr_vf[g_gr_vf_n].a8 = a8;
    g_gr_vf_n++;
    InterlockedIncrement(&c_gr_atlas);
    if (g_gr_atlas_aviso++ < 12)
        apuntar("  (gráficos) letras: fuente del motor nº %d (%d×%d, %d letras, alto %d) dibujada al doble → %d×%d", g_gr_vf_n, w, h,
                *(const int *)(marco + 0x18), *(const int *)(marco + 0x50), 2 * w, 2 * h);
}
static long __fastcall gr_ctfd(void *self, void *edx, void **h, DWORD tipo, DWORD flags, BYTE *datos, DWORD w, DWORD hh, DWORD mips)
{
    /* (los argumentos están en la pila del juego, en su lugar: justo debajo de h, la vuelta; encima de mips, el marco del exe) */
    DWORD vuelta = *(DWORD *)((BYTE *)&h - 4);
    if (vuelta == GR_AT_RET && tipo == 2 && g_gr_letras == 1 && g_e2d_activa) {
        const BYTE *marco = (const BYTE *)&mips + 4;           /* = esp del exe antes de los 7 push (0x4A71FB) */
        const BYTE *tabla = *(const BYTE *const *)(marco + 0x4C);
        DWORD n = *(const DWORD *)(marco + 0x50);
        HDC dc = *(const HDC *)(marco + 0x54);
        WORD *doble = NULL;
        doble = gr_atlas_doble(dc, tabla, n, w, hh);
        if (doble) {
            long r = g_gr_ctfd_real(self, edx, h, tipo, flags, (BYTE *)doble, w * 2, hh * 2, mips);
            HeapFree(GetProcessHeap(), 0, doble);
            InterlockedIncrement(&c_gr_atlas);
            if (g_gr_atlas_aviso++ < 12)
                apuntar("  (gráficos) letras: atlas del juego %lu×%lu (%lu letras) dibujado al doble → %lu×%lu", w, hh, n, w * 2, hh * 2);
            return r;
        }
        if (g_gr_atlas_aviso++ < 12) apuntar("  (gráficos) letras: atlas %lu×%lu (%lu letras): no se pudo redibujar, queda el del juego", w, hh, n);
    }
    if (vuelta == GR_VF_RET && tipo == 2 && g_gr_letras == 1)          /* (las fuentes del motor: se dibujan aparte, a cualquier escala) */
        gr_vf_registrar(g_gr_touta_dc, (const BYTE *)&mips + 4, *(const WORD *const *)((BYTE *)h + 4), (const WORD *)datos, (int)w, (int)hh);
    return g_gr_ctfd_real(self, edx, h, tipo, flags, datos, w, hh, mips);
}
/* (se engancha cuando el motor ya tiene la interfaz de texturas; sólo si es el exe medido: los dos sitios) */
static void gr_atlas_enganchar(void)
{
    static int visto;
    if (g_gr_ctfd_real || visto) return;
    const BYTE *a = (const BYTE *)(ULONG_PTR)(GR_VF_RET - 3), *b = (const BYTE *)(ULONG_PTR)(GR_AT_RET - 3);
    if (IsBadReadPtr(a, 3) || IsBadReadPtr(b, 3) || a[0] != 0xFF || a[1] != 0x52 || a[2] != 0x0C || b[0] != 0xFF || b[1] != 0x50 || b[2] != 0x0C) {
        visto = 1;
        apuntar("  (gráficos) letras: el exe no es el medido (0x736683 / 0x4A71FB): sin cambios");
        return;
    }
    void *iface = *(void *volatile *)(ULONG_PTR)GR_VF_IFACE, *otra = *(void *volatile *)(ULONG_PTR)GR_AT_IFACE;
    if (!iface) return;                                      /* (todavía no: se reintenta en el próximo TextOutA/W) */
    visto = 1;
    g_gr_ctfd_vt = VT(iface);
    poner(g_gr_ctfd_vt, 3, (void *)gr_ctfd, (void **)&g_gr_ctfd_real);
    apuntar("  (gráficos) letras: enganchado CreateTextureFromData de las fuentes (interfaz 0x%p%s)", iface,
            otra && VT(otra) != g_gr_ctfd_vt ? " · la del exe es otra tabla: su atlas queda como en 2009" : "");
}

static void gr_resumen(void)                /* (cada ~30 s, con el resto del registro) */
{
    static long a0, t0;
    if (c_gr_aniso == a0 && c_gr_tri == t0) return;
    apuntar("  (gráficos) anisotrópico ×%d: %ld filtros convertidos · trilineal: %ld · brillo %ld · antialias %d · letras: %d atlas, %ld usos · "
            "render targets: %ld usos, %ld veces de destino · atlas al doble %ld (%ld letras) · TextOutA %ld · TextOutW %ld · letras sueltas CLAMP %ld", gr_limitar_aniso(g_gr_aniso), c_gr_aniso - a0, c_gr_tri - t0, (long)g_gr_brillo,
            g_gr_aa_puesto, g_gr_fu_n, c_gr_letras, c_gr_rt_usada, c_e2d_rt_fuera, c_gr_atlas, c_gr_atlas_letras, c_gr_touta, c_gr_toutw, c_gr_glifos);
    a0 = c_gr_aniso;
    t0 = c_gr_tri;
}

