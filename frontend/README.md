# Interface EstudaTJ

Interface sem bibliotecas externas. O servidor deve disponibilizar `index.html`, `style.css` e `app.js` na mesma origem da API. É necessário JavaScript habilitado. Ela não inclui dados fictícios; os indicadores derivam das respostas registradas.

## Contrato da API

- `GET /api/documents`: array com `id`, `filename` e `status`.
- `POST /api/documents`: corpo PDF binário, `Content-Type: application/pdf` e `X-Filename` codificado para URL; retorna documento com `id`. A caixa de OCR fica desmarcada por padrão; quando marcada, envia `X-Enable-OCR: true`. O processamento exige configuração do servidor e envia imagens das páginas digitalizadas sem texto à OpenAI, com possível custo.
- `GET /api/documents/{id}`: documento com `filename` e `pages`, array de `{page, text, extraction_method, ocr_status}`; a numeração de página começa em 1. A interface identifica páginas processadas por OCR e informa falhas, ausência de idioma ou limites. Documentos anteriores sem esses metadados têm origem indicada como não registrada.
- `POST /api/documents/{id}/ocr`: botão voluntário solicita processamento de até 10 páginas pendentes com `{ "confirm": true }`; a interface informa previamente que imagens serão enviadas à OpenAI e que pode haver custos.
- `GET /api/documents/{id}/pdf`: PDF original para conferência de página, imagens e textos de apoio.
- `GET /api/documents/{id}/drafts`: sugestões de questões, com página, matéria, enunciado, contexto, alternativas, alertas e estado.
- `POST /api/drafts/{id}/publish`: revisão explícita da sugestão, com campos corrigidos, página e gabarito opcional.
- `GET /api/questions`: array de questões revisadas com `id`, `subject`, `prompt`, `options` e `answer_source`.
- `POST /api/questions`: cadastro manual com `document_id`, `page`, `number`, `subject`, `prompt`, `context`, `options`, `answer` (índice iniciado em zero ou nulo) e `answer_source`; o envio representa revisão humana.
- `GET /api/attempts`: array de tentativas com `correct`.
- `POST /api/attempts`: JSON com `question_id` e `selected` (índice iniciado em zero); retorna `correct`, `answer` e `answer_source`. Sem gabarito, registra a tentativa sem classificá-la.
- `GET /api/settings`: provedor da tutoria, modelo, estado de configuração da chave e meta diária; não retorna a chave.
- `POST /api/settings`: atualiza provedor, modelo e meta, e opcionalmente a chave da DeepSeek em memória. Campo de chave vazio mantém a chave da sessão; reiniciar o processo a apaga. A caixa de remoção solicita sua exclusão explícita.
- `POST /api/tutor`: envia `question_id` e pergunta opcional. Apenas a ação explícita do usuário envia a questão e sua pergunta à DeepSeek; a resposta é apresentada como sugestão sujeita a conferência e pode gerar custos.

Respostas são JSON; erros incluem `error`. A interface identifica o gabarito como informado pelo usuário e não apresenta a extração como conteúdo oficial. O texto extraído, inclusive por OCR, serve de apoio e pode estar incompleto. Não há autenticação ou avaliação automática de direitos nesta interface; essas responsabilidades dependem do servidor e do ambiente de implantação.
