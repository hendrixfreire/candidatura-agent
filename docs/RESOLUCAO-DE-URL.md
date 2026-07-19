# Resolução de URL de candidatura

> Última validação: 18/07/2026.

## Objetivo

Transformar uma vaga qualificada do LinkedIn em uma URL oficial, verificável e utilizável pelo pipeline. A URL do LinkedIn é apenas a origem; nunca é tratada como destino de candidatura.

## Ordem de resolução

1. **Página oficial/ATS indexado** — buscar combinações exatas de cargo, empresa e localização; abrir a candidata e validar empresa, cargo, estado da vaga e local.
2. **Página de carreira da empresa** — procurar a vaga no board oficial quando a busca genérica não retornar um ATS diretamente.
3. **Brave autenticado no LinkedIn** — fallback obrigatório. Abrir a `source_url` em nova guia, clicar somente em `Apply/Aplicar` e registrar a URL externa final.

O fallback do Brave existe porque a página pública do LinkedIn frequentemente não expõe o destino externo do botão. O navegador usa a sessão já autenticada do usuário; ele não lê cookies, não usa senhas e não envia candidaturas.

## Limites de segurança

Na etapa de resolução o agente pode:

- abrir a vaga de origem;
- clicar em `Apply/Aplicar` para seguir o redirecionamento;
- capturar e validar a URL final;
- persistir uma URL de ATS reconhecido.

Ele não pode:

- preencher campos;
- anexar CV;
- responder perguntas;
- aceitar termos;
- clicar em `Submit/Enviar`;
- usar, copiar ou expor credenciais/cookies.

## Persistência e estados

A fila de ativos tem duas etapas independentes:

| Etapa | Critério | Próxima ação |
|---|---|---|
| `resolve` | vaga qualificada sem `apply_url` | resolver URL e ATS |
| `resume` | URL/ATS validado, sem CV específico | preparar e validar CV |

Separar as etapas evita que URLs pendentes bloqueiem a preparação de CV de vagas já resolvidas.

Quando não há evidência suficiente, o agente registra `fail-resolution` com cooldown de 24 horas. Quando encontra uma página oficial em ATS ainda não suportado, registra o fato e usa cooldown de 72 horas: não inventa URL nem finge que a vaga pode ser automatizada.

## Operação

- **Resolver público:** cron `candidatura-url-resolver`, até três vagas por execução.
- **Fallback visual:** o mesmo cron tem `computer_use` liberado e usa o Brave autenticado somente depois de falharem as rotas públicas.
- **Preparação de CV:** cron `candidatura-asset-prep`, somente para a etapa `resume`.
- **Validação:** `asset_cli queue --stage resolve` e `asset_cli queue --stage resume` mostram cada fila sem misturá-las.

## Evidência de validação

- O fallback visual foi incorporado ao prompt operacional do cron.
- `45` testes automatizados passaram após a alteração.
- A suíte deve ser executada antes de alterar adaptadores ou permitir autoenvio em um novo ATS.
