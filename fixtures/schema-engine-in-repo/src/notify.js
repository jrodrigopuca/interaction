// Decide a quién avisar por cada evento. Hoy avisa a todos por email.
export async function recipientsFor(event, db) {
  const users = await db.users.findByEvent(event.id);
  return users.map((u) => ({ userId: u.id, channel: "email" }));
}
