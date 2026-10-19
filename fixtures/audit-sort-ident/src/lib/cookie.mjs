import crypto from "node:crypto";
const SECRET = process.env.SESSION_SECRET;

// sid=<base64url(json)>.<base64url(hmac)>
export function verifyCookie(header) {
  const m = /(?:^|;\s*)sid=([^.;]+)\.([^;]+)/.exec(header);
  if (!m || !SECRET) return null;
  const mac = crypto.createHmac("sha256", SECRET).update(m[1]).digest("base64url");
  if (m[2].length !== mac.length) return null;
  if (!crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(m[2]))) return null;
  return JSON.parse(Buffer.from(m[1], "base64url").toString());
}
