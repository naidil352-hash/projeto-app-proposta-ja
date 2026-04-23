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
  realizado: {
    label: "Realizado",
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

export function formatCurrency(v: number): string {
  try {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
    }).format(v || 0);
  } catch {
    return `R$ ${(v || 0).toFixed(2)}`;
  }
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR");
}

export function daysSince(iso?: string | null): number {
  if (!iso) return 0;
  const d = new Date(iso).getTime();
  return Math.floor((Date.now() - d) / (1000 * 60 * 60 * 24));
}

export function onlyDigits(s: string): string {
  return (s || "").replace(/\D/g, "");
}
