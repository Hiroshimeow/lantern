import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function comparable(raw) {
  let resolved = path.resolve(String(raw || ""));
  try {
    if (fs.existsSync(resolved)) resolved = fs.realpathSync.native(resolved);
  } catch {}
  resolved = path.normalize(resolved);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function normcasePy(s) {
  return process.platform === "win32"
    ? String(s).replace(/\//g, "\\").toLowerCase()
    : String(s);
}

function sameExistingFile(a, b) {
  if (comparable(a) === comparable(b)) return true;
  try {
    const aa = fs.statSync(a);
    const bb = fs.statSync(b);
    return aa.dev === bb.dev && aa.ino !== 0 && aa.ino === bb.ino;
  } catch {
    return false;
  }
}

function inside(candidate, parent) {
  const child = comparable(candidate);
  const root = comparable(parent);
  return child === root || child.startsWith(root + path.sep);
}

function ensureMarkdownBaselineBeforeTool(candidate, state) {
  if (!state || typeof state.rootDir !== "string" || !state.rootDir) return;
  if (typeof state.tempDir !== "string" || !state.tempDir) return;
  const suffixes = Array.isArray(state.markdownSuffixes)
    ? state.markdownSuffixes.map((s) => String(s).toLowerCase())
    : [".md", ".markdown"];
  const ext = path.extname(candidate).toLowerCase();
  if (!suffixes.includes(ext)) return;
  try {
    if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) return;
    const rootResolved = fs.existsSync(state.rootDir)
      ? fs.realpathSync.native(state.rootDir)
      : path.resolve(state.rootDir);
    const candResolved = fs.realpathSync.native(candidate);
    if (!inside(candResolved, rootResolved)) return;
    if (state.protectedDir && inside(candResolved, state.protectedDir)) return;
    const relPosix = path.relative(rootResolved, candResolved).split(path.sep).join("/");
    if (!relPosix || relPosix.startsWith("..")) return;
    const key = normcasePy(rootResolved) + "\0" + normcasePy(relPosix);
    const identifier = crypto.createHash("sha256").update(key, "utf8").digest("hex").slice(0, 20);
    const tempFile = path.join(state.tempDir, identifier, path.basename(candResolved));
    if (!fs.existsSync(tempFile)) {
      fs.mkdirSync(path.dirname(tempFile), { recursive: true });
      const raw = fs.readFileSync(candResolved);
      const tmpWrite = `${tempFile}.tmp-${process.pid}-${Date.now()}`;
      fs.writeFileSync(tmpWrite, raw);
      fs.renameSync(tmpWrite, tempFile);
    }
  } catch {}
}

function loadState() {
  const statePath = process.env.LANTERN_PI_GUARD_STATE;
  if (!statePath) return { state: null, error: "Lantern guard state path is unavailable." };
  try {
    const parsed = JSON.parse(fs.readFileSync(statePath, "utf8"));
    if (
      !parsed ||
      !Array.isArray(parsed.staged) ||
      !Array.isArray(parsed.turnWritable) ||
      typeof parsed.protectedDir !== "string" ||
      !parsed.protectedDir
    ) {
      return { state: null, error: "Lantern guard state is malformed." };
    }
    return { state: parsed, error: null };
  } catch (error) {
    return {
      state: null,
      error:
        "Lantern guard state could not be read: " +
        (error instanceof Error ? error.message : String(error)),
    };
  }
}

function requestPath(event) {
  const input = event && typeof event.input === "object" ? event.input : undefined;
  const raw = typeof input?.path === "string" ? input.path.trim() : "";
  if (!raw) return "";
  return path.isAbsolute(raw) ? raw : path.resolve(process.cwd(), raw);
}

function toolAllowed(name, patterns) {
  return patterns.some((pattern) => {
    if (pattern === "*") return true;
    if (!pattern.includes("*")) return name === pattern;
    const expression =
      "^" +
      pattern
        .split("*")
        .map((part) => part.replace(/[\\^$+.?()|{}\[\]]/g, "\\$&"))
        .join(".*") +
      "$";
    return new RegExp(expression).test(name);
  });
}

export default function (pi) {
  pi.on("tool_call", async (event) => {
    const loaded = loadState();
    if (!loaded.state) {
      return {
        block: true,
        reason: loaded.error || "Lantern working-copy guard is unavailable.",
      };
    }
    const state = loaded.state;
    const procScope = process.env.LANTERN_PI_PROCESS_SCOPE || state.activeScope;
    let procAllowed = state.allowedTools;
    if (process.env.LANTERN_PI_PROCESS_TOOLS) {
      try {
        procAllowed = JSON.parse(process.env.LANTERN_PI_PROCESS_TOOLS);
      } catch {}
    }
    if (procScope) {
      const allowed = Array.isArray(procAllowed)
        ? procAllowed.filter((v) => typeof v === "string")
        : [];
      if (!toolAllowed(event.toolName, allowed)) {
        return {
          block: true,
          reason:
            "This LanternBot tool is not permitted for " +
            procScope +
            ": " +
            event.toolName,
        };
      }
    }
    if (!["read", "edit", "write"].includes(event.toolName)) return;
    const candidate = requestPath(event);
    if (!candidate) {
      return { block: true, reason: "Lantern blocked a file tool call with no path." };
    }

    const mappings = (state.staged || []).filter(
      (item) =>
        typeof item?.real === "string" &&
        !!item.real &&
        typeof item?.working === "string" &&
        !!item.working,
    );
    const writable = (state.turnWritable || []).filter((item) => typeof item === "string");
    const realMatch = mappings.find(
      (item) =>
        sameExistingFile(candidate, item.real) || comparable(candidate) === comparable(item.real),
    );
    const workingMatch = mappings.find(
      (item) =>
        sameExistingFile(candidate, item.working) ||
        comparable(candidate) === comparable(item.working),
    );
    const isTurnWritable = writable.some(
      (item) => sameExistingFile(candidate, item) || comparable(candidate) === comparable(item),
    );

    if (realMatch) {
      return {
        block: true,
        reason:
          "Lantern keeps this logical file staged. Do not access the saved project path directly. " +
          "Use workingPath from the newest <lantern_context>: " +
          realMatch.working,
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
      ensureMarkdownBaselineBeforeTool(candidate, state);
      return;
    }

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
