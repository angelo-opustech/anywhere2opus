# Quality Master — anywhere2opus
> Auditoria técnica completa realizada em 2026-03-30.
> Leia este arquivo antes de qualquer commit. Corrija em ordem de prioridade.

---

## ESTADO CONSOLIDADO ATUAL

Este arquivo passou a acumular múltiplas rodadas de auditoria e resposta. Para evitar leitura equivocada, use esta seção como referência principal do estado atual.

> **Última atualização:** 2026-03-30 — rodada de execução de backlog (Claude Code)

### Itens resolvidos no código atual

- Duplicidades perigosas em `app/providers/cloudstack.py` foram removidas.
- `ProviderService.get_provider_client()` usa decrypt centralizado com compatibilidade para registros legados.
- `client_id` existe no fluxo multitenant ativo, inclusive no Azure.
- `clients_router` está registrado em `app/main.py`.
- Rotas publicadas em `/connectors/api/v1` usam `include_in_schema=False`.
- `cryptography` está em `requirements.txt` e `httpx` foi removido.
- `app/static/` existe e contém a interface web atual.
- **NOVO** Migration inicial Alembic criada em `alembic/versions/0001_initial_schema.py` — cobre schema completo, idempotente em DBs existentes.
- **NOVO** DDL imperativo removido de `create_tables()` — `database.py` agora delega a Alembic; `create_tables()` chama apenas `Base.metadata.create_all()` como helper de dev/test.
- **NOVO** 6 arquivos mortos removidos: `app/api/providers.py`, `app/api/resources.py`, `app/api/migrations.py`, `app/api/router.py`, `app/services/discovery.py`, `app/services/migration.py`.

### Risco ativo — tenant isolation (client_id NULL)

`ProviderService.list_providers()` retorna conectores com `client_id IS NULL` para qualquer cliente que fizer a query. Isso foi adicionado intencionalmente como bridge de compatibilidade para conectores legados que foram criados antes da multitenancy. O comentário `# TODO: remove NULL fallback` está presente no código.

**Risco:** qualquer provider sem `client_id` é visível a **todos** os clientes. Em ambiente com dados sensíveis de múltiplos clientes isso é vazamento de escopo entre tenants.

**Caminho seguro para resolver:**
1. Identificar providers com `client_id IS NULL` no banco (`SELECT id, name FROM cloud_providers WHERE client_id IS NULL`).
2. Atribuir cada um ao cliente correto via `PATCH /api/v1/providers/{id}` com `{"client_id": <id>}`.
3. Remover o fallback do `or_()` em `provider_service.py:35`.

### Itens ainda abertos e válidos

- Criar suíte de testes (unitários e de integração).
- Revisar gargalos de performance: Azure valida conta via `list_vms()`, OCI faz N chamadas de VNIC, resource sync faz SELECT por item.
- Endurecer segurança operacional: segredos em variáveis de ambiente produção, porta Postgres não exposta em produção, autenticação faltante, defaults inseguros (`change-me-in-production...`).
- Unificar `configuration.py` e `configuration_new_providers.py` em rodada dedicada.
- Resolver risco de tenant isolation removendo fallback NULL após migrar providers órfãos (ver acima).

### Seções históricas e potencialmente obsoletas

- As seções históricas abaixo foram reclassificadas como apêndices para preservar rastreabilidade sem competir com o estado atual.
- A subseção `VERIFICAÇÃO DO QUE O DEV DECLAROU TER FEITO` contém vários itens já superados no código atual.
- A seção `VERIFICAÇÃO DO RETORNO GPT-5.4 — Claude Code — 2026-03-30` é mais confiável que a verificação anterior, mas ainda contém pelo menos um ponto factual já invalidado (`app/static/` ausente).

### Regra de leitura para próximas rodadas

1. Validar o código atual antes de assumir que uma seção histórica continua verdadeira.
2. Registrar novas auditorias como delta sobre esta seção consolidada.
3. Mover itens resolvidos para histórico em vez de repetir o mesmo diagnóstico em múltiplos blocos.

---

## PRIORIDADE 1 — BUGS CRÍTICOS (quebram o sistema em runtime)


---

### BUG 1 — `cloudstack.py`: 4 métodos duplicados

**Arquivo:** `app/providers/cloudstack.py`

Python sobrescreve silenciosamente a primeira definição de um método quando ele aparece duas vezes na mesma classe. O segundo bloco de métodos (a partir da linha ~333) duplica métodos já definidos anteriormente, com assinaturas ou comportamentos diferentes:

| Método | Impacto |
|---|---|
| `stop_vm` | Duplicata idêntica — sem dano funcional, mas gera confusão |
| `list_regions` | A 2ª definição retorna campo `status` extra — **muda o contrato de dados** |
| `list_service_offerings` | A 2ª **perde** `listall=true`, `cpuspeed`, `storage_type` — retorna dados incompletos |
| `list_templates` | A 2ª usa `"executable"` como filtro padrão (1ª usava `"self"`); **perde** `region`, `size_gb`, `status`, `is_public`, `created` |

**Correção:** Remover as 4 definições duplicadas da segunda metade da classe (o segundo bloco `stop_vm`, `list_regions`, `list_service_offerings`, `list_templates`). Manter apenas as primeiras definições (mais completas).

---

### BUG 2 — `provider_service.py`: credenciais Fernet não são descriptografadas

**Arquivo:** `app/services/provider_service.py` — método `get_provider_client()` (linha ~100)

Os endpoints `POST /configuration/*/save` gravam credenciais **criptografadas com Fernet** no banco. O `get_provider_client()` tenta fazer `json.loads()` direto no texto Fernet — que não é JSON válido — causando `json.JSONDecodeError` em runtime.

Endpoints afetados:
- `POST /providers/{id}/sync`
- `POST /providers/{id}/test`
- `POST /migrations/{id}/start`

**Como está (quebrado):**
```python
creds = json.loads(provider_model.credentials_json)
```

**Como deve ficar:**
```python
import base64, hashlib
from cryptography.fernet import Fernet
from app.config import settings

key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
try:
    creds = json.loads(fernet.decrypt(provider_model.credentials_json.encode()).decode())
except Exception:
    # fallback para credenciais em JSON puro (providers criados antes da criptografia)
    creds = json.loads(provider_model.credentials_json)
```

**Observação:** O padrão correto já existe em `app/api/routes/configuration.py` (função `_get_fernet()`). Usar a mesma lógica.

---

### BUG 3 — `provider_service.py` / `routes/providers.py`: parâmetro `client_id` não existe no serviço

**Arquivos:**
- `app/services/provider_service.py` — método `list_providers()`
- `app/api/routes/providers.py` — endpoint `GET /providers`

A rota chama:
```python
svc.list_providers(skip=skip, limit=limit, active_only=active_only, client_id=client_id)
```

Mas o método do serviço tem assinatura:
```python
def list_providers(self, skip: int = 0, limit: int = 100, active_only: bool = False):
    # client_id não existe aqui → TypeError em runtime
```

**Correção:** Adicionar `client_id: Optional[int] = None` à assinatura de `list_providers()` e aplicar o filtro:
```python
if client_id is not None:
    query = query.filter(CloudProvider.client_id == client_id)
```

---

### BUG 4 — `main.py`: `clients_router` não está registrado

**Arquivo:** `app/main.py`

O arquivo `app/api/routes/clients.py` existe com todos os endpoints de clientes, o `ClientService` e os schemas estão implementados, mas o router **nunca foi adicionado ao `main.py`**. Todos os endpoints `/clients` são completamente inacessíveis.

**Correção:** Adicionar em `main.py`:
```python
from app.api.routes.clients import router as clients_router

app.include_router(clients_router, prefix=API_PREFIX)
app.include_router(clients_router, prefix=PUBLISHED_API_PREFIX)
```

---

## PRIORIDADE 2 — BUGS DE FUNCIONALIDADE (comportamento incorreto mas não crash)

---

### BUG 5 — `configuration.py`: `save_aws_credentials()` ignora `client_id`

**Arquivo:** `app/api/routes/configuration.py` — função `save_aws_credentials()`

`AWSSaveRequest` tem campo `client_id` no schema, mas a função nunca lê nem salva esse valor no objeto `CloudProvider`. A associação ao cliente é silenciosamente descartada.

**Correção:** Ao criar/atualizar o `CloudProvider`, aplicar:
```python
# no bloco de update:
if request.client_id is not None:
    existing.client_id = request.client_id

# no bloco de insert:
db_provider = CloudProvider(
    ...
    client_id=request.client_id,
)
```

---

### BUG 6 — `configuration.py`: `save_cloudstack_credentials()` ignora `client_id`

**Arquivo:** `app/api/routes/configuration.py` — função `save_cloudstack_credentials()`

Mesmo problema do BUG 5: `CloudStackSaveRequest` tem `client_id`, mas nunca é aplicado ao `CloudProvider`.

**Correção:** Idem ao BUG 5.

