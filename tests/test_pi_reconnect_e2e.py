"""PI-T003 lossless replay feasibility proof.

Explicit run:
  LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e

The proof does not modify Lantern production code. It uses the repository's
vendored xterm for raw-tail falsification and a temporary, version-compatible
@xterm/headless@6.0.0 + @xterm/addon-serialize@0.14.0 install for upstream
serialization feasibility.
"""
from __future__ import annotations

import html
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from lantern.terminal import NativePty, TerminalManager
from lantern.ws import WebSocketHub, dispatch

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / ".plan" / "lantern-pi-native-20261018" / "evidence-turn6"


def _edge() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return next((p for p in candidates if p.is_file()), None)


def _vendored_raw_results() -> dict:
    edge = _edge()
    if not edge:
        raise unittest.SkipTest("Microsoft Edge is required for exact vendored-xterm proof")
    vendor = (ROOT / "static/vendor/xterm.js").resolve().as_uri()
    script = r"""
const write=(t,d)=>new Promise(r=>t.write(d,r));
const cell=c=>({ch:c.getChars(),w:c.getWidth(),fg:c.getFgColor(),bg:c.getBgColor(),
 fgm:c.getFgColorMode(),bgm:c.getBgColorMode(),b:c.isBold(),i:c.isItalic(),
 u:c.isUnderline(),v:c.isInverse(),d:c.isDim(),k:c.isBlink(),x:c.isInvisible(),s:c.isStrikethrough()});
const snap=t=>{const b=t.buffer.active,rows=[];for(let y=0;y<t.rows;y++){const l=b.getLine(b.viewportY+y),r=[];
 if(l)for(let x=0;x<t.cols;x++)r.push(cell(l.getCell(x)));rows.push(r)}
 return {cols:t.cols,rows:t.rows,type:b.type,cx:b.cursorX,cy:b.cursorY,base:b.baseY,view:b.viewportY,
  modes:t.modes?JSON.parse(JSON.stringify(t.modes)):null,cells:rows}};
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
async function replay(chunks,o={}){const cols=o.cols||20,rows=o.rows||6;
 const a=new Terminal({cols,rows,scrollback:100,allowProposedApi:true});for(const c of chunks)await write(a,c);if(o.resize)a.resize(...o.resize);
 const ref=snap(a);let raw=chunks.join('');if(o.tail!=null)raw=raw.slice(-o.tail);
 const b=new Terminal({cols:o.replayCols||a.cols,rows:o.replayRows||a.rows,scrollback:100,allowProposedApi:true});await write(b,raw);
 return {equal:eq(ref,snap(b)),ref,recon:snap(b)}}
(async()=>{const r={};
 r.split=await replay(['A\x1b[3','1mRED\x1b[0','mZ']);
 r.alt=await replay(['normal\x1b[?1049h','ALT\x1b[2;5H@']);
 r.altExit=await replay(['BASE\x1b[2;4H\x1b[1;32mN\x1b[0m','\x1b[?1049hALT\x1b[3;7H\x1b[4;35m@\x1b[0m','\x1b[?1049l']);
 r.style=await replay(['hello','\x1b[2;4H\x1b[1;34mX\x1b[0m\x1b[K']);
 r.truncated=await replay(['base line\r\n','\x1b[31mRED\x1b[0m\r\n','\x1b[2A\x1b[5G!'],{tail:9});
 r.modes=await replay(['\x1b[?2004h\x1b[?1h\x1b[?1004h','MODE']);
 r.resize=await replay(['0123456789ABCDEFGHIJ','\r\nTAIL'],{cols:10,resize:[16,6]});
 r.width=await replay(['0123456789ABCDEFGHIJ\r\nEND'],{cols:12,replayCols:20});
 document.getElementById('out').textContent='RESULT:'+JSON.stringify(r);
})().catch(e=>document.getElementById('out').textContent='ERROR:'+String(e));
"""
    with tempfile.TemporaryDirectory(prefix="lantern-replay-edge-") as td:
        page = Path(td) / "probe.html"
        page.write_text(
            f"<!doctype html><meta charset=utf-8><pre id=out></pre>"
            f"<script src={json.dumps(vendor)}></script><script>{script}</script>",
            encoding="utf-8",
        )
        cp = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--virtual-time-budget=3000",
                "--dump-dom",
                page.as_uri(),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    if cp.returncode:
        raise AssertionError(f"Edge vendored-xterm probe failed: {cp.stderr[-1000:]}")
    marker = "RESULT:"
    if marker not in cp.stdout:
        raise AssertionError(f"vendored-xterm result missing: {cp.stdout[-1200:]}")
    raw = html.unescape(cp.stdout.split(marker, 1)[1].split("</pre>", 1)[0])
    return json.loads(raw)


