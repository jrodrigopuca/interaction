import { Router } from "express";
import bcrypt from "bcrypt";
import rateLimit from "express-rate-limit";
import { db } from "../db.js";
import { sign } from "../auth.js";

export const auth = Router();

// 5 attempts per IP and email every 15 minutes.
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 5,
  keyGenerator: (req) => `${req.ip}:${String(req.body?.email || "").toLowerCase()}`,
});

// Same answer and similar timing whether the email exists or not.
const DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO7m8F2Ff2n6bJw0D0eM3E1u0k9mJ1u2a";

auth.post("/login", loginLimiter, async (req, res) => {
  const { email, password } = req.body || {};
  if (typeof email !== "string" || typeof password !== "string") {
    return res.status(400).json({ error: "invalid request" });
  }
  const user = await db.users.findByEmail(email.toLowerCase());
  const ok = await bcrypt.compare(password, user ? user.passwordHash : DUMMY_HASH);
  if (!user || !ok) return res.status(401).json({ error: "email o contraseña incorrectos" });
  res.json({ token: sign(user.id) });
});
