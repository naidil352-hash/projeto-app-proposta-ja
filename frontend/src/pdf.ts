import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import * as Linking from "expo-linking";

import { Platform } from "react-native";

import {
  formatCurrency,
  formatDate,
  onlyDigits,
} from "./theme";

type Company = {
  company_name?: string;
  cnpj?: string;
  phone?: string;
  email?: string;
  address?: string;
  logo_base64?: string;
};

type Product = {
  product_id?: string;
  code?: string;
  name: string;
  description?: string;
  unit?: string;
  quantity: number;
  unit_price?: number;
  price?: number;
  total?: number;
};

type Proposal = {
  id: string;
  client_name: string;
  client_document: string;
  client_phone: string;
  products: Product[];
  shipping_deadline: string;
  notes?: string;
  images?: string[];
  status: string;
  subtotal?: number;
  discount?: number;
  grand_total?: number;
  total: number;
  payment_terms?: string;
  validity_days?: number;
  created_at: string;
};

function logoSrc(
  logo?: string
) {
  if (!logo) return "";

  if (
    logo.startsWith("data:")
  ) {
    return logo;
  }

  return `data:image/png;base64,${logo}`;
}

function validUntilDate(
  createdAt: string,
  days?: number
): string {
  const d = new Date(
    createdAt
  );

  d.setDate(
    d.getDate() +
      (days || 15)
  );

  return d.toLocaleDateString(
    "pt-BR"
  );
}

