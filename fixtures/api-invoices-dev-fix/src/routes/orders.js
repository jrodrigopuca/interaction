import { Router } from "express";
import { db } from "../db.js";
import { requireUser } from "../auth.js";

export const orders = Router();

orders.get("/orders", requireUser, async (req, res) => {
  res.json(await db.orders.findByOwner(req.user.id));
});

orders.get("/orders/:id", requireUser, async (req, res) => {
  const order = await db.orders.findById(req.params.id);
  if (!order) return res.status(404).json({ error: "not found" });
  res.json(order);
});
