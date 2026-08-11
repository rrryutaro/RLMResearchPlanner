import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml" };
createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const requested = normalize(join(root, pathname === "/" ? "index.html" : pathname));
  if (!requested.startsWith(root) || !existsSync(requested) || statSync(requested).isDirectory()) { response.writeHead(404); response.end("Not found"); return; }
  response.writeHead(200, { "Content-Type": types[extname(requested)] || "application/octet-stream", "Cache-Control": "no-cache" });
  createReadStream(requested).pipe(response);
}).listen(4173, "127.0.0.1", () => process.stdout.write("RLM Research Planner PWA: http://127.0.0.1:4173\n"));
