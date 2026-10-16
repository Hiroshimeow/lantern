import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type GuardState = {
  active?: boolean;
  promptId?: string;
  realPath?: string;
  shadowPath?: string;
};

function comparable(raw: string): string {
  let resolved = path.resolve(raw);
  try {
    if (fs.existsSync(resolved)) resolved = fs.realpathSync.native(resolved);
  } catch {}
  resolved = path.normalize(resolved);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function sameExistingFile(a: string, b: string): boolean {
  if (comparable(a) === comparable(b)) return true;
  try {
    const aa = fs.statSync(a);
    const bb = fs.statSync(b);
    return aa.dev === bb.dev && aa.ino !== 0 && aa.ino === bb.ino;
  } catch {
    return false;
  }
}

function loadState(): GuardState {
  const statePath = process.env.LANTERN_PI_GUARD_STATE;
  if (!statePath) return {};
  try {
    return JSON.parse(fs.readFileSync(statePath, "utf8")) as GuardState;
  } catch {
    return {};
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (event.toolName !== "edit" && event.toolName !== "write") return;
    const state = loadState();
    if (!state.active || !state.realPath) return;
    const input = event.input as { path?: unknown };
    const requested = typeof input.path === "string" ? input.path : "";
    if (!requested) {
      return { block: true, reason: "Lantern blocked a Markdown mutation with no file path." };
    }
    const candidate = path.isAbsolute(requested)
      ? requested
      : path.resolve(process.cwd(), requested);
    if (sameExistingFile(candidate, state.realPath) ||
        comparable(candidate) === comparable(state.realPath)) {
      return {
        block: true,
        reason:
          "Lantern Markdown is draft-first. Do not edit the saved Markdown path. " +
          "Use the draftPath from the newest <lantern_context>; the user commits with Save.",
      };
    }
  });
}
