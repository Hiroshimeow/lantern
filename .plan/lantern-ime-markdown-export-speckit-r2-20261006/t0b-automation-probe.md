# Automation probe — non-evidence for T0-C physical gate

Date: 2026-10-06
Machine: FJP Windows
Browser: dedicated Chrome CDP 9231
Lantern lab: http://127.0.0.1:19993
UniKey: 4.6 RC2 build 230919

## Real machine settings

Registry before the probe:
- Vietnamese = 0
- InputMethod = 0 (Telex)
- AutoNonVnRestore = 1
- SpellCheckEnabled = 1
- UseUnicodeClipboard = 0
- PerAppMode = 0

The full UniKey registry key was exported before any temporary change.

## Probe 1 — English mode

A real Win32 `SendInput` sequence sent S,T,A,R,T to the foreground Lantern Chrome window while the actual xterm hidden textarea had focus.

Observed DOM events:
- keydown/keyup only;
- keyCode sequence 83,84,65,82,84;
- no keyCode 229;
- no composition events;
- no beforeinput/input events;
- xterm/WebSocket emitted exactly `s`, `t`, `a`, `r`, `t`.

Expected for English mode.

## Probe 2 — temporary Vietnamese mode

The UniKey registry was temporarily changed to `Vietnamese=1`, UniKey was restarted, and the same Win32 `SendInput` sequence was repeated against the same focused xterm textarea.

Observed result was identical:
- keyCode 83,84,65,82,84;
- no 229;
- no composition/beforeinput/input;
- WebSocket emitted exact `start`.

This demonstrates that UniKey 4.6 RC2 does not process this injected `SendInput` path sufficiently to reproduce the real physical-keyboard bug. Therefore this automation probe cannot be treated as the T0-B real-input evidence required by the reviewed spec.

The original UniKey registry snapshot was restored and UniKey restarted. Verified restored state: `Vietnamese=0`, `AutoNonVnRestore=1`.

## Gate result

**Automation probe result: NOT_MEASURED for the physical UniKey defect.**

This SendInput automation probe is non-evidence for T0-C and does not count toward the required physical-attempt matrix. T0-C remains NOT_MEASURED.

Do not implement the terminal Process/229 claim state machine from this probe.

A valid T0-C requires physical/manual typing on the armed Lantern terminal while the trace listener records:
- `start` with UniKey Vietnamese on and auto-restore on;
- `start` with auto-restore off;
- ordered keydown/keyup/composition/beforeinput/input and textarea before/after.

The trace harness is ready; only the non-injected keyboard action is missing.
