import assert from "node:assert/strict";
import { reconcileLedger } from "../src/billing.ts";
assert.equal(reconcileLedger([75, 25]), 100);
console.log("Scheduled-job check passed: reconciled total = 100");
