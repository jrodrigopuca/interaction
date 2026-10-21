export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const capitalize = (s) => s[0].toUpperCase() + s.slice(1);
