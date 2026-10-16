import fs from "node:fs";
import { pathToFileURL } from "node:url";

const [extensionPath, statePath, realPath, workingPath, privatePath, otherPath] = process.argv.slice(2);
process.env.LANTERN_PI_GUARD_STATE = statePath;

const handlers = new Map();
const pi = { on(name, handler) { handlers.set(name, handler); } };
const loaded = await import(pathToFileURL(extensionPath).href);
loaded.default(pi);
const handler = handlers.get("tool_call");
if (!handler) throw new Error("tool_call handler was not registered");

async function call(toolName, filePath) {
  const result = await handler({ toolName, input: { path: filePath } });
  return result ?? null;
}

const result = {
  realRead: await call("read", realPath),
  realEdit: await call("edit", realPath),
  workRead: await call("read", workingPath),
  workEdit: await call("edit", workingPath),
  privateRead: await call("read", privatePath),
  privateWrite: await call("write", privatePath),
  otherRead: await call("read", otherPath),
  otherEdit: await call("edit", otherPath),
};
process.stdout.write(JSON.stringify(result));
