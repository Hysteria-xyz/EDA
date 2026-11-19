/* eda_teclas.c — ★ (Punto 4, 18-nov) LAS TECLAS DEL JUEGO, SIN WINDOWS NI PYTHON: leer las que tiene el
 *   autoexec.cfg, cambiarlas y armar (a) los comandos de consola que las aplican AL INSTANTE y (b) el
 *   autoexec.cfg nuevo. Lo usa eda_opciones.c (la sección CONTROLES de Options); C puro, sin Win32, para
 *   poder probarlo solo: `gcc -o p prueba_teclas.c && ./p` (herramientas/dll_d3d9/prueba_teclas.c).
 *
 *   ★ Medido en el exe (EDA_limpio 0799387e, tabla de comandos de consola en 0x910B20):
 *     «Bind» = 0x422DA0: (dispositivo, botón, acción…): BORRA lo que tenía ese botón (input+0x28) y le pone
 *       cada acción (input+0x2C, con rango 0,0). Sin acciones: sólo lo borra.
 *     «RangeBind» = 0x422E20: sólo AGREGA (con rangos). Es lo que el juego escribe en autoexec.cfg al salir
 *       («rangebind "##keyboard" "##59" 0.000000 0.000000 "Skill1"») con lo que tiene en memoria.
 *   ⇒ en vivo: «Bind» por la consola del juego (la misma cola que ya usan las Options en vivo); para el
 *     próximo arranque: las líneas «rangebind» del autoexec.cfg (el launcher no lo pisa: ENTORNOS §5), y como
 *     el juego lo reescribe al salir con lo que tiene en memoria —que ya es lo nuevo— no lo revierte.
 *   Las acciones y las teclas de fábrica son las de paneles/EDA-Teclas.py (medidas el 13-nov).
 *   Código de una tecla: 1..255 = código DirectInput (el del autoexec, «##59» = F1); 0x100 + n = botón n del
 *   mouse («##Button n»); 0 = ninguna. */

/* (sin la CRT de más: lstrcmpiA de kernel32, como el resto de la dll) */
static int tec_empieza_n(const char *s, const char *pref, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        char a = s[i], b = pref[i];
        if (a >= 'A' && a <= 'Z') a += 32;
        if (b >= 'A' && b <= 'Z') b += 32;
        if (a != b) return 1;
        if (!a) return 0;
    }
    return 0;
}

