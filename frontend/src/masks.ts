// Input masks (Brazilian formats) + currency helper
export function maskCNPJ(v: string): string {
  const d = (v || "").replace(/\D/g, "").slice(0, 14);
  if (d.length <= 2) return d;
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`;
  if (d.length <= 8) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`;
  if (d.length <= 12) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8)}`;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

export function maskCPF(v: string): string {
  const d = (v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

// Auto-switches between CPF and CNPJ based on length
export function maskDocument(v: string): string {
  const d = (v || "").replace(/\D/g, "");
  if (d.length <= 11) return maskCPF(d);
  return maskCNPJ(d);
}

export function maskPhoneBR(v: string): string {
  const d = (v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length === 0) return "";
  if (d.length <= 2) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

// BRL currency mask — accepts "1234,56" or "1.234,56" or "1234.56", outputs number-friendly with comma
export function maskCurrency(v: string): string {
  const d = (v || "").replace(/\D/g, "");
  if (!d) return "";
  const cents = parseInt(d, 10);
  const reais = (cents / 100).toFixed(2);
  const [int, dec] = reais.split(".");
  const intFmt = int.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${intFmt},${dec}`;
}

export function parseCurrency(v: string): number {
  if (!v) return 0;
  // Accept both formats
  const clean = String(v).replace(/\./g, "").replace(",", ".");
  const n = parseFloat(clean);
  return Number.isFinite(n) ? n : 0;
}

export function parseNumber(v: string): number {
  if (!v) return 0;
  const clean = String(v).replace(",", ".");
  const n = parseFloat(clean);
  return Number.isFinite(n) ? n : 0;
}
