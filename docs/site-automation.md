# Automação do site

O repositório público `hendrixfreire/linkedin-job-scraper` é a origem atual do
LinkedIn Jobs Search e do agente de candidatura após a fusão. O site vive no
repositório privado `hendrixfreire/linkedin-job-toolkit-site`.

O workflow `.github/workflows/notify-toolkit-site.yml` envia somente metadados
do GitHub para o site:

- todo push em `main` solicita um deployment de produção;
- abertura, reabertura ou atualização de PR contra `main` solicita um preview;
- execuções mais antigas da mesma PR ou de produção são canceladas;
- código vindo da PR não é baixado nem executado pelo workflow privilegiado
  `pull_request_target`.

São alterações relevantes: código Python em `src/` ou na raiz, scripts,
documentação, arquivos de dependências/configuração pública, skills e a própria
automação. Testes, dados locais, relatórios, banco, configuração pessoal e
arquivos operacionais não disparam o site.

## Configuração necessária

Crie no repositório `linkedin-job-scraper`:

| Tipo | Nome | Escopo mínimo |
| --- | --- | --- |
| Secret | `SITE_DISPATCH_TOKEN` | Fine-grained PAT limitado ao repositório privado `linkedin-job-toolkit-site`, com `Contents: write` |

O `GITHUB_TOKEN` deste repositório não pode disparar um workflow em outro
repositório, por isso o token dedicado é necessário. Não reutilize um token
pessoal amplo.

O receptor precisa existir na branch padrão do site antes do primeiro evento:
`.github/workflows/deploy-source-event.yml`. A configuração Vercel e o token
usado para publicar previews ficam exclusivamente no repositório privado do
site.

## Falhas esperadas

- `SITE_DISPATCH_TOKEN is not configured`: o secret ainda não foi criado.
- resposta `404` do endpoint `dispatches`: o token não enxerga o repositório
  privado ou o nome do repositório está incorreto.
- o dispatch retorna sucesso, mas nada inicia: o workflow receptor ainda não
  existe na branch `main` do site.
