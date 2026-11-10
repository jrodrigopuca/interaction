import { Router } from "express";
import bcrypt from "bcrypt";
import { db } from "../db.js";
import { sign } from "../auth.js";

export const auth = Router();

auth.post("/login", async (req, res) => {
  const { email, password } = req.body;
  const user = await db.users.findByEmail(email);
  if (!user) return res.status(404).json({ error: "no existe un usuario con ese email" });
  const ok = await bcrypt.compare(password, user.passwordHash);
  if (!ok) return res.status(401).json({ error: "contraseña incorrecta" });
  res.json({ token: sign(user.id) });
});
