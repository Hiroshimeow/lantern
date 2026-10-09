"""W1/D1 LAN multi-client correctness and bounded-preview regressions."""
from __future__ import annotations

import tempfile
import threading
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

import plugin
from lantern_terminal import TerminalManager
from lantern_ws import WebSocketHub, dispatch


class Peer:
    def __init__(self):
        self.subscriptions: set[str] = set()
        self.messages: list[dict] = []

    def send(self, msg: dict):
        self.messages.append(msg)


class FakePty:
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit

    def emit(self, s: str):
        self.on_data(s)

    def close(self, graceful: bool = True):
        pass


class LanTerminalTests(unittest.TestCase):
    def test_clients_subscribe_independently_without_terminating_shared_pty(self):
        pts = {}
        hub = WebSocketHub()
        a, b = Peer(), Peer()
        hub.add(a)
        hub.add(b)

        def fake_pty(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            pts[term_id] = FakePty(on_data, on_exit)
            return pts[term_id]

        with tempfile.TemporaryDirectory() as tmp:
            manager = TerminalManager(Path(tmp), hub.broadcast, pty_factory=fake_pty)
            manager.create("shared", tmp)
            pts["shared"].emit("initial")
            self.assertFalse(any(m["type"] == "terminal_output" for m in a.messages + b.messages))
            dispatch(a, {"type": "terminal_subscribe", "terminalId": "shared"}, manager, None, hub)
            ar = [m for m in a.messages if m["type"] == "terminal_replay"]
            self.assertEqual(len(ar), 1)
            self.assertEqual(ar[0]["output"], "initial")
            self.assertEqual(ar[0]["seq"], 1)
            pts["shared"].emit("live")
            self.assertEqual([m["seq"] for m in a.messages if m["type"] == "terminal_output"], [2])
            self.assertFalse(any(m["type"] == "terminal_output" for m in b.messages))
            dispatch(b, {"type": "terminal_subscribe", "terminalId": "shared"}, manager, None, hub)
            br = [m for m in b.messages if m["type"] == "terminal_replay"]
            self.assertEqual(br[0]["output"], "initiallive")
            self.assertEqual(br[0]["seq"], 2)
            dispatch(a, {"type": "terminal_unsubscribe", "terminalId": "shared"}, manager, None, hub)
            pts["shared"].emit("still-running")
            self.assertEqual([m["seq"] for m in a.messages if m["type"] == "terminal_output"], [2])
            self.assertEqual([m["seq"] for m in b.messages if m["type"] == "terminal_output"], [3])
            self.assertTrue(next(x for x in manager.list() if x["id"] == "shared")["running"])
            hub.remove(a)
            self.assertEqual(a.subscriptions, set())
            pts["shared"].emit("visible-on-b")
            self.assertEqual([m["seq"] for m in b.messages if m["type"] == "terminal_output"], [3,4])

    def test_switch_subscription_on_one_client_does_not_accumulate_idle_output(self):
        hub = WebSocketHub()
        a, b = Peer(), Peer()
        hub.add(a)
        hub.add(b)
        pts = {}
        with tempfile.TemporaryDirectory() as tmp:
            manager = TerminalManager(Path(tmp), hub.broadcast,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                    pts.setdefault(tid, FakePty(on_data, on_exit)))
            manager.create("first", tmp)
            manager.create("second", tmp)
            dispatch(a, {"type": "terminal_subscribe", "terminalId": "first"}, manager, None, hub)
            dispatch(b, {"type": "terminal_subscribe", "terminalId": "first"}, manager, None, hub)
            dispatch(a, {"type": "terminal_subscribe", "terminalId": "second"}, manager, None, hub)
            self.assertEqual(a.subscriptions, {"second"})
            self.assertEqual(b.subscriptions, {"first"})
            a.messages.clear()
            b.messages.clear()
            pts["first"].emit("FIRST")
            pts["second"].emit("SECOND")
            self.assertEqual([(m["terminalId"], m["data"]) for m in a.messages if m["type"]=="terminal_output"],
                             [("second","SECOND")])
            self.assertEqual([(m["terminalId"], m["data"]) for m in b.messages if m["type"]=="terminal_output"],
                             [("first","FIRST")])

    def test_extreme_active_replay_is_bounded_without_losing_server_history(self):
        import json
        from lantern_ws import _MAX_QUEUED_BYTES
        hub = WebSocketHub()
        pts = {}
        with tempfile.TemporaryDirectory() as tmp:
            manager = TerminalManager(Path(tmp), hub.broadcast, max_output=5_000_000,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                    pts.setdefault(tid, FakePty(on_data, on_exit)))
            manager.create("giant", tmp)
            pts["giant"].emit("\x1b" * 5_000_000)
            peer = Peer()
            hub.add(peer)
            dispatch(peer, {"type": "terminal_subscribe", "terminalId": "giant"}, manager, None, hub)
            item = next(m for m in peer.messages if m["type"] == "terminal_replay")
            self.assertTrue(item["truncated"])
            self.assertLessEqual(len(item["output"]), 800_000)
            self.assertLess(len(json.dumps(item, ensure_ascii=False).encode("utf-8")), _MAX_QUEUED_BYTES)
            _meta, retained, seq = manager.replay_one("giant")
            self.assertEqual(len(retained), 5_000_000)
            self.assertEqual(seq, 1)

    def test_legacy_reconnect_snapshot_is_bounded_without_deleting_server_history(self):
        import json
        from types import SimpleNamespace
        from lantern_ws import _legacy_snapshot_payload, _MAX_QUEUED_BYTES
        tail = "\x1b" * 200000
        retained = [(f"t{i}", tail) for i in range(64)]
        manager = SimpleNamespace(
            replay=lambda: iter(retained),
            list=lambda: [{"id": f"t{i}"} for i in range(64)],
        )
        payload, truncated = _legacy_snapshot_payload(manager)
        self.assertTrue(truncated)
        self.assertEqual(len(retained[0][1]), 200000,
                         "legacy display cap must never modify stored PTY output")
        self.assertEqual(len(payload["output"]), 64)
        self.assertTrue(all(len(s)==20000 for s in payload["output"].values()))
        encoded=json.dumps(payload, ensure_ascii=False, separators=(",",":")).encode("utf-8")
        self.assertLess(len(encoded), _MAX_QUEUED_BYTES)

    def test_sync_only_sends_metadata_even_with_many_full_buffers(self):
        hub = WebSocketHub()
        pt = {}
        with tempfile.TemporaryDirectory() as tmp:
            manager = TerminalManager(Path(tmp), hub.broadcast,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                  pt.setdefault(tid, FakePty(on_data, on_exit)), max_live=16, max_output=200_000)
            for n in range(8):
                manager.create(f"t{n}", tmp)
                pt[f"t{n}"].emit("\x1b[31m" * 20000)
            peer = Peer()
            hub.add(peer)
            dispatch(peer, {"type": "terminal_sync"}, manager, None, hub)
            self.assertEqual(len(peer.messages), 1)
            self.assertEqual(peer.messages[0]["type"], "terminal_list")
            self.assertEqual(len(peer.messages[0]["terminals"]), 8)
            self.assertLess(len(str(peer.messages[0])), 20_000)
            self.assertFalse(any("output" in m for m in peer.messages))

    def test_subscription_racing_with_output_has_seq_for_deduplication(self):
        hub = WebSocketHub()
        got_snapshot = threading.Event()
        allow_send = threading.Event()

        class SlowPeer(Peer):
            def send(self, msg):
                if msg["type"] == "terminal_replay":
                    got_snapshot.set()
                    allow_send.wait(5)
                super().send(msg)

        peer = SlowPeer()
        hub.add(peer)
        pts = {}
        with tempfile.TemporaryDirectory() as tmp:
            manager = TerminalManager(Path(tmp), hub.broadcast,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                  pts.setdefault(tid, FakePty(on_data, on_exit)))
            manager.create("a", tmp)
            pts["a"].emit("one")
            thread = threading.Thread(target=dispatch,args=(peer,{"type":"terminal_subscribe","terminalId":"a"},manager,None,hub))
            thread.start()
            try:
                self.assertTrue(got_snapshot.wait(5))
                pts["a"].emit("two")
                self.assertEqual([m["seq"] for m in peer.messages if m["type"]=="terminal_output"],[2])
            finally:
                allow_send.set()
                thread.join(5)
            snapshot=next(m for m in peer.messages if m["type"]=="terminal_replay")
            self.assertEqual(snapshot["seq"],1)
            self.assertEqual(snapshot["output"],"one")


class BoundedOfficePreviewTests(unittest.TestCase):
    def make_zip(self, path: Path, files: dict[str, bytes]):
        with zipfile.ZipFile(path, "w",compression=zipfile.ZIP_DEFLATED) as z:
            for name, body in files.items():
                z.writestr(name,body)

    def test_docx_large_compressed_xml_uses_stream_not_whole_zip_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=Path(tmp)/"massive.docx"
            data=(b'<w:document xmlns:w="urn:word"><w:body><w:p><w:r><w:t>'
                  +b'A'*(9*1024*1024)+b'</w:t></w:r></w:p></w:body></w:document>')
            self.make_zip(doc,{"word/document.xml":data})
            old=zipfile.ZipFile.read
            def forbid(self,name,*args,**kwargs):
                if name=="word/document.xml":
                    raise AssertionError("DOCX must not whole-read XML")
                return old(self,name,*args,**kwargs)
            with patch.object(zipfile.ZipFile,"read",forbid):
                title,body=plugin._render_docx(doc)
            self.assertEqual(title,"DOCX preview")
            self.assertIn("AAAA",body)
            self.assertIn("truncated",body.lower())
            self.assertLess(len(body),plugin.MAX_TEXT_CHARS+2000)

    def test_xlsx_deep_shared_string_index_is_correct_and_streamed(self):
        ns=b'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        wbr= b'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        strings=(b'<sst xmlns="'+ns+b'">'+b'<si><t>unused</t></si>'*999
                 +b'<si><t>Deep correct value</t></si></sst>')
        work=(b'<workbook xmlns="'+ns+b'" xmlns:r="'+wbr+b'"><sheets>'
              +b'<sheet name="Data" r:id="rId1"/></sheets></workbook>')
        rels=(b'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        sheet=(b'<worksheet xmlns="'+ns+b'"><sheetData>'
               +b'<row r="1"><c r="A1" t="s"><v>999</v></c>'
               +b'<c r="B1"><v>42</v></c></row>'
               +b'</sheetData></worksheet>')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"example.xlsx"
            self.make_zip(path,{"xl/workbook.xml":work,"xl/_rels/workbook.xml.rels":rels,
                                "xl/sharedStrings.xml":strings,"xl/worksheets/sheet1.xml":sheet})
            old=zipfile.ZipFile.read
            def forbid(self,name,*args,**kwargs):
                if name in {"xl/sharedStrings.xml","xl/worksheets/sheet1.xml"}:
                    raise AssertionError("XLSX huge XML must be streamed")
                return old(self,name,*args,**kwargs)
            with patch.object(zipfile.ZipFile,"read",forbid):
                title,body=plugin._render_xlsx(path)
            self.assertEqual(title,"Excel preview")
            self.assertIn("Deep correct value",body)
            self.assertIn("42",body)
            self.assertNotIn("<td>999</td>",body)

    def test_xlsx_inline_rich_text_and_long_cell_are_precise_and_bounded(self):
        ns=b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rns=b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook=(b'<workbook xmlns="'+ns+b'" xmlns:r="'+rns+
                  b'"><sheets><sheet name="Data" r:id="rId1"/></sheets></workbook>')
        rels=b'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        sheet=(b'<worksheet xmlns="'+ns+b'"><sheetData><row>'
               b'<c t="inlineStr"><is><r><t>Good</t></r><r><t> morning</t></r></is></c>'
               b'<c><v>42</v></c>'
               b'<c t="inlineStr"><is><t>'+b'X'*8000+
               b'</t></is></c></row></sheetData></worksheet>')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"inline.xlsx"
            self.make_zip(path,{"xl/workbook.xml":workbook,"xl/_rels/workbook.xml.rels":rels,
                                "xl/worksheets/sheet1.xml":sheet})
            title,body=plugin._render_xlsx(path)
            self.assertEqual(title,"Excel preview")
            self.assertIn("<td>Good morning</td>",body)
            self.assertIn("<td>42</td>",body)
            self.assertIn("<td>"+("X"*plugin.MAX_CELL_CHARS)+"</td>",body)
            self.assertNotIn("X"*(plugin.MAX_CELL_CHARS+1),body)
            self.assertIn("truncated",body.lower())

    def test_xlsx_unrelated_element_flood_has_bounded_peak_memory(self):
        import tracemalloc
        ns=b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rns=b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook=(b'<workbook xmlns="'+ns+b'" xmlns:r="'+rns+
                  b'"><sheets><sheet name="Data" r:id="rId1"/></sheets></workbook>')
        rels=b'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        xml=(b'<worksheet xmlns="'+ns+b'">'+b'<x/>'*250000+
             b'<sheetData><row><c><v>7</v></c></row></sheetData></worksheet>')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"flood.xlsx"
            self.make_zip(path,{"xl/workbook.xml":workbook,"xl/_rels/workbook.xml.rels":rels,
                                "xl/worksheets/sheet1.xml":xml})
            tracemalloc.start()
            try:
                title,body=plugin._render_xlsx(path)
                _current,peak=tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(title,"Excel preview")
            self.assertIn("<td>7</td>",body)
            self.assertLess(peak,12*1024*1024,f"unexpected XML tree amplification: peak={peak}")

    def test_xlsx_one_wide_row_has_bounded_peak_memory(self):
        import tracemalloc
        ns=b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rns=b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook=(b'<workbook xmlns="'+ns+b'" xmlns:r="'+rns+
                  b'"><sheets><sheet name="Data" r:id="rId1"/></sheets></workbook>')
        rels=b'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        xml=(b'<worksheet xmlns="'+ns+b'"><sheetData><row>'+
             b'<c><v>7</v></c>'+b'<c/>'*250000+
             b'</row></sheetData></worksheet>')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"wide.xlsx"
            self.make_zip(path,{"xl/workbook.xml":workbook,"xl/_rels/workbook.xml.rels":rels,
                                "xl/worksheets/sheet1.xml":xml})
            tracemalloc.start()
            try:
                title,body=plugin._render_xlsx(path)
                _current,peak=tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(title,"Excel preview")
            self.assertIn("<td>7</td>",body)
            self.assertIn("truncated",body.lower())
            self.assertLess(peak,12*1024*1024,f"unexpected huge-row materialization: peak={peak}")

    def test_pdf_flate_decompress_has_bounded_output_and_keeps_first_text(self):
        inflated=b"(HELLO bounded PDF) Tj\n"+b" "* (13*1024*1024)
        packed=zlib.compress(inflated)
        data=b"<< /Filter /FlateDecode >>\nstream\n"+packed+b"\nendstream"
        with patch.object(plugin.zlib,"decompress",side_effect=AssertionError("unlimited inflate prohibited")):
            result=plugin._extract_pdf_text_naive(data)
        self.assertIn("HELLO bounded PDF",result)
        self.assertLess(len(result),plugin.MAX_TEXT_CHARS+2000)


    def test_pdftotext_stdout_is_bounded_even_if_child_emits_megabytes(self):
        import subprocess
        import sys
        real_popen = subprocess.Popen
        def spawn(_command, **kwargs):
            return real_popen([sys.executable, "-c",
                               "import sys;sys.stdout.buffer.write(b'Z'*3000000)"], **kwargs)
        with patch.object(plugin.subprocess, "Popen", side_effect=spawn):
            value = plugin._pdftotext_bounded(Path("no-real-file.pdf"))
        self.assertIsNotNone(value)
        text, truncated = value
        self.assertTrue(truncated)
        self.assertLessEqual(len(text.encode("utf-8")), plugin.MAX_PDF_OUTPUT_BYTES)

    def test_pdftotext_timeout_terminates_child_before_fallback(self):
        import subprocess
        import sys
        import time
        real_popen = subprocess.Popen
        def spawn(_command, **kwargs):
            return real_popen([sys.executable, "-c", "import time;time.sleep(10)"], **kwargs)
        before = time.monotonic()
        with patch.object(plugin.subprocess, "Popen", side_effect=spawn):
            with patch.object(plugin, "MAX_PDF_SECONDS", 0.1):
                value = plugin._pdftotext_bounded(Path("no-real-file.pdf"))
        self.assertIsNotNone(value)
        self.assertEqual(value, ("", True))
        self.assertLess(time.monotonic()-before, 2.0)


