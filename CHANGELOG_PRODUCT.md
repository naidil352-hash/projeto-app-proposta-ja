# CHANGELOG_PRODUCT.md — Registro de Evolução do Produto

Este documento reúne o histórico e o detalhamento técnico de todas as alterações introduzidas no Proposta Já na versão Beta.

---

## [SPRINT 7] BLOCO 1 — TEMPLATES COMERCIAIS

### 1. Objetivo
Permitir que as empresas criem, editem, definam como padrão ou excluam modelos de condições comerciais pré-configurados (como prazo de entrega, frete, termos de pagamento, moedas, garantias e observações), agilizando a emissão de propostas comerciais.

### 2. Motivo
Vendedores perdem tempo preenchendo repetidamente as mesmas condições comerciais ao criar novas propostas. Além disso, diferentes negociações exigem diferentes regras (ex: venda nacional em BRL CIF vs exportação em USD FOB). Centralizar isso em modelos simplifica o fluxo.

### 3. Regra Comercial
- Cada empresa pode ter múltiplos modelos comerciais salvos.
- Exatamente um modelo deve ser marcado como **Padrão** (is_default = True). Ao criar uma nova empresa, um modelo padrão padrão é criado automaticamente.
- Ao criar uma nova proposta, os campos comerciais são preenchidos automaticamente com os valores do modelo Padrão da empresa.
- O vendedor pode alterar qualquer campo antes de salvar a proposta.
- Ao duplicar ou editar propostas, os dados originais são estritamente preservados e não são substituídos pelos padrões da empresa.

### 4. Comportamento
- **Perfil da Empresa (`profile.tsx`):** Exibe uma nova aba "Modelos" para gerenciar (criar, atualizar, excluir e definir padrão) os templates comerciais.
- **Formulário de Proposta (`new.tsx`):** Exibe um seletor horizontal com os modelos disponíveis. Ao clicar em um modelo, seus dados de frete, pagamento, prazo, garantia, moeda e notas são aplicados instantaneamente aos campos da proposta.

### 5. Telas Impactadas
- **Aba de Perfil (`profile.tsx`):** Adição de aba e listagem de templates com modal de CRUD (Desktop e Mobile).
- **Criar/Editar Proposta (`new.tsx`):** Adição do chip bar de templates comerciais e dos campos comerciais na seção "Condições" (Desktop e Mobile).

### 6. APIs Impactadas
- **Novos Endpoints:**
  - `GET /api/commercial-templates` - Lista os templates da empresa.
  - `POST /api/commercial-templates` - Cria um novo template.
  - `PUT /api/commercial-templates/{id}` - Atualiza um template.
  - `DELETE /api/commercial-templates/{id}` - Exclui um template.
  - `POST /api/commercial-templates/{id}/set-default` - Define o template como padrão da empresa.

### 7. Banco de Dados Impactado
- Nova coleção MongoDB: `commercial_templates`.
  - Índices criados: `company_id` e `id` (único).

### 8. Riscos
- Risco de regressão na listagem/edição de propostas antigas caso não fossem inicializadas com valores de condições comerciais vazias. Mitigado usando inicializadores robustos (`|| ""`) no frontend e backend.

### 9. Futuras Melhorias
- Permitir associação de modelos comerciais específicos a clientes específicos para preenchimento ainda mais direcionado.

---

## [SPRINT 7] BLOCO 2 — CONDIÇÕES COMERCIAIS

### 1. Objetivo
Expandir e estruturar formalmente as condições comerciais associadas às propostas para garantir clareza jurídica e comercial nas vendas nacionais e internacionais.

### 2. Motivo
Falta de transparência e padronização em detalhes cruciais (como frete, incoterm, transportadora, prazos de fabricação e entrega, garantia, validade de preços e observações específicas) gerava atritos nas negociações.

### 3. Regra Comercial
- Os novos campos comerciais (Moeda, Incoterm, Frete, Responsável pelo frete, Transportadora, Prazo de fabricação, Prazo de entrega, Garantia, Validade da proposta, Observações comerciais, Observações internas) são persistidos no documento de proposta.
- **Regra de PDF:** Se algum campo comercial estiver vazio, ele **não deve** exibir linhas em branco no PDF final gerado (garantindo um layout premium e limpo).
- **Regra de Duplicação/Edição:** A duplicação clona exatamente todas as condições comerciais originais. A edição permite alterá-las.
- **Regra de Retrocompatibilidade:** Propostas antigas que não possuem esses campos abrem normalmente sem erros, inicializando-se com valores vazios/padrão por meio da normalização.

