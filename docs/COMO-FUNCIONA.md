# Como funciona o Candidatura Agent

> Documento de orientação operacional. Última verificação: 14/07/2026.

## Resumo em uma frase

O sistema busca vagas no LinkedIn, grava tudo localmente, calcula aderência, prepara uma fila e mostra o estado num dashboard; o preenchimento real ainda está em `dry_run` e o envio automático permanece desligado.

## Onde cada coisa está

### 1. Projeto principal

```text
/Users/hendrixfreire/Projetos/candidatura-agent/
```

| Caminho | Função |
|---|---|
| `README.md` | Visão resumida do projeto |
| `docs/COMO-FUNCIONA.md` | Este mapa operacional |
| `docs/arquitetura.html` | Diagrama visual do fluxo |
| `config.json` | Chaves operacionais: meta mínima, ATS permitidos, Discord e flags de navegador/envio |
| `src/candidatura_agent/` | Código Python do sistema |
| `tests/` | Testes automatizados |
| `scripts/` | Comandos de execução |
| `data/` | Dados locais e privados; não entram no Git |
| `reports/` | Relatórios e capturas; não entram no Git |

### 2. Descoberta de vagas integrada

```text
/Users/hendrixfreire/Projetos/candidatura-agent/src/candidatura_agent/linkedin.py
/Users/hendrixfreire/Projetos/candidatura-agent/data/linkedin_jobs_new.json
```

- `linkedin.py`: consulta vagas no LinkedIn, filtra e deduplica contra o SQLite.
- `linkedin_jobs_new.json`: artefato local de compatibilidade para ingestão e relatório.

Wrapper do cron horário:

```text
/Users/hendrixfreire/.hermes/scripts/candidatura-hourly.sh
```

Ele chama apenas `scripts/run_hourly.sh`; descoberta e candidatura agora vivem no mesmo projeto.

### 3. Dados privados e estado

```text
/Users/hendrixfreire/Projetos/candidatura-agent/data/
```

| Arquivo/pasta | Conteúdo |
|---|---|
| `candidaturas.db` | SQLite: vagas, avaliações, candidaturas, eventos, feedback e respostas |
| `profile.json` | Perfil factual e respostas aprovadas para formulários |
| `run_control.json` | Resultado resumido da última execução horária |
| `browser-profile-brave/`, `browser-profile-chrome/`, `browser-profile-chromium/` | Sessões persistentes separadas por navegador; apenas perfis efetivamente usados são criados |

Esses itens estão no `.gitignore`. Código vai para Git; dados pessoais, sessões e histórico operacional ficam apenas na máquina.

### 4. CVs personalizados

Fonte factual única:

```text
/Users/hendrixfreire/Documents/CVs/cv_estruturado.md
```

Saída por empresa:

```text
/Users/hendrixfreire/Documents/CVs/<Empresa>/
```

Exemplo validado:

```text
/Users/hendrixfreire/Documents/CVs/Wellhub/cv-hendrix-freire-wellhub-senior-marketing-analytics-engineer.pdf
```

### 5. Relatórios e evidências

```text
/Users/hendrixfreire/Projetos/candidatura-agent/reports/
```

- `candidaturas-AAAA-MM-DD.md`: relatório diário.
- `screenshots/<vaga>/`: evidência visual das simulações.

### 6. Dashboard persistente

URL:

```text
http://127.0.0.1:8765
```

Código:

```text
src/candidatura_agent/dashboard.py
scripts/run_dashboard.sh
```

Serviço do macOS:

```text
/Users/hendrixfreire/Library/LaunchAgents/com.hendrix.candidatura-agent.plist
```

Logs:

```text
/tmp/candidatura-dashboard.out
/tmp/candidatura-dashboard.err
```

O `launchd` inicia o dashboard no login e o mantém vivo.

## Como as informações fluem

```text
Hermes Cron
   ↓
linkedin.py
   ↓
data/linkedin_jobs_new.json
   ↓
hourly.py → ingest.py → policy.py
   ↓
data/candidaturas.db
   ├──→ dashboard.py → http://127.0.0.1:8765
   ├──→ daily_report.py → reports/candidaturas-AAAA-MM-DD.md
   └──→ fila qualificada
            ↓
       CV personalizado por vaga
            ↓
       browser.py + Playwright + adaptador do ATS
            ↓
       dry_run / blocked / submitted
            ↓
       volta ao SQLite e ao relatório
```

## O que cada módulo faz

| Módulo | Responsabilidade |
|---|---|
| `ingest.py` | Lê o JSON do scraper e evita duplicatas |
| `linkedin.py` | Busca, filtra, deduplica e enriquece vagas do LinkedIn |
| `policy.py` | Calcula aderência e aplica filtros duros |
| `db.py` | Mantém o SQLite e a trilha de auditoria |
| `adapters.py` | Reconhece ATS e classifica campos do formulário |
| `browser.py` | Preenche formulários com Playwright e bloqueia perguntas inseguras |
| `hourly.py` | Orquestra ingestão, score, fila e navegador opcional |
| `dashboard.py` | Exibe estado e recebe feedback |
| `report.py` | Monta o texto do relatório diário |
| `daily_report.py` | Executa e salva o relatório |

