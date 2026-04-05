# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Notebook de Setup: Ambiente CI/CD no Microsoft Fabric
#
# **Objetivo**: Este notebook cria toda a infraestrutura necessaria para CI/CD no Microsoft Fabric.
#
# **O que ele faz**:
# 1. Instala o pyfabricops
# 2. Cria os workspaces (DEV, STG, PRD)
# 3. Cria os Fabric Environments com bibliotecas Python
# 4. Cria as Variable Libraries com parametros por ambiente
# 5. Atribui roles de seguranca
# 6. Cria conexao com Azure DevOps
# 7. Conecta workspaces ao repositorio Git
# 8. Gera os YAML de pipelines para Azure DevOps
#
# **Pre-requisitos** (leia a documentacao antes de executar):
# - App Registration criado no Entra ID
# - Tenant settings habilitadas no Fabric Admin Portal
# - Repositorio criado no Azure DevOps
# - Personal Access Token (PAT) do Azure DevOps

# CELL ********************

# ============================================================
# CELULA 1 - INSTALACAO
# ============================================================
# Instala a biblioteca pyfabricops no ambiente do notebook.
# Isso e necessario porque o Fabric nao vem com ela pre-instalada.

%pip install pyfabricops --quiet

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# PARAMETERS CELL ********************

# ============================================================
# CELULA 2 - PARAMETROS DE CONFIGURACAO
# ============================================================
# IMPORTANTE: Preencha TODOS os parametros abaixo antes de executar.
# Esses valores definem o nome do projeto, credenciais e configuracoes.
#
# DICA DE SEGURANCA: Nunca deixe secrets hardcoded em notebooks de producao.
# Aqui usamos para setup inicial. Depois, use Variable Groups no ADO.

# --- IDENTIFICACAO DO PROJETO ---
# Nome base do projeto. Os workspaces serao criados como:
#   MeuProjeto-DEV, MeuProjeto-STG, MeuProjeto-PRD
project_name = "MeuProjeto"

# Nome da capacidade Fabric onde os workspaces serao criados
# Encontre em: Fabric Portal > Settings > Admin Portal > Capacity settings
capacity_name = "MinhaCapacidadeFabric"

# --- CREDENCIAIS DO SERVICE PRINCIPAL ---
# Obtenha no Azure Portal > Entra ID > App registrations
fab_client_id = "00000000-0000-0000-0000-000000000000"
fab_client_secret = "seu-client-secret-aqui"
fab_tenant_id = "00000000-0000-0000-0000-000000000000"

# --- AZURE DEVOPS ---
# Organizacao: o nome que aparece em dev.azure.com/NOME-AQUI
ado_organization = "minha-organizacao"

# Projeto: o nome do projeto dentro da organizacao
ado_project = "meu-projeto-fabric"

# Repositorio: o nome do repositorio Git
ado_repository = "fabric-cicd"

# PAT (Personal Access Token) do Azure DevOps
# Crie em: Azure DevOps > User Settings > Personal Access Tokens
# Permissoes necessarias: Code (Read & Write), Build (Read & Execute)
ado_pat = "seu-pat-token-aqui"

# --- SEGURANCA: UUIDs DE USUARIOS/GRUPOS ---
# UUID do Service Principal (mesmo valor de fab_client_id na maioria dos casos)
spn_uuid = "00000000-0000-0000-0000-000000000000"

# UUID do grupo de seguranca dos engenheiros de dados (opcional)
# Deixe vazio "" se nao quiser atribuir
grupo_engenheiros_uuid = ""

# UUID do grupo de seguranca dos analistas/viewers (opcional)
grupo_analistas_uuid = ""

# --- BIBLIOTECAS PYTHON PARA O ENVIRONMENT ---
# Lista de tuplas (nome, versao) que serao instaladas no Fabric Environment
python_libraries = [
    ("pyfabricops", "0.5.4"),
    ("python-dotenv", "1.1.1"),
]

# --- CONFIGURACAO DE AMBIENTES (servidores, databases, etc) ---
# Preencha com os valores reais do seu projeto
config_dev = {
    "sql_server": "meuserver-dev.database.windows.net",
    "sql_database": "meubanco_dev",
    "adls_endpoint": "https://meudatalake-dev.dfs.core.windows.net",
}

config_stg = {
    "sql_server": "meuserver-stg.database.windows.net",
    "sql_database": "meubanco_stg",
    "adls_endpoint": "https://meudatalake-stg.dfs.core.windows.net",
}

