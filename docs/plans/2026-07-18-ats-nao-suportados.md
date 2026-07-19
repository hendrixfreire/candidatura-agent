# ATS não suportados — Implementation Plan

> **For Hermes:** implementar por etapas com TDD e sem liberar autoenvio de uma plataforma antes da validação em `dry_run`.

**Goal:** transformar URLs oficiais hoje bloqueadas por ATS desconhecido em candidaturas automatizáveis, preservando a regra de que nenhuma resposta ou envio ocorre sem validação.

**Architecture:** separar descoberta de URL, identificação de plataforma e execução de formulário. Toda URL oficial deve ser persistida mesmo quando não tiver adaptador; um registro de capacidade do ATS decide entre `discovered`, `manual`, `dry_run` e `auto_submit`. Adaptadores implementam uma interface pequena, são testados com fixtures locais e só mudam de estágio após evidência real.

**Tech Stack:** Python, SQLite, Playwright, pytest, Hermes cron e `computer_use` apenas para descoberta visual de URL.

---

## Evidência que motivou o plano

Na execução de 18/07/2026 o resolvedor identificou vagas oficiais que não avançaram porque os formulários pertenciam a:

- Quickin;
- formulário proprietário do empregador.

O problema deixou de ser descoberta de URL. Agora é falta de classificação persistida e de adaptadores testados para plataformas fora da allowlist.

## Princípios

1. **URL oficial não é descartável.** Encontrar uma URL válida deve gerar evidência persistida, mesmo que o ATS ainda não seja automatizável.
2. **Um ATS por vez.** Priorizar por quantidade de vagas qualificadas, aderência média, estabilidade do HTML e custo de manutenção.
3. **Dry run antes de envio.** Um adaptador novo nunca entra direto em `auto_submit`.
4. **Pergunta desconhecida bloqueia a vaga, não o ATS.** Não inferir dados legais, salariais, de elegibilidade ou autodeclaração.
5. **Sem seletor mágico genérico.** O adaptador pode compartilhar primitives de campo, mas deve possuir reconhecimento e verificações próprias.

## Fase 0 — Inventário auditável

### Task 1: Persistir URL oficial ainda sem suporte

**Objective:** impedir que URL de ATS desconhecido seja transformada apenas em erro temporário.

**Files:**
- Modify: `src/candidatura_agent/db.py`
- Modify: `src/candidatura_agent/asset_cli.py`
- Test: `tests/test_ingest_db.py`

**Step 1: Write failing test**

Criar vaga qualificada e registrar URL oficial com `ats="unknown"`, `automation_mode="discovered"` e fonte de evidência. Confirmar que a fila de CV não a consome e que a fila de triagem de ATS a mostra.

**Step 2: Run test to verify failure**

```bash
.venv/bin/python -m pytest tests/test_ingest_db.py -q
```

Expected: FAIL — colunas/método de persistência inexistentes.

**Step 3: Write minimal implementation**

Adicionar campos de URL oficial, plataforma detectada, modo de automação, evidência e data de verificação. Criar consulta `unsupported_ats_queue()` ordenada por `fit_score`.

**Step 4: Run test to verify pass**

```bash
.venv/bin/python -m pytest tests/test_ingest_db.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/candidatura_agent/db.py src/candidatura_agent/asset_cli.py tests/test_ingest_db.py
git commit -m "feat: persist official URLs for unsupported ATS"
```

### Task 2: Exibir backlog e métricas de prioridade

**Objective:** tornar explícito quais ATS merecem implementação primeiro.

**Files:**
- Modify: `src/candidatura_agent/dashboard.py`
- Modify: `src/candidatura_agent/db.py`
- Test: `tests/test_dashboard.py` (create if absent)

**Step 1: Write failing test**

Validar agregação por `ats_detected`: vagas, empresas, média/máximo de aderência e última evidência.

**Step 2: Run test to verify failure**

```bash
.venv/bin/python -m pytest tests/test_dashboard.py -q
```

Expected: FAIL.

**Step 3: Write minimal implementation**

Adicionar bloco “ATS pendentes” no dashboard e endpoint JSON correspondente. Mostrar somente metadados da vaga, nunca perfil, respostas ou sessão.

**Step 4: Run test to verify pass**

```bash
.venv/bin/python -m pytest tests/test_dashboard.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/candidatura_agent/dashboard.py src/candidatura_agent/db.py tests/test_dashboard.py
git commit -m "feat: expose unsupported ATS backlog"
```

## Fase 1 — Classificação e contrato de adaptador

### Task 3: Formalizar capacidade por ATS

**Objective:** separar reconhecimento, simulação e envio real.

**Files:**
- Modify: `src/candidatura_agent/adapters.py`
- Modify: `config.json`
- Test: `tests/test_adapters.py`

**Step 1: Write failing test**

Cobrir `detect_ats(url)` e `capability_for(ats)`, incluindo `quickin`, `unknown` e plataformas já conhecidas.

**Step 2: Run test to verify failure**

```bash
.venv/bin/python -m pytest tests/test_adapters.py -q
```

Expected: FAIL.

**Step 3: Write minimal implementation**

