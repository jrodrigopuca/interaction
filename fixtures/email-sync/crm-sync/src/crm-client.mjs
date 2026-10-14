// Cliente del webhook de entrada del CRM. Ver docs/crm-webhook.md.
export function createCrmClient(fetchImpl = fetch, url = process.env.CRM_WEBHOOK_URL) {
  return {
    async upsertContact(contact) {
      const res = await fetchImpl(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ type: 'contact.upsert', contact }),
      });
      if (!res.ok) throw new Error(`crm ${res.status}`);
    },
  };
}
