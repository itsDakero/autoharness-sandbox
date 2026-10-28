// Headless smoke test: loads dist/index.html with a fake DOM and renders every tab.
// Usage: node tests/run.js [path/to/save.json]
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'dist', 'index.html'), 'utf8');
const code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
const el = () => ({ options: [], appendChild() {}, addEventListener() {}, style: {}, set innerHTML(v) { this._h = v }, get innerHTML() { return this._h }, textContent: '', value: '', disabled: false, dataset: {}, scrollIntoView() {} });
const els = {};
global.document = { getElementById: id => els[id] || (els[id] = el()), createElement: () => ({}), querySelector: () => el(), querySelectorAll: () => [] };
global.window = { scrollTo() {} }; global.localStorage = { getItem: () => null, setItem() {} };
const __save = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2], 'utf8')) : null;
const txt = h => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
eval(code + `
if (__save) S = Object.assign(S, __save.data || __save.state || __save);
for (const tab of ['play','guide','team','battle','dex']) { S.tab = tab; const t0 = Date.now(); render(); console.log(tab.padEnd(6), (Date.now()-t0)+'ms', txt(els.main._h).slice(0, 160)); }
S.beaten.champion = true; S.tab = 'team'; render();
if (!txt(els.main._h).includes('Lock Hall of Fame team')) throw new Error('no lock button');
if (S.team.length) { lockHof(); const sp0 = S.hof.nine[0].sp; S.cards = { 0: { sp: sp0, id: 'x-1', name: 'Test', n: '1', set: 'Set', rarity: 'Ultra Rare', image: 'http://x/y', got: true } }; }
render(); if (S.team.length && !txt(els.main._h).includes('Binder')) throw new Error('no binder');
console.log('cards ', S.team.length ? 'Binder ok' : 'no team in this save (lock skipped)');
console.log('OK');
`);
