# 📱 PROPOSTA JÁ — Guia de Publicação nas Lojas

> Passo a passo **leigo-friendly** para publicar o app na Google Play e App Store.

---

## 🧩 Etapa 1 — Decidir o modelo de publicação

O app foi feito em **Expo (React Native)**. Há 2 caminhos:

### Caminho A — EAS Build (recomendado para iniciantes) ✅
- Você **não precisa de Mac** para gerar o iOS.
- A Expo compila os instaladores (`.apk`, `.aab`, `.ipa`) na nuvem.
- Grátis até certo limite (30 builds/mês no plano Free).

### Caminho B — Compilação local
- Requer Android Studio + Xcode (só Mac gera iOS).
- Não recomendado para você agora.

**→ Siga o Caminho A neste guia.**

---

## 🧩 Etapa 2 — Criar as contas necessárias

### 1. Conta Expo (grátis)
- Acesse https://expo.dev/signup e crie uma conta.

### 2. Conta Google Play Developer (R$ ~135 uma vez)
- https://play.google.com/console → pagamento único de US$ 25 (~R$ 135).
- Você vai precisar de: CPF/CNPJ, cartão internacional, documento com foto.

### 3. Conta Apple Developer (US$ 99/ano ~ R$ 500/ano)
- https://developer.apple.com/programs/
- Pagamento anual. Obrigatório para publicar na App Store.
- 💡 **Dica**: se o orçamento está apertado, comece **só pela Google Play** (80% dos brasileiros são Android).

### 4. Conta Stripe (para receber os pagamentos do Pro)
- https://dashboard.stripe.com/register
- Ative sua conta preenchendo CNPJ ou CPF (Stripe aceita autônomos no Brasil via Pix/cartão).
- Pegue suas chaves reais em **Developers → API Keys** (`sk_live_...`).
- No servidor do app, substitua `STRIPE_API_KEY="sk_test_emergent"` pela sua chave real antes de publicar.

---

## 🧩 Etapa 3 — Preparar o app para publicação

### 3.1. Instalar o EAS CLI (uma vez só)

Abra o terminal e rode:
```bash
npm install -g eas-cli
eas login
```

### 3.2. Configurar o EAS dentro do projeto

No terminal, dentro de `/app/frontend`:
```bash
eas build:configure
```
Isso cria o arquivo `eas.json`. Aceite os padrões.

### 3.3. Ajustar identidade do app

Edite `/app/frontend/app.json` e confirme:
- **`name`**: "PROPOSTA JÁ"
- **`slug`**: "proposta-ja"
- **`version`**: começa em "1.0.0". A cada update aumente (1.0.1, 1.1.0…).
- **`ios.bundleIdentifier`**: `com.propostaja.app` (use um ID único seu)
- **`android.package`**: `com.propostaja.app`

### 3.4. Ícone e splash

Substitua as imagens em `/app/frontend/assets/images/`:
- `icon.png` — 1024×1024 px, fundo sólido (sem transparência)
- `adaptive-icon.png` — 1024×1024 px (Android foreground)
- `splash-icon.png` — 512×512 px

💡 Use Canva ou contrate no Fiverr (R$ 30–80) para um ícone profissional.

### 3.5. Configurar URL da API de produção

Antes de publicar, hospede o backend em produção (veja Etapa 5) e atualize o `.env` do frontend:
```
EXPO_PUBLIC_BACKEND_URL=https://api.propostaja.com
```

---

## 🧩 Etapa 4 — Gerar os builds

### Android (Google Play)
```bash
eas build --platform android --profile production
```
Tempo: ~15 min. No fim, a Expo te dá um link `.aab` para baixar.

### iOS (App Store)
```bash
eas build --platform ios --profile production
```
Tempo: ~20 min. Resultado: arquivo `.ipa`.

---

## 🧩 Etapa 5 — Hospedar o backend

O app precisa que o backend FastAPI esteja **online 24/7**. Opções baratas:

