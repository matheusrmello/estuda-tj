# EstudaTJ — planejamento

Projeto privado de estudos para Escrevente Técnico Judiciário do TJ-SP. A versão local identifica candidatos a questões em PDFs, para revisão e publicação, permite cadastro manual, prática por matéria e acompanhamento básico. Páginas digitalizadas podem passar por OCR com a API OpenAI, mediante configuração e escolha explícita no envio; veja `backend/README.md`. A extração é heurística; simulados e tutoria IA ainda não foram implementados.

## Executar localmente

Com Python 3 e `pdftotext` instalados, execute `python3 backend/server.py` na raiz e abra `http://127.0.0.1:8000/`. O servidor escuta somente no próprio computador e não possui autenticação: não o exponha à rede. Os dados ficam em `backend/data/`; detalhes e limitações estão em `backend/README.md`.

Para testar: `python3 -m unittest discover -s backend -v`.

## Comece aqui
1. Abra a pasta `EstudaTJ` como projeto no Codex e confira se a pasta `.codex` foi incluída (é oculta em alguns sistemas). Confie no projeto apenas após revisar seus arquivos.
2. Leia `AGENTS.md`, `docs/00-fontes-e-decisoes.md` e `prompts/00-inicio.md`. Cole o prompt inicial no chat do Codex. Os demais prompts são sequenciais e podem ser executados separadamente.
3. Identifique as quatro últimas edições e adicione edital, retificações, provas e gabaritos oficiais de interesse quando disponíveis. A referência visual fornecida está em `docs/referencias/mockup-plataforma.png`. Não inclua dados pessoais reais nem arquivos sem autorização de uso no repositório.
4. A implementação inicial foi autorizada em 30/10/2026. Revise as decisões e pendências em `docs/00-fontes-e-decisoes.md` antes dos próximos incrementos.

## Arquivos
- `docs/`: fontes, produto, arquitetura, domínio, qualidade de IA, design system e roadmap.
- `prompts/`: comandos prontos para cada etapa e revisão final.
- `docs/08-agentes-e-modelos.md`: papéis de revisão e orientação sobre modelos. A pasta `.codex/agents/` citada no planejamento não está presente neste checkout; sua configuração permanece pendente.

Se for copiar o bootstrap, copie toda esta pasta, inclusive `.codex`. Para criar histórico Git em outra máquina, execute `git init` dentro dela e faça o primeiro commit conforme sua preferência. Nenhum repositório remoto é necessário.