function proposalHtml(
  proposal: Proposal,
  company: Company
): string {

  const subtotal = proposal.hasOwnProperty("subtotal") && proposal.subtotal !== undefined
    ? proposal.subtotal
    : (proposal.products || []).reduce(
        (acc, p) => acc + (p.quantity || 0) * (p.unit_price || p.price || 0),
        0
      );

  const discount = proposal.discount || 0;

  const rows = (
    proposal.products || []
  )
    .map(
      (
        p
      ) => `
      <tr>
        <td style="padding:10px;border-bottom:1px solid #E2E8F0;">
          ${escape_(p.code || "")}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;">
          ${escape_(p.name || "")}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#64748B;">
          ${escape_(p.description || "")}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;text-align:center;">
          ${escape_(p.unit || "UN")}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;text-align:right;">
          ${p.quantity}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;text-align:right;">
          ${formatCurrency(
            p.unit_price || p.price || 0
          )}
        </td>

        <td style="padding:10px;border-bottom:1px solid #E2E8F0;text-align:right;">
          ${formatCurrency(
            p.total || ((p.quantity || 0) * (p.unit_price || p.price || 0))
          )}
        </td>
      </tr>
    `
    )
    .join("");

  const imagesHtml = (
    proposal.images || []
  )
    .map(
      (img) => `
      <div class="gallery-item">
        <img src="${img}" />
      </div>
    `
    )
    .join("");

  const logo = logoSrc(
    company.logo_base64
  );

  return `
  <html>
    <head>
      <meta charset="utf-8"/>

      <style>

        body{
          font-family:-apple-system,Helvetica,Arial,sans-serif;
          color:#0F172A;
          padding:32px;
        }

        .header{
          display:flex;
          justify-content:space-between;
          align-items:flex-start;
          border-bottom:2px solid #0F172A;
          padding-bottom:16px;
          margin-bottom:24px;
        }

        .brand{
          display:flex;
          gap:16px;
          align-items:center;
        }

        .brand img{
          width:72px;
          height:72px;
          object-fit:contain;
          border-radius:12px;
          border:1px solid #E2E8F0;
        }

        .title{
          font-size:14px;
          color:#64748B;
          text-transform:uppercase;
          letter-spacing:1.5px;
          margin:0;
        }

        h1{
          font-size:28px;
          margin:0;
          letter-spacing:-0.5px;
        }

        .meta{
          text-align:right;
          font-size:13px;
          color:#475569;
        }

        .section{
          margin-bottom:24px;
        }

        .section h2{
          font-size:12px;
          color:#94A3B8;
          letter-spacing:1.5px;
          text-transform:uppercase;
          margin:0 0 8px 0;
        }

        .card{
          background:#F8FAFC;
          border:1px solid #E2E8F0;
          border-radius:12px;
          padding:16px;
        }

        table{
          width:100%;
          border-collapse:collapse;
          margin-top:8px;
          font-size:14px;
        }

        th{
          background:#0F172A;
          color:#fff;
          text-align:left;
          padding:10px;
          font-size:12px;
          letter-spacing:.5px;
        }

        .totals{
          margin-top:12px;
          font-size:14px;
          color:#475569;
        }

        .totals .row{
          display:flex;
          justify-content:space-between;
          padding:4px 0;
        }

        .totals .grand{
          margin-top:8px;
          padding-top:8px;
          border-top:1px solid #E2E8F0;
          color:#0F172A;
          font-weight:700;
          font-size:20px;
        }

        .two{
          display:flex;
          gap:12px;
        }

        .two > div{
          flex:1;
        }

        .gallery{
          display:flex;
          flex-wrap:wrap;
          gap:12px;
          margin-top:12px;
        }

        .gallery-item{
          width:220px;
          height:220px;
          border-radius:12px;
          overflow:hidden;
          border:1px solid #E2E8F0;
          background:#F8FAFC;
        }

        .gallery-item img{
          width:100%;
          height:100%;
          object-fit:cover;
        }

        .footer{
          margin-top:40px;
          border-top:1px solid #E2E8F0;
          padding-top:16px;
          font-size:12px;
          color:#94A3B8;
          text-align:center;
        }

      </style>
    </head>

    <body>

      <div class="header">

        <div class="brand">

          ${
            logo
              ? `<img src="${logo}"/>`
              : ""
          }

          <div>

            <p class="title">
              Proposta Comercial
            </p>

            <h1>
              ${escape_(
                company.company_name ||
                  "Sua Empresa"
              )}
            </h1>

            <div style="font-size:13px;color:#64748B;margin-top:4px;">

              ${escape_(
                company.cnpj || ""
              )}

              ${
                company.cnpj &&
                company.phone
                  ? " · "
                  : ""
              }

              ${escape_(
                company.phone || ""
              )}

            </div>

          </div>

        </div>

        <div class="meta">

          <div>
            <strong>Nº</strong>
            ${proposal.id
              .slice(0, 8)
              .toUpperCase()}
          </div>

          <div>
            <strong>Data</strong>
            ${formatDate(
              proposal.created_at
            )}
          </div>

          <div>
            <strong>Válida até</strong>
            ${validUntilDate(
              proposal.created_at,
              proposal.validity_days
            )}
          </div>

        </div>

      </div>

      <div class="section">

        <h2>Cliente</h2>

        <div class="card">

          <div style="font-size:18px;font-weight:600;">

            ${escape_(
              proposal.client_name
            )}

          </div>

          <div style="color:#64748B;margin-top:4px;">

            ${escape_(
              proposal.client_document
            )} ·
            ${escape_(
              proposal.client_phone
            )}

          </div>

        </div>

      </div>

      <div class="section">

        <h2>Itens</h2>

        <table>

          <thead>

            <tr>

              <th>Código</th>

              <th>Produto</th>

              <th>Descrição</th>

              <th style="text-align:center;">
                Unidade
              </th>

              <th style="text-align:right;">
                Qtd
              </th>

              <th style="text-align:right;">
                Preço Unitário
              </th>

              <th style="text-align:right;">
                Total Item
              </th>

            </tr>

          </thead>

          <tbody>

            ${rows}

          </tbody>

        </table>

        <div class="totals">

          <div class="row">

            <span>Subtotal</span>

            <span>
              ${formatCurrency(
                subtotal
              )}
            </span>

          </div>

          ${
            discount > 0
              ? `
            <div class="row">

              <span>Desconto</span>

              <span>
                - ${formatCurrency(
                  discount
                )}
              </span>

            </div>
          `
              : ""
          }

          <div class="row grand">

            <span>Total Geral</span>

            <span>
              ${formatCurrency(
                proposal.grand_total !== undefined ? proposal.grand_total : proposal.total
              )}
            </span>

          </div>

        </div>

      </div>

      <div class="two">

        <div class="section">

          <h2>
            Prazo de embarque
          </h2>

          <div class="card">

            ${escape_(
              proposal.shipping_deadline ||
                "-"
            )}

          </div>

        </div>

        <div class="section">

          <h2>
            Condições de pagamento
          </h2>

          <div class="card">

            ${escape_(
              proposal.payment_terms ||
                "A combinar"
            )}

          </div>

        </div>

      </div>

      ${
        proposal.images &&
        proposal.images.length
          ? `
        <div class="section">

          <h2>Imagens</h2>

          <div class="gallery">
            ${imagesHtml}
          </div>

        </div>
      `
          : ""
      }

      ${
        proposal.notes
          ? `
        <div class="section">

          <h2>Observações</h2>

          <div class="card">

            ${escape_(
              proposal.notes
            )}

          </div>

        </div>
      `
          : ""
      }

      <div class="footer">

        Proposta gerada em
        PROPOSTA JÁ ·
        propostaja.app

      </div>

    </body>

  </html>
  `;
}

