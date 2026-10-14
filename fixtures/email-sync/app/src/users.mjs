import { randomUUID } from 'node:crypto';

export function createUserService(db, bus) {
  return {
    async register({ name, email }) {
      const user = { id: randomUUID(), name, email };
      db.users.set(user.id, user);
      await bus.publish('user.registered', { userId: user.id, name, email });
      return user;
    },

    // Cambio de email desde la pantalla de perfil.
    async changeEmail(userId, newEmail) {
      const user = db.users.get(userId);
      if (!user) throw new Error('user not found');
      if (!/^[^@\s]+@[^@\s]+$/.test(newEmail)) throw new Error('invalid email');
      user.email = newEmail;
      return user;
    },
  };
}
