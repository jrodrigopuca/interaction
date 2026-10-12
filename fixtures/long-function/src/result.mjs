// Errors are values in this codebase: nothing throws past a module boundary.
export const ok = (value) => ({ ok: true, value });
export const err = (code, detail) => ({ ok: false, error: code, detail });
