# Case Real: CI/CD Completo com PyFabricOps + Azure DevOps

> **Cenario**: Empresa "Contoso Analytics" precisa implementar CI/CD para um projeto de dados no Microsoft Fabric com 3 ambientes (DEV, STG, PRD), versionamento Git via Azure DevOps, parametrizacao por ambiente e deploy automatizado.

---

## Indice

1. [Visao Geral do Case](#1-visao-geral-do-case)
2. [Arquitetura da Solucao](#2-arquitetura-da-solucao)
3. [Pre-requisitos Detalhados](#3-pre-requisitos-detalhados)
4. [Passo 1 - Configurar Azure AD (Entra ID)](#4-passo-1---configurar-azure-ad-entra-id)
5. [Passo 2 - Configurar o Fabric Admin Portal](#5-passo-2---configurar-o-fabric-admin-portal)
6. [Passo 3 - Criar o Repositorio no Azure DevOps](#6-passo-3---criar-o-repositorio-no-azure-devops)
7. [Passo 4 - Preparar o Projeto Local](#7-passo-4---preparar-o-projeto-local)
8. [Passo 5 - Criar Workspaces no Fabric](#8-passo-5---criar-workspaces-no-fabric)
9. [Passo 6 - Criar Conexoes (ADO + Dados)](#9-passo-6---criar-conexoes-ado--dados)
10. [Passo 7 - Conectar Workspaces ao Azure DevOps](#10-passo-7---conectar-workspaces-ao-azure-devops)
11. [Passo 8 - Exportar Objetos e Parametrizar](#11-passo-8---exportar-objetos-e-parametrizar)
12. [Passo 9 - Entendendo Variaveis e Parametros por Tipo de Objeto](#12-passo-9---entendendo-variaveis-e-parametros-por-tipo-de-objeto)
13. [Passo 10 - Criar os Arquivos de Configuracao por Ambiente](#13-passo-10---criar-os-arquivos-de-configuracao-por-ambiente)
14. [Passo 11 - Scripts de Deploy com Substituicao de Parametros](#14-passo-11---scripts-de-deploy-com-substituicao-de-parametros)
15. [Passo 12 - Pipelines Azure DevOps (YAML)](#15-passo-12---pipelines-azure-devops-yaml)
16. [Passo 13 - Deployment Pipelines do Fabric (Opcional)](#16-passo-13---deployment-pipelines-do-fabric-opcional)
17. [Passo 14 - Bind de Conexoes e Refresh Pos-Deploy](#17-passo-14---bind-de-conexoes-e-refresh-pos-deploy)
18. [Passo 15 - Validacao e Testes](#18-passo-15---validacao-e-testes)
19. [O Que Voce Pode Estar Esquecendo](#19-o-que-voce-pode-estar-esquecendo)
20. [Mapa Completo: Onde Cada Tipo de Variavel Faz Sentido](#20-mapa-completo-onde-cada-tipo-de-variavel-faz-sentido)
21. [Troubleshooting Avancado](#21-troubleshooting-avancado)

---

## 1. Visao Geral do Case

### O Projeto

A Contoso Analytics tem um projeto de dados no Microsoft Fabric composto por:

| Objeto | Nome | Descricao |
|--------|------|-----------|
| **Lakehouse** | `lkh_vendas` | Armazena dados brutos e curados de vendas |
| **Notebook** | `nb_ingestao` | Ingesta dados da fonte SQL para o Lakehouse |
| **Notebook** | `nb_transformacao` | Transforma dados brutos em curados |
| **Data Pipeline** | `pl_etl_vendas` | Orquestra a ingestao completa |
| **Dataflow Gen2** | `df_dimensoes` | Carrega dimensoes para o Lakehouse |
| **Semantic Model** | `sm_vendas` | Modelo semantico Power BI (Import) |
| **Report** | `rpt_dashboard_vendas` | Dashboard de vendas |

### O Problema

- Tudo e desenvolvido direto em producao
- Nao ha versionamento
- Nenhum controle de quem alterou o que
- Parametros (servidor SQL, IDs de workspace/lakehouse) estao hardcoded
- Deploy manual propenso a erros

### A Solucao

Implementar CI/CD com 3 ambientes, versionamento Git via Azure DevOps, parametrizacao por ambiente e deploy automatizado usando PyFabricOps.

---

## 2. Arquitetura da Solucao

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AZURE DEVOPS                                  │
│                                                                      │
│  Repo: contoso-fabric                                                │
│  ┌─────────┐    PR     ┌──────────┐    PR     ┌─────────┐           │
│  │   dev    │ ───────► │ staging  │ ───────► │  main   │           │
│  └────┬────┘           └────┬─────┘           └────┬────┘           │
│       │                     │                      │                 │
│  ┌────▼────────────┐  ┌────▼────────────┐  ┌─────▼───────────┐     │
│  │ pipeline-dev.yml│  │pipeline-stg.yml │  │pipeline-prd.yml │     │
│  └────┬────────────┘  └────┬────────────┘  └─────┬───────────┘     │
└───────┼────────────────────┼─────────────────────┼───────────────────┘
        │                    │                     │
        ▼                    ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ FABRIC DEV   │    │ FABRIC STG   │    │ FABRIC PRD   │
│              │    │              │    │              │
│ Contoso-DEV  │    │ Contoso-STG  │    │ Contoso-PRD  │
│ Capacity: F2 │    │ Capacity: F4 │    │ Capacity: F8 │
│              │    │              │    │              │
│ SQL: dev-srv │    │ SQL: stg-srv │    │ SQL: prd-srv │
│ LKH: lkh-dev│    │ LKH: lkh-stg│    │ LKH: lkh-prd│
└──────────────┘    └──────────────┘    └──────────────┘
```

### Fluxo

1. Desenvolvedor trabalha no workspace **Contoso-DEV** (branch `dev`)
2. Altera objetos, testa, faz commit para Git
3. Cria PR de `dev` → `staging` → Pipeline ADO faz deploy em **Contoso-STG**
4. Apos validacao, PR de `staging` → `main` → Pipeline ADO faz deploy em **Contoso-PRD**
5. Parametros sao substituidos automaticamente por ambiente

---

## 3. Pre-requisitos Detalhados

### Azure / Entra ID
- [ ] Tenant Azure com licenca Microsoft Fabric (F2+ ou P1+ ou Trial)
- [ ] Permissao para criar App Registration no Entra ID
- [ ] Permissao de Global Admin ou Fabric Admin para configurar tenant settings

### Azure DevOps
- [ ] Organizacao Azure DevOps criada
- [ ] Projeto criado dentro da organizacao
- [ ] Repositorio Git inicializado
- [ ] Permissao para criar Service Connections e Pipelines

### Maquina Local
- [ ] Python 3.10+ instalado
- [ ] Git instalado e configurado
- [ ] Acesso ao Azure DevOps via CLI (`az devops`)

### Instalacao

```bash
# Instalar pyfabricops
pip install pyfabricops

# Ou com todas as dependencias opcionais
pip install pyfabricops[all]

# Verificar
python -c "import pyfabricops as pf; print(pf.__version__)"
```

---

## 4. Passo 1 - Configurar Azure AD (Entra ID)

### 4.1 Criar App Registration

1. Acesse portal.azure.com > Microsoft Entra ID > App registrations
2. Clique "New registration"
3. Preencha:
   - **Name**: `contoso-fabric-cicd`
   - **Supported account types**: Single tenant
   - **Redirect URI**: (deixe vazio)
4. Clique "Register"
5. **Anote**:
   - `Application (client) ID` → sera seu `FAB_CLIENT_ID`
   - `Directory (tenant) ID` → sera seu `FAB_TENANT_ID`

### 4.2 Criar Client Secret

1. No App Registration, va em "Certificates & secrets"
2. Clique "New client secret"
3. Descricao: `fabric-cicd-secret`
4. Expiracao: 12 meses (ou conforme politica da empresa)
5. **Anote o Value** (so aparece uma vez) → sera seu `FAB_CLIENT_SECRET`

### 4.3 Adicionar Permissoes de API

1. Va em "API permissions" > "Add a permission"
2. Adicione:

**Power BI Service:**
- `Tenant.Read.All`
- `Tenant.ReadWrite.All`

**Microsoft Graph (se usar funcoes de resolucao de identidades):**
- `User.Read.All`
- `Group.Read.All`
- `Application.Read.All`

3. Clique "Grant admin consent for [Tenant]"

### 4.4 Criar Security Group (recomendado)

1. Entra ID > Groups > New group
2. **Name**: `SG-Fabric-CICD`
3. **Type**: Security
4. Adicione o App Registration `contoso-fabric-cicd` como membro
5. Esse grupo sera usado no Fabric Admin Portal

---

## 5. Passo 2 - Configurar o Fabric Admin Portal

Acesse `app.fabric.microsoft.com` > Settings (engrenagem) > Admin portal

### 5.1 Tenant Settings

Habilite as seguintes configuracoes (aplique ao grupo `SG-Fabric-CICD`):

| Setting | Localizacao | Valor |
|---------|-------------|-------|
| Service principals can use Fabric APIs | Tenant settings > Developer settings | Enabled para SG-Fabric-CICD |
| Service principals can access read-only admin APIs | Tenant settings > Admin API settings | Enabled para SG-Fabric-CICD |
| Users can create Fabric items | Tenant settings > Fabric settings | Enabled |
| Allow XMLA endpoints | Tenant settings > Integration settings | Enabled (se usar DMV) |
| Users can synchronize workspace items with their Git repositories | Tenant settings > Git integration | Enabled |

### 5.2 Importante

Apos habilitar as settings, **aguarde ate 15 minutos** para propagacao. Testes imediatos podem falhar com 401/403.

---

## 6. Passo 3 - Criar o Repositorio no Azure DevOps

### 6.1 Estrutura do Projeto ADO

```
Organization: contoso-analytics
Project:      fabric-vendas
Repository:   contoso-fabric
```

### 6.2 Criar branches

```bash
# Clonar repositorio
git clone https://dev.azure.com/contoso-analytics/fabric-vendas/_git/contoso-fabric
cd contoso-fabric

# Criar branch dev
git checkout -b dev
git push -u origin dev

# Criar branch staging
git checkout -b staging
git push -u origin staging

# Voltar para main
git checkout main
```

### 6.3 Configurar Variable Groups no Azure DevOps

Va em Pipelines > Library > + Variable group

**Grupo: `Fabric-Credentials`**

| Variavel | Valor | Secreta? |
|----------|-------|----------|
| `FAB_CLIENT_ID` | (seu client id) | Nao |
| `FAB_CLIENT_SECRET` | (seu client secret) | **Sim** |
| `FAB_TENANT_ID` | (seu tenant id) | Nao |

**Grupo: `Fabric-Config-DEV`**

| Variavel | Valor | Secreta? |
|----------|-------|----------|
| `WORKSPACE_NAME` | Contoso-DEV | Nao |
| `SQL_SERVER` | contoso-dev-sql.database.windows.net | Nao |
| `SQL_DATABASE` | contoso_dev | Nao |
| `SQL_USERNAME` | admin_dev | Nao |
| `SQL_PASSWORD` | (senha) | **Sim** |
| `LAKEHOUSE_ID` | (uuid do lakehouse DEV) | Nao |
| `WORKSPACE_ID` | (uuid do workspace DEV) | Nao |

**Grupo: `Fabric-Config-STG`** (mesma estrutura, valores de STG)

**Grupo: `Fabric-Config-PRD`** (mesma estrutura, valores de PRD)

> **Por que Variable Groups?** Permitem segregar credenciais por ambiente, controlar acesso por equipe, e sao nativos do Azure DevOps. Diferente de variaveis inline na pipeline, eles sao reutilizaveis e auditaveis.

---

## 7. Passo 4 - Preparar o Projeto Local

### 7.1 Gerar arquivos de suporte

```python
#!/usr/bin/env python3
"""scripts/01_setup_projeto.py - Executar UMA vez"""

import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO", format_style="standard")

# Gera: .env, branches.json, workspaces_roles.json,
#        connections_roles.json, .gitignore, .gitattributes, src/README.md
pf.create_support_files()

print("Arquivos de suporte criados!")
```

### 7.2 Configurar o `.env` local

```env
# .env (NAO commitar! Ja esta no .gitignore)
FAB_CLIENT_ID=12345678-abcd-1234-efgh-123456789012
FAB_CLIENT_SECRET=seu~secret~aqui
FAB_TENANT_ID=87654321-dcba-4321-hgfe-210987654321

# Credenciais de usuario (opcional, para credential_type="user")
FAB_USERNAME=admin@contoso.com
FAB_PASSWORD=SenhaSegura123!

# Credenciais de banco
DATABASE_USERNAME=admin_dev
DATABASE_PASSWORD=DbSenha123!
```

### 7.3 Editar `branches.json`

```json
{
    "main": "-PRD",
    "staging": "-STG",
    "dev": "-DEV"
}
```

### 7.4 Editar `workspaces_roles.json`

```json
[
    {
        "user_uuid": "uuid-do-service-principal-contoso-fabric-cicd",
        "user_type": "ServicePrincipal",
        "role": "Admin"
    },
    {
        "user_uuid": "uuid-do-grupo-engenheiros-dados",
        "user_type": "Group",
        "role": "Member"
    },
    {
        "user_uuid": "uuid-do-grupo-analistas",
        "user_type": "Group",
        "role": "Viewer"
    }
]
```

### 7.5 Criar `env_config/` - Configuracoes por ambiente

```
contoso-fabric/
├── env_config/
│   ├── dev.json
│   ├── stg.json
│   └── prd.json
```

**`env_config/dev.json`**:
```json
{
    "workspace_name": "Contoso-DEV",
    "sql_server": "contoso-dev-sql.database.windows.net",
    "sql_database": "contoso_dev",
    "lakehouse_id": "aaaaaaaa-bbbb-cccc-dddd-111111111111",
    "workspace_id": "11111111-2222-3333-4444-555555555555",
    "semantic_model_server": "powerbi://api.powerbi.com/v1.0/myorg/Contoso-DEV",
    "semantic_model_database": "sm_vendas",
    "notebook_params": {
        "nb_ingestao": {
            "source_server": "contoso-dev-sql.database.windows.net",
            "source_database": "contoso_dev",
            "target_lakehouse": "lkh_vendas",
            "load_mode": "full"
        },
        "nb_transformacao": {
            "lakehouse_name": "lkh_vendas",
            "output_schema": "curated",
            "debug_mode": true
        }
    },
    "data_pipeline_vars": {
        "pl_etl_vendas": {
            "source_database": "contoso_dev",
            "source_connection": "conn-sql-dev-uuid",
            "sink_workspace_id": "11111111-2222-3333-4444-555555555555",
            "sink_artifact_id": "aaaaaaaa-bbbb-cccc-dddd-111111111111"
        }
    },
    "dataflow_vars": {
        "df_dimensoes": {
            "workspaceId": "11111111-2222-3333-4444-555555555555",
            "lakehouseId": "aaaaaaaa-bbbb-cccc-dddd-111111111111"
        }
    },
    "semantic_model_params": {
        "sm_vendas": {
            "ServerEndpoint": "contoso-dev-sql.database.windows.net",
            "DatabaseId": "contoso_dev"
        }
    }
}
```

**`env_config/stg.json`** e **`env_config/prd.json`**: mesma estrutura, valores do ambiente correspondente.

### 7.6 Estrutura final do repositorio

```
contoso-fabric/
├── .azure-pipelines/
│   ├── templates/
│   │   └── deploy-template.yml
│   ├── pipeline-dev.yml
│   ├── pipeline-stg.yml
│   └── pipeline-prd.yml
├── scripts/
│   ├── 01_setup_projeto.py
│   ├── 02_setup_workspaces.py
│   ├── 03_setup_conexoes.py
│   ├── 04_conectar_ado.py
│   ├── 05_exportar_objetos.py
│   ├── 06_parametrizar.py
│   ├── deploy.py                  # Script principal de deploy
│   └── utils_deploy.py            # Funcoes utilitarias
├── env_config/
│   ├── dev.json
│   ├── stg.json
│   └── prd.json
├── src/                            # Definicoes Fabric exportadas
│   ├── lkh_vendas.Lakehouse/
│   ├── nb_ingestao.Notebook/
│   ├── nb_transformacao.Notebook/
│   ├── pl_etl_vendas.DataPipeline/
│   ├── df_dimensoes.Dataflow/
│   ├── sm_vendas.SemanticModel/
│   └── rpt_dashboard_vendas.Report/
├── .env                            # Local only (NAO commitar)
├── .gitignore
├── .gitattributes
├── branches.json
├── workspaces_roles.json
├── connections_roles.json
└── requirements.txt
```

**`requirements.txt`**:
```
pyfabricops>=0.5.4
```

---

## 8. Passo 5 - Criar Workspaces no Fabric

```python
#!/usr/bin/env python3
"""scripts/02_setup_workspaces.py"""

import json
import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

PROJECT = "Contoso"
CAPACITY = "ContosoCapacity"  # Nome da sua capacidade Fabric

# Ler branches.json
with open("branches.json") as f:
    branches = json.load(f)

# Ler roles
with open("workspaces_roles.json") as f:
    roles = json.load(f)

# Criar workspaces
for branch, suffix in branches.items():
    ws_name = f"{PROJECT}{suffix}"

    print(f"\n--- Criando workspace: {ws_name} ---")

    try:
        result = pf.create_workspace(
            display_name=ws_name,
            capacity=CAPACITY,
            description=f"Workspace {suffix.strip('-')} do projeto {PROJECT}"
        )
        print(f"  Workspace criado: {ws_name}")
    except Exception as e:
        print(f"  Workspace {ws_name} ja existe ou erro: {e}")

    # Atribuir roles
    for role_def in roles:
        try:
            pf.add_workspace_role_assignment(
                workspace=ws_name,
                user_uuid=role_def["user_uuid"],
                user_type=role_def["user_type"],
                role=role_def["role"]
            )
            print(f"  Role {role_def['role']} atribuida para {role_def['user_type']}")
        except Exception as e:
            print(f"  Role ja existente ou erro: {e}")

# Listar workspaces para confirmar
print("\n--- Workspaces criados ---")
ws = pf.list_workspaces(df=False)
for w in ws:
    if PROJECT in w["displayName"]:
        print(f"  {w['displayName']} -> {w['id']}")

print("\nAnote os UUIDs acima para preencher env_config/*.json")
```

---

## 9. Passo 6 - Criar Conexoes (ADO + Dados)

```python
#!/usr/bin/env python3
"""scripts/03_setup_conexoes.py"""

import os
import pyfabricops as pf
from dotenv import load_dotenv

load_dotenv()
pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

# ============================================================
# 1. CONEXAO AZURE DEVOPS (para integracao Git)
# ============================================================
print("--- Criando conexao Azure DevOps ---")
ado_conn = pf.create_azure_devops_connection_with_service_principal(
    display_name="ado-contoso-fabric",
    repository_url="https://dev.azure.com/contoso-analytics/fabric-vendas/_git/contoso-fabric",
    client_id=os.getenv("FAB_CLIENT_ID"),
    client_secret=os.getenv("FAB_CLIENT_SECRET"),
    tenant_id=os.getenv("FAB_TENANT_ID"),
    df=False
)
print(f"  Conexao ADO criada: {ado_conn}")
# ANOTE o connection ID retornado!

# ============================================================
# 2. CONEXAO SQL CLOUD (uma por ambiente)
# ============================================================
environments = {
    "DEV": {
        "server": "contoso-dev-sql.database.windows.net",
        "database": "contoso_dev",
    },
    "STG": {
        "server": "contoso-stg-sql.database.windows.net",
        "database": "contoso_stg",
    },
    "PRD": {
        "server": "contoso-prd-sql.database.windows.net",
        "database": "contoso_prd",
    },
}

for env_name, config in environments.items():
    print(f"\n--- Criando conexao SQL {env_name} ---")
    try:
        conn = pf.create_sql_cloud_connection(
            display_name=f"conn-sql-{env_name.lower()}",
            server=config["server"],
            database=config["database"],
            username=os.getenv("DATABASE_USERNAME"),
            password=os.getenv("DATABASE_PASSWORD"),
            df=False
        )
        print(f"  Conexao criada: conn-sql-{env_name.lower()} -> {conn}")
    except Exception as e:
        print(f"  Erro ou ja existe: {e}")

    # Atribuir role ao Service Principal na conexao
    try:
        pf.add_connection_role_assignment(
            connection=f"conn-sql-{env_name.lower()}",
            user_uuid=os.getenv("FAB_CLIENT_ID"),
            user_type="ServicePrincipal",
            role="User"
        )
    except Exception as e:
        print(f"  Role ja atribuida: {e}")

# ============================================================
# 3. CONEXAO ADLS GEN2 (se necessario)
# ============================================================
# pf.create_adlsgen2_connection_with_service_principal_credentials(
#     display_name="conn-adls-contoso",
#     adls_endpoint="https://contosodatalake.dfs.core.windows.net",
#     client_id=os.getenv("FAB_CLIENT_ID"),
#     client_secret=os.getenv("FAB_CLIENT_SECRET"),
#     tenant_id=os.getenv("FAB_TENANT_ID"),
# )

print("\n--- Listando conexoes ---")
conns = pf.list_connections(df=False)
for c in conns:
    if "contoso" in c["displayName"].lower() or "ado" in c["displayName"].lower():
        print(f"  {c['displayName']} -> {c['id']}")

print("\nAnote os UUIDs das conexoes para env_config/*.json")
```

---

## 10. Passo 7 - Conectar Workspaces ao Azure DevOps

```python
#!/usr/bin/env python3
"""scripts/04_conectar_ado.py"""

import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

# UUID da conexao ADO criada no passo anterior
ADO_CONNECTION_ID = "uuid-da-conexao-ado-aqui"

# Configuracao por ambiente
ambientes = {
    "Contoso-DEV": {
        "branch": "dev",
        "directory": "src"
    },
    "Contoso-STG": {
        "branch": "staging",
        "directory": "src"
    },
    "Contoso-PRD": {
        "branch": "main",
        "directory": "src"
    },
}

for ws_name, config in ambientes.items():
    print(f"\n--- Conectando {ws_name} ao ADO (branch: {config['branch']}) ---")

    try:
        result = pf.ado_connect(
            workspace=ws_name,
            connection_id=ADO_CONNECTION_ID,
            organization_name="contoso-analytics",
            project_name="fabric-vendas",
            repository_name="contoso-fabric",
            branch_name=config["branch"],
            directory_name=config["directory"],
        )
        print(f"  Conectado: {result}")

        # Inicializar Git no workspace
        print(f"  Inicializando Git...")
        pf.git_init(
            workspace=ws_name,
            initialize_strategy="PreferWorkspace"
        )
        print(f"  Git inicializado para {ws_name}")

    except Exception as e:
        print(f"  Erro: {e}")

# Verificar status
for ws_name in ambientes:
    print(f"\n--- Status Git: {ws_name} ---")
    status = pf.git_status(ws_name, df=False)
    if status:
        print(f"  Remote: {status.get('remoteCommitHash', 'N/A')}")
        print(f"  Head:   {status.get('workspaceHead', 'N/A')}")
```

---

## 11. Passo 8 - Exportar Objetos e Parametrizar

### 8.1 Exportar tudo do workspace DEV

```python
#!/usr/bin/env python3
"""scripts/05_exportar_objetos.py"""

import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

WORKSPACE = "Contoso-DEV"
EXPORT_PATH = "./src"

print(f"Exportando todos os objetos de {WORKSPACE} para {EXPORT_PATH}...")

# Exportar por tipo (ordem recomendada)
print("\n1. Lakehouses...")
pf.export_all_lakehouses(WORKSPACE, EXPORT_PATH)

print("\n2. Notebooks...")
pf.export_all_notebooks(WORKSPACE, EXPORT_PATH)

print("\n3. Data Pipelines...")
pf.export_all_data_pipelines(WORKSPACE, EXPORT_PATH)

print("\n4. Dataflows Gen2...")
pf.export_all_dataflows_gen2(WORKSPACE, EXPORT_PATH)

print("\n5. Semantic Models...")
pf.export_all_semantic_models(WORKSPACE, EXPORT_PATH)

print("\n6. Reports...")
pf.export_all_reports(WORKSPACE, EXPORT_PATH)

# Ou tudo de uma vez:
# pf.export_all_items(WORKSPACE, EXPORT_PATH)

print("\nExportacao concluida! Verifique a pasta src/")
```

### 8.2 Parametrizar os objetos exportados

```python
#!/usr/bin/env python3
"""scripts/06_parametrizar.py - Substituir valores reais por placeholders"""

import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

SRC = "./src"

# ============================================================
# 1. NOTEBOOKS - Extrair e parametrizar
# ============================================================
print("=== NOTEBOOKS ===")
for nb_name in ["nb_ingestao", "nb_transformacao"]:
    nb_path = f"{SRC}/{nb_name}.Notebook"
    print(f"\nProcessando: {nb_name}")

    # Extrair parametros atuais
    params = pf.extract_notebook_parameters(nb_path)
    print(f"  Parametros encontrados: {len(params)}")
    for p in params:
        print(f"    {p['variable_name']} = {p['variable_value']} ({p['parameter_type']})")

    # Substituir por placeholders: #{nb_ingestao_source_server}#
    pf.replace_notebook_parameters_with_placeholders(nb_path, params)
    print(f"  Placeholders aplicados!")

# ============================================================
# 2. SEMANTIC MODELS - Extrair e parametrizar
# ============================================================
print("\n=== SEMANTIC MODELS ===")
sm_path = f"{SRC}/sm_vendas.SemanticModel"
print(f"\nProcessando: sm_vendas")

# Extrair parametros TMDL (expressions.tmdl)
sm_params = pf.extract_tmdl_parameters_from_semantic_model(sm_path)
if sm_params:
    print(f"  Parametros encontrados:")
    for name, value in sm_params.items():
        print(f"    {name} = {value}")

    # Substituir por placeholders: #{ServerEndpoint}#, #{DatabaseId}#
    pf.replace_semantic_model_parameters_with_placeholders(sm_path)
    print(f"  Placeholders aplicados!")

# ============================================================
# 3. DATA PIPELINES - Extrair e parametrizar
# ============================================================
print("\n=== DATA PIPELINES ===")
pl_path = f"{SRC}/pl_etl_vendas.DataPipeline"
print(f"\nProcessando: pl_etl_vendas")

# Extrair variaveis (source_database, source_connection, sink_workspace_id, sink_artifact_id)
pl_vars = pf.extract_data_pipeline_variables(pl_path)
print(f"  Variaveis encontradas: {len(pl_vars)}")
for v in pl_vars:
    print(f"    Activity: {v['activity_name']} > {v['subactivity_name']}")
    print(f"      source_database: {v['source_database']}")
    print(f"      source_connection: {v['source_connection']}")
    print(f"      sink_workspace_id: {v['sink_workspace_id']}")
    print(f"      sink_artifact_id: {v['sink_artifact_id']}")

# Substituir por placeholders
pf.replace_data_pipeline_variables_with_placeholders(pl_path, pl_vars)
print(f"  Placeholders aplicados!")

# ============================================================
# 4. DATAFLOWS GEN2 - Extrair e parametrizar
# ============================================================
print("\n=== DATAFLOWS GEN2 ===")
df_path = f"{SRC}/df_dimensoes.Dataflow"
print(f"\nProcessando: df_dimensoes")

# Extrair variaveis (workspaceId, lakehouseId do mashup.pq)
df_vars = pf.extract_dataflow_gen2_variables(df_path)
print(f"  Destinos encontrados: {len(df_vars)}")
for v in df_vars:
    print(f"    Query: {v['query_name']} -> {v.get('destination_type', 'N/A')}")
    if 'workspaceId' in v:
        print(f"      workspaceId: {v['workspaceId']}")
    if 'lakehouseId' in v:
        print(f"      lakehouseId: {v['lakehouseId']}")

# Substituir por placeholders
pf.replace_dataflow_gen2_variables_with_placeholders(df_path, df_vars)
print(f"  Placeholders aplicados!")

print("\n=== PARAMETRIZACAO CONCLUIDA ===")
print("Agora os arquivos em src/ contem placeholders #{...}#")
print("No deploy, eles serao substituidos pelos valores do ambiente alvo.")
```

---

## 12. Passo 9 - Entendendo Variaveis e Parametros por Tipo de Objeto

### Mapa de onde cada tipo de variavel/parametro se aplica

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE VARIAVEIS                                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ VARIAVEIS DE AMBIENTE (.env / ADO Variable Groups / Secrets)       │  │
│  │                                                                     │  │
│  │ FAB_CLIENT_ID, FAB_CLIENT_SECRET, FAB_TENANT_ID                    │  │
│  │ DATABASE_USERNAME, DATABASE_PASSWORD                                │  │
│  │                                                                     │  │
│  │ QUANDO USAR: Credenciais, segredos, tokens                         │  │
│  │ ONDE: .env (local), Variable Groups (ADO), Secrets (GitHub)        │  │
│  │ NUNCA COMMITAR NO GIT                                              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ VARIAVEIS DE PIPELINE (ADO Pipeline Variables / Inline)            │  │
│  │                                                                     │  │
│  │ WORKSPACE_NAME, SQL_SERVER, ENVIRONMENT                            │  │
│  │                                                                     │  │
│  │ QUANDO USAR: Config que varia por execucao/ambiente                │  │
│  │ ONDE: azure-pipelines.yml (variables section) ou Variable Groups   │  │
│  │ PODE COMMITAR (se nao for secret)                                  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ PARAMETROS DE PIPELINE (ADO Pipeline Parameters)                   │  │
│  │                                                                     │  │
│  │ parameters:                                                         │  │
│  │   - name: environment                                               │  │
│  │     type: string                                                    │  │
│  │     values: [dev, stg, prd]                                         │  │
│  │                                                                     │  │
│  │ QUANDO USAR: Escolhas do usuario no trigger manual                 │  │
│  │ ONDE: Pipeline YAML (parameters section)                            │  │
│  │ Disponiveis via ${{ parameters.environment }}                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ PLACEHOLDERS PYFABRICOPS (Dentro das definicoes dos objetos)       │  │
│  │                                                                     │  │
│  │ Formato: #{NomeObjeto_NomeParametro}#                              │  │
│  │                                                                     │  │
│  │ NOTEBOOKS (notebook-content.py):                                    │  │
│  │   source_server = "#{nb_ingestao_source_server}#"                  │  │
│  │                                                                     │  │
│  │ SEMANTIC MODELS (expressions.tmdl):                                 │  │
│  │   expression ServerEndpoint = "#{ServerEndpoint}#"                  │  │
│  │   Sql.Database("#{ServerEndpoint}#", "#{DatabaseId}#")             │  │
│  │                                                                     │  │
│  │ DATA PIPELINES (pipeline-content.json):                             │  │
│  │   "database": "#{ForEach_CopyData_source_database}#"              │  │
│  │   "workspaceId": "#{ForEach_CopyData_sink_workspace_id}#"         │  │
│  │                                                                     │  │
│  │ DATAFLOWS GEN2 (mashup.pq):                                        │  │
│  │   workspaceId = "#{df_dimensoes_Clientes_workspaceId}#"           │  │
│  │   lakehouseId = "#{df_dimensoes_Clientes_lakehouseId}#"           │  │
│  │                                                                     │  │
│  │ QUANDO USAR: IDs, servers, databases que mudam entre ambientes     │  │
│  │ ONDE: Dentro dos arquivos de definicao exportados no src/          │  │
│  │ COMMITAR COM PLACEHOLDERS (nunca com valores reais de PRD)         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ CONFIG POR AMBIENTE (env_config/*.json)                            │  │
│  │                                                                     │  │
│  │ Mapeamento: placeholder -> valor real por ambiente                 │  │
│  │                                                                     │  │
│  │ QUANDO USAR: Valores nao-secretos que variam por ambiente          │  │
│  │ ONDE: env_config/dev.json, env_config/stg.json, env_config/prd.json│  │
│  │ PODE COMMITAR (sem secrets)                                        │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ BRANCHES.JSON (Branch -> Workspace Suffix)                         │  │
│  │                                                                     │  │
│  │ { "main": "-PRD", "staging": "-STG", "dev": "-DEV" }              │  │
│  │                                                                     │  │
│  │ QUANDO USAR: Determinar workspace alvo automaticamente             │  │
│  │ ONDE: Raiz do repositorio                                          │  │
│  │ COMMITAR                                                           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Tabela resumo: onde cada tipo faz sentido

| Tipo de Variavel | Onde Armazenar | Exemplo | Commitar? |
|------------------|----------------|---------|-----------|
| **Credenciais** | .env + ADO Variable Groups (secret) | FAB_CLIENT_SECRET, DATABASE_PASSWORD | NUNCA |
| **IDs de Tenant/App** | .env + ADO Variable Groups | FAB_CLIENT_ID, FAB_TENANT_ID | Apenas ID (sem secret) |
| **Workspace/Lakehouse IDs** | env_config/*.json | workspace_id, lakehouse_id por ambiente | Sim |
| **Servidores/Databases** | env_config/*.json | sql_server, sql_database por ambiente | Sim |
| **Placeholders em objetos** | src/**/* (arquivos exportados) | `#{nb_ingestao_source_server}#` | Sim (com placeholder) |
| **Branch mapping** | branches.json | `{"main": "-PRD"}` | Sim |
| **Workspace roles** | workspaces_roles.json | UUIDs de usuarios/grupos | Sim |
| **Pipeline params** | .azure-pipelines/*.yml | environment, deploy_type | Sim |

---

## 13. Passo 10 - Criar os Arquivos de Configuracao por Ambiente

### `env_config/dev.json` (exemplo completo)

```json
{
    "workspace_name": "Contoso-DEV",
    "workspace_id": "11111111-2222-3333-4444-555555555555",

    "notebook_params": {
        "nb_ingestao": [
            {
                "variable_name": "source_server",
                "variable_value": "contoso-dev-sql.database.windows.net",
                "parameter_type": "string"
            },
            {
                "variable_name": "source_database",
                "variable_value": "contoso_dev",
                "parameter_type": "string"
            },
            {
                "variable_name": "target_lakehouse",
                "variable_value": "lkh_vendas",
                "parameter_type": "string"
            },
            {
                "variable_name": "load_mode",
                "variable_value": "full",
                "parameter_type": "string"
            }
        ],
        "nb_transformacao": [
            {
                "variable_name": "lakehouse_name",
                "variable_value": "lkh_vendas",
                "parameter_type": "string"
            },
            {
                "variable_name": "output_schema",
                "variable_value": "curated",
                "parameter_type": "string"
            },
            {
                "variable_name": "debug_mode",
                "variable_value": "True",
                "parameter_type": "boolean"
            }
        ]
    },

    "semantic_model_params": {
        "sm_vendas": {
            "ServerEndpoint": "contoso-dev-sql.database.windows.net",
            "DatabaseId": "contoso_dev"
        }
    },

    "data_pipeline_vars": {
        "pl_etl_vendas": [
            {
                "activity_index": 0,
                "activity_name": "ForEach",
                "subactivity_index": 0,
                "subactivity_name": "CopyData",
                "source_database": "contoso_dev",
                "source_connection": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "sink_name": "Lakehouse",
                "sink_workspace_id": "11111111-2222-3333-4444-555555555555",
                "sink_artifact_id": "aaaaaaaa-bbbb-cccc-dddd-111111111111"
            }
        ]
    },

    "dataflow_vars": {
        "df_dimensoes": [
            {
                "destination_name": "Clientes_DataDestination",
                "query_name": "Clientes",
                "workspaceId": "11111111-2222-3333-4444-555555555555",
                "lakehouseId": "aaaaaaaa-bbbb-cccc-dddd-111111111111",
                "destination_type": "Lakehouse"
            },
            {
                "destination_name": "Produtos_DataDestination",
                "query_name": "Produtos",
                "workspaceId": "11111111-2222-3333-4444-555555555555",
                "lakehouseId": "aaaaaaaa-bbbb-cccc-dddd-111111111111",
                "destination_type": "Lakehouse"
            }
        ]
    },

    "connection_bind": {
        "sm_vendas": {
            "connection_type": "SQL",
            "connection_path": "contoso-dev-sql.database.windows.net;contoso_dev",
            "connection_name": "conn-sql-dev"
        }
    }
}
```

---

## 14. Passo 11 - Scripts de Deploy com Substituicao de Parametros

### `scripts/utils_deploy.py` - Funcoes utilitarias

```python
"""scripts/utils_deploy.py - Funcoes compartilhadas de deploy"""

import json
import shutil
from pathlib import Path


def load_env_config(environment: str) -> dict:
    """Carrega configuracao do ambiente."""
    config_path = f"env_config/{environment}.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def copy_src_to_staging() -> str:
    """Copia src/ para _stg/ para nao alterar os originais."""
    stg_path = "./_stg/src"
    if Path(stg_path).exists():
        shutil.rmtree(stg_path)
    shutil.copytree("./src", stg_path)
    return stg_path
```

### `scripts/deploy.py` - Script principal

```python
#!/usr/bin/env python3
"""
scripts/deploy.py - Script de deploy principal
Uso: python scripts/deploy.py --env dev|stg|prd
"""

import argparse
import sys

import pyfabricops as pf

from utils_deploy import copy_src_to_staging, load_env_config

# ============================================================
# ARGUMENTOS
# ============================================================
parser = argparse.ArgumentParser(description="Deploy para Microsoft Fabric")
parser.add_argument("--env", required=True, choices=["dev", "stg", "prd"],
                    help="Ambiente alvo: dev, stg, prd")
parser.add_argument("--skip-sync", action="store_true",
                    help="Pular sincronizacao Git")
args = parser.parse_args()

# ============================================================
# CONFIGURACAO
# ============================================================
pf.set_auth_provider("env")
pf.setup_logging(level="INFO", format_style="standard")

config = load_env_config(args.env)
workspace = config["workspace_name"]

print(f"\n{'='*60}")
print(f"DEPLOY PARA: {workspace} (ambiente: {args.env})")
print(f"{'='*60}")

# ============================================================
# 1. COPIAR PARA STAGING (nao modificar originais)
# ============================================================
print("\n[1/6] Copiando src/ para staging...")
stg_path = copy_src_to_staging()

# ============================================================
# 2. SUBSTITUIR PLACEHOLDERS POR VALORES DO AMBIENTE
# ============================================================
print("\n[2/6] Substituindo placeholders...")

# --- Notebooks ---
if "notebook_params" in config:
    for nb_name, params in config["notebook_params"].items():
        nb_path = f"{stg_path}/{nb_name}.Notebook"
        print(f"  Notebook: {nb_name}")
        pf.replace_notebook_placeholders_with_parameters(nb_path, params)

# --- Semantic Models ---
if "semantic_model_params" in config:
    for sm_name, params in config["semantic_model_params"].items():
        sm_path = f"{stg_path}/{sm_name}.SemanticModel"
        print(f"  Semantic Model: {sm_name}")
        pf.replace_semantic_model_placeholders_with_parameters(sm_path, params)

# --- Data Pipelines ---
if "data_pipeline_vars" in config:
    for pl_name, vars_list in config["data_pipeline_vars"].items():
        pl_path = f"{stg_path}/{pl_name}.DataPipeline"
        print(f"  Data Pipeline: {pl_name}")
        pf.replace_data_pipeline_placeholders_with_variables(pl_path, vars_list)

# --- Dataflows Gen2 ---
if "dataflow_vars" in config:
    for df_name, vars_list in config["dataflow_vars"].items():
        df_path = f"{stg_path}/{df_name}.Dataflow"
        print(f"  Dataflow Gen2: {df_name}")
        pf.replace_dataflow_gen2_placeholders_with_parameters(df_path, vars_list)

# ============================================================
# 3. DEPLOY DOS OBJETOS
# ============================================================
print(f"\n[3/6] Fazendo deploy no workspace {workspace}...")

# Deploy na ordem correta de dependencias
print("  Deploying Lakehouses...")
pf.deploy_all_lakehouses(workspace, stg_path)

print("  Deploying Notebooks...")
pf.deploy_all_notebooks(workspace, stg_path)

print("  Deploying Data Pipelines...")
pf.deploy_all_data_pipelines(workspace, stg_path)

print("  Deploying Dataflows Gen2...")
pf.deploy_all_dataflows_gen2(workspace, stg_path)

print("  Deploying Semantic Models...")
pf.deploy_all_semantic_models(workspace, stg_path)

print("  Deploying Reports...")
pf.deploy_all_reports(workspace, stg_path)

# ============================================================
# 4. BIND DE CONEXOES
# ============================================================
print(f"\n[4/6] Vinculando conexoes...")

if "connection_bind" in config:
    for sm_name, bind_config in config["connection_bind"].items():
        print(f"  Binding {sm_name} -> {bind_config['connection_name']}")
        pf.bind_semantic_model_connection(
            workspace=workspace,
            semantic_model=sm_name,
            connection_type=bind_config["connection_type"],
            connection_path=bind_config["connection_path"],
            connection=bind_config["connection_name"],
        )

# ============================================================
# 5. REFRESH SEMANTIC MODEL (opcional)
# ============================================================
print(f"\n[5/6] Refresh do semantic model...")

if args.env in ["stg", "prd"]:
    for sm_name in config.get("semantic_model_params", {}):
        print(f"  Refreshing {sm_name}...")
        pf.refresh_semantic_model(
            workspace=workspace,
            semantic_model=sm_name,
            type="Full",
            notify_option="NoNotification",
        )

# ============================================================
# 6. SINCRONIZAR GIT (se nao pulado)
# ============================================================
if not args.skip_sync:
    print(f"\n[6/6] Sincronizando Git...")
    pf.update_from_git(
        workspace=workspace,
        conflict_resolution_policy="PreferRemote",
        allow_override_items=True,
    )
else:
    print(f"\n[6/6] Sincronizacao Git pulada (--skip-sync)")

print(f"\n{'='*60}")
print(f"DEPLOY CONCLUIDO COM SUCESSO: {workspace}")
print(f"{'='*60}")
```

---

## 15. Passo 12 - Pipelines Azure DevOps (YAML)

### Template reutilizavel

**`.azure-pipelines/templates/deploy-template.yml`**:

```yaml
parameters:
  - name: environment
    type: string
  - name: variableGroup
    type: string
  - name: skipSync
    type: boolean
    default: false

jobs:
  - job: Deploy_${{ parameters.environment }}
    displayName: "Deploy to ${{ parameters.environment }}"
    pool:
      vmImage: "ubuntu-latest"
    
    variables:
      - group: Fabric-Credentials
      - group: ${{ parameters.variableGroup }}
    
    steps:
      - checkout: self
        fetchDepth: 0

      - task: UsePythonVersion@0
        inputs:
          versionSpec: "3.13"
        displayName: "Setup Python"

      - script: pip install pyfabricops
        displayName: "Install pyfabricops"

      - script: |
          python scripts/deploy.py \
            --env ${{ parameters.environment }} \
            ${{ if eq(parameters.skipSync, true) }}:
              --skip-sync
        displayName: "Deploy to Fabric (${{ parameters.environment }})"
        env:
          FAB_CLIENT_ID: $(FAB_CLIENT_ID)
          FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
          FAB_TENANT_ID: $(FAB_TENANT_ID)

      - script: |
          python -c "
          import pyfabricops as pf
          pf.set_auth_provider('env')
          status = pf.git_status('$(WORKSPACE_NAME)', df=False)
          if status:
              print(f\"Remote: {status.get('remoteCommitHash', 'N/A')}\")
              print(f\"Head:   {status.get('workspaceHead', 'N/A')}\")
              if status.get('remoteCommitHash') == status.get('workspaceHead'):
                  print('Workspace sincronizado!')
              else:
                  print('AVISO: Workspace pode estar dessincronizado')
          "
        displayName: "Verify Git sync status"
        env:
          FAB_CLIENT_ID: $(FAB_CLIENT_ID)
          FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
          FAB_TENANT_ID: $(FAB_TENANT_ID)
```

### Pipeline DEV (trigger automatico)

**`.azure-pipelines/pipeline-dev.yml`**:

```yaml
trigger:
  branches:
    include:
      - dev
  paths:
    include:
      - src/**
      - env_config/dev.json
      - scripts/**

pr: none  # Nao rodar em PRs

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Deploy_DEV
    displayName: "Deploy to DEV"
    jobs:
      - template: templates/deploy-template.yml
        parameters:
          environment: dev
          variableGroup: Fabric-Config-DEV
```

### Pipeline STG (trigger em PR para staging)

**`.azure-pipelines/pipeline-stg.yml`**:

```yaml
trigger:
  branches:
    include:
      - staging
  paths:
    include:
      - src/**

pr: none

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Deploy_STG
    displayName: "Deploy to STG"
    jobs:
      - template: templates/deploy-template.yml
        parameters:
          environment: stg
          variableGroup: Fabric-Config-STG
```

### Pipeline PRD (manual com aprovacao)

**`.azure-pipelines/pipeline-prd.yml`**:

```yaml
trigger: none  # NUNCA trigger automatico em PRD
pr: none

parameters:
  - name: confirmDeploy
    displayName: "Confirma deploy para PRODUCAO?"
    type: boolean
    default: false
  - name: refreshModels
    displayName: "Executar refresh dos semantic models?"
    type: boolean
    default: true
  - name: deployNote
    displayName: "Nota do deploy"
    type: string
    default: ""

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Validation
    displayName: "Pre-deploy Validation"
    jobs:
      - job: Validate
        steps:
          - script: |
              if [ "${{ parameters.confirmDeploy }}" != "True" ]; then
                echo "##vso[task.logissue type=error]Deploy NAO confirmado. Marque o checkbox."
                exit 1
              fi
              echo "Deploy confirmado. Nota: ${{ parameters.deployNote }}"
            displayName: "Validate confirmation"

  - stage: Deploy_PRD
    displayName: "Deploy to PRD"
    dependsOn: Validation
    condition: succeeded()
    jobs:
      - deployment: DeployProduction
        displayName: "Deploy Production"
        environment: "Fabric-Production"  # Requer aprovacao manual no ADO
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self
                  fetchDepth: 0

                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: "3.13"

                - script: pip install pyfabricops
                  displayName: "Install pyfabricops"

                - script: |
                    python scripts/deploy.py --env prd
                  displayName: "Deploy to Fabric PRD"
                  env:
                    FAB_CLIENT_ID: $(FAB_CLIENT_ID)
                    FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
                    FAB_TENANT_ID: $(FAB_TENANT_ID)
```

### Configurar Environments no Azure DevOps

1. Va em Pipelines > Environments
2. Crie `Fabric-Production`
3. Adicione **Approvals**: selecione os aprovadores
4. Adicione **Branch control**: somente `main`

---

## 16. Passo 13 - Deployment Pipelines do Fabric (Opcional)

Se preferir usar Deployment Pipelines nativas do Fabric alem (ou no lugar) do deploy via API:

```python
#!/usr/bin/env python3
"""scripts/setup_deployment_pipeline.py"""

import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

# Criar Deployment Pipeline
print("Criando Deployment Pipeline...")
pf.create_deployment_pipeline(
    display_name="Contoso Analytics - Pipeline",
    stages=[
        {"displayName": "Development",  "description": "Ambiente DEV", "isPublic": False},
        {"displayName": "Staging",      "description": "Ambiente STG", "isPublic": False},
        {"displayName": "Production",   "description": "Ambiente PRD", "isPublic": True},
    ],
    description="Pipeline de deploy do projeto Contoso Analytics"
)

# Atribuir workspaces aos estagios
print("\nAtribuindo workspaces...")
for stage, ws in [("Development", "Contoso-DEV"),
                   ("Staging", "Contoso-STG"),
                   ("Production", "Contoso-PRD")]:
    pf.assign_workspace_to_stage(
        workspace=ws,
        pipeline="Contoso Analytics - Pipeline",
        stage=stage
    )
    print(f"  {ws} -> {stage}")

# Promover conteudo (usar no ADO Pipeline como step adicional)
# pf.deploy_stage_content(
#     pipeline="Contoso Analytics - Pipeline",
#     source_stage="Development",
#     target_stage="Staging",
#     note="Automated deploy via ADO"
# )
```

### Adicionar step de promocao na pipeline ADO

```yaml
# Adicionar como step adicional no deploy-template.yml
- script: |
    python -c "
    import pyfabricops as pf
    pf.set_auth_provider('env')
    pf.deploy_stage_content(
        pipeline='Contoso Analytics - Pipeline',
        source_stage='${{ parameters.sourceStage }}',
        target_stage='${{ parameters.targetStage }}',
        note='ADO Build $(Build.BuildNumber) - $(Build.SourceVersionMessage)'
    )
    "
  displayName: "Promote via Deployment Pipeline"
  condition: and(succeeded(), eq('${{ parameters.useDeploymentPipeline }}', 'true'))
  env:
    FAB_CLIENT_ID: $(FAB_CLIENT_ID)
    FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
    FAB_TENANT_ID: $(FAB_TENANT_ID)
```

---

## 17. Passo 14 - Bind de Conexoes e Refresh Pos-Deploy

Apos o deploy, os semantic models precisam ser vinculados as conexoes do ambiente correto.

```python
"""Trecho do deploy.py - Bind e Refresh"""

# ============================================================
# BIND DE CONEXOES POS-DEPLOY
# ============================================================

# Vincular semantic model a conexao do ambiente
pf.bind_semantic_model_connection(
    workspace="Contoso-PRD",
    semantic_model="sm_vendas",
    connection_type="SQL",
    connection_path="contoso-prd-sql.database.windows.net;contoso_prd",
    connectivity_type="ShareableCloud",
    connection="conn-sql-prd",  # Nome da conexao criada no passo 6
)

# Opcionalmente, vincular a um gateway on-premises
# pf.bind_semantic_model_to_gateway(
#     workspace="Contoso-PRD",
#     semantic_model="sm_vendas",
#     gateway="GatewayOnPremises",
# )

# ============================================================
# REFRESH POS-DEPLOY
# ============================================================

# Refresh completo
pf.refresh_semantic_model(
    workspace="Contoso-PRD",
    semantic_model="sm_vendas",
    type="Full",
    notify_option="MailOnFailure",
    max_parallelism=3,
    retry_count=2,
    timeout="01:00:00",
)

# Verificar status do refresh
refreshes = pf.get_semantic_model_refreshes(
    workspace="Contoso-PRD",
    semantic_model="sm_vendas",
    top=1,
    df=False,
)
print(f"Ultimo refresh: {refreshes}")

# Refresh parcial (apenas tabelas especificas)
# pf.refresh_semantic_model(
#     workspace="Contoso-PRD",
#     semantic_model="sm_vendas",
#     type="Full",
#     objects=[
#         {"table": "FactVendas", "partition": "2024"},
#         {"table": "DimProdutos"},
#     ],
# )
```

---

## 18. Passo 15 - Validacao e Testes

### Script de validacao pos-deploy

```python
#!/usr/bin/env python3
"""scripts/validate_deploy.py - Validar deploy"""

import sys
import pyfabricops as pf

pf.set_auth_provider("env")
pf.setup_logging(level="INFO")

ENV = sys.argv[1] if len(sys.argv) > 1 else "dev"
from utils_deploy import load_env_config

config = load_env_config(ENV)
workspace = config["workspace_name"]

print(f"Validando deploy em {workspace}...")
errors = []

# 1. Verificar workspace existe
print("\n[1] Verificando workspace...")
ws = pf.list_workspaces(df=False)
ws_found = any(w["displayName"] == workspace for w in ws)
if not ws_found:
    errors.append(f"Workspace {workspace} nao encontrado!")
else:
    print(f"  OK: {workspace}")

# 2. Verificar itens existem
print("\n[2] Verificando itens...")
expected_items = [
    "lkh_vendas", "nb_ingestao", "nb_transformacao",
    "pl_etl_vendas", "sm_vendas", "rpt_dashboard_vendas"
]
items = pf.list_items(workspace, df=False)
if items:
    item_names = [i["displayName"] for i in items]
    for expected in expected_items:
        if expected in item_names:
            print(f"  OK: {expected}")
        else:
            errors.append(f"Item {expected} nao encontrado em {workspace}")
            print(f"  ERRO: {expected} nao encontrado")

# 3. Verificar status Git
print("\n[3] Verificando status Git...")
status = pf.git_status(workspace, df=False)
if status:
    remote = status.get("remoteCommitHash")
    head = status.get("workspaceHead")
    if remote == head:
        print(f"  OK: Sincronizado ({remote[:8]}...)")
    else:
        errors.append(f"Git dessincronizado: remote={remote}, head={head}")
        print(f"  AVISO: Dessincronizado")

# 4. Verificar conexoes
print("\n[4] Verificando conexoes...")
conns = pf.list_connections(df=False)
expected_conn = f"conn-sql-{ENV}"
conn_found = any(c["displayName"] == expected_conn for c in conns)
if conn_found:
    print(f"  OK: {expected_conn}")
else:
    errors.append(f"Conexao {expected_conn} nao encontrada")

# 5. Executar query DAX para validar modelo
print("\n[5] Validando semantic model (query DAX)...")
try:
    result = pf.execute_queries(
        workspace=workspace,
        semantic_model="sm_vendas",
        query="EVALUATE ROW(\"test\", 1)",
        df=False,
    )
    if result:
        print("  OK: Semantic model respondendo a queries")
    else:
        errors.append("Semantic model nao respondeu a query DAX")
except Exception as e:
    errors.append(f"Erro na query DAX: {e}")

# Resultado
print(f"\n{'='*60}")
if errors:
    print(f"VALIDACAO FALHOU ({len(errors)} erros):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("VALIDACAO OK: Todos os checks passaram!")
    sys.exit(0)
```

### Adicionar validacao na pipeline ADO

```yaml
# Adicionar apos o deploy no template
- script: |
    python scripts/validate_deploy.py ${{ parameters.environment }}
  displayName: "Validate deployment"
  env:
    FAB_CLIENT_ID: $(FAB_CLIENT_ID)
    FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
    FAB_TENANT_ID: $(FAB_TENANT_ID)
```

---

## 19. O Que Voce Pode Estar Esquecendo

### Seguranca e Governanca

1. **Rotacao de secrets**: O `FAB_CLIENT_SECRET` expira. Configure alerta para renovacao e atualize nos Variable Groups do ADO
2. **Principio do menor privilegio**: O SPN so precisa de `Contributor` nos workspaces DEV/STG e `Viewer` em PRD (a menos que faca deploy)
3. **Audit trail**: Use `pf.list_deployment_pipeline_operations()` para rastrear deploys
4. **Network Security**: Se usar Private Endpoints no SQL/ADLS, o pipeline runner do ADO precisa de acesso (considere self-hosted agents)

### Objetos que requerem atencao especial

5. **Lakehouse shortcuts**: Use `pf.generate_lakehouse_shortcuts_metadata()` para recriar shortcuts entre ambientes - os IDs de workspace/artifact mudam
6. **Environments (Spark)**: Bibliotecas Python/R sao instaladas separadamente com `pf.add_environment_external_library_from_pypi()`. Inclua isso no deploy
7. **Variable Libraries**: Se usar Variable Libraries do Fabric, inclua `pf.deploy_variable_library()` no fluxo. Elas tem definicoes que tambem precisam de `get/update_variable_library_definition()`
8. **Reports PBIR**: Se o report aponta para semantic model por **byConnection** vs **byPath**, use `pf.convert_report_definition_to_by_path()` ou `pf.convert_report_definition_to_by_connection()` conforme necessario
9. **Dataflows Gen1**: Usam `model.json` serializado com formato especifico. Nao tem parametrizacao automatica como Gen2 - considere migrar para Gen2

### Operacional

10. **Rate limiting**: A API Fabric tem rate limits. Para workspaces com muitos objetos, adicione `time.sleep()` entre chamadas ou use `deploy_all_items()` (que ja tem tratamento interno)
11. **Long-Running Operations**: Operacoes de Git (init, update, commit) sao LRO. O PyFabricOps ja faz polling automatico (ate 10 retries, 5s cada), mas operacoes muito grandes podem precisar de mais tempo
12. **Ordem de deploy importa**: Lakehouses e Warehouses antes de Notebooks que os referenciam. Semantic Models antes de Reports. Data Pipelines por ultimo (referenciam tudo)
13. **`.gitattributes` com merge=union**: Ja configurado para `config.json` evitar conflitos de merge, mas revise se outros arquivos JSON precisam da mesma estrategia
14. **Backup antes de deploy em PRD**: Exporte o estado atual antes de aplicar novas alteracoes:
    ```python
    pf.export_all_items("Contoso-PRD", "./backup/pre-deploy")
    ```

### Azure DevOps Specifico

15. **Service Connection vs Variable Group**: Use Variable Groups para credenciais Fabric (mais flexivel). Service Connections sao para recursos Azure nativos
16. **Pipeline Environments com Gates**: Configure approval gates no Environment `Fabric-Production` para deploy em PRD
17. **Artifact staging**: O script ja copia para `_stg/` antes de modificar. Isso preserva os originais com placeholders no repositorio
18. **Branch policies**: Configure branch policies no ADO:
    - `main`: Requerer PR com pelo menos 1 aprovador
    - `staging`: Requerer PR de `dev` com build validation
    - `dev`: Permitir push direto (ou requerer PR de feature branches)

### Monitoramento e Observabilidade

19. **Logging em CI/CD**: Use `pf.setup_logging(level="DEBUG")` durante troubleshooting e `pf.setup_logging(level="WARNING")` em producao
20. **DMV queries para validacao**: Apos deploy de semantic models, execute DMV queries para validar schema:
    ```python
    # Verificar tabelas e particoes apos deploy
    tables = pf.dmv_fetch_tables_raw(conn_str)
    partitions = pf.dmv_fetch_partitions_enriched(conn_str)
    ```
21. **Microsoft Graph para notificacoes**: Use `pf.get_user_email()` para resolver UUIDs em notificacoes de deploy

---

## 20. Mapa Completo: Onde Cada Tipo de Variavel Faz Sentido

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  NOTEBOOK (notebook-content.py)                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ # PARAMETERS CELL ************************************************** │  │
│  │ source_server = "#{nb_ingestao_source_server}#"      ← PLACEHOLDER   │  │
│  │ source_database = "#{nb_ingestao_source_database}#"  ← PLACEHOLDER   │  │
│  │ load_mode = "#{nb_ingestao_load_mode}#"              ← PLACEHOLDER   │  │
│  │ debug_mode = "#{nb_ingestao_debug_mode}#"            ← PLACEHOLDER   │  │
│  │                                                                        │  │
│  │ # Estes NAO sao parametrizados (derivados):                           │  │
│  │ connection_str = f"Server={source_server};Database={source_database}"  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  Funcoes: extract_notebook_parameters()                                      │
│           replace_notebook_parameters_with_placeholders()                     │
│           replace_notebook_placeholders_with_parameters()                     │
│                                                                              │
│  SEMANTIC MODEL (definition/expressions.tmdl)                                │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ // Import Mode:                                                        │  │
│  │ expression ServerEndpoint = "#{ServerEndpoint}#"     ← PLACEHOLDER    │  │
│  │ expression DatabaseId = "#{DatabaseId}#"             ← PLACEHOLDER    │  │
│  │                                                                        │  │
│  │ // Direct Lake Mode:                                                   │  │
│  │ Sql.Database("#{ServerEndpoint}#", "#{DatabaseId}#") ← PLACEHOLDER    │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  Funcoes: extract_tmdl_parameters_from_semantic_model()                       │
│           replace_semantic_model_parameters_with_placeholders()                │
│           replace_semantic_model_placeholders_with_parameters()                │
│                                                                              │
│  DATA PIPELINE (pipeline-content.json)                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ "database": "#{ForEach_CopyData_source_database}#"   ← PLACEHOLDER   │  │
│  │ "connection": "#{ForEach_CopyData_source_connection}#"← PLACEHOLDER   │  │
│  │ "workspaceId": "#{ForEach_CopyData_sink_workspace_id}#" ← PLACEHOLDER│  │
│  │ "artifactId": "#{ForEach_CopyData_sink_artifact_id}#"← PLACEHOLDER   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  Funcoes: extract_data_pipeline_variables()                                   │
│           replace_data_pipeline_variables_with_placeholders()                  │
│           replace_data_pipeline_placeholders_with_variables()                  │
│                                                                              │
│  DATAFLOW GEN2 (mashup.pq)                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ shared Clientes_DataDestination = let                                  │  │
│  │   workspaceId = "#{df_dimensoes_Clientes_workspaceId}#" ← PLACEHOLDER│  │
│  │   lakehouseId = "#{df_dimensoes_Clientes_lakehouseId}#" ← PLACEHOLDER│  │
│  │ in ...                                                                 │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  Funcoes: extract_dataflow_gen2_variables()                                   │
│           replace_dataflow_gen2_variables_with_placeholders()                  │
│           replace_dataflow_gen2_placeholders_with_parameters()                 │
│                                                                              │
│  REPORT (definition.pbir)                                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Nao usa placeholders #{...}#. Usa bind por referencia:                │  │
│  │                                                                        │  │
│  │ byPath: aponta para SM por caminho relativo (mesmo workspace)         │  │
│  │ byConnection: aponta por connection string (cross-workspace)          │  │
│  │                                                                        │  │
│  │ No deploy, ajuste com:                                                │  │
│  │   convert_report_definition_to_by_path() - para mesmo workspace       │  │
│  │   convert_report_definition_to_by_connection() - para cross-workspace │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  VARIAVEIS DE AMBIENTE (nunca no Git)                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ .env (local)           | ADO Variable Groups (CI/CD)                  │  │
│  │                        |                                               │  │
│  │ FAB_CLIENT_ID=...      | FAB_CLIENT_ID = ...                          │  │
│  │ FAB_CLIENT_SECRET=...  | FAB_CLIENT_SECRET = ... (secret)             │  │
│  │ FAB_TENANT_ID=...      | FAB_TENANT_ID = ...                          │  │
│  │ DATABASE_USERNAME=...  | DATABASE_PASSWORD = ... (secret)             │  │
│  │ DATABASE_PASSWORD=...  |                                               │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  VARIAVEIS/PARAMETROS DE PIPELINE ADO                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ variables:                  | parameters:                              │  │
│  │   - group: Fabric-Creds    |   - name: environment                    │  │
│  │   - group: Fabric-Config-X |     type: string                         │  │
│  │   - name: CUSTOM_VAR       |     values: [dev, stg, prd]              │  │
│  │     value: "inline"        |   - name: confirmDeploy                  │  │
│  │                             |     type: boolean                        │  │
│  │ Uso: $(VARIABLE_NAME)      | Uso: ${{ parameters.name }}              │  │
│  │ Quando: Valores fixos por  | Quando: Escolhas do usuario              │  │
│  │ pipeline/ambiente          | em execucao manual                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 21. Troubleshooting Avancado

### Erro: 401 Unauthorized

```
AuthenticationError: Token request failed: 401
```

**Causas e solucoes**:
1. Client Secret expirado → Renovar no Entra ID e atualizar Variable Group
2. Tenant Settings nao propagaram → Aguardar 15 min apos habilitar
3. SPN nao tem role no workspace → Executar `add_workspace_role_assignment()`
4. Permissoes de API nao concedidas → Verificar Admin Consent no Entra ID

### Erro: 403 Forbidden

```
RequestError: 403 - Caller does not have permissions
```

**Causas e solucoes**:
1. SPN precisa ser Admin no workspace para operacoes Git
2. "Service principals can use Fabric APIs" nao habilitado
3. SPN nao esta no Security Group habilitado no Tenant Settings

### Erro: Git status retorna None

```python
status = pf.git_status("MeuWorkspace", df=False)
# Returns None
```

**Causas**:
1. Workspace nao esta conectado ao Git → Executar `ado_connect()` + `git_init()`
2. Conexao ADO expirou → Verificar com `get_git_connection()`
3. Branch nao existe no repositorio → Criar branch no ADO primeiro

### Erro: Placeholder nao substituido

Se apos deploy um objeto contem `#{...}#`:

1. Verifique se o `env_config/*.json` tem a chave correta
2. Verifique se a copia para staging (`_stg/`) esta funcionando
3. Verifique a ordem: copiar → substituir → deploy (nao o contrario)
4. Use `pf.enable_debug_mode()` para ver detalhes da substituicao

### Erro: Deploy falha com "Item already exists"

O PyFabricOps automaticamente detecta se o item existe (update) ou nao (create). Se falhar:

1. Verifique se o item no workspace tem o mesmo nome + tipo
2. Lembre que o `.platform` file contem o `displayName` - verifique consistencia
3. Se renomeou um item, delete o antigo primeiro

### Dica: Debug completo

```python
pf.setup_logging(level="DEBUG", format_style="detailed")
pf.enable_debug_mode(include_external=True)
# Agora todas as chamadas HTTP sao logadas (headers redacted)
```

---

## Checklist Final

- [ ] App Registration criado no Entra ID com Client ID/Secret/Tenant ID
- [ ] API Permissions concedidas com Admin Consent
- [ ] Security Group criado e SPN adicionado
- [ ] Tenant Settings habilitadas no Fabric Admin Portal (esperar 15 min)
- [ ] Repositorio ADO criado com branches dev/staging/main
- [ ] Variable Groups criados no ADO (Credentials + Config por ambiente)
- [ ] Workspaces DEV/STG/PRD criados no Fabric com roles atribuidas
- [ ] Conexao ADO criada com `create_azure_devops_connection_with_service_principal()`
- [ ] Conexoes SQL criadas por ambiente
- [ ] Workspaces conectados ao ADO com `ado_connect()` + `git_init()`
- [ ] Objetos exportados do DEV com `export_all_*`
- [ ] Parametros extraidos e substituidos por placeholders
- [ ] Arquivos `env_config/*.json` preenchidos com valores de cada ambiente
- [ ] Script `deploy.py` testado localmente com `--env dev`
- [ ] Pipelines YAML criadas no ADO (dev auto, stg auto, prd manual)
- [ ] Environment `Fabric-Production` com approval gates
- [ ] Branch policies configuradas no ADO
- [ ] Script de validacao testado
- [ ] Backup do estado atual de PRD antes do primeiro deploy automatizado