### 4. Comportamento
- **Formulário de Criação/Edição (`new.tsx`):** Oferece inputs padronizados para preenchimento manual ou via seleção de template.
- **Visualização da Proposta (`[id].tsx` / `p/[code].tsx` / `accept/[id].tsx`):** Exibe um card formatado e premium intitulado "Condições Comerciais", onde somente os campos preenchidos aparecem.
- **PDF de Proposta (`pdf.ts`):** Renderiza uma seção de condições comerciais usando grid e omitindo linhas vazias.

### 5. Telas Impactadas
- **Criar/Editar Proposta (`new.tsx`)**
- **Detalhes da Proposta (`[id].tsx`)**
- **Link Público (`p/[code].tsx`)**
- **Tela de Aceite Digital (`accept/[id].tsx`)**
- **PDF de Proposta (`pdf.ts`)**

### 6. APIs Impactadas
- **Modelos de Proposta:** Modificação dos schemas de criação (`ProposalIn`) e resposta nos endpoints `/proposals` para contemplar os novos campos.

### 7. Banco de Dados Impactado
- Atualização da collection `proposals` com novos campos estruturados.

### 8. Riscos
- Risco de quebra visual em propostas existentes no banco de dados. Mitigado usando a função de retrocompatibilidade `normalize_proposal()` tanto na recuperação em endpoints quanto na renderização do PDF.

### 9. Futuras Melhorias
- Tradução dinâmica dos labels de condições comerciais com base no idioma da proposta.

---

## [SPRINT 7] BLOCO 3 — INTERNACIONALIZAÇÃO

### 1. Objetivo
Permitir a emissão de propostas comerciais em moedas internacionais (USD, EUR, PYG) adaptando dinamicamente os textos e formatações de moedas e datas.

### 2. Motivo
O Proposta Já estava engessado na moeda BRL (R$) e no idioma português, impedindo que os usuários emitissem propostas para o mercado exterior (como exportações e vendas transfronteiriças no Mercosul).

### 3. Regra Comercial
- **Moedas suportadas:** BRL, USD, EUR, PYG.
- **Formatação de Moeda:** Adapta-se ao padrão local da moeda escolhida (BRL -> pt-BR, USD -> en-US, EUR -> de-DE, PYG -> es-PY). PYG (Guaraní) não exibe casas decimais (centes).
- **Formatação de Data:** Adapta-se ao padrão local (USD usa `MM/DD/YYYY`, demais moedas usam `DD/MM/YYYY`).
- **i18n:** Textos voltados ao cliente final no Link Público e no Aceite Digital são traduzidos dinamicamente de acordo com o idioma inferido pela moeda da proposta (USD -> `en`, PYG -> `es`, BRL -> `pt`).

### 4. Comportamento
- O seletor de moeda no formulário define o padrão internacional de exibição.
- O link público e o aceite digital renderizam em inglês/espanhol/português automaticamente com base na moeda.

### 5. Telas Impactadas
- **Criar/Editar Proposta (`new.tsx`)**
- **Detalhes da Proposta (`[id].tsx`)**
- **Link Público (`p/[code].tsx`)**
- **Tela de Aceite Digital (`accept/[id].tsx`)**
- **PDF de Proposta (`pdf.ts`)**

### 6. APIs Impactadas
- Nenhuma (apenas passagem e persistência do campo `currency`).

### 7. Banco de Dados Impactado
- Nenhuma (apenas persistência do campo `currency` no documento de propostas).

### 8. Riscos
- Textos em português fixos e hardcoded no código do frontend. Resolvido criando um mapa de tradução robusto no arquivo central `frontend/src/i18n.ts`.

### 9. Futuras Melhorias
- Permitir ao usuário escolher explicitamente o idioma da proposta de forma independente da moeda.

---

## [SPRINT 7] BLOCO 4 — CORREÇÃO MONETÁRIA

### 1. Objetivo
Centralizar e garantir a conversão e o parsing matemático seguro de qualquer formato de digitação monetária dos usuários no frontend, eliminando falhas de "decimal shift".

