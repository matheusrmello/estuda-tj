# EstudaTJ — planejamento

Projeto privado de estudos para Escrevente Técnico Judiciário do TJ-SP. A versão local importa questões de PDFs, permite prática por matéria, simulados com tempo, acompanhamento básico e tutoria DeepSeek. A extração por IA é aproximada e pode conter erros. A associação automática de gabaritos continua pendente; veja `backend/README.md`.

## Executar localmente

Com Python 3 e `pdftotext` instalados, execute `python3 backend/server.py` na raiz e abra `http://127.0.0.1:8000/`. O servidor escuta somente no próprio computador e não possui autenticação: não o exponha à rede. Os dados ficam em `backend/data/`; detalhes e limitações estão em `backend/README.md`.

Para testar: `python3 -m unittest discover -s backend -v`.

## Executar com Docker

Construa a imagem na raiz do projeto:

```sh
docker build -t estudatj:local .
docker run -d --name estudatj -p 127.0.0.1:8001:8000 -v estudatj_data:/data estudatj:local
```

Abra `http://127.0.0.1:8001/`. O volume nomeado mantém os dados entre reinícios e é separado dos dados da execução fora do Docker. A aplicação ainda não tem autenticação; mantenha o endereço publicado em `127.0.0.1` e não exponha o contêiner à rede. A chave DeepSeek fica apenas na memória e precisa ser informada novamente após reiniciar. Para parar, use `docker stop estudatj`; para iniciar novamente, `docker start estudatj`.

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
