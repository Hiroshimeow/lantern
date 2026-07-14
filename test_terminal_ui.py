from __future__ import annotations

import ast
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "lan_drive.py"


def extract_js() -> str:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "JS" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, str):
            break
        start = value.index("// ---------------- Terminal drawer ----------------")
        return value[start:]
    raise AssertionError("Could not extract JS terminal implementation")


HARNESS = r"""
const nodeAssert = require('assert');
const listeners = {};
const screenListeners = {};
let selectionText = '';
const selectionNode = {};
let clipboardText = '';
let clipboardReadText = '';
let fetchCalls = [];

function classList(initial = []) {
  const values = new Set(initial);
  return {
    add(...xs) { xs.forEach(x => values.add(x)); },
    remove(...xs) { xs.forEach(x => values.delete(x)); },
    contains(x) { return values.has(x); },
    toggle(x, force) {
      if (force === true) values.add(x);
      else if (force === false) values.delete(x);
      else if (values.has(x)) values.delete(x);
      else values.add(x);
      return values.has(x);
    }
  };
}

const screen = {
  id: 'termScreen', textContent: '', scrollTop: 0, scrollHeight: 400,
  clientHeight: 360, clientWidth: 800, classList: classList(),
  style: {}, focus() { document.activeElement = this; },
  contains(node) { return node === selectionNode || node === this; },
  addEventListener(type, fn) { screenListeners[type] = fn; }
};
const drawer = { id: 'termDrawer', classList: classList(['show']), style: {} };
const elements = {
  termScreen: screen,
  termDrawer: drawer,
  termCommand: { classList: classList(), addEventListener() {} },
  termPrompt: { textContent: '' },
  termLine: {
    value: '', selectionStart: 0, selectionEnd: 0,
    focus() { document.activeElement = this; },
    setRangeText(text, start, end) {
      this.value = this.value.slice(0, start) + text + this.value.slice(end);
      this.selectionStart = this.selectionEnd = start + text.length;
    },
    addEventListener(type, fn) { listeners['line:' + type] = fn; }
  },
  termMode: { textContent: '' },
  termCwd: { textContent: '' },
  termStatus: { textContent: '', dataset: {} },
  termCols: { textContent: '' },
};

const document = {
  activeElement: screen,
  body: { appendChild() {} },
  addEventListener(type, fn) { listeners[type] = fn; },
  createElement() {
    return {
      textContent: '', value: '', style: {},
      getBoundingClientRect() { return { width: 80 }; },
      focus() {}, select() {}, remove() {}
    };
  },
  execCommand() { return true; }
};
const window = {
  addEventListener(type, fn) { listeners['window:' + type] = fn; },
  getSelection() {
    return {
      isCollapsed: !selectionText,
      anchorNode: selectionNode,
      focusNode: selectionNode,
      toString() { return selectionText; }
    };
  }
};
const navigator = { clipboard: {
  async writeText(text) { clipboardText = text; },
  async readText() { return clipboardReadText; }
} };
const defaults = { terminal_max_buffer_chars: 500000, terminal_poll_ms: 150, terminal_enabled: true };
const $ = selector => elements[String(selector).replace(/^#/, '')] || null;
const toast = () => {};
const currentPath = () => '';
const confirm = () => true;
const prompt = () => '';
const getComputedStyle = () => ({
  font: '13px monospace', lineHeight: '19',
  paddingLeft: '16', paddingRight: '16', paddingTop: '12', paddingBottom: '12'
});
const fetch = async (url, options = {}) => {
  fetchCalls.push({ url, options });
  return { ok: true, status: 200, async json() { return { ok: true }; } };
};
"""

TESTS = r"""
async function runTests() {
  term.screen = null;
  termInitScreen();
  termAppend('A表B');
  nodeAssert.strictEqual(term.screen.c, 4, 'CJK character must occupy two terminal cells');
  nodeAssert.strictEqual(screen.textContent, 'A表B');

  term.screen = null;
  termInitScreen();
  termAppend('e\u0301X');
  nodeAssert.strictEqual(term.screen.c, 2, 'combining mark must not advance the cursor');
  nodeAssert.strictEqual(screen.textContent, 'e\u0301X');

  term.screen = null;
  termInitScreen();
  termAppend('\u{1F469}\u200D\u{1F4BB}X');
  nodeAssert.strictEqual(term.screen.c, 3, 'a joined emoji must occupy two cells as one grapheme');
  nodeAssert.strictEqual(screen.textContent, '\u{1F469}\u200D\u{1F4BB}X');

  term.screen = null;
  termInitScreen();
  termAppend('progress 10%\rprogress 20%');
  nodeAssert.strictEqual(screen.textContent, 'progress 20%', 'carriage-return redraw must replace the line in place');

  selectionText = 'selected output';
  let prevented = false;
  term.id = 'session';
  term.mode = 'pty';
  document.activeElement = screen;
  await listeners.keydown({
    ctrlKey: true, metaKey: false, altKey: false, key: 'c', code: 'KeyC',
    preventDefault() { prevented = true; }
  });
  nodeAssert.strictEqual(prevented, false, 'Ctrl+C with a selection must use native browser copy');

  let copied = '';
  screenListeners.copy({
    preventDefault() {},
    clipboardData: { setData(type, value) { if (type === 'text/plain') copied = value; } }
  });
  nodeAssert.strictEqual(copied, 'selected output');

  selectionText = '';
  prevented = false;
  fetchCalls = [];
  await listeners.keydown({
    ctrlKey: true, metaKey: false, altKey: false, key: 'c', code: 'KeyC',
    preventDefault() { prevented = true; }
  });
  nodeAssert.strictEqual(prevented, true, 'Ctrl+C without a selection must interrupt the process');
  nodeAssert.ok(fetchCalls.some(call => call.url === '/api/term/input'), 'SIGINT must reach terminal input API');

  clipboardReadText = 'pasted';
  term.mode = 'command';
  elements.termLine.value = 'echo ';
  elements.termLine.selectionStart = elements.termLine.selectionEnd = 5;
  await termPasteClipboard();
  nodeAssert.strictEqual(elements.termLine.value, 'echo pasted', 'Paste button must insert text into Windows command input');
  nodeAssert.strictEqual(document.activeElement, elements.termLine, 'command input must keep focus after paste');
}

runTests().catch(error => {
  console.error(error && error.stack || error);
  process.exit(1);
});
"""


class TerminalUiTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows command-mode encoding test")
    def test_windows_command_mode_preserves_utf8(self) -> None:
        import lan_drive

        lan_drive.CONFIG = SimpleNamespace(
            terminal_command_timeout=10,
            terminal_shell_windows="powershell",
            terminal_shell_linux="/bin/sh",
            terminal_max_buffer_chars=500000,
        )
        session = lan_drive.TerminalSession("test", "command", ROOT)
        result = lan_drive.terminal_run_command(session, "Write-Output 'A表B'")
        self.assertTrue(result["ok"], result)
        self.assertIn("A表B", result["output"])

    def test_terminal_renderer_and_copy_shortcut(self) -> None:
        script = HARNESS + "\n" + extract_js() + "\n" + TESTS
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
