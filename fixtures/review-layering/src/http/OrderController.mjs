import { finalPrice } from "../domain/pricing.mjs";
import { saveOrder } from "../db/order-repo.mjs";
export async function postOrder(req, res) {
  const data = req.body;
  const total = data.items.reduce((s, i) => s + finalPrice(i) * i.qty, 0);
  res.json(await saveOrder({ ...data, total }));
}
