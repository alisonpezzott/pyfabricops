# Melhores Praticas CI/CD com PyFabricOps

Documento consolidado com 24 melhorias organizadas em 4 secoes. Cada item referencia o notebook ou script correspondente que sera criado nas proximas tarefas.

---

## Sumario

1. [Robustez Operacional](#1-robustez-operacional)
2. [Governanca e Compliance](#2-governanca-e-compliance)
3. [Developer Experience](#3-developer-experience)
4. [Escalabilidade](#4-escalabilidade)
5. [Tabela de Prioridades](#tabela-de-prioridades)

---

## 1. Robustez Operacional

### 1.1 Deploy com Backup Snapshot

Antes de qualquer deploy em HML ou PRD, o pipeline exporta e persiste um snapshot de todos os itens do workspace de destino. Em caso de falha, o rollback restaura exatamente o estado anterior sem dependencia de Git ou de um deploy anterior bem-sucedido.

**Arquivo:** [nb_deploy_com_backup.py](nb_deploy_com_backup.py)

**Fluxo resumido:**

```
1. export_workspace(workspace_target)  -> salva em /tmp/snapshot_YYYYMMDD_HHMMSS/
2. deploy() -> aplica os itens do workspace fonte
3. Em caso de erro: restore_snapshot() <- le /tmp/snapshot_*/
```

**Variaveis de controle:**

| Variavel | Descricao | Exemplo |
|---|---|---|
| `BACKUP_ENABLED` | Ativa/desativa backup antes do deploy | `true` |
| `BACKUP_RETENTION_DAYS` | Quantos dias manter snapshots | `7` |
| `SNAPSHOT_STORAGE_PATH` | Caminho no ADLS para persistencia | `abfss://backups@sa.dfs.core.windows.net/cicd/` |

---

### 1.2 Deploy Atomico com Dry-Run

O modo `--dry-run` executa todas as validacoes e simulacoes do deploy (diff de itens, verificacao de parametros, teste de conectividade) sem realizar nenhuma alteracao real no workspace de destino. Util para validar pipelines ADO antes de promover para PRD.

**Arquivo:** [nb_deploy_com_backup.py](nb_deploy_com_backup.py) (flag `--dry-run`)

**Comportamento:**

```python
# Com dry_run=True, o notebook imprime o plano de execucao mas nao chama
# nenhuma funcao destrutiva (create_item, update_item, delete_item)
deploy(
    workspace_source="WS-DEV",
    workspace_target="WS-PRD",
    dry_run=True   # <- sem alteracoes reais
)
```

**Saida esperada no dry-run:**

```
[DRY-RUN] Items a criar   : 3  (Notebook: nb_vendas, Notebook: nb_clientes, DataPipeline: pl_ingest)
[DRY-RUN] Items a atualizar: 5  (SemanticModel: sm_receita, ...)
[DRY-RUN] Items a deletar  : 0
[DRY-RUN] Parametros a substituir: 12 placeholders encontrados
[DRY-RUN] Nenhuma alteracao foi aplicada.
```

---

### 1.3 Health Checks Pre e Pos-Deploy

Conjunto de verificacoes automatizadas executadas antes e depois do deploy para garantir que o ambiente esta operacional e que os itens deployados funcionam corretamente.

**Arquivo:** [nb_health_checks.py](nb_health_checks.py)

**Checks pre-deploy:**

| Check | O que valida |
|---|---|
| Conectividade workspace | `get_workspace()` retorna sem erro |
| Capacidade ativa | Workspace nao esta em estado suspenso |
| Git sync | HEAD do workspace bate com o commit do pipeline |
| Conexoes disponiveis | Todas as conexoes referenciadas existem |
| Placeholders resolvidos | Nenhum `#{...}#` restante apos substituicao |

**Checks pos-deploy:**

| Check | O que valida |
|---|---|
| Items deployados existem | `list_items()` confirma presenca de cada item |
| Semantic Models carregados | Query DAX `EVALUATE {1}` retorna sem erro |
| Data Pipelines validos | `get_item_definition()` parse sem erro |
| Refresh apos deploy | Opcional: dispara refresh e aguarda conclusao |

---

### 1.4 Retry com Idempotencia

Todas as operacoes de deploy implementam retry com backoff exponencial e sao idempotentes: executar a mesma operacao duas vezes produz o mesmo resultado sem efeitos colaterais.

**Implementacao:** inclusa nos notebooks [nb_deploy_com_backup.py](nb_deploy_com_backup.py) e [nb_health_checks.py](nb_health_checks.py)

**Padrao de retry:**

```python
import time

def deploy_with_retry(fn, max_attempts=3, base_delay=10):
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"[RETRY] Tentativa {attempt} falhou: {e}. Aguardando {delay}s...")
            time.sleep(delay)
```

**Garantias de idempotencia:**

- `create_item`: verifica existencia antes; se ja existe, faz `update_item`
- `replace_*_parameters`: aplica substituicao sobre o conteudo original, nao sobre versao ja substituida
- `git_commit`: verifica se ha mudancas reais antes de comitar

---

### 1.5 Notificacoes de Resultado

Notificacoes automaticas via Teams webhook ao final de cada deploy (sucesso ou falha), incluindo link para o pipeline ADO, lista de itens deployados e duracao.

**Implementacao:** webhook do Teams chamado via task `InvokeRestAPI` no pipeline Azure DevOps

**Snippet YAML para pipeline ADO:**

```yaml
# azure-pipelines.yml - task de notificacao apos deploy
- task: InvokeRestAPI@1
  displayName: "Notificar Teams - Resultado do Deploy"
  condition: always()
  inputs:
    connectionType: connectedServiceName
    serviceConnection: "teams-webhook-sc"
    method: POST
    headers: |
      {
        "Content-Type": "application/json"
      }
    body: |
      {
        "type": "message",
        "attachments": [
          {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
              "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
              "type": "AdaptiveCard",
              "version": "1.4",
              "body": [
                {
                  "type": "TextBlock",
                  "size": "Medium",
                  "weight": "Bolder",
                  "text": "Deploy $(Build.DefinitionName) - $(Agent.JobStatus)"
                },
                {
                  "type": "FactSet",
                  "facts": [
                    { "title": "Ambiente",   "value": "$(AMBIENTE)" },
                    { "title": "Branch",     "value": "$(Build.SourceBranchName)" },
                    { "title": "Commit",     "value": "$(Build.SourceVersion)" },
                    { "title": "Executado por", "value": "$(Build.RequestedFor)" },
                    { "title": "Duracao",    "value": "$(DEPLOY_DURATION_SECONDS)s" }
                  ]
                }
              ],
              "actions": [
                {
                  "type": "Action.OpenUrl",
                  "title": "Ver Pipeline",
                  "url": "$(System.CollectionUri)$(System.TeamProject)/_build/results?buildId=$(Build.BuildId)"
                }
              ]
            }
          }
        ]
      }
```

---

### 1.6 Integracao com Azure Key Vault

Centralizacao de segredos (connection strings, tokens, chaves de API) no Azure Key Vault, com dois padroes de acesso: via ADO Variable Group (para pipelines) e via `mssparkutils` (para notebooks Fabric).

**Arquivo:** [nb_keyvault_setup.py](nb_keyvault_setup.py)

**Diagrama de arquitetura:**

```
                    +-------------------+
                    |  Azure Key Vault  |
                    |  (segredos/certs) |
                    +--------+----------+
                             |
              +--------------+---------------+
              |                              |
   +----------v-----------+    +-------------v----------+
   | ADO Variable Group   |    |  mssparkutils.credentials|
   | (linked to KV)       |    |  (Fabric notebook)      |
   +----------+-----------+    +-------------+----------+
              |                              |
   +----------v-----------+    +-------------v----------+
   | azure-pipelines.yml  |    |  nb_deploy_com_backup  |
   | ($(KV_SECRET_NAME))  |    |  nb_health_checks      |
   +---------------------+    +------------------------+
```

**Acesso no notebook Fabric:**

```python
# Leitura de segredo via mssparkutils (requer Managed Identity ou SPN com acesso ao KV)
secret_value = mssparkutils.credentials.getSecret(
    "https://kv-contoso-cicd.vault.azure.net/",
    "sql-connection-string"
)
```

**Acesso no pipeline ADO (Variable Group linkado ao KV):**

```yaml
variables:
  - group: "vg-keyvault-cicd"   # Variable Group linkado ao Azure Key Vault

steps:
  - script: echo "Usando segredo: $(sql-connection-string)"
```

**Tabela RBAC minimo para o Key Vault:**

| Identidade | Role KV | Justificativa |
|---|---|---|
| SPN do pipeline ADO | Key Vault Secrets User | Leitura de segredos durante deploy |
| Managed Identity do workspace Fabric | Key Vault Secrets User | Leitura em notebooks |
| Time DevOps (grupo AAD) | Key Vault Secrets Officer | Gestao de segredos (sem acesso a chaves) |
| Nenhum usuario individual | — | Acesso via grupos, nunca direto |

---

## 2. Governanca e Compliance

### 2.1 Audit Trail Automatizado

Registro estruturado de cada execucao de deploy em formato JSON, persistido no ADLS e/ou Delta Lake para consultas historicas e auditorias.

**Arquivo:** [nb_audit_trail.py](nb_audit_trail.py)

**Schema do registro de auditoria (JSON):**

```json
{
  "timestamp":         "2026-04-04T14:32:01Z",
  "executor":          "spn-cicd-contoso@tenant.onmicrosoft.com",
  "pipeline_run_id":   "12345678-ado-run-id",
  "workspace_source":  "WS-STG",
  "workspace_target":  "WS-PRD",
  "items_deployed": [
    { "type": "Notebook",      "name": "nb_vendas",   "status": "updated" },
    { "type": "SemanticModel", "name": "sm_receita",  "status": "created" }
  ],
  "git_commit_hash":   "a1b2c3d4e5f6...",
  "status":            "success",
  "duration_seconds":  142,
  "dry_run":           false,
  "errors":            []
}
```

**Destinos de persistencia:**

| Destino | Quando usar |
|---|---|
| ADLS Gen2 (JSON por execucao) | Auditoria simples, baixo custo |
| Delta Lake (tabela `cicd_audit_log`) | Consultas SQL, historico longo prazo |
| Log Analytics Workspace | Alertas e dashboards no Azure Monitor |

---

### 2.2 Politica de Aprovacao por Ambiente

Cada ambiente possui politica de aprovacao proporcional ao risco. DEV e automatico; HML exige aprovacao do TechLead; PRD exige aprovacao do TechLead e do Product Owner.

**Arquivo:** [templates/azure-pipelines-com-aprovacao.yml](templates/azure-pipelines-com-aprovacao.yml)

**Tabela de aprovacoes:**

| Ambiente | Aprovacao necessaria | Timeout | Notificacao |
|---|---|---|---|
| DEV | Automatico (sem aprovacao) | — | Teams (informativo) |
| HML | TechLead | 4 horas | Teams + email |
| PRD | TechLead + Product Owner | 2 horas | Teams + email + SMS |

**Configuracao no ADO (Environments + Approvals):**

```yaml
stages:
  - stage: deploy_prd
    displayName: "Deploy PRD"
    dependsOn: deploy_hml
    jobs:
      - deployment: deploy_prd_job
        environment: "fabric-prd"    # <- environment com aprovacao configurada no ADO
        strategy:
          runOnce:
            deploy:
              steps:
                - script: uv run python nb_deploy_com_backup.py --env PRD
```

> **Nota:** A aprovacao e configurada no Azure DevOps em `Pipelines > Environments > fabric-prd > Approvals and checks`, nao no YAML. O YAML apenas referencia o environment.

---

### 2.3 RBAC Granular por Workspace

Matriz de permissoes por perfil e ambiente, aplicada programaticamente pelo notebook de validacao.

**Arquivo:** [nb_rbac_validacao.py](nb_rbac_validacao.py)

**Matriz de permissoes:**

| Perfil | DEV | HML | PRD |
|---|---|---|---|
| Desenvolvedor | Admin | Contributor | Viewer |
| TechLead | Admin | Admin | Contributor |
| SPN (pipeline CI/CD) | Contributor | Contributor | Contributor |
| Product Owner | Viewer | Viewer | Viewer |
| Usuario de Negocio | — | Viewer | Viewer |

**Funcoes PyFabricOps usadas:**

```python
from pyfabricops import add_workspace_role_assignment, list_workspace_role_assignments

# Adicionar membro
add_workspace_role_assignment(
    workspace_id="...",
    principal_id="...",
    principal_type="ServicePrincipal",  # User | Group | ServicePrincipal
    role="Contributor"
)

# Validar que a matriz esta correta
assignments = list_workspace_role_assignments(workspace_id="...")
```

---

### 2.4 Classificacao e Protecao de Dados

Padrao de nomenclatura obrigatorio para itens que contem dados sensiveis, integrado com Microsoft Purview Sensitivity Labels.

**Convencao de nomenclatura:**

| Prefixo | Nivel de sensibilidade | Exemplo |
|---|---|---|
| `[CONF]` | Confidencial — acesso restrito | `[CONF] sm_dados_financeiros` |
| `[INT]` | Interno — apenas colaboradores | `[INT] nb_relatorio_vendas` |
| `[PUB]` | Publico — sem restricao | `[PUB] nb_indicadores_site` |

**Integracao com Purview Sensitivity Labels:**

```python
# Aplicar sensitivity label via API REST do Fabric
# (requer permissao Information Protection Administrator)
from pyfabricops import call_fabric_api

call_fabric_api(
    method="PATCH",
    endpoint=f"/v1/workspaces/{workspace_id}/items/{item_id}/sensitivityLabel",
    body={
        "sensitivityLabel": {
            "labelId": "confidential-label-guid"
        }
    }
)
```

**Validacao automatica:** o notebook [nb_compliance_checks.py](nb_compliance_checks.py) verifica se todos os Semantic Models e Notebooks seguem a convencao de nomenclatura.

---

### 2.5 Change Tracking com Git Tags

Cada deploy em PRD gera uma tag Git com formato padronizado, permitindo rastrear exatamente qual versao esta em producao e facilitar rollback por tag.

**Formato da tag:** `prod-v{BUILD_ID}-{YYYYMMDD}`

**Exemplos:** `prod-v42-20260404`, `prod-v43-20260405`

**Snippet bash para o pipeline ADO:**

```bash
# Executado apos deploy bem-sucedido em PRD
TAG_NAME="prod-v$(Build.BuildId)-$(date +%Y%m%d)"

git config user.email "cicd@contoso.com"
git config user.name  "Pipeline CI/CD"
git tag -a "$TAG_NAME" -m "Deploy PRD build $(Build.BuildId) - $(Build.SourceBranchName)"
git push origin "$TAG_NAME"

echo "Tag criada: $TAG_NAME"
```

**Tarefa ADO equivalente:**

```yaml
- script: |
    TAG="prod-v$(Build.BuildId)-$(date +%Y%m%d)"
    git config user.email "cicd@contoso.com"
    git config user.name "Pipeline CI/CD"
    git tag -a "$TAG" -m "Deploy PRD build $(Build.BuildId)"
    git push origin "$TAG"
  displayName: "Criar Git Tag de producao"
  condition: and(succeeded(), eq(variables['AMBIENTE'], 'PRD'))
```

---

### 2.6 Compliance as Code

Conjunto de validacoes automatizadas que garantem que os itens Fabric atendem aos padroes de compliance antes de qualquer deploy.

**Arquivo:** [nb_compliance_checks.py](nb_compliance_checks.py)

**Lista de validacoes:**

| # | Validacao | Severidade | Como verifica |
|---|---|---|---|
| 1 | Sem segredos hardcoded em notebooks | Critica | Regex: `password\s*=\s*['"][^'"]+['"]` |
| 2 | Sem segredos hardcoded em pipelines JSON | Critica | Regex em `pipeline-content.json` |
| 3 | Convencao de nomenclatura `[CONF]/[INT]/[PUB]` | Alta | Lista de itens vs. regex de prefixo |
| 4 | JSON de Data Pipelines valido | Alta | `json.loads()` sem excecao |
| 5 | TMDL de Semantic Models valido | Alta | Parse do `expressions.tmdl` |
| 6 | Sem plaintext em Variable Libraries | Alta | Verifica valores que parecem senhas |
| 7 | Placeholders `#{...}#` resolvidos | Media | Regex em todos os arquivos de definicao |
| 8 | Documentacao de items presente | Baixa | Campo `description` preenchido |

**Saida esperada:**

```
[COMPLIANCE] Verificando 18 itens no workspace WS-STG...
[OK]  nb_vendas                  - sem segredos, nomenclatura correta
[OK]  sm_receita                 - TMDL valido, sem placeholders residuais
[FAIL] nb_dados_brutos           - CRITICO: senha hardcoded detectada na linha 42
[WARN] pl_ingest_clientes        - nomenclatura sem prefixo [CONF]/[INT]/[PUB]
---
Resultado: 1 falha critica, 1 aviso. Deploy BLOQUEADO.
```

---

## 3. Developer Experience

### 3.1 CLI Local

Interface de linha de comando para desenvolvedores executarem operacoes CI/CD localmente, sem precisar disparar pipelines ADO.

**Arquivo:** [dev_cli.py](dev_cli.py)

**Comandos disponiveis:**

| Comando | Descricao | Exemplo |
|---|---|---|
| `export` | Exporta workspace para pasta local | `python dev_cli.py export --ws WS-DEV --out ./export/` |
| `validate` | Executa compliance checks localmente | `python dev_cli.py validate --path ./export/` |
| `deploy` | Deploy entre workspaces com backup | `python dev_cli.py deploy --src WS-DEV --dst WS-HML` |
| `status` | Mostra diff entre dois workspaces | `python dev_cli.py status --src WS-DEV --dst WS-HML` |
| `backup` | Cria snapshot do workspace de destino | `python dev_cli.py backup --ws WS-PRD` |
| `sandbox` | Cria workspace sandbox descartavel | `python dev_cli.py sandbox --from WS-DEV --ttl 4h` |

**Uso tipico no dia a dia do desenvolvedor:**

```bash
# Verificar o que mudou antes de criar o PR
python dev_cli.py status --src WS-DEV --dst WS-HML

# Validar compliance antes do push
python dev_cli.py validate --path ./export/

# Testar deploy localmente (dry-run)
python dev_cli.py deploy --src WS-DEV --dst WS-HML --dry-run
```

---

### 3.2 Template Parametrizavel

Melhoria no notebook de setup existente para aceitar um dicionario de configuracao externo, eliminando a necessidade de editar o codigo do notebook para cada novo projeto.

**Arquivo:** [nb_setup_ambiente_cicd.py](nb_setup_ambiente_cicd.py) (existente — melhoria proposta)

**Config dict padrao (a ser externalizado):**

```python
CONFIG = {
    "projeto": "contoso-analytics",
    "ambientes": ["DEV", "HML", "PRD"],
    "capacidade_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "ado_org": "https://dev.azure.com/contoso",
    "ado_projeto": "FabricCI",
    "ado_repo": "fabric-workspaces",
    "grupos_aad": {
        "devs":    "grp-fabric-devs@contoso.com",
        "leads":   "grp-fabric-leads@contoso.com",
        "pos":     "grp-fabric-pos@contoso.com"
    },
    "keyvault_url": "https://kv-contoso-cicd.vault.azure.net/",
    "notificacoes": {
        "teams_webhook": "https://contoso.webhook.office.com/..."
    }
}
```

---

### 3.3 Sandbox Descartavel

Workspace temporario criado automaticamente para testes isolados, com tempo de vida (TTL) configuravel e limpeza automatica apos expiracao.

**Implementacao:** comando `sandbox` do [dev_cli.py](dev_cli.py)

**Fluxo:**

```
1. Cria workspace "SANDBOX-{user}-{timestamp}"
2. Copia itens do workspace fonte (DEV)
3. Aplica parametros do ambiente DEV
4. Registra TTL em tag de metadata do workspace
5. Job agendado (ADO Scheduled Pipeline) limpa sandboxes expirados
```

**Funcoes PyFabricOps usadas:**

```python
from pyfabricops import create_workspace, delete_workspace, copy_item

# Criar sandbox
ws = create_workspace(display_name=f"SANDBOX-{user}-{ts}", capacity_id="...")

# Copiar itens
for item in list_items(workspace_id=source_ws_id):
    copy_item(item_id=item["id"], source_workspace_id=source_ws_id,
              target_workspace_id=ws["id"])

# Cleanup apos TTL
delete_workspace(workspace_id=ws["id"])
```

---

### 3.4 Documentacao Viva

Geracao automatica de documentacao dos workspaces Fabric (inventario de itens, esquema de datasets, lineage) diretamente a partir dos metadados da API, mantendo a documentacao sempre sincronizada com o estado real.

**Arquivo:** [nb_docs_vivos.py](nb_docs_vivos.py)

**O que e documentado automaticamente:**

- Inventario completo de itens por workspace (tipo, nome, criado por, ultima modificacao)
- Esquema das tabelas dos Semantic Models (via DMV `$SYSTEM.TMSCHEMA_COLUMNS`)
- Grafico de lineage (quais pipelines alimentam quais datasets)
- Parametros e placeholders de cada tipo de objeto
- Conexoes utilizadas por workspace

**Saida:** arquivo Markdown gerado e commitado automaticamente no repositorio Git a cada deploy bem-sucedido.

---

### 3.5 Onboarding Automatizado

Notebook que configura o ambiente completo de um novo desenvolvedor em menos de 5 minutos, incluindo permissoes, acesso ao Git, variaveis de ambiente e validacao de conectividade.

**Arquivo:** [nb_onboarding.py](nb_onboarding.py)

**Passos automatizados:**

```
1. Valida que o usuario existe no Azure AD
2. Adiciona o usuario ao workspace DEV como Contributor
3. Configura acesso ao repositorio ADO (add como Reader no projeto)
4. Cria arquivo .env local com template (sem segredos reais)
5. Valida conectividade: GET /v1/myorg/admin/workspaces
6. Exibe checklist de proximos passos manuais
```

---

### 3.6 Pre-commit Hooks

Validacoes automaticas executadas no `git commit` local, impedindo que codigo com problemas de compliance chegue ao repositorio.

**Arquivos:**
- [pre-commit-config-exemplo.yaml](pre-commit-config-exemplo.yaml)
- [validate_hooks.py](validate_hooks.py)

**Hooks configurados:**

```yaml
# pre-commit-config-exemplo.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-json
      - id: check-yaml
      - id: detect-private-key

  - repo: local
    hooks:
      - id: validate-fabric-items
        name: Validar itens Fabric (compliance basico)
        entry: python validate_hooks.py
        language: python
        pass_filenames: false
        files: \.(py|json|tmdl|pq)$

      - id: ruff-check
        name: Ruff lint
        entry: uv run ruff check
        language: system
        types: [python]

      - id: ruff-format
        name: Ruff format
        entry: uv run ruff format --check
        language: system
        types: [python]
```

**Instalacao:**

```bash
pip install pre-commit
pre-commit install
# Testar sem commit
pre-commit run --all-files
```

---

## 4. Escalabilidade

### 4.1 Deploy Incremental (somente itens alterados)

Em vez de redeployar todos os itens do workspace, comparar o estado atual com o ultimo deploy e aplicar apenas as diferencas (added, modified, deleted).

**Arquivos:**
- [GUIA_ESCALABILIDADE.md](GUIA_ESCALABILIDADE.md)
- [templates/deploy_incremental.py](templates/deploy_incremental.py)

**Algoritmo de diff:**

```python
# Pseudocodigo do deploy incremental
snapshot_atual  = get_workspace_items_hashes(workspace_source)
snapshot_ultimo = load_last_deploy_snapshot(workspace_target)

added    = snapshot_atual.keys() - snapshot_ultimo.keys()
deleted  = snapshot_ultimo.keys() - snapshot_atual.keys()
modified = {k for k in snapshot_atual if
            k in snapshot_ultimo and
            snapshot_atual[k] != snapshot_ultimo[k]}

# Aplica somente o diff
deploy_items(added | modified)
delete_items(deleted)
save_snapshot(snapshot_atual, workspace_target)
```

---

### 4.2 Deploy Paralelo por Tipo de Item

Executar o deploy de diferentes tipos de item em paralelo (Notebooks, Semantic Models, Data Pipelines) para reduzir o tempo total de deploy em workspaces grandes.

**Arquivo:** [templates/deploy_incremental.py](templates/deploy_incremental.py)

**Ordem de dependencia (deve ser respeitada mesmo com paralelismo):**

```
1. Conexoes e Lakehouses (sem dependencias)
2. Semantic Models (dependem de Lakehouses)
3. Notebooks e Data Pipelines (dependem de Semantic Models)
4. Reports (dependem de Semantic Models)
```

**Implementacao com ThreadPoolExecutor:**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

grupos_paralelos = [
    [item for item in items if item["type"] == "Notebook"],
    [item for item in items if item["type"] == "DataPipeline"],
]

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(deploy_item, item): item
               for grupo in grupos_paralelos
               for item in grupo}
    for future in as_completed(futures):
        item = futures[future]
        print(f"[OK] {item['type']}: {item['displayName']}")
```

---

### 4.3 Gerenciamento de Capacidade

Monitorar o uso de CUs (Capacity Units) antes e durante o deploy para evitar throttling ou suspensao da capacidade.

**Arquivo:** [GUIA_ESCALABILIDADE.md](GUIA_ESCALABILIDADE.md)

**Boas praticas:**

| Pratica | Descricao |
|---|---|
| Janela de deploy | Agendar deploys pesados fora do horario de pico |
| Pause/Resume | Pausar itens nao criticos antes de refresh em massa |
| Smoothing | Distribuir refreshes ao longo do tempo (`time.sleep(30)` entre batches) |
| Monitoramento | Verificar `capacityMetrics` via API antes de iniciar deploy em PRD |

---

### 4.4 Cache de Token e Connection Pooling

Evitar overhead de autenticacao repetida em operacoes em massa reutilizando tokens e conexoes ja estabelecidas.

**Arquivo:** [GUIA_ESCALABILIDADE.md](GUIA_ESCALABILIDADE.md)

**Ja implementado no PyFabricOps:** o modulo `api/auth.py` possui cache de token por sessao. Para operacoes de longa duracao, verificar o TTL do token antes de cada batch e renovar se necessario.

```python
from pyfabricops.api.auth import get_token, is_token_expired

token = get_token()
for batch in batches:
    if is_token_expired(token):
        token = get_token(force_refresh=True)
    deploy_batch(batch, token=token)
```

---

### 4.5 Multi-Tenant e Multi-Regiao

Suporte a cenarios onde DEV, HML e PRD estao em tenants ou regioes Azure diferentes.

**Arquivo:** [GUIA_ESCALABILIDADE.md](GUIA_ESCALABILIDADE.md)

**Configuracao por ambiente:**

```python
AMBIENTES = {
    "DEV": {
        "tenant_id":  "tenant-dev-guid",
        "fabric_url": "https://api.fabric.microsoft.com",
        "regiao":     "brazilsouth"
    },
    "PRD": {
        "tenant_id":  "tenant-prd-guid",
        "fabric_url": "https://api.fabric.microsoft.com",
        "regiao":     "eastus2"
    }
}
```

---

### 4.6 Observabilidade e Metricas de Pipeline

Dashboard centralizado com metricas de saude dos pipelines CI/CD: frequencia de deploy, taxa de sucesso, tempo medio de deploy, itens mais alterados.

**Arquivo:** [GUIA_ESCALABILIDADE.md](GUIA_ESCALABILIDADE.md)

**Metricas recomendadas (exportar para Log Analytics):**

| Metrica | Formula | Meta |
|---|---|---|
| Taxa de sucesso | `deploys_ok / deploys_total * 100` | > 95% |
| Tempo medio de deploy | `media(duration_seconds)` por ambiente | < 5 min (DEV), < 15 min (PRD) |
| MTTR (tempo medio de recuperacao) | `media(tempo_entre_falha_e_proximo_sucesso)` | < 30 min |
| Frequencia de deploy | Deploys por semana por ambiente | Referencia para maturidade |
| Itens mais alterados | Ranking por numero de updates | Identifica instabilidade |

---

## Tabela de Prioridades

| # | Item | Secao | Prioridade | Esforco | Impacto |
|---|---|---|---|---|---|
| 1.1 | Deploy com Backup Snapshot | Robustez | **Alta** | Medio | Muito Alto |
| 1.2 | Deploy Atomico com Dry-Run | Robustez | **Alta** | Baixo | Alto |
| 1.3 | Health Checks Pre e Pos-Deploy | Robustez | **Alta** | Medio | Alto |
| 2.6 | Compliance as Code | Governanca | **Alta** | Medio | Alto |
| 2.1 | Audit Trail Automatizado | Governanca | **Alta** | Baixo | Alto |
| 1.6 | Integracao com Azure Key Vault | Robustez | **Alta** | Alto | Muito Alto |
| 2.2 | Politica de Aprovacao por Ambiente | Governanca | **Alta** | Baixo | Alto |
| 3.6 | Pre-commit Hooks | Dev Experience | **Alta** | Baixo | Medio |
| 1.4 | Retry com Idempotencia | Robustez | **Alta** | Baixo | Alto |
| 2.3 | RBAC Granular por Workspace | Governanca | Media | Medio | Alto |
| 3.1 | CLI Local | Dev Experience | Media | Alto | Alto |
| 4.1 | Deploy Incremental | Escalabilidade | Media | Alto | Alto |
| 1.5 | Notificacoes de Resultado | Robustez | Media | Baixo | Medio |
| 2.5 | Change Tracking com Git Tags | Governanca | Media | Baixo | Medio |
| 3.4 | Documentacao Viva | Dev Experience | Media | Medio | Medio |
| 4.2 | Deploy Paralelo por Tipo | Escalabilidade | Media | Alto | Medio |
| 4.6 | Observabilidade e Metricas | Escalabilidade | Media | Alto | Alto |
| 2.4 | Classificacao e Protecao de Dados | Governanca | Media | Medio | Alto |
| 3.2 | Template Parametrizavel | Dev Experience | Media | Baixo | Medio |
| 3.5 | Onboarding Automatizado | Dev Experience | Baixa | Medio | Medio |
| 3.3 | Sandbox Descartavel | Dev Experience | Baixa | Alto | Medio |
| 4.3 | Gerenciamento de Capacidade | Escalabilidade | Baixa | Medio | Medio |
| 4.4 | Cache de Token e Connection Pooling | Escalabilidade | Baixa | Baixo | Baixo |
| 4.5 | Multi-Tenant e Multi-Regiao | Escalabilidade | Baixa | Alto | Medio |

### Roadmap sugerido

```
Sprint 1 (Semana 1-2) — Seguranca e Estabilidade
  - 1.6 Key Vault
  - 1.1 Backup Snapshot
  - 1.2 Dry-Run
  - 2.1 Audit Trail
  - 3.6 Pre-commit Hooks

Sprint 2 (Semana 3-4) — Qualidade e Governanca
  - 1.3 Health Checks
  - 1.4 Retry/Idempotencia
  - 2.6 Compliance as Code
  - 2.2 Aprovacao por Ambiente
  - 2.3 RBAC Validacao

Sprint 3 (Semana 5-6) — Produtividade
  - 3.1 CLI Local
  - 1.5 Notificacoes Teams
  - 2.5 Git Tags
  - 4.1 Deploy Incremental
  - 4.6 Observabilidade
```

---

*Documento gerado em 2026-04-04. Versao 1.0.*
*Referencia: [TUTORIAL_CICD_PYFABRICOPS.md](TUTORIAL_CICD_PYFABRICOPS.md) | [CASE_REAL_CICD_AZURE_DEVOPS.md](CASE_REAL_CICD_AZURE_DEVOPS.md)*
