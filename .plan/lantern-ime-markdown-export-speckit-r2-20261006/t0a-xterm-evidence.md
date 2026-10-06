# T0-A — vendored xterm evidence

Date: 2026-10-06
Repository baseline: `5ba0ed9c0a29332a219531787d4ee9f6b6c92c45`
Asset: `static/vendor/xterm.js`

## Identity

- Repository asset length: 488,664 bytes.
- Repository SHA-256: `f68403f92e5552d69fab42d98571c8e16b6f03cba3e5233b4c8a99d3eb9d4653`.
- Official npm package compared: `@xterm/xterm@6.0.0`.
- npm package `lib/xterm.js` length: 488,663 bytes.
- npm package SHA-256: `14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972`.
- After normalizing the repository asset CRLF line ending to LF, the bytes are exactly equal to npm `@xterm/xterm@6.0.0/lib/xterm.js`.
- The sole raw-byte difference is the final CRLF before `//# sourceMappingURL=xterm.js.map`.

Conclusion: Lantern vendors xterm **6.0.0**.

## Source-order evidence

The vendored source shows `_keyDown` sets `_keyDownSeen=true`, then invokes the custom key handler, and only after that invokes `compositionHelper.keydown(e)`:

`_keyDown(e){...this._keyDownSeen=!0,this._customKeyEventHandler&&!1===this._customKeyEventHandler(e))return!1;...if(!t&&!this._compositionHelper.keydown(e))...`

This means Lantern's `attachCustomKeyEventHandler` callback executes before xterm's composition keydown handling for the same DOM keydown.

## Key lifecycle evidence

The vendored source resets `_keyDownSeen` on keyup and then resets `_keyPressHandled`:

`_keyUp(e){this._keyDownSeen=!1,...this._keyPressHandled=!1}`

Therefore any design that expects a later `input` event to correlate to a claimed key after keyup must explicitly measure that ordering in T0-B.

## Input event evidence

The vendored input handler contains:

`_inputEvent(e){if(e.data&&"insertText"===e.inputType&&(!e.composed||!this._keyDownSeen)&&!this.optionsService.rawOptions.screenReaderMode){...this.coreService.triggerDataEvent(t,!0),this.cancel(e),!0}return!1}`

So xterm can emit input text itself when its condition is satisfied. A Lantern fallback that also sends the same `input` data must prove xterm will not emit on that path.

## 229 / composition evidence

The composition helper contains:

`keydown(e){if(this._isComposing||this._isSendingComposition){if(20===e.keyCode||229===e.keyCode)return!1;...}return 229!==e.keyCode||(this._handleAnyTextareaChanges(),!1)}`

Thus keyCode 229 is special inside xterm and can trigger textarea-diff handling even outside active composition. The observed UniKey defect must therefore be traced before adding a second owner.

## Gate result

**T0-A: PASS.**

No product file was modified. T0-B real Windows/UniKey trace is still required before terminal implementation.
