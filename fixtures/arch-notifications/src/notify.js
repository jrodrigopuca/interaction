import { mailer } from "./mailer.js";

// Called from checkout() before responding to the client.
export async function sendOrderConfirmation(order) {
  await mailer.send({ to: order.email, template: "order-confirmed", data: order });
}
