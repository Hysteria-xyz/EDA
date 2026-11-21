// probar_popup.js — ★ 21-nov-2026: prueba el POP-UP de novedades con la PANTALLA DE VERDAD del launcher de R2Beat.
//
//   node launcher/popup-novedades/probar_popup.js <Launcher.exe> <noticia.json> [carpeta-de-salida]
//
// 1. Saca la pantalla (launcher.html, launcher.js, noticias.js… comprimidas con brotli adentro del exe de Tauri) a
//    una carpeta temporal. No se guarda en el repo: es código del launcher, no nuestro.
// 2. Le aplica el cambio propuesto (noticias.js: `ultimaSinVer`; launcher.html: carga novedades.js) y FALLA si el
//    launcher cambió y el cambio ya no encaja.
// 3. La abre en Chrome sin ventana, con el MOCK que trae el mismo launcher (su «vista previa» sin Tauri), y hace lo
//    que hace el launcher de verdad: LU.publico (las noticias del panel), LU.edaProg (bajando) y LU.eda (listo).
// 4. Comprueba: se abre SOLA, una vez, con la versión, corregidos, mejoras y avisos; no se abre si no bajó nada, si
//    terminó en error ni con el juego abierto; si las noticias llegan después, se abre cuando llegan. Capturas.
'use strict';
const fs = require('fs'), path = require('path'), zlib = require('zlib'), os = require('os');
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd(), '/opt/npm-tools/node_modules'] }));

const [exe, noticiaJson, salida = path.join(os.tmpdir(), 'popup-capturas')] = process.argv.slice(2);
if (!exe || !noticiaJson) { console.error('uso: node probar_popup.js <Launcher.exe> <noticia.json> [salida]'); process.exit(2); }
const AQUI = __dirname;

/** Las pantallas de Tauri: una tabla (ruta &str, datos &[u8]) en .rdata; los datos, brotli. */
function extraer(exePath, dest) {
  const b = fs.readFileSync(exePath);
  const pe = b.readUInt32LE(0x3c), n = b.readUInt16LE(pe + 6), opt = b.readUInt16LE(pe + 20);
  const base = b.readBigUInt64LE(pe + 24 + 24);
  const secs = [];
  for (let i = 0; i < n; i++) {
    const o = pe + 24 + opt + 40 * i;
    secs.push({ va: base + BigInt(b.readUInt32LE(o + 12)), vs: b.readUInt32LE(o + 8), off: b.readUInt32LE(o + 20), rs: b.readUInt32LE(o + 16) });
  }
  const aOff = v => { for (const s of secs) if (v >= s.va && v < s.va + BigInt(Math.max(s.vs, s.rs))) return Number(v - s.va) + s.off; return -1; };
  let k = 0;
  for (let j = 0; j + 32 <= b.length; j += 8) {
    const p = aOff(b.readBigUInt64LE(j)), l = Number(b.readBigUInt64LE(j + 8));
    if (p < 0 || l < 2 || l > 120 || b[p] !== 0x2f) continue;
    const ruta = b.toString('latin1', p, p + l);
    if (!/^\/[\w.\/-]+$/.test(ruta)) continue;
    const d = aOff(b.readBigUInt64LE(j + 16)), dl = Number(b.readBigUInt64LE(j + 24));
    if (d < 0 || dl < 1 || dl > 5e6) continue;
    try {
      const out = zlib.brotliDecompressSync(b.subarray(d, d + dl));
      const f = path.join(dest, ruta);
      fs.mkdirSync(path.dirname(f), { recursive: true });
      fs.writeFileSync(f, out);
      k++;
    } catch (e) { /* (no era una pantalla) */ }
  }
  return k;
}