class BrowserSequenceTests(unittest.TestCase):
    def test_pending_local_terminal_survives_other_lan_client_list_event(self):
        import json
        import subprocess
        script=Path(__file__).parent/"static"/"terminal_scm.js"
        code=r"""
const assert=require('assert');
global.location={protocol:'http:',host:'127.0.0.1'};
global.innerHeight=900;
global.localStorage={getItem:()=>null,setItem:()=>{}};
global.document={querySelector:()=>null,addEventListener:()=>{}};
global.addEventListener=()=>{};
global.setInterval=()=>0;
global.requestAnimationFrame=()=>{};
class FakeWS{static OPEN=1;constructor(){this.readyState=1}send(){}close(){}}
global.WebSocket=FakeWS;
require(REPLACE_JS);
const api=global.__lanternTerminalScm;
const classes={add(){},remove(){},toggle(){},contains(name){return name==='show'}};
const drawer={classList:classes,style:{}};
const elem=()=>({classList:{add(){},remove(){},toggle(){},contains(){return false}},
                  dataset:{},style:{},offsetWidth:400,offsetHeight:200,
                  appendChild(){},remove(){}});
const stack=elem(),tabs=elem(),dims=elem();
global.document.createElement=elem;
global.document.querySelector=s=>({'#termDrawer':drawer,'#lxTermStack':stack,
                                    '#lxTermTabs':tabs,'#lxDims':dims}[s]||null);
class Term {
  constructor(){this.cols=80;this.rows=24}
  loadAddon(){}open(){}attachCustomKeyEventHandler(){}onData(){}
  reset(){}write(){}focus(){}dispose(){}
}
global.Terminal=Term;
global.FitAddon={FitAddon:class{fit(){}}};
global.ResizeObserver=class{observe(){}disconnect(){}};
api.state.connected=true;api.state.termListReady=true;
global.newTerminalSession();
const entries=[...api.state.terms.entries()];
assert.equal(entries.length,1);
const [id,t]=entries[0];
assert.equal(t.pending,true,'mount must not erase pending flag for not-yet-created terminal');
api.handleMessage({type:'terminal_list',terminals:[{id:'from_other_client',generation:'other',running:true}]});
assert(api.state.terms.has(id),'other LAN client metadata must not dispose a pending terminal');
"""
        code=code.replace("REPLACE_JS",json.dumps(str(script)))
        proc=subprocess.run(["node","-e",code],capture_output=True,text=True,timeout=8)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)

    def test_browser_deduplicates_out_of_order_output_across_replay(self):
        import json
        import subprocess
        from pathlib import Path
        js = Path(__file__).parent / "static" / "terminal_scm.js"
        code = r"""
const assert=require('assert');
global.location={protocol:'http:',host:'local.test'};
global.document={querySelector:()=>null,addEventListener:()=>{},hidden:false};
global.addEventListener=()=>{};
global.setInterval=()=>0;
class FakeWebSocket { static OPEN=1; constructor(){this.readyState=1;this.sent=[]}send(raw){this.sent.push(JSON.parse(raw))}close(){} }
global.WebSocket=FakeWebSocket;
require(REPLACE_JS);
const api=global.__lanternTerminalScm;
const writes=[];
const term={reset:()=>writes.push('<reset>'),write:(s,cb)=>{writes.push(s);cb?.()}};
const t={meta:{id:'x',generation:'g1',running:true},term,pending:false,
         pendingChunks:new Map(),seq:null,replaying:false,replayTok:0,ro:null};
api.state.terms.set('x',t);
api.state.subscribed='x';
api.handleMessage({type:'terminal_output',terminalId:'x',generation:'g1',seq:3,data:'C'});
api.handleMessage({type:'terminal_output',terminalId:'x',generation:'g1',seq:2,data:'B'});
assert.equal(writes.length,0,'live chunks arriving before replay must wait');
api.handleMessage({type:'terminal_replay',terminalId:'x',meta:{id:'x',generation:'g1'},seq:1,output:'A'});
api.handleMessage({type:'terminal_output',terminalId:'x',generation:'g1',seq:2,data:'DUPLICATE'});
assert.deepEqual(writes,['<reset>','A','B','C']);
"""
        code=code.replace("REPLACE_JS",json.dumps(str(js)))
        result=subprocess.run(["node","-e",code],capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class LanPreviewConcurrencyTests(unittest.TestCase):
    def test_per_server_heavy_preview_slots_cover_separate_clients(self):
        """Four concurrent clients: two parsers run, two reject without waiting."""
        import time
        import lan_drive
        from types import SimpleNamespace

        class Stub:
            def __init__(self):
                self.result = None
            def send_error(self, status, msg):
                self.result = (status, msg)
            def send_bytes(self, status, body, mime):
                self.result = (status, body)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "file.pdf").write_bytes(b"%PDF-test")
            clients = [Stub() for _ in range(4)]
            begin = threading.Event()
            finish = threading.Event()
            entered = []
            lock = threading.Lock()

            def render(*_args, **_kwargs):
                with lock:
                    entered.append(threading.get_ident())
                finish.wait(3)
                return b"<html>Test preview</html>"

            config = SimpleNamespace(root=root, cache_dir=root, title="Test Lantern")
            def handle(stub):
                begin.wait(3)
                lan_drive.Handler.api_plugin_preview(stub, "p=file.pdf")

            from unittest.mock import patch
            with patch.object(lan_drive, "CONFIG", config, create=True), patch.object(lan_drive.LAN_PLUGIN, "render_preview_page", side_effect=render):
                jobs = [threading.Thread(target=handle, args=(stub,)) for stub in clients]
                for job in jobs: job.start()
                begin.set()
                try:
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and len(entered) < 2:
                        time.sleep(0.01)
                    self.assertEqual(len(entered), 2, "exactly two heavy parsers may run at once")
                finally:
                    finish.set()
                    for job in jobs: job.join(4)
            results = [c.result[0] for c in clients]
            self.assertEqual(sorted(results), [200, 200, 503, 503])
            self.assertFalse(any(job.is_alive() for job in jobs))

    def test_separate_lantern_servers_do_not_share_pty_state_by_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = TerminalManager(Path(tmp), lambda event: None,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                  FakePty(on_data,on_exit))
            b = TerminalManager(Path(tmp), lambda event: None,
                pty_factory=lambda tid, cwd, cols, rows, on_data, on_exit, command=None:
                  FakePty(on_data,on_exit))
            a.create("owned-by-server-a",tmp)
            self.assertEqual(len(a.list()),1)
            self.assertEqual(b.list(),[], "shared SMB/root does not imply shared terminal state")


if __name__ == "__main__":
    unittest.main()
