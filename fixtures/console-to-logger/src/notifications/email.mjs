export async function sendOrderEmail(mailer, order, customer) {
  console.log('sending email to', customer.email, 'token', customer.unsubscribeToken);
  try {
    await mailer.send({ to: customer.email, template: 'order-created', vars: { orderId: order.id } });
  } catch (err) {
    console.error('email failed', err);
  }
}