## Automações ativas

| Automação | Agenda | Entrega | Estado verificado |
|---|---:|---|---|
| `linkedin-job-search` | 08:00, 13:00 e 18:00 | Telegram Home | Ativa |
| `candidatura-hourly` | de hora em hora, 08:30–18:30 | Local | Ativa |
| `candidatura-asset-prep` | de hora em hora, 08:45–18:45 | Local | Ativa |
| `candidatura-daily-report` | 20:15 | Esta conversa | Ativa |
| Dashboard via `launchd` | contínuo | localhost:8765 | Rodando |


A coleta é uma só e pertence ao Candidatura Agent. O cron de relatório e o ciclo horário usam o mesmo módulo e o mesmo SQLite.

## O que já é automático

- busca e deduplicação de vagas;
- ingestão no SQLite;
- score e filtros;
- fila de qualificadas;
- enriquecimento das descrições do LinkedIn;
- resolução conservadora de URL oficial/ATS, com cooldown quando não há evidência;
- geração e validação de um CV específico por execução horária;
- dashboard e relatório diário;
- navegador Brave em `dry_run`, com Chrome como fallback;
- lock contra execuções horárias concorrentes;
- evidência visual antes do envio e, quando o envio for liberado, depois do clique;
- meta mínima de dez candidaturas por dia, sem teto diário;
- processamento de zero, uma ou várias vagas prontas em cada execução horária;
- notificação individual no Discord após cada envio confirmado;
- bloqueio de CAPTCHA, login, 2FA, ATS não autorizado e perguntas desconhecidas;
- reutilização de respostas já aprovadas.

## O que ainda NÃO é automático

- resolver automaticamente URLs que não aparecem em página oficial ou ATS indexado; esses casos entram na fila do resolvedor assistido;
- responder perguntas legais, sensíveis ou factuais ainda não aprovadas;
- superar login expirado, CAPTCHA ou 2FA sem participação humana;
- enviar candidatura: `auto_submit` permanece desligado;
- ampliar envio real além de Greenhouse, Ashby e Factorial; os demais ATS aceitos continuam restritos a `dry_run`.

Configuração de segurança atual:

```json
{
  "daily_target_min": 10,
  "browser_enabled": true,
  "auto_submit": false,
  "allowed_ats": ["greenhouse", "ashby", "factorial"],
  "dry_run_allowed_ats": ["greenhouse", "lever", "ashby", "gupy", "peopleforce", "factorial", "workday", "smartrecruiters", "solides", "recruitee", "workable", "teamtailor", "bamboohr", "inhire", "quickin", "abler", "kenoby", "pandape", "compleo"],
  "notification_target": "discord:1526233025346666617:1526233025346666617"
}
```

Dez é uma meta mínima, não um máximo. Com o navegador habilitado, cada ciclo pode processar todas as vagas prontas e qualificadas encontradas; isso pode produzir mais de uma candidatura por hora e mais de dez no dia. O envio real continua bloqueado por `auto_submit=false`.

A notificação usa a outbox `notifications` no SQLite. Um envio confirmado cria uma única entrada. `hermes send` entrega a mensagem no Discord e somente depois marca a entrada como entregue; falhas permanecem pendentes para retry na próxima execução.

Formato padrão:

```text
CANDIDATURA ENVIADA

Cargo: <cargo>
Empresa: <empresa>
Local: <local>
Aderência: <score>/100
Destaques: <motivos resumidos>
ATS: <plataforma>
Enviada em: <data/hora>

Resumo: <descrição curta>

Link da vaga: <URL externa>
Origem: <URL do LinkedIn, quando diferente>
```

Portanto, o cron horário já prepara ativos e executa simulações seguras; candidaturas reais continuam bloqueadas porque `auto_submit=false`, mesmo com Greenhouse, Ashby e Factorial na allowlist de envio.

## Estado verificado em 14/07/2026

```text
99 vagas no banco
74 rejeitadas
20 qualificadas aguardando preparação
2 dry-runs concluídos
2 submissões controladas já registradas
40 testes passando
Dashboard HTTP 200
```

## Comandos para não se perder

```bash
cd ~/Projetos/candidatura-agent

# Resumo operacional sem exibir dados pessoais
./scripts/status.sh

# Abrir dashboard
open http://127.0.0.1:8765

# Rodar testes
.venv/bin/python -m pytest -q

# Executar apenas ingestão/classificação
./scripts/run_hourly.sh

# Gerar relatório
./scripts/run_report.sh

# Abrir o mapa visual
open docs/arquitetura.html
```

## Regra de segurança

`dry_run` pode preencher e anexar arquivos, mas não envia. `auto_submit` só deve ser habilitado depois de cinco simulações reais aprovadas e somente para ATS liberados. CAPTCHA, login, 2FA, pergunta nova ou inconsistência factual bloqueiam apenas aquela vaga.
