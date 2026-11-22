/* eda_diag_nucleo.c — ★ (21-nov) lo PORTABLE del diagnóstico automático (sin Windows: se prueba en Linux con gcc,
 * prueba_diag.c): SHA-256, HMAC, la clave y la firma de cada lote (las mismas de servidor/diag.py), la cola de eventos
 * sin candados, el armado de un evento JSON, el corte de un lote (≤ 500 líneas, ≤ 64 KB) y la dirección (sólo https,
 * salvo 127.0.0.1). Lo que toca Windows (el hilo, WinHTTP, los archivos) está en eda_diag.c. */
#include <stdint.h>
#include <string.h>
#include <stdio.h>

/* ── SHA-256 (FIPS 180-4) ─────────────────────────────────────────────────────────────────────────────── */
typedef struct { uint32_t h[8]; uint64_t n; unsigned char b[64]; unsigned nb; } DG_SHA;
static const uint32_t DG_K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
    0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
#define DG_ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void dg_sha_bloque(DG_SHA *s, const unsigned char *p)
{
    uint32_t w[64], a, b, c, d, e, f, g, h;
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = DG_ROR(w[i - 15], 7) ^ DG_ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = DG_ROR(w[i - 2], 17) ^ DG_ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3]; e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (DG_ROR(e, 6) ^ DG_ROR(e, 11) ^ DG_ROR(e, 25)) + ((e & f) ^ (~e & g)) + DG_K[i] + w[i];
        uint32_t t2 = (DG_ROR(a, 2) ^ DG_ROR(a, 13) ^ DG_ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d; s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static void dg_sha_ini(DG_SHA *s)
{
    static const uint32_t H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(s->h, H0, sizeof(H0));
    s->n = 0;
    s->nb = 0;
}

static void dg_sha_mas(DG_SHA *s, const void *datos, size_t n)
{
    const unsigned char *p = (const unsigned char *)datos;
    s->n += n;
    while (n--) {
        s->b[s->nb++] = *p++;
        if (s->nb == 64) { dg_sha_bloque(s, s->b); s->nb = 0; }
    }
}

static void dg_sha_fin(DG_SHA *s, unsigned char out[32])
{
    uint64_t bits = s->n * 8;
    unsigned char uno = 0x80, cero = 0;
    dg_sha_mas(s, &uno, 1);
    while (s->nb != 56) dg_sha_mas(s, &cero, 1);
    unsigned char l[8];
    for (int i = 0; i < 8; i++) l[i] = (unsigned char)(bits >> (56 - 8 * i));
    dg_sha_mas(s, l, 8);
    for (int i = 0; i < 8; i++) {
        out[4 * i] = (unsigned char)(s->h[i] >> 24); out[4 * i + 1] = (unsigned char)(s->h[i] >> 16);
        out[4 * i + 2] = (unsigned char)(s->h[i] >> 8); out[4 * i + 3] = (unsigned char)s->h[i];
    }
}

static void dg_sha256(const void *d, size_t n, unsigned char out[32])
{
    DG_SHA s;
    dg_sha_ini(&s);
    dg_sha_mas(&s, d, n);
    dg_sha_fin(&s, out);
}

static void dg_hmac(const unsigned char *k, size_t nk, const void *msg, size_t nm, unsigned char out[32])
{
    unsigned char kb[64] = {0}, ip[64], op[64], in[32];
    if (nk > 64) dg_sha256(k, nk, kb); else memcpy(kb, k, nk);
    for (int i = 0; i < 64; i++) { ip[i] = kb[i] ^ 0x36; op[i] = kb[i] ^ 0x5c; }
    DG_SHA s;
    dg_sha_ini(&s); dg_sha_mas(&s, ip, 64); dg_sha_mas(&s, msg, nm); dg_sha_fin(&s, in);
    dg_sha_ini(&s); dg_sha_mas(&s, op, 64); dg_sha_mas(&s, in, 32); dg_sha_fin(&s, out);
}

static void dg_hex(const unsigned char *b, int n, char *out)
{
    static const char H[] = "0123456789abcdef";
    for (int i = 0; i < n; i++) { out[2 * i] = H[b[i] >> 4]; out[2 * i + 1] = H[b[i] & 15]; }
    out[2 * n] = 0;
}

/* ★ la clave del diagnóstico: K = HMAC-SHA256(ticket, "eda-diag-v1"). El ticket no se guarda: sólo K */
#define DG_DOMINIO "eda-diag-v1"
static void dg_clave(const char *ticket, size_t n, unsigned char k[32])
{
    dg_hmac((const unsigned char *)ticket, n, DG_DOMINIO, sizeof(DG_DOMINIO) - 1, k);
}

/* la firma de un lote: hex de HMAC(K, "eda-diag-v1\ncuenta\nhora\nsesion\nlote\nsha256hex(cuerpo)") */
static void dg_firmar(const unsigned char k[32], const char *cuenta, unsigned long long hora, const char *sesion,
                      unsigned long lote, const char *cuerpo, size_t n, char firma[65])
{
    unsigned char h[32], f[32];
    char hh[65], msg[256];
    dg_sha256(cuerpo, n, h);
    dg_hex(h, 32, hh);
    int m = snprintf(msg, sizeof(msg), DG_DOMINIO "\n%s\n%llu\n%s\n%lu\n%s", cuenta, hora, sesion, lote, hh);
    dg_hmac(k, 32, msg, (size_t)m, f);
    dg_hex(f, 32, firma);
}

/* ── un evento: {"t":ms UTC,"m":ms desde el arranque,"e":"nombre"<extra>} ─────────────────────────────────────
 * `extra` lo arma quien llama SÓLO con números y nombres fijos (",\"vt\":\"0x899670\""); por las dudas, el nombre del
 * evento se limpia: letras, dígitos y «_», hasta 23. */
static int dg_evento(char *out, int cap, unsigned long long t, unsigned long long m, const char *e, const char *extra)
{
    char nom[24];
    int j = 0;
    for (const char *p = e; *p && j < 23; p++)
        if ((*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') || *p == '_') nom[j++] = *p;
    nom[j] = 0;
    int n = snprintf(out, cap, "{\"t\":%llu,\"m\":%llu,\"e\":\"%s\"%s}", t, m, nom, extra ? extra : "");
    return n > 0 && n < cap ? n : 0;
}

/* ── la COLA: el hilo del juego (o un gancho, o el vigía) anota y sigue; el hilo del diagnóstico saca en orden ───────
 * Un anillo de líneas con un candado de INTENTO: anotar copia ≤ 240 bytes adentro; si el candado está tomado más de
 * unas vueltas, o la cola está llena (el lector se atrasó), la línea se DESCARTA y se cuenta. Nadie espera de verdad. */
#define DG_LUGARES 256
#define DG_LARGO 240
typedef struct { volatile long candado; long escribir, leer; volatile long perdidos; char l[DG_LUGARES][DG_LARGO]; } DG_COLA;

#ifndef DG_ATOMICO_MAS
#define DG_ATOMICO_MAS(p) __sync_add_and_fetch((p), 1)
#endif

static int dg_tomar(DG_COLA *c)
{
    for (int i = 0; i < 2000; i++)
        if (__sync_bool_compare_and_swap(&c->candado, 0, 1)) return 1;
    return 0;
}

static void dg_soltar(DG_COLA *c) { __sync_lock_release(&c->candado); }

static int dg_cola_poner(DG_COLA *c, const char *txt)
{
    if (!dg_tomar(c)) { DG_ATOMICO_MAS(&c->perdidos); return 0; }
    if (c->escribir - c->leer >= DG_LUGARES) { dg_soltar(c); DG_ATOMICO_MAS(&c->perdidos); return 0; }
    char *d = c->l[c->escribir % DG_LUGARES];
    size_t k = strlen(txt);
    if (k >= DG_LARGO) k = DG_LARGO - 1;
    memcpy(d, txt, k);
    d[k] = 0;
    c->escribir++;
    dg_soltar(c);
    return 1;
}

/* saca la próxima en orden (1) o nada (0) */
static int dg_cola_sacar(DG_COLA *c, char *out, int cap)
{
    if (!dg_tomar(c)) return 0;
    if (c->leer >= c->escribir) { dg_soltar(c); return 0; }
    const char *s = c->l[c->leer % DG_LUGARES];
    int k = (int)strlen(s);
    if (k >= cap) k = cap - 1;
    memcpy(out, s, k);
    out[k] = 0;
    c->leer++;
    dg_soltar(c);
    return 1;
}

/* ── el LOTE: de un texto de líneas, cuántos bytes mandar (≤ 500 líneas, ≤ 64 KB, siempre líneas enteras) ───── */
#define DG_LOTE_LINEAS 500
#define DG_LOTE_BYTES (60 * 1024)
static size_t dg_cortar_lote(const char *t, size_t n)
{
    size_t fin = 0, i = 0;
    int lineas = 0;
    while (i < n && lineas < DG_LOTE_LINEAS) {
        const char *nl = memchr(t + i, '\n', n - i);
        if (!nl) break;                                       /* (una línea a medias no se manda) */
        size_t prox = (size_t)(nl - t) + 1;
        if (prox > DG_LOTE_BYTES) break;
        fin = i = prox;
        lineas++;
    }
    return fin;
}

/* ── la dirección: https://host[:puerto]/ruta; http SÓLO a 127.0.0.1 (para probar en la misma PC) ──────────── */
static int dg_url(const char *u, int *https, char *host, int cap_host, int *puerto, char *ruta, int cap_ruta)
{
    const char *p;
    if (!strncmp(u, "https://", 8)) { *https = 1; p = u + 8; *puerto = 443; }
    else if (!strncmp(u, "http://", 7)) { *https = 0; p = u + 7; *puerto = 80; }
    else return 0;
    int i = 0;
    while (*p && *p != '/' && *p != ':' && i < cap_host - 1) host[i++] = *p++;
    host[i] = 0;
    if (!i) return 0;
    for (int k = 0; k < i; k++) {
        char c = host[k];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return 0;
    }
    if (*p == ':') {
        int v = 0;
        p++;
        while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
        if (v <= 0 || v > 65535) return 0;
        *puerto = v;
    }
    if (*p != '/') return 0;
    int j = 0;
    while (*p && j < cap_ruta - 1) ruta[j++] = *p++;
    ruta[j] = 0;
    if (!*https && strcmp(host, "127.0.0.1")) return 0;          /* ★ afuera, sólo https */
    return 1;
}