function parchear(dir) {
  const rep = (f, viejo, nuevo) => {
    const p = path.join(dir, f), s = fs.readFileSync(p, 'utf8');
    if (s.split(viejo).length !== 2) throw new Error(`⛔ ${f}: el launcher cambió, el parche no encaja («${viejo.slice(0, 40)}»)`);
    fs.writeFileSync(p, s.replace(viejo, nuevo));
  };
  rep('noticias.js', '  return { pintar, abrir, cerrar };',
    "  function ultimaSinVer(juego, etiqueta) {\n    return lista.find(n => n.juego === juego && (!etiqueta || n.etiqueta === etiqueta) && nueva(n)) || null;\n  }\n\n  return { pintar, abrir, cerrar, ultimaSinVer };");
  rep('launcher.html', '<script src="noticias.js" charset="utf-8"></script>\n',
    '<script src="noticias.js" charset="utf-8"></script>\n<script src="novedades.js" charset="utf-8"></script>\n');
  fs.copyFileSync(path.join(AQUI, 'novedades.js'), path.join(dir, 'novedades.js'));
}

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'launcher-'));
  const n = extraer(exe, dir);
  if (!fs.existsSync(path.join(dir, 'launcher.html')) || !fs.existsSync(path.join(dir, 'noticias.js')))
    throw new Error('⛔ no encontré launcher.html / noticias.js adentro del exe');
  parchear(dir);
  fs.mkdirSync(salida, { recursive: true });
  const noticia = JSON.parse(fs.readFileSync(noticiaJson, 'utf8'));
  const otras = [{ id: 'n1', juego: 'r2beat', titulo: 'Ruleta nueva', texto: 'x', etiqueta: 'evento', fecha: '2026-10-26' },
                 { id: 'eda-viejo', juego: 'eda', titulo: 'EDA abre su beta', texto: 'x', etiqueta: 'noticia', fecha: '2026-11-15' }];
  const navegador = await chromium.launch({ executablePath: fs.existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined });
  const res = [];
  const ok = (t, c, extra) => { res.push(!!c); console.log(`  ${c ? '✅' : '⛔'} ${t}${extra ? ' ' + extra : ''}`); };

  async function pagina() {
    const pg = await navegador.newPage({ viewport: { width: 1280, height: 760 } });
    const errores = [];
    pg.on('pageerror', e => errores.push(String(e)));
    await pg.goto('file://' + path.join(dir, 'launcher.html'));
    await pg.waitForFunction(() => typeof LU !== 'undefined' && typeof Novedades !== 'undefined' && typeof Noticias !== 'undefined');
    // (la «vista previa» del launcher: el MOCK de launcher.js; set_option se espía para ver lo que se guarda)
    await pg.evaluate(() => { window.__guardado = {}; MOCK.set_option = async (k, v) => { window.__guardado[k] = v; }; });
    await pg.evaluate(() => MOCK.login('prueba', 'x', true, false));
    await pg.waitForTimeout(900);
    return { pg, errores };
  }
  const abierto = pg => pg.evaluate(() => { const o = document.querySelector('#nvOv'); return !!o && o.classList.contains('on'); });
  const titulo = pg => pg.evaluate(() => (document.querySelector('#nvOv h2') || {}).textContent || '');
  const cuerpo = pg => pg.evaluate(() => (document.querySelector('#nvOv .nv-cuerpo') || {}).textContent || '');
  async function actualizar(pg, final = { estado: 'listo', carpeta: 'C:\\Game\\EDA', archivos: 0, mb: 0, nueva: false }) {
    await pg.evaluate(async f => {
      for (let p = 0; p <= 100; p += 25) { LU.edaProg(p, `${p} / 3 MB`); await new Promise(r => setTimeout(r, 40)); }
      LU.edaProg(null); LU.eda(f);
    }, final);
    await pg.waitForTimeout(1200);
  }

  console.log(`la pantalla del launcher: ${n} archivos sacados de ${path.basename(exe)} · parche aplicado`);
  {   // 1. el caso normal
    const { pg, errores } = await pagina();
    await pg.evaluate(ns => LU.publico({ noticias: ns }), [noticia, ...otras]);
    await pg.waitForTimeout(500);
    ok('antes de actualizar: no se abre nada solo', !(await abierto(pg)));
    await actualizar(pg);
    const t = await titulo(pg), c = await cuerpo(pg);
    ok('después de instalar la actualización se abre SOLA', await abierto(pg));
    ok('…con la versión instalada', t.includes(noticia.titulo) && c.includes('Nueva versión instalada'), `«${t}»`);
    ok('…con errores corregidos, mejoras y avisos', ['Errores corregidos', 'Mejoras', 'Avisos importantes'].every(x => c.includes(x)));
    await pg.screenshot({ path: path.join(salida, '1-popup-tras-actualizar.png') });
    ok('…y queda como vista (noticias_vistas, en las prefs del launcher)',
       ((await pg.evaluate(() => window.__guardado.noticias_vistas)) || []).includes(noticia.id));
    await pg.click('#nvOv .nv-x');
    await actualizar(pg);
    ok('★ el revés: otra actualización después → NO se vuelve a abrir (una sola vez)', !(await abierto(pg)));
    ok('sin errores de JavaScript en la pantalla', !errores.length, errores.join(' | '));
    await pg.close();
  }
  {   // 2. reveses
    const { pg } = await pagina();
    await pg.evaluate(ns => LU.publico({ noticias: ns }), [noticia, ...otras]);
    await pg.evaluate(() => LU.eda({ estado: 'listo', carpeta: 'C:\\Game\\EDA' }));
    await pg.waitForTimeout(1000);
    ok('★ el revés: el launcher sólo REVISA (no bajó nada) → no se abre', !(await abierto(pg)));
    await actualizar(pg, { estado: 'error', error: 'no hay conexión' });
    ok('★ el revés: la actualización termina en ERROR → no se abre', !(await abierto(pg)));
    await pg.close();
  }
  {   // 3. con el juego abierto: espera
    const { pg } = await pagina();
    await pg.evaluate(ns => LU.publico({ noticias: ns }), [noticia, ...otras]);
    await pg.evaluate(() => document.body.classList.add('jugando'));
    await actualizar(pg);
    ok('con EDA abierto (jugando) NO se abre encima del juego', !(await abierto(pg)));
    await pg.evaluate(() => document.body.classList.remove('jugando'));
    await pg.waitForTimeout(2600);
    ok('…y se abre al cerrar el juego', await abierto(pg));
    await pg.close();
  }
  {   // 4. las noticias llegan después
    const { pg } = await pagina();
    await actualizar(pg);
    ok('si las noticias todavía no llegaron, no se abre nada raro', !(await abierto(pg)));
    await pg.evaluate(ns => LU.publico({ noticias: ns }), [noticia, ...otras]);
    await pg.waitForTimeout(900);
    ok('…y se abre cuando llegan', await abierto(pg) && (await titulo(pg)).includes(noticia.titulo));
    await pg.close();
  }
  {   // 5. ya la había abierto desde el acordeón
    const { pg } = await pagina();
    await pg.evaluate(ns => LU.publico({ noticias: ns }), [noticia, ...otras]);
    await pg.evaluate(id => { Noticias.abrir(id); Noticias.cerrar(); }, noticia.id);
    await actualizar(pg);
    ok('★ el revés: si ya la leyó en el acordeón, no se repite', !(await abierto(pg)));
    await pg.close();
  }
  await navegador.close();
  fs.rmSync(dir, { recursive: true, force: true });
  const bien = res.every(Boolean);
  console.log(`\n${bien ? '→ TODO BIEN' : '→ ⛔ ALGO FALLA'} (${res.filter(Boolean).length}/${res.length}) · capturas en ${salida}`);
  process.exit(bien ? 0 : 1);
})().catch(e => { console.error(e.message || e); process.exit(1); });