#define TEC_FILAS 29
#define TEC_GRUPOS 5
#define TEC_MOUSE 0x100
typedef struct { const char *accion; const WCHAR *texto; int grupo, defecto[2]; } TEC_FILA;
static const WCHAR *const TEC_GRUPO_T[TEC_GRUPOS] = {L"Movimiento", L"Combate", L"Habilidades", L"Ítems", L"Interfaz"};
static const TEC_FILA TEC[TEC_FILAS] = {
    {"MoveForward", L"Avanzar", 0, {17, 200}}, {"MoveBackward", L"Retroceder", 0, {31, 208}},
    {"MoveLeft", L"Izquierda", 0, {30, 203}}, {"MoveRight", L"Derecha", 0, {32, 205}},
    {"Jump", L"Saltar", 0, {57, 0}}, {"Guard", L"Defender / guardia", 0, {42, 0}},
    {"MouseButtonL", L"Atacar", 1, {TEC_MOUSE + 0, 0}}, {"MouseButtonR", L"Lanzar la habilidad elegida", 1, {TEC_MOUSE + 1, 0}},
    {"MouseButtonM", L"Botón medio del mouse", 1, {TEC_MOUSE + 2, 0}}, {"ChangeWeapon", L"Cambiar de arma", 1, {33, 0}},
    {"Skill_Next", L"Habilidad siguiente", 1, {18, 0}}, {"Skill_Prev", L"Habilidad anterior", 1, {16, 0}},
    {"Skill1", L"Habilidad 1", 2, {59, 0}}, {"Skill2", L"Habilidad 2", 2, {60, 0}}, {"Skill3", L"Habilidad 3", 2, {61, 0}},
    {"Skill4", L"Habilidad 4", 2, {62, 0}}, {"Skill5", L"Habilidad 5", 2, {63, 0}}, {"Skill6", L"Habilidad 6", 2, {64, 0}},
    {"Skill7", L"Habilidad 7", 2, {65, 0}}, {"Skill8", L"Habilidad 8", 2, {66, 0}},
    {"GameItem1", L"Ítem 1 (HP, MP…)", 3, {2, 0}}, {"GameItem2", L"Ítem 2 (HP, MP…)", 3, {3, 0}},
    {"GameItem3", L"Ítem 3", 3, {4, 0}}, {"GameItem4", L"Ítem 4", 3, {5, 0}}, {"GameItem5", L"Ítem 5", 3, {6, 0}},
    {"GameItem6", L"Ítem 6", 3, {7, 0}}, {"Revival7", L"Revivir: opción 7", 3, {8, 0}},
    {"Tab", L"Tabla de puntos", 4, {15, 0}}, {"Enter", L"Chat", 4, {28, 0}},
};
/* las acciones que van JUNTO con otra en el mismo botón: el número de cada ítem también elige al revivir */
static const char *tec_junto(int fila, char *buf)
{
    if (!strncmp(TEC[fila].accion, "GameItem", 8) && TEC[fila].accion[8] >= '1' && TEC[fila].accion[8] <= '6') {
        strcpy(buf, "Revival");
        buf[7] = TEC[fila].accion[8];
        buf[8] = 0;
        return buf;
    }
    return NULL;
}
/* ¿es una de las que maneja este panel (incluidas las que van junto)? (las demás —ejes del mouse…— no se tocan) */
static int tec_nuestra(const char *accion)
{
    char j[16];
    for (int i = 0; i < TEC_FILAS; i++)
        if (!lstrcmpiA(accion, TEC[i].accion) || (tec_junto(i, j) && !lstrcmpiA(accion, j))) return 1;
    return 0;
}
/* F9–F12 son de EDA (listo, Options, Messenger, Clan); Esc cancela */
static int tec_reservada(int cod) { return cod == 1 || cod == 67 || cod == 68 || cod == 87 || cod == 88; }

/* el nombre que se ve (0 = «—»); devuelve 0 si la tecla no tiene nombre (no se deja usar) */
static int tec_nombre(int cod, WCHAR *t)
{
    static const struct { unsigned char c; const WCHAR *n; } N[] = {
        {1, L"Esc"}, {12, L"-"}, {13, L"="}, {14, L"Retroceso"}, {15, L"Tab"}, {26, L"["}, {27, L"]"}, {28, L"Enter"},
        {29, L"Ctrl"}, {39, L"Ñ"}, {40, L"'"}, {41, L"º"}, {42, L"Shift"}, {43, L"\\"}, {51, L","}, {52, L"."}, {53, L"/"},
        {54, L"Shift der."}, {55, L"Num *"}, {56, L"Alt"}, {57, L"Espacio"}, {58, L"Bloq Mayús"}, {71, L"Num 7"},
        {72, L"Num 8"}, {73, L"Num 9"}, {74, L"Num -"}, {75, L"Num 4"}, {76, L"Num 5"}, {77, L"Num 6"}, {78, L"Num +"},
        {79, L"Num 1"}, {80, L"Num 2"}, {81, L"Num 3"}, {82, L"Num 0"}, {83, L"Num ."}, {86, L"<"}, {156, L"Num Enter"},
        {157, L"Ctrl der."}, {181, L"Num /"}, {184, L"Alt Gr"}, {199, L"Inicio"}, {200, L"↑"}, {201, L"RePág"},
        {203, L"←"}, {205, L"→"}, {207, L"Fin"}, {208, L"↓"}, {209, L"AvPág"}, {210, L"Insert"}, {211, L"Supr"}};
    static const char *const FILA1 = "QWERTYUIOP", *const FILA2 = "ASDFGHJKL", *const FILA3 = "ZXCVBNM";
    t[0] = 0;
    if (!cod) { t[0] = 0x2014; t[1] = 0; return 1; }                      /* — */
    if (cod >= TEC_MOUSE) {
        static const WCHAR *const M[5] = {L"Clic izq.", L"Clic der.", L"Clic medio", L"Botón lat. 1", L"Botón lat. 2"};
        int b = cod - TEC_MOUSE;
        if (b < 0 || b > 4) return 0;
        for (int i = 0; (t[i] = M[b][i]); i++) {}
        return 1;
    }
    if (cod >= 2 && cod <= 11) { t[0] = cod == 11 ? L'0' : (WCHAR)(L'0' + cod - 1); t[1] = 0; return 1; }
    if (cod >= 16 && cod <= 25) { t[0] = FILA1[cod - 16]; t[1] = 0; return 1; }
    if (cod >= 30 && cod <= 38) { t[0] = FILA2[cod - 30]; t[1] = 0; return 1; }
    if (cod >= 44 && cod <= 50) { t[0] = FILA3[cod - 44]; t[1] = 0; return 1; }
    if (cod >= 59 && cod <= 68) { t[0] = L'F'; if (cod == 68) { t[1] = L'1'; t[2] = L'0'; t[3] = 0; } else { t[1] = (WCHAR)(L'1' + cod - 59); t[2] = 0; } return 1; }
    if (cod == 87 || cod == 88) { t[0] = L'F'; t[1] = L'1'; t[2] = cod == 87 ? L'1' : L'2'; t[3] = 0; return 1; }
    for (unsigned i = 0; i < sizeof(N) / sizeof(N[0]); i++)
        if (N[i].c == cod) { for (int k = 0; (t[k] = N[i].n[k]); k++) {} return 1; }
    return 0;
}