config_prd = {
    "sql_server": "meuserver-prd.database.windows.net",
    "sql_database": "meubanco_prd",
    "adls_endpoint": "https://meudatalake-prd.dfs.core.windows.net",
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ============================================================
# CELULA 3 - CONFIGURACAO INICIAL
# ============================================================
# Importa a biblioteca e configura a autenticacao.
# Como estamos dentro de um notebook Fabric, usamos o metodo "fabric"
# que aproveita o token do usuario ja autenticado.

import pyfabricops as pf
import json
import base64
import time
import requests

# Autenticacao usando o token do notebook Fabric
# Isso significa que nao precisamos de usuario/senha aqui -
# o Fabric usa o token da sessao do usuario logado
pf.set_auth_provider("fabric")

# Configurar logging para ver o que esta acontecendo
# "INFO" mostra as operacoes principais sem poluir com detalhes
pf.setup_logging(level="INFO", format_style="standard")

print("pyfabricops configurado com sucesso!")
print(f"Versao: {pf.__version__}")
print(f"Projeto: {project_name}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 1: Criar Workspaces
#
# Workspaces sao os "containers" do Fabric. Cada ambiente (DEV, STG, PRD) tera seu proprio workspace.
#
# **Por que 3 workspaces?**
# - **DEV**: Onde desenvolvedores trabalham livremente, testam coisas novas
# - **STG (Staging)**: Onde testamos se tudo funciona antes de ir para producao
# - **PRD (Producao)**: O ambiente real que os usuarios finais acessam

# CELL ********************

# ============================================================
# CELULA 4 - CRIAR WORKSPACES
# ============================================================

# Definicao dos ambientes
# Cada entrada tem: sufixo do workspace, branch Git correspondente, descricao
ambientes = {
    "DEV": {
        "suffix": "-DEV",
        "branch": "dev",
        "description": "Ambiente de DESENVOLVIMENTO - Para testes e experimentacao"
    },
    "STG": {
        "suffix": "-STG",
        "branch": "staging",
        "description": "Ambiente de HOMOLOGACAO - Para validacao antes de producao"
    },
    "PRD": {
        "suffix": "-PRD",
        "branch": "main",
        "description": "Ambiente de PRODUCAO - Somente deploys aprovados"
    },
}

# Dicionario para guardar os IDs dos workspaces criados
# Vamos precisar desses IDs nos passos seguintes
workspace_ids = {}

print("=" * 60)
print("ETAPA 1: CRIACAO DE WORKSPACES")
print("=" * 60)

for env_name, env_config in ambientes.items():
    ws_name = f"{project_name}{env_config['suffix']}"
    print(f"\n--- Criando workspace: {ws_name} ---")

    try:
        result = pf.create_workspace(
            display_name=ws_name,
            capacity=capacity_name,
            description=env_config["description"],
            df=False
        )
        workspace_ids[env_name] = result["id"]
        print(f"  CRIADO: {ws_name} -> ID: {result['id']}")
    except Exception as e:
        # Se ja existe, vamos buscar o ID
        print(f"  AVISO: {e}")
        print(f"  Tentando buscar workspace existente...")
        try:
            ws_list = pf.list_workspaces(df=False)
            for ws in ws_list:
                if ws["displayName"] == ws_name:
                    workspace_ids[env_name] = ws["id"]
                    print(f"  ENCONTRADO: {ws_name} -> ID: {ws['id']}")
                    break
        except Exception as e2:
            print(f"  ERRO: Nao foi possivel criar ou encontrar {ws_name}: {e2}")

print("\n--- Resumo dos Workspaces ---")
for env, ws_id in workspace_ids.items():
    print(f"  {project_name}-{env}: {ws_id}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 2: Atribuir Roles de Seguranca
#
# Roles controlam quem pode fazer o que no workspace.
#
# | Role | Pode ver | Pode editar | Pode compartilhar | Controle total |
# |------|---------|-------------|-------------------|----------------|
# | Viewer | Sim | Nao | Nao | Nao |
# | Contributor | Sim | Sim | Nao | Nao |
# | Member | Sim | Sim | Sim | Nao |
# | Admin | Sim | Sim | Sim | Sim |
#
# **Regra de ouro**: O Service Principal precisa ser Admin para operacoes de Git e deploy.

# CELL ********************

# ============================================================
# CELULA 5 - ATRIBUIR ROLES DE SEGURANCA
# ============================================================

print("=" * 60)
print("ETAPA 2: ATRIBUICAO DE ROLES")
print("=" * 60)

for env_name, ws_id in workspace_ids.items():
    ws_name = f"{project_name}-{env_name}"
    print(f"\n--- Roles para: {ws_name} ---")

    # 1. Service Principal SEMPRE precisa ser Admin
    # Sem isso, o SPN nao consegue fazer deploy nem operacoes Git
    if spn_uuid and spn_uuid != "00000000-0000-0000-0000-000000000000":
        try:
            pf.add_workspace_role_assignment(
                workspace=ws_id,
                user_uuid=spn_uuid,
                user_type="ServicePrincipal",
                role="Admin"
            )
            print(f"  Admin -> Service Principal ({spn_uuid[:8]}...)")
        except Exception as e:
            print(f"  (SPN role ja existe ou erro: {e})")

    # 2. Grupo de engenheiros: Member em DEV/STG, Viewer em PRD
    if grupo_engenheiros_uuid:
        role = "Viewer" if env_name == "PRD" else "Member"
        try:
            pf.add_workspace_role_assignment(
                workspace=ws_id,
                user_uuid=grupo_engenheiros_uuid,
                user_type="Group",
                role=role
            )
            print(f"  {role} -> Engenheiros ({grupo_engenheiros_uuid[:8]}...)")
        except Exception as e:
            print(f"  (Engenheiros role ja existe ou erro: {e})")

    # 3. Grupo de analistas: Viewer em todos os ambientes
    if grupo_analistas_uuid:
        try:
            pf.add_workspace_role_assignment(
                workspace=ws_id,
                user_uuid=grupo_analistas_uuid,
                user_type="Group",
                role="Viewer"
            )
            print(f"  Viewer -> Analistas ({grupo_analistas_uuid[:8]}...)")
        except Exception as e:
            print(f"  (Analistas role ja existe ou erro: {e})")

print("\nRoles atribuidas!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 3: Criar Fabric Environments
#
# **O que e um Fabric Environment?**
# E um pacote de configuracoes para o Spark: quais bibliotecas Python estao instaladas,
# qual versao do runtime usar, quanta memoria o Spark tem, etc.
#
# Criamos um Environment em cada workspace para garantir que:
# - DEV pode ter bibliotecas experimentais
# - STG tem exatamente as mesmas bibliotecas que irao para PRD
# - PRD tem versoes fixas e testadas

# CELL ********************

# ============================================================
# CELULA 6 - CRIAR FABRIC ENVIRONMENTS
# ============================================================

print("=" * 60)
print("ETAPA 3: CRIACAO DE ENVIRONMENTS")
print("=" * 60)

environment_ids = {}

for env_name, ws_id in workspace_ids.items():
    ws_name = f"{project_name}-{env_name}"
    env_display_name = f"env_{project_name.lower()}"
    print(f"\n--- Criando Environment: {env_display_name} em {ws_name} ---")

    try:
        result = pf.create_environment(
            workspace=ws_id,
            display_name=env_display_name,
            description=f"Environment Python para o projeto {project_name} ({env_name})",
            df=False
        )
        environment_ids[env_name] = result["id"]
        print(f"  CRIADO: {env_display_name} -> ID: {result['id']}")
    except Exception as e:
        print(f"  AVISO: {e}")
        try:
            envs = pf.list_environments(ws_id, df=False)
            for env in envs:
                if env["displayName"] == env_display_name:
                    environment_ids[env_name] = env["id"]
                    print(f"  ENCONTRADO: {env_display_name} -> ID: {env['id']}")
                    break
        except Exception as e2:
            print(f"  ERRO: {e2}")

# Agora instalar bibliotecas Python em cada Environment
print("\n--- Instalando bibliotecas Python ---")
for env_name, ws_id in workspace_ids.items():
    env_display_name = f"env_{project_name.lower()}"
    print(f"\n  {project_name}-{env_name} / {env_display_name}:")
    print(f"    Bibliotecas: {python_libraries}")

    try:
        pf.add_environment_external_library_from_pypi(
            workspace=ws_id,
            environment=env_display_name,
            libraries=python_libraries,
        )
        print(f"    Bibliotecas adicionadas ao staging!")

        # Publicar o environment para aplicar as mudancas
        # Sem isso, as bibliotecas ficam em "staging" e nao sao usadas
        pf.publish_environment(
            workspace=ws_id,
            environment=env_display_name,
        )
        print(f"    Publish iniciado! (pode levar alguns minutos)")
    except Exception as e:
        print(f"    ERRO ao instalar bibliotecas: {e}")

print("\nEnvironments criados e configurados!")
print("NOTA: O publish pode levar 5-10 minutos para concluir.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 4: Criar Variable Libraries
#
# **O que e uma Variable Library?**
# E um objeto do Fabric que armazena variaveis (chave-valor) que podem ser
# usadas por notebooks e pipelines. Funciona como um "cofre de configuracoes".
#
# **Por que usar?**
# - Centraliza configuracoes que mudam entre ambientes (servidor SQL, IDs, etc.)
# - Evita hardcode de valores dentro dos notebooks
# - Facilita o deploy: cada ambiente tem sua propria Variable Library
#
# **Estrutura do arquivo variables.json:**
# ```json
# {
#   "sql_server": { "type": "string", "value": "meuserver.database.windows.net" },
#   "sql_database": { "type": "string", "value": "meubanco" }
# }
# ```

# CELL ********************

# ============================================================
# CELULA 7 - CRIAR VARIABLE LIBRARIES
# ============================================================

print("=" * 60)
print("ETAPA 4: CRIACAO DE VARIABLE LIBRARIES")
print("=" * 60)

# Mapeamento de ambiente -> configuracao
configs_por_ambiente = {
    "DEV": config_dev,
    "STG": config_stg,
    "PRD": config_prd,
}

variable_library_ids = {}

for env_name, ws_id in workspace_ids.items():
    ws_name = f"{project_name}-{env_name}"
    vl_name = f"vl_{project_name.lower()}"
    env_config = configs_por_ambiente[env_name]

    print(f"\n--- Variable Library: {vl_name} em {ws_name} ---")

    # Montar o conteudo da Variable Library
    # Cada variavel tem um tipo e um valor
    variables_content = {
        "type": "VariableLibrary",
        "variables": {
            "project_name": {
                "type": "string",
                "value": project_name
            },
            "environment": {
                "type": "string",
                "value": env_name
            },
            "sql_server": {
                "type": "string",
                "value": env_config.get("sql_server", "")
            },
            "sql_database": {
                "type": "string",
                "value": env_config.get("sql_database", "")
            },
            "adls_endpoint": {
                "type": "string",
                "value": env_config.get("adls_endpoint", "")
            },
            "workspace_id": {
                "type": "string",
                "value": ws_id
            },
        }
    }

    # Converter para o formato de definicao que a API espera
    # A API exige que o conteudo seja base64-encoded
    variables_json = json.dumps(variables_content, indent=2)
    variables_b64 = base64.b64encode(variables_json.encode("utf-8")).decode("utf-8")

    item_definition = {
        "parts": [
            {
                "path": "variables.json",
                "payload": variables_b64,
                "payloadType": "InlineBase64"
            }
        ]
    }

    try:
        result = pf.create_variable_library(
            workspace=ws_id,
            display_name=vl_name,
            item_definition=item_definition,
            description=f"Variaveis do projeto {project_name} para {env_name}",
            df=False
        )
        variable_library_ids[env_name] = result["id"]
        print(f"  CRIADA: {vl_name} -> ID: {result['id']}")
        print(f"  Variaveis:")
        for var_name, var_data in variables_content["variables"].items():
            # Mascarar valores sensiveis na saida
            value = var_data["value"]
            if len(value) > 20:
                value = value[:8] + "..." + value[-4:]
            print(f"    {var_name} = {value}")
    except Exception as e:
        print(f"  AVISO: {e}")
        try:
            vls = pf.list_variable_libraries(ws_id, df=False)
            for vl in vls:
                if vl["displayName"] == vl_name:
                    variable_library_ids[env_name] = vl["id"]
                    print(f"  ENCONTRADA: {vl_name} -> ID: {vl['id']}")
                    break
        except Exception as e2:
            print(f"  ERRO: {e2}")

print("\nVariable Libraries criadas!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 5: Criar Repositorio e Conexao Azure DevOps
#
# Agora vamos conectar o Fabric ao Azure DevOps para versionamento Git.
#
# **Fluxo de integracao:**
# ```
# Azure DevOps Repo          Fabric Workspaces
# ┌──────────────┐           ┌─────────────────┐
# │ branch: dev  │ ◄──────► │ MeuProjeto-DEV  │
# │ branch: stg  │ ◄──────► │ MeuProjeto-STG  │
# │ branch: main │ ◄──────► │ MeuProjeto-PRD  │
# └──────────────┘           └─────────────────┘
# ```
#
# **O que e uma "conexao" no Fabric?**
# E um objeto que armazena as credenciais de acesso a um servico externo
# (neste caso, o Azure DevOps). O Fabric usa essa conexao para ler/escrever no Git.

# CELL ********************

# ============================================================
# CELULA 8 - CRIAR REPOSITORIO NO AZURE DEVOPS (VIA API REST)
# ============================================================
# O Azure DevOps tem sua propria API REST.
# Usamos ela para criar o repositorio e as branches automaticamente.

print("=" * 60)
print("ETAPA 5: CONFIGURACAO DO AZURE DEVOPS")
print("=" * 60)

# Funcoes auxiliares para chamar a API do Azure DevOps
# Usamos o PAT (Personal Access Token) para autenticacao
def ado_api_request(method, url, payload=None):
    """Faz uma chamada a API do Azure DevOps."""
    # O PAT e enviado como Basic Auth (usuario vazio : token)
    auth = ("", ado_pat)
    headers = {"Content-Type": "application/json"}

    if method == "GET":
        resp = requests.get(url, auth=auth, headers=headers)
    elif method == "POST":
        resp = requests.post(url, auth=auth, headers=headers, json=payload)
    elif method == "PUT":
        resp = requests.put(url, auth=auth, headers=headers, json=payload)
    elif method == "PATCH":
        resp = requests.patch(url, auth=auth, headers=headers, json=payload)

    return resp

# URL base da API do Azure DevOps
ADO_BASE = f"https://dev.azure.com/{ado_organization}/{ado_project}/_apis"

# --- 5.1: Verificar/Criar o Repositorio ---
print("\n--- 5.1: Repositorio Git ---")
repo_url = f"{ADO_BASE}/git/repositories?api-version=7.1"
repos_resp = ado_api_request("GET", repo_url)

repo_id = None
if repos_resp.status_code == 200:
    repos = repos_resp.json().get("value", [])
    for repo in repos:
        if repo["name"] == ado_repository:
            repo_id = repo["id"]
            print(f"  Repositorio ja existe: {ado_repository} -> ID: {repo_id}")
            break

if not repo_id:
    print(f"  Criando repositorio: {ado_repository}")
    create_repo_resp = ado_api_request("POST", repo_url, {
        "name": ado_repository
    })
    if create_repo_resp.status_code in [200, 201]:
        repo_data = create_repo_resp.json()
        repo_id = repo_data["id"]
        print(f"  CRIADO: {ado_repository} -> ID: {repo_id}")
    else:
        print(f"  ERRO ao criar repo: {create_repo_resp.status_code} - {create_repo_resp.text}")

# --- 5.2: Inicializar repositorio com um commit inicial ---
print("\n--- 5.2: Commit inicial ---")
if repo_id:
    # Verificar se o repo ja tem commits
    refs_url = f"{ADO_BASE}/git/repositories/{repo_id}/refs?api-version=7.1"
    refs_resp = ado_api_request("GET", refs_url)
    refs = refs_resp.json().get("value", []) if refs_resp.status_code == 200 else []

    if not refs:
        print("  Repositorio vazio. Criando commit inicial...")

        # Criar arquivo README e branches.json no commit inicial
        branches_json_content = json.dumps({
            "main": "-PRD",
            "staging": "-STG",
            "dev": "-DEV"
        }, indent=4)

        gitignore_content = (
            "**/.pbi/localSettings.json\n"
            "**/.pbi/cache.abf\n"
            "**/__pycache__/**\n"
            "**/_stg/**\n"
            ".vscode/\n"
            ".venv\n"
            ".env\n"
            "metadata/\n"
        )

        gitattributes_content = "src/**/config.json merge=union\n"

        readme_content = (
            f"# {project_name} - Fabric CI/CD\n\n"
            f"Repositorio de versionamento dos objetos Microsoft Fabric.\n\n"
            f"## Ambientes\n\n"
            f"| Branch | Workspace | Ambiente |\n"
            f"|--------|-----------|----------|\n"
            f"| `dev` | {project_name}-DEV | Desenvolvimento |\n"
            f"| `staging` | {project_name}-STG | Homologacao |\n"
            f"| `main` | {project_name}-PRD | Producao |\n"
        )

        push_url = f"{ADO_BASE}/git/repositories/{repo_id}/pushes?api-version=7.1"
        push_payload = {
            "refUpdates": [{"name": "refs/heads/main", "oldObjectId": "0" * 40}],
            "commits": [{
                "comment": "chore: Commit inicial - estrutura do projeto CI/CD",
                "changes": [
                    {"changeType": "add", "item": {"path": "/README.md"}, "newContent": {"content": readme_content, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/branches.json"}, "newContent": {"content": branches_json_content, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/.gitignore"}, "newContent": {"content": gitignore_content, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/.gitattributes"}, "newContent": {"content": gitattributes_content, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/src/README.md"}, "newContent": {"content": "# Definicoes Fabric\n\nDiretorio com objetos exportados do Fabric.\n", "contentType": "rawtext"}},
                ]
            }]
        }
        push_resp = ado_api_request("POST", push_url, push_payload)
        if push_resp.status_code in [200, 201]:
            print("  Commit inicial criado na branch main!")
        else:
            print(f"  ERRO no commit: {push_resp.status_code} - {push_resp.text}")
    else:
        print(f"  Repositorio ja tem {len(refs)} branch(es). Pulando commit inicial.")

# --- 5.3: Criar branches dev e staging ---
print("\n--- 5.3: Branches ---")
if repo_id:
    # Buscar o SHA da branch main para criar as outras a partir dela
    refs_url = f"{ADO_BASE}/git/repositories/{repo_id}/refs?filter=heads/main&api-version=7.1"
    refs_resp = ado_api_request("GET", refs_url)

    main_sha = None
    if refs_resp.status_code == 200:
        for ref in refs_resp.json().get("value", []):
            if ref["name"] == "refs/heads/main":
                main_sha = ref["objectId"]
                print(f"  Branch main encontrada: {main_sha[:8]}...")

    if main_sha:
        for branch_name in ["dev", "staging"]:
            # Verificar se ja existe
            check_url = f"{ADO_BASE}/git/repositories/{repo_id}/refs?filter=heads/{branch_name}&api-version=7.1"
            check_resp = ado_api_request("GET", check_url)
            exists = any(
                r["name"] == f"refs/heads/{branch_name}"
                for r in check_resp.json().get("value", [])
            ) if check_resp.status_code == 200 else False

            if exists:
                print(f"  Branch '{branch_name}' ja existe.")
            else:
                create_ref_url = f"{ADO_BASE}/git/repositories/{repo_id}/refs?api-version=7.1"
                create_ref_payload = [{
                    "name": f"refs/heads/{branch_name}",
                    "oldObjectId": "0" * 40,
                    "newObjectId": main_sha
                }]
                ref_resp = ado_api_request("POST", create_ref_url, create_ref_payload)
                if ref_resp.status_code == 200:
                    print(f"  Branch '{branch_name}' criada a partir de main!")
                else:
                    print(f"  ERRO ao criar branch '{branch_name}': {ref_resp.text}")

print("\nConfiguracoes do Azure DevOps concluidas!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 6: Criar Conexao ADO e Conectar Workspaces ao Git
#
# Agora que o repositorio existe com as branches, vamos:
# 1. Criar uma "conexao" do Fabric com o Azure DevOps
# 2. Conectar cada workspace a sua branch correspondente
# 3. Inicializar o Git em cada workspace
#
# **IMPORTANTE**: Esta etapa usa credenciais do Service Principal.
# Para isso, precisamos mudar temporariamente o auth provider para "env".

# CELL ********************

# ============================================================
# CELULA 9 - CONEXAO ADO E GIT
# ============================================================

print("=" * 60)
print("ETAPA 6: CONEXAO COM AZURE DEVOPS")
print("=" * 60)

# Precisamos mudar para autenticacao "env" porque a criacao de conexao
# exige credenciais do Service Principal (client_id + secret)
import os
os.environ["FAB_CLIENT_ID"] = fab_client_id
os.environ["FAB_CLIENT_SECRET"] = fab_client_secret
os.environ["FAB_TENANT_ID"] = fab_tenant_id
pf.set_auth_provider("env")

# --- 6.1: Criar conexao Azure DevOps no Fabric ---
print("\n--- 6.1: Conexao Azure DevOps ---")
ado_repo_url = f"https://dev.azure.com/{ado_organization}/{ado_project}/_git/{ado_repository}"
ado_connection_id = None

try:
    result = pf.create_azure_devops_connection_with_service_principal(
        display_name=f"ado-{project_name.lower()}-conn",
        repository_url=ado_repo_url,
        client_id=fab_client_id,
        client_secret=fab_client_secret,
        tenant_id=fab_tenant_id,
        df=False
    )
    ado_connection_id = result["id"]
    print(f"  CRIADA: ado-{project_name.lower()}-conn -> ID: {ado_connection_id}")
except Exception as e:
    print(f"  AVISO: {e}")
    # Tentar encontrar conexao existente
    try:
        conns = pf.list_connections(df=False)
        for c in conns:
            if c["displayName"] == f"ado-{project_name.lower()}-conn":
                ado_connection_id = c["id"]
                print(f"  ENCONTRADA: -> ID: {ado_connection_id}")
                break
    except Exception as e2:
        print(f"  ERRO: {e2}")

# --- 6.2: Conectar cada workspace ao Git ---
print("\n--- 6.2: Conectando workspaces ao Git ---")
if ado_connection_id:
    for env_name, ws_id in workspace_ids.items():
        branch_name = ambientes[env_name]["branch"]
        ws_name = f"{project_name}-{env_name}"
        print(f"\n  Conectando {ws_name} -> branch: {branch_name}")

        try:
            pf.ado_connect(
                workspace=ws_id,
                connection_id=ado_connection_id,
                organization_name=ado_organization,
                project_name=ado_project,
                repository_name=ado_repository,
                branch_name=branch_name,
                directory_name="src",
            )
            print(f"    Conectado ao Git!")

            # Pequena pausa para a API processar
            time.sleep(5)

            # Inicializar Git no workspace
            print(f"    Inicializando Git (PreferWorkspace)...")
            pf.git_init(
                workspace=ws_id,
                initialize_strategy="PreferWorkspace"
            )
            print(f"    Git inicializado!")

        except Exception as e:
            print(f"    ERRO: {e}")
else:
    print("  ERRO: Conexao ADO nao disponivel. Pule esta etapa e configure manualmente.")

# Voltar para autenticacao fabric para as proximas celulas
pf.set_auth_provider("fabric")

print("\nConexoes Git configuradas!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 7: Gerar Pipelines YAML para Azure DevOps
#
# Agora vamos gerar os arquivos YAML que definem as pipelines de CI/CD no Azure DevOps.
#
# **O que e uma pipeline YAML?**
# E um arquivo de texto que diz ao Azure DevOps: "quando alguem fizer push na branch X,
# execute esses comandos automaticamente". E como uma receita automatizada.
#
# **Vamos criar 4 arquivos:**
# - `deploy-template.yml` - Template reutilizavel (a receita base)
# - `pipeline-dev.yml` - Trigger automatico quando push em `dev`
# - `pipeline-stg.yml` - Trigger automatico quando push em `staging`
# - `pipeline-prd.yml` - Trigger MANUAL (producao precisa de aprovacao)

# CELL ********************

# ============================================================
# CELULA 10 - GERAR PIPELINES YAML PARA AZURE DEVOPS
# ============================================================

print("=" * 60)
print("ETAPA 7: GERACAO DE PIPELINES YAML")
print("=" * 60)

# --- Template reutilizavel ---
deploy_template = f"""# Template de deploy reutilizavel
# Este arquivo NAO e executado diretamente.
# Ele e chamado pelas pipelines de cada ambiente.

parameters:
  - name: environment
    type: string
  - name: variableGroup
    type: string

jobs:
  - job: Deploy_${{{{ parameters.environment }}}}
    displayName: "Deploy para ${{{{ parameters.environment }}}}"
    pool:
      vmImage: "ubuntu-latest"

    variables:
      - group: Fabric-Credentials
      - group: ${{{{ parameters.variableGroup }}}}

    steps:
      - checkout: self
        fetchDepth: 0

      - task: UsePythonVersion@0
        inputs:
          versionSpec: "3.13"
        displayName: "Configurar Python 3.13"

      - script: pip install pyfabricops
        displayName: "Instalar pyfabricops"

      - script: |
          python scripts/deploy.py --env ${{{{ parameters.environment }}}}
        displayName: "Deploy para Fabric (${{{{ parameters.environment }}}})"
        env:
          FAB_CLIENT_ID: $(FAB_CLIENT_ID)
          FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
          FAB_TENANT_ID: $(FAB_TENANT_ID)

      - script: |
          python scripts/validate_deploy.py ${{{{ parameters.environment }}}}
        displayName: "Validar deploy"
        env:
          FAB_CLIENT_ID: $(FAB_CLIENT_ID)
          FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
          FAB_TENANT_ID: $(FAB_TENANT_ID)
"""

# --- Pipeline DEV (automatico) ---
pipeline_dev = f"""# Pipeline de deploy automatico para DEV
# Executa toda vez que alguem faz push na branch dev

trigger:
  branches:
    include:
      - dev
  paths:
    include:
      - src/**
      - scripts/**
      - env_config/dev.json

pr: none

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Deploy_DEV
    displayName: "Deploy para DEV"
    jobs:
      - template: templates/deploy-template.yml
        parameters:
          environment: dev
          variableGroup: Fabric-Config-DEV
"""

# --- Pipeline STG (automatico) ---
pipeline_stg = f"""# Pipeline de deploy automatico para STAGING
# Executa toda vez que alguem faz push na branch staging

trigger:
  branches:
    include:
      - staging
  paths:
    include:
      - src/**
      - scripts/**
      - env_config/stg.json

pr: none

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Deploy_STG
    displayName: "Deploy para STG"
    jobs:
      - template: templates/deploy-template.yml
        parameters:
          environment: stg
          variableGroup: Fabric-Config-STG
"""

# --- Pipeline PRD (manual com aprovacao) ---
pipeline_prd = f"""# Pipeline de deploy para PRODUCAO
# NUNCA executa automaticamente!
# Precisa ser disparado manualmente e aprovado.

trigger: none
pr: none

parameters:
  - name: confirmDeploy
    displayName: "Eu confirmo o deploy para PRODUCAO"
    type: boolean
    default: false
  - name: deployNote
    displayName: "Descricao do deploy"
    type: string
    default: ""

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Validacao
    displayName: "Validacao Pre-Deploy"
    jobs:
      - job: ValidarConfirmacao
        steps:
          - script: |
              if [ "${{{{ parameters.confirmDeploy }}}}" != "True" ]; then
                echo "ERRO: Deploy NAO confirmado. Marque o checkbox."
                exit 1
              fi
              echo "Deploy confirmado!"
              echo "Nota: ${{{{ parameters.deployNote }}}}"
            displayName: "Verificar confirmacao"

  - stage: Deploy_PRD
    displayName: "Deploy para PRD"
    dependsOn: Validacao
    condition: succeeded()
    jobs:
      - deployment: DeployProducao
        displayName: "Deploy Producao"
        environment: "Fabric-Production"
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
                  displayName: "Instalar pyfabricops"

                - script: |
                    python scripts/deploy.py --env prd
                  displayName: "Deploy para Fabric PRD"
                  env:
                    FAB_CLIENT_ID: $(FAB_CLIENT_ID)
                    FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
                    FAB_TENANT_ID: $(FAB_TENANT_ID)

                - script: |
                    python scripts/validate_deploy.py prd
                  displayName: "Validar deploy PRD"
                  env:
                    FAB_CLIENT_ID: $(FAB_CLIENT_ID)
                    FAB_CLIENT_SECRET: $(FAB_CLIENT_SECRET)
                    FAB_TENANT_ID: $(FAB_TENANT_ID)
"""

# --- Fazer push dos YAML para o repositorio ---
print("\nEnviando YAML para o repositorio Azure DevOps...")

if repo_id:
    # Buscar ultimo commit da branch main
    refs_url = f"{ADO_BASE}/git/repositories/{repo_id}/refs?filter=heads/main&api-version=7.1"
    refs_resp = ado_api_request("GET", refs_url)
    main_sha = None
    for ref in refs_resp.json().get("value", []):
        if ref["name"] == "refs/heads/main":
            main_sha = ref["objectId"]

    if main_sha:
        push_url = f"{ADO_BASE}/git/repositories/{repo_id}/pushes?api-version=7.1"
        push_payload = {
            "refUpdates": [{"name": "refs/heads/main", "oldObjectId": main_sha}],
            "commits": [{
                "comment": "chore: Adicionar pipelines YAML de CI/CD",
                "changes": [
                    {"changeType": "add", "item": {"path": "/.azure-pipelines/templates/deploy-template.yml"},
                     "newContent": {"content": deploy_template, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/.azure-pipelines/pipeline-dev.yml"},
                     "newContent": {"content": pipeline_dev, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/.azure-pipelines/pipeline-stg.yml"},
                     "newContent": {"content": pipeline_stg, "contentType": "rawtext"}},
                    {"changeType": "add", "item": {"path": "/.azure-pipelines/pipeline-prd.yml"},
                     "newContent": {"content": pipeline_prd, "contentType": "rawtext"}},
                ]
            }]
        }
        resp = ado_api_request("POST", push_url, push_payload)
        if resp.status_code in [200, 201]:
            print("  Pipelines YAML enviados para o repositorio!")
        else:
            print(f"  AVISO: {resp.status_code} - Arquivos podem ja existir")
            print(f"  Detalhes: {resp.text[:200]}")

print("\nPipelines geradas!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 8: Criar Pipelines no Azure DevOps
#
# Os YAML ja estao no repositorio. Agora precisamos dizer ao Azure DevOps
# para usa-los como pipelines reais.

# CELL ********************

# ============================================================
# CELULA 11 - REGISTRAR PIPELINES NO AZURE DEVOPS
# ============================================================

print("=" * 60)
print("ETAPA 8: REGISTRO DE PIPELINES NO AZURE DEVOPS")
print("=" * 60)

pipelines_to_create = [
    {
        "name": f"{project_name}-Deploy-DEV",
        "yaml_path": "/.azure-pipelines/pipeline-dev.yml",
        "folder": "\\\\CI-CD"
    },
    {
        "name": f"{project_name}-Deploy-STG",
        "yaml_path": "/.azure-pipelines/pipeline-stg.yml",
        "folder": "\\\\CI-CD"
    },
    {
        "name": f"{project_name}-Deploy-PRD",
        "yaml_path": "/.azure-pipelines/pipeline-prd.yml",
        "folder": "\\\\CI-CD"
    },
]

PIPELINES_BASE = f"https://dev.azure.com/{ado_organization}/{ado_project}/_apis/pipelines"

for pipe_config in pipelines_to_create:
    print(f"\n  Criando pipeline: {pipe_config['name']}")
    create_pipe_payload = {
        "name": pipe_config["name"],
        "folder": pipe_config["folder"],
        "configuration": {
            "type": "yaml",
            "path": pipe_config["yaml_path"],
            "repository": {
                "id": repo_id,
                "type": "azureReposGit",
                "name": ado_repository,
            }
        }
    }

    resp = ado_api_request(
        "POST",
        f"{PIPELINES_BASE}?api-version=7.1",
        create_pipe_payload
    )

    if resp.status_code in [200, 201]:
        pipe_data = resp.json()
        print(f"    CRIADA: ID {pipe_data.get('id')} - {pipe_config['name']}")
    else:
        print(f"    AVISO: {resp.status_code} - Pipeline pode ja existir")

print("\nPipelines registradas no Azure DevOps!")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Etapa 9: Resumo e Proximos Passos
#
# Parabens! Se chegou aqui sem erros, seu ambiente CI/CD esta configurado.
#
# ### O que foi criado:
# | Recurso | DEV | STG | PRD |
# |---------|-----|-----|-----|
# | Workspace | MeuProjeto-DEV | MeuProjeto-STG | MeuProjeto-PRD |
# | Environment | env_meuprojeto | env_meuprojeto | env_meuprojeto |
# | Variable Library | vl_meuprojeto | vl_meuprojeto | vl_meuprojeto |
# | Branch Git | dev | staging | main |
# | Pipeline ADO | Deploy-DEV (auto) | Deploy-STG (auto) | Deploy-PRD (manual) |

# CELL ********************

# ============================================================
# CELULA 12 - RESUMO FINAL E VERIFICACAO
# ============================================================

print("=" * 60)
print("RESUMO FINAL - VERIFICACAO DO AMBIENTE")
print("=" * 60)

pf.set_auth_provider("fabric")

print(f"\nProjeto: {project_name}")
print(f"Azure DevOps: {ado_organization}/{ado_project}/{ado_repository}")

print("\n--- Workspaces ---")
for env_name, ws_id in workspace_ids.items():
    ws_name = f"{project_name}-{env_name}"
    print(f"  {ws_name}: {ws_id}")

    # Verificar status Git
    try:
        status = pf.git_status(ws_id, df=False)
        if status:
            remote = str(status.get("remoteCommitHash", "N/A"))[:8]
            head = str(status.get("workspaceHead", "N/A"))[:8]
            sync = "Sincronizado" if remote == head else "DESSINCRONIZADO"
            print(f"    Git: remote={remote}... head={head}... [{sync}]")
    except Exception:
        print(f"    Git: Nao conectado ou erro ao verificar")

print("\n--- Environments ---")
for env_name, env_id in environment_ids.items():
    print(f"  {project_name}-{env_name}: {env_id}")

print("\n--- Variable Libraries ---")
for env_name, vl_id in variable_library_ids.items():
    print(f"  {project_name}-{env_name}: {vl_id}")

print(f"""
{'=' * 60}
PROXIMOS PASSOS (leia com atencao!):
{'=' * 60}

1. NO AZURE DEVOPS:
   a) Va em Pipelines > Library > + Variable group
   b) Crie o grupo "Fabric-Credentials" com:
      - FAB_CLIENT_ID = {fab_client_id}
      - FAB_CLIENT_SECRET = (marcar como SECRET)
      - FAB_TENANT_ID = {fab_tenant_id}
   c) Crie grupos "Fabric-Config-DEV", "Fabric-Config-STG", "Fabric-Config-PRD"
      com o WORKSPACE_NAME de cada ambiente

2. NO AZURE DEVOPS (Environments):
   a) Va em Pipelines > Environments
   b) Crie "Fabric-Production"
   c) Adicione Approvals (quem pode aprovar deploy em PRD)

3. NO AZURE DEVOPS (Branch Policies):
   a) Va em Repos > Branches
   b) Na branch "main": exigir PR com pelo menos 1 aprovador
   c) Na branch "staging": exigir PR com build validation

4. COMECE A DESENVOLVER:
   a) Crie objetos no workspace {project_name}-DEV
   b) Quando estiver pronto, faca push para a branch "dev"
   c) Crie PR de "dev" para "staging" (deploy automatico para STG)
   d) Apos validacao, PR de "staging" para "main" (deploy manual para PRD)

5. SEGURANCA:
   - Rotacione o Client Secret a cada 6 meses
   - Revise as roles dos workspaces trimestralmente
   - Nunca compartilhe o PAT do Azure DevOps

{'=' * 60}
SETUP CONCLUIDO COM SUCESSO!
{'=' * 60}
""")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