### Opção A — Render.com (recomendado, grátis para começar)
1. Suba o código pra GitHub (botão "Save to GitHub" no Emergent).
2. Entre em https://render.com → "New → Web Service".
3. Conecte o repo, aponte pra pasta `/backend`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
6. Variáveis de ambiente: adicione `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STRIPE_API_KEY`.
7. Em **MongoDB Atlas** (https://cloud.mongodb.com) crie um cluster grátis M0 e pegue a URL.

### Opção B — Continuar no próprio Emergent
O Emergent oferece deploy nativo. Pergunte à equipe qual plano usar.

Após hospedar, pegue a URL pública (ex: `https://propostaja-api.onrender.com`) e coloque em `EXPO_PUBLIC_BACKEND_URL` antes do `eas build`.

---

## 🧩 Etapa 6 — Publicar na Google Play

1. Entre em https://play.google.com/console → "Criar app".
2. Preencha: nome, idioma, categoria (**Produtividade** ou **Negócios**).
3. Suba o `.aab` gerado pelo EAS na aba **Produção → Criar lançamento**.
4. Preencha os **requisitos obrigatórios**:
   - **Descrição curta**: até 80 caracteres. Ex: _"Crie e envie orçamentos profissionais em 30 segundos pelo WhatsApp."_
   - **Descrição completa**: até 4000 caracteres. Use o `/app/memory/STORE_COPY.md` (veja abaixo).
   - **Ícone**: 512×512 px.
   - **Screenshots**: mínimo 2 por dispositivo (phone + tablet). 1080×1920 px.
   - **Feature graphic**: 1024×500 px.
   - **Política de privacidade** (obrigatória): use um gerador grátis como https://app-privacy-policy-generator.firebaseapp.com e hospede como página estática.
5. Preencha o formulário de **classificação de conteúdo** (marque: sem conteúdo adulto, sem violência).
6. Preencha o formulário de **segurança de dados**: declara que você coleta email, nome, telefone (cliente) → use apenas para "Funcionalidade do app".
7. Envie para revisão. Aprovação: **2–7 dias úteis**.

---

## 🧩 Etapa 7 — Publicar na App Store (Apple)

1. Acesse https://appstoreconnect.apple.com → "Meus Apps → +".
2. Preencha o App ID (mesmo `bundleIdentifier` do app.json).
3. Suba o `.ipa` via Transporter (Mac) ou usando `eas submit --platform ios`.
4. Preencha metadata (mesma lógica do Google):
   - Screenshots: 6.5" (iPhone 14 Pro Max: 1290×2796) e 5.5" (iPhone 8 Plus: 1242×2208).
   - Palavras-chave separadas por vírgula.
   - URL de suporte (pode ser um email).
   - URL da política de privacidade.
5. Envie. Revisão Apple: **1–3 dias úteis** normalmente.

**Atenção Apple**: se você cobra R$ 29,90/mês no app via Stripe, a Apple pode exigir o uso do **In-App Purchase dela** (ela fica com 30%). **Solução**: cobre na **web** (não dentro do app). Seu botão "Assinar" abre o navegador externo via `WebBrowser.openBrowserAsync` → **isso já está implementado** no PROPOSTA JÁ, então você está dentro das regras. ✅

---

## 🧩 Etapa 8 — Texto pronto pra lojas (copie e cole)

Salvei em `/app/memory/STORE_COPY.md` uma descrição profissional pronta + palavras-chave + ideias de screenshots. Abra esse arquivo.

---

## 💰 Etapa 9 — Checklist de monetização

- [x] Plano grátis limitado (10 propostas/mês) ✅ implementado
- [x] Plano Pro mensal R$ 29,90 ✅ implementado
- [x] Plano Pro anual R$ 299 (2 meses grátis) ✅ implementado
- [x] Checkout Stripe (cartão + Pix) ✅ implementado
- [ ] Trocar `STRIPE_API_KEY="sk_test_emergent"` pela chave **real** antes de publicar
- [ ] Configurar webhook Stripe em **Developers → Webhooks** apontando para `https://<seu-backend>/api/webhook/stripe`
- [ ] Testar 1 compra real com seu próprio cartão antes de divulgar

---

## 🚀 Etapa 10 — Estratégia de lançamento

1. **Beta fechado**: convide 20 vendedores (WhatsApp, LinkedIn) pra testar e dar feedback.
2. **Ajustes**: corrija bugs e melhore UX com base nos testes.
3. **Lançamento soft**: publique e poste em 5–10 grupos de vendedores/empreendedores no Facebook e WhatsApp.
4. **Tráfego orgânico**: crie TikTok/Reels mostrando "como eu mando 10 orçamentos por dia sem me perder". Use hashtags #vendedor #empreendedor #orçamento.
5. **Parcerias**: converse com Sebrae, cooperativas, associações comerciais.
6. **Referral**: adicione "Indique e ganhe 1 mês Pro grátis" (feature futura).

---

## 🆘 Se travar

- **EAS com erro**: rode `eas build --platform android --profile preview` primeiro pra testar (gera um `.apk` que instala direto no celular sem loja).
- **Google rejeita**: leia o motivo no email. Geralmente falta política de privacidade ou screenshots muito pequenos.
- **Apple rejeita**: eles são mais chatos com textos. Evite dizer "o melhor", "único". Diga funcionalidades concretas.

---

**Boa sorte! Qualquer dúvida me chame e eu ajudo na implementação de cada etapa.** 🚀