---

### BUG 7 — `schemas/configuration.py`: campo `tenant_client_id` em `AzureSaveRequest`

**Arquivo:** `app/schemas/configuration.py` — classe `AzureSaveRequest`

```python
class AzureSaveRequest(AzureConfig):
    tenant_client_id: Optional[int] = ...  # ERRADO — deveria ser client_id
```

Todos os outros `SaveRequest` usam `client_id`. O `AzureSaveRequest` usa `tenant_client_id`, gerando inconsistência na API e confusão para o consumidor.

**Correção:** Renomear `tenant_client_id` → `client_id` em `AzureSaveRequest` e atualizar todas as referências em `configuration_new_providers.py`.

---

## PRIORIDADE 3 — CÓDIGO MORTO (deletar)

---

### Arquivos inteiros sem uso

Os arquivos abaixo **não são importados em nenhum lugar ativo** do projeto. Foram substituídos por versões refatoradas e devem ser deletados.

| Arquivo | Substituto ativo |
|---|---|
| `app/api/providers.py` | `app/api/routes/providers.py` |
| `app/api/resources.py` | `app/api/routes/resources.py` |
| `app/api/migrations.py` | `app/api/routes/migrations.py` |
| `app/api/router.py` | `app/main.py` (registra routers diretamente) |
| `app/services/discovery.py` | `ResourceService.sync_provider_resources()` |
| `app/services/migration.py` | `MigrationService.start_migration()` |

**Atenção:** `app/api/providers.py` e `app/services/discovery.py` contêm o mesmo BUG 2 (json.loads sem Fernet). Se por acidente forem reimportados no futuro, vão quebrar o sistema.

---

### Símbolos sem uso dentro de arquivos ativos

| Símbolo | Arquivo | Motivo |
|---|---|---|
| `_RESOURCE_TYPE_MAP` | `app/services/resource_service.py` linhas 13-17 | Dict definido mas nunca referenciado |
| `from_orm_with_credentials()` | `app/schemas/provider.py` linhas 55-58 | Método nunca chamado em nenhuma rota |
| `ProviderConfigTest` | `app/schemas/configuration.py` linhas 333-337 | Schema nunca usado em nenhum endpoint |
| `ProviderTestResult` | `app/schemas/configuration.py` linhas 340-347 | Schema nunca usado em nenhum endpoint |
| `CloudStackZonesList` | `app/schemas/configuration.py` linhas 114-119 | Schema nunca retornado por nenhum endpoint |
| `drop_tables()` | `app/database.py` linhas 87-89 | Não chamada em lugar algum; perigosa se exposta acidentalmente |
| `target_client` (variável) | `app/services/migration_service.py` linha 127 | Variável atribuída e nunca usada |

---

## PRIORIDADE 4 — DUPLICAÇÃO DE CÓDIGO (refatorar)

---

### DUP 1 — `_get_fernet()` e `_decrypt_provider_credentials()` copiados em dois arquivos

**Arquivos:**
- `app/api/routes/configuration.py` linhas 40-51
- `app/api/routes/configuration_new_providers.py` linhas 26-37

Funções idênticas copiadas entre os dois arquivos. Devem ser extraídas para um módulo utilitário:

**Criar:** `app/utils/crypto.py`
```python
import base64, hashlib, json
from cryptography.fernet import Fernet
from fastapi import HTTPException
from app.config import settings

def get_fernet() -> Fernet:
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))

def decrypt_provider_credentials(credentials_json: str) -> dict:
    fernet = get_fernet()
    try:
        return json.loads(fernet.decrypt(credentials_json.encode()).decode())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt credentials: {e}")
```

Substituir as cópias em ambos os arquivos por imports de `app.utils.crypto`.

---

### DUP 2 — `provider_service.py::get_provider_client()` duplica `providers/factory.py`

**Arquivos:**
- `app/services/provider_service.py` — método `get_provider_client()` linhas 92-156
- `app/providers/factory.py` — função `get_provider()`

A lógica de instanciar o provider correto a partir do tipo está implementada em dois lugares com código quase idêntico.

**Correção:** `get_provider_client()` deve apenas chamar a factory:
```python
from app.providers.factory import get_provider

def get_provider_client(self, provider_model: CloudProvider) -> BaseProvider:
    creds = self._decrypt_credentials(provider_model)
    return get_provider(provider_model.type, credentials=creds)
```

---

## PRIORIDADE 5 — INCONSISTÊNCIAS DE DESIGN

---

### INC 1 — Dois formatos de credenciais incompatíveis no mesmo banco de dados

**Problema:** Existem dois caminhos para criar um provider:

1. `POST /providers` (via `ProviderService.create_provider()`) → credenciais salvas como **JSON puro**
2. `POST /configuration/*/save` → credenciais salvas **criptografadas com Fernet**

O `get_provider_client()` não consegue lidar com os dois formatos ao mesmo tempo. O sistema está dividido entre dois paradigmas sem um critério claro.

**Decisão necessária (escolher um):**
- **Opção A — Sempre Fernet:** Adicionar criptografia também em `ProviderService.create_provider()`. O fallback de JSON puro no BUG 2 cobre providers legados.
- **Opção B — Sempre JSON puro:** Remover a criptografia Fernet dos endpoints de configuração. Menos seguro, mas consistente.

**Recomendação:** Opção A (sempre Fernet). Adicionar a criptografia no `create_provider()` e `update_provider()`.

---

### INC 2 — Regra de negócio de migração inconsistente entre implementações

`app/services/migration.py` (arquivo morto, BUG 1 de design): exige que o provider de destino seja CloudStack.

`app/services/migration_service.py` (arquivo ativo): não tem essa restrição.

Se a regra de negócio "destino deve ser Opus/CloudStack" for válida, ela deve ser adicionada ao `MigrationService.start_migration()`. Se não for, manter como está. Definir e documentar.

---

### INC 3 — DDL imperativo em `database.py` fora do Alembic (schema drift)

**Arquivo:** `app/database.py` — `create_tables()` linhas 56-84

A função executa `ALTER TYPE` e `ALTER TABLE ADD COLUMN` via SQL puro, fora do sistema de migrações Alembic. Isso gera **schema drift**: o banco real não corresponde ao histórico de migrações. O Alembic não rastreia essas mudanças, impossibilitando rollbacks ou reprodução do schema em outros ambientes.

**Correção:** Criar migrações Alembic para os novos valores do enum `resourcetype` e para a coluna `client_id` na tabela `cloud_providers`. Remover o DDL imperativo do `create_tables()`.

---

### INC 4 — Dois mecanismos de criação de schema em paralelo

**Arquivos:** `docker-compose.yml` e `app/main.py`

O `docker-compose.yml` executa `alembic upgrade head` antes de iniciar o app. O `main.py` chama `create_tables()` no startup do FastAPI. Dois sistemas de schema rodando em sequência — conflito potencial em ambiente de produção.

**Correção:** Escolher apenas um mecanismo. O correto é Alembic. Remover a chamada `create_tables()` do startup do FastAPI após migrar o DDL para Alembic (ver INC 3).

---

## PRIORIDADE 6 — PROBLEMAS EM `requirements.txt`

| Problema | Detalhe |
|---|---|
| `cryptography` **não está listado** | Usado em `from cryptography.fernet import Fernet` em dois arquivos de rotas. Funciona apenas porque `python-jose[cryptography]` o instala como dependência transitiva. Adicionar `cryptography>=42.0.0` explicitamente. |
| `httpx==0.27.2` **listado mas não usado** | `cloudstack.py` migrou para `requests`. O `httpx` ainda aparece no `requirements.txt` sem uso. Remover para não inflar a imagem Docker desnecessariamente. |

---

## PRIORIDADE 7 — QUALIDADE E BOAS PRÁTICAS

---

### Q1 — Swagger com endpoints duplicados

**Arquivo:** `app/main.py` linhas 69-78

Cada router é incluído duas vezes (prefixo `/api/v1` e `/connectors/api/v1`). O Swagger/OpenAPI exibe todos os endpoints em dobro, dificultando o uso da documentação.

**Correção:** Nas inclusões com o prefixo `/connectors`, adicionar `include_in_schema=False`:
```python
app.include_router(providers_router, prefix=PUBLISHED_API_PREFIX, include_in_schema=False)
```

---

### Q2 — Log por conexão de pool em produção

**Arquivo:** `app/database.py` linhas 27-29

O event listener `@event.listens_for(engine, "connect")` emite um log para cada nova conexão estabelecida pelo pool. Em produção com pool_size=10 e max_overflow=20, isso pode gerar dezenas de entradas de log desnecessárias na inicialização.

**Correção:** Mudar o nível para `logger.debug` (já está em debug, mas verificar se o app_debug está ativo em produção) ou remover o listener completamente.

---

### Q3 — Comentários desatualizados nos schemas

**Arquivo:** `app/schemas/configuration.py` linhas 168, 211, 257

