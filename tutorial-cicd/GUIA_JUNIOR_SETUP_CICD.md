# Guia para Iniciantes: Montando CI/CD no Microsoft Fabric

> Este guia foi escrito para quem esta comecando.
> Se voce nunca configurou CI/CD antes, este documento e para voce.
> Leia com calma, siga na ordem, e nao pule etapas.

---

## O que voce vai aprender

Ao final deste guia, voce tera:

- 3 ambientes separados no Microsoft Fabric (DEV, STG, PRD)
- Um repositorio Git no Azure DevOps com 3 branches
- Pipelines automatizadas que fazem deploy quando voce faz push
- Seguranca configurada (quem pode ver e editar o que)
- Variaveis centralizadas por ambiente (sem hardcode)

**Tempo estimado**: 1 a 2 horas na primeira vez.

---

## Antes de comecar: O que e CI/CD?

Imagine que voce tem uma receita de bolo. Hoje voce faz o bolo na mao (desenvolvimento manual). CI/CD e como comprar uma maquina de fazer bolo automatica:

- **CI (Continuous Integration)**: Toda vez que voce muda a receita, a maquina verifica se a receita esta correta
- **CD (Continuous Deployment)**: Se a receita esta correta, a maquina faz o bolo sozinha

No nosso caso:
- A **receita** sao os objetos do Fabric (notebooks, modelos, reports)
- A **maquina** e o Azure DevOps
- O **bolo** e o deploy no ambiente de producao

### Por que 3 ambientes?

```
DEV (Desenvolvimento)     STG (Staging/Homologacao)     PRD (Producao)
┌───────────────────┐     ┌───────────────────────┐     ┌────────────────┐
│ Aqui voce testa   │     │ Aqui o gestor valida  │     │ Aqui os        │
│ coisas novas.     │ --> │ se esta tudo certo    │ --> │ usuarios usam  │
│ Pode quebrar.     │     │ antes de ir para PRD. │     │ o sistema real.│
│ Sem problema.     │     │ Ambiente controlado.  │     │ NAO pode       │
│                   │     │                       │     │ quebrar.       │
└───────────────────┘     └───────────────────────┘     └────────────────┘
```

**Regra de ouro**: Nunca altere producao diretamente. Sempre passe por DEV e STG primeiro.

---

## Glossario: Termos que voce precisa conhecer

| Termo | O que e | Analogia |
|-------|---------|----------|
| **Workspace** | Uma pasta no Fabric que contem seus objetos | Uma pasta no seu computador |
| **Environment** | Pacote de configuracoes do Spark (bibliotecas Python, etc.) | O Python instalado no seu computador |
| **Variable Library** | Cofre de variaveis (chave-valor) do Fabric | Um arquivo .env, mas gerenciado pelo Fabric |
| **Git** | Sistema de controle de versao (historico de alteracoes) | O "Ctrl+Z" infinito para codigo |
| **Branch** | Uma "copia paralela" do seu codigo | Um rascunho de um documento |
| **PR (Pull Request)** | Pedido para juntar uma branch na outra | Pedir aprovacao antes de publicar |
| **Pipeline** | Sequencia automatizada de passos | Uma receita executada automaticamente |
| **Service Principal** | Uma "conta de robo" que faz coisas automaticamente | Um assistente virtual com permissoes |
| **Token/Secret** | Uma senha para acessar servicos | A chave da sua casa |
| **Capacity** | Poder computacional do Fabric | O motor do seu carro |
| **TMDL** | Linguagem que define modelos semanticos | A planta de uma casa |
| **Placeholder** | Marcador que sera substituido por um valor real | O `[NOME]` em um contrato que sera preenchido |

---

## Conceitos Importantes de Seguranca

### O que NUNCA fazer

1. **Nunca coloque senhas dentro do codigo**
   ```python
   # ERRADO - Qualquer pessoa que ver o codigo tera a senha
   password = "MinhaSenha123!"

   # CERTO - A senha vem de uma variavel de ambiente
   import os
   password = os.getenv("DATABASE_PASSWORD")
   ```

2. **Nunca commite o arquivo `.env` no Git**
   - O `.gitignore` ja cuida disso, mas confira sempre
   - Se commitar por acidente, rotacione TODAS as senhas imediatamente

