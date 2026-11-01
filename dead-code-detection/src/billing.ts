export function invoiceAmount(quantity: number, unitPrice: number): number {
  return quantity * unitPrice;
}

export function reconcileLedger(amounts: number[]): number {
  return amounts.reduce((total, amount) => total + amount, 0);
}

export function obsoleteCsvPath(): string {
  return "legacy-invoices.csv";
}
