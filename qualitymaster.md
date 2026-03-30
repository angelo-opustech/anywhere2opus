# Quality Master — anywhere2opus
> Auditoria técnica completa realizada em 2026-03-30.
> Leia este arquivo antes de qualquer commit. Corrija em ordem de prioridade.

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
