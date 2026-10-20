// Node.js, sem dependências: instalação, identidade visual e contraste.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../frontend');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.webmanifest')));
assert.equal(manifest.display, 'standalone');
assert.equal(manifest.scope, '/');
assert.ok(manifest.start_url.startsWith('/'));
assert.equal(manifest.prefer_related_applications, false);
for (const size of [192, 512]) {
  const icon = manifest.icons.find(i => i.sizes === `${size}x${size}` && i.purpose === 'any');
  assert.ok(icon);
  const png = fs.readFileSync(path.join(root, icon.src));
  assert.equal(png.readUInt32BE(16), size);
  assert.equal(png.readUInt32BE(20), size);
}
function luminance(hex) {
  const rgb=hex.match(/[0-9a-f]{2}/gi).map(n=>parseInt(n,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
  return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
for (const [fg,bg] of [['FFFFFF','111111'],['FFFFFF','1E1E1E'],['BBBBBB','111111'],['BBBBBB','1E1E1E'],['111111','FFD700'],['111111','2ECC71'],['FFD700','1E1E1E'],['2ECC71','1E1E1E']]) {
  assert.ok(contrast(fg,bg)>=4.5,`${fg}/${bg} contrast`);
  console.log(`${fg}/${bg}: ${contrast(fg,bg).toFixed(2)}:1`);
}
const css=fs.readFileSync(path.join(root,'style.css'),'utf8');
assert.ok(css.startsWith(':root{color-scheme:dark;'));
for(const color of ['#111111','#1E1E1E','#FFD700','#FFFFFF','#BBBBBB','#2ECC71'])assert.ok(css.includes(color));
assert.equal(manifest.background_color,'#111111');assert.equal(manifest.theme_color,'#1E1E1E');
for(const asset of ['logo.svg','symbol.svg'])assert.ok(fs.readFileSync(path.join(root,asset),'utf8').includes('#FFD700'));
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
assert.ok(html.includes('rel="manifest"'));
assert.ok(html.includes('src="/logo.svg"'));assert.ok(!html.includes('theme-toggle'));
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
assert.ok(app.includes("cache:'no-store'"));
for(const filename of ['install.js','app.js','ai.js']) {
  const s=fs.readFileSync(path.join(root,filename),'utf8');
  assert.ok(!s.includes('serviceWorker.register'));
  assert.ok(!s.includes('caches.open'));
  assert.ok(!s.includes('indexedDB'));
  assert.ok(!s.includes('localStorage'));
  assert.ok(!s.includes('GEMINI_API_KEY'));
  assert.ok(!s.includes('x-goog-api-key'));
}
console.log('OK: manifest, ícones 192/512, standalone, identidade escura, contraste AA e API sem cache.');
