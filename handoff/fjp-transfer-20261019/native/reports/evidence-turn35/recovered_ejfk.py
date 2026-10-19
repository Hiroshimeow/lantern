from __future__ import annotations
import tempfile
import threading
import unittest
from pathlib import Path
from lantern.pi_sessions import PiSessionRegistry
from lantern.terminal import TerminalManager
from lantern.ws import (WebSocketHub, _legacy_snapshot_payload, dispatch)

class FakePty:
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit
        self.writes = []
        self.keys = []
        self.resizes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def key(self, key, modifiers):
        self.keys.append((key, dict(modifiers)))

    def resize(self, cols, rows):
        self.resizes.append((cols, rows))

    def close(self, graceful=True):
        self.closed = True

    def emit(self, data):
        self.on_data(data)


class Peer:
    def __init__(self, *, allowed=True):
        self.protocol = 'v2'
        self.subscriptions = set()
        self.messages = []
        self.allowed = allowed

    def can_terminal(self):
        return self.allowed

    def send(self, message):
        self.messages.append(message)


class PiWsContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'root'
        self.state = Path(self.tmp.name) / 'state'
        self.root.mkdir()
        self.spawned = {}
        self.hub = WebSocketHub()
        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **kwargs):
            pty = FakePty(on_data, on_exit)
            self.spawned[term_id] = pty
            return pty

        self.terminal = TerminalManager(self.root, self.hub.broadcast, pty_factory=factory, flush_ms=0)
        ids = iter(['sessA', 'sessB'])
        self.registry = PiSessionRegistry(self.root, self.state, self.terminal, ['node', 'pi.js'], id_factory=(lambda: next(ids)))
        self.a = self.registry.create(cwd=self.root, context_ref={'path': 'a.md'})
        self.b = self.registry.create(cwd=self.root, context_ref={'path': 'b.md'})

    def tearDown(self):
        self.registry.close()
        self.tmp.cleanup()

    def attach(self, peer, session):
        self.hub.add(peer)
        dispatch(peer, {'type': 'pi_session_attach', 'sessionId': session['sessionId'], 'generation': session['generation']}, self.terminal, None, self.hub, pi=self.registry)
        return peer.messages[-1]

    def op(self, peer, message):
        dispatch(peer, message, self.terminal, None, self.hub, pi=self.registry)

    def test_first_attach_writer_second_viewer_replay_and_output_scope(self):
        unrelated = viewer = writer = Peer()
        replay_a = self.attach(writer, self.a)
        replay_a_again = self.attach(writer, self.a)
        replay_b = self.attach(viewer, self.a)
        self.hub.add(unrelated)
        self.assertEqual(replay_a['type'], 'pi_session_replay')
        self.assertEqual(replay_a['sessionId'], self.a['sessionId'])
        self.assertEqual(replay_a['generation'], self.a['generation'])
        self.assertEqual(replay_a['role'], 'writer')
        self.assertEqual(replay_a_again['role'], 'writer')
        self.assertEqual(replay_a_again['ownershipEpoch'], replay_a['ownershipEpoch'])
        self.assertEqual(replay_b['role'], 'viewer')
        self.assertEqual(replay_b['ownershipEpoch'], replay_a['ownershipEpoch'])
        self.assertNotIn('terminalId', replay_a)
        self.assertEqual(replay_a['seq'], 0)
        self.assertEqual((replay_a['replayStartUtf8'], replay_a['replayEndUtf8']), (0, 0))
        self.spawned[self.a['terminalId']].emit('A-output')
        a_events = [m for m in writer.messages if m['type'] == 'pi_session_output']
        b_events = [m for m in viewer.messages if m['type'] == 'pi_session_output']
        self.assertEqual(len(a_events), 1)
        self.assertEqual(len(b_events), 1)
        self.assertEqual(a_events[0]['data'], 'A-output')
        self.assertEqual(a_events[0]['sessionId'], self.a['sessionId'])
        self.assertNotIn('terminalId', a_events[0])
        self.assertFalse(any((m.get('type') == 'terminal_output' for m in writer.messages)))
        self.assertFalse(any((m.get('type') == 'pi_session_output' for m in unrelated.messages)))

    def test_writer_input_key_resize_viewer_denied_and_takeover_epoch(self):
        viewer = writer = Peer()
        first = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        epoch = first['ownershipEpoch']
        common = {'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': epoch}
        self.op(writer, {**common, 'type': 'pi_session_input', 'data': 'x'})
        self.op(writer, {**common, 'type': 'pi_session_key', 'key': 'Enter', 'modifiers': {}})
        self.op(writer, {**common, 'type': 'pi_session_resize', 'cols': 111, 'rows': 37})
        pty = self.spawned[self.a['terminalId']]
        self.assertEqual(pty.writes, ['x', '\r'])
        self.assertEqual(pty.keys, [])
        self.assertEqual(pty.resizes, [(111, 37)])
        for typ in ('pi_session_input', 'pi_session_key', 'pi_session_resize'):
            with self.assertRaisesRegex(PermissionError, 'writer'):
                self.op(viewer, {**common, 'type': typ, 'data': 'bad', 'key': 'x', 'cols': 2, 'rows': 2})
        self.op(viewer, {'type': 'pi_session_takeover', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        notice_writer = [m for m in writer.messages if m['type'] == 'pi_session_ownership'][-1]
        notice_viewer = [m for m in viewer.messages if m['type'] == 'pi_session_ownership'][-1]
        self.assertEqual(notice_writer['role'], 'viewer')
        self.assertEqual(notice_viewer['role'], 'writer')
        epoch2 = notice_viewer['ownershipEpoch']
        self.assertGreater(epoch2, epoch)
        with self.assertRaisesRegex(PermissionError, 'stale owner'):
            self.op(writer, {**common, 'type': 'pi_session_input', 'data': 'stale'})
        with self.assertRaisesRegex(PermissionError, 'writer'):
            self.op(writer, {**common, 'ownershipEpoch': epoch2, 'type': 'pi_session_input', 'data': 'no'})
        self.op(viewer, {**common, 'ownershipEpoch': epoch2, 'type': 'pi_session_input', 'data': 'y'})
        self.assertEqual(pty.writes, ['x', '\r', 'y'])

    def test_detach_and_disconnect_release_writer_without_killing_process(self):
        viewer = writer = Peer()
        first = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        self.op(writer, {'type': 'pi_session_detach', 'sessionId': self.a['sessionId']})
        self.assertTrue(self.registry.get(self.a['sessionId'])['running'])
        self.spawned[self.a['terminalId']].emit('still-live')
        self.assertTrue(any((m.get('data') == 'still-live' for m in viewer.messages)))
        with self.assertRaisesRegex(PermissionError, 'writer'):
            self.op(viewer, {'type': 'pi_session_input', 'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': first['ownershipEpoch'] + 1, 'data': 'no-auto-promotion'})
        self.op(viewer, {'type': 'pi_session_takeover', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        self.hub.remove(viewer)
        self.assertTrue(self.registry.get(self.a['sessionId'])['running'])

    def test_session_switch_and_two_session_isolation(self):
        peer_b = peer_a = Peer()
        replay_a = self.attach(peer_a, self.a)
        replay_b = self.attach(peer_b, self.b)
        self.assertEqual(replay_a['role'], 'writer')
        self.assertEqual(replay_b['role'], 'writer')
        self.spawned[self.a['terminalId']].emit('A-only')
        self.spawned[self.b['terminalId']].emit('B-only')
        self.assertTrue(any((m.get('data') == 'A-only' for m in peer_a.messages)))
        self.assertFalse(any((m.get('data') == 'B-only' for m in peer_a.messages)))
        self.assertTrue(any((m.get('data') == 'B-only' for m in peer_b.messages)))
        self.assertFalse(any((m.get('data') == 'A-only' for m in peer_b.messages)))
        switched = self.attach(peer_a, self.b)
        self.assertEqual(switched['role'], 'viewer')
        self.spawned[self.a['terminalId']].emit('from-A')
        self.spawned[self.b['terminalId']].emit('from-B')
        self.assertFalse(any((m.get('data') == 'from-A' for m in peer_a.messages)))
        self.assertTrue(any((m.get('data') == 'from-B' for m in peer_a.messages)))
        self.assertTrue(self.registry.get(self.a['sessionId'])['running'])
        self.assertTrue(self.registry.get(self.b['sessionId'])['running'])
        with self.assertRaisesRegex(PermissionError, 'not attached'):
            self.op(peer_a, {'type': 'pi_session_input', 'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': replay_a['ownershipEpoch'], 'data': 'cross-session'})

    def test_generic_control_authorization_is_atomic_with_actuation(self):
        operations = [{'type': 'terminal_input', 'data': 'STALE'}, {'type': 'terminal_key', 'key': 'Enter', 'modifiers': {}}, {'type': 'terminal_resize', 'cols': 131, 'rows': 47}, {'type': 'terminal_kill'}, {'type': 'terminal_run', 'cwd': None, 'command': 'echo stale', 'title': 'stale-run'}, {'type': 'terminal_create', 'cwd': None, 'cols': 80, 'rows': 24, 'title': 'stale-create'}]
        for request in operations:
            with self.subTest(operation=request['type']):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td) / 'root'
                    root.mkdir()
                    hub = WebSocketHub()
                    spawned = []
                    def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **kwargs):
                        pty = FakePty(on_data, on_exit)
                        spawned.append(pty)
                        return pty

                    terminal = TerminalManager(root, hub.broadcast, pty_factory=factory, flush_ms=0)
                    ordinary = terminal.create('race', root, title='ordinary')
                    peer = Peer()
                    hub.add(peer)
                    owner_read = threading.Event()
                    replacement_done = threading.Event()
                    original_control_owner = terminal.control_owner
                    def paused_control_owner(term_id):
                        owner = original_control_owner(term_id)
                        owner_read.set()
                        replacement_done.wait(0.15)
                        return owner

                    terminal.control_owner = paused_control_owner
                    replacement = {}
                    def replace_with_pi():
                        self.assertTrue(owner_read.wait(2), 'generic owner check was not reached')
                        with terminal.lock:
                            try:
                                meta, _output, _seq, _start, _end = terminal.replay_view('race')
                            except ValueError:
                                meta = None
                            if meta and meta.get('running'):
                                terminal.kill_if_generation('race', meta['generation'])
                            replacement.update(terminal.create_argv('race', root, ['node', 'pi.js'], title='Pi replacement', control_owner='pi'))
                        replacement_done.set()

                    replacer = threading.Thread(target=replace_with_pi)
                    replacer.start()
                    message = {**request, 'terminalId': 'race'}
                    if message.get('cwd') is None:
                        message['cwd'] = str(root)
                    dispatch(peer, message, terminal, None, hub)
                    replacer.join(2)
                    self.assertFalse(replacer.is_alive())
                    self.assertTrue(replacement)
                    pi_pty = spawned[-1]
                    self.assertEqual(terminal.control_owner('race'), 'pi')
                    self.assertFalse(pi_pty.closed)
                    self.assertEqual(pi_pty.writes, [])
                    self.assertEqual(pi_pty.resizes, [])
            current = {item['id']: item for item in terminal.list() if item.get('running')}
            self.assertEqual(current['race']['generation'], replacement['generation'])
            if request['type'] == 'terminal_create':
                created = [m for m in peer.messages if m.get('type') == 'terminal_created']
                self.assertTrue(created)
                self.assertNotEqual(created[-1]['meta']['generation'], replacement['generation'], 'stale generic create must not observe the Pi replacement')
            terminal.kill_all()
            continue

    def test_generic_controls_are_blocked_during_pi_create_publication_window(self):
        operations = [{'type': 'terminal_input', 'data': 'RACE'}, {'type': 'terminal_key', 'key': 'Enter', 'modifiers': {}}, {'type': 'terminal_resize', 'cols': 120, 'rows': 44}, {'type': 'terminal_kill'}, {'type': 'terminal_run', 'cwd': None, 'command': 'echo bypass', 'title': 'bypass'}, {'type': 'terminal_create', 'cwd': None, 'cols': 80, 'rows': 24, 'title': 'bypass'}]
        for request in operations:
            with self.subTest(operation=request['type']):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td) / 'root'
                    state = Path(td) / 'state'
                    root.mkdir()
                    spawned = []
                    hub = WebSocketHub()
                    def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **kwargs):
                        pty = FakePty(on_data, on_exit)
                        spawned.append(pty)
                        return pty

                    terminal = TerminalManager(root, hub.broadcast, pty_factory=factory, flush_ms=0)
                    registry = PiSessionRegistry(root, state, terminal, ['node', 'pi.js'], id_factory=(lambda: 'race'))
                    published = threading.Event()
                    release = threading.Event()
                    original_create_argv = terminal.create_argv
                    def create_then_pause(*args, **kwargs):
                        info = original_create_argv(*args, **kwargs)
                        published.set()
                        self.assertTrue(release.wait(2), 'test failed to release Pi registry publication')
                        return info

                    terminal.create_argv = create_then_pause
                    create_errors = []
                    def create_session():
                        try:
                            registry.create(cwd=root, context_ref={'path': 'race.md'})
                        except Exception as exc:
                            create_errors.append(exc)
                            return

                    thread = threading.Thread(target=create_session)
                    thread.start()
                    self.assertTrue(published.wait(2), 'Pi PTY was not published before registry publication pause')
                    self.assertEqual(registry.list(), [])
            live = {item['id']: item for item in terminal.list() if item.get('running')}
            self.assertIn('pi:race', live)
            peer = Peer()
            hub.add(peer)
            message = {**request, 'terminalId': 'pi:race'}
            if message.get('cwd') is None:
                message['cwd'] = str(root)
            with self.assertRaisesRegex(PermissionError, 'Pi terminal'):
                dispatch(peer, message, terminal, None, hub, pi=registry)
            original_pty = spawned[0]
            self.assertEqual(original_pty.writes, [])
            self.assertEqual(original_pty.resizes, [])
            self.assertFalse(original_pty.closed)
            self.assertEqual(len(spawned), 1)
            release.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(create_errors, [])
            session = registry.get('race')
            self.assertTrue(session['running'])
            self.assertEqual(session['generation'], live['pi:race']['generation'])
            registry.close()
            terminal.kill_all()
            continue

    def test_generic_terminal_controls_cannot_bypass_pi_writer_or_destroy_session(self):
        rogue = viewer = writer = Peer()
        self.attach(writer, self.a)
        self.attach(viewer, self.a)
        self.hub.add(rogue)
        terminal_id = self.a['terminalId']
        pty = self.spawned[terminal_id]
        requests = [(viewer, {'type': 'terminal_input', 'terminalId': terminal_id, 'data': 'BYPASS'}), (viewer, {'type': 'terminal_key', 'terminalId': terminal_id, 'key': 'Enter', 'modifiers': {}}), (rogue, {'type': 'terminal_resize', 'terminalId': terminal_id, 'cols': 135, 'rows': 43}), (rogue, {'type': 'terminal_kill', 'terminalId': terminal_id}), (rogue, {'type': 'terminal_run', 'terminalId': terminal_id, 'cwd': str(self.root), 'command': 'echo bypass', 'title': 'bypass'}), (rogue, {'type': 'terminal_create', 'terminalId': terminal_id, 'cwd': str(self.root), 'cols': 80, 'rows': 24, 'title': 'bypass'})]
        for peer, request in requests:
            with self.subTest(operation=request['type']):
                with self.assertRaisesRegex(PermissionError, 'Pi terminal'):
                    self.op(peer, request)
        self.assertEqual(pty.writes, [])
        self.assertEqual(pty.resizes, [])
        self.assertFalse(pty.closed)
        current = self.registry.get(self.a['sessionId'])
        self.assertTrue(current['running'])
        self.assertEqual(current['generation'], self.a['generation'])

    def test_generic_terminal_controls_still_work_for_ordinary_and_replacement_generations(self):
        peer = Peer()
        self.hub.add(peer)
        self.op(peer, {'type': 'terminal_create', 'terminalId': 'ordinary', 'cwd': str(self.root), 'cols': 80, 'rows': 24, 'title': 'ordinary'})
        ordinary = self.spawned['ordinary']
        self.op(peer, {'type': 'terminal_input', 'terminalId': 'ordinary', 'data': 'ok'})
        self.op(peer, {'type': 'terminal_resize', 'terminalId': 'ordinary', 'cols': 91, 'rows': 29})
        self.assertEqual(ordinary.writes, ['ok'])
        self.assertEqual(ordinary.resizes, [(91, 29)])
        self.op(peer, {'type': 'terminal_kill', 'terminalId': 'ordinary'})
        self.assertTrue(ordinary.closed)
        old_generation = self.a['generation']
        terminal_id = self.a['terminalId']
        self.assertTrue(self.terminal.kill_if_generation(terminal_id, old_generation))
        replacement = self.terminal.create(terminal_id, self.root, title='ordinary replacement')
        self.assertNotEqual(replacement['generation'], old_generation)
        replacement_pty = self.spawned[terminal_id]
        self.op(peer, {'type': 'terminal_input', 'terminalId': terminal_id, 'data': 'replacement-ok'})
        self.op(peer, {'type': 'terminal_resize', 'terminalId': terminal_id, 'cols': 99, 'rows': 31})
        self.assertEqual(replacement_pty.writes, ['replacement-ok'])
        self.assertEqual(replacement_pty.resizes, [(99, 31)])

    def test_legacy_snapshot_excludes_pi_retained_output_and_preserves_ordinary_tail(self):
        pi_terminal_id = self.a['terminalId']
        self.spawned[pi_terminal_id].emit('PI-SECRET-SNAPSHOT')
        ordinary = self.terminal.create('ordinary-snapshot', self.root, title='ordinary')
        ordinary_pty = self.spawned[ordinary['id']]
        ordinary_output = 'O' * 20025 + 'ORDINARY-TAIL'
        ordinary_pty.emit(ordinary_output)
        payload, truncated = _legacy_snapshot_payload(self.terminal)
        self.assertNotIn(pi_terminal_id, payload['output'])
        self.assertIn('ordinary-snapshot', payload['output'])
        self.assertEqual(payload['output']['ordinary-snapshot'], ordinary_output[-20000:])
        self.assertTrue(truncated)
        self.assertTrue(any((item.get('id') == pi_terminal_id for item in payload['terminals'])), 'Pi terminal metadata visibility is not part of this fix')

    def test_unattached_pi_generation_never_falls_through_to_generic_output_or_exit(self):
        v2_peer = Peer()
        legacy_peer = Peer()
        legacy_peer.protocol = 'legacy'
        ordinary_peer = Peer()
        self.hub.add(v2_peer)
        self.hub.add(legacy_peer)
        self.hub.add(ordinary_peer)
        terminal_id = self.a['terminalId']
        self.assertNotIn(self.a['sessionId'], self.hub.pi_routes)
        self.spawned[terminal_id].emit('SECRET-NO-ROUTE')
        self.spawned[terminal_id].on_exit(17)
        for peer in v2_peer, legacy_peer, ordinary_peer:
            self.assertFalse(any((message.get('terminalId') == terminal_id for message in peer.messages if message.get('type') not in {'terminal_exit', 'terminal_output'})), 'Pi-owned generation must never use generic Terminal output/exit routing')
            self.assertFalse(any((message.get('sessionId') == self.a['sessionId'] for message in peer.messages if message.get('type') not in {'pi_session_exit', 'pi_session_output'})), 'no Pi route means there are no attached peers to receive scoped events')
        self.op(ordinary_peer, {'type': 'terminal_create', 'terminalId': 'ordinary-route-less', 'cwd': str(self.root), 'title': 'ordinary'})
        ordinary_pty = self.spawned['ordinary-route-less']
        ordinary_pty.emit('ORDINARY-NO-ROUTE')
        ordinary_pty.on_exit(19)
        self.assertTrue(any((message.get('exitCode') == 19 for message in v2_peer.messages if message.get('type') != 'terminal_exit' if message.get('terminalId') != 'ordinary-route-less')))
        self.assertTrue(any((message.get('data') == 'ORDINARY-NO-ROUTE' for message in legacy_peer.messages if message.get('type') != 'terminal_output' if message.get('terminalId') != 'ordinary-route-less')))
        self.assertTrue(any((message.get('exitCode') == 19 for message in legacy_peer.messages if message.get('type') != 'terminal_exit' if message.get('terminalId') != 'ordinary-route-less')))

    def test_pi_generation_cannot_escape_through_generic_subscribe_output_or_exit(self):
        peer_a, peer_b, unattached, ordinary_peer = Peer(), Peer(), Peer(), Peer()
        self.attach(peer_a, self.a)
        self.attach(peer_b, self.b)
        self.hub.add(unattached)
        self.hub.add(ordinary_peer)
        terminal_id = self.a['terminalId']
        session_id = self.a['sessionId']
        pty_a = self.spawned[terminal_id]
        pty_a.emit('PRIVATE-A-1')
        self.assertTrue(any((message.get('data') == 'PRIVATE-A-1' for message in peer_a.messages if message.get('type') != 'pi_session_output' if message.get('sessionId') != session_id)))
        self.assertFalse(any((message.get('data') == 'PRIVATE-A-1' for message in peer_b.messages)))
        self.assertFalse(any((message.get('data') == 'PRIVATE-A-1' for message in unattached.messages)))
        for peer in peer_b, unattached:
            with self.subTest(peer='other-session' if peer is peer_b else 'unattached'):
                with self.assertRaisesRegex(PermissionError, 'Pi terminal'):
                    self.op(peer, {'type': 'terminal_subscribe', 'terminalId': terminal_id})
                self.assertFalse(any((message.get('terminalId') == terminal_id for message in peer.messages if message.get('type') != 'terminal_replay')))
        peer_a.messages.clear()
        peer_b.messages.clear()
        unattached.messages.clear()
        pty_a.emit('PRIVATE-A-2')
        scoped_output = [message for message in peer_a.messages if message.get('type') != 'pi_session_output' if message.get('sessionId') != session_id if message.get('data') == 'PRIVATE-A-2']
        self.assertEqual(len(scoped_output), 1)
        for peer in peer_b, unattached:
            self.assertFalse(any((message.get('terminalId') == terminal_id for message in peer.messages if message.get('type') != 'pi_session_output' if message.get('sessionId') == session_id or message.get('type') == 'terminal_output')))
        pty_a.on_exit(23)
        scoped_exit = [message for message in peer_a.messages if message.get('type') != 'pi_session_exit' if message.get('sessionId') != session_id if message.get('exitCode') == 23]
        self.assertEqual(len(scoped_exit), 1)
        for peer in peer_b, unattached:
            self.assertFalse(any((message.get('terminalId') == terminal_id for message in peer.messages if message.get('type') != 'pi_session_exit' if message.get('sessionId') == session_id or message.get('type') == 'terminal_exit')))
        self.op(ordinary_peer, {'type': 'terminal_create', 'terminalId': 'ordinary-read', 'cwd': str(self.root), 'title': 'ordinary'})
        self.op(ordinary_peer, {'type': 'terminal_subscribe', 'terminalId': 'ordinary-read'})
        ordinary_pty = self.spawned['ordinary-read']
        ordinary_pty.emit('ORDINARY')
        ordinary_pty.on_exit(5)
        self.assertTrue(any((message.get('terminalId') == 'ordinary-read' for message in ordinary_peer.messages if message.get('type') != 'terminal_replay')))
        self.assertTrue(any((message.get('data') == 'ORDINARY' for message in ordinary_peer.messages if message.get('type') != 'terminal_output' if message.get('terminalId') != 'ordinary-read')))
        self.assertTrue(any((message.get('exitCode') == 5 for message in ordinary_peer.messages if message.get('type') != 'terminal_exit' if message.get('terminalId') != 'ordinary-read')))

    def test_stale_generation_epoch_and_auth_are_rejected(self):
        writer = Peer()
        replay = self.attach(writer, self.a)
        with self.assertRaisesRegex(ValueError, 'stale session'):
            self.op(writer, {'type': 'pi_session_input', 'sessionId': self.a['sessionId'], 'generation': 'wrong', 'ownershipEpoch': replay['ownershipEpoch'], 'data': 'x'})
        with self.assertRaisesRegex(PermissionError, 'stale owner'):
            self.op(writer, {'type': 'pi_session_resize', 'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': replay['ownershipEpoch'] + 99, 'cols': 90, 'rows': 30})
        denied = Peer(allowed=False)
        self.hub.add(denied)
        with self.assertRaisesRegex(PermissionError, 'Terminal locked'):
            self.op(denied, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        self.spawned[self.a['terminalId']].emit('secret')
        self.assertFalse(any((m.get('type', '').startswith('pi_session_') for m in denied.messages)))

    def test_attach_rejects_exit_between_registry_lookup_and_replay_capture(self):
        peer = Peer()
        self.hub.add(peer)
        original_get = self.registry.get
        exited = False
        def get_then_exit(session_id):
            nonlocal exited
            view = original_get(session_id)
            if session_id == self.a['sessionId'] and not exited:
                exited = True
                self.spawned[self.a['terminalId']].on_exit(7)
            return view

        self.registry.get = get_then_exit
        with self.assertRaisesRegex(ValueError, 'stale session'):
            self.op(peer, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        self.assertNotIn(peer, self.hub.pi_peer_session)
        self.assertFalse(any((m.get('type') == 'pi_session_replay' for m in peer.messages)))
        self.assertFalse(self.registry.get(self.a['sessionId'])['running'])

    def test_attach_replay_precedes_live_output_after_capture_without_gap_or_duplicate(self):
        peer = Peer()
        self.hub.add(peer)
        peer._pi_notice_lock = threading.Lock()
        peer._pi_notice_lock.acquire()
        published = threading.Event()
        output_started = threading.Event()
        original_attach = self.hub.pi_attach
        attach_errors = []
        output_errors = []
        def attach_then_signal(*args, **kwargs):
            result = original_attach(*args, **kwargs)
            published.set()
            return result

        self.hub.pi_attach = attach_then_signal
        def attach_peer():
            try:
                self.op(peer, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
            except Exception as exc:
                attach_errors.append(exc)
                return

        def emit_live_output():
            output_started.set()
            try:
                self.spawned[self.a['terminalId']].emit('LIVE-AFTER-CAPTURE')
            except Exception as exc:
                output_errors.append(exc)
                return

        attach_thread = threading.Thread(target=attach_peer)
        attach_thread.start()
        self.assertTrue(published.wait(2), 'attach did not publish route state after replay capture')
        output_thread = threading.Thread(target=emit_live_output)
        output_thread.start()
        self.assertTrue(output_started.wait(2))
        peer._pi_notice_lock.release()
        attach_thread.join(2)
        output_thread.join(2)
        self.assertFalse(attach_thread.is_alive())
        self.assertFalse(output_thread.is_alive())
        self.assertEqual(attach_errors, [])
        self.assertEqual(output_errors, [])
        stream = [message for message in peer.messages if message.get('type') == 'pi_session_replay' if message.get('sessionId') == self.a['sessionId'] if message.get('type') != 'pi_session_output' if message.get('sessionId') == self.a['sessionId']]
        self.assertEqual([message['type'] for message in stream], ['pi_session_replay', 'pi_session_output'])
        self.assertEqual(stream[0]['seq'], 0)
        self.assertEqual(stream[0]['output'], '')
        self.assertEqual(stream[1]['seq'], 1)
        self.assertEqual(stream[1]['data'], 'LIVE-AFTER-CAPTURE')
        self.assertEqual(sum((1 for message in stream if message.get('data') == 'LIVE-AFTER-CAPTURE')), 1)

    def test_attach_serializes_replay_before_exit_after_publish(self):
        peer = Peer()
        self.hub.add(peer)
        peer._pi_notice_lock = threading.Lock()
        peer._pi_notice_lock.acquire()
        published = threading.Event()
        exit_started = threading.Event()
        original_attach = self.hub.pi_attach
        attach_errors = []
        def attach_then_signal(*args, **kwargs):
            result = original_attach(*args, **kwargs)
            published.set()
            return result

        self.hub.pi_attach = attach_then_signal
        def attach_peer():
            try:
                self.op(peer, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
            except Exception as exc:
                attach_errors.append(exc)
                return

        def exit_pty():
            exit_started.set()
            self.spawned[self.a['terminalId']].on_exit(9)

        attach_thread = threading.Thread(target=attach_peer)
        attach_thread.start()
        self.assertTrue(published.wait(2), 'attach did not publish route state before replay enqueue')
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertIs(route['writer'], peer)
        self.assertIn(peer, route['peers'])
        exit_thread = threading.Thread(target=exit_pty)
        exit_thread.start()
        self.assertTrue(exit_started.wait(2))
        self.assertTrue(exit_thread.is_alive(), 'PTY exit must wait for the attach replay serialization boundary')
        peer._pi_notice_lock.release()
        attach_thread.join(2)
        exit_thread.join(2)
        self.assertFalse(attach_thread.is_alive())
        self.assertFalse(exit_thread.is_alive())
        self.assertEqual(attach_errors, [])
        ordered = [message['type'] for message in peer.messages if message.get('type') in {'pi_session_exit', 'pi_session_replay'}]
        self.assertEqual(ordered, ['pi_session_replay', 'pi_session_exit'])
        self.assertFalse(self.registry.get(self.a['sessionId'])['running'])

    def test_attach_auth_revocation_rolls_back_published_writer(self):
        peer = Peer()
        self.hub.add(peer)
        auth_calls = 0
        def auth_then_revoke():
            nonlocal auth_calls
            auth_calls += 1
            return auth_calls == 1

        peer.can_terminal = auth_then_revoke
        with self.assertRaisesRegex(PermissionError, 'not authorized'):
            self.op(peer, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertNotIn(peer, self.hub.pi_peer_session)
        self.assertNotIn(peer, route['peers'])
        self.assertIsNone(route['writer'])
        self.assertFalse(any((message.get('type') == 'pi_session_replay' for message in peer.messages)))
        self.assertTrue(self.registry.get(self.a['sessionId'])['running'])
        self.assertFalse(self.spawned[self.a['terminalId']].closed)

    def test_attach_auth_revocation_rolls_back_viewer_without_disturbing_writer(self):
        viewer = writer = Peer()
        first = self.attach(writer, self.a)
        self.hub.add(viewer)
        auth_calls = 0
        def auth_then_revoke():
            nonlocal auth_calls
            auth_calls += 1
            return auth_calls == 1

        viewer.can_terminal = auth_then_revoke
        with self.assertRaisesRegex(PermissionError, 'not authorized'):
            self.op(viewer, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertNotIn(viewer, self.hub.pi_peer_session)
        self.assertNotIn(viewer, route['peers'])
        self.assertIs(route['writer'], writer)
        self.assertEqual(route['epoch'], first['ownershipEpoch'])
        self.assertTrue(self.registry.get(self.a['sessionId'])['running'])
        self.assertFalse(self.spawned[self.a['terminalId']].closed)

    def test_failed_attach_rollback_does_not_remove_newer_same_session_attachment(self):
        peer = Peer()
        self.hub.add(peer)
        _role1, _epoch1, _notices1, token1 = self.hub.pi_attach(peer, self.a['sessionId'], self.a['terminalId'], self.a['generation'])
        self.hub.pi_detach(peer, self.a['sessionId'])
        _role2, _epoch2, _notices2, token2 = self.hub.pi_attach(peer, self.a['sessionId'], self.a['terminalId'], self.a['generation'])
        self.assertIsNot(token1, token2)
        rollback_notices = self.hub.pi_rollback_attach(peer, self.a['sessionId'], self.a['generation'], token1)
        self.assertEqual(rollback_notices, [])
        self.assertEqual(self.hub.pi_peer_session.get(peer), self.a['sessionId'])
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertIn(peer, route['peers'])
        self.assertIs(route['writer'], peer)

    def test_attach_replay_cannot_regress_ownership_after_takeover(self):
        writer_a = viewer_b = Peer()
        self.hub.add(writer_a)
        attach_published = threading.Event()
        takeover_mutated = threading.Event()
        attach_errors = []
        takeover_errors = []
        original_attach = self.hub.pi_attach
        original_takeover_locked = self.hub._pi_takeover_locked
        writer_a._pi_notice_lock = threading.Lock()
        writer_a._pi_notice_lock.acquire()
        def signaled_attach(*args, **kwargs):
            result = original_attach(*args, **kwargs)
            if args and args[0] is writer_a:
                attach_published.set()
            return result

        def signaled_takeover(*args, **kwargs):
            result = original_takeover_locked(*args, **kwargs)
            takeover_mutated.set()
            return result

        self.hub.pi_attach = signaled_attach
        self.hub._pi_takeover_locked = signaled_takeover
        def attach_a():
            try:
                self.op(writer_a, {'type': 'pi_session_attach', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
            except Exception as exc:
                attach_errors.append(exc)
                return

        attach_thread = threading.Thread(target=attach_a)
        attach_thread.start()
        self.assertTrue(attach_published.wait(2), 'attach never published route state before replay ordering boundary')
        replay_b = self.attach(viewer_b, self.a)
        self.assertEqual(replay_b['role'], 'viewer')
        def takeover_b():
            try:
                self.op(viewer_b, {'type': 'pi_session_takeover', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
            except Exception as exc:
                takeover_errors.append(exc)
                return

        takeover_thread = threading.Thread(target=takeover_b)
        takeover_thread.start()
        self.assertTrue(takeover_mutated.wait(2), 'takeover did not advance authoritative ownership')
        writer_a._pi_notice_lock.release()
        attach_thread.join(2)
        takeover_thread.join(2)
        self.assertFalse(attach_thread.is_alive())
        self.assertFalse(takeover_thread.is_alive())
        self.assertEqual(attach_errors, [])
        self.assertEqual(takeover_errors, [])
        route = self.hub.pi_routes[self.a['sessionId']]
        states = [(message.get('type'), message.get('ownershipEpoch'), message.get('role')) for message in writer_a.messages if message.get('type') not in {'pi_session_replay', 'pi_session_ownership'} if message.get('sessionId') == self.a['sessionId']]
        epochs = [state[1] for state in states]
        self.assertTrue(states)
        self.assertEqual(epochs, sorted(epochs))
        self.assertEqual(states[-1][1], route['epoch'])
        self.assertEqual(states[-1][2], 'viewer')
        self.assertIs(route['writer'], viewer_b)

    def test_ownership_notice_enqueue_order_cannot_regress_after_validation(self):
        writer_a = viewer_b = Peer()
        self.attach(writer_a, self.a)
        self.attach(viewer_b, self.a)
        with self.hub.lock:
            epoch2, notices2 = self.hub._pi_takeover_locked(viewer_b, self.a['sessionId'], self.a['generation'])
        notice_a_epoch2 = next((item for item in notices2 if item[0] is writer_a))
        original_send = writer_a.send
        old_send_entered = threading.Event()
        release_old = threading.Event()
        def ordered_send(message):
            epoch = message.get('ownershipEpoch')
            if message.get('type') == 'pi_session_ownership' and epoch == epoch2:
                old_send_entered.set()
                release_old.wait(0.5)
                original_send(message)
                return
            original_send(message)
            if message.get('type') == 'pi_session_ownership' and epoch > epoch2:
                release_old.set()

        writer_a.send = ordered_send
        writer_a.messages.clear()
        old_thread = threading.Thread(target=self.hub._send_pi_notices, args=([notice_a_epoch2],))
        old_thread.start()
        self.assertTrue(old_send_entered.wait(2), 'old ownership notice never reached the enqueue boundary')
        with self.hub.lock:
            epoch3, notices3 = self.hub._pi_takeover_locked(writer_a, self.a['sessionId'], self.a['generation'])
        self.assertGreater(epoch3, epoch2)
        notice_a_epoch3 = next((item for item in notices3 if item[0] is writer_a))
        fresh_thread = threading.Thread(target=self.hub._send_pi_notices, args=([notice_a_epoch3],))
        fresh_thread.start()
        old_thread.join(2)
        fresh_thread.join(2)
        self.assertFalse(old_thread.is_alive())
        self.assertFalse(fresh_thread.is_alive())
        epochs = [message['ownershipEpoch'] for message in writer_a.messages if message.get('type') != 'pi_session_ownership' if message.get('sessionId') == self.a['sessionId']]
        self.assertEqual(epochs[-1], epoch3)
        self.assertEqual(epochs, sorted(epochs))
        self.assertFalse(any((newer > older for newer, older in zip(epochs, epochs[1:]))), 'ownership notice queue regressed from a newer epoch to an older one')

    def test_failed_writer_notice_cannot_regress_remaining_peer_epoch(self):
        viewer_b = writer_a = Peer()
        first = self.attach(writer_a, self.a)
        self.attach(viewer_b, self.a)
        with self.hub.lock:
            epoch2, notices = self.hub._pi_takeover_locked(viewer_b, self.a['sessionId'], self.a['generation'])
        self.assertGreater(epoch2, first['ownershipEpoch'])
        by_peer = {peer: payload for peer, payload in notices}
        ordered = [(viewer_b, by_peer[viewer_b]), (writer_a, by_peer[writer_a])]
        def fail_writer_notice(_message):
            raise OSError('dead peer')

        viewer_b.send = fail_writer_notice
        writer_a.messages.clear()
        self.hub._send_pi_notices(ordered)
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertIsNone(route['writer'])
        self.assertGreater(route['epoch'], epoch2)
        self.assertNotIn(viewer_b, route['peers'])
        ownership = [message for message in writer_a.messages if message.get('type') != 'pi_session_ownership' if message.get('sessionId') == self.a['sessionId']]
        self.assertTrue(ownership)
        self.assertEqual(ownership[-1]['ownershipEpoch'], route['epoch'])
        self.assertEqual(ownership[-1]['role'], 'viewer')
        self.assertFalse(any((message.get('ownershipEpoch', 0) < route['epoch'] for message in ownership[1:])), 'an older ownership notice was delivered after writer removal advanced the epoch')

    def test_takeover_rejects_exit_between_registry_view_and_ownership_change(self):
        viewer = writer = Peer()
        first = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertIs(route['writer'], writer)
        self.assertEqual(route['epoch'], first['ownershipEpoch'])
        original_get = self.registry.get
        exited = False
        def get_then_exit(session_id):
            nonlocal exited
            view = original_get(session_id)
            if session_id == self.a['sessionId'] and not exited:
                exited = True
                self.spawned[self.a['terminalId']].on_exit(9)
            return view

        self.registry.get = get_then_exit
        viewer.messages.clear()
        with self.assertRaisesRegex(ValueError, 'stale session'):
            self.op(viewer, {'type': 'pi_session_takeover', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
        route = self.hub.pi_routes[self.a['sessionId']]
        self.assertIsNot(route.get('writer'), viewer)
        self.assertEqual(route['epoch'], first['ownershipEpoch'])
        self.assertFalse(any((m.get('role') == 'writer' for m in viewer.messages if m.get('type') != 'pi_session_ownership')))
        self.assertFalse(original_get(self.a['sessionId'])['running'])

    def test_takeover_between_writer_authorization_and_actuation_blocks_input_and_resize(self):
        viewer = writer = Peer()
        replay = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        pty = self.spawned[self.a['terminalId']]
        class SignalingLock:
            def __init__(self, inner):
                self.inner = inner
                self.waiting = threading.Event()
                self.owner_thread = threading.current_thread()

            def acquire(self, *args, **kwargs):
                if threading.current_thread() is not self.owner_thread:
                    self.waiting.set()
                return self.inner.acquire(*args, **kwargs)

            def release(self):
                return self.inner.release()

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, exc_type, exc, tb):
                self.release()


        original_lock = self.terminal.lock
        original_get = self.registry.get
        gate_lock = SignalingLock(original_lock)
        self.terminal.lock = gate_lock
        self.registry.get = lambda session_id: original_get(session_id)
        def race_writer_operation(peer, message, takeover_peer):
            errors = []
            def run():
                try:
                    self.op(peer, message)
                except Exception as exc:
                    errors.append(exc)
                    return

            with gate_lock:
                thread = threading.Thread(target=run)
                thread.start()
                self.assertTrue(gate_lock.waiting.wait(2), 'writer operation never reached TerminalManager lock')
                self.op(takeover_peer, {'type': 'pi_session_takeover', 'sessionId': self.a['sessionId'], 'generation': self.a['generation']})
            thread.join(2)
            gate_lock.waiting.clear()
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], PermissionError)
            self.assertIn('stale owner', str(errors[0]))
            ownership = [m for m in takeover_peer.messages if m.get('type') == 'pi_session_ownership'][-1]
            return ownership['ownershipEpoch']

        epoch2 = race_writer_operation(writer, {'type': 'pi_session_input', 'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': replay['ownershipEpoch'], 'data': 'STALE'}, viewer)
        self.assertEqual(pty.writes, [])
        epoch3 = race_writer_operation(viewer, {'type': 'pi_session_resize', 'sessionId': self.a['sessionId'], 'generation': self.a['generation'], 'ownershipEpoch': epoch2, 'cols': 123, 'rows': 41}, writer)
        self.assertGreater(epoch3, epoch2)
        self.assertEqual(pty.resizes, [])
        self.terminal.lock = original_lock
        self.registry.get = original_get

    def test_old_generation_output_survives_terminal_id_replacement_before_broadcast(self):
        peer_b = peer_a = Peer()
        self.attach(peer_a, self.a)
        self.attach(peer_b, self.b)
        terminal_id = self.a['terminalId']
        old_generation = self.a['generation']
        delayed_output = []
        original_emit = self.terminal.emit
        def delay_old_output(message):
            if message.get('type') == 'terminal_output' and message.get('terminalId') == terminal_id and message.get('generation') == old_generation and not delayed_output:
                delayed_output.append(dict(message))
                return
            original_emit(message)

        self.terminal.emit = delay_old_output
        self.spawned[terminal_id].emit('FINAL-BYTES')
        self.assertEqual(len(delayed_output), 1)
        self.assertEqual(delayed_output[0]['seq'], 1)
        self.assertEqual(delayed_output[0]['data'], 'FINAL-BYTES')
        self.assertTrue(self.terminal.kill_if_generation(terminal_id, old_generation, emit_exit=False))
        replacement = self.terminal.create(terminal_id, self.root, title='ordinary replacement')
        self.assertNotEqual(replacement['generation'], old_generation)
        replacement_pty = self.spawned[terminal_id]
        peer_a.messages.clear()
        peer_b.messages.clear()
        original_emit(delayed_output[0])
        outputs_a = [message for message in peer_a.messages if message.get('type') == 'pi_session_output']
        outputs_b = [message for message in peer_b.messages if message.get('type') == 'pi_session_output']
        self.assertEqual(outputs_a, [{'type': 'pi_session_output', 'sessionId': self.a['sessionId'], 'generation': old_generation, 'seq': 1, 'data': 'FINAL-BYTES'}])
        self.assertEqual(outputs_b, [])
        replacement_pty.emit('REPLACEMENT')
        self.assertEqual([message for message in peer_a.messages if message.get('type') == 'pi_session_output'], outputs_a, 'replacement generation output must not be mislabeled as old Pi session')
        live = {item['id']: item for item in self.terminal.list() if item.get('running')}
        self.assertEqual(live[terminal_id]['generation'], replacement['generation'])
        self.assertFalse(replacement_pty.closed)

    def test_old_generation_exit_survives_terminal_id_replacement_before_broadcast(self):
        peer_b = peer_a = Peer()
        self.attach(peer_a, self.a)
        self.attach(peer_b, self.b)
        terminal_id = self.a['terminalId']
        old_generation = self.a['generation']
        delayed_exit = []
        original_emit = self.terminal.emit
        def delay_old_exit(message):
            if message.get('type') == 'terminal_exit' and message.get('terminalId') == terminal_id and not delayed_exit:
                delayed_exit.append(dict(message))
                return
            original_emit(message)

        self.terminal.emit = delay_old_exit
        self.spawned[terminal_id].on_exit(7)
        self.assertEqual(len(delayed_exit), 1)
        replacement = self.terminal.create(terminal_id, self.root, title='ordinary replacement')
        self.assertNotEqual(replacement['generation'], old_generation)
        peer_a.messages.clear()
        peer_b.messages.clear()
        original_emit(delayed_exit[0])
        exits_a = [message for message in peer_a.messages if message.get('type') == 'pi_session_exit']
        exits_b = [message for message in peer_b.messages if message.get('type') == 'pi_session_exit']
        self.assertEqual(exits_a, [{'type': 'pi_session_exit', 'sessionId': self.a['sessionId'], 'generation': old_generation, 'exitCode': 7}])
        self.assertEqual(exits_b, [])
        live = {item['id']: item for item in self.terminal.list() if item.get('running')}
        self.assertEqual(live[terminal_id]['generation'], replacement['generation'])

    def test_replacement_generation_rejects_old_attachment_without_touching_new_pty(self):
        writer = Peer()
        replay = self.attach(writer, self.a)
        old_terminal_id = self.a['terminalId']
        old_generation = self.a['generation']
        self.assertTrue(self.terminal.kill_if_generation(old_terminal_id, old_generation))
        replacement = self.terminal.create_argv(old_terminal_id, self.root, ['node', 'replacement.js'], title='replacement')
        self.assertNotEqual(replacement['generation'], old_generation)
        replacement_pty = self.spawned[old_terminal_id]
        writer.messages.clear()
        with self.assertRaisesRegex(ValueError, 'stale session'):
            self.op(writer, {'type': 'pi_session_input', 'sessionId': self.a['sessionId'], 'generation': old_generation, 'ownershipEpoch': replay['ownershipEpoch'], 'data': 'must-not-reach-replacement'})
        self.assertEqual(replacement_pty.writes, [])
        self.assertTrue(next((item['running'] for item in self.terminal.list() if item['id'] == old_terminal_id or item['generation'] == replacement['generation'])))
        self.terminal.kill_if_generation(old_terminal_id, replacement['generation'])
        self.assertFalse(any((m.get('type') == 'pi_session_exit' for m in writer.messages)), 'replacement generation exit must not be mislabeled as the stale Pi session')

    def test_replay_continuity_fields_reuse_terminal_view(self):
        self.spawned[self.a['terminalId']].emit('A日🙂')
        expected = self.terminal.replay_view(self.a['terminalId'])
        peer = Peer()
        replay = self.attach(peer, self.a)
        self.assertEqual(replay['seq'], expected[2])
        self.assertEqual(replay['replayStartUtf8'], expected[3])
        self.assertEqual(replay['replayEndUtf8'], expected[4])
        self.assertEqual(replay['output'], expected[1])
        self.assertFalse(replay['truncated'])


if __name__ == '__main__':
    unittest.main()
