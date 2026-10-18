"""MD-T003 isolated CodeMirror 6 merge/unified Source POC.

Opt in:
    set LANTERN_CM_POC=1
    python -m unittest -v tests.test_md_source_merge_e2e

The POC installs exact packages below .plan only. It does not wire writes into
Lantern and does not modify package.json/package-lock.json. A green harness may
record a NO-GO conclusion when the fixed 5,500-line product target is missed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / ".plan" / "lantern-markdown-main-20261018"
DEPS = PLAN / "cm6-merge-poc-deps"
EVIDENCE = PLAN / "dev_turn9_md_source_merge.json"

MERGE_VERSION = "6.12.2"
CM_VERSION = "6.0.2"
ESBUILD_VERSION = "0.28.2"
MERGE_INTEGRITY = (
    "sha512-V8JvyAPjHbPupqP7BeMcsdsYCbyPij74jxIbaIJDORI+VZzW44zFmon8bF+"
    "oxGWvOKhcRmkiUMXd8MxHr3YA2w=="
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3)


def _lines(count: int, width: int = 45) -> str:
    return "\n".join(
        f"{index:06d} " + ("x" * width) for index in range(count)
    ) + "\n"


def _sized_text(target_bytes: int, width: int) -> str:
    seed = _lines(1024, width)
    repeats = target_bytes // len(seed.encode("utf-8")) + 2
    text = seed * repeats
    raw = text.encode("utf-8")
    return raw[:target_bytes].decode("utf-8", errors="ignore")


def _raw_patch_utf8(
    raw: bytes,
    start_utf16: int,
    end_utf16: int,
    insert: str,
) -> bytes:
    bom = raw.startswith(b"\xef\xbb\xbf")
    payload = raw[3:] if bom else raw
    text = payload.decode("utf-8")
    utf16 = text.encode("utf-16-le")
    prefix = utf16[: start_utf16 * 2].decode("utf-16-le").encode("utf-8")
    suffix = utf16[end_utf16 * 2 :].decode("utf-16-le").encode("utf-8")
    return (
        (b"\xef\xbb\xbf" if bom else b"")
        + prefix
        + insert.encode("utf-8")
        + suffix
    )


ENTRY = r"""
import {EditorView, keymap} from "@codemirror/view";
import {EditorState, ChangeSet} from "@codemirror/state";
import {history, historyKeymap, undo, redo} from "@codemirror/commands";
import {
  unifiedMergeView, MergeView, getChunks, getOriginalDoc, originalDocChangeEffect
} from "@codemirror/merge";

const stats={updates:0,docChanges:0,serializations:0};
let view=null, split=null;

function createUnified(parent, original, current, lineSeparator="\n") {
  if (view) view.destroy();
  parent.textContent="";
  stats.updates=stats.docChanges=stats.serializations=0;
  view=new EditorView({
    state:EditorState.create({
      doc:current,
      extensions:[
        EditorState.lineSeparator.of(lineSeparator),
        history(),
        keymap.of(historyKeymap),
        EditorView.lineWrapping,
        EditorView.updateListener.of(update=>{
          stats.updates++;
          if(update.docChanged) stats.docChanges++;
        }),
        unifiedMergeView({
          original,
          highlightChanges:true,
          gutter:true,
          mergeControls:false
        })
      ]
    }),
    parent
  });
  return snapshot();
}

function snapshot() {
  const chunks=getChunks(view.state);
  return {
    length:view.state.doc.length,
    lines:view.state.doc.lines,
    originalLength:getOriginalDoc(view.state).length,
    chunkCount:chunks?.chunks?.length||0,
    domLines:view.dom.querySelectorAll(".cm-line").length,
    changedLines:view.dom.querySelectorAll(".cm-changedLine").length,
    deletedChunks:view.dom.querySelectorAll(
      ".cm-deletedChunk,.cm-deletedLine,.cm-deletedText"
    ).length,
    gutters:view.dom.querySelectorAll(".cm-gutter").length,
    active:document.activeElement===view.contentDOM,
    selection:{
      from:view.state.selection.main.from,
      to:view.state.selection.main.to
    },
    updates:stats.updates,
    docChanges:stats.docChanges,
    serializations:stats.serializations
  };
}

function setSelection(from,to=from) {
  view.dispatch({selection:{anchor:from,head:to}});
  view.focus();
  return snapshot();
}

