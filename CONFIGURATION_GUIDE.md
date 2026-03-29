# 🔧 Cloud Provider Configuration & Testing Guide

## Overview

A nova seção de **Configuration & Testing** oferece endpoints para testar a conectividade com os provedores de cloud **antes** de salvar as configurações no banco de dados.

**Benefícios:**
- ✅ Teste credenciais sem comprometer o banco
- ✅ Valide configurações antes de criar providers
- ✅ Descubra zonas e recursos disponíveis
- ✅ Diagnóstico rápido de problemas de conexão

---

## 📚 Endpoints Disponíveis

### 1. CloudStack - Testar Conexão
**Endpoint:** `POST /api/v1/configuration/cloudstack/test`

Testa a conectividade com uma API CloudStack.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://your-cloudstack.example.com/client/api",
    "api_key": "your-api-key",
    "secret_key": "your-secret-key",
    "zone_id": "zone-123",
    "verify_ssl": true
  }'
```

**Parameters:**
- `api_url` (required): URL completa da API CloudStack  
- `api_key` (required): Chave de API do CloudStack  
- `secret_key` (required): Chave secreta do CloudStack  
- `zone_id` (optional): ID da zona padrão  
- `verify_ssl` (optional): Validar certificado SSL (default: true)

**Response Success:**
```json
{
  "connected": true,
  "api_url": "https://your-cloudstack.example.com/client/api",
  "zones_found": 3,
  "error_message": null,
  "details": {
    "zones": [
      {"id": "zone-1", "name": "Zone 1"},
      {"id": "zone-2", "name": "Zone 2"},
      {"id": "zone-3", "name": "Zone 3"}
    ]
  }
}
```

**Response Failure:**
```json
{
  "connected": false,
  "api_url": "https://your-cloudstack.example.com/client/api",
  "zones_found": null,
  "error_message": "HTTPSConnectionPool host='...': Max retries exceeded",
  "details": null
}
```

---

### 2. CloudStack - Listar Zonas
**Endpoint:** `POST /api/v1/configuration/cloudstack/zones`

Lista as zonas disponíveis em um CloudStack.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/zones \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://your-cloudstack.example.com/client/api",
    "api_key": "your-api-key",
    "secret_key": "your-secret-key"
  }'
```

**Response:**
```json
{
  "total": 3,
  "zones": [
    {
      "id": "zone-1",
      "name": "Zone 1",
      "network_type": "Advanced",
      "dns1": "8.8.8.8",
      "dns2": "8.8.4.4"
    },
    {
      "id": "zone-2",
      "name": "Zone 2"
    }
  ]
}
```

---

### 3. Testar Qualquer Provider
**Endpoint:** `POST /api/v1/configuration/test`

Endpoint genérico para testar qualquer provedor suportado.

**Request (CloudStack):**
```bash
curl -X POST http://localhost:8000/api/v1/configuration/test \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "CLOUDSTACK",
    "config": {
      "api_url": "https://cloudstack.example.com/client/api",
      "api_key": "your-api-key",
      "secret_key": "your-secret-key"
    }
  }'
```

**Supported Provider Types:**
- `CLOUDSTACK` - Apache CloudStack / Opus
- `AWS` - Amazon Web Services
- `GCP` - Google Cloud Platform
- `AZURE` - Microsoft Azure
- `OCI` - Oracle Cloud Infrastructure

**Response:**
```json
{
  "provider_type": "CLOUDSTACK",
  "connected": true,
  "timestamp": "2026-03-29T17:56:54.940824Z",
  "message": "Connection successful",
  "details": null
}
```

---

## 🧪 Exemplos de Uso

### Exemplo 1: Testar CloudStack Local
```bash
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "http://192.168.1.100:8080/client/api",
    "api_key": "C7zqKjJXoKBw...",
    "secret_key": "K8LrX9mPqNt...",
    "verify_ssl": false
  }'
```

### Exemplo 2: Validar Credenciais Antes de Criar
```bash
# Primeiro, teste a conexão
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://opus.company.com/client/api",
    "api_key": "your-key",
    "secret_key": "your-secret"
  }'

# Se connected: true, então criar o provider
curl -X POST http://localhost:8000/api/v1/providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production CloudStack",
    "type": "CLOUDSTACK",
    "is_active": true,
    "credentials": {
      "api_url": "https://opus.company.com/client/api",
      "api_key": "your-key",
      "secret_key": "your-secret"
    }
  }'
```

### Exemplo 3: Listar Zonas Disponíveis
```bash
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/zones \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://cloudstack.company.com/client/api",
    "api_key": "admin-key",
    "secret_key": "admin-secret"
  }' | python3 -m json.tool
```

---

## 🔐 Segurança

### Best Practices:
1. **Não salve credenciais em histórico de comando**
   ```bash
   # ❌ Ruim - credentials em histórico
   curl ... -d '{"api_key": "secret"}'
   
   # ✅ Bom - usar arquivo
   curl ... -d @credentials.json
   ```

2. **Use HTTPS em produção**
   ```json
   {
     "api_url": "https://...",
     "verify_ssl": true
   }
   ```

3. **Proteja arquivos de credenciais**
   ```bash
   chmod 600 credentials.json
   .gitignore: *.json (para credenciais)
   ```

---

## 🐛 Troubleshooting

### Erro: "Failed to resolve hostname"
**Causa:** Hostname não resolveu  
**Solução:** Verifique se o domínio está correto e acessível

```bash
# Teste o domínio
ping your-cloudstack.example.com
# ou
nslookup your-cloudstack.example.com
```

### Erro: "SSL certificate verify failed"
**Causa:** Certificado SSL inválido  
**Solução:** Use `"verify_ssl": false` (não recomendado em produção)

```json
{
  "api_url": "https://...",
  "verify_ssl": false
}
```

### Erro: "Invalid API key or signature"
**Causa:** Credenciais incorretas  
**Solução:** Verifique api_key e secret_key

---

## 📊 Workflow Recomendado

```
1. Testar Conexão
   POST /configuration/cloudstack/test
   
   ↓ (se conectou)
   
2. Listar Zonas Disponíveis
   POST /configuration/cloudstack/zones
   
   ↓
   
3. Criar Provider (salvar no BD)
   POST /providers
   
   ↓
   
4. Sincronizar Recursos
   POST /providers/{id}/sync
```

---

## 💡 Dicas

### 1. Usar arquivo de credenciais
```bash
# credentials.json
{
  "api_url": "https://cloudstack.example.com/client/api",
  "api_key": "your-key",
  "secret_key": "your-secret",
  "verify_ssl": true
}

# Usar com curl
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d @credentials.json
```

### 2. Usar variáveis de ambiente
```bash
export CLOUDSTACK_URL="https://cloudstack.example.com/client/api"
export CLOUDSTACK_API_KEY="your-key"
export CLOUDSTACK_SECRET="your-secret"

curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d "{
    \"api_url\": \"$CLOUDSTACK_URL\",
    \"api_key\": \"$CLOUDSTACK_API_KEY\",
    \"secret_key\": \"$CLOUDSTACK_SECRET\"
  }"
```

### 3. Validar resposta com jq
```bash
curl -s -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d @credentials.json | \
  jq 'if .connected then "✅ Connected!" else "❌ Failed: " + .error_message end'
```

---

## 📈 Próximos Passos

- [ ] Implementar endpoints similares para AWS, GCP, Azure, OCI
- [ ] Adicionar suporte a múltiplas zonas no descobrimento
- [ ] Criar webhook para notificações de teste
- [ ] Adicionar cache de resultados de teste
- [ ] Implementar histórico de testes

---

**Última Atualização:** 2026-03-29