def _upstream_results() -> dict:
    modules = Path(tempfile.gettempdir()) / "lantern-pi-replay-proof6" / "node_modules"
    if not (modules / "@xterm" / "headless").is_dir() or not (
        modules / "@xterm" / "addon-serialize"
    ).is_dir():
        raise unittest.SkipTest(
            "temporary xterm replay dependencies unavailable; install outside repo: "
            "@xterm/headless@6.0.0 @xterm/addon-serialize@0.14.0"
        )
    probe = EVIDENCE / "replay_probe.js"
    if not probe.is_file():
        raise unittest.SkipTest("ignored PI-T003 replay probe helper unavailable")
    env = os.environ.copy()
    env["NODE_PATH"] = str(modules)
    cp = subprocess.run(
        ["node", str(probe)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if cp.returncode:
        raise AssertionError(f"upstream serializer probe failed: {cp.stderr[-1200:]}")
    return json.loads(cp.stdout)


def _real_pi_headless_cross_stack_results() -> dict:
    edge = _edge()
    if not edge:
        raise unittest.SkipTest("Microsoft Edge is required for real-Pi cross-stack proof")

    evidence = ROOT / ".plan" / "lantern-pi-native-20261018" / "evidence-turn4"
    raw_path = evidence / "pi-t002-g6-winconpty-raw.txt"
    meta_path = evidence / "pi-t002-g6-winconpty.json"
    if not raw_path.is_file() or not meta_path.is_file():
        raise unittest.SkipTest("accepted PI-T002 native WinConPty capture is unavailable")

    raw_bytes = raw_path.read_bytes()
    raw = raw_bytes.decode("utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    argv = [str(v) for v in meta.get("argv", [])]
    provenance = {
        "captureByteExact": raw.encode("utf-8") == raw_bytes,
        "offline": "--offline" in argv,
        "nativePiCli": any("@earendil-works" in v and "pi-coding-agent" in v for v in argv),
        "nativeUiMarkers": all(
            marker in raw
            for marker in (
                "Auto-resize images",
                "Resume Session (Current Folder)",
                "New session started",
                "Messages",
                "Status:",
            )
        ),
    }

    modules = Path(tempfile.gettempdir()) / "lantern-pi-replay-proof6" / "node_modules"
    if not (modules / "@xterm" / "headless").is_dir() or not (
        modules / "@xterm" / "addon-serialize"
    ).is_dir():
        raise unittest.SkipTest("scoped xterm 6 replay dependencies unavailable")

    with tempfile.TemporaryDirectory(prefix="lantern-real-pi-replay-") as td:
        td_path = Path(td)
        node_probe = td_path / "serialize.js"
        node_probe.write_text(
            """
const fs=require('fs');
const {Terminal}=require('@xterm/headless');
const {SerializeAddon}=require('@xterm/addon-serialize');
const raw=fs.readFileSync(process.argv[2],'utf8');
const term=new Terminal({cols:120,rows:40,scrollback:8000,allowProposedApi:true});
const addon=new SerializeAddon();
term.loadAddon(addon);
term.write(raw,()=>{
  const serialized=addon.serialize({scrollback:8000});
  const h=require('@xterm/headless/package.json').version;
  const s=require('@xterm/addon-serialize/package.json').version;
  process.stdout.write(JSON.stringify({versions:{headless:h,serialize:s},serialized}));
});
""".strip(),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["NODE_PATH"] = str(modules)
        cp = subprocess.run(
            ["node", str(node_probe), str(raw_path)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if cp.returncode:
            raise AssertionError(f"real-Pi headless serialization failed: {cp.stderr[-1200:]}")
        node_result = json.loads(cp.stdout)

        vendor = (ROOT / "static/vendor/xterm.js").resolve().as_uri()
        import base64

        raw_b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        serialized_b64 = base64.b64encode(
            node_result["serialized"].encode("utf-8")
        ).decode("ascii")
        page = td_path / "compare.html"
        page.write_text(
            f"""<!doctype html><meta charset='utf-8'><pre id='out'></pre>
<script src={json.dumps(vendor)}></script>
<script>
const dec=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
const raw=dec({json.dumps(raw_b64)}), serialized=dec({json.dumps(serialized_b64)});
const write=(t,d)=>new Promise(r=>t.write(d,r));
const cell=c=>({{ch:c.getChars(),w:c.getWidth(),fg:c.getFgColor(),bg:c.getBgColor(),
 fgm:c.getFgColorMode(),bgm:c.getBgColorMode(),b:c.isBold(),i:c.isItalic(),
 u:c.isUnderline(),v:c.isInverse(),d:c.isDim(),k:c.isBlink(),x:c.isInvisible(),s:c.isStrikethrough()}});
const snap=t=>{{const b=t.buffer.active,rows=[];for(let y=0;y<t.rows;y++){{const l=b.getLine(b.viewportY+y),r=[];
 if(l)for(let x=0;x<t.cols;x++)r.push(cell(l.getCell(x)));rows.push(r)}}
 return {{cols:t.cols,rows:t.rows,type:b.type,cx:b.cursorX,cy:b.cursorY,base:b.baseY,view:b.viewportY,
  modes:t.modes?JSON.parse(JSON.stringify(t.modes)):null,cells:rows}}}};
const summary=s=>({{cols:s.cols,rows:s.rows,type:s.type,cx:s.cx,cy:s.cy,base:s.base,view:s.view,modes:s.modes}});
(async()=>{{
 const ref=new Terminal({{cols:120,rows:40,scrollback:8000,allowProposedApi:true}});
 const recon=new Terminal({{cols:120,rows:40,scrollback:8000,allowProposedApi:true}});
 await write(ref,raw); await write(recon,serialized);
 const a=snap(ref),b=snap(recon);
 document.getElementById('out').textContent='RESULT:'+JSON.stringify({{equal:JSON.stringify(a)===JSON.stringify(b),ref:summary(a),recon:summary(b)}});
}})().catch(e=>document.getElementById('out').textContent='ERROR:'+String(e));
</script>""",
            encoding="utf-8",
        )
        browser = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--virtual-time-budget=5000",
                "--dump-dom",
                page.as_uri(),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    if browser.returncode:
        raise AssertionError(f"vendored-xterm real-Pi replay failed: {browser.stderr[-1200:]}")
    marker = "RESULT:"
    if marker not in browser.stdout:
        raise AssertionError(f"vendored-xterm real-Pi result missing: {browser.stdout[-1200:]}")
    browser_result = json.loads(
        html.unescape(browser.stdout.split(marker, 1)[1].split("</pre>", 1)[0])
    )
    return {
        "versions": node_result["versions"],
        "provenance": provenance,
        "browser": browser_result,
    }


def _real_pi_exact_client_results() -> dict:
    edge = _edge()
    if not edge:
        raise unittest.SkipTest("Microsoft Edge is required for exact-client snapshot proof")

    evidence = ROOT / ".plan" / "lantern-pi-native-20261018" / "evidence-turn4"
    raw_path = evidence / "pi-t002-g6-winconpty-raw.txt"
    meta_path = evidence / "pi-t002-g6-winconpty.json"
    if not raw_path.is_file() or not meta_path.is_file():
        raise unittest.SkipTest("accepted PI-T002 native WinConPty capture is unavailable")

    raw_bytes = raw_path.read_bytes()
    raw = raw_bytes.decode("utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    argv = [str(v) for v in meta.get("argv", [])]
    provenance = {
        "captureByteExact": raw.encode("utf-8") == raw_bytes,
        "offline": "--offline" in argv,
        "nativePiCli": any("@earendil-works" in v and "pi-coding-agent" in v for v in argv),
        "nativeUiMarkers": all(
            marker in raw
            for marker in (
                "Auto-resize images",
                "Resume Session (Current Folder)",
                "New session started",
                "Messages",
                "Status:",
            )
        ),
    }

    modules = Path(tempfile.gettempdir()) / "lantern-pi-replay-proof6" / "node_modules"
    addon_js = modules / "@xterm" / "addon-serialize" / "lib" / "addon-serialize.js"
    addon_pkg = modules / "@xterm" / "addon-serialize" / "package.json"
    if not addon_js.is_file() or not addon_pkg.is_file():
        raise unittest.SkipTest("temporary @xterm/addon-serialize@0.14.0 is unavailable")
    serialize_version = json.loads(addon_pkg.read_text(encoding="utf-8"))["version"]

    import base64

    raw_b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    vendor = (ROOT / "static/vendor/xterm.js").resolve().as_uri()
    addon = addon_js.resolve().as_uri()
    with tempfile.TemporaryDirectory(prefix="lantern-exact-client-replay-") as td:
        page = Path(td) / "compare.html"
        page.write_text(
            f"""<!doctype html><meta charset='utf-8'><pre id='out'></pre>
<script src={json.dumps(vendor)}></script>
<script src={json.dumps(addon)}></script>
<script>
const dec=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
const raw=dec({json.dumps(raw_b64)});
const write=(t,d)=>new Promise(r=>t.write(d,r));
const cell=c=>({{ch:c.getChars(),w:c.getWidth(),fg:c.getFgColor(),bg:c.getBgColor(),
 fgm:c.getFgColorMode(),bgm:c.getBgColorMode(),b:c.isBold(),i:c.isItalic(),
 u:c.isUnderline(),v:c.isInverse(),d:c.isDim(),k:c.isBlink(),x:c.isInvisible(),s:c.isStrikethrough()}});
const snap=t=>{{const b=t.buffer.active,rows=[];for(let y=0;y<t.rows;y++){{const l=b.getLine(b.viewportY+y),r=[];
 if(l)for(let x=0;x<t.cols;x++)r.push(cell(l.getCell(x)));rows.push(r)}}
 return {{cols:t.cols,rows:t.rows,type:b.type,cx:b.cursorX,cy:b.cursorY,base:b.baseY,view:b.viewportY,
  modes:t.modes?JSON.parse(JSON.stringify(t.modes)):null,cells:rows}}}};
const summary=s=>({{cols:s.cols,rows:s.rows,type:s.type,cx:s.cx,cy:s.cy,base:s.base,view:s.view,modes:s.modes}});
(async()=>{{
 const ref=new Terminal({{cols:120,rows:40,scrollback:8000,allowProposedApi:true}});
 const addon=new SerializeAddon.SerializeAddon();
 ref.loadAddon(addon);
 await write(ref,raw);
 const serialized=addon.serialize({{scrollback:8000}});
 const recon=new Terminal({{cols:120,rows:40,scrollback:8000,allowProposedApi:true}});
 await write(recon,serialized);
 const a=snap(ref),b=snap(recon);
 const chunks=[
  '\\r\\nDELTA-BEGIN',
  '\\x1b[3','1mR','ED\\x1b[0m',
  '\\x1b[2;10H@',
  '\\x1b[?1049hALT\\x1b[3;7H\\x1b[1;34m#\\x1b[0m',
  '\\x1b[?1049l',
  '\\x1b[?2004h'
 ];
 for(const chunk of chunks){{await write(ref,chunk);await write(recon,chunk);}}
 const da=snap(ref),db=snap(recon);
 document.getElementById('out').textContent='RESULT:'+JSON.stringify({{
  browser:{{equal:JSON.stringify(a)===JSON.stringify(b),ref:summary(a),recon:summary(b),snapshotUtf8Bytes:new TextEncoder().encode(serialized).length,snapshotUtf16CodeUnits:serialized.length}},
  delta:{{equal:JSON.stringify(da)===JSON.stringify(db),ref:summary(da),recon:summary(db),chunks:chunks.length}}
 }});
}})().catch(e=>document.getElementById('out').textContent='ERROR:'+String(e));
</script>""",
            encoding="utf-8",
        )
        browser = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--virtual-time-budget=5000",
                "--dump-dom",
                page.as_uri(),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    if browser.returncode:
        raise AssertionError(f"exact-client replay probe failed: {browser.stderr[-1200:]}")
    pre = '<pre id="out">'
    if pre not in browser.stdout:
        raise AssertionError(f"exact-client replay result missing: {browser.stdout[-1200:]}")
    payload = html.unescape(browser.stdout.split(pre, 1)[1].split("</pre>", 1)[0])
    if payload.startswith("ERROR:"):
        raise AssertionError(payload)
    if not payload.startswith("RESULT:"):
        raise AssertionError(f"exact-client replay output empty/unexpected: {browser.stdout[-1600:]}")
    browser_result = json.loads(payload.removeprefix("RESULT:"))
    return {
        "serializeVersion": serialize_version,
        "provenance": provenance,
        "browser": browser_result["browser"],
        "delta": browser_result["delta"],
    }


class _CapturePty(NativePty):
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit
        self.writes: list[str] = []
        self.resizes: list[tuple[int, int]] = []
        self.closed = False

    def write(self, data: str) -> None:
        self.writes.append(data)

    def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    def close(self, graceful: bool = True) -> None:
        self.closed = True

    def emit(self, data: str) -> None:
        self.on_data(data)


@unittest.skipUnless(
    os.environ.get("LANTERN_PI_REPLAY_E2E") == "1",
    "set LANTERN_PI_REPLAY_E2E=1 to run PI-T003 replay proof",
)
class PiReconnectProof(unittest.TestCase):
    def test_current_raw_tail_replay_is_not_lossless(self) -> None:
        result = _vendored_raw_results()
        self.assertTrue(result["split"]["equal"], "split escape chunks must parse when full stream is retained")
        self.assertTrue(result["alt"]["equal"], "full raw stream can reconstruct this active alternate-buffer case")
        self.assertTrue(result["altExit"]["equal"], "full raw stream must restore normal state after alternate-buffer exit")
        self.assertEqual(result["altExit"]["ref"]["type"], "normal")
        self.assertTrue(result["style"]["equal"], "full raw stream can reconstruct tested style/cursor case")
        self.assertFalse(result["truncated"]["equal"], "bounded tail must not be promoted to lossless replay")
        self.assertTrue(result["modes"]["equal"], "full retained stream preserves tested public modes")
        self.assertTrue(result["modes"]["ref"]["modes"]["bracketedPasteMode"])
        self.assertTrue(result["resize"]["equal"], "same final geometry can reconstruct this retained stream")
        self.assertFalse(result["width"]["equal"], "raw terminal state is geometry-dependent")

    def test_upstream_serializer_is_lossless_for_tested_same_geometry_state(self) -> None:
        result = _upstream_results()
        self.assertEqual(result["versions"], {"headless": "6.0.0", "serialize": "0.14.0"})
        for name in ("serializeAlt", "serializeAltExit", "serializeStyle", "serializeModes", "serializeResize"):
            self.assertTrue(result[name]["equal"], name)
        self.assertFalse(result["serializeWidth"]["equal"], "serialized state must remain geometry-scoped")
        self.assertEqual(result["serializeAlt"]["ref"]["type"], "alternate")
        self.assertEqual(result["serializeAltExit"]["ref"]["type"], "normal")
        self.assertTrue(result["serializeModes"]["ref"]["modes"]["bracketedPasteMode"])
        self.assertTrue(result["serializeModes"]["ref"]["modes"]["applicationCursorKeysMode"])
        self.assertEqual(
            result["serializeModes"]["ref"]["modes"],
            result["serializeModes"]["recon"]["modes"],
        )

    def test_real_pi_headless_serializer_mismatch_is_preserved(self) -> None:
        result = _real_pi_headless_cross_stack_results()
        self.assertEqual(result["versions"], {"headless": "6.0.0", "serialize": "0.14.0"})
        self.assertTrue(result["provenance"]["offline"])
        self.assertTrue(result["provenance"]["nativePiCli"])
        self.assertTrue(result["provenance"]["nativeUiMarkers"])
        self.assertTrue(result["provenance"].get("captureByteExact"), result["provenance"])
        self.assertFalse(result["browser"]["equal"], result["browser"])

    def test_real_pi_exact_client_snapshot_round_trips(self) -> None:
        result = _real_pi_exact_client_results()
        self.assertEqual(result["serializeVersion"], "0.14.0")
        self.assertTrue(result["provenance"]["offline"])
        self.assertTrue(result["provenance"]["nativePiCli"])
        self.assertTrue(result["provenance"]["nativeUiMarkers"])
        self.assertTrue(result["provenance"].get("captureByteExact"), result["provenance"])
        self.assertTrue(result["browser"]["equal"], result["browser"])
        self.assertEqual(result["browser"]["snapshotUtf8Bytes"], 6130)
        self.assertEqual(result["browser"]["snapshotUtf16CodeUnits"], 5708)
        self.assertGreater(
            result["browser"]["snapshotUtf8Bytes"],
            result["browser"]["snapshotUtf16CodeUnits"],
            "native Pi snapshot contains non-ASCII data; UTF-8 bytes must not be mislabeled code units",
        )
        self.assertEqual((result["browser"]["ref"]["cols"], result["browser"]["ref"]["rows"]), (120, 40))
        self.assertEqual(result["browser"]["ref"], result["browser"]["recon"])
        self.assertTrue(result["delta"]["equal"], result["delta"])
        self.assertEqual(result["delta"]["ref"], result["delta"]["recon"])
        self.assertGreater(result["delta"]["chunks"], 1)

    def test_public_ws_replay_cannot_signal_internal_retention_gap(self) -> None:
        spawned: dict[str, _CapturePty] = {}
        hub = WebSocketHub()

        class Peer:
            def __init__(self) -> None:
                self.subscriptions: set[str] = set()
                self.messages: list[dict] = []
                self.protocol = "v2"

            def send(self, msg: dict) -> None:
                self.messages.append(msg)

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            pty = _CapturePty(on_data, on_exit)
            spawned[term_id] = pty
            return pty

        with tempfile.TemporaryDirectory(prefix="lantern-replay-gap-") as td:
            manager = TerminalManager(
                Path(td), hub.broadcast, pty_factory=factory, flush_ms=0, max_output=8
            )
            manager.create("pi-gap", td, 80, 24, "Gap proof")
            pty = spawned["pi-gap"]
            pty.emit("SNAP")  # snapshot boundary S=1
            pty.emit("ABCDEFGHIJK")  # seq=2 exceeds retained output capacity

            peer = Peer()
            hub.add(peer)
            dispatch(
                peer,
                {"type": "terminal_subscribe", "terminalId": "pi-gap"},
                manager,
                None,
                hub,
            )
            replay = next(m for m in peer.messages if m["type"] == "terminal_replay")
            self.assertEqual(replay["seq"], 2)
            self.assertEqual(replay["output"], "DEFGHIJK")
            self.assertIs(replay["truncated"], False)
            self.assertNotIn("outputOffset", replay["meta"])
            self.assertNotIn("oldestSeq", replay["meta"])
            self.assertNotIn("truncated", replay["meta"])
            manager.kill("pi-gap")

    def test_manager_detach_replay_orders_output_without_resending_input(self) -> None:
        events: list[dict] = []
        spawned: dict[str, _CapturePty] = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            pty = _CapturePty(on_data, on_exit)
            spawned[term_id] = pty
            return pty

        with tempfile.TemporaryDirectory(prefix="lantern-replay-manager-") as td:
            manager = TerminalManager(Path(td), events.append, pty_factory=factory, flush_ms=0)
            info = manager.create("pi-replay", td, 80, 24, "Replay proof")
            pty = spawned["pi-replay"]
            manager.input("pi-replay", "ONE-USER-INPUT")
            before_boundary = threading.Event()
            release_after_boundary = threading.Event()
            producer_done = threading.Event()

            def produce_across_detach_boundary() -> None:
                pty.emit("A")
                pty.emit("\x1b[31")
                before_boundary.set()
                release_after_boundary.wait(2.0)
                pty.emit("mRED\x1b[0m")
                pty.emit("POST")
                producer_done.set()

            producer = threading.Thread(target=produce_across_detach_boundary)
            producer.start()
            self.assertTrue(before_boundary.wait(2.0), "producer must reach detach boundary")

            meta, output, seq = manager.replay_one("pi-replay")
            self.assertEqual(output, "A\x1b[31")
            self.assertEqual(meta["generation"], info["generation"])
            self.assertEqual(seq, 2)

            release_after_boundary.set()
            self.assertTrue(producer_done.wait(2.0), "post-boundary output must arrive")
            producer.join(2.0)
            self.assertFalse(producer.is_alive())

            meta_after, output_after, seq_after = manager.replay_one("pi-replay")
            self.assertEqual(meta_after["generation"], info["generation"])
            self.assertEqual(output_after, "A\x1b[31mRED\x1b[0mPOST")
            self.assertEqual(seq_after, 4)
            self.assertEqual(pty.writes, ["ONE-USER-INPUT"], "replay must never resend user input")
            output_events = [e for e in events if e.get("type") == "terminal_output"]
            self.assertEqual([e["seq"] for e in output_events], [1, 2, 3, 4])
            self.assertEqual(
                [e["data"] for e in output_events],
                ["A", "\x1b[31", "mRED\x1b[0m", "POST"],
            )
            self.assertTrue(all(e["generation"] == info["generation"] for e in output_events))
            manager.resize("pi-replay", 100, 30)
            self.assertEqual(pty.resizes, [(100, 30)])
            manager.kill("pi-replay")


if __name__ == "__main__":
    unittest.main()
