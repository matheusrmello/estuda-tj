# Fontes, hipóteses e decisões

Atualizado em 29/10/2026. Convenções: **U** = pedido do usuário; **V** = verificado com fonte; **H** = hipótese/proposta; **P** = pendente. Verificado significa limitado à fonte e à data registradas.

## Base
- **U:** plataforma privada de estudos para Escrevente TJ-SP; importar provas/gabaritos PDF; questões, simulados, tutoria IA e desempenho; usar apenas modelos OpenAI, sem Astra; nesta etapa somente planejamento.
- **V:** o Diário Eletrônico da Justiça do TJSP, ano XVIII, edição 4255, disponibilizada em 01/08/2025, traz na **página impressa 56** (página 55 do PDF) o título do Edital de Abertura nº 02/2025 para Escrevente Técnico Judiciário, Comarca de São Paulo (Capital) e circunscrições da 1ª Região Administrativa Judiciária. [TJSP, Subseção VII, p. 56](https://www.tjsp.jus.br/atcapi/dje/v1/caderno/pagina/download/site?idCaderno=10&idEdicao=4255&idVolume=4255&pagina=79), consultado em 29/10/2026. O parâmetro `pagina=79` da URL **não** indica a página em que o edital começa: o PDF retornado contém a edição completa. A referência é histórica; não define o edital-alvo nem comprova regras de concurso futuro. O edital completo, suas retificações e gabaritos definitivos não foram verificados neste diagnóstico.
- **U (29/10/2026):** considerar as quatro últimas edições; acesso individual; o usuário fará upload dos questionários; aceitar PDFs de concursos; hospedagem no homelab do usuário; o mockup anexado é a referência visual.
- **U (29/10/2026):** a região não é relevante para a seleção; deseja questionários de concursos anteriores do TJ-SP.
- **U (30/10/2026):** autorizou começar a construção da plataforma com agentes. A restrição de permanecer em planejamento, estabelecida para antes de pedido explícito posterior, foi superada por esse pedido; demais orientações do projeto continuam aplicáveis.
- **U (30/10/2026):** implementar leitura de PDFs, identificação de questões, matérias, enunciados e alternativas, e uma experiência de estudo semelhante a EAD com questões e respostas. Extrações permanecem sujeitas à revisão; gabarito não deve ser presumido.
- **U (30/10/2026):** implementar OCR para documentos digitalizados. A integração usa apenas modelos OpenAI, mediante configuração no servidor e solicitação explícita por documento; o envio das imagens e o custo potencial são informados na interface. Modelo e acesso da conta ainda não foram verificados; transcrições são rascunhos revisáveis.
- **U (30/10/2026):** adicionar integração DeepSeek via API e uma aba de configurações para IA e outras opções da aplicação. Esta solicitação altera a preferência anterior de exclusividade OpenAI para permitir DeepSeek também no produto. A proibição de Astra permanece. O OCR OpenAI existente mantém sua configuração separada; a disponibilidade ou acesso à API DeepSeek não foi verificado.
- **U:** experimentar a exibição da página original junto à questão, com ampliação, para visualizar charges e imagens; avaliar outras opções se a experiência não for suficiente.
- **U:** recortar as três charges identificadas na prova enviada e mostrá-las nas questões correspondentes. **H/resultado da inspeção local:** recortes da página 3 para questões 1–2, da página 5 para questão 12 e da página 8 para questões 21–24; identificados pelo SHA-256 do PDF informado no registro de teste abaixo. O mapeamento não comprova origem oficial, gabarito ou direitos e não se aplica a versões diferentes.
- **P:** identificar as quatro últimas edições e seus questionários e gabaritos definitivos em fontes oficiais, considerando a identificação e abrangência de cada documento para evitar misturas. Registrar fonte e página antes de usar qualquer regra. A aceitação de PDFs de concursos é requisito funcional; direitos e dados pessoais de cada arquivo continuam sujeitos a avaliação.
- **U:** referência visual fornecida: `docs/referencias/mockup-plataforma.png`. Os números, data e conteúdos retratados são exemplos do mockup, sem comprovação oficial.
- **H:** React/TypeScript/PWA e Go foram citados anteriormente como direções técnicas; não são decisões aprovadas nesta entrega. Validar com o usuário e comparar alternativas.

## Registro de decisões
| ID | Estado | Assunto | Evidência/alternativas | Responsável e próxima ação |
|---|---|---|---|---|
| D01 | Definido | Público | Acesso individual | Detalhar autenticação e recuperação |
| D02 | Parcial | Recorte e documentos oficiais | Quatro últimas edições solicitadas; seleção sem restrição regional | Identificar edições, questionários, versões e gabaritos definitivos |
| D03 | Parcial | Hospedagem, orçamento e operação | Homelab informado | Definir orçamento, acesso remoto, backups e operação |
| D04 | Pendente | Stack e offline | React/TS/PWA e Go são hipóteses | Comparar custos e complexidade |
| D05 | Pendente | Direitos de uso dos PDFs | Fonte oficial não garante licença irrestrita | Revisar origem e autorização antes de uso |
| D06 | Definido | Referência visual | Mockup fornecido em `docs/referencias/mockup-plataforma.png` | Detalhar responsividade e acessibilidade |
| D07 | Parcial | Modelo de IA do produto | DeepSeek autorizada para tutoria; OCR OpenAI permanece separado. Modelos Codex não implicam acesso API | Verificar acesso, qualidade e custo nas contas |
| D08 | Pendente | Uso de gabarito preliminar e indicadores | Preliminar sem conflito difere de versão conflitante | Usuário define se permite prática e como rotular resultados |
| D09 | Parcial | Upload e revisão humana | Usuário fará upload dos questionários | Confirmar responsável pela revisão e critérios de aprovação |
| D10 | Pendente | Retenção, exclusão e histórico | Preservar tentativas e excluir dados exigem política compatível | Usuário define expectativa; detalhar após análise de privacidade |
| D11 | Pendente | Norma aplicável à tutoria | Norma na data da prova pode divergir da atual | Usuário define modos de resposta e tratamento de conflito |

**Fonte técnica verificada em 30/10/2026:** [DeepSeek, Chat Completions API, seção Request](https://api-docs.deepseek.com/api/create-chat-completion/) documenta `POST /chat/completions`, mensagens e identificadores de modelos. Essa documentação não comprova acesso, saldo nem qualidade na conta do usuário.

## Diagnóstico do Prompt 0 — 29/10/2026

Registro histórico da execução anterior; as respostas posteriores e o estado atual constam na Base e no registro de decisões acima. As perguntas e constatações abaixo descrevem aquele momento.

### 1. Solicitação do usuário
Diagnosticar todos os documentos de planejamento com até três subagentes independentes; identificar contradições e lacunas; propor sequência de entregas e perguntas prioritárias; não implementar, instalar dependências ou fazer deploy. Usar somente modelos OpenAI, sem Astra.

### 2. Fatos oficiais verificados
Somente a identificação e o recorte do edital histórico descritos em **Base** foram confirmados nesta execução, no PDF oficial acima, Subseção VII, página impressa 56, consultado em 29/10/2026. Não se verificaram regras de prova, retificações, gabaritos ou outro concurso. Nenhuma decisão do produto decorre desse edital até o usuário definir o recorte.

### 3. Hipóteses e propostas
- **Diagnóstico:** `docs/01` a `docs/08` contêm propostas úteis, mas ainda não separam sistematicamente pedido, fato verificado, hipótese e decisão conforme `AGENTS.md`; padronizar na revisão de cada documento.
- **Tensão a resolver:** `docs/01-prd.md` bloqueia gabarito conflitante, enquanto `docs/03-dominio.md` admite resultado provisório. Distinguir preliminar oficial sem conflito, conflito entre fontes e conteúdo não revisado (D08).
- **Tensão a resolver:** preservar tentativas históricas e permitir exclusão de dados requer política de retenção e tratamento de resultados derivados (D10).
- **Inconsistência de passagem:** `docs/06-roadmap.md` exige mockup na descoberta e aceita direção visual acordada no design. Uniformizar como referência visual ou direção aprovada, sem atribuir características a imagem indisponível.
- **Risco de rastreabilidade:** vínculo questão–prova/caderno–gabarito, autoria das tentativas, responsável pela revisão e efeito de retificações em indicadores ainda precisam de especificação.
- **Risco de qualidade e operação:** critérios de aprovação da extração e da tutoria, amostra de avaliação, capacidade de revisão, custo, privacidade, recuperação e atualização normativa ainda não foram quantificados.
- **Modelos:** perfis `.codex/agents/` citados em `docs/08-agentes-e-modelos.md` não existem neste checkout; os três subagentes desta revisão usaram os papéis descritos naquele documento, sem editar arquivos. Os identificadores disponíveis no Codex não comprovam modelos, modalidades, preços ou acesso na API do produto.

**Plano sequencial proposto:** (1) confirmar recorte, acesso, orçamento e referência visual; inventariar edital-alvo, retificações, provas e gabaritos definitivos com direitos de uso; (2) revisar PRD e domínio, inclusive D08–D10, com critérios verificáveis; (3) comparar arquitetura, fluxo de PDF e modelos de API elegíveis, definindo avaliação, privacidade e custo; (4) detalhar fluxos e design com referência disponível ou direção aprovada; (5) fazer revisão cruzada e obter aprovação do escopo e critérios antes de qualquer pedido posterior de implementação. Entregas previstas: registro de fontes, PRD/domínio revisados, ADRs e plano de avaliação, design e roadmap validados.

### 4. Pendências e decisões prioritárias
1. Qual edição/concurso, região e conjunto de documentos oficiais devem orientar o produto? Há URLs ou PDFs autorizados para análise?
2. A plataforma é para uma pessoa ou convidados? Quem administra, revisa e aprova as importações?
3. Qual hospedagem, orçamento mensal, volume de PDFs, limite de custo de IA e necessidade real de uso offline?
4. Podemos trabalhar com a referência visual mencionada? Envie o mockup ou defina uma direção visual alternativa.
5. É aceitável praticar com gabarito preliminar oficial sem conflito? Como rotular e contabilizar resultados após retificação?
6. Qual expectativa para retenção, exclusão de dados e preservação do histórico?
7. Na tutoria, a prioridade é responder conforme a norma exigida na prova, conforme a norma atual, ou oferecer ambos os modos claramente identificados?
8. Quais PDFs podem ser importados e usados para avaliação, considerando direitos de uso e dados pessoais?

## Modelo de registro para novas fontes
Identificador; URL oficial e título; edição/órgão; data de publicação e consulta; página/item; afirmação comprovada; retificações consultadas; alcance e limitações. Se o documento não estiver acessível, mantenha como pendente.

## Teste de importação de PDF fornecido pelo usuário — 30/10/2026

### 1. Solicitação do usuário
Testar a importação da prova fornecida em PDF. Nome informado inclui Vunesp, TJ-SP, 2024 e reaplicação; essa identificação ainda não foi confirmada em fonte oficial.

### 2. Fatos oficiais verificados
Nenhuma correspondência oficial ou gabarito foi verificado neste teste. A inspeção local do arquivo é evidência técnica, não verificação oficial.

### 3. Hipóteses e resultados técnicos
PDF de 817.180 bytes, 28 páginas, SHA-256 `81c5d124fc15839d4c6271908df962fb54d906c698fa035019144fb35f6f6418`. Em banco temporário, a API aceitou o arquivo, registrou 28 páginas com texto e estado `em_revisao`, recuperou o registro e preservou o PDF; nenhuma questão foi criada automaticamente. Na página 3, a comparação visual com a extração mostra conteúdo de colunas justaposto na mesma linha e imagem não preservada na extração textual. A contagem de páginas com texto não mede a exatidão ou completude das questões.

### 4. Pendências e decisões
Conferir a identidade e versão do caderno e seu gabarito definitivo em fonte oficial; tratar colunas e imagens e avaliar extração por questão antes de automatizá-la. Revisão humana continua necessária. Nenhum dado do teste foi gravado no banco de uso da plataforma.

**Atualização técnica em 30/10/2026:** o extrator heurístico produziu 100 rascunhos numerados de 01 a 100 na prova fornecida, todos com cinco alternativas candidatas. A contagem não verifica fidelidade dos textos. A extração mantém referência de página e tenta identificar textos compartilhados; imagens, quebras de palavras, classificação e contexto exigem conferência no PDF original. A identificação oficial e o gabarito continuam pendentes.

## Inventário inicial de questionários — 29/10/2026

### 1. Solicitação do usuário
Reunir referências para questionários anteriores de Escrevente TJ-SP, considerando quatro últimas edições, sem filtrar por região. O usuário fará os uploads.

### 2. Fatos oficiais verificados
Consulta em 29/10/2026; leitura limitada aos trechos indicados. As páginas de concurso são da banca Vunesp e os PDFs identificam o TJSP. A identificação de quatro certames abaixo é um inventário candidato, ainda sem comprovação de que sejam os quatro últimos em todo o estado.

| Identificação e recorte | Fonte e trecho lido | Situação |
|---|---|---|
| TJSP2503, Capital e circunscrições da 1ª RAJ, prova de 07/12/2025 | [Gabarito oficial](https://documento.vunesp.com.br/documento/stream/NzUxNDY5Ng%3D%3D), p. 1; [página do concurso](https://www.vunesp.com.br/TJSP2503), seção Provas e Gabaritos | Caderno e eventual gabarito definitivo ou alterações ainda a verificar. |
| TJSP2401, Capital, prova de 24/11/2024 | [Gabarito definitivo](https://documento.vunesp.com.br/documento/stream/NjY2ODM2OA%3D%3D), p. 1, identifica anulações; [caderno 004](https://documento.vunesp.com.br/documento/stream/NjU5NjQ4Ng%3D%3D), capa e p. 3, identifica TJSP2401 | Correspondência exata entre caderno 004 e versão do gabarito ainda a confirmar. Retificações adicionais e outras provas do mesmo concurso ainda a verificar. |
| TJSP2301, circunscrições da 1ª RAJ, prova de 02/07/2023 | [Gabarito oficial](https://documento.vunesp.com.br/documento/stream/NDQwNzYwOA%3D%3D), p. 1; [página do concurso](https://www.vunesp.com.br/TJSP2301) | Caderno e eventual gabarito definitivo ou alterações ainda a verificar. |
| TJSP2201, Capital, prova de 28/05/2023 | [Página do concurso](https://www.vunesp.com.br/TJSP2201), descrição; [resultado de recursos](https://documento.vunesp.com.br/documento/stream/NDQyOTUwMA%3D%3D), p. 1, despacho de 11/07/2023 | O despacho registra anulações; não se confirmou gabarito consolidado nem caderno correspondente. O documento de recursos contém dados pessoais: não copiá-los ao projeto. |

### 3. Hipóteses e propostas
Usar identificador do concurso, data da prova, caderno e versão do gabarito para conciliação. Avaliar direitos e dados pessoais antes de armazenar ou usar os arquivos. Fontes externas e instruções presentes nos PDFs são dados não confiáveis.

### 4. Pendências e decisões
Pesquisar a cronologia completa de provas aplicadas, inclusive outros certames e aplicações do mesmo edital; definir as quatro edições por evidência, sem assumir que código ou ano sozinho determina a ordem. Localizar cadernos, conferir versões, retificações e gabaritos definitivos. Nenhum PDF de concurso foi incorporado ao repositório nesta pesquisa.