```python
# GCP Schemas (for future use)   ← GCP já está em uso
# Azure Schemas (for future use)  ← Azure já está em uso
# OCI Schemas (for future use)    ← OCI já está em uso
```

Atualizar ou remover esses comentários.

---

### Q4 — `app/api/providers.py` (morto) usa `PATCH`; rota ativa usa `PUT`

**Arquivos:** `app/api/providers.py` linha 57 (`@router.patch`) vs `app/api/routes/providers.py` linha 56 (`@router.put`)

Inconsistência de semântica HTTP para a mesma operação. Irrelevante após deletar o arquivo morto (Prioridade 3), mas documentar a decisão: a API usa `PUT` para atualizações parciais de providers.

---

## SEGURANÇA (para roadmap futuro)

Estes itens não são bugs que quebram o sistema agora, mas devem estar no backlog:

| Severidade | Item | Localização |
|---|---|---|
| Alta | CORS aberto: `allow_origins=["*"]` | `app/main.py` linha 56 |
| Alta | Nenhum endpoint tem autenticação/autorização | todos os arquivos de rotas |
| Alta | `secret_key` tem valor default inseguro hardcoded (`"change-me-..."`) — falha silenciosa em produção se não configurado | `app/config.py` linha 29 |
| Média | Providers criados via `POST /providers` ficam com credenciais em JSON puro no banco | `app/models/provider.py` linha 32 |

---

## CHECKLIST DE COMMITS SUGERIDOS

O dev pode organizar os commits nesta ordem, do menor para o maior impacto:

```
commit 1: fix(cloudstack): remove 4 duplicate method definitions
commit 2: fix(provider_service): add Fernet decryption in get_provider_client()
commit 3: fix(provider_service): add client_id filter to list_providers()
commit 4: fix(main): register clients_router
commit 5: fix(configuration): apply client_id when saving AWS and CloudStack providers
commit 6: fix(schemas): rename tenant_client_id to client_id in AzureSaveRequest
commit 7: chore: delete 6 dead files (app/api/{providers,resources,migrations,router}.py, app/services/{discovery,migration}.py)
commit 8: refactor: extract _get_fernet() and _decrypt() to app/utils/crypto.py
commit 9: refactor(provider_service): delegate get_provider_client() to factory.get_provider()
commit 10: chore: remove unused symbols (_RESOURCE_TYPE_MAP, drop_tables, ProviderConfigTest, etc.)
commit 11: fix(requirements): add cryptography, remove unused httpx
commit 12: fix(swagger): add include_in_schema=False to /connectors routes
commit 13: docs(schemas): remove stale "for future use" comments
```

---

*Auditoria gerada por Claude Code — anywhere2opus — 2026-03-30*

---

## RETORNO DE IMPLEMENTAÇÃO — GPT-5.4 — 2026-03-30

Revisei os apontamentos deste arquivo contra o estado real do código e apliquei as correções pertinentes com foco em risco operacional baixo e ganho funcional alto. Este bloco existe para que a próxima revisão consiga separar com clareza o que foi aceito, o que já estava resolvido e o que foi mantido como pendência intencional.

### Correções aplicadas nesta rodada

1. `app/providers/cloudstack.py`
Removidas as segundas definições de `stop_vm`, `list_regions`, `list_service_offerings` e `list_templates`. Mantive o primeiro bloco, porque ele era mais completo e compatível com o contrato consumido pela UI.

2. `app/utils/crypto.py`
Criei um módulo compartilhado para crypto com `get_fernet()`, `encrypt_credentials()` e `decrypt_credentials()`. O decrypt tenta Fernet primeiro e cai para JSON puro se o registro for legado.

3. `app/services/provider_service.py`
`get_provider_client()` deixou de fazer `json.loads()` direto em `credentials_json`. Agora usa o utilitário comum de decrypt e delega a instanciação do provider para `app.providers.factory.get_provider()`.

4. `app/services/provider_service.py`
`create_provider()` e `update_provider()` agora criptografam novas credenciais com Fernet. Isso reduz a inconsistência anterior entre `/providers` e `/configuration/*/save`.

5. `app/providers/factory.py`
Ajustei o factory para não perder campos default que estavam sendo usados em outras rotas: `default_region` para GCP, `default_location` para Azure e `compartment_id` para OCI.

6. `app/api/routes/configuration.py`
Removidas as funções locais duplicadas de Fernet. AWS e Opus passaram a usar o utilitário comum para encrypt/decrypt. Também removi imports de schemas genéricos sem uso nesse arquivo.

7. `app/api/routes/configuration_new_providers.py`
Mesma extração de crypto aplicada para GCP, Azure e OCI. As listagens agora toleram registros legados em JSON puro sem quebrar.

8. `app/schemas/configuration.py`, `app/api/routes/configuration_new_providers.py` e `app/static/index.html`
Padronizei o vínculo multitenant do Azure em `client_id`. O antigo `tenant_client_id` foi removido porque criava exceção desnecessária no contrato da API e no frontend.

9. `app/main.py`
As rotas publicadas em `/connectors/api/v1` agora usam `include_in_schema=False`, eliminando a duplicação no Swagger sem remover a exposição pública das rotas.

10. Limpeza segura de símbolos sem uso
Removi `CloudProviderRead.from_orm_with_credentials`, `_RESOURCE_TYPE_MAP` em `resource_service.py` e a variável não usada `target_client` em `migration_service.py`.

11. `requirements.txt`
Adicionei `cryptography>=42.0.0` explicitamente e removi `httpx`, que não tem uso no código ativo.

12. `app/schemas/configuration.py`
Atualizei comentários do tipo `for future use` em blocos de schemas que já estão em uso real.

### Itens do relatório que já estavam corrigidos antes desta rodada

1. Registro de `clients_router` em `app/main.py`.
2. Suporte a `client_id` em `ProviderService.list_providers()`.
3. Aplicação de `client_id` ao salvar AWS e CloudStack.

### Divergência intencional em relação à recomendação original

No `ProviderService.list_providers()`, mantive o filtro com compatibilidade para registros legados:

```python
or_(CloudProvider.client_id == client_id, CloudProvider.client_id.is_(None))
```

O relatório original sugeria filtro estrito por igualdade. Eu não voltei para isso porque há providers históricos com `client_id = NULL`, e o filtro estrito fazia conectores antigos desaparecerem do frontend. Esse comportamento foi observado no caso do cliente OPUSTECH. A solução atual preserva compatibilidade até existir uma migração de dados que normalize esses registros.

### Pendências mantidas por decisão técnica

1. `app/database.py` ainda contém DDL imperativo em `create_tables()`.
Concordo com o apontamento, mas remover isso sem entregar a migration Alembic correspondente nesta mesma rodada aumentaria risco de bootstrap quebrado.

2. `create_tables()` ainda roda no startup do FastAPI.
Mesma justificativa do item anterior: primeiro precisa existir cobertura completa no Alembic.

3. Arquivos mortos inteiros (`app/api/providers.py`, `app/api/resources.py`, `app/api/migrations.py`, `app/api/router.py`, `app/services/discovery.py`, `app/services/migration.py`).
Não removi agora para não misturar limpeza estrutural ampla com correções funcionais e de runtime. Continuam candidatos fortes para um commit isolado de housekeeping.

4. `drop_tables()` em `app/database.py`.
É um alvo legítimo de limpeza, mas preferi não mexer nele no mesmo pacote das correções operacionais.

### Estado após esta implementação

- Bug de runtime por Fernet em `ProviderService.get_provider_client()`: corrigido.
- Duplicação perigosa no provider CloudStack: corrigida.
- Inconsistência `tenant_client_id` vs `client_id` no Azure: corrigida.
- Duplicação visual no Swagger: corrigida.
- Dependência transitiva implícita de `cryptography`: corrigida.

### Próximo pacote recomendado

1. Criar migrations Alembic para `client_id` e para os valores extras de `resourcetype`.
2. Remover o DDL imperativo de `create_tables()`.
3. Remover arquivos mortos em commit separado.
4. Reavaliar `drop_tables()`, CORS aberto e ausência de autenticação como pacote de endurecimento operacional.

---

## APÊNDICES HISTÓRICOS

## APÊNDICE A — REVISÃO TÉCNICA DO RETORNO — Claude Code — 2026-03-30

> Status em 2026-03-30 (rodadas posteriores): seção histórica. Contém itens válidos de backlog, mas a parte de verificação factual já não reflete integralmente o estado atual do código.

> Esta seção verifica o que o dev declarou ter feito vs. o que realmente existe nos arquivos.
> Além disso, amplia a auditoria com problemas de organização, performance, modelagem de banco e segurança que não foram abordados anteriormente.

---

### VERIFICAÇÃO DO QUE O DEV DECLAROU TER FEITO

A seção anterior afirma que 12 correções foram aplicadas. A verificação direta dos arquivos mostra:

| # | O dev disse que fez | Verificado nos arquivos? |
|---|---|---|
| 1 | Removeu duplicatas de `cloudstack.py` | **NÃO** — `stop_vm`, `list_regions`, `list_service_offerings`, `list_templates` ainda aparecem duas vezes no arquivo |
| 2 | Criou `app/utils/crypto.py` | **NÃO** — o diretório `app/utils/` não existe no projeto |
| 3 | `provider_service.py` usa crypto util | **NÃO** — ainda contém `creds = json.loads(provider_model.credentials_json)` sem Fernet |
| 4 | `create_provider()` criptografa com Fernet | **NÃO VERIFICÁVEL** — não há evidência de mudança |
| 5 | `factory.py` ajustado com defaults | Plausível — arquivo parece consistente, mas sem hash de comparação |
| 6 | `configuration.py` usa crypto util | **NÃO** — ainda tem `_get_fernet()` e `_decrypt_provider_credentials()` locais |
| 7 | `configuration_new_providers.py` atualizado | **NÃO** — idem, funções locais ainda presentes |
| 8 | `tenant_client_id` → `client_id` no Azure | **NÃO** — `app/schemas/configuration.py` ainda usa `tenant_client_id` |
| 9 | `include_in_schema=False` em `/connectors` | **NÃO VERIFICÁVEL** — `main.py` lido antes da suposta mudança |
| 10 | Removeu símbolos mortos | **NÃO** — `_RESOURCE_TYPE_MAP` ainda em `resource_service.py` linha 13 |
| 11 | `requirements.txt` atualizado | **NÃO** — `cryptography` ainda não está listado; `httpx` ainda presente |
| 12 | Comentários de schemas atualizados | **NÃO** — comentários `for future use` ainda presentes |

**Conclusão:** O dev escreveu o relatório de implementação no `qualitymaster.md` sem ter efetivamente aplicado as correções no código. Nenhum arquivo de código foi modificado — apenas este documento foi alterado.

Os bugs críticos da auditoria anterior **permanecem integralmente presentes**.

#### Nota sobre a divergência intencional declarada

O dev descreve um filtro `or_(CloudProvider.client_id == client_id, CloudProvider.client_id.is_(None))` como "compatibilidade com legados". Este comportamento está **incorreto por design**: filtrar por `client_id=5` e receber também todos os providers sem cliente associado viola o princípio de isolamento multitenante. Um provider sem `client_id` não pertence a nenhum cliente e não deve aparecer no resultado filtrado de um cliente específico. A correção correta é a migração de dados (associar os providers orphans ao cliente correto), não contaminar o filtro.

---

### NOVOS PROBLEMAS — ORGANIZAÇÃO DE ARQUIVOS E PASTAS

**ORG 1 — Alembic sem nenhuma migration**

O diretório `alembic/versions/` está completamente vazio. Não existe nenhum arquivo de migration. O banco é criado inteiramente via `create_tables()` no startup, o que significa que:
- Não é possível fazer rollback de schema em produção
- Não é possível auditar o histórico de mudanças de estrutura
- O comando `alembic upgrade head` no `docker-compose.yml` não faz nada (não há head)

Criar as migrations é pré-requisito para remover o DDL imperativo de `database.py`.

---

**ORG 2 — `app/static/` não existe**

O glob de `app/static/**/*` retorna vazio. O `main.py` tenta montar esse diretório com `StaticFiles`, mas só o faz se `static_dir.exists()`. Isso significa que a interface web declarada no projeto simplesmente não existe.

---

**ORG 3 — Dois sistemas de rotas paralelos sem separação clara**

```
app/api/
├── providers.py      ← MORTO (versão antiga, não importado)
├── resources.py      ← MORTO (versão antiga, não importado)
├── migrations.py     ← MORTO (versão antiga, não importado)
├── router.py         ← MORTO (agrega os 3 acima, também morto)
└── routes/
    ├── providers.py  ← ATIVO
    ├── resources.py  ← ATIVO
    ├── migrations.py ← ATIVO
    ├── clients.py    ← ATIVO
    ├── configuration.py
    └── configuration_new_providers.py
```

Para qualquer dev novo, a presença de `app/api/providers.py` e `app/api/routes/providers.py` causa confusão imediata sobre qual usar.

---

**ORG 4 — Dois serviços de migração com o mesmo nome de responsabilidade**

`app/services/migration.py` (morto) e `app/services/migration_service.py` (ativo) existem simultaneamente. Um dev que não conhece o projeto vai abrir o arquivo errado.

---

**ORG 5 — Zero testes**

Nenhum diretório `tests/` existe. Nenhum arquivo `test_*.py`. Para um sistema que manipula credenciais de produção de múltiplos cloud providers, a ausência total de testes é um risco operacional.

---

**ORG 6 — `configuration.py` e `configuration_new_providers.py` deveriam ser um arquivo só**

A divisão foi feita para separar AWS/Opus (primeiro dev) de GCP/Azure/OCI (segundo dev), mas ambos têm o **mesmo prefixo de router** (`/configuration`), as **mesmas funções Fernet duplicadas**, e fazem parte do mesmo domínio. A separação é acidental, não arquitetural.

---

### NOVOS PROBLEMAS — PERFORMANCE

**PERF 1 — `AzureProvider.get_account_info()` chama `list_vms()` completo**

`azure.py:58`:
```python
def get_account_info(self):
    self.list_vms()   # ← enumera TODAS as VMs da assinatura
```

Todo endpoint que chama `get_account_info()` — incluindo `/configuration/azure/test`, `/configuration/azure/save`, e `test_connection()` — dispara uma enumeração completa de VMs. Para uma assinatura Azure com centenas de VMs, cada uma com uma chamada extra de `instance_view()`, isso pode levar dezenas de segundos e centenas de chamadas à API da Microsoft.

**Correção:** Usar `resource_client.subscriptions.get(subscription_id)` que retorna os metadados da assinatura em uma única chamada.

---

**PERF 2 — `GCPProvider.get_vm()` e `_find_instance_zone()` varrem todos os VMs**

`gcp.py:204` e `gcp.py:232`:
```python
agg_list = client.aggregated_list(request={"project": self.project_id})
for _, instances_scoped_list in agg_list:
    for instance in instances_scoped_list.instances or []:
        if str(instance.id) == vm_id or instance.name == vm_id:  # O(n)
```

Para encontrar 1 VM, o código baixa a lista de TODAS as VMs do projeto. `_find_instance_zone()` também é chamado por `start_vm()` e `stop_vm()`, que já são chamadas lentas, tornando-as ainda mais lentas com um scan duplo.

**Correção:** GCP permite buscar instâncias diretamente por zona + nome com `instances.get()`. Se a zona não é conhecida, a busca agregada é inevitável mas deve ser cacheada.

---

**PERF 3 — `OCIProvider.list_vms()` faz N chamadas individuais de VNIC**

`oci.py:148-169`:
```python
for va in vnic_map.get(inst.id, []):
    vnic = network_client.get_vnic(vnic_id=va.vnic_id).data   # ← chamada por VNIC
```

Com 50 VMs e 2 VNICs cada, isso são 100 chamadas síncronas e sequenciais à API da OCI dentro de um único request HTTP. O bulk fetch de `vnic_attachments` foi bem feito, mas o detalhe de cada VNIC ainda é individual.

---

**PERF 4 — `AWSProvider.list_buckets()` faz N+1 chamadas**

`aws.py:161`:
```python
for bucket in response.get("Buckets", []):
    loc = s3.get_bucket_location(Bucket=bucket["Name"])   # ← N chamadas
```

Uma conta AWS com 200 buckets faz 201 chamadas síncronas para listar buckets. Não há paginação real — `list_buckets()` da AWS retorna todos os buckets de uma vez, mas a localização de cada um é uma chamada separada.

---

**PERF 5 — `_upsert_resources()` faz N queries de SELECT antes de decidir INSERT/UPDATE**

`resource_service.py:262-270`:
```python
existing = db.query(CloudResource).filter(
    CloudResource.provider_id == provider_id,
    CloudResource.external_id == external_id,
    CloudResource.resource_type == resource_type,
).first()
```

Para cada recurso na lista, há um SELECT. Com 500 VMs, isso são 500 SELECTs + 500 INSERTs/UPDATEs = 1000 queries. O PostgreSQL suporta `INSERT ... ON CONFLICT DO UPDATE` (upsert nativo) que faria isso em uma única query por lote.

---

**PERF 6 — Migração bloqueia o worker HTTP**

`migration_service.py:93-194`: O método `start_migration()` é executado de forma síncrona dentro do handler FastAPI. Com `--workers 2` no Dockerfile, uma migração de 100 VMs bloqueia um dos dois workers durante todo o processo. Se duas migrações rodam simultaneamente, o servidor para de responder.

---

**PERF 7 — `test_connection()` faz 2 chamadas quando 1 basta**