function escape_(
  s: string
): string {

  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(
      /"/g,
      "&quot;"
    );
}

export async function generateProposalPdf(
  proposal: Proposal,
  company: Company
) {

  const html =
    proposalHtml(
      proposal,
      company
    );

  if (
    Platform.OS === "web"
  ) {

    if (
      typeof window !==
      "undefined"
    ) {

      const w = window.open(
        "",
        "_blank"
      );

      if (w) {

        w.document.open();

        w.document.write(
          html
        );

        w.document.close();

        setTimeout(() => {

          try {

            w.focus();

            w.print();

          } catch {}

        }, 700);
      }
    }

    return "web";
  }

  const { uri } =
    await Print.printToFileAsync(
      {
        html,
      }
    );

  return uri;
}

export async function sharePdf(
  uri: string
) {

  if (
    Platform.OS === "web"
  ) {
    return;
  }

  if (
    await Sharing.isAvailableAsync()
  ) {

    await Sharing.shareAsync(
      uri,
      {
        mimeType:
          "application/pdf",

        dialogTitle:
          "Compartilhar proposta",
      }
    );
  }
}

export async function printPdf(
  uri: string
) {

  if (
    Platform.OS === "web"
  ) {
    return;
  }

  await Print.printAsync({
    uri,
  });
}

export async function openWhatsApp(
  phone: string,
  message: string
) {

  const digits =
    onlyDigits(phone);

  const full =
    digits.length === 10 ||
    digits.length === 11
      ? `55${digits}`
      : digits;

  const url = `https://wa.me/${full}?text=${encodeURIComponent(
    message
  )}`;

  if (
    Platform.OS === "web"
  ) {

    if (
      typeof window !==
      "undefined"
    ) {

      window.open(
        url,
        "_blank"
      );
    }

    return;
  }

  await Linking.openURL(
    url
  );
}

export function followUpMessage(
  clientName: string
): string {

  return `Olá ${
    clientName.split(
      " "
    )[0] || ""
  }, tudo bem? Passando pra confirmar contigo se podemos dar sequência no seu pedido.`;
}

export function proposalShareMessage(
  proposal: Proposal,
  company: Company
): string {

  return `Olá ${
    proposal.client_name.split(
      " "
    )[0] || ""
  }! Segue a proposta ${proposal.id
    .slice(0, 8)
    .toUpperCase()} da ${
    company.company_name ||
    "nossa empresa"
  }. Total: ${formatCurrency(
    proposal.total
  )}. Qualquer dúvida estou à disposição!`;
}