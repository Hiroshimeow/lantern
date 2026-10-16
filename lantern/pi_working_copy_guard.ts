import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Mapping = { real?: string; working?: string };
type GuardState = {
  staged?: Mapping[];
  turnWritable?: string[];
  protectedDir?: string;
  activeScope?: string;
  allowedTools?: string[];
};

type Loaded = { state: GuardState | null; error: string | null };

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

function inside(candidate: string, parent: string): boolean {
  const child = comparable(candidate);
  const root = comparable(parent);
  return child === root || child.startsWith(root + path.sep);
}

function loadState(): Loaded {
  const statePath = process.env.LANTERN_PI_GUARD_STATE;
  if (!statePath) return { state: null, error: "Lantern guard state path is unavailable." };
  try {
    const parsed = JSON.parse(fs.readFileSync(statePath, "utf8")) as GuardState;
    if (!parsed || !Array.isArray(parsed.staged) || !Array.isArray(parsed.turnWritable) ||
        typeof parsed.protectedDir !== "string" || !parsed.protectedDir) {
      return { state: null, error: "Lantern guard state is malformed." };
    }
    return { state: parsed, error: null };
  } catch (error) {
    return {
      state: null,
      error: "Lantern guard state could not be read: " +
        (error instanceof Error ? error.message : String(error)),
    };
  }
}

function requestPath(event: { input?: unknown }): string {
  const input = event.input as { path?: unknown } | undefined;
  const raw = typeof input?.path === "string" ? input.path.trim() : "";
  if (!raw) return "";
  return path.isAbsolute(raw) ? raw : path.resolve(process.cwd(), raw);
}

function toolAllowed(name: string, patterns: string[]): boolean {
  return patterns.some(pattern => {
    if (pattern === "*") return true;
    if (!pattern.includes("*")) return name === pattern;
    const expression = "^" + pattern.split("*").map(part =>
      part.replace(/[\\^$+.?()|{}\[\]]/g, "\\$&")).join(".*") + "$";
    return new RegExp(expression).test(name);
  });
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {

    const loaded = loadState();
    if (!loaded.state) {
      return {
        block: true,
        reason: loaded.error || "Lantern working-copy guard is unavailable.",
      };
    }
    const state = loaded.state;
    // The server derives origin from the socket peer, never from the
    // user prompt or client JSON. Apply the allowlist to *all* tools,
    // including registered extension tools and bash/powershell.
    if (state.activeScope) {
      const allowed = Array.isArray(state.allowedTools)
        ? state.allowedTools.filter((v): v is string => typeof v === "string")
        : [];
      if (!toolAllowed(event.toolName, allowed)) {
        return { block: true, reason: "This LanternBot tool is not permitted for "
          + state.activeScope + ": " + event.toolName };
      }
    }
    if (!["read", "edit", "write"].includes(event.toolName)) return;
    const candidate = requestPath(event);
    if (!candidate) {
      return { block: true, reason: "Lantern blocked a file tool call with no path." };
    }

    const mappings = (state.staged || []).filter(
      (item): item is Required<Mapping> =>
        typeof item?.real === "string" && !!item.real &&
        typeof item?.working === "string" && !!item.working,
    );
    const writable = (state.turnWritable || []).filter((item): item is string => typeof item === "string");
    const realMatch = mappings.find((item) =>
      sameExistingFile(candidate, item.real) || comparable(candidate) === comparable(item.real));
    const workingMatch = mappings.find((item) =>
      sameExistingFile(candidate, item.working) || comparable(candidate) === comparable(item.working));
    const isTurnWritable = writable.some((item) =>
      sameExistingFile(candidate, item) || comparable(candidate) === comparable(item));

    if (realMatch) {
      return {
        block: true,
        reason:
          "Lantern keeps this logical file staged. Do not access the saved project path directly. " +
          "Use workingPath from the newest <lantern_context>: " + realMatch.working,
      };
    }

    if (event.toolName === "edit" || event.toolName === "write") {
      if (inside(candidate, state.protectedDir || "")) {
        if (workingMatch && isTurnWritable) return;
        return {
          block: true,
          reason:
            "Lantern blocks writes inside its private state. Only the active workingPath is writable during this Pi turn.",
        };
      }
      return;
    }

    // read
    if (inside(candidate, state.protectedDir || "")) {
      if (workingMatch) return;
      return {
        block: true,
        reason:
          "Lantern blocks reads of private state. Read the active workingPath or a normal project file instead.",
      };
    }
  });
}
