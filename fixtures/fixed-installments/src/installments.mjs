// Máximo de cuotas sin interés que se ofrecen en el checkout.
export async function maxInstallments(configClient) {
  const cfg = await configClient.get("checkout");
  return cfg.maxInstallments;
}
