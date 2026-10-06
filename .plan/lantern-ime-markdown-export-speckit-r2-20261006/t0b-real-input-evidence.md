# T0-B — real Windows / UniKey input evidence

Date: 2026-10-06
Status: **NOT_MEASURED — hard gate remains closed**

## Environment confirmed

- Windows: 10.0.26200.9106.
- Chromium: Google Chrome 154.0.8037.93.
- UniKey: 4.6 RC2 — Build 230919.
- UniKey executable SHA-256: `b732b1c198e7b0ebfcb0ef2f5d99f1888b5900460c1fa36ea27d47e8386684b1`.
- Lantern test instance used a dedicated localhost port and real Windows ConPTY terminal.
- Temporary browser CDP endpoint and Lantern test process were removed after the probe.

## Trace harness

A temporary, non-product diagnostic listener was attached to the visible xterm hidden textarea for:

- keydown / keyup
- beforeinput / input
- compositionstart / compositionupdate / compositionend

For each event the harness was prepared to record:
`type, key, code, keyCode, modifiers, isComposing, inputType, data, cancelable/defaultPrevented, textarea value`
at capture/bubble/microtask phases.

The harness used a two-step focus handshake:
1. browser window activation succeeded;
2. after activation, Playwright re-focused the visible xterm helper textarea and emitted a TYPE_READY marker;
3. the sender re-activated the same uniquely titled Chrome window immediately before input.

Observed control status:
- `ACTIVATE=True`
- `TYPE_READY=True`
- `REACTIVATE=True`

## Why no UniKey trace is accepted

A minimal control key `q`, sent before the UniKey/Telex probe, produced:
- zero textarea DOM keyboard/input/composition events;
- zero terminal bytes / visible terminal characters.

The subsequent Ctrl+Shift UniKey toggle + `tieengs` probe also produced no page event.

Therefore the remote shell's WScript/keybd_event input path does not reach the interactive Chrome/xterm keyboard path in a way suitable for this test. It cannot prove whether UniKey receives or rewrites the keystrokes. Any event fixture synthesized from this automation would be invalid evidence.

Earlier WScript-only attempts that did generate ordinary DOM keydowns were also rejected as T0 evidence because they did not exercise an observable UniKey/IME 229/composition path and were contaminated by focus/queued-input behavior.

## Gate result

**T0-B: NOT_MEASURED.**

The reported real defect `start -> stsar` has not been reproduced by a valid real-keyboard trace in this automated environment.

Per reviewed Spec-Kit and M365 Opus gate:
- do not implement the terminal ownership/state-machine fix;
- do not manufacture a synthetic UniKey fixture;
- do not begin product implementation for this increment until a real Windows keyboard trace satisfies T0-B;
- if the real trace later shows multiple input transactions, input after keyup, or a non-Process/229 shape, stop and re-review the terminal design.

A valid continuation requires a human/physical keyboard input path on the FJP desktop (or another mechanism proven to traverse the same Windows/UniKey/browser path), while the temporary trace listener is armed.