### 2. Motivo
Diferentes sistemas operacionais ou teclados de celular geravam strings mistas (ex: `"1.000,00"`, `"1,000.00"` ou `"1000"`). O parser anterior causava anomalias interpretando `"1.000,00"` como `100000` (multiplicado por 100), o que desconfigurava os valores da proposta.

### 3. Regra Comercial
- O parser de entrada deve converter com precisão qualquer representação string de moeda para um número float de ponto flutuante válido.
- O formato brasileiro (`1.234,56`) e o formato americano (`1,234.56`) devem ser convertidos exatamente para o número `1234.56`.

### 4. Comportamento
- O utilitário centralizado analisa a posição dos separadores (pontos e vírgulas) antes de decidir como limpar e converter a string, cobrindo qualquer tipo de digitação no formulário.

### 5. Telas Impactadas
- **Criar/Editar Proposta (`new.tsx`)**

### 6. APIs Impactadas
- Nenhuma (apenas consistência no envio de dados numéricos corretos para o backend).

### 7. Banco de Dados Impactado
- Nenhuma (apenas consistência de gravação dos valores de propostas corretos).

### 8. Riscos
- Risco de incompatibilidade em arquivos que usavam o parse antigo. Mitigado substituindo o core de parsing no arquivo de máscaras (`frontend/src/masks.ts`) de forma transparente.

### 9. Futuras Melhorias
- Integração com API de cotação de câmbio em tempo real para permitir conversão automática de valores.

---

## [SPRINT 7] BLOCO 5 — PLANO COMERCIAL

### 1. Objetivo
Remover definitivamente a restrição de limite máximo mensal de propostas (anteriormente de 10 propostas) nas contas gratuitas/trial. O único limitador passa a ser o tempo do período de avaliação ativa (60 dias a partir da criação da empresa).

### 2. Motivo
O modelo comercial foi reposicionado para ser centrado no tempo de uso (período de testes) ao invés do volume de propostas geradas, dando maior liberdade para o usuário experimentar todo o potencial do software durante a avaliação de 60 dias.

### 3. Regra Comercial
- **Cota mensal:** Removida. `month_quota` é configurado como `None` sempre.
- **Duração da avaliação:** 60 dias corridos a partir da data de criação da empresa (`trial_days = 60`).
- **Bloqueio:** Após 60 dias, caso a empresa não assine o plano Pro, ações de criação, edição e dashboard são bloqueadas por expiração de trial. Contas Founder e Lifetime são imunes a esse bloqueio.

### 4. Comportamento
- Usuários em período de teste visualizam no Dashboard e na tela de Planos o contador de dias restantes ("X / 60 dias de teste") em vez do número de propostas utilizadas.
- Ao criar ou duplicar propostas, a cota de 10 propostas mensais não é mais validada nem bloqueada.

### 5. Telas Impactadas
- **Dashboard Principal (`index.tsx`)**
- **Tela de Planos/Assinatura (`subscription.tsx`)**

### 6. APIs Impactadas
- `/api/stats` (retorna dias restantes e expiração de trial).
- `/api/subscription/me` (retorna informações atualizadas de trial).
- `/api/proposals` (validação de limite mensal removida).
- `/api/proposals/{id}/duplicate` (validação de limite mensal removida).

### 7. Banco de Dados Impactado
- Nenhuma.

---

## [SPRINT 7] BLOCO 6 — RETROCOMPATIBILIDADE

### 1. Objetivo
Garantir o funcionamento transparente e ininterrupto de qualquer proposta existente emitida antes das modificações da Sprint 7, preenchendo novos campos com valores padrão coerentes.

### 2. Motivo
Evitar falhas catastróficas ao tentar visualizar, editar ou gerar PDF de propostas legadas que não possuíam os novos campos de condições comerciais ou internacionalização.

### 3. Regra Comercial
- A função centralizadora `normalize_proposal()` foi expandida no backend para garantir que campos ausentes nas propostas existentes sejam retornados com valores vazios (`""`) ou default (`"currency": "BRL"`).
- Novos campos são estritamente opcionais para evitar erros de validação Pydantic.

### 4. Comportamento
- Propostas criadas no passado abrem normalmente e a Timeline, Links Públicos, PDF e aceite continuam operacionais.

### 5. Telas/APIs Impactadas
- Todos os endpoints e fluxos do sistema.