/* ── lo que tiene el autoexec.cfg: cada botón (teclado / botón del mouse) con sus acciones ── */
#define TEC_BOTONES 128
#define TEC_ACC_MAX 6
typedef struct { int cod, n; char acc[TEC_ACC_MAX][24]; } TEC_BOTON;
typedef struct { int n; TEC_BOTON b[TEC_BOTONES]; } TEC_MAPA;

static TEC_BOTON *tec_boton(TEC_MAPA *m, int cod, int crear)
{
    for (int i = 0; i < m->n; i++) if (m->b[i].cod == cod) return &m->b[i];
    if (!crear || m->n >= TEC_BOTONES) return NULL;
    TEC_BOTON *b = &m->b[m->n++];
    memset(b, 0, sizeof(*b));
    b->cod = cod;
    return b;
}
static void tec_agregar(TEC_BOTON *b, const char *accion)
{
    for (int i = 0; i < b->n; i++) if (!lstrcmpiA(b->acc[i], accion)) return;
    if (b->n < TEC_ACC_MAX) { strncpy(b->acc[b->n], accion, 23); b->acc[b->n][23] = 0; b->n++; }
}
/* ★ (18-nov, noche) el autoexec.cfg ORIGINAL (2009, el de una instalación nueva) nombra las teclas por su
 *   nombre de DirectInput ("W", "F1", "1", "Q"…) en vez de «##n»: también se leen (si no, esas teclas no se
 *   veían y al GUARDAR quedaba la línea vieja además de la nueva). Sólo las que usa ese archivo: letras,
 *   números y F1–F12; cualquier otra → 0 (no se toca la línea). */
static int tec_por_nombre(const char *n)
{
    static const char *const FILAS[3] = {"QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"};
    static const int DESDE[3] = {16, 30, 44};
    if (n[0] && !n[1]) {
        char c = n[0] >= 'a' && n[0] <= 'z' ? (char)(n[0] - 32) : n[0];
        if (c >= '1' && c <= '9') return 2 + (c - '1');
        if (c == '0') return 11;
        for (int f = 0; f < 3; f++)
            for (int i = 0; FILAS[f][i]; i++) if (FILAS[f][i] == c) return DESDE[f] + i;
        return 0;
    }
    if ((n[0] == 'F' || n[0] == 'f') && n[1] >= '1' && n[1] <= '9') {
        int k = atoi(n + 1);
        if (k >= 1 && k <= 10 && (n[2] == 0 || (n[2] == '0' && !n[3] && k == 10))) return 58 + k;
        if ((k == 11 || k == 12) && !n[3]) return 76 + k;
    }
    return 0;
}

