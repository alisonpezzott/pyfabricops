# CLAUDE.md - Contexto do Projeto PyFabricOps

## Sobre o Repositorio

**PyFabricOps** (v0.5.4) e uma biblioteca Python wrapper para as APIs REST do Microsoft Fabric, Power BI e Microsoft Graph. Autor: Alison Pezzott.

- **Linguagem**: Python 3.10-3.14
- **Gerenciador de pacotes**: uv
- **Linting/Formatting**: ruff (line-length 79, rules E/F/I/B/UP)
- **Testes**: pytest com doctests (`uv run pytest`)
- **Docs**: mkdocs-material em https://pyfabricops.readthedocs.io

## Estrutura do Codigo-Fonte

```
src/pyfabricops/
├── api/           # HTTP requests, autenticacao (env/oauth/fabric), token cache
├── core/          # Workspaces, git, connections, deployment pipelines, gateways, etc.
├── items/         # CRUD de objetos Fabric (notebooks, semantic models, reports, etc.)
├── helpers/       # Funcoes alto nivel: export, deploy, parametrizacao por tipo
├── cd/            # Geracao de arquivos de suporte CI/CD
├── dmv/           # Consultas DMV via XMLA
├── graph/         # Resolucao de identidades via Microsoft Graph
└── utils/         # Logging, decorators (@df), exceptions, utilitarios
```

## Comandos Uteis

```bash
uv sync --group dev         # Instalar com dependencias dev
uv run pytest               # Rodar testes
uv run ruff format .        # Formatar
uv run ruff check .         # Lint
uv build                    # Build wheel/sdist
```

## Sistema de Parametrizacao (Placeholders)

O PyFabricOps usa o padrao `#{NomeObjeto_NomeParametro}#` para parametrizar objetos entre ambientes. Cada tipo de objeto tem funcoes especificas:

| Tipo | Arquivo Alvo | Funcoes |
|------|-------------|---------|
| Notebook | `notebook-content.py` | `extract_notebook_parameters()`, `replace_notebook_*()` |
| Semantic Model | `definition/expressions.tmdl` | `extract_tmdl_parameters_from_semantic_model()`, `replace_semantic_model_*()` |
| Data Pipeline | `pipeline-content.json` | `extract_data_pipeline_variables()`, `replace_data_pipeline_*()` |
| Dataflow Gen2 | `mashup.pq` | `extract_dataflow_gen2_variables()`, `replace_dataflow_gen2_*()` |

## Documentacao Criada (tutorial-cicd/)

Pasta `tutorial-cicd/` contem documentacao produzida neste projeto:

### 1. TUTORIAL_CICD_PYFABRICOPS.md
Tutorial completo de referencia com 22 secoes cobrindo:
- Todas as capacidades do PyFabricOps
- 3 metodos de autenticacao (env, oauth, fabric)
- Integracao Git (GitHub + Azure DevOps)
- Export/deploy de objetos
- Deployment Pipelines
- Workflows GitHub Actions
- DMV, Graph, logging, troubleshooting
- Referencia rapida de 180+ funcoes

### 2. CASE_REAL_CICD_AZURE_DEVOPS.md
Case real passo a passo com 21 secoes cobrindo:
- Cenario ficticio "Contoso Analytics" reproduzivel do zero
- Setup completo: Entra ID, Fabric Admin Portal, Azure DevOps
- Criacao de workspaces, conexoes (ADO + SQL + ADLS)
- Conexao workspaces ao Azure DevOps (`ado_connect`)
- Exportacao e parametrizacao completa por tipo de objeto
- Arquivos `env_config/*.json` por ambiente (DEV/STG/PRD)
- Script `deploy.py` com substituicao de placeholders
- Pipelines YAML ADO (template + dev/stg/prd)
- Deploy PRD com approval gates
- Bind de conexoes e refresh pos-deploy
- Validacao pos-deploy com query DAX
- Mapa visual de onde cada tipo de variavel faz sentido
- Checklist final e troubleshooting avancado

### 3. nb_setup_ambiente_cicd.py
Notebook Fabric que monta toda a infraestrutura CI/CD automaticamente:
- Cria 3 workspaces (DEV, STG, PRD) com roles de seguranca
- Cria Fabric Environments com bibliotecas Python + publish
- Cria Variable Libraries com variaveis por ambiente
- Cria repositorio no Azure DevOps via API REST (com branches dev/staging/main)
- Gera e commita pipelines YAML no repositorio
- Registra as pipelines no Azure DevOps
- Conecta workspaces ao Git (ado_connect + git_init)
- Usa auth "fabric" (notebook) e troca para "env" quando precisa do SPN

### 4. GUIA_JUNIOR_SETUP_CICD.md
Documentacao para iniciantes com linguagem acessivel:
- Glossario de termos (workspace, branch, PR, pipeline, etc.)
- Explicacao visual de CI/CD com analogias
- Diferencas entre variaveis de ambiente, placeholders e Variable Libraries
- Passo a passo detalhado dos pre-requisitos (Entra ID, PAT, Admin Portal)
- Guia celula por celula do notebook de setup
- Fluxo do dia a dia (como desenvolver, promover para STG/PRD)
- Checklist de seguranca
- Erros comuns e como resolver
- Perguntas frequentes

## Convencoes de Trabalho

- Nao alterar codigo-fonte do PyFabricOps sem solicitacao explicita
- Documentacao em portugues (sem acentos nos .md para compatibilidade)
- Arquivos de tutorial/documentacao vao na pasta `tutorial-cicd/`
- Nunca commitar .env ou credenciais
