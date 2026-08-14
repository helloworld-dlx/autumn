import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.className = ''; this._text = ''; }
  append(...nodes) { this.children.push(...nodes); }
  get firstChild() { return this.children[0]; }
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); }
}

const source = await readFile(new URL('./index.html', import.meta.url), 'utf8');
const renderer = source.slice(source.indexOf('function appendInline'), source.indexOf('function show('));
const markdown = new Function('document', `${renderer}; return markdown;`)({
  createElement: (tagName) => new Element(tagName),
  createTextNode: (text) => ({ tagName: '#text', textContent: String(text) }),
});

function find(root, tagName) {
  if (root.tagName === tagName) return root;
  for (const child of root.children || []) { const found = find(child, tagName); if (found) return found; }
}

test('Markdown fenced code creates pre and code DOM', () => {
  const root = markdown('```\nconst answer = 42;\n```');
  const pre = find(root, 'pre');
  assert.equal(pre.firstChild.tagName, 'code');
  assert.equal(pre.firstChild.textContent, 'const answer = 42;');
});

test('Markdown tables create table DOM', () => {
  const root = markdown('| Name | Value |\n| --- | --- |\n| Autumn | Ready |');
  assert.equal(find(root, 'table').tagName, 'table');
});

test('Markdown keeps plain text and escapes HTML', () => {
  const root = markdown('普通文本\n<script>alert(1)</script>');
  assert.equal(root.children[0].tagName, 'p');
  assert.equal(root.children[0].children[0].textContent, '普通文本');
  assert.equal(find(root, 'script'), undefined);
  assert.equal(root.children[1].children[0].textContent, '<script>alert(1)</script>');
});