/* una línea «rangebind "##keyboard" "##59" 0.000000 0.000000 "Skill1" …» → cod y las acciones (sus textos
 *   entre comillas desde el 3º). Devuelve el cod (0 = no es de un botón: ejes del mouse, otra cosa). */
static int tec_linea(const char *l, char q[][24], int *nq)
{
    *nq = 0;
    while (*l == ' ' || *l == '\t') l++;
    if (tec_empieza_n(l, "rangebind", 9)) return 0;
    for (const char *p = l + 9; *p && *p != '\r' && *p != '\n' && *nq < TEC_ACC_MAX + 2; p++) {
        if (*p != '"') continue;
        const char *f = p + 1;
        int k = 0;
        while (f[k] && f[k] != '"' && f[k] != '\n' && k < 23) k++;
        memcpy(q[*nq], f, k);
        q[*nq][k] = 0;
        (*nq)++;
        p = f + k;
        if (*p != '"') break;
    }
    if (*nq < 2) return 0;
    if (!lstrcmpiA(q[0], "##keyboard") && !strncmp(q[1], "##", 2) && q[1][2] >= '0' && q[1][2] <= '9') {
        int c = atoi(q[1] + 2);
        return c > 0 && c < 256 ? c : 0;
    }
    if (!lstrcmpiA(q[0], "##keyboard")) return tec_por_nombre(q[1]);   /* (el autoexec.cfg de 2009: "W", "F1", "1") */
    if (!lstrcmpiA(q[0], "##mouse") && !tec_empieza_n(q[1], "##Button ", 9)) return TEC_MOUSE + atoi(q[1] + 9);
    return 0;
}
static void tec_leer_cfg(const char *cfg, TEC_MAPA *m)
{
    char q[TEC_ACC_MAX + 2][24];
    int nq;
    m->n = 0;
    for (const char *p = cfg; p && *p; ) {
        int c = tec_linea(p, q, &nq);
        if (c) {
            TEC_BOTON *b = tec_boton(m, c, 1);
            for (int i = 2; b && i < nq; i++) tec_agregar(b, q[i]);
        }
        while (*p && *p != '\n') p++;
        if (*p) p++;
    }
}
/* las dos teclas de cada acción, según el mapa (de menor a mayor: el teclado antes que el mouse) */
static void tec_de_mapa(const TEC_MAPA *m, int t[][2])
{
    for (int f = 0; f < TEC_FILAS; f++) {
        t[f][0] = t[f][1] = 0;
        for (int i = 0; i < m->n; i++) {
            int tiene = 0;
            for (int k = 0; k < m->b[i].n; k++) if (!lstrcmpiA(m->b[i].acc[k], TEC[f].accion)) tiene = 1;
            if (!tiene) continue;
            int c = m->b[i].cod;
            if (!t[f][0] || c < t[f][0]) { t[f][1] = t[f][0]; t[f][0] = c; }
            else if (!t[f][1] || c < t[f][1]) t[f][1] = c;
        }
    }
}
static void tec_de_fabrica(int t[][2])
{
    for (int f = 0; f < TEC_FILAS; f++) { t[f][0] = TEC[f].defecto[0]; t[f][1] = TEC[f].defecto[1]; }
}
/* poner `cod` en (fila, lugar): se saca de donde estaba (una tecla, una acción). Devuelve cuántas la perdieron
 *   y en `quitada` la primera (para el aviso). */
static int tec_poner(int t[][2], int fila, int lugar, int cod, int *quitada)
{
    int n = 0;
    *quitada = -1;
    if (cod)
        for (int f = 0; f < TEC_FILAS; f++)
            for (int l = 0; l < 2; l++)
                if (t[f][l] == cod && !(f == fila && l == lugar)) { t[f][l] = 0; if (*quitada < 0 && f != fila) *quitada = f; n++; }
    t[fila][lugar] = cod;
    return n;
}

