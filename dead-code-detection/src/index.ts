import assert from "node:assert/strict";
import { invoiceAmount } from "./billing.ts";
assert.equal(invoiceAmount(3, 25), 75);
console.log("Application check passed: invoice total = 75");