Definir modos `discovered`, `manual`, `dry_run` e `auto_submit`. O padrão para qualquer domínio novo é `discovered`; somente configuração explícita promove estágio.

**Step 4: Run test to verify pass**

```bash
.venv/bin/python -m pytest tests/test_adapters.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/candidatura_agent/adapters.py config.json tests/test_adapters.py
git commit -m "feat: add staged ATS capabilities"
```

### Task 4: Criar corpus de fixtures por plataforma

**Objective:** permitir desenvolvimento sem depender de páginas ao vivo.

**Files:**
- Create: `tests/fixtures/ats/quickin/`
- Create: `tests/fixtures/ats/proprietary/`
- Modify: `tests/test_adapters.py`

**Step 1: Capture fixtures sanitizadas**

Salvar HTML de páginas públicas ou de `dry_run`, removendo nomes, e-mails, IDs de sessão, tokens, CVs e respostas. Não versionar perfis do navegador nem dados de `data/`.

**Step 2: Write failing test**

Para cada fixture, validar reconhecimento de formulário, campos obrigatórios e botão de avanço/envio.

**Step 3: Run test**

```bash
.venv/bin/python -m pytest tests/test_adapters.py -q
```

Expected: FAIL até o adaptador existir.

**Step 4: Commit fixtures sanitizadas**

```bash
git add tests/fixtures/ats tests/test_adapters.py
git commit -m "test: add sanitized ATS fixtures"
```

## Fase 2 — Primeiro adaptador: Quickin

### Task 5: Implementar o adaptador Quickin em `dry_run`

**Objective:** tornar a plataforma com evidência atual a primeira candidata de teste controlado.

**Files:**
- Create: `src/candidatura_agent/adapters/quickin.py` ou módulo equivalente no layout existente
- Modify: `src/candidatura_agent/adapters.py`
- Modify: `src/candidatura_agent/browser.py`
- Test: `tests/test_quickin_adapter.py`

**Step 1: Write failing tests**

Cobrir: detecção de domínio, preenchimento de nome/e-mail/telefone, upload de CV, seleção de combobox React, bloqueio de pergunta desconhecida e ausência de clique final de envio.

**Step 2: Run test to verify failure**

```bash
.venv/bin/python -m pytest tests/test_quickin_adapter.py -q
```

Expected: FAIL.

**Step 3: Implement minimal adapter**

Usar apenas primitives já validadas de `browser.py`. O adaptador deve retornar campos preenchidos, bloqueios e evidência visual. `auto_submit` permanece proibido para `quickin` nesta fase.

**Step 4: Run focused and full suite**

```bash
.venv/bin/python -m pytest tests/test_quickin_adapter.py -q
.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 5: Validate real dry runs**

Executar três vagas distintas, sem envio. Revisar screenshot, campos obrigatórios, CV anexado e blockers. Se qualquer resposta desconhecida surgir, registrar o campo e manter bloqueado.

**Step 6: Commit**

```bash
git add src/candidatura_agent/adapters.py src/candidatura_agent/browser.py src/candidatura_agent/adapters tests/test_quickin_adapter.py
git commit -m "feat: add Quickin dry-run adapter"
```

### Task 6: Promover Quickin somente após evidência

**Objective:** liberar envio apenas se o adaptador provou consistência.

**Acceptance criteria:**

- três `dry_run` reais sem erro material;
- testes verdes;
- nenhum CAPTCHA/login/2FA não tratado;
- campos bloqueantes preservados;
- autorização explícita do usuário para incluir Quickin em `allowed_ats`.

**Files:**
- Modify: `config.json`
- Modify: `docs/COMO-FUNCIONA.md`
- Test: suíte completa.

**Step 1: Change allowlist only after acceptance**

```json
{ "allowed_ats": ["greenhouse", "quickin"] }
```

**Step 2: Verify**

```bash
.venv/bin/python -m pytest -q
./scripts/run_hourly.sh
```

Expected: processamento idempotente, sem submissão duplicada.

**Step 3: Commit**

```bash
git add config.json docs/COMO-FUNCIONA.md
git commit -m "feat: enable validated Quickin submissions"
```

## Fase 3 — ATS proprietário

### Task 7: Decidir por família, não por empresa

**Objective:** evitar criar um adaptador descartável para cada site proprietário.

Para cada URL proprietária, registrar assinatura estrutural: domínio, motor do formulário, campos, upload, autenticação, CAPTCHA e fluxo de envio. Só criar adaptador se houver pelo menos duas vagas/empresas com a mesma família ou valor recorrente comprovado. Caso contrário, manter `manual` com URL oficial e CV pronto.

**Verification:** relatório mensal com volume, fit médio, taxa de bloqueio e manutenção por família.

## Ordem de execução sugerida

1. Fase 0 inteira: dados e priorização antes de automação.
2. Fase 1 inteira: contrato e fixtures.
3. Quickin em `dry_run` (Fase 2), pois já apareceu no backlog atual.
4. Repriorizar com dados reais.
5. Só então avaliar plataformas proprietárias por família.

## Critério de sucesso

Uma URL oficial de ATS desconhecido deixa de desaparecer em cooldown: fica rastreável, priorizada e pronta para evoluir de `discovered` → `dry_run` → `auto_submit` com evidência verificável.
