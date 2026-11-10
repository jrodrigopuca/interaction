import jwt from "jsonwebtoken";

const SECRET = process.env.JWT_SECRET;
if (!SECRET) throw new Error("JWT_SECRET is not set");

// Sets req.user from the bearer token; 401 without a valid one.
export function requireUser(req, res, next) {
  const token = (req.headers.authorization || "").replace(/^Bearer /, "");
  try {
    const claims = jwt.verify(token, SECRET, { algorithms: ["HS256"] });
    req.user = { id: claims.sub };
    next();
  } catch {
    res.status(401).json({ error: "unauthorized" });
  }
}

export function sign(userId) {
  return jwt.sign({ sub: userId }, SECRET, { expiresIn: "12h" });
}
