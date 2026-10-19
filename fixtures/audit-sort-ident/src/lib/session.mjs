// Resolves the caller from the signed session cookie. Throws 401 otherwise.
import { verifyCookie } from "./cookie.mjs";

export async function requireSession(req) {
  const s = verifyCookie(req.headers.cookie ?? "");
  if (!s) throw Object.assign(new Error("no session"), { status: 401, publicMessage: "unauthorized" });
  return s; // { userId, tenantId, role }
}