/* ── lo nuevo: el mapa con nuestras acciones según `t` (lo demás de cada botón, igual) ── */
static void tec_armar(const TEC_MAPA *viejo, int t[][2], TEC_MAPA *nuevo)
{
    char j[16];
    nuevo->n = 0;
    for (int i = 0; i < viejo->n; i++) {                    /* lo que no es nuestro se queda */
        TEC_BOTON *b = tec_boton(nuevo, viejo->b[i].cod, 1);
        for (int k = 0; b && k < viejo->b[i].n; k++)
            if (!tec_nuestra(viejo->b[i].acc[k])) tec_agregar(b, viejo->b[i].acc[k]);
    }
    for (int f = 0; f < TEC_FILAS; f++)
        for (int l = 0; l < 2; l++) {
            if (!t[f][l]) continue;
            TEC_BOTON *b = tec_boton(nuevo, t[f][l], 1);
            if (!b) continue;
            if (tec_junto(f, j)) tec_agregar(b, j);
            tec_agregar(b, TEC[f].accion);
        }
}
static int tec_iguales(const TEC_BOTON *a, const TEC_BOTON *b)    /* (NULL = sin acciones) */
{
    int na = a ? a->n : 0, nb = b ? b->n : 0;
    if (na != nb) return 0;
    for (int i = 0; i < na; i++) {
        int esta = 0;
        for (int k = 0; k < nb; k++) if (!lstrcmpiA(a->acc[i], b->acc[k])) esta = 1;
        if (!esta) return 0;
    }
    return 1;
}
static void tec_objeto(int cod, char *dispositivo, char *objeto)
{
    if (cod >= TEC_MOUSE) { strcpy(dispositivo, "##mouse"); sprintf(objeto, "##Button %d", cod - TEC_MOUSE); }
    else { strcpy(dispositivo, "##keyboard"); sprintf(objeto, "##%d", cod); }
}
/* los botones que cambiaron (lista de cod) */
static int tec_cambiados(const TEC_MAPA *viejo, const TEC_MAPA *nuevo, int *cods, int max)
{
    int n = 0;
    for (int pasada = 0; pasada < 2; pasada++) {
        const TEC_MAPA *m = pasada ? viejo : nuevo;
        for (int i = 0; i < m->n && n < max; i++) {
            int c = m->b[i].cod, ya = 0;
            for (int k = 0; k < n; k++) if (cods[k] == c) ya = 1;
            if (ya) continue;
            const TEC_BOTON *a = tec_boton((TEC_MAPA *)viejo, c, 0), *b = tec_boton((TEC_MAPA *)nuevo, c, 0);
            if (!tec_iguales(a, b)) cods[n++] = c;
        }
    }
    return n;
}
/* EN VIVO: «Bind "##keyboard" "##59" "Skill1"» (borra el botón y le pone las acciones; sin acciones, lo borra) */
static int tec_comando(const TEC_MAPA *nuevo, int cod, char *l, int cap)
{
    char d[16], o[24];
    tec_objeto(cod, d, o);
    const TEC_BOTON *b = tec_boton((TEC_MAPA *)nuevo, cod, 0);
    int n = (int)strlen(d) + (int)strlen(o) + 12;
    for (int k = 0; b && k < b->n; k++) n += (int)strlen(b->acc[k]) + 3;
    if (n >= cap) return 0;
    n = sprintf(l, "Bind \"%s\" \"%s\"", d, o);
    for (int k = 0; b && k < b->n; k++) n += sprintf(l + n, " \"%s\"", b->acc[k]);
    return 1;
}
/* la línea del autoexec.cfg, como la escribe el juego */
static int tec_renglon(const TEC_BOTON *b, char *l, int cap)
{
    char d[16], o[24];
    tec_objeto(b->cod, d, o);
    int n = (int)strlen(d) + (int)strlen(o) + 16;
    for (int k = 0; k < b->n; k++) n += (int)strlen(b->acc[k]) + 21;
    if (n >= cap) return 0;
    n = sprintf(l, "rangebind \"%s\" \"%s\" ", d, o);
    for (int k = 0; k < b->n; k++) n += sprintf(l + n, "0.000000 0.000000 \"%s\" ", b->acc[k]);
    return 1;
}
/* ★ el autoexec.cfg NUEVO: las líneas de los botones que cambiaron se sacan, y las nuevas van debajo de su
 *   «enabledevice» (o al final); el resto del archivo —opciones, ejes del mouse, AddAction…— queda igual, con sus
 *   finales de línea. `salida` tiene que tener lugar para cfg + 4 KB. Devuelve el largo (o -1). */
