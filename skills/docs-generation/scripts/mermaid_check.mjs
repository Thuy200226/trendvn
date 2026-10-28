// Parses Mermaid blocks with the real parser. Input: path to a JSON file [{file, line, code}].
// Output: JSON array [{file, line, ok, error}] on stdout. Run by check_mermaid.py from a directory that has
// node_modules/mermaid and node_modules/jsdom; a DOM shim is needed because Mermaid expects a browser.
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });

const mermaid = (await import('mermaid')).default;
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });

const blocks = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const results = [];
for (const b of blocks) {
  try {
    await mermaid.parse(b.code);
    results.push({ file: b.file, line: b.line, ok: true });
  } catch (e) {
    const msg = String((e && e.message) || e).split('\n').slice(0, 4).join(' | ');
    results.push({ file: b.file, line: b.line, ok: false, error: msg });
  }
}
process.stdout.write(JSON.stringify(results));
process.exit(0);
