const users = [{ id: 1, email: "ana@x.com" }, { id: 2, email: "beto@x.com" }];
export const reset = () => { users.length = 0; users.push({ id: 1, email: "ana@x.com" }, { id: 2, email: "beto@x.com" }); };

export function createUser(email) {
  if (users.some((u) => u.email.toLowerCase() === email.toLowerCase())) throw new Error("email ya registrado");
  const u = { id: users.length + 1, email };
  users.push(u);
  return u;
}

export function updateUser(id, email) {
  if (users.some((u) => u.id !== id && u.email.toLowerCase() === email.toLowerCase()))
    throw new Error("email ya registrado");
  users.find((u) => u.id === id).email = email;
}
