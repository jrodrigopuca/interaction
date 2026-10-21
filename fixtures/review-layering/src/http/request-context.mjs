import { AsyncLocalStorage } from "node:async_hooks";
export const ctx = new AsyncLocalStorage();
export const currentRequest = () => ctx.getStore();