3. **Nunca compartilhe o PAT (Personal Access Token) do Azure DevOps**
   - Trate como uma senha pessoal
   - Se vazar, revogue imediatamente

4. **Nunca faca deploy em producao sem aprovacao**
   - A pipeline de PRD exige confirmacao manual por isso
   - Se estiver em duvida, pergunte antes de aprovar

### Onde guardar cada tipo de informacao

| Tipo de informacao | Onde guardar | Exemplo |
|--------------------|-------------|---------|
| Senhas, tokens, secrets | ADO Variable Groups (marcado como secret) | FAB_CLIENT_SECRET |
| IDs que mudam por ambiente | Variable Library do Fabric | workspace_id, lakehouse_id |
| Configuracoes do pipeline | Arquivo YAML no repositorio | Qual Python usar, quais steps executar |
| Mapeamento branch/workspace | branches.json no repositorio | `{"main": "-PRD"}` |
| Placeholders nos objetos | Dentro dos arquivos em src/ | `#{nb_ingestao_server}#` |

---

## O que e o PyFabricOps?

PyFabricOps e uma biblioteca Python que faz o trabalho pesado por voce. Em vez de clicar em dezenas de botoes no portal do Fabric, voce escreve algumas linhas de codigo e ela faz tudo automaticamente.

**Exemplo simples:**

```python
import pyfabricops as pf

# Ao inves de clicar em "New workspace" no portal:
pf.create_workspace("MeuProjeto-DEV", capacity="MinhaCapacidade")

# Ao inves de ir em Settings > Git > Connect:
pf.ado_connect(
    workspace="MeuProjeto-DEV",
    connection_id="id-da-conexao",
    organization_name="minha-org",
    project_name="meu-projeto",
    repository_name="meu-repo",
    branch_name="dev",
    directory_name="src"
)
```

### Como o PyFabricOps se autentica?

Ele tem 3 modos:

| Modo | Quando usar | Como funciona |
|------|-------------|---------------|
| `"fabric"` | Dentro de notebooks do Fabric | Usa o login do usuario ja logado |
| `"env"` | Em pipelines CI/CD, scripts locais | Usa variaveis de ambiente (FAB_CLIENT_ID, etc.) |
| `"oauth"` | Desenvolvimento local no VS Code | Abre o navegador para login |

---

## O que sao Placeholders e por que usamos?

Imagine que voce tem um notebook que acessa um banco de dados:

```python
# Em DEV, o servidor e: meuserver-dev.database.windows.net
# Em STG, o servidor e: meuserver-stg.database.windows.net
# Em PRD, o servidor e: meuserver-prd.database.windows.net
```

Se voce colocar o servidor DEV direto no codigo e fizer deploy em PRD, ele vai acessar o banco ERRADO. Isso e um problema grave.

**Solucao: Placeholders**

No codigo, em vez de colocar o valor real, colocamos um marcador:

```python
# No arquivo versionado (com placeholder):
source_server = "#{nb_ingestao_source_server}#"

# Na hora do deploy para DEV, vira:
source_server = "meuserver-dev.database.windows.net"

# Na hora do deploy para PRD, vira:
source_server = "meuserver-prd.database.windows.net"
```

O placeholder `#{nb_ingestao_source_server}#` e substituido automaticamente pelo script de deploy, que consulta o arquivo de configuracao do ambiente correto.

### Formato dos placeholders por tipo de objeto

| Objeto | Onde fica o placeholder | Formato |
|--------|------------------------|---------|
| Notebook | `notebook-content.py` | `#{NomeNotebook_variavel}#` |
| Semantic Model | `expressions.tmdl` | `#{NomeParametro}#` |
| Data Pipeline | `pipeline-content.json` | `#{Activity_SubActivity_campo}#` |
| Dataflow Gen2 | `mashup.pq` | `#{NomeDataflow_Query_campo}#` |

---

## O que e uma Variable Library do Fabric?

E diferente de uma variavel de ambiente ou de um placeholder. Veja a comparacao:

| Conceito | Onde vive | Quem le | Quando usar |
|----------|----------|---------|-------------|
| **Variavel de ambiente** | Sistema operacional (.env) | Codigo Python via `os.getenv()` | Credenciais em CI/CD |
| **Placeholder** | Dentro dos arquivos src/ | Script de deploy (substituicao de texto) | IDs e configs que mudam entre ambientes |
| **Variable Library** | Dentro do workspace Fabric | Notebooks Fabric em runtime | Parametros consultados em tempo de execucao |

**Exemplo de uso da Variable Library em um notebook:**

```python
# Dentro de um notebook no Fabric, voce pode fazer:
from notebookutils import mssparkutils

# Ler a variavel direto da Variable Library
sql_server = mssparkutils.credentials.getSecret("keyvault", "sql-server")

# Ou, se usando pyfabricops, via API:
vl = pf.get_variable_library_definition("MeuWorkspace", "vl_meuprojeto")
```

A Variable Library e util para:
- Guardar configuracoes que notebooks consultam em tempo de execucao
- Centralizar parametros sem precisar alterar codigo
- Ter visibilidade de todas as configuracoes de um workspace

---

## O que e um Fabric Environment?

E o "pacote de software" que o Spark usa quando roda seu notebook. Sem ele, bibliotecas como `pyfabricops` nao estariam disponiveis.

**Ciclo de vida:**

```
1. Voce cria o Environment
2. Voce adiciona bibliotecas (ex: pyfabricops)
3. Voce faz "Publish" (instalacao das bibliotecas)
4. Voce associa o Environment ao notebook
5. Quando o notebook roda, ele usa as bibliotecas do Environment
```

**Por que um Environment por workspace?**

Porque em DEV voce pode querer testar versoes novas de uma biblioteca, enquanto PRD precisa ter versoes estaveis e testadas.

---

## Passo a passo: Executando o Notebook de Setup

### Passo 0: Pre-requisitos (faca ANTES de executar o notebook)

#### 0.1 Criar App Registration no Azure

