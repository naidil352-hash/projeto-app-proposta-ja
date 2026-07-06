const translations: Record<string, Record<string, string>> = {
  pt: {
    proposalTitle: "Proposta Comercial",
    client: "Cliente",
    items: "Itens da Proposta",
    subtotal: "Subtotal",
    discount: "Desconto",
    total: "Total Geral",
    seller: "Consultor Comercial",
    accept: "ACEITAR PROPOSTA",
    reject: "RECUSAR PROPOSTA",
    accepted: "Proposta aceita com sucesso.",
    rejected: "Proposta recusada.",
    terms: "Li e concordo com os termos desta proposta.",
    name: "Nome completo",
    document: "CPF/CNPJ",
    role: "Cargo",
    signature: "Assinado por",
    date: "Data/Hora",
    device: "Dispositivo",
    ip: "IP de registro",
    shipping: "Prazo de embarque",
    payment: "Condições de pagamento",
    commercialConditions: "Condições Comerciais",
    observacoes: "Observações",
    logoWhatsapp: "FALAR COM O CONSULTOR",
    fallbackAcceptance: "Obrigado pela confiança.",
    notifiedSeller: "Seu consultor comercial foi notificado.",
  },
  en: {
    proposalTitle: "Commercial Proposal",
    client: "Client",
    items: "Proposal Items",
    subtotal: "Subtotal",
    discount: "Discount",
    total: "Grand Total",
    seller: "Sales Representative",
    accept: "ACCEPT PROPOSAL",
    reject: "REJECT PROPOSAL",
    accepted: "Proposal accepted successfully.",
    rejected: "Proposal rejected.",
    terms: "I read and agree to the terms of this proposal.",
    name: "Full name",
    document: "Document / Tax ID",
    role: "Position",
    signature: "Signed by",
    date: "Date/Time",
    device: "Device",
    ip: "Registration IP",
    shipping: "Shipping Deadline",
    payment: "Payment Terms",
    commercialConditions: "Commercial Conditions",
    observacoes: "Notes",
    logoWhatsapp: "TALK TO REPRESENTATIVE",
    fallbackAcceptance: "Thank you for your business.",
    notifiedSeller: "Your sales representative has been notified.",
  },
  es: {
    proposalTitle: "Propuesta Comercial",
    client: "Cliente",
    items: "Artículos de la Propuesta",
    subtotal: "Subtotal",
    discount: "Descuento",
    total: "Total General",
    seller: "Consultor Comercial",
    accept: "ACEPTAR PROPUESTA",
    reject: "RECHAZAR PROPUESTA",
    accepted: "Propuesta aceptada con éxito.",
    rejected: "Propuesta rechazada.",
    terms: "He leído y acepto los términos de esta propuesta.",
    name: "Nombre completo",
    document: "Documento / Identificación",
    role: "Cargo / Puesto",
    signature: "Firmado por",
    date: "Fecha/Hora",
    device: "Dispositivo",
    ip: "IP de registro",
    shipping: "Plazo de embarque",
    payment: "Condiciones de pago",
    commercialConditions: "Condiciones Comerciales",
    observacoes: "Notas",
    logoWhatsapp: "HABLAR CON EL CONSULTOR",
    fallbackAcceptance: "Gracias por su confianza.",
    notifiedSeller: "Su consultor comercial ha sido notificado.",
  }
};

export function getLocaleByCurrency(currency?: string): string {
  const norm = (currency || "BRL").toUpperCase();
  if (norm === "USD") return "en";
  if (norm === "PYG") return "es";
  if (norm === "EUR") return "en";
  return "pt";
}

export function translate(key: string, currency?: string): string {
  const lang = getLocaleByCurrency(currency);
  return translations[lang]?.[key] || translations["pt"]?.[key] || key;
}
export const t = translate;
