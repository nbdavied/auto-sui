const state = {
  books: [
    { id: '1183356777640235009', name: '测试账本', provider: 'shenxiang' },
    { id: '1505498391', name: '旧随手记账本', provider: 'legacy' }
  ]
};

function findBook(token) {
  if (!token) return null;
  if (token.includes(':')) {
    const idx = token.indexOf(':');
    const p = token.slice(0, idx);
    const id = token.slice(idx + 1);
    return state.books.find(b => b.provider === p && b.id === id) || null;
  }
  return state.books.find(b => b.id === token) || null;
}

function findBookOld(token) {
  if (!token) return null;
  if (token.includes(':')) {
    const [p, id] = token.split(':', 1);
    return state.books.find(b => b.provider === p && b.id === id) || null;
  }
  return state.books.find(b => b.id === token) || null;
}

const cases = [
  ['legacy:1505498391', 'legacy', '1505498391'],
  ['shenxiang:1183356777640235009', 'shenxiang', '1183356777640235009'],
  ['', null, null],
  ['1505498391', 'legacy', '1505498391']
];

let pass = 0, fail = 0;
for (const [tok, expProvider, expId] of cases) {
  const got = findBook(tok);
  let ok;
  if (expProvider === null) ok = got === null;
  else ok = got && got.provider === expProvider && got.id === expId;
  console.log(ok ? 'PASS' : 'FAIL', JSON.stringify(tok), '=>', got ? got.provider + ':' + got.id : 'null');
  if (ok) pass++; else fail++;
}
console.log('NEW:', pass, '/', cases.length);

const old = findBookOld('legacy:1505498391');
console.log('OLD bug repro:', old ? old.provider + ':' + old.id : 'null (expected: null because old impl drops the id)');