static int tec_nuevo_cfg(const char *cfg, const TEC_MAPA *nuevo, const int *cods, int ncods, char *salida, int cap)
{
    const char *nl = strstr(cfg, "\r\n") ? "\r\n" : "\n";
    char q[TEC_ACC_MAX + 2][24], r[256];
    int nq, n = 0, puestos[2] = {0, 0};
    for (const char *p = cfg; *p; ) {
        const char *fin = p;
        while (*fin && *fin != '\n') fin++;
        if (*fin) fin++;
        int c = tec_linea(p, q, &nq), sacar = 0;
        for (int k = 0; c && k < ncods; k++) if (cods[k] == c) sacar = 1;
        if (!sacar) {
            if (n + (fin - p) >= cap) return -1;
            memcpy(salida + n, p, fin - p);
            n += (int)(fin - p);
            const char *s = p;
            while (*s == ' ' || *s == '\t') s++;
            for (int disp = 0; disp < 2; disp++) {
                const char *en = disp ? "enabledevice \"##mouse\"" : "enabledevice \"##keyboard\"";
                if (!puestos[disp] && !tec_empieza_n(s, en, strlen(en))) {
                    if (n && salida[n - 1] != '\n') { if (n + 2 >= cap) return -1; n += sprintf(salida + n, "%s", nl); }
                    for (int k = 0; k < ncods; k++) {
                        if ((cods[k] >= TEC_MOUSE) != disp) continue;
                        const TEC_BOTON *b = tec_boton((TEC_MAPA *)nuevo, cods[k], 0);
                        if (!b || !b->n || !tec_renglon(b, r, sizeof(r))) continue;
                        if (n + (int)strlen(r) + 3 >= cap) return -1;
                        n += sprintf(salida + n, "%s%s", r, nl);
                    }
                    puestos[disp] = 1;
                }
            }
        }
        p = fin;
    }
    for (int disp = 0; disp < 2; disp++) {                   /* (sin «enabledevice»: al final, con el suyo) */
        if (puestos[disp]) continue;
        int hay = 0;
        for (int k = 0; k < ncods; k++) {
            const TEC_BOTON *b = tec_boton((TEC_MAPA *)nuevo, cods[k], 0);
            if ((cods[k] >= TEC_MOUSE) == disp && b && b->n) hay = 1;
        }
        if (!hay) continue;
        if (n && salida[n - 1] != '\n') { if (n + 2 >= cap) return -1; n += sprintf(salida + n, "%s", nl); }
        if (n + 40 >= cap) return -1;
        n += sprintf(salida + n, "enabledevice \"%s\"%s", disp ? "##mouse" : "##keyboard", nl);
        for (int k = 0; k < ncods; k++) {
            const TEC_BOTON *b = tec_boton((TEC_MAPA *)nuevo, cods[k], 0);
            if ((cods[k] >= TEC_MOUSE) != disp || !b || !b->n || !tec_renglon(b, r, sizeof(r))) continue;
            if (n + (int)strlen(r) + 3 >= cap) return -1;
            n += sprintf(salida + n, "%s%s", r, nl);
        }
    }
    salida[n] = 0;
    return n;
}

