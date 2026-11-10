// Deliberately small DOM helpers: client documents are always text, never HTML.
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'text') el.textContent = String(value);
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (['value', 'checked', 'disabled'].includes(key)) el[key] = value;
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

const paths = {
  plus: ['M12 5v14M5 12h14'],
  arrow: ['M5 12h14M13 6l6 6-6 6'],
  back: ['M19 12H5M11 6l-6 6 6 6'],
  chevron: ['m9 5 7 7-7 7'],
  down: ['m6 9 6 6 6-6'],
  search: ['M21 21l-5.2-5.2', 'M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0'],
  folder: ['M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z'],
  file: ['M14 2H5v20h14V7Z', 'M14 2v6h5M8 12h8M8 16h6'],
  upload: ['M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5'],
  check: ['m5 12 4 4L19 6'],
  clock: ['M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', 'M12 6v6l4 2'],
  message: ['M21 11a8 8 0 0 1-8 8H8l-5 3V7a5 5 0 0 1 5-5h5a8 8 0 0 1 8 9Z', 'M7 8h10M7 12h7'],
  settings: ['M4 7h16M4 17h16', 'M8 4v6M16 14v6'],
  person: ['M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0', 'M4 22v-3a8 8 0 0 1 16 0v3'],
  refresh: ['M20 7a9 9 0 1 0 1 8M20 2v6h-6'],
  copy: ['M9 9h12v13H9Z', 'M15 6V2H3v14h3'],
  info: ['M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', 'M12 11v6M12 7h.01'],
  close: ['M6 6l12 12M18 6 6 18'],
  shield: ['M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z', 'm8 12 3 3 5-6'],
  more: ['M5 12h.01M12 12h.01M19 12h.01'],
  external: ['M14 3h7v7M10 14 21 3M10 3H3v18h18v-7'],
  spark: ['m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z'],
};
export function icon(name, cls = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':'1.6', 'stroke-linecap':'round', 'stroke-linejoin':'round', 'aria-hidden':'true', class:`icon ${cls}`})) svg.setAttribute(key, value);
  for (const d of paths[name] || paths.file) {
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', d); svg.append(path);
  }
  return svg;
}

export function safeLink(value) {
  try {const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;} catch {return null;}
}
function inline(text, openLink) {
  // A bounded subset of Markdown; no images, HTML interpretation, or arbitrary URL protocols.
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\))/g).filter(Boolean).map(part => {
    if (part.startsWith('**') && part.endsWith('**')) return h('strong', {text:part.slice(2,-2)});
    if (part.startsWith('`') && part.endsWith('`')) return h('code', {text:part.slice(1,-1)});
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {const href = safeLink(link[2]); return href ? h('a', {href, target:'_blank', rel:'noopener noreferrer', text:link[1],onclick:openLink?e=>{e.preventDefault();openLink(href);}:null}) : part;}
    return part;
  });
}
export function prose(text, openLink) {
  const article = h('article', {class:'prose'});
  const lines = String(text).replaceAll('\r\n','\n').split('\n');
  let paragraph = [], list = null, quote = [], code = null;
  function flush() {
    if (paragraph.length) article.append(h('p', {}, inline(paragraph.join(' '),openLink)));
    if (quote.length) article.append(h('blockquote', {}, inline(quote.join(' '),openLink)));
    paragraph = []; quote = []; list = null;
  }
  for (const line of lines) {
    if (line.startsWith('```')) {
      flush(); if (code !== null) {article.append(h('pre', {}, h('code', {text:code.join('\n')}))); code = null;} else code = [];
      continue;
    }
    if (code !== null) {code.push(line); continue;}
    if (!line.trim()) {flush(); continue;}
    const head = line.match(/^(#{1,6})\s+(.+)$/);
    if (head) {flush(); article.append(h(`h${Math.min(head[1].length+1,6)}`, {}, inline(head[2],openLink))); continue;}
    const item = line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
    if (item) {
      const tag = item[1] ? 'ul' : 'ol';
      if (!list || list.tagName.toLowerCase() !== tag) {flush(); list = h(tag); article.append(list);}
      list.append(h('li', {}, inline(item[2],openLink))); continue;
    }
    if (/^>\s?/.test(line)) {if (paragraph.length || list) flush(); quote.push(line.replace(/^>\s?/,'')); continue;}
    if (/^[-*_]{3,}$/.test(line.trim())) {flush(); article.append(h('hr')); continue;}
    if (list || quote.length) flush(); paragraph.push(line);
  }
  flush(); if (code !== null) article.append(h('pre', {text:code.join('\n')}));
  return article;
}