function getDoc() {
  stats.serializations++;
  return view.state.sliceDoc();
}

function getOriginal() {
  return getOriginalDoc(view.state).toString();
}

function updateOriginal(text) {
  const old=getOriginalDoc(view.state);
  const changes=ChangeSet.of(
    {from:0,to:old.length,insert:text},
    old.length
  );
  const before=view.state.doc;
  view.dispatch({
    effects:originalDocChangeEffect(view.state,changes)
  });
  return {
    sameCurrent:view.state.doc.eq(before),
    ...snapshot()
  };
}

function doUndo() {
  undo(view);
  return snapshot();
}

function doRedo() {
  redo(view);
  return snapshot();
}

function createSplit(parent,a,b) {
  if(split) split.destroy();
  parent.textContent="";
  split=new MergeView({
    a:{doc:a},
    b:{doc:b},
    parent,
    highlightChanges:true,
    gutter:true,
    mergeControls:false
  });
  return {
    aLines:split.a.state.doc.lines,
    bLines:split.b.state.doc.lines,
    domLines:parent.querySelectorAll(".cm-line").length
  };
}

window.CMPoc={
  createUnified,
  snapshot,
  setSelection,
  getDoc,
  getOriginal,
  updateOriginal,
  doUndo,
  doRedo,
  createSplit,
  get view(){return view}
};
"""


@unittest.skipUnless(
    os.environ.get("LANTERN_CM_POC") == "1",
    "CodeMirror merge POC opt-in",
)
class CodeMirrorMergePocE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.package_before = _sha(ROOT / "package.json")
        cls.lock_before = _sha(ROOT / "package-lock.json")
        DEPS.mkdir(parents=True, exist_ok=True)

        npm = "npm.cmd" if os.name == "nt" else "npm"
        install = subprocess.run(
            [
                npm,
                "install",
                "--prefix",
                str(DEPS),
                "--no-save",
                "--package-lock=false",
                f"@codemirror/merge@{MERGE_VERSION}",
                f"codemirror@{CM_VERSION}",
                f"esbuild@{ESBUILD_VERSION}",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        (PLAN / "dev_turn9_cm6_npm_install.log").write_text(
            install.stdout,
            encoding="utf-8",
        )

        merge_pkg = json.loads(
            (DEPS / "node_modules/@codemirror/merge/package.json").read_text(
                encoding="utf-8"
            )
        )
        cm_pkg = json.loads(
            (DEPS / "node_modules/codemirror/package.json").read_text(
                encoding="utf-8"
            )
        )
        esbuild_pkg = json.loads(
            (DEPS / "node_modules/esbuild/package.json").read_text(
                encoding="utf-8"
            )
        )
        hidden_lock = json.loads(
            (DEPS / "node_modules/.package-lock.json").read_text(
                encoding="utf-8"
            )
        )
        merge_lock = hidden_lock["packages"]["node_modules/@codemirror/merge"]
        cls.package_evidence = {
            "mergeVersion": merge_pkg["version"],
            "mergeLicense": merge_pkg["license"],
            "mergeIntegrity": merge_lock["integrity"],
            "codemirrorVersion": cm_pkg["version"],
            "esbuildVersion": esbuild_pkg["version"],
        }

        cls.assertEqual = unittest.TestCase().assertEqual
        cls.assertEqual(cls.package_evidence["mergeVersion"], MERGE_VERSION)
        cls.assertEqual(cls.package_evidence["mergeLicense"], "MIT")
        cls.assertEqual(cls.package_evidence["mergeIntegrity"], MERGE_INTEGRITY)
        cls.assertEqual(cls.package_evidence["codemirrorVersion"], CM_VERSION)
        cls.assertEqual(cls.package_evidence["esbuildVersion"], ESBUILD_VERSION)
        cls.assertEqual(_sha(ROOT / "package.json"), cls.package_before)
        cls.assertEqual(_sha(ROOT / "package-lock.json"), cls.lock_before)

        entry = DEPS / "entry.js"
        bundle = DEPS / "cm6-poc.js"
        entry.write_text(ENTRY, encoding="utf-8")
        esbuild = DEPS / "node_modules/.bin/esbuild.cmd"
        build = subprocess.run(
            [
                str(esbuild),
                str(entry),
                "--bundle",
                "--format=iife",
                "--platform=browser",
                "--target=chrome114",
                f"--outfile={bundle}",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        (PLAN / "dev_turn9_cm6_build.log").write_text(
            build.stdout,
            encoding="utf-8",
        )
        cls.bundle = bundle

        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(channel="msedge", headless=True)
        cls.browser_version = cls.browser.version

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.browser.close()
            cls.play.stop()
        finally:
            if _sha(ROOT / "package.json") != cls.package_before:
                raise AssertionError("POC changed package.json")
            if _sha(ROOT / "package-lock.json") != cls.lock_before:
                raise AssertionError("POC changed package-lock.json")

    def _new_page(self):
        page = self.browser.new_page(
            viewport={"width": 1200, "height": 700}
        )
        page.set_content(
            "<html><body>"
            "<div id='app' style='height:600px;overflow:auto'></div>"
            "</body></html>"
        )
        page.add_script_tag(path=str(self.bundle))
        return page

    def _typing_probe(
        self,
        text: str,
        typed: str = "benchmark",
    ) -> dict[str, object]:
        page = self._new_page()
        navigations: list[str] = []
        page.on(
            "framenavigated",
            lambda frame: navigations.append(frame.url)
            if frame == page.main_frame
            else None,
        )
        try:
            page.evaluate(
                """text => CMPoc.createUnified(
                  document.getElementById('app'), text, text
                )""",
                text,
            )
            initial = page.evaluate("() => CMPoc.snapshot()")
            page.evaluate(
                """() => {
                  const host=CMPoc.view.contentDOM;
                  window.__pocMetrics={
                    paint:[],long:[],mutations:0,added:0,removed:0,
                    maxAdded:0,maxRemoved:0,inputs:0
                  };
                  new MutationObserver(records=>{
                    for(const record of records){
                      __pocMetrics.mutations++;
                      __pocMetrics.added+=record.addedNodes.length;
                      __pocMetrics.removed+=record.removedNodes.length;
                      __pocMetrics.maxAdded=Math.max(
                        __pocMetrics.maxAdded,
                        record.addedNodes.length
                      );
                      __pocMetrics.maxRemoved=Math.max(
                        __pocMetrics.maxRemoved,
                        record.removedNodes.length
                      );
                    }
                  }).observe(host,{childList:true,subtree:true});
                  try{
                    new PerformanceObserver(list=>{
                      __pocMetrics.long.push(
                        ...list.getEntries().map(entry=>entry.duration)
                      );
                    }).observe({type:'longtask',buffered:true});
                  }catch(_){}
                  host.addEventListener('input',()=>{
                    const start=performance.now();
                    __pocMetrics.inputs++;
                    requestAnimationFrame(
                      ()=>__pocMetrics.paint.push(performance.now()-start)
                    );
                  },true);
                  CMPoc.setSelection(0);
                  CMPoc.view.focus();
                }"""
            )
            navigations.clear()
            wall: list[float] = []
            for char in typed:
                start = time.perf_counter()
                page.keyboard.type(char)
                wall.append((time.perf_counter() - start) * 1000)
                page.wait_for_timeout(40)
            page.wait_for_timeout(250)

            final = page.evaluate("() => CMPoc.snapshot()")
            metrics = page.evaluate("() => window.__pocMetrics")
            return {
                "bytes": len(text.encode("utf-8")),
                "lines": text.count("\n"),
                "typedInputs": len(typed),
                "keyWallMs": [round(value, 3) for value in wall],
                "keyWallP95Ms": _p95(wall),
                "inputPaintP95Ms": _p95(
                    [float(value) for value in metrics["paint"]]
                ),
                "longTaskCount": len(metrics["long"]),
                "longTaskMaxMs": round(
                    max(metrics["long"], default=0),
                    3,
                ),
                "domLinesBefore": initial["domLines"],
                "domLinesAfter": final["domLines"],
                "mutationRecords": metrics["mutations"],
                "domAdded": metrics["added"],
                "domRemoved": metrics["removed"],
                "maxAdded": metrics["maxAdded"],
                "maxRemoved": metrics["maxRemoved"],
                "serializationCallsDuringTyping": final["serializations"],
                "focusPreserved": final["active"],
                "caret": final["selection"],
                "navigationCount": len(navigations),
            }
        finally:
            page.close()

    def test_unified_merge_poc(self) -> None:
        report: dict[str, object] = {
            "schema": 1,
            "browser": {
                "channel": "msedge",
                "version": self.browser_version,
            },
            "packages": self.package_evidence,
        }

        page = self._new_page()
        try:
            original = (
                "same line\n"
                "changed old\n"
                "removed line\n"
                "end old\n"
            )
            current = (
                "same LINE\n"
                "changed new\n"
                "end old\n"
                "bottom added\n"
            )
            functional = page.evaluate(
                """({original,current}) => {
                  const initial=CMPoc.createUnified(
                    document.getElementById('app'),
                    original,
                    current
                  );
                  const classes=[...new Set(
                    [...document.querySelectorAll('[class*="cm-"]')]
                      .map(element=>element.className)
                      .filter(value=>typeof value==='string')
                  )];
                  CMPoc.setSelection(2,7);
                  return {
                    initial,
                    selected:CMPoc.snapshot(),
                    classes
                  };
                }""",
                {"original": original, "current": current},
            )
            self.assertGreaterEqual(functional["initial"]["chunkCount"], 2)
            self.assertGreater(functional["initial"]["changedLines"], 0)
            self.assertGreater(functional["initial"]["deletedChunks"], 0)
            self.assertGreater(functional["initial"]["gutters"], 0)
            self.assertTrue(
                any("cm-deletedChunk" in value for value in functional["classes"])
            )
            self.assertTrue(
                any("cm-changedLine" in value for value in functional["classes"])
            )
            self.assertEqual(
                functional["selected"]["selection"],
                {"from": 2, "to": 7},
            )

            page.keyboard.type("Z")
            typed_doc = page.evaluate("() => CMPoc.getDoc()")
            undo_doc = page.evaluate(
                "() => {CMPoc.doUndo(); return CMPoc.getDoc()}"
            )
            redo_doc = page.evaluate(
                "() => {CMPoc.doRedo(); return CMPoc.getDoc()}"
            )
            self.assertNotEqual(typed_doc, undo_doc)
            self.assertEqual(typed_doc, redo_doc)

            new_baseline = (
                "same line\n"
                "changed accepted\n"
                "removed line\n"
                "end old\n"
            )
            baseline = page.evaluate(
                """text => {
                  const before=CMPoc.getDoc();
                  const update=CMPoc.updateOriginal(text);
                  return {
                    before,
                    after:CMPoc.getDoc(),
                    original:CMPoc.getOriginal(),
                    update
                  };
                }""",
                new_baseline,
            )
            self.assertTrue(baseline["update"]["sameCurrent"])
            self.assertEqual(baseline["before"], baseline["after"])
            self.assertEqual(baseline["original"], new_baseline)

            crlf = page.evaluate(
                """() => {
                  const host=document.getElementById('app');
                  CMPoc.createUnified(
                    host,
                    'a\\r\\nb\\r\\n',
                    'a\\r\\nb\\r\\n',
                    '\\r\\n'
                  );
                  CMPoc.setSelection(0);
                  return CMPoc.getDoc();
                }"""
            )
            self.assertEqual(crlf, "a\r\nb\r\n")

            split = page.evaluate(
                """({a,b}) => {
                  const host=document.createElement('div');
                  document.body.appendChild(host);
                  return CMPoc.createSplit(host,a,b);
                }""",
                {"a": original, "b": current},
            )
            self.assertGreaterEqual(split["domLines"], 2)
            report["functional"] = {
                "unified": functional,
                "addChangeDeleteAndBottom": True,
                "inlineGutterDeletionAffordances": True,
                "keyboardSelection": True,
                "undoRedo": True,
                "uniformCrlfSliceDocPreserved": True,
                "baselineUpdatePreservesCurrent": True,
            }
            report["splitComparison"] = split
        finally:
            page.close()

        raw = (
            b"\xef\xbb\xbf"
            + "# T\r\n\r\n日本語 🏮\nBefore\nEDIT_TARGET\r\nTail".encode(
                "utf-8"
            )
        )
        decoded = raw[3:].decode("utf-8")
        marker_chars = decoded.index("EDIT_TARGET")
        marker_start = len(
            decoded[:marker_chars].encode("utf-16-le")
        ) // 2
        marker_end = marker_start + (
            len("EDIT_TARGET".encode("utf-16-le")) // 2
        )
        patched = _raw_patch_utf8(
            raw,
            marker_start,
            marker_end,
            "EDIT_TARGET_X",
        )
        expected = raw.replace(
            b"EDIT_TARGET",
            b"EDIT_TARGET_X",
            1,
        )
        self.assertEqual(patched, expected)
        self.assertTrue(patched.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", patched)
        self.assertIn("日本語 🏮".encode("utf-8"), patched)
        self.assertIn(b"Before\n", patched)
        report["byteStrategy"] = {
            "bomPreserved": True,
            "mixedEolUntouchedBytesPreserved": True,
            "nonBmpBoundaryCovered": True,
            "strategy": (
                "CodeMirror transaction UTF-16 range -> authoritative "
                "raw UTF-8 byte patch; never whole-document serialization"
            ),
        }

        page = self._new_page()
        try:
            cjk = "日本語 中文 🏮\n"
            page.evaluate(
                """text => CMPoc.createUnified(
                  document.getElementById('app'),
                  text,
                  text
                )""",
                cjk,
            )
            page.evaluate(
                "() => {CMPoc.setSelection(0); CMPoc.view.focus()}"
            )
            page.keyboard.insert_text("かな")
            cjk_doc = page.evaluate("() => CMPoc.getDoc()")
            self.assertTrue(cjk_doc.startswith("かな日本語"))
            page.evaluate(
                """() => {
                  const element=CMPoc.view.contentDOM;
                  element.dispatchEvent(new CompositionEvent(
                    'compositionstart',
                    {bubbles:true,data:''}
                  ));
                  element.dispatchEvent(new CompositionEvent(
                    'compositionupdate',
                    {bubbles:true,data:'漢字'}
                  ));
                  element.dispatchEvent(new CompositionEvent(
                    'compositionend',
                    {bubbles:true,data:'漢字'}
                  ));
                }"""
            )
            report["ime"] = {
                "cjkInsertText": True,
                "syntheticComposition": (
                    "events-dispatched-only; NOT native Windows IME acceptance"
                ),
            }
        finally:
            page.close()

        perf = {
            "lines5500": self._typing_probe(_lines(5500, 45)),
            "bytes500k": self._typing_probe(
                _sized_text(500_000, 55)
            ),
            "bytes5m": self._typing_probe(
                _sized_text(4_800_000, 950),
                "bench",
            ),
        }
        for name, item in perf.items():
            self.assertLess(
                item["domLinesAfter"],
                300,
                (name, item),
            )
            self.assertLess(
                item["maxAdded"],
                300,
                (name, item),
            )
            self.assertEqual(
                item["serializationCallsDuringTyping"],
                0,
                (name, item),
            )
            self.assertTrue(item["focusPreserved"], (name, item))
            self.assertEqual(item["navigationCount"], 0, (name, item))

        fixed = perf["lines5500"]
        fixed_pass = bool(
            fixed["keyWallP95Ms"] is not None
            and fixed["keyWallP95Ms"] < 40.0
            and fixed["maxAdded"] < 300
            and fixed["domLinesAfter"] < 300
        )
        report["performance"] = perf
        report["fixed5500Target"] = {
            "keyWallP95LtMs": 40.0,
            "noFullDocumentDomRebuild": True,
            "pocMeetsTarget": fixed_pass,
        }
        report["conclusion"] = (
            "GO_WITH_CONSTRAINTS"
            if fixed_pass
            else "NO_GO_CURRENT_UNIFIED_CONFIG_AT_FIXED_5500_TARGET"
        )
        report["alternativeReviewQuestion"] = (
            None
            if fixed_pass
            else (
                "Benchmark mature Monaco DiffEditor before authorizing "
                "any custom diff editor. Split CodeMirror MergeView remains "
                "comparison-only because it duplicates editor surfaces."
            )
        )
        report["constraints"] = [
            (
                "real .md bytes stay authoritative; CodeMirror state is "
                "decoded editor text only"
            ),
            (
                "retain BOM/newline metadata and raw-byte patch adapter "
                "for exact persistence"
            ),
            (
                "mixed EOL cannot be preserved by whole-document "
                "CodeMirror serialization"
            ),
            (
                "synthetic composition coverage is not native Windows "
                "IME acceptance"
            ),
            (
                "5 MB is characterization only; no pass threshold was "
                "invented"
            ),
        ]
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        self.assertEqual(
            _sha(ROOT / "package.json"),
            self.package_before,
        )
        self.assertEqual(
            _sha(ROOT / "package-lock.json"),
            self.lock_before,
        )


if __name__ == "__main__":
    unittest.main()
