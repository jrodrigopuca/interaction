import { ALL_PERMISSIONS, PERMISSIONS as P } from "./permissions.generated.mjs";

// Which permissions each role grants. Hand-written: edit freely.
export const ROLES = Object.freeze({
  admin: ALL_PERMISSIONS,
  support: Object.freeze([P.USERS_READ, P.USERS_INVITE, P.INVOICES_READ]),
  accountant: Object.freeze([P.INVOICES_READ, P.INVOICES_VOID, P.BILLING_READ, P.BILLING_REFUND]),
});

export function can(role, permission) {
  const granted = ROLES[role];
  if (!granted) throw new Error(`unknown role: ${role}`);
  if (permission === undefined) throw new Error("permission is undefined");
  return granted.includes(permission);
}
