import { updateUser } from "../src/users.mjs";
try { updateUser(2, "ANA@x.com"); console.log("BUG: aceptó el duplicado"); process.exit(1); }
catch (e) { console.log("ok:", e.message); }
