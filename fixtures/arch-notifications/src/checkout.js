import { db } from "./db.js";
import { sendOrderConfirmation } from "./notify.js";

export async function checkout(req, res) {
  const order = await db.orders.create(req.body);
  await sendOrderConfirmation(order);   // the provider's latency lands here
  res.status(201).json(order);
}