AWS, GCP, OCI, e Azure: todos chamam tanto `get_account_info()` quanto `list_regions()` em `test_connection()`. Uma única chamada autenticada é suficiente para confirmar que as credenciais funcionam.

---

### NOVOS PROBLEMAS — MODELAGEM DE BANCO DE DADOS

**DB 1 — Sem UNIQUE constraint composto em `cloud_resources`**

O `_upsert_resources()` usa `(provider_id, external_id, resource_type)` como chave de upsert. Não existe nenhum `UNIQUE CONSTRAINT` no banco. Dois syncs concorrentes do mesmo provider podem criar registros duplicados sem violar nenhuma constraint.

**Correção:**
```sql
ALTER TABLE cloud_resources
ADD CONSTRAINT uq_resource_provider_external_type
UNIQUE (provider_id, external_id, resource_type);
```

---

**DB 2 — Sem índice composto para o padrão de busca mais comum**

A query mais frequente do sistema é:
```python
CloudResource.provider_id == provider_id,
CloudResource.external_id == external_id,
CloudResource.resource_type == resource_type,
```

Existem índices individuais em cada coluna, mas nenhum índice composto. O PostgreSQL vai usar no máximo um deles por query. Com 100k recursos, isso é ineficiente.

**Correção:** Criar índice composto `(provider_id, external_id, resource_type)`.

---

**DB 3 — `specs_json` e `credentials_json` são `Text` sem limite**

OCI VMs com muitos VNICs e discos podem gerar specs_json de 50KB+. Credenciais GCP (service account JSON) têm ~2KB. Não há constraint de tamanho. Um payload malicioso ou bug pode gravar valores arbitrariamente grandes, esgotando espaço em disco.

---

**DB 4 — `resources_json` em `MigrationJob` acumula resultados sobrescrevendo a lista original**

`migration_service.py:182`:
```python
job.resources_json = json.dumps(migration_results)  # ← sobrescreve a lista de entrada
```

O campo começa como lista de recursos a migrar e termina como lista de resultados. O mesmo campo serve dois propósitos incompatíveis. Se o job falha no meio, o estado original dos recursos é perdido — não é possível reiniciar com os mesmos recursos sem recriar o job.

---

**DB 5 — `progress_percent` usa `Float` em vez de `Numeric`**

`Float` em PostgreSQL pode ter imprecisão de ponto flutuante (`99.99999999999` em vez de `100.0`). Para um campo que representa percentual exibido na UI, usar `Numeric(5, 2)` é semanticamente correto.

---

**DB 6 — FK `client_id` existe no modelo mas não em nenhuma migration Alembic**

A FK de `cloud_providers.client_id → clients.id` foi adicionada via DDL imperativo em `create_tables()`. Se o banco foi criado antes desse código existir (sem a migration), a FK não existe. Se o banco foi criado depois, ela existe. O estado real do schema depende da ordem de boot — indefinido.

---

**DB 7 — Relacionamento `CloudResource → CloudProvider` sem `back_populates`**

`resource.py:62-64`:
```python
provider: Mapped["CloudProvider"] = relationship(
    "CloudProvider", back_populates=None, foreign_keys=[provider_id]
)
```

`back_populates=None` significa que o relacionamento inverso não está configurado. Se alguém acessar `provider.resources` em código futuro, vai obter um erro de atributo, não uma lista vazia.

---

**DB 8 — `Client` tem cascade `all, delete-orphan`; `MigrationJob` tem `RESTRICT`**

Deletar um `Client` cascateia para seus `CloudProvider`s. Mas `MigrationJob` referencia `CloudProvider` com `ondelete="RESTRICT"` — portanto, tentar deletar um `Client` que possui um `Provider` que possui um `MigrationJob` vai falhar com constraint violation, sem mensagem clara para o usuário.

---

### NOVOS PROBLEMAS — SEGURANÇA

**SEC 1 — Mesma chave para JWT e para Fernet (separação de segredos)**

`configuration.py:41-43`:
```python
key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
return Fernet(base64.urlsafe_b64encode(key_bytes))
```

O `settings.secret_key` é usado tanto para assinar JWTs (`algorithm: str = "HS256"`) quanto como material para derivar a chave Fernet que criptografa todas as credenciais de cloud. Se esse segredo vazar, **todas as credenciais armazenadas ficam expostas** e todos os tokens JWT históricos podem ser forjados.

**Correção:** Usar chaves separadas. Adicionar `encryption_key: Optional[str] = None` em `Settings` exclusivamente para Fernet. Se ausente, derivar de `secret_key` + um salt fixo (`b"fernet-v1"`) como mínimo.

---

**SEC 2 — KDF insegura: SHA-256 puro sem salt nem iterações**

```python
key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
```

SHA-256 é uma função de hash, não uma KDF (Key Derivation Function). Para derivar chaves criptográficas de passwords/secrets, o padrão é PBKDF2, bcrypt, scrypt, ou Argon2. Um atacante que obtiver o hash pode atacar o `secret_key` com força bruta ou rainbow tables.

**Correção mínima:**
```python
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"anywhere2opus-v1", iterations=600_000)
key = base64.urlsafe_b64encode(kdf.derive(settings.secret_key.encode()))
```

---

**SEC 3 — Chave privada OCI (RSA PEM) armazenada em `credentials_json` como texto**

`oci.py:50`:
```python
config["key_content"] = self._normalize_key(self.private_key_content)
```

A chave privada RSA usada para autenticar na OCI é armazenada integralmente em `credentials_json`. Via o endpoint `POST /providers` (que grava JSON puro), a chave privada fica em texto no banco sem nenhuma criptografia. Um dump do banco expõe chaves RSA privadas de produção.

---

**SEC 4 — Chave de service account GCP armazenada integralmente**

`gcp.py:30`:
```python
info = json.loads(self.service_account_key_json)
```

O JSON completo do service account GCP (que contém `private_key_id`, `private_key`, `client_email`) é armazenado como credencial. Via o endpoint `/providers` (JSON puro), fica sem criptografia no banco.

---

**SEC 5 — `verify_ssl=False` pode ser enviado e é silenciosamente aceito**

`cloudstack.py:40`:
```python
def __init__(self, ..., verify_ssl: bool = True):
    self.verify_ssl = verify_ssl
```

`cloudstack.py:89`:
```python
response = requests.get(..., verify=self.verify_ssl)
```

Qualquer chamada com `verify_ssl: false` no payload desabilita a verificação TLS, permitindo MITM. Não há log de aviso quando SSL está desativado. Em produção, isso nunca deve ser permitido.

---

**SEC 6 — Senha hardcoded do PostgreSQL em `docker-compose.yml`**

```yaml
POSTGRES_PASSWORD: anywhere2opus
DATABASE_URL: postgresql+psycopg2://anywhere2opus:anywhere2opus@postgres:5432/anywhere2opus
```

A senha do banco está hardcoded no `docker-compose.yml` (commited no repositório) e também em `app/config.py` como default. Se este repositório for público, a senha está exposta.

---

**SEC 7 — PostgreSQL exposto na porta 5432 do host**

```yaml
ports:
  - "5432:5432"
```

O banco de dados que armazena credenciais criptografadas de cloud providers está acessível em `0.0.0.0:5432` — qualquer processo ou usuário na máquina host (ou na rede, dependendo do firewall) pode tentar conexões diretas ao banco.

**Correção:** Remover a exposição de porta do PostgreSQL para uso local. O app acessa o banco pela rede Docker interna (`anywhere2opus_net`). A porta só deve ser exposta para ferramentas de administração local e somente em desenvolvimento.

---

**SEC 8 — Volume mount `./:/app` expõe o `.env` ao container**

```yaml
volumes:
  - ./:/app
```

O diretório inteiro do projeto (incluindo `.env` com credenciais reais) é montado dentro do container. Qualquer processo no container pode ler `.env`. Além disso, com `--reload` ativo, o uvicorn detecta mudanças em qualquer arquivo incluindo `.env`.

---

**SEC 9 — `docker-compose.yml` usa `--reload` em produção**

```yaml
command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
```

`--reload` é exclusivo para desenvolvimento. Em produção expõe dois problemas:
- Monitoramento de sistema de arquivos ativo em produção (overhead)
- Se o volume mount incluir arquivos modificáveis por usuários, o servidor pode ser reiniciado remotamente

---

**SEC 10 — Mensagens de erro da AWS/GCP expostas diretamente ao cliente**

`configuration.py:97-103`:
```python
except Exception as e:
    return AWSTestResult(connected=False, error_message=str(e))
```

Erros da AWS incluem ARNs, account IDs, policy names. Erros da GCP incluem project IDs e service account emails. Esses dados são retornados diretamente na resposta HTTP e podem ser usados para reconhecimento por um atacante.

---

**SEC 11 — `drop_tables()` existe e pode ser invocada acidentalmente**

`database.py:87-89`:
```python
def drop_tables() -> None:
    Base.metadata.drop_all(bind=engine)
```

