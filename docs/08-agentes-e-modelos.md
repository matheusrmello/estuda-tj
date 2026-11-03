# Agentes e modelos

## 1. Solicitação do usuário
Organizar revisões de planejamento com até três subagentes simultâneos, tarefas independentes, modelos OpenAI e exclusão de Astra.

## 2. Fatos oficiais verificados
Nenhum fato sobre edital-alvo ou sobre disponibilidade de modelos na API do produto foi verificado neste documento. As URLs ao final são referências de documentação a conferir por seção e data antes de sustentar decisões de configuração.

## 3. Hipóteses e propostas

Os papéis abaixo orientam o planejamento. A pasta `.codex/agents/` **não existe neste checkout em 29/10/2026**; portanto, não há perfis TOML a carregar nem limite configurado em arquivo. Os modelos `gpt-6.1-sol`, `gpt-6.1-terra` e `gpt-6-luna` aparecem como opções da ferramenta de colaboração nesta sessão, o que não confirma acesso em outra conta, instalação ou na API do produto. Se um modelo falhar, usar outro modelo OpenAI disponível, registrar a troca e nunca usar Astra.

| Papel | Modelo | Esforço | Resultado |
|---|---|---|---|
| Coordenador (seleção manual) | gpt-6.1-sol | high | Integração e decisão de planejamento |
| produto_dominio | gpt-6.1-sol | high | PRD, domínio e pendências |
| arquitetura_ia | gpt-6.1-sol | high | arquitetura, segurança, qualidade de IA |
| design | gpt-6.1-terra | high | sistema visual e fluxos |
| pesquisa | gpt-6-luna | medium | inventário de fontes e evidências |
| revisor | gpt-6.1-sol | high | inconsistências, lacunas e critérios |

Limite de trabalho solicitado: três subagentes simultâneos, excluído o coordenador. Não execute simultaneamente editores do mesmo arquivo; atribua arquivos ou peça relatórios ao coordenador. Atribuições são recomendações, não garantia de custo: preços de API e franquia do Codex são coisas diferentes.

## 4. Pendências e decisões
Decidir se os perfis TOML serão criados em etapa posterior de planejamento; conferir por seção e data as referências de configuração e do [catálogo de modelos da API](https://developers.openai.com/api/docs/models), além do acesso real da conta. Referências candidatas: [subagentes](https://learn.chatgpt.com/docs/agent-configuration/subagents) e [configuração](https://learn.chatgpt.com/docs/config-file/config-reference).

**Execução do Prompt 0 em 29/10/2026:** `produto_dominio` e `arquitetura_ia` usaram `gpt-6.1-sol` com esforço high; `design_fontes` usou `gpt-6.1-terra` com esforço high. Produziram relatórios independentes sem editar arquivos. O coordenador integrou as conclusões. Não houve substituição de modelo nesta execução.
