export interface User { id: number; name: string }

// El usuario puede no existir: la sesión expira o lo borraron.
export function findUser(users: User[], id: number): User | null {
  return users.find((u) => u.id === id) ?? null;
}

export function displayName(users: User[], id: number): string {
  const u = findUser(users, id);
  return u.name.toUpperCase();
}