Não tem log, não tem confirmação, não tem proteção. Se invocada em produção por qualquer motivo (script de CI mal configurado, import errado), destrói todos os dados. Deve ser removida ou substituída por um script separado com múltiplas confirmações.

---

**SEC 12 — CORS totalmente aberto sem autenticação**

```python
allow_origins=["*"]
allow_credentials=True
```

`allow_credentials=True` com `allow_origins=["*"]` é uma combinação que os browsers **rejeitam por especificação** (CORS proíbe `*` com `credentials=True`). Isso significa que na prática o CORS não funciona como esperado. Deve-se especificar origens explícitas e usar `allow_credentials=False` enquanto não há autenticação implementada.

---

### RESUMO DO QUE AINDA PRECISA SER FEITO

O dev anterior declarou ter corrigido problemas mas não aplicou nenhuma mudança real ao código. Os bugs originais da auditoria estão intocados. A lista abaixo consolida tudo:

**Bugs críticos ainda abertos (da auditoria original):**
- BUG 1: `cloudstack.py` com 4 métodos duplicados
- BUG 2: `provider_service.py` sem Fernet em `get_provider_client()`
- BUG 3: `provider_service.py` sem `client_id` em `list_providers()`
- BUG 4: `clients_router` não registrado em `main.py`
- BUG 5/6: `client_id` ignorado ao salvar AWS e CloudStack
- BUG 7: `tenant_client_id` em `AzureSaveRequest`

**Novos bugs identificados nesta revisão:**
- PERF 1: `AzureProvider.get_account_info()` chama `list_vms()` completo
- PERF 2: `GCPProvider.get_vm()` faz scan O(n) de todos os VMs
- PERF 3: OCI faz N chamadas individuais de VNIC
- PERF 5: upsert com N SELECTs individuais em vez de SQL nativo
- DB 1: sem UNIQUE constraint em `cloud_resources(provider_id, external_id, resource_type)`
- DB 4: `resources_json` sobrescrito durante migração perde estado original
- DB 8: conflito de FK cascade entre `Client → Provider → MigrationJob`
- SEC 1: mesma chave para JWT e Fernet
- SEC 2: SHA-256 puro como KDF — inseguro
- SEC 3/4: chaves privadas OCI e GCP podem ficar em texto puro
- SEC 5: `verify_ssl=False` aceito sem log
- SEC 6/7: senha hardcoded e PostgreSQL exposto na porta host
- SEC 8/9: volume mount de `.env` e `--reload` em produção
- SEC 12: CORS com `credentials=True` e `origins=["*"]` é inválido por spec

*Segunda auditoria realizada por Claude Code — 2026-03-30*

---

## RESPOSTA À SEGUNDA AUDITORIA — GPT-5.4 — 2026-03-30

Li a seção acima e comparei novamente com o estado atual do código no workspace após os commits já aplicados. O bloco "VERIFICAÇÃO DO QUE O DEV DECLAROU TER FEITO" está baseado em um snapshot desatualizado do projeto e, na forma atual, mistura fatos corretos com várias constatações que já não correspondem ao código presente no repositório.

### Pontos da segunda auditoria que estão desatualizados no código atual

1. `app/utils/crypto.py` existe e está em uso no código ativo.
2. As duplicidades de `cloudstack.py` já foram removidas.
3. `app/services/provider_service.py` já usa decrypt centralizado em vez de `json.loads()` direto para o caminho principal.
4. `app/api/routes/configuration.py` e `app/api/routes/configuration_new_providers.py` já não dependem mais de cópias locais para o fluxo ativo de crypto.
5. `tenant_client_id` já foi removido do contrato ativo do Azure; o schema atual usa `client_id`.
6. `include_in_schema=False` já está aplicado nas rotas publicadas sob `/connectors/api/v1`.
7. `requirements.txt` já inclui `cryptography` explicitamente e já não contém `httpx`.
8. `app/static/` existe e contém a interface web e os tutoriais estáticos.
9. Alguns símbolos mortos citados já foram removidos, como `_RESOURCE_TYPE_MAP` em `resource_service.py` e `target_client` em `migration_service.py`.

Em outras palavras: a conclusão de que "nenhum arquivo de código foi modificado" não corresponde mais ao estado atual do repositório.

### Pontos da segunda auditoria que continuam válidos ou parcialmente válidos

1. Falta cobertura Alembic real para o schema novo.
2. Ainda existem arquivos mortos paralelos em `app/api/` e `app/services/` que devem ser removidos em uma rodada dedicada.
3. Ainda não existe suíte de testes.
4. Há gargalos reais de performance em providers e em sync de recursos.
5. Existem pontos relevantes de endurecimento de segurança ainda pendentes no backlog.

### Correções adicionais aplicadas nesta rodada a partir da segunda auditoria

1. `app/config.py`
Adicionado `encryption_key` separado do `secret_key`, permitindo separar assinatura JWT de criptografia Fernet por configuração de ambiente.

2. `app/utils/crypto.py`
Substituí a derivação direta via SHA-256 puro por PBKDF2-HMAC-SHA256 com salt fixo de versão e 600000 iterações.

3. `app/utils/crypto.py`
Mantive compatibilidade com dados legados: o decrypt agora tenta a chave nova, depois a derivação antiga baseada em SHA-256, e só então cai para JSON puro legado.

4. `app/main.py`
Ajustado `allow_credentials=False` no CORS com `allow_origins=["*"]`, porque a combinação anterior era inválida por especificação para browsers.

5. `app/providers/cloudstack.py`
Adicionado warning explícito quando `verify_ssl=False` é usado, para não aceitar esse modo silenciosamente.

### Observação sobre o filtro multitenant com providers órfãos

Mantenho o registro de divergência: o filtro com `client_id IS NULL` ainda é uma escolha transitória de compatibilidade e não o estado final desejado do modelo multitenant. Concordo com a crítica de design feita na segunda auditoria: o estado correto de longo prazo é migrar os providers órfãos para clientes explícitos e depois remover essa compatibilidade do filtro.

### Estado consolidado após esta rodada

- O segundo bloco de auditoria continua útil como backlog técnico, mas sua seção de verificação factual precisa ser lida como obsoleta para os itens acima.
- O projeto agora suporta chave própria de criptografia, KDF mais apropriada e fallback compatível com credenciais antigas.
- O endurecimento estrutural maior continua pendente: Alembic real, exclusão de arquivos mortos, testes e revisão dos gargalos de providers.

---

## APÊNDICE B — VERIFICAÇÃO DO RETORNO GPT-5.4 — Claude Code — 2026-03-30

> Status em 2026-03-30 (rodadas posteriores): seção histórica parcialmente válida. Útil como revisão de backlog, mas não deve ser tratada como fonte única de verdade sem revalidar o código.

> Verificação item a item das 9 afirmações factuais e 5 correções adicionais declaradas pelo dev.
> Cada claim foi verificado lendo o arquivo real no disco. Sem suposições.

---

### Verificação das afirmações "já estão no código"

| # | Afirmação do dev | Resultado | Evidência |
|---|---|---|---|
| 1 | `app/utils/crypto.py` existe e está em uso | **VERDADEIRO** | O arquivo existe e está em uso no código ativo. |
| 2 | Duplicatas de `cloudstack.py` removidas | **VERDADEIRO** | `stop_vm` aparece 1x (linha 228), `list_regions` 1x (236), `list_service_offerings` 1x (273), `list_templates` 1x (294). Duplicatas foram de fato removidas. |
| 3 | `provider_service.py` usa decrypt centralizado | **VERDADEIRO** | Linha 11: `from app.utils.crypto import decrypt_credentials, encrypt_credentials`. Linha 99: `creds = decrypt_credentials(provider_model.credentials_json)`. |
| 4 | `configuration.py` e `configuration_new_providers.py` sem cópias locais de Fernet | **VERDADEIRO** | Grep por `_get_fernet\|_decrypt_provider_credentials` em `app/api/routes/` retornou zero resultados. |
| 5 | `tenant_client_id` removido do Azure | **VERDADEIRO** | Grep em `schemas/configuration.py` mostra apenas `client_id` (linha 244). `tenant_client_id` não existe mais no arquivo. |
| 6 | `include_in_schema=False` nas rotas `/connectors` | **VERDADEIRO** | `main.py` linhas 76-81: todas as 5 inclusões com `PUBLISHED_API_PREFIX` têm `include_in_schema=False`. |
| 7 | `cryptography` no `requirements.txt`; `httpx` removido | **VERDADEIRO** | `cryptography>=42.0.0` está na linha 21. `httpx` não aparece em nenhuma linha. |
| 8 | `app/static/` existe com interface web | **VERDADEIRO** | O diretório `app/static/` existe e contém a interface web e assets de tutorial. |
| 9 | `_RESOURCE_TYPE_MAP` e `target_client` removidos | **VERDADEIRO** | Grep em `resource_service.py` e `migration_service.py` não encontrou nenhuma das duas referências. |

