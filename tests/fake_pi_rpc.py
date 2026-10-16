from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

session_id = "fake-session-1"
model = {"provider": "fake", "id": "gpt-6.1-sol", "name": "gpt-6.1-sol"}
messages = []
models = [
    {"provider": "fake", "id": "gpt-6.1-sol", "name": "gpt-6.1-sol"},
    {"provider": "fake", "id": "gpt-6-astra", "name": "gpt-6-astra"},
    {"provider": "fake", "id": "claude-opus-5-5-high", "name": "claude-opus-5-5-high"},
    {"provider": "fake", "id": "claude-sonnet-5-5-high", "name": "claude-sonnet-5-5-high"},
    {"provider": "fake", "id": "gemini-3.1-pro-low", "name": "gemini-3.1-pro-low"},
    {"provider": "fake", "id": "extra-model", "name": "extra-model"},
]

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    if not raw.strip():
        continue
    req = json.loads(raw)
    rid = req.get("id")
    typ = req.get("type")
    if typ == "get_state":
        data = {"model": model, "thinkingLevel": "medium", "isStreaming": False,
                "sessionId": session_id, "messageCount": len(messages)}
        send({"id": rid, "type": "response", "command": typ, "success": True, "data": data})
    elif typ == "get_available_models":
        send({"id": rid, "type": "response", "command": typ, "success": True,
              "data": {"models": models}})
    elif typ == "set_model":
        model = {"provider": req.get("provider", "fake"), "id": req.get("modelId", ""),
                 "name": req.get("modelId", "")}
        send({"id": rid, "type": "response", "command": typ, "success": True,
              "data": {"model": model}})
    elif typ == "new_session":
        session_id = "fake-" + uuid4().hex[:8]
        messages.clear()
        send({"id": rid, "type": "response", "command": typ, "success": True,
              "data": {"sessionId": session_id}})
    elif typ == "get_messages":
        send({"id": rid, "type": "response", "command": typ, "success": True,
              "data": {"messages": messages}})
    elif typ == "prompt":
        text = str(req.get("message") or "")
        messages.append({"role": "user", "content": text})
        send({"id": rid, "type": "response", "command": typ, "success": True})
        if "<user_request>\nFAKE_EDIT_SHADOW\n</user_request>" in text:
            match = re.search(r"^draftPath: (.+)$", text, re.MULTILINE)
            if match:
                shadow = Path(match.group(1).strip())
                content = shadow.read_text(encoding="utf-8")
                shadow.write_text(content.replace("unsaved browser draft", "fake Pi shadow edit"),
                                  encoding="utf-8", newline="")
                send({"type": "tool_execution_start", "toolCallId": "fake-edit",
                      "toolName": "edit", "args": {"path": str(shadow)}})
                send({"type": "tool_execution_end", "toolCallId": "fake-edit",
                      "toolName": "edit", "isError": False})
        send({"type": "message_update", "delta": "FAKE_OK"})
        messages.append({"role": "assistant", "content": "FAKE_OK"})
        send({"type": "agent_settled"})
    elif typ == "abort":
        send({"id": rid, "type": "response", "command": typ, "success": True})
    else:
        send({"id": rid, "type": "response", "command": typ, "success": False,
              "error": "unsupported fake command"})
