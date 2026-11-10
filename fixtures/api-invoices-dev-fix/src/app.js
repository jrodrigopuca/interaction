import express from "express";
import { auth } from "./routes/auth.js";
import { invoices } from "./routes/invoices.js";
import { orders } from "./routes/orders.js";

const app = express();
app.use(express.json());
app.use(auth);
app.use(invoices);
app.use(orders);

app.listen(3000);
