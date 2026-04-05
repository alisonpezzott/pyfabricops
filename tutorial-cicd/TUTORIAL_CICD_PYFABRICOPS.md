# Tutorial Completo: CI/CD com PyFabricOps para Microsoft Fabric

> **PyFabricOps v0.5.4** | Autor do pacote: Alison Pezzott  
> Documentacao oficial: https://pyfabricops.readthedocs.io/en/latest/  
> Repositorio: https://github.com/alisonpezzott/pyfabricops

---

## Indice

1. [O que e o PyFabricOps](#1-o-que-e-o-pyfabricops)
2. [Arquitetura e Capacidades](#2-arquitetura-e-capacidades)
3. [Pre-requisitos](#3-pre-requisitos)
4. [Instalacao](#4-instalacao)
5. [Autenticacao](#5-autenticacao)
6. [Estrutura do Projeto CI/CD](#6-estrutura-do-projeto-cicd)
7. [Integracao com Git (GitHub e Azure DevOps)](#7-integracao-com-git-github-e-azure-devops)
8. [Gerenciamento de Workspaces](#8-gerenciamento-de-workspaces)
9. [Exportacao e Versionamento de Objetos Fabric](#9-exportacao-e-versionamento-de-objetos-fabric)
10. [Deploy Automatizado de Objetos](#10-deploy-automatizado-de-objetos)
11. [Deployment Pipelines (Esteiras de Implantacao)](#11-deployment-pipelines-esteiras-de-implantacao)
12. [CI/CD com GitHub Actions](#12-cicd-com-github-actions)
13. [CI/CD com Azure DevOps](#13-cicd-com-azure-devops)
14. [Estrategia de Branches e Ambientes](#14-estrategia-de-branches-e-ambientes)
15. [Gerenciamento de Conexoes e Gateways](#15-gerenciamento-de-conexoes-e-gateways)
16. [Seguranca e Roles](#16-seguranca-e-roles)
17. [Logging e Depuracao](#17-logging-e-depuracao)
18. [Uso Dentro de Notebooks Fabric](#18-uso-dentro-de-notebooks-fabric)
19. [DMV - Consultas de Gerenciamento Dinamico](#19-dmv---consultas-de-gerenciamento-dinamico)
20. [Referencia Rapida de Funcoes](#20-referencia-rapida-de-funcoes)
21. [Troubleshooting](#21-troubleshooting)
22. [Boas Praticas e Recomendacoes](#22-boas-praticas-e-recomendacoes)

---

## 1. O que e o PyFabricOps

**PyFabricOps** e uma biblioteca Python wrapper que fornece uma interface simples e consistente para as APIs REST oficiais do Microsoft Fabric e Power BI. Quando a API do Fabric nao cobre determinado recurso, a biblioteca faz fallback automatico para a API REST do Power BI.

### Principais Casos de Uso

- **Versionamento**: Exportar definicoes de objetos Fabric para Git
- **CI/CD**: Automatizar deploy de objetos entre ambientes (DEV, STG, PRD)
- **Governanca**: Gerenciar workspaces, roles, conexoes e dominios via codigo
- **Monitoramento**: Consultar DMVs para analise de modelos semanticos
- **Automacao**: Scripts e notebooks para operacoes em massa

### O que o PyFabricOps gerencia

| Categoria | Objetos |
|-----------|---------|
| **Core** | Workspaces, Capacities, Connections, Domains, Folders, Tags, Gateways |
| **Items** | Notebooks, Lakehouses, Semantic Models, Reports, Data Pipelines, Dataflows Gen1/Gen2, Environments, Warehouses, Variable Libraries, Shortcuts |
| **CI/CD** | Deployment Pipelines, Git Integration (GitHub + Azure DevOps) |
| **Analytics** | DMV Queries (XMLA endpoint) |
| **Identity** | Usuarios, Grupos, Service Principals (via Microsoft Graph) |

---

## 2. Arquitetura e Capacidades

### Estrutura de Modulos

```
pyfabricops/
├── api/          # Camada de comunicacao HTTP, autenticacao, tokens
├── core/         # Operacoes fundamentais (workspaces, git, connections...)
├── items/        # CRUD de objetos Fabric
├── helpers/      # Funcoes de alto nivel (export, deploy, config)
├── cd/           # Arquivos de suporte para CI/CD
├── dmv/          # Consultas DMV via XMLA
├── graph/        # Integracao Microsoft Graph (usuarios, grupos)
└── utils/        # Utilitarios, logging, decorators, exceptions
```

### APIs Consumidas

| API | Base URL | Uso |
|-----|----------|-----|
| **Fabric REST** | `https://api.fabric.microsoft.com/v1` | Operacoes principais |
| **Power BI REST** | `https://api.powerbi.com/v1.0/myorg` | Fallback quando Fabric nao cobre |
| **Microsoft Graph** | `https://graph.microsoft.com/v1.0` | Resolucao de identidades |

### Recursos Tecnicos

- **Paginacao automatica**: Continuacao transparente em respostas paginadas
- **Long-Running Operations (LRO)**: Polling automatico para operacoes longas
- **Token caching**: Cache de tokens com refresh automatico (buffer de 5 min)
- **Decorator `@df`**: Conversao automatica de respostas JSON para pandas DataFrame
- **Resolucao name/ID**: Aceita tanto nomes quanto UUIDs em todas as funcoes

---

## 3. Pre-requisitos

### No Azure / Microsoft Entra ID

1. **App Registration (Service Principal)**
   - Acesse o portal Azure > Microsoft Entra ID > App registrations
   - Crie um novo registro de aplicativo
   - Anote: `Application (client) ID`, `Directory (tenant) ID`
   - Em "Certificates & secrets", crie um Client Secret
   - Anote o valor do secret (so e exibido uma vez)

2. **Permissoes da API**
   - No App Registration, va em "API permissions"
   - Adicione permissoes para:
     - **Power BI Service**: `Tenant.Read.All`, `Tenant.ReadWrite.All`
     - **Microsoft Graph**: `User.Read.All`, `Group.Read.All` (se usar funcoes Graph)

3. **Admin Consent**
   - Solicite grant de admin consent para as permissoes adicionadas

4. **Configurar no Fabric Admin Portal**
   - Acesse `app.fabric.microsoft.com` > Settings > Admin Portal
   - Em "Tenant settings", habilite:
     - "Service principals can use Fabric APIs"
     - "Service principals can access read-only admin APIs"
     - Adicione seu Service Principal ou grupo de seguranca

5. **Capacidade Fabric**
   - Necessario ter uma capacidade F ou P ativa (F2+, P1+, ou Trial)

### No ambiente local

- Python >= 3.10, < 3.15
- Git instalado e configurado
- Acesso a internet para APIs do Azure/Fabric

---

## 4. Instalacao

### Via pip

```bash
pip install pyfabricops
```

### Via uv (recomendado pelo projeto)

```bash
uv add pyfabricops
```

### Com dependencias opcionais

```bash
# DMV (consultas XMLA)
pip install pyfabricops[dmv]

# Gateway (criptografia de credenciais)
pip install pyfabricops[gateway]

# Todas as dependencias
pip install pyfabricops[all]
```

### Verificar instalacao

```python
import pyfabricops as pf
print(pf.__version__)  # 0.5.4
```

---

## 5. Autenticacao

O PyFabricOps suporta **tres metodos de autenticacao**, cada um ideal para um cenario:

### 5.1 Environment Variables (`env`) - Recomendado para CI/CD

Ideal para automacao, GitHub Actions, Azure DevOps Pipelines.

```python
import pyfabricops as pf

pf.set_auth_provider("env")
```

**Variaveis de ambiente necessarias:**

```env
# .env (NAO commitar no Git!)
FAB_CLIENT_ID=seu_client_id_aqui
FAB_CLIENT_SECRET=seu_client_secret_aqui
FAB_TENANT_ID=seu_tenant_id_aqui

# Opcionais (para credential_type="user")
FAB_USERNAME=seu_email@empresa.com
FAB_PASSWORD=sua_senha_aqui

# Opcionais
GH_TOKEN=seu_github_token
DATABASE_USERNAME=usuario_banco
DATABASE_PASSWORD=senha_banco
```

**Tipos de credencial suportados:**
- `credential_type="spn"` (padrao) - Usa Client ID + Client Secret (Service Principal)
- `credential_type="user"` - Usa Username + Password (ROPC flow)

### 5.2 OAuth Interativo (`oauth`) - Para desenvolvimento local

Abre o navegador para autenticacao interativa. Token e cacheado automaticamente.

```python
import pyfabricops as pf

pf.set_auth_provider("oauth")

# Na primeira chamada, abrira o navegador
workspaces = pf.list_workspaces()
```

> **Nota**: NAO funciona em ambientes headless (CI/CD, containers).

### 5.3 Fabric Notebook (`fabric`) - Para notebooks no Fabric

Usa `notebookutils.credentials.getToken()` do proprio ambiente Fabric.

```python
import pyfabricops as pf

pf.set_auth_provider("fabric")

# Usa o token do usuario autenticado no notebook
workspaces = pf.list_workspaces()
```

> **Nota**: Funciona APENAS dentro de notebooks Microsoft Fabric.

### Gerenciamento de Token Cache

```python
# Limpar cache de tokens (forca re-autenticacao)
pf.clear_token_cache()
```

O cache e armazenado em `{tempdir}/pf_token_cache.json` com refresh automatico 5 minutos antes da expiracao.

---

## 6. Estrutura do Projeto CI/CD

### 6.1 Gerar arquivos de suporte

O PyFabricOps oferece uma funcao para criar a estrutura inicial do projeto:

```python
import pyfabricops as pf

pf.create_support_files()
```

Isso cria:

```
projeto/
├── .env                    # Template de variaveis de ambiente
├── .gitignore              # Exclusoes para Fabric metadata
├── .gitattributes          # Merge strategy para JSON (union)
├── branches.json           # Mapeamento branch -> sufixo do workspace
├── workspaces_roles.json   # Definicao de roles por workspace
├── connections_roles.json  # Definicao de roles para conexoes
└── src/
    └── README.md           # Diretorio para definicoes exportadas
```

### 6.2 Estrutura recomendada do repositorio

```
fabric-project/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Validacao em PRs
│       ├── deploy-dev.yml      # Deploy para DEV
│       ├── deploy-stg.yml      # Deploy para STG
│       └── deploy-prd.yml      # Deploy para PRD
├── scripts/
│   ├── export.py               # Script de exportacao
│   ├── deploy.py               # Script de deploy
│   └── setup_workspace.py      # Script de configuracao
├── src/                        # Definicoes exportadas do Fabric
│   ├── MyNotebook.Notebook/
│   ├── MySalesModel.SemanticModel/
│   ├── SalesReport.Report/
│   └── ETLPipeline.DataPipeline/
├── .env                        # Variaveis locais (NAO commitar)
├── .gitignore
├── .gitattributes
├── branches.json               # Mapeamento de branches
├── workspaces_roles.json       # Roles dos workspaces
├── connections_roles.json      # Roles das conexoes
└── requirements.txt            # ou pyproject.toml
```

### 6.3 Conteudo do `.gitignore` gerado

```gitignore
**/.pbi/localSettings.json
**/.pbi/cache.abf
**/__pycache__/**
**/_stg/**
.vscode/
.venv
.env
**/py_fab.egg-info
**/dist
**/build
metadata/
```

### 6.4 Conteudo do `.gitattributes` gerado

```
src/**/config.json merge=union
```

Essa configuracao permite merge union em arquivos `config.json`, evitando conflitos desnecessarios ao mesclar branches.

### 6.5 Mapeamento de branches (`branches.json`)

```json
{
    "main": "-PRD",
    "master": "-PRD",
    "dev": "-DEV",
    "develop": "-DEV",
    "staging": "-STG"
}
```

Esse arquivo mapeia nomes de branches Git para sufixos de workspaces no Fabric. Por exemplo:
- Branch `dev` → Workspace `MeuProjeto-DEV`
- Branch `staging` → Workspace `MeuProjeto-STG`
- Branch `main` → Workspace `MeuProjeto-PRD`

---

## 7. Integracao com Git (GitHub e Azure DevOps)

O PyFabricOps permite conectar workspaces Fabric a repositorios Git, sincronizar alteracoes e versionar objetos.

### 7.1 Conectar ao GitHub

```python
import pyfabricops as pf

pf.set_auth_provider("env")

# Conectar workspace ao repositorio GitHub
pf.github_connect(
    workspace="MeuProjeto-DEV",
    connection="MinhaConexaoGitHub",     # Nome ou ID da conexao configurada
    owner_name="minha-organizacao",      # Owner do repo no GitHub
    repository_name="fabric-project",    # Nome do repositorio
    branch_name="dev",                   # Branch a conectar
    directory_name="/src"                # Diretorio dentro do repo
)
```

### 7.2 Conectar ao Azure DevOps

```python
pf.ado_connect(
    workspace="MeuProjeto-DEV",
    connection_id="id-da-conexao",
    organization_name="minha-organizacao",
    project_name="meu-projeto-ado",
    repository_name="fabric-repo",
    branch_name="develop",
    directory_name="src"
)
```

### 7.3 Verificar status do Git

```python
# Retorna DataFrame com status
status = pf.git_status("MeuProjeto-DEV")
print(status)

# Retorna dicionario
status = pf.git_status("MeuProjeto-DEV", df=False)
print(status["remoteCommitHash"])
print(status["workspaceHead"])
```

### 7.4 Inicializar conexao Git

```python
# Inicializa com preferencia para o workspace
pf.git_init(
    workspace="MeuProjeto-DEV",
    initialize_strategy="PreferWorkspace"  # ou "PreferRemote" ou "None"
)
```

**Estrategias de inicializacao:**
- `PreferWorkspace`: Em conflito, mantem a versao do workspace
- `PreferRemote`: Em conflito, mantem a versao do repositorio Git
- `None`: Nao resolve conflitos automaticamente

### 7.5 Sincronizar do Git para o Workspace

```python
# Atualiza o workspace com as ultimas alteracoes do Git
pf.update_from_git(
    workspace="MeuProjeto-DEV",
    conflict_resolution_policy="PreferRemote",  # Git vence em conflitos
    allow_override_items=True
)
```

A funcao `update_from_git` faz polling automatico:
- Verifica se `remoteCommitHash == workspaceHead`
- Se diferente, envia requisicao de update
- Repete ate 10 vezes com intervalo de 20 segundos
- Retorna `True` quando sincronizado

### 7.6 Commitar do Workspace para o Git

```python
# Commit de todas as alteracoes
pf.commit_to_git(
    workspace="MeuProjeto-DEV",
    mode="All",
    comment="feat: Atualizado modelo de vendas com novas medidas"
)

# Commit seletivo
pf.commit_to_git(
    workspace="MeuProjeto-DEV",
    mode="Selective",
    comment="fix: Corrigido calculo de margem",
    selective_payload={
        "items": [
            {"objectId": "item-uuid-aqui", "logicalId": "logical-id-aqui"}
        ]
    }
)
```

### 7.7 Obter informacoes da conexao Git

```python
# Ver detalhes da conexao
conexao = pf.get_git_connection("MeuProjeto-DEV", df=False)
print(conexao)

# Ver credenciais
credenciais = pf.get_my_git_credentials("MeuProjeto-DEV", df=False)
print(credenciais)
```

### 7.8 Desconectar do Git

```python
pf.git_disconnect("MeuProjeto-DEV")
```

---

## 8. Gerenciamento de Workspaces

### 8.1 Listar workspaces

```python
# Como DataFrame
workspaces = pf.list_workspaces()
print(workspaces)

# Como lista de dicionarios
workspaces = pf.list_workspaces(df=False)
for ws in workspaces:
    print(f"{ws['displayName']} - {ws['id']}")
```

### 8.2 Criar workspace

```python
pf.create_workspace(
    display_name="MeuProjeto-DEV",
    capacity="NomeDaCapacidade",     # Nome ou ID da capacidade
    description="Workspace de desenvolvimento do projeto"
)
```

### 8.3 Atualizar workspace

```python
pf.update_workspace(
    workspace="MeuProjeto-DEV",
    display_name="MeuProjeto-DEV-v2",
    description="Descricao atualizada"
)
```

### 8.4 Deletar workspace

```python
pf.delete_workspace("MeuProjeto-OLD")
```

### 8.5 Atribuir workspace a uma capacidade

```python
pf.assign_workspace_to_capacity(
    workspace="MeuProjeto-DEV",
    capacity="F2-capacity"
)
```

### 8.6 Gerenciar roles do workspace

```python
# Adicionar role
pf.add_workspace_role_assignment(
    workspace="MeuProjeto-DEV",
    user_uuid="uuid-do-usuario",
    user_type="User",         # User, Group, ServicePrincipal, ServicePrincipalProfile
    role="Contributor"         # Admin, Member, Contributor, Viewer
)

# Listar roles
roles = pf.list_workspace_role_assignments("MeuProjeto-DEV")
print(roles)
```

---

## 9. Exportacao e Versionamento de Objetos Fabric

A exportacao converte definicoes de objetos Fabric em arquivos no disco, permitindo versionamento com Git.

### 9.1 Exportar um item especifico

```python
# Exportar um notebook
pf.export_notebook("MeuProjeto-DEV", "MeuNotebook", "./src")

# Exportar um semantic model
pf.export_semantic_model("MeuProjeto-DEV", "ModeloVendas", "./src")

# Exportar um report
pf.export_report("MeuProjeto-DEV", "RelatorioVendas", "./src")

# Exportar um data pipeline
pf.export_data_pipeline("MeuProjeto-DEV", "ETLPipeline", "./src")

# Exportar um dataflow gen2
pf.export_dataflow_gen2("MeuProjeto-DEV", "MeuDataflow", "./src")

# Exportar um item generico (qualquer tipo)
pf.export_item("MeuProjeto-DEV", "QualquerItem", "./src")
```

### 9.2 Exportar todos os itens de um tipo

```python
# Exportar todos os notebooks
pf.export_all_notebooks("MeuProjeto-DEV", "./src")

# Exportar todos os semantic models
pf.export_all_semantic_models("MeuProjeto-DEV", "./src")

# Exportar todos os reports
pf.export_all_reports("MeuProjeto-DEV", "./src")

# Exportar todos os data pipelines
pf.export_all_data_pipelines("MeuProjeto-DEV", "./src")

# Exportar TODOS os itens do workspace
pf.export_all_items("MeuProjeto-DEV", "./src")
```

### 9.3 Estrutura dos arquivos exportados

Apos a exportacao, os arquivos ficam organizados por tipo:

```
src/
├── MeuNotebook.Notebook/
│   ├── notebook-content.py
│   └── .platform
├── ModeloVendas.SemanticModel/
│   ├── definition/
│   │   ├── tables/
│   │   │   ├── Vendas.tmdl
│   │   │   └── Clientes.tmdl
│   │   ├── model.tmdl
│   │   └── ...
│   └── .platform
├── RelatorioVendas.Report/
│   ├── definition.pbir
│   ├── report.json
│   └── .platform
└── ETLPipeline.DataPipeline/
    ├── pipeline-content.json
    └── .platform
```

### 9.4 Obter configuracao de itens

```python
# Config de um notebook (retorna dicionario)
config = pf.get_notebook_config("MeuProjeto-DEV", "MeuNotebook")

# Config de todos os notebooks
all_configs = pf.get_all_notebooks_config("MeuProjeto-DEV")

# Config de semantic model
config = pf.get_semantic_model_config("MeuProjeto-DEV", "ModeloVendas")
```

---

## 10. Deploy Automatizado de Objetos

O deploy pega definicoes locais (exportadas para disco) e cria ou atualiza os objetos no workspace destino.

### 10.1 Deploy de um item especifico

```python
# Deploy de um notebook
pf.deploy_notebook("MeuProjeto-STG", "./src/MeuNotebook.Notebook")

# Deploy de um semantic model
pf.deploy_semantic_model("MeuProjeto-STG", "./src/ModeloVendas.SemanticModel")

# Deploy de um report
pf.deploy_report("MeuProjeto-STG", "./src/RelatorioVendas.Report")

# Deploy de um data pipeline
pf.deploy_data_pipeline("MeuProjeto-STG", "./src/ETLPipeline.DataPipeline")

# Deploy de um item generico
pf.deploy_item("MeuProjeto-STG", "./src/QualquerItem.Tipo")
```

### 10.2 Deploy de todos os itens

```python
# Deploy de todos os notebooks
pf.deploy_all_notebooks("MeuProjeto-STG", "./src")

# Deploy de todos os semantic models
pf.deploy_all_semantic_models("MeuProjeto-STG", "./src")

# Deploy de TODOS os itens (respeita ordem de dependencia)
pf.deploy_all_items("MeuProjeto-STG", "./src")
```

A funcao `deploy_all_items` processa os tipos na seguinte ordem:
1. Notebook
2. DataPipeline
3. Dataflow
4. SemanticModel
5. Report
6. VariableLibrary
7. Lakehouse
8. Warehouse
9. Environment
10. CopyJob

### 10.3 Logica de deploy (create vs update)

Para cada item, o PyFabricOps:
1. Verifica se o item ja existe no workspace destino (por nome + tipo)
2. Se **nao existe**: cria o item com `create_item()`, incluindo atribuicao de folder
3. Se **ja existe**: atualiza a definicao com `update_item_definition()`

### 10.4 Script completo de deploy

```python
#!/usr/bin/env python3
"""Script de deploy automatizado para Microsoft Fabric"""

import json
import subprocess
import pyfabricops as pf

# Configuracao
pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

# Determinar workspace baseado na branch atual
branch = subprocess.check_output(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"]
).decode().strip()

with open("branches.json") as f:
    branches = json.load(f)

suffix = branches.get(branch, "-DEV")
workspace_name = f"MeuProjeto{suffix}"

print(f"Branch: {branch} -> Workspace: {workspace_name}")

# Deploy de todos os itens
pf.deploy_all_items(workspace_name, "./src")

# Opcional: Atualizar conexao Git do workspace
pf.update_from_git(
    workspace=workspace_name,
    conflict_resolution_policy="PreferRemote"
)

print("Deploy concluido com sucesso!")
```

---

## 11. Deployment Pipelines (Esteiras de Implantacao)

As Deployment Pipelines do Fabric permitem promover conteudo entre estagios (DEV -> STG -> PRD) de forma controlada.

### 11.1 Listar pipelines existentes

```python
pipelines = pf.list_deployment_pipelines()
print(pipelines)
```

### 11.2 Criar uma deployment pipeline

```python
pf.create_deployment_pipeline(
    display_name="Projeto Vendas - Pipeline",
    stages=[
        {
            "displayName": "Development",
            "description": "Ambiente de desenvolvimento",
            "isPublic": False
        },
        {
            "displayName": "Staging",
            "description": "Ambiente de homologacao",
            "isPublic": False
        },
        {
            "displayName": "Production",
            "description": "Ambiente de producao",
            "isPublic": True
        }
    ],
    description="Pipeline de deploy do projeto de vendas"
)
```

### 11.3 Atribuir workspaces aos estagios

```python
# Atribuir workspace DEV ao estagio Development
pf.assign_workspace_to_stage(
    workspace="MeuProjeto-DEV",
    pipeline="Projeto Vendas - Pipeline",
    stage="Development"
)

# Atribuir workspace STG ao estagio Staging
pf.assign_workspace_to_stage(
    workspace="MeuProjeto-STG",
    pipeline="Projeto Vendas - Pipeline",
    stage="Staging"
)

# Atribuir workspace PRD ao estagio Production
pf.assign_workspace_to_stage(
    workspace="MeuProjeto-PRD",
    pipeline="Projeto Vendas - Pipeline",
    stage="Production"
)
```

### 11.4 Promover conteudo entre estagios

```python
# Deploy de DEV para STG (todos os itens)
pf.deploy_stage_content(
    pipeline="Projeto Vendas - Pipeline",
    source_stage="Development",
    target_stage="Staging",
    note="Release v1.2.0 - Novas medidas de vendas"
)

# Deploy seletivo de STG para PRD
pf.deploy_stage_content(
    pipeline="Projeto Vendas - Pipeline",
    source_stage="Staging",
    target_stage="Production",
    items=[
        {
            "sourceItemId": "uuid-semantic-model",
            "itemType": "SemanticModel"
        },
        {
            "sourceItemId": "uuid-report",
            "itemType": "Report"
        }
    ],
    note="Hotfix: Correcao no calculo de margem",
    options={"allowCrossRegionDeployment": True}
)
```

### 11.5 Gerenciar roles da pipeline

```python
# Adicionar permissao
pf.add_deployment_pipeline_role_assignment(
    pipeline="Projeto Vendas - Pipeline",
    user_uuid="uuid-do-usuario",
    user_type="ServicePrincipal",
    role="Admin"
)

# Listar permissoes
roles = pf.list_deployment_pipeline_role_assignments("Projeto Vendas - Pipeline")
print(roles)
```

### 11.6 Monitorar operacoes

```python
# Listar operacoes da pipeline
ops = pf.list_deployment_pipeline_operations("Projeto Vendas - Pipeline")
print(ops)

# Detalhes de uma operacao especifica
op = pf.get_deployment_pipeline_operation(
    "Projeto Vendas - Pipeline",
    "operation-uuid"
)
```

### 11.7 Atualizar e deletar

```python
# Atualizar pipeline
pf.update_deployment_pipeline(
    pipeline="Projeto Vendas - Pipeline",
    display_name="Vendas - Deploy Pipeline v2",
    description="Pipeline atualizada"
)

# Atualizar estagio
pf.update_deployment_pipeline_stage(
    pipeline="Vendas - Deploy Pipeline v2",
    stage="Production",
    description="Producao - somente deploys aprovados",
    is_public=True
)

# Desassociar workspace de um estagio
pf.unassign_workspace_to_stage(
    pipeline="Vendas - Deploy Pipeline v2",
    stage="Development"
)

# Deletar pipeline
pf.delete_deployment_pipeline("Pipeline-Antiga")
```

---

## 12. CI/CD com GitHub Actions

### 12.1 Workflow de validacao (CI)

Crie `.github/workflows/ci.yml`:

```yaml
name: CI - Validate Fabric Definitions

on:
  pull_request:
    branches: [main, dev, staging]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      
      - name: Install dependencies
        run: pip install pyfabricops
      
      - name: Validate structure
        run: |
          python -c "
          import os, sys
          src_path = './src'
          if not os.path.exists(src_path):
              print('ERRO: Diretorio src/ nao encontrado')
              sys.exit(1)
          
          valid_types = [
              'Notebook', 'SemanticModel', 'Report', 'DataPipeline',
              'Dataflow', 'Lakehouse', 'Warehouse', 'Environment',
              'VariableLibrary', 'CopyJob'
          ]
          
          for item in os.listdir(src_path):
              if '.' in item:
                  item_type = item.split('.')[-1]
                  if item_type not in valid_types:
                      print(f'AVISO: Tipo desconhecido: {item} ({item_type})')
                  else:
                      print(f'OK: {item}')
          
          print('Validacao concluida!')
          "
```

### 12.2 Workflow de deploy (CD)

Crie `.github/workflows/deploy.yml`:

```yaml
name: CD - Deploy to Fabric

on:
  push:
    branches: [dev, staging, main]

env:
  FAB_CLIENT_ID: ${{ secrets.FAB_CLIENT_ID }}
  FAB_CLIENT_SECRET: ${{ secrets.FAB_CLIENT_SECRET }}
  FAB_TENANT_ID: ${{ secrets.FAB_TENANT_ID }}
  PROJECT_NAME: MeuProjeto

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      
      - name: Install dependencies
        run: pip install pyfabricops
      
      - name: Determine target workspace
        id: workspace
        run: |
          BRANCH="${GITHUB_REF_NAME}"
          case "$BRANCH" in
            main|master)  SUFFIX="-PRD" ;;
            staging)      SUFFIX="-STG" ;;
            dev|develop)  SUFFIX="-DEV" ;;
            *)            SUFFIX="-DEV" ;;
          esac
          echo "name=${PROJECT_NAME}${SUFFIX}" >> $GITHUB_OUTPUT
          echo "Deploying to: ${PROJECT_NAME}${SUFFIX}"
      
      - name: Deploy all items
        run: |
          python -c "
          import pyfabricops as pf
          
          pf.set_auth_provider('env')
          pf.setup_logging(level='INFO')
          
          workspace = '${{ steps.workspace.outputs.name }}'
          print(f'Deploying to workspace: {workspace}')
          
          pf.deploy_all_items(workspace, './src')
          print('Deploy concluido!')
          "
      
      - name: Sync from Git
        run: |
          python -c "
          import pyfabricops as pf
          
          pf.set_auth_provider('env')
          
          workspace = '${{ steps.workspace.outputs.name }}'
          pf.update_from_git(
              workspace=workspace,
              conflict_resolution_policy='PreferRemote'
          )
          "
```

### 12.3 Workflow com Deployment Pipeline

```yaml
name: CD - Promote via Deployment Pipeline

on:
  workflow_dispatch:
    inputs:
      source_stage:
        description: "Source stage"
        required: true
        type: choice
        options:
          - Development
          - Staging
      target_stage:
        description: "Target stage"
        required: true
        type: choice
        options:
          - Staging
          - Production
      note:
        description: "Deploy note"
        required: false

env:
  FAB_CLIENT_ID: ${{ secrets.FAB_CLIENT_ID }}
  FAB_CLIENT_SECRET: ${{ secrets.FAB_CLIENT_SECRET }}
  FAB_TENANT_ID: ${{ secrets.FAB_TENANT_ID }}

jobs:
  promote:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      
      - run: pip install pyfabricops
      
      - name: Promote content
        run: |
          python -c "
          import pyfabricops as pf
          
          pf.set_auth_provider('env')
          pf.setup_logging(level='INFO')
          
          pf.deploy_stage_content(
              pipeline='Projeto Vendas - Pipeline',
              source_stage='${{ inputs.source_stage }}',
              target_stage='${{ inputs.target_stage }}',
              note='${{ inputs.note }}' or 'Automated deploy via GitHub Actions'
          )
          print('Promocao concluida!')
          "
```

### 12.4 Configurar Secrets no GitHub

1. Va ao repositorio GitHub > Settings > Secrets and variables > Actions
2. Adicione os seguintes secrets:
   - `FAB_CLIENT_ID` - Client ID do App Registration
   - `FAB_CLIENT_SECRET` - Client Secret do App Registration
   - `FAB_TENANT_ID` - Tenant ID do Azure AD

---

## 13. CI/CD com Azure DevOps

### 13.1 Pipeline YAML para Azure DevOps

Crie `azure-pipelines.yml`:

```yaml
trigger:
  branches:
    include:
      - main
      - dev
      - staging

pool:
  vmImage: 'ubuntu-latest'

variables:
  - group: FabricCredentials  # Variable group com FAB_CLIENT_ID, FAB_CLIENT_SECRET, FAB_TENANT_ID
  - name: projectName
    value: 'MeuProjeto'

stages:
  - stage: Deploy
    jobs:
      - job: DeployToFabric
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.13'
          
          - script: pip install pyfabricops
            displayName: 'Install pyfabricops'
          
          - script: |
              python -c "
              import os, pyfabricops as pf
              
              pf.set_auth_provider('env')
              pf.setup_logging(level='INFO')
              
              branch = '$(Build.SourceBranchName)'
              suffixes = {'main': '-PRD', 'master': '-PRD', 'dev': '-DEV', 'develop': '-DEV', 'staging': '-STG'}
              suffix = suffixes.get(branch, '-DEV')
              workspace = f'$(projectName){suffix}'
              
              print(f'Branch: {branch} -> Workspace: {workspace}')
              pf.deploy_all_items(workspace, './src')
              print('Deploy concluido!')
              "
            displayName: 'Deploy items to Fabric'
            env:
              FAB_CLIENT_ID: $(FAB_CLIENT_ID)
              FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
              FAB_TENANT_ID: $(FAB_TENANT_ID)
```

---

## 14. Estrategia de Branches e Ambientes

### 14.1 Modelo recomendado: Git Flow Simplificado

```
                           ┌─────────────┐
                           │ feature/*    │ ← Desenvolvimento de features
                           └──────┬──────┘
                                  │ PR
                           ┌──────▼──────┐
                           │    dev       │ ← Workspace MeuProjeto-DEV
                           └──────┬──────┘
                                  │ PR (aprovacao)
                           ┌──────▼──────┐
                           │  staging     │ ← Workspace MeuProjeto-STG
                           └──────┬──────┘
                                  │ PR (aprovacao + testes)
                           ┌──────▼──────┐
                           │    main      │ ← Workspace MeuProjeto-PRD
                           └─────────────┘
```

### 14.2 Configuracao dos workspaces por ambiente

| Branch | Workspace | Capacidade | Proposito |
|--------|-----------|-----------|-----------|
| `dev` | MeuProjeto-DEV | F2 (menor custo) | Desenvolvimento e testes |
| `staging` | MeuProjeto-STG | F4 | Homologacao e UAT |
| `main` | MeuProjeto-PRD | F8+ (producao) | Producao |

### 14.3 Script de setup completo dos ambientes

```python
#!/usr/bin/env python3
"""Configura todos os workspaces e conexoes para o projeto"""

import json
import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

PROJECT = "MeuProjeto"
CAPACITY = "MinhaCapacidadeF2"

# Ler configuracao de branches
with open("branches.json") as f:
    branches = json.load(f)

# Ler roles
with open("workspaces_roles.json") as f:
    roles = json.load(f)

# Criar workspaces para cada ambiente
for branch, suffix in branches.items():
    ws_name = f"{PROJECT}{suffix}"
    
    # Criar workspace (ignora se ja existe)
    try:
        pf.create_workspace(
            display_name=ws_name,
            capacity=CAPACITY,
            description=f"Workspace {suffix.replace('-', '')} do projeto {PROJECT}"
        )
        print(f"Workspace criado: {ws_name}")
    except Exception as e:
        print(f"Workspace {ws_name} ja existe ou erro: {e}")
    
    # Atribuir roles
    for role_def in roles:
        try:
            pf.add_workspace_role_assignment(
                workspace=ws_name,
                user_uuid=role_def["user_uuid"],
                user_type=role_def["user_type"],
                role=role_def["role"]
            )
        except Exception as e:
            print(f"Role ja atribuida ou erro: {e}")

print("Setup concluido!")
```

---

## 15. Gerenciamento de Conexoes e Gateways

### 15.1 Conexoes

```python
# Listar todas as conexoes
conexoes = pf.list_connections()
print(conexoes)

# Criar uma conexao
pf.create_connection(
    display_name="MinhaConexaoSQL",
    connectivity_type="ShareableCloud",
    connection_details={
        "type": "SQL",
        "parameters": [
            {"name": "server", "value": "myserver.database.windows.net"},
            {"name": "database", "value": "mydb"}
        ]
    },
    credential_details={
        "singleCredential": {
            "credentialType": "Basic",
            "username": "admin",
            "password": "senha-segura"
        }
    }
)

# Atribuir roles a conexao
pf.add_connection_role_assignment(
    connection="MinhaConexaoSQL",
    user_uuid="uuid-do-usuario",
    user_type="ServicePrincipal",
    role="User"
)
```

### 15.2 Gateways

```python
# Listar gateways
gateways = pf.list_gateways()
print(gateways)

# Detalhes de um gateway
gateway = pf.get_gateway("MeuGateway")
print(gateway)
```

---

## 16. Seguranca e Roles

### 16.1 Resolucao de identidades via Microsoft Graph

```python
# Obter UUID de um usuario por email
user_id = pf.get_user_id("joao@empresa.com")

# Obter email por UUID
email = pf.get_user_email("uuid-do-usuario")

# Obter UUID de um grupo de seguranca
group_id = pf.get_security_group_id("DataEngineers")

# Obter UUID de um Service Principal
spn_id = pf.get_service_principal_id("MeuAppCICD")

# Obter UUID de um App Registration
app_id = pf.get_app_registration_id("MeuApp")
```

### 16.2 Configuracao via arquivo `workspaces_roles.json`

```json
[
    {
        "user_uuid": "uuid-admin-principal",
        "user_type": "User",
        "role": "Admin"
    },
    {
        "user_uuid": "uuid-grupo-engenheiros",
        "user_type": "Group",
        "role": "Member"
    },
    {
        "user_uuid": "uuid-service-principal-cicd",
        "user_type": "ServicePrincipal",
        "role": "Contributor"
    },
    {
        "user_uuid": "uuid-grupo-viewers",
        "user_type": "Group",
        "role": "Viewer"
    }
]
```

### 16.3 Tipos de roles disponiveis

| Role | Permissoes |
|------|-----------|
| **Admin** | Controle total do workspace |
| **Member** | Editar conteudo, compartilhar itens |
| **Contributor** | Editar conteudo, sem compartilhar |
| **Viewer** | Somente visualizacao |

---

## 17. Logging e Depuracao

### 17.1 Configuracao de logging

```python
import pyfabricops as pf

# Formato padrao (recomendado)
pf.setup_logging(level="INFO", format_style="standard")

# Formato minimo (apenas timestamp + nivel + mensagem)
pf.setup_logging(level="INFO", format_style="minimal")

# Formato detalhado (todas as informacoes)
pf.setup_logging(level="DEBUG", format_style="detailed")
```

### 17.2 Niveis de log

| Nivel | Valor | Uso |
|-------|-------|-----|
| `DEBUG` | 10 | Detalhes internos, payloads HTTP |
| `INFO` | 20 | Operacoes normais |
| `SUCCESS` | 25 | Operacoes concluidas com exito (custom) |
| `WARNING` | 30 | Situacoes de atencao |
| `ERROR` | 40 | Falhas em operacoes |
| `CRITICAL` | 50 | Erros fatais |

### 17.3 Modo debug

```python
# Ativa debug somente para pyfabricops
pf.enable_debug_mode()

# Ativa debug incluindo bibliotecas externas (requests, azure-identity...)
pf.enable_debug_mode(include_external=True)

# Desabilitar logging completamente
pf.disable_logging()

# Resetar para configuracao padrao
pf.reset_logging()
```

---

## 18. Uso Dentro de Notebooks Fabric

O PyFabricOps pode ser usado diretamente dentro de notebooks do Microsoft Fabric.

### 18.1 Instalacao no notebook

```python
# Primeira celula do notebook
%pip install pyfabricops
```

### 18.2 Configuracao

```python
import pyfabricops as pf

# Usa o token do usuario ja autenticado no Fabric
pf.set_auth_provider("fabric")
pf.setup_logging(level="INFO")
```

### 18.3 Exemplo: Exportar e sincronizar

```python
# Listar itens do workspace atual
items = pf.list_items("MeuWorkspace")
display(items)

# Verificar status Git
status = pf.git_status("MeuWorkspace")
display(status)

# Commitar alteracoes
pf.commit_to_git(
    workspace="MeuWorkspace",
    comment="feat: Novas transformacoes no pipeline de dados"
)
```

### 18.4 Exemplo: Deploy entre workspaces via notebook

```python
# Promover conteudo de DEV para STG usando deployment pipeline
pf.deploy_stage_content(
    pipeline="Pipeline do Projeto",
    source_stage="Development",
    target_stage="Staging",
    note="Promocao automatizada via notebook"
)
```

---

## 19. DMV - Consultas de Gerenciamento Dinamico

O PyFabricOps permite consultar DMVs (Dynamic Management Views) de Semantic Models via XMLA endpoint.

> **Requisito**: Instale com `pip install pyfabricops[dmv]` e tenha o DAX Studio ou ADOMD.NET disponivel.

### 19.1 Configurar conexao DMV

```python
import pyfabricops as pf
from pathlib import Path

# Importar pyadomd (apontar para a pasta do DAX Studio)
pf.import_pyadomd(Path(r"C:\Program Files\DAX Studio\bin"))

# Conexao via Service Principal
conn_str = pf.set_dmv_connection_string_spn(
    client_id="seu-client-id",
    client_secret="seu-client-secret",
    tenant_id="seu-tenant-id",
    workspace_name="MeuProjeto-PRD",
    semantic_model_name="ModeloVendas"
)
```

### 19.2 Executar consultas

```python
# Tabelas do modelo
tables = pf.dmv_fetch_tables_raw(conn_str)
print(tables)

# Particoes com metadados enriquecidos
partitions = pf.dmv_fetch_partitions_enriched(conn_str)
print(partitions)

# Query DMV personalizada
result = pf.dmv_query(conn_str, "SELECT * FROM $SYSTEM.TMSCHEMA_MEASURES")
print(result)
```

---

## 20. Referencia Rapida de Funcoes

### Autenticacao
| Funcao | Descricao |
|--------|-----------|
| `set_auth_provider(source)` | Definir metodo de autenticacao ("env", "oauth", "fabric") |
| `clear_token_cache()` | Limpar cache de tokens |

### Workspaces
| Funcao | Descricao |
|--------|-----------|
| `list_workspaces()` | Listar todos os workspaces |
| `create_workspace(name, capacity)` | Criar workspace |
| `update_workspace(ws, name)` | Atualizar workspace |
| `delete_workspace(ws)` | Deletar workspace |
| `add_workspace_role_assignment(ws, user, type, role)` | Adicionar role |

### Git
| Funcao | Descricao |
|--------|-----------|
| `github_connect(ws, conn, owner, repo)` | Conectar ao GitHub |
| `ado_connect(ws, conn, org, project, repo)` | Conectar ao Azure DevOps |
| `git_init(ws, strategy)` | Inicializar conexao Git |
| `git_status(ws)` | Status da sincronizacao |
| `update_from_git(ws, policy)` | Sincronizar Git -> Workspace |
| `commit_to_git(ws, mode, comment)` | Commit Workspace -> Git |
| `git_disconnect(ws)` | Desconectar do Git |

### Export/Deploy
| Funcao | Descricao |
|--------|-----------|
| `export_item(ws, item, path)` | Exportar item para disco |
| `export_all_items(ws, path)` | Exportar todos os itens |
| `deploy_item(ws, path)` | Deploy de item do disco |
| `deploy_all_items(ws, path)` | Deploy de todos os itens |

### Deployment Pipelines
| Funcao | Descricao |
|--------|-----------|
| `create_deployment_pipeline(name, stages)` | Criar pipeline |
| `assign_workspace_to_stage(ws, pipe, stage)` | Atribuir workspace |
| `deploy_stage_content(pipe, source, target)` | Promover conteudo |
| `list_deployment_pipeline_operations(pipe)` | Listar operacoes |

### Items (funcoes por tipo)
Cada tipo (notebook, semantic_model, report, data_pipeline, dataflow_gen2, lakehouse, warehouse, environment) tem:
- `list_<tipo>s(ws)` - Listar
- `get_<tipo>(ws, item)` - Obter detalhes
- `create_<tipo>(ws, name)` - Criar
- `update_<tipo>(ws, item)` - Atualizar
- `delete_<tipo>(ws, item)` - Deletar
- `export_<tipo>(ws, item, path)` - Exportar
- `deploy_<tipo>(ws, path)` - Deploy

---

## 21. Troubleshooting

### Erros comuns e solucoes

| Erro | Causa | Solucao |
|------|-------|---------|
| `AuthenticationError: Token request failed: 401` | Credenciais invalidas | Verifique FAB_CLIENT_ID, FAB_CLIENT_SECRET, FAB_TENANT_ID |
| `AuthenticationError: Token request failed: 400` | Permissoes insuficientes | Verifique API permissions e Admin Consent no Azure |
| `ResourceNotFoundError` | Workspace/item nao encontrado | Verifique o nome exato ou use UUID |
| `OptionNotAvailableError` | Parametro invalido | Verifique os valores aceitos na documentacao |
| `notebookutils is not available` | Usando auth "fabric" fora do Fabric | Use "env" ou "oauth" em ambientes locais |
| `ConfigurationError` | Configuracao ausente | Verifique .env e variaveis de ambiente |
| `RequestError: 429 Too Many Requests` | Rate limiting da API | Adicione delays entre chamadas em massa |

### Verificacoes rapidas

```python
import pyfabricops as pf

# Testar autenticacao
pf.set_auth_provider("env")
pf.setup_logging(level="DEBUG")

# Se isso funcionar, a autenticacao esta OK
try:
    ws = pf.list_workspaces()
    print(f"Autenticacao OK! {len(ws)} workspaces encontrados.")
except Exception as e:
    print(f"Erro de autenticacao: {e}")
```

### Limpar cache em caso de problemas de token

```python
pf.clear_token_cache()
```

---

## 22. Boas Praticas e Recomendacoes

### Seguranca

1. **Nunca commite o arquivo `.env`** - Ja esta no `.gitignore` gerado
2. **Use GitHub Secrets / Azure DevOps Variable Groups** para credenciais no CI/CD
3. **Prefira Service Principal (SPN)** ao inves de credenciais de usuario
4. **Rotacione Client Secrets** periodicamente
5. **Aplique o principio do menor privilegio** nas roles de cada ambiente
6. **Segregue capacidades** - Use capacidades menores em DEV, maiores em PRD

### Fluxo de Trabalho

1. **Desenvolva em DEV** - Faca alteracoes no workspace DEV, conectado a branch `dev`
2. **Exporte definicoes** - Use `export_all_items()` ou `commit_to_git()` para versionar
3. **Revise via PR** - Crie Pull Requests de `dev` para `staging`
4. **Homologue em STG** - Automatize deploy para STG apos merge
5. **Aprove para PRD** - Use workflow manual ou approval gates para producao
6. **Monitore operacoes** - Use `list_deployment_pipeline_operations()` para auditoria

### Organizacao do Repositorio

1. **Use `branches.json`** para mapear branches a workspaces
2. **Use `workspaces_roles.json`** para definir roles como codigo
3. **Mantenha o diretorio `src/`** exclusivo para definicoes Fabric
4. **Separe scripts** de automacao em `scripts/`
5. **Documente** decisoes de arquitetura e configuracoes

### Performance

1. **Use `df=False`** quando nao precisar de DataFrames (mais rapido)
2. **Evite chamar `list_*` repetidamente** - Armazene resultados em variaveis
3. **Use deploy seletivo** quando possivel, em vez de `deploy_all_items()`
4. **Configure `setup_logging(level="WARNING")`** em producao para reduzir output

### Pontos de Atencao

1. **Ordem de deploy importa**: Semantic Models antes de Reports, Lakehouses antes de Notebooks que os referenciam
2. **Deployment Pipelines vs Git Deploy**: Use Deployment Pipelines para fluxos controlados (aprovacao por estagios) e Git Deploy para automacao direta
3. **Conflitos de Git**: Defina politica clara (`PreferRemote` ou `PreferWorkspace`) por ambiente
4. **Limites de API**: A API do Fabric tem rate limiting; em operacoes em massa, considere adicionar delays
5. **Objetos nao suportados para export**: Nem todos os tipos de item suportam `get_item_definition()` (ex: SQLEndpoint e filtrado automaticamente)
6. **Ambientes com Spark**: Environments precisam de tratamento especial para bibliotecas e configuracoes Spark

---

## Apendice: Fluxo Completo Passo a Passo

### Cenario: Setup completo de CI/CD do zero

```python
#!/usr/bin/env python3
"""
Script completo para configurar CI/CD com PyFabricOps
Execute UMA vez para setup inicial
"""
import pyfabricops as pf

# 1. Configurar autenticacao
pf.set_auth_provider("env")
pf.setup_logging(level="INFO", format_style="standard")

# 2. Gerar arquivos de suporte
pf.create_support_files()
print("Arquivos de suporte criados!")

# 3. Criar workspaces
for env_name, suffix in [("DEV", "-DEV"), ("STG", "-STG"), ("PRD", "-PRD")]:
    ws_name = f"MeuProjeto{suffix}"
    pf.create_workspace(
        display_name=ws_name,
        capacity="MinhaCapacidade",
        description=f"Ambiente {env_name}"
    )
    print(f"Workspace criado: {ws_name}")

# 4. Criar Deployment Pipeline
pf.create_deployment_pipeline(
    display_name="MeuProjeto - Pipeline",
    stages=[
        {"displayName": "Development", "isPublic": False},
        {"displayName": "Staging", "isPublic": False},
        {"displayName": "Production", "isPublic": True}
    ]
)

# 5. Atribuir workspaces aos estagios
for stage, suffix in [("Development", "-DEV"), ("Staging", "-STG"), ("Production", "-PRD")]:
    pf.assign_workspace_to_stage(
        workspace=f"MeuProjeto{suffix}",
        pipeline="MeuProjeto - Pipeline",
        stage=stage
    )

# 6. Conectar workspace DEV ao GitHub
pf.github_connect(
    workspace="MeuProjeto-DEV",
    connection="MinhaConexaoGitHub",
    owner_name="minha-org",
    repository_name="fabric-project",
    branch_name="dev",
    directory_name="/src"
)

# 7. Inicializar Git
pf.git_init(
    workspace="MeuProjeto-DEV",
    initialize_strategy="PreferWorkspace"
)

# 8. Exportar estado atual para o repositorio
pf.export_all_items("MeuProjeto-DEV", "./src")

print("""
Setup concluido! Proximos passos:
1. Commite os arquivos gerados no Git
2. Configure os secrets no GitHub/Azure DevOps
3. Crie os workflows de CI/CD
4. Conecte os outros workspaces (STG, PRD) as respectivas branches
""")
```

---

> **Dica final**: A documentacao oficial do PyFabricOps esta em https://pyfabricops.readthedocs.io/en/latest/ e e gerada automaticamente a partir dos docstrings do codigo. Consulte-a para detalhes atualizados de cada funcao.
