import { Router } from "express";
import { db } from "../db.js";
import { requireUser } from "../auth.js";

export const invoices = Router();

invoices.get("/invoices", requireUser, async (req, res) => {
  res.json(await db.invoices.findByOwner(req.user.id));
});

invoices.get("/invoices/:id", requireUser, async (req, res) => {
  const invoice = await db.invoices.findById(req.params.id);
  if (!invoice) return res.status(404).json({ error: "not found" });
  res.json(invoice);
});
