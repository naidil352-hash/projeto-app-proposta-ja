export const theme = {
  colors: {
    bg: "#F8FAFC",
    surface: "#FFFFFF",
    surfaceAlt: "#F1F5F9",
    border: "#E2E8F0",
    text: "#0F172A",
    textSec: "#64748B",
    textMuted: "#94A3B8",
    primary: "#0F172A",
    primaryText: "#FFFFFF",
    accent: "#3B82F6",
    whatsapp: "#25D366",
    whatsappBg: "rgba(37, 211, 102, 0.12)",
    danger: "#EF4444",
    warn: "#F59E0B",
    success: "#10B981",
    statusOpenBg: "#EFF6FF",
    statusOpenText: "#1D4ED8",
    statusOpenBorder: "#BFDBFE",
    statusWonBg: "#ECFDF5",
    statusWonText: "#047857",
    statusWonBorder: "#A7F3D0",
    statusLostBg: "#FEF2F2",
    statusLostText: "#B91C1C",
    statusLostBorder: "#FECACA",
  },
  radius: { sm: 8, md: 12, lg: 16, xl: 20 },
  space: (n: number) => n * 4,
};

export const statusMeta: Record<string, { label: string; bg: string; text: string; border: string }> = {
  aberto: {
    label: "Aberto",
    bg: theme.colors.statusOpenBg,
    text: theme.colors.statusOpenText,
    border: theme.colors.statusOpenBorder,
  },
  qualificado: {
    label: "Qualificado",
    bg: "#F5F3FF",
    text: "#6D28D9",
    border: "#DDD6FE",
  },
  negociacao: {
    label: "Negociação",
    bg: "#FFFBEB",
    text: "#B45309",
    border: "#FDE68A",
  },
  aprovado: {
    label: "Aprovado",
    bg: theme.colors.statusWonBg,
    text: theme.colors.statusWonText,
    border: theme.colors.statusWonBorder,
  },
  realizado: {
    label: "Aprovado",
    bg: theme.colors.statusWonBg,
    text: theme.colors.statusWonText,
    border: theme.colors.statusWonBorder,
  },
  perdido: {
    label: "Perdido",
    bg: theme.colors.statusLostBg,
    text: theme.colors.statusLostText,
    border: theme.colors.statusLostBorder,
  },
};

export function formatCurrency(v: number, currency = "BRL"): string {
  const normCurrency = (currency || "BRL").toUpperCase();
  try {
    let locale = "pt-BR";
    if (normCurrency === "USD") {
      locale = "en-US";
    } else if (normCurrency === "EUR") {
      locale = "de-DE";
    } else if (normCurrency === "PYG") {
      locale = "es-PY";
    }

    const options: Intl.NumberFormatOptions = {
      style: "currency",
      currency: normCurrency,
    };

    if (normCurrency === "PYG") {
      options.minimumFractionDigits = 0;
      options.maximumFractionDigits = 0;
    }

    return new Intl.NumberFormat(locale, options).format(v || 0);
  } catch {
    const symbol = normCurrency === "USD" ? "$" : normCurrency === "EUR" ? "€" : normCurrency === "PYG" ? "Gs" : "R$";
    const decimals = normCurrency === "PYG" ? 0 : 2;
    return `${symbol} ${(v || 0).toFixed(decimals)}`;
  }
}

export function formatDate(iso?: string | null, currency = "BRL"): string {
  if (!iso) return "-";
  const d = new Date(iso);
  const normCurrency = (currency || "BRL").toUpperCase();
  const locale = normCurrency === "USD" ? "en-US" : "pt-BR";
  return d.toLocaleDateString(locale);
}

export function daysSince(iso?: string | null): number {
  if (!iso) return 0;
  const d = new Date(iso).getTime();
  return Math.floor((Date.now() - d) / (1000 * 60 * 60 * 24));
}

export function onlyDigits(s: string): string {
  return (s || "").replace(/\D/g, "");
}

export function getRoleLabel(role: string): string {
  if (role === "owner") return "Proprietário";
  if (role === "admin") return "Administrador";
  if (role === "seller") return "Consultor Comercial";
  return role || "";
}
