# PRD inicial — proposta para validação

## 1. Solicitação do usuário
Planejar plataforma de estudo para Escrevente TJ-SP com acesso individual, hospedagem no homelab, upload de questionários pelo usuário e suporte a PDFs de concursos, além de questões, simulados, tutoria IA e desempenho. O recorte solicitado abrange as quatro últimas edições, ainda a identificar.

## 2. Fatos oficiais verificados
Nenhuma regra do edital-alvo foi verificada para este PRD. A fonte histórica limitada, com URL, edição, página e consulta, está em `00-fontes-e-decisoes.md` e não define requisitos do concurso escolhido.

## 3. Hipóteses e propostas

## Problema e objetivo
O estudante precisa organizar fontes confiáveis, praticar e identificar lacunas de estudo em um ambiente privado. Objetivo proposto: reduzir o trabalho manual de organizar questões e orientar a revisão com evidência rastreável. O acesso individual foi definido (D01).

## Jornadas e critérios de aceitação propostos
1. **Importação:** selecionar prova e gabarito autorizados; visualizar extração por página e eventuais falhas; revisar correspondência questão/gabarito; publicar apenas itens revisados com origem e versão. PDF ilegível ou gabarito conflitante deve ficar pendente, não virar resposta oficial presumida.
2. **Questões:** filtrar por disciplina, assunto, origem e estado de revisão; responder, ver resultado e referência do gabarito; registrar tentativas sem alterar a fonte original.
3. **Simulados:** configurar seleção, duração e regras; iniciar, retomar ou concluir; ver acertos, erros e não respondidas. Regra de pontuação específica de edital só quando verificada.
4. **Tutoria:** solicitar explicação de alternativa, receber resposta com referências e limites; sinalizar erro e reconhecer quando não há evidência suficiente. Uma resposta de IA não modifica gabarito oficial.
5. **Desempenho:** exibir tentativas, acertos e evolução por assunto e período com amostra e filtros; distinguir falta de dados de desempenho zero.

## Prioridade proposta
MVP: acesso privado, importação revisável, prática de questões, simulado básico e indicadores; tutoria limitada e fundamentada se passar avaliação. Ordem e inclusão final dependem de custos e decisão do usuário. Fora do MVP proposto: comunidade pública, pagamentos, ranking e promessas de aprovação.

## Medidas propostas
Taxa de itens importados aceitos após revisão; taxa de divergências identificadas; sessões de estudo concluídas; custo por explicação útil. Definições, metas, amostras e privacidade devem ser aprovadas antes de medir.

## Requisitos transversais
Acessibilidade, responsividade, isolamento de acesso, backup e recuperação, rastreabilidade, exclusão de dados e controle de custos. Definir metas quantitativas com o usuário. Direitos das provas, dados pessoais e disponibilidade de fontes precisam de análise antes de uso.

## 4. Pendências e decisões
Confirmar público, recorte do concurso, direitos dos PDFs, prioridade do MVP, responsável pela revisão e orçamento. Decidir D08 (uso de gabarito preliminar) e D10 (retenção e exclusão) no registro central.
