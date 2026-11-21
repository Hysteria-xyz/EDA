/* novedades.js — ★ 21-nov-2026: el POP-UP DE NOVEDADES después de instalar una actualización (para el launcher de
 * R2Beat; lo pidió el dueño de EDA: «después de instalar correctamente la actualización, el jugador ve UNA sola vez un
 * POP-UP: nueva versión instalada, errores corregidos, mejoras y avisos»).
 *
 * Cómo funciona, sin tocar el Rust ni cambiar cómo se baja nada:
 *  · El texto es una NOTICIA más del panel (`launcher_contenido`), con juego `eda`, etiqueta `parche` y el id
 *    `eda-<versión>` (lo arma `herramientas/version_cliente.py noticia <versión>` desde NOVEDADES.json). Se ve como
 *    cualquier noticia (acordeón de EDA, con NUEVO) y se abre con el popup de siempre (noticias.js).
 *  · Lo nuevo: si el launcher BAJÓ algo de EDA (LU.edaProg con un porcentaje) y termina con `estado: 'listo'` (la
 *    verificación pasó), se abre SOLA la última noticia `parche` de EDA que el jugador todavía no vio. Al abrirla
 *    queda en `noticias_vistas` (las prefs del launcher): no vuelve a aparecer sola. Si termina en error, no se abre.
 *  · Nunca con un juego abierto (`body.jugando`): espera a que se cierre. Nunca encima de otro popup.
 *  · Si la actualización termina antes de que lleguen las noticias, se abre cuando llegan (Noticias.pintar).
 * Se carga DESPUÉS de launcher.js y noticias.js (envuelve LU.edaProg / LU.eda / Noticias.pintar; no los reemplaza). */
const Novedades = (() => {
  const E = { bajo: false, pendiente: null, ultima: null };

  function intentar() {
    if (!E.pendiente || typeof Noticias === 'undefined' || !Noticias.ultimaSinVer) return;
    if (document.body.classList.contains('jugando') || document.querySelector('#nvOv.on')) {
      setTimeout(intentar, 2000);                     // (con el juego abierto u otro popup: después)
      return;
    }
    const n = Noticias.ultimaSinVer(E.pendiente, 'parche');
    if (!n) return;                                   // (todavía no llegaron, o ya la vio: nada)
    E.pendiente = null;
    E.ultima = n.id;
    Noticias.abrir(n.id);
  }

  function envolver() {
    if (typeof LU === 'undefined') return;
    const prog = LU.edaProg, eda = LU.eda;
    LU.edaProg = function (pct, txt) {
      if (pct !== null && pct !== undefined) E.bajo = true;
      return prog.apply(this, arguments);
    };
    LU.eda = function (d) {
      const r = eda.apply(this, arguments);
      if (d && d.estado === 'listo' && E.bajo) { E.bajo = false; E.pendiente = 'eda'; setTimeout(intentar, 400); }
      else if (d && d.estado === 'error') E.bajo = false;
      return r;
    };
    if (typeof Noticias !== 'undefined') {           // (las noticias llegan por LU.publico y por api().publico())
      const pintar = Noticias.pintar;
      Noticias.pintar = function () {
        const r = pintar.apply(this, arguments);
        if (E.pendiente) setTimeout(intentar, 400);
        return r;
      };
    }
  }
  envolver();
  return { intentar, estado: () => ({ ...E }) };
})();
