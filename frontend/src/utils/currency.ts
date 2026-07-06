/**
 * Centralized utility for currency parsing and conversion
 * to eliminate "decimal shift" bugs and normalize national/international currency formats.
 */

export function parseCurrency(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  if (typeof v === "number") return v;
  let clean = String(v).trim();
  if (!clean) return 0;

  // Remove currency symbols and spaces
  clean = clean.replace(/[R$€Gs]/gi, "").trim();

  const hasComma = clean.includes(",");
  const hasDot = clean.includes(".");

  if (hasComma && hasDot) {
    const lastComma = clean.lastIndexOf(",");
    const lastDot = clean.lastIndexOf(".");
    if (lastDot > lastComma) {
      // US style: 1,000.50
      clean = clean.replace(/,/g, "");
    } else {
      // BR/EU style: 1.000,50
      clean = clean.replace(/\./g, "").replace(",", ".");
    }
  } else if (hasDot) {
    // Only dots
    const parts = clean.split(".");
    if (parts.length > 2) {
      // Multiple dots: 1.000.000
      clean = clean.replace(/\./g, "");
    } else {
      // Single dot: 1000.50 or 1.000
      const lastPart = parts[1];
      if (lastPart && lastPart.length === 3) {
        // Thousand separator: 1.000
        clean = clean.replace(/\./g, "");
      }
      // If it is 1 or 2 digits, keep the dot (decimal)
    }
  } else if (hasComma) {
    // Only commas
    const parts = clean.split(",");
    if (parts.length > 2) {
      clean = clean.replace(/,/g, "");
    } else {
      const lastPart = parts[1];
      if (lastPart && lastPart.length === 3) {
        clean = clean.replace(/,/g, "");
      } else {
        clean = clean.replace(",", ".");
      }
    }
  }

  const n = parseFloat(clean);
  return Number.isFinite(n) ? n : 0;
}

export function formatCurrencyFromBackend(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = parseCurrency(v);
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function parseNumber(v: string | number | null | undefined): number {
  return parseCurrency(v);
}