1. Acesse [portal.azure.com](https://portal.azure.com)
2. Pesquise "Microsoft Entra ID" na barra de busca
3. No menu lateral, clique em "App registrations"
4. Clique em "+ New registration"
5. Preencha:
   - **Name**: `meu-projeto-fabric-cicd`
   - **Supported account types**: Accounts in this organizational directory only
   - **Redirect URI**: (deixe vazio)
6. Clique em "Register"
7. Na tela que abrir, **copie e guarde** dois valores:
   - **Application (client) ID** → Este e o `FAB_CLIENT_ID`
   - **Directory (tenant) ID** → Este e o `FAB_TENANT_ID`

#### 0.2 Criar Client Secret

1. Ainda na pagina do App Registration, clique em "Certificates & secrets"
2. Clique em "+ New client secret"
3. Descricao: `fabric-cicd`
4. Expiracao: 12 meses
5. Clique em "Add"
6. **Copie o Value** (atencao: ele so aparece uma vez!) → Este e o `FAB_CLIENT_SECRET`

#### 0.3 Dar permissoes ao App Registration

1. Clique em "API permissions" no menu lateral
2. Clique em "+ Add a permission"
3. Clique em "Power BI Service"
4. Selecione "Application permissions"
5. Marque:
   - `Tenant.Read.All`
   - `Tenant.ReadWrite.All`
6. Clique em "Add permissions"
7. Clique no botao "Grant admin consent for [Tenant]" (precisa ser admin)
8. Confirme clicando "Yes"

#### 0.4 Habilitar no Fabric Admin Portal

1. Acesse [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Clique na engrenagem (Settings) no canto superior direito
3. Clique em "Admin portal"
4. Va em "Tenant settings"
5. Procure e habilite:
   - **"Service principals can use Fabric APIs"** → Habilite e adicione seu App Registration ou Security Group
   - **"Users can synchronize workspace items with their Git repositories"** → Habilite

**IMPORTANTE**: Depois de habilitar, espere 15 minutos antes de continuar.

#### 0.5 Criar PAT no Azure DevOps

1. Acesse [dev.azure.com](https://dev.azure.com)
2. Clique no icone de usuario no canto superior direito
3. Clique em "Personal access tokens"
4. Clique em "+ New Token"
5. Preencha:
   - **Name**: `fabric-setup`
   - **Expiration**: 30 dias
   - **Scopes**: Custom defined → Marque:
     - Code: Read & Write
     - Build: Read & Execute
     - Project and Team: Read, Write & Manage
6. Clique em "Create"
7. **Copie o token** (so aparece uma vez!) → Este e o `ado_pat`

### Passo 1: Abrir o Notebook no Fabric

1. Acesse [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Abra qualquer workspace onde voce tenha permissao
3. Clique em "+ New item" > "Notebook"
4. Copie o conteudo do arquivo `nb_setup_ambiente_cicd.py` para o notebook
5. Ou importe o arquivo diretamente

### Passo 2: Preencher os parametros

Na **Celula 2 (PARAMETROS)**, preencha TODOS os valores:

```python
# Troque esses valores pelos seus:
project_name = "MeuProjeto"                    # Nome do seu projeto
capacity_name = "MinhaCapacidadeFabric"        # Nome da capacidade
fab_client_id = "seu-client-id-aqui"           # Do passo 0.1
fab_client_secret = "seu-secret-aqui"          # Do passo 0.2
fab_tenant_id = "seu-tenant-id-aqui"           # Do passo 0.1
ado_organization = "sua-organizacao"           # Nome no Azure DevOps
ado_project = "seu-projeto"                    # Nome do projeto ADO
ado_repository = "fabric-cicd"                 # Nome do repositorio
ado_pat = "seu-pat-aqui"                       # Do passo 0.5
spn_uuid = "mesmo-valor-do-client-id"         # Geralmente igual ao FAB_CLIENT_ID
```

### Passo 3: Executar celula por celula

**NAO execute tudo de uma vez.** Execute celula por celula e leia a saida.

| Celula | O que faz | O que esperar |
|--------|-----------|---------------|
| 1 | Instala pyfabricops | `Successfully installed pyfabricops` |
| 2 | Define parametros | Nenhuma saida (so define variaveis) |
| 3 | Configura autenticacao | `pyfabricops configurado com sucesso!` |
| 4 | Cria workspaces | `CRIADO: MeuProjeto-DEV -> ID: ...` (3 vezes) |
| 5 | Atribui roles | `Admin -> Service Principal ...` |
| 6 | Cria environments | `CRIADO: env_meuprojeto -> ID: ...` |
| 7 | Cria variable libraries | `CRIADA: vl_meuprojeto -> ID: ...` |
| 8 | Configura ADO repo | `Repositorio criado`, `Branches criadas` |
| 9 | Conecta Git | `Conectado ao Git!` |
| 10 | Gera YAML | `Pipelines YAML enviados para o repositorio!` |
| 11 | Registra pipelines | `CRIADA: Deploy-DEV`, etc. |
| 12 | Resumo final | Lista tudo que foi criado + proximos passos |

### Passo 4: Configurar Variable Groups no Azure DevOps

Esta parte e feita MANUALMENTE no portal do Azure DevOps (o notebook nao faz isso porque envolve marcar campos como secret na interface).

1. Va em Azure DevOps > Pipelines > Library
2. Clique em "+ Variable group"
3. Crie **Fabric-Credentials**:

   | Nome da variavel | Valor | Cadeado (secret)? |
   |-----------------|-------|-------------------|
   | FAB_CLIENT_ID | (seu client id) | Nao |
   | FAB_CLIENT_SECRET | (seu client secret) | **SIM** |
   | FAB_TENANT_ID | (seu tenant id) | Nao |

4. Crie **Fabric-Config-DEV**, **Fabric-Config-STG**, **Fabric-Config-PRD** com:

   | Nome da variavel | Valor DEV | Valor STG | Valor PRD |
   |-----------------|-----------|-----------|-----------|
   | WORKSPACE_NAME | MeuProjeto-DEV | MeuProjeto-STG | MeuProjeto-PRD |

### Passo 5: Configurar aprovacao para producao

1. Va em Azure DevOps > Pipelines > Environments
2. Clique em "+ New environment"
3. Nome: `Fabric-Production`
4. Clique nos tres pontinhos (...) > "Approvals and checks"
5. Clique em "+ Approvals"
6. Adicione as pessoas que podem aprovar deploy em PRD
7. Salve

### Passo 6: Configurar branch policies

1. Va em Azure DevOps > Repos > Branches
2. Na branch `main`, clique nos tres pontinhos > "Branch policies"
3. Habilite:
   - **Require a minimum number of reviewers**: 1
   - **Check for linked work items**: Opcional
   - **Check for comment resolution**: Opcional

---

## Fluxo do dia a dia (apos o setup)

### Como desenvolver

```
1. Abra o workspace MeuProjeto-DEV no Fabric
2. Crie ou edite seus objetos (notebooks, modelos, etc.)
3. Quando estiver pronto, va em Source Control no Fabric
4. Faca commit das alteracoes para a branch "dev"
5. A pipeline Deploy-DEV roda automaticamente
```

### Como promover para STG

```
1. No Azure DevOps, va em Repos > Pull requests
2. Crie um PR de "dev" -> "staging"
3. Descreva o que mudou
4. Peca para alguem revisar
5. Apos aprovacao, faca o merge
6. A pipeline Deploy-STG roda automaticamente
```

### Como promover para PRD

```
1. Crie um PR de "staging" -> "main"
2. Descreva o que mudou e por que
3. Peca aprovacao (minimo 1 reviewer)
4. Apos aprovacao do PR, faca o merge
5. Va em Pipelines > MeuProjeto-Deploy-PRD
6. Clique em "Run pipeline"
7. Marque o checkbox "Eu confirmo o deploy para PRODUCAO"
8. Preencha a descricao do deploy
9. Clique em "Run"
10. O aprovador recebera uma notificacao para aprovar
11. Apos aprovacao, o deploy acontece
```

---

## Diagrama do fluxo completo

```
  DESENVOLVEDOR                      AZURE DEVOPS                     FABRIC
  ============                      ============                     ======

  Edita notebook        Commit
  no Fabric DEV ──────────────► branch "dev" ──────► Pipeline DEV
                                                      │
                                                      ▼
                                                    Deploy para
                                                    MeuProjeto-DEV
                                                      │
                                                      ▼
                          PR: dev -> staging          Testa em DEV
                         (revisao de codigo) ◄────── tudo OK?
                                │
                                ▼
                         Merge aprovado ──────────► Pipeline STG
                                                      │
                                                      ▼
                                                    Deploy para
                                                    MeuProjeto-STG
                                                      │
                                                      ▼
                          PR: staging -> main        Valida em STG
                         (revisao + aprovacao) ◄──── tudo OK?
                                │
                                ▼
                         Merge aprovado
                                │
                         Pipeline PRD (manual)
                         + Aprovacao ──────────────► Deploy para
                                                    MeuProjeto-PRD
```

---

## Checklist de seguranca

Use esta lista para verificar se tudo esta seguro:

- [ ] Client Secret NAO esta em nenhum arquivo no repositorio
- [ ] PAT do Azure DevOps NAO esta em nenhum arquivo no repositorio
- [ ] Arquivo `.env` esta no `.gitignore`
- [ ] Variable Groups com secrets estao marcados com o cadeado
- [ ] Service Principal tem role "Admin" nos 3 workspaces
- [ ] Grupo de analistas tem role "Viewer" (nao "Contributor") em PRD
- [ ] Branch `main` exige PR com aprovacao
- [ ] Pipeline de PRD exige confirmacao manual
- [ ] Environment `Fabric-Production` tem aprovadores configurados
- [ ] Client Secret tem data de expiracao definida (maximo 12 meses)

---

## Erros comuns e como resolver

### "Token request failed: 401"

**O que significa**: As credenciais estao erradas ou expiraram.

**Como resolver**:
1. Verifique se FAB_CLIENT_ID, FAB_CLIENT_SECRET e FAB_TENANT_ID estao corretos
2. Verifique se o Client Secret nao expirou (va no Entra ID > App registrations > Certificates & secrets)
3. Crie um novo secret se necessario

### "Caller does not have permissions"

**O que significa**: O Service Principal nao tem permissao suficiente.

**Como resolver**:
1. Verifique se "Service principals can use Fabric APIs" esta habilitado no Fabric Admin Portal
2. Verifique se o SPN tem role "Admin" no workspace
3. Espere 15 minutos apos habilitar settings no Admin Portal

### "Workspace already exists"

**O que significa**: O workspace ja foi criado antes (talvez voce rodou o notebook duas vezes).

**Nao e um erro**: O notebook detecta isso e busca o workspace existente. Pode continuar normalmente.

### "Branch already exists"

**O que significa**: A branch ja foi criada antes.

**Nao e um erro**: O notebook pula a criacao e continua. Normal se executar mais de uma vez.

### Pipeline do ADO falha com "access denied"

**Como resolver**:
1. Verifique se o Variable Group "Fabric-Credentials" esta acessivel pela pipeline
2. Va no Variable Group > Pipeline permissions > Adicione a pipeline

---

## Estrutura de arquivos no repositorio

Apos o setup, seu repositorio tera esta estrutura:

```
contoso-fabric/
│
├── .azure-pipelines/              ← Pipelines de CI/CD
│   ├── templates/
│   │   └── deploy-template.yml    ← Template reutilizavel
│   ├── pipeline-dev.yml           ← Pipeline DEV (automatico)
│   ├── pipeline-stg.yml           ← Pipeline STG (automatico)
│   └── pipeline-prd.yml           ← Pipeline PRD (manual)
│
├── src/                           ← Objetos do Fabric (exportados)
│   ├── MeuNotebook.Notebook/      ← Cada pasta e um objeto
│   ├── MeuModelo.SemanticModel/
│   └── MeuReport.Report/
│
├── env_config/                    ← Configuracoes por ambiente
│   ├── dev.json                   ← Valores para DEV
│   ├── stg.json                   ← Valores para STG
│   └── prd.json                   ← Valores para PRD
│
├── scripts/                       ← Scripts de automacao
│   ├── deploy.py                  ← Script principal de deploy
│   └── validate_deploy.py         ← Validacao pos-deploy
│
├── .gitignore                     ← Arquivos que o Git ignora
├── .gitattributes                 ← Configs de merge
├── branches.json                  ← Branch -> sufixo do workspace
├── README.md                      ← Descricao do projeto
└── requirements.txt               ← Dependencias Python
```

---

## Perguntas frequentes

### "Posso rodar o notebook mais de uma vez?"

Sim. Ele detecta recursos que ja existem e pula a criacao. E seguro re-executar.

### "E se eu errar um parametro?"

Corrija o parametro na celula 2 e re-execute a partir da celula que precisa. Nao precisa rodar tudo de novo.

### "Preciso de uma capacidade paga do Fabric?"

Sim. O Fabric precisa de pelo menos uma capacidade F2 (ou P1, ou Trial) para criar workspaces. A Trial funciona para aprender e testar.

### "Posso usar GitHub em vez de Azure DevOps?"

Sim. O PyFabricOps suporta ambos. Use `pf.github_connect()` em vez de `pf.ado_connect()` e `pf.create_github_source_control_connection()` para a conexao.

### "O que acontece se alguem fizer push direto em main?"

Se voce configurou branch policies (Passo 6), o Azure DevOps bloqueia pushes diretos. Somente PRs aprovados passam.

### "Preciso refazer tudo se mudar o nome do projeto?"

Sim, pois os nomes dos workspaces sao baseados no `project_name`. E mais facil criar um projeto novo do que renomear tudo.

---

## Proximos passos apos o setup

1. **Exporte objetos existentes** do workspace DEV para o repositorio:
   ```python
   pf.export_all_items("MeuProjeto-DEV", "./src")
   ```

2. **Parametrize os objetos** (substitua valores reais por placeholders):
   ```python
   params = pf.extract_notebook_parameters("./src/MeuNotebook.Notebook")
   pf.replace_notebook_parameters_with_placeholders("./src/MeuNotebook.Notebook", params)
   ```

3. **Crie os scripts de deploy** (veja o CASE_REAL_CICD_AZURE_DEVOPS.md para exemplos completos)

4. **Teste o fluxo** fazendo uma alteracao pequena em DEV e promovendo ate PRD