/* ★ (18-nov, noche) ¿QUÉ TIENE EL MOTOR DE VERDAD? Para no dar por bueno un «Bind» sólo porque se mandó: se
 *   leen (SÓLO LEER) las mismas estructuras que recorre el propio juego al escribir autoexec.cfg al salir
 *   (0x445B70, el que imprime «rangebind "%s" "%s" » y «%f %f "%s" »):
 *     [0x930D68]      el primer dispositivo; el siguiente en +0x2FC
 *     dispositivo     nombre: [+4] o, si es 0, el texto en +0xC  («##keyboard», «##mouse»)
 *                     sus botones: lista circular desde [+0x8C]; el siguiente en +4; el nombre en +0x6C («##17»)
 *     botón           sus acciones: [+0x138]; cada una {+0 desde, +4 hasta, +8 texto «*…», +0xC acción
 *                     (su nombre en +4)}; la siguiente en +0x10
 *   `leer` devuelve 4 bytes de una dirección (0 en *ok si no se puede leer) y `texto` copia un texto: así se
 *   prueba sin Windows (prueba_teclas.c arma una memoria de mentira con esa forma).
 *   Devuelve -1 = no está el dispositivo, 0 = el botón no está (= sin acciones), 1 = está (acciones en `out`). */
typedef unsigned int (*TEC_LEER4)(unsigned int dir, int *ok);
typedef int (*TEC_TEXTO)(unsigned int dir, char *t, int cap);
static int tec_motor(unsigned int primero, const char *disp, const char *obj, char *out, int cap,
                     TEC_LEER4 leer, TEC_TEXTO texto)
{
    char n[40];
    int ok = 1;
    out[0] = 0;
    for (unsigned int d = primero, vueltas = 0; d && vueltas < 16; vueltas++) {
        unsigned int pn = leer(d + 4, &ok);
        if (!ok || !texto(pn ? pn : d + 0xC, n, sizeof(n))) return -1;
        if (!lstrcmpiA(n, disp)) {
            unsigned int cabeza = leer(d + 0x8C, &ok), b = cabeza;
            for (int i = 0; ok && b && i < 1024; i++) {
                if (texto(b + 0x6C, n, sizeof(n)) && !lstrcmpiA(n, obj)) {
                    int largo = 0;
                    unsigned int a = leer(b + 0x138, &ok);
                    for (int k = 0; ok && a && k < 16; k++) {
                        unsigned int acc = leer(a + 0xC, &ok), t8 = ok ? leer(a + 8, &ok) : 0;
                        char nom[32];
                        if (!ok) break;
                        if (!(acc ? texto(acc + 4, nom, sizeof(nom)) : t8 ? texto(t8, nom, sizeof(nom)) : 0)) strcpy(nom, "?");
                        if (largo + (int)strlen(nom) + 3 < cap) largo += sprintf(out + largo, "%s%s", largo ? "," : "", nom);
                        a = leer(a + 0x10, &ok);
                    }
                    return 1;
                }
                b = leer(b + 4, &ok);
                if (b == cabeza) break;
            }
            return ok ? 0 : -1;
        }
        d = leer(d + 0x2FC, &ok);
        if (!ok) return -1;
    }
    return -1;
}
/* ¿las acciones que quedaron en el motor («A,B») son las pedidas (el Bind: «… "A" "B"»)? (sin orden) */
static int tec_mismas(const char *motor, char q[][24], int desde, int nq)
{
    int cuenta = 0;
    for (const char *p = motor; *p; ) {
        char un[32];
        int k = 0;
        while (*p && *p != ',' && k < 31) un[k++] = *p++;
        un[k] = 0;
        if (*p == ',') p++;
        int esta = 0;
        for (int i = desde; i < nq; i++) if (!lstrcmpiA(un, q[i])) esta = 1;
        if (!esta) return 0;
        cuenta++;
    }
    return cuenta == nq - desde;
}
/* los textos entre comillas de un comando de consola («Bind "##keyboard" "##17" "MoveForward"») */
static int tec_comillas(const char *l, char q[][24], int max)
{
    int n = 0;
    for (const char *p = l; *p && n < max; p++) {
        if (*p != '"') continue;
        const char *f = p + 1;
        int k = 0;
        while (f[k] && f[k] != '"' && k < 23) k++;
        memcpy(q[n], f, k);
        q[n][k] = 0;
        n++;
        p = f + k;
        if (*p != '"') break;
    }
    return n;
}