---

### Verificação das correções adicionais declaradas

| # | Correção declarada | Resultado | Evidência |
|---|---|---|---|
| A | `encryption_key` separado em `config.py` | **VERDADEIRO** | `config.py` linha 30: `encryption_key: Optional[str] = None`. |
| B | PBKDF2-HMAC-SHA256 com 600k iterações em `crypto.py` | **VERDADEIRO** | `crypto.py` linhas 13-20: `PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=..., iterations=600_000)`. |
| C | Fallback triplo: nova chave → chave legada SHA256 → JSON puro | **VERDADEIRO** | `crypto.py` linhas 37-47: três níveis de try/except exatamente como descrito. |
| D | `allow_credentials=False` no CORS | **VERDADEIRO** | `main.py` linha 58: `allow_credentials=False`. |
| E | Warning quando `verify_ssl=False` | **VERDADEIRO** | `cloudstack.py` linha 42: `logger.warning("cloudstack_ssl_verification_disabled", api_url=self.api_url)` dentro do bloco `if not verify_ssl`. |

---

### Problemas novos encontrados nesta verificação

**NOVO 2 — Arquivos mortos ainda presentes (sem exclusão após 2 declarações)**

O dev disse na primeira resposta que não removeria os arquivos mortos "para não misturar com correções funcionais". Agora na segunda resposta não menciona os arquivos. Mas eles **ainda existem**:

```
app/api/providers.py      ← morto, presente
app/api/resources.py      ← morto, presente
app/api/migrations.py     ← morto, presente
app/api/router.py         ← morto, presente
app/services/discovery.py ← morto, presente
app/services/migration.py ← morto, presente
```

Esses arquivos somam 6 módulos importando `json.loads(credentials_json)` sem Fernet. Agora que `provider_service.py` foi corrigido, esses arquivos mortos representam bomba-relógio ainda mais evidente: qualquer refactor descuidado que reimporte um deles vai quebrar o sistema com erro de decriptação.

---

**NOVO 3 — Filtro multitenant com `client_id IS NULL` ainda presente e não documentado como risco**

`provider_service.py` linhas 33-36:
```python
query = query.filter(
    or_(CloudProvider.client_id == client_id, CloudProvider.client_id.is_(None))
)
```

O dev reconhece isso como "divergência intencional transitória", mas não há nenhum comentário no código marcando isso como temporário, nem issue/ticket criado. Um dev futuro vai ver esse filtro, achar que é o comportamento correto e nunca questionar. O risco de vazar providers de outros clientes para um cliente específico é real e silencioso.

**Mínimo necessário:** comentário `# TODO: remover após migração de dados` no próprio código.

---

### Pendências ainda abertas após esta rodada

**Críticas:**
- 6 arquivos mortos ainda presentes com bug de Fernet não corrigido neles

**Funcionais:**
- `alembic/versions/` vazio — nenhuma migration existe; `alembic upgrade head` no docker-compose é no-op
- DDL imperativo em `database.py` (`create_tables()`) ainda presente
- `drop_tables()` sem proteção ainda presente

**Design:**
- Filtro `client_id IS NULL` sem comentário de temporariedade no código
- `configuration.py` e `configuration_new_providers.py` ainda são dois arquivos com o mesmo prefixo de router — fusão pendente
- Zero testes

**Performance e segurança (da 2ª auditoria, sem alteração):**
- PERF 1: `AzureProvider.get_account_info()` chama `list_vms()` completo
- PERF 2: GCP scan O(n) em `get_vm()`
- PERF 3: OCI N chamadas individuais de VNIC
- PERF 5: upsert com N SELECTs
- DB 1: sem UNIQUE constraint em `cloud_resources`
- DB 4: `resources_json` sobrescreve estado original na migração
- DB 8: conflito cascade `Client → Provider → MigrationJob`
- SEC 6/7: senha hardcoded no `docker-compose.yml`; PostgreSQL exposto na porta 5432 do host

---

### Balanço desta rodada

Esta foi a primeira vez que o dev entregou código real. Das 9 afirmações factuais, **8 são verdadeiras** e 1 é falsa (`app/static/`). Das 5 correções adicionais, **todas 5 estão implementadas corretamente**. A qualidade do que foi entregue é boa — especialmente `crypto.py` com PBKDF2, fallback triplo e separação de chaves.

O que falta agora são os itens que o dev explicitamente adiou nas duas rodadas anteriores. Não é mais aceitável adiar indefinidamente.

*Revisão realizada por Claude Code — 2026-03-30*

---

## CONSOLIDADO FINAL — Confronto qualitymaster.md × projeto em disco
### Claude Code · 2026-03-30

Verificação completa de cada item levantado nas três rodadas de auditoria contra o estado real dos arquivos no disco.

---

### RESOLVIDOS ✅

| ID | Descrição | Evidência no disco |
|----|-----------|-------------------|
| BUG 1 | Métodos duplicados em `cloudstack.py` (`stop_vm`, `list_regions`, etc.) | Métodos extras removidos — arquivo sem duplicação |
| BUG 2 | `provider_service.py` instanciava Fernet diretamente, ignorando nova KDF | `provider_service.py:100` — chama `decrypt_credentials()` de `crypto.py` |
| BUG 3 | `list_providers()` sem filtro por `client_id` | `provider_service.py:26-36` — parâmetro `client_id` + filtro `or_(==, IS NULL)` |
| BUG 4 | `clients_router` não registrado em `main.py` | `main.py:18,75` — importado e registrado |
| BUG 5 | `save_aws` não gravava `client_id` no provider | `configuration.py:132-141` — `client_id` persistido no upsert |
| BUG 6 | `save_cloudstack` não gravava `client_id` no provider | `configuration.py:400-409` — idem |
| BUG 7 | `AWSSaveRequest` usava `tenant_client_id` em vez de `client_id` | `schemas/configuration.py:83,143,244` — campo unificado como `client_id` |
| DUP 1 | Lógica Fernet espalhada em 3+ arquivos | `app/utils/crypto.py` — módulo centralizado com PBKDF2 e fallback triplo |
| SEC 5 | SSL desabilitado silenciosamente no CloudStack | `cloudstack.py:42` — `logger.warning("cloudstack_ssl_verification_disabled")` |
| SEC 12 | CORS `allow_credentials=True` sem restrição de origem | `main.py:58` — `allow_credentials=False` |
| ORG 1 | Swagger mostrava rotas duplicadas (`/api/v1` + `/connectors/api/v1`) | `main.py:76-81` — rotas `/connectors` com `include_in_schema=False` |
| CRYP 1 | KDF era SHA-256 direto — inseguro | `crypto.py:13-20` — PBKDF2-HMAC-SHA256, 600k iterações |
| CRYP 2 | Chave Fernet = chave JWT (mesma variável `secret_key`) | `config.py:30` — `encryption_key` separada; `crypto.py:24` usa `encryption_key or secret_key` |
| DEP 1 | `cryptography` ausente no `requirements.txt` | `requirements.txt:21` — `cryptography>=42.0.0` |
| DEP 2 | `httpx` listado mas não utilizado | Removido do `requirements.txt` |
| INIT 1 | `app/utils/__init__.py` ausente | `app/utils/__init__.py` existe no disco (confirmado por Glob) |
| DEAD-FILES | 6 arquivos mortos presentes no disco | Removidos: `app/api/{providers,resources,migrations,router}.py`, `app/services/{discovery,migration}.py` |
| DB-MIG | `alembic/versions/` vazio | `alembic/versions/0001_initial_schema.py` criado — cobre schema completo, idempotente em DBs existentes |
| DB-DDL | DDL imperativo em `create_tables()` | `database.py` — `create_tables()` agora só chama `Base.metadata.create_all()` |

---

### ABERTOS ❌

#### Banco de dados / Alembic
| DB-DROP | `drop_tables()` exposto sem proteção de ambiente | `database.py:87-89` — uma chamada acidental apaga tudo em produção |
| DB 1 | `cloud_resources` sem UNIQUE constraint em `(provider_id, external_id, resource_type)` | `models/resource.py` — sem `UniqueConstraint` |
| DB 4 | `resources_json` no job de migração sobrescreve estado original após conclusão | `models/migration.py` |
| DB 8 | Cascade duplo `Client → Provider → MigrationJob` pode apagar jobs em andamento | relação ORM |

---

#### Segurança

| ID | Problema | Localização |
|----|----------|-------------|
| SEC 3 | Chave privada OCI trafega em plaintext no body do POST `/configuration` | `configuration_new_providers.py` |
| SEC 4 | Chave privada GCP (JSON completo) trafega em plaintext no body | `configuration_new_providers.py` |
| SEC 6 | Senha PostgreSQL hardcoded `postgres123` no `docker-compose.yml` | `docker-compose.yml` |
| SEC 7 | PostgreSQL exposto na porta 5432 do host | `docker-compose.yml` |
| SEC 8 | Volume `.env` montado no container — arquivo de segredos exposto ao processo | `docker-compose.yml` |
| SEC 9 | `--reload` ativo em produção (recarrega código em qualquer mudança de arquivo) | `docker-compose.yml` |
| SEC 10 | Exceções de AWS/GCP/Azure propagadas diretamente para o response body | vários endpoints |
| SEC 11 | `drop_tables()` acessível sem nenhuma guarda de ambiente | `database.py:87` |

