# Arquitetura inicial — opções, não implementação

## 1. Solicitação do usuário
Construir uma plataforma de acesso individual, hospedada no homelab do usuário, com upload de PDFs de concursos, prática, simulados, tutoria IA e desempenho. O usuário autorizou implementação e, posteriormente, DeepSeek além de OpenAI; Astra permanece proibida.

## 2. Fatos oficiais verificados
Nenhuma regra técnica do edital-alvo, condição de hospedagem ou capacidade de serviço foi verificada para este documento. A única fonte histórica limitada está em `00-fontes-e-decisoes.md`.

## 3. Hipóteses e propostas

## Limites e componentes propostos
Interface de estudo e revisão → API de aplicação → armazenamento de usuários, questões e tentativas; documentos em armazenamento privado. O processamento extrai PDF, apresenta sugestões para revisão e vincula gabarito; a tutoria pode chamar DeepSeek após solicitação do usuário, enquanto o OCR existente usa OpenAI mediante ativação específica. Revisão humana é fronteira antes de publicação. A hospedagem será no homelab; equipamentos, acesso e operação ainda não foram especificados.

## Decisões a comparar
- Cliente: React/TypeScript e possível PWA versus aplicação web mais simples; avaliar experiência, manutenção e real necessidade offline. Offline de dados sensíveis requer política de dispositivo.
- Servidor: Go, citado anteriormente, versus alternativa familiar à equipe; avaliar bibliotecas PDF, operação e custo de manutenção. Não presumir escolha.
- Persistência relacional proposta para relações e auditoria; armazenamento de objetos privado para PDFs. Busca textual ou vetorial é opção sujeita a avaliação; embeddings também devem ser OpenAI se usados.
- Processamento: primeiro extração textual determinística; OCR/visão para páginas escaneadas como proposta a avaliar por qualidade, custo e privacidade. Não assumir acerto de extração ou disposição das alternativas.

## Fronteiras e falhas
Validar tamanho/tipo de arquivo, isolar processamento, não executar conteúdo embutido, limitar acesso por usuário e por documento, registrar origem e operação. Upload duplicado usa identificação de conteúdo; reprocessamento cria nova versão sem sobrescrever versões aprovadas. Emparelhamento ambíguo, alternativas faltantes, gabarito ausente ou conflito de versão bloqueiam publicação e vão à fila de revisão. Prever falha de processamento, retomada idempotente, retenção e exclusão de arquivos, logs sem dados sensíveis e restauração de backup testada.

## IA e segurança
Texto de PDF é entrada não confiável, não instrução. Somente servidor futuro deve acessar credenciais, guardadas em serviço de segredos; nunca no repositório ou cliente. Planejar autenticação, autorização por objeto, criptografia, retenção, auditoria e minimização de dados. Investigar tratamento de dados e condições do provedor antes de integrar. Definir orçamento, cotas, limites e comportamento quando excedidos.

## Decisões abertas
D01–D11 em `00-fontes-e-decisoes.md`; definir ainda volume de PDFs, orçamento mensal, tolerância a falhas, conectividade, exigências de acessibilidade e regime de backups. Elaborar ADRs com contexto, alternativas, decisão e consequências depois de validação.

## 4. Pendências e decisões
Confirmar acesso e hospedagem, volume e direitos dos PDFs, orçamento, responsável pela revisão, política de dados e necessidade offline. D01–D11 estão no registro central; nenhuma stack foi aprovada.
