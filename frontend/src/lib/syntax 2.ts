/**
 * Tiny MicroPython tokenizer for the code well. Discipline: only keywords
 * get the chrome family (ion-dim); comments go faint, numbers bright,
 * strings dim. No grammar, no state — a single master regex per line.
 */

export interface Token {
  text: string;
  cls?: 'tok-kw' | 'tok-comment' | 'tok-num' | 'tok-str';
}

const KEYWORDS = new Set([
  'import',
  'from',
  'class',
  'def',
  'return',
  'for',
  'in',
  'while',
  'if',
  'elif',
  'else',
  'try',
  'except',
  'finally',
  'with',
  'as',
  'pass',
  'raise',
  'not',
  'and',
  'or',
  'None',
  'True',
  'False',
  'self',
  'lambda',
  'global',
  'del',
  'yield',
]);

const MASTER =
  /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)/g;

export function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  for (const m of line.matchAll(MASTER)) {
    const idx = m.index ?? 0;
    if (idx > last) tokens.push({ text: line.slice(last, idx) });
    const [full, comment, str, num, word] = m;
    if (comment) tokens.push({ text: full, cls: 'tok-comment' });
    else if (str) tokens.push({ text: full, cls: 'tok-str' });
    else if (num) tokens.push({ text: full, cls: 'tok-num' });
    else if (word && KEYWORDS.has(word)) tokens.push({ text: full, cls: 'tok-kw' });
    else tokens.push({ text: full });
    last = idx + full.length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last) });
  return tokens;
}