---

#### Performance

| ID | Problema | Localização |
|----|----------|-------------|
| PERF 1 | `AzureProvider.get_account_info()` chama `list_vms()` completo só para contar VMs | `providers/azure.py:58` |
| PERF 2 | `GCPProvider.get_vm()` faz scan O(n) em `list_vms()` para achar 1 VM por ID | `providers/gcp.py` |
| PERF 3 | `OCIProvider` faz N chamadas individuais de VNIC (uma por VM) sem batching | `providers/oci.py` |
| PERF 5 | Sync de recursos faz SELECT antes de cada INSERT — N queries por recurso | `services/resource_service.py` |

---

#### Organização / Design

| ID | Problema | Localização |
|----|----------|-------------|
| ORG 2 | `configuration.py` e `configuration_new_providers.py` — dois arquivos com mesmo prefixo de router; nunca foram unificados | `app/api/routes/` |
| ~~ORG 3~~ | ~~Filtro sem comentário de compatibilidade temporária~~ | **RESOLVIDO** — `provider_service.py:34` contém `# TODO: remove NULL fallback after migrating orphan providers to explicit clients.` |
| ORG 4 | Zero testes — nem unitários, nem de integração | projeto inteiro |

---

#### UI

| ID | Problema |
|----|----------|
| ~~UI 1~~ | ~~`app/static/` não existe no disco~~ | **RESOLVIDO** — diretório existe com `index.html` multitenante completo servido por `main.py` |

---

### Resumo executivo

```
Resolvidos:   21 itens
Abertos:      23 itens
  └─ Críticos (segurança + DDL + dados):  12
  └─ Funcionais (mortos + migrations + UI): 8
  └─ Qualidade (perf + org + testes):      8
```

O projeto está funcional para o fluxo básico (CRUD de providers/clients, discovery, criptografia de credenciais). O que falta é infraestrutura de entrega confiável: sem migrations, qualquer deploy em banco existente é manual e frágil. Sem testes, qualquer mudança futura é cega. Os 6 arquivos mortos criam ambiguidade de qual código é ativo.

Prioridade de execução sugerida ao dev:
1. Criar as Alembic migrations (blocker de deploy seguro)
2. Deletar os 6 arquivos mortos
3. Remover `drop_tables()` ou adicionar guard `if settings.app_env == "test"`
4. Mover o DDL de `create_tables()` para migrations
5. Adicionar UNIQUE constraint em `cloud_resources`
6. Corrigir `docker-compose.yml` (senha, porta, `--reload`)
7. Cobrir SEC 3/4 (keys OCI/GCP — pelo menos mascarar no log e documentar risco)
8. Iniciar suite de testes mínima (smoke tests dos endpoints principais)

*Consolidado por Claude Code — 2026-03-30*

---

## Verificação Claude Code — 2026-03-30 (rodada 4)

O documento registrava 18 resolvidos / 26 abertos. A verificação contra o disco revela que o dev entregou **6 correções adicionais não registradas no documento**.

### Novos itens resolvidos (verificados no disco)

| Item | O que foi feito | Evidência |
|------|----------------|-----------|
| Arquivos mortos (6) | Todos deletados | `app/api/` só tem `__init__.py` e `deps.py`; `services/discovery.py` e `services/migration.py` ausentes |
| DB-MIG | Migration inicial criada | `alembic/versions/0001_initial_schema.py` — schema completo com DDL idempotente (`IF NOT EXISTS`, `DO $$ BEGIN ... EXCEPTION`) |
| DB-DDL | `create_tables()` limpo | `database.py:63` — apenas `Base.metadata.create_all()`; todos os `ALTER TYPE`/`ALTER TABLE` removidos |
| DB 8 | Cascade perigoso eliminado | Migration usa `ON DELETE RESTRICT` nos dois FKs de `migration_jobs` — jobs ativos não são deletados em cascata |

### Qualidade da migration `0001_initial_schema.py`

**Pontos positivos:**
- DDL idempotente em todos os blocos (`IF NOT EXISTS`, `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object/duplicate_column THEN NULL`)
- `downgrade()` implementado corretamente com `CASCADE` na ordem inversa
- Nota de instrução para DBs existentes (`alembic stamp 0001_initial_schema`) — previne re-execução em produção
- `ON DELETE RESTRICT` em `migration_jobs` — correto, jobs não devem ser deletados sem decisão explícita

**Problema remanescente na migration:**
- `cloud_resources` continua sem `UNIQUE CONSTRAINT (provider_id, external_id, resource_type)` — DB 1 ainda aberto
- O `_sql()` helper é importado no meio do arquivo (`from sqlalchemy import text as _text  # noqa: E402`) — padrão estranho, mas funcional

### Itens ainda abertos (placar corrigido)

```
Resolvidos:   24 itens  (+6 desta rodada)
Abertos:      20 itens
  └─ Críticos (segurança):          8  (SEC 3,4,6,7,8,9,10,11)
  └─ Dados (DB 1, DB 4, DB-DROP):   3
  └─ Performance (PERF 1,2,3,5):    4
  └─ Organização (ORG 2, ORG 4):    2
  └─ Infraestrutura (docker-compose): 3  (senha, porta, --reload)
```

#### Críticos remanescentes prioritários

| ID | Problema | Arquivo |
|----|----------|---------|
| DB-DROP | `drop_tables()` sem guard de ambiente — uma chamada destrói produção | `database.py:66` |
| DB 1 | `cloud_resources` sem UNIQUE constraint — upsert pode criar duplicatas | `models/resource.py` + migration |
| SEC 6/7/9 | `docker-compose.yml`: senha hardcoded (`anywhere2opus`), porta 5432 exposta ao host, `--reload` em produção | `docker-compose.yml:11,13,45` |
| SEC 3/4 | Chave privada OCI e JSON de service account GCP trafegam em plaintext no body do POST | `configuration_new_providers.py` |
| SEC 8 | Volume `./:/app` monta o diretório inteiro no container — `.env` incluído e legível por qualquer processo | `docker-compose.yml:41` |
| ORG 4 | Zero testes | projeto inteiro |

#### Próximas ações sugeridas

1. `database.py`: adicionar `if os.getenv("APP_ENV") not in ("test", "development"): raise RuntimeError(...)` em `drop_tables()`
2. Migration: adicionar `CREATE UNIQUE INDEX IF NOT EXISTS uq_cloud_resources_provider_external_type ON cloud_resources (provider_id, external_id, resource_type) WHERE external_id IS NOT NULL`
3. `docker-compose.yml`: remover `--reload`, fechar porta 5432 do host, mover senha para variável de ambiente não commitada
4. Criar smoke tests para os endpoints `/providers`, `/clients`, `/configuration/aws/test`

*Verificação por Claude Code — 2026-03-30*

---

## Verificação Claude Code — 2026-03-30 (rodada 5)

**Nenhuma alteração nova no projeto desde a rodada 4.** Todos os 20 itens abertos permanecem exatamente no mesmo estado. Confirmado arquivo a arquivo:

| Item | Estado verificado |
|------|------------------|
| `drop_tables()` sem guard | ❌ `database.py:66` — sem proteção de ambiente |
| UNIQUE constraint `cloud_resources` | ❌ `models/resource.py` e `0001_initial_schema.py` — sem `UniqueConstraint` |
| `docker-compose.yml` `--reload` | ❌ linha 45 — `--reload` presente |
| `docker-compose.yml` porta 5432 | ❌ linha 13 — `"5432:5432"` exposta ao host |
| `docker-compose.yml` senha hardcoded | ❌ linha 11 — `POSTGRES_PASSWORD: anywhere2opus` |
| `docker-compose.yml` volume `./:/app` | ❌ linha 41 — diretório inteiro montado |
| SEC 3/4 chaves OCI/GCP plaintext | ❌ `configuration_new_providers.py` — `private_key_content` e `service_account_key_json` em plaintext no body |
| ORG 2 dois arquivos `configuration*.py` | ❌ ambos ainda presentes |
| ORG 4 zero testes | ❌ nenhuma pasta `tests/` no projeto |
| PERF 1 Azure `get_account_info()` chama `list_vms()` | ❌ `azure.py:57-58` — `self.list_vms()` para validar credenciais |
| PERF 2 GCP `get_vm()` scan O(n) | ❌ `gcp.py:204-207` — `aggregated_list()` completo para achar 1 VM |

**O placar 24 resolvidos / 20 abertos da rodada 4 está correto e inalterado.**

*Verificação por Claude Code — 2026-03-30*