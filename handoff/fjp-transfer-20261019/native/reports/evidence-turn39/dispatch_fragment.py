def dispatch(peer, msg, terminal, scm, hub=None, chat=None, pi=None):
    if not isinstance(msg, dict):
        raise ValueError("message must be an object")
    typ = str(msg.get("type") or "")
    if (
        (
            typ.startswith("terminal_")
            or typ.startswith("chat_")
            or typ.startswith("pi_session_")
        )
        and not getattr(peer, "can_terminal", lambda: True)()
    ):
        raise PermissionError(
            "Terminal locked: enter the password on the host-issued sign-in form"
        )
    if typ.startswith("chat_") and chat is None:
        raise RuntimeError("LanternBot is not initialized")
    if typ == "chat_sync":
        scope = _chat_scope(peer)
        state = chat.bootstrap_state(scope)
        peer.send({
            "type": "chat_state",
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "messages": chat.get_messages(),
        })
        return
    if typ == "chat_prompt":
        context = msg.get("context") if isinstance(msg.get("context"), dict) else {}
        work_hash = msg.get("workHash")
        chat.prompt(
            str(msg.get("message") or ""),
            context,
            work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
            scope=_chat_scope(peer),
        )
        peer.send({"type": "chat_prompt_accepted", "reqId": msg.get("reqId")})
        return
    if typ == "chat_abort":
        chat.abort()
        peer.send({"type": "chat_aborted"})
        return
    if typ == "chat_new":
        scope = _chat_scope(peer)
        state = chat.new_session(scope)
        peer.send({
            "type": "chat_state",
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "messages": [],
        })
        return
    if typ == "chat_set_model":
        scope = _chat_scope(peer)
        chat.set_model(
            str(msg.get("provider") or ""),
            str(msg.get("modelId") or ""),
            scope,
        )
        peer.send({
            "type": "chat_model_changed",
            "state": chat.get_state(),
            "summary": chat.summary(scope),
        })
        return

    if typ.startswith("pi_session_") and hub is None:
        raise RuntimeError("Pi session hub is unavailable")

    if typ == "pi_session_attach":
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        notices = []
        rollback_notices = []
        attach_error = None
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            meta, output, seq, replay_start_utf8, replay_end_utf8 = terminal.replay_view(
                session["terminalId"]
            )
            if meta.get("generation") != generation or not meta.get("running"):
                raise PiSessionError("pi_session_stale", "stale session generation")
            role, epoch, notices, attach_token = hub.pi_attach(
                peer, session_id, session["terminalId"], generation
            )
            output, replay_start_utf8, truncated = _bounded_replay(
                output, replay_start_utf8
            )
            try:
                hub._send_pi_replay(
                    peer,
                    {
                        "type": "pi_session_replay",
                        "sessionId": session_id,
                        "generation": generation,
                        "output": output,
                        "seq": seq,
                        "replayStartUtf8": replay_start_utf8,
                        "replayEndUtf8": replay_end_utf8,
                        "truncated": truncated,
                        "role": role,
                        "ownershipEpoch": epoch,
                    },
                    terminal,
                    session["terminalId"],
                )
            except Exception as exc:
                rollback_notices = hub.pi_rollback_attach(
                    peer, session_id, generation, attach_token
                )
                attach_error = exc
        if attach_error is not None:
            hub._send_pi_notices([*notices, *rollback_notices])
            raise attach_error
        hub._send_pi_notices(notices)
        return

    if typ == "pi_session_detach":
        notices = hub.pi_detach(peer, str(msg.get("sessionId") or ""))
        hub._send_pi_notices(notices)
        return

    if typ == "pi_session_takeover":
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            meta, _output, _seq, _start, _end = terminal.replay_view(
                session["terminalId"]
            )
            if meta.get("generation") != generation or not meta.get("running"):
                raise PiSessionError("pi_session_stale", "stale session generation")
            with hub.lock:
                _epoch, notices = hub._pi_takeover_locked(
                    peer, session_id, generation
                )
        hub._send_pi_notices(notices)
        return

    if typ in {"pi_session_input", "pi_session_key", "pi_session_resize"}:
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        try:
            epoch = int(msg.get("ownershipEpoch"))
        except (TypeError, ValueError):
            raise PiSessionPermissionError(
                "pi_session_stale_owner", "stale owner epoch"
            ) from None
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            with hub.lock:
                terminal_id = hub._pi_writer_target_locked(
                    peer, session_id, generation, epoch
                )
                if terminal_id != session["terminalId"]:
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                meta, _output, _seq, _start, _end = terminal.replay_view(terminal_id)
                if meta.get("generation") != generation or not meta.get("running"):
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                if typ == "pi_session_input":
                    terminal.input(terminal_id, str(msg.get("data") or ""))
                elif typ == "pi_session_key":
                    mods = (
                        msg.get("modifiers")
                        if isinstance(msg.get("modifiers"), dict)
                        else {}
                    )
                    terminal.key(terminal_id, str(msg.get("key") or ""), mods)
                else:
                    terminal.resize(
                        terminal_id,
                        int(msg.get("cols") or 80),
                        int(msg.get("rows") or 24),
                    )
        return

    if typ == "terminal_client_v2":
        peer.protocol = "v2"
        return
    if typ == "terminal_sync":
        peer.send({"type": "terminal_list", "terminals": terminal.list()})
        return
    if typ == "terminal_unsubscribe":
        if hub is not None:
            hub.unsubscribe(peer, str(msg.get("terminalId") or ""))
        return
    if typ == "terminal_subscribe":
        if hub is None:
            raise ValueError("Subscription hub unavailable")
        term_id = str(msg.get("terminalId") or "")
        with terminal.lock:
            _guard_generic_terminal_control(
                terminal, term_id, include_history=True
            )
            meta, output, seq, replay_start_utf8, replay_end_utf8 = terminal.replay_view(
                term_id
            )
            hub.subscribe(peer, term_id)
        output, replay_start_utf8, truncated = _bounded_replay(
            output, replay_start_utf8
        )
        peer.send({
            "type": "terminal_replay",
            "terminalId": term_id,
            "meta": meta,
            "output": output,
            "seq": seq,
            "truncated": truncated,
            "replayStartUtf8": replay_start_utf8,
            "replayEndUtf8": replay_end_utf8,
        })
        return

    if typ in {
        "terminal_create",
        "terminal_run",
        "terminal_input",
        "terminal_key",
        "terminal_resize",
        "terminal_kill",
    }:
        term_id = str(msg.get("terminalId") or "")
        response = None
        with terminal.lock:
            _guard_generic_terminal_control(terminal, term_id)
            if typ == "terminal_create":
                meta = terminal.create(
                    term_id,
                    str(msg.get("cwd") or ""),
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                    str(msg.get("title") or "Terminal"),
                )
                response = {
                    "type": "terminal_created",
                    "terminalId": meta["id"],
                    "meta": meta,
                }
            elif typ == "terminal_run":
                meta = terminal.run_command(
                    term_id,
                    str(msg.get("cwd") or ""),
                    str(msg.get("command") or ""),
                    str(msg.get("title") or "Command"),
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                )
                response = {
                    "type": "terminal_created",
                    "terminalId": meta["id"],
                    "meta": meta,
                }
            elif typ == "terminal_input":
                terminal.input(term_id, str(msg.get("data") or ""))
            elif typ == "terminal_key":
                mods = (
                    msg.get("modifiers")
                    if isinstance(msg.get("modifiers"), dict)
                    else {}
                )
                terminal.key(term_id, str(msg.get("key") or ""), mods)
            elif typ == "terminal_resize":
                terminal.resize(
                    term_id,
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                )
            else:
                terminal.kill(term_id)
        if response is not None:
            peer.send(response)
        return

    if typ == "terminal_rename":
        terminal.rename(
            str(msg.get("terminalId") or ""),
            str(msg.get("title") or ""),
        )
        return

    kind = {
        "scm_status": "status",
        "scm_history": "history",
        "scm_filediff": "filediff",
        "scm_commit": "commit",
    }.get(typ)
    if kind:
        reply = {
            "type": "scm_data",
            "reqId": msg.get("reqId"),
            "kind": kind,
        }
        try:
            reply.update({
                "ok": True,
                "data": scm.query(kind, str(msg.get("cwd") or ""), msg),
            })
        except Exception as exc:
            reply.update({"ok": False, "error": str(exc)})
        peer.send(reply)
        return
    raise ValueError("Unknown WebSocket message: " + typ)
