#!/bin/bash
# Exemplos Práticos de Teste - CloudStack Configuration

echo "🔧 CloudStack Configuration Testing - Exemplos Práticos"
echo "========================================================="
echo ""

# Documento com exemplos reais que o usuário pode copiar e usar
echo "1. TESTE BÁSICO DE CONEXÃO"
echo "============================"
echo ""
echo "Comando:"
echo ""
cat << 'EXAMPLE1'
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://cloudstack.example.com/client/api",
    "api_key": "your-api-key-here",
    "secret_key": "your-secret-key-here",
    "verify_ssl": true
  }'
EXAMPLE1

echo ""
echo ""
echo "2. TESTE COM SSL DESABILITADO (Para certificados auto-assinados)"
echo "================================================================="
echo ""
echo "Comando:"
echo ""
cat << 'EXAMPLE2'
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://192.168.1.100:8089/client/api",
    "api_key": "your-api-key",
    "secret_key": "your-secret-key",
    "verify_ssl": false
  }'
EXAMPLE2

echo ""
echo ""
echo "3. LISTAR ZONAS DISPONÍVEIS"
echo "============================"
echo ""
echo "Comando:"
echo ""
cat << 'EXAMPLE3'
curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/zones \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://cloudstack.example.com/client/api",
    "api_key": "your-api-key",
    "secret_key": "your-secret-key"
  }' | python3 -m json.tool
EXAMPLE3

echo ""
echo ""
echo "4. USANDO ARQUIVO DE CREDENCIAIS"
echo "=================================="
echo ""
echo "1º - Crie um arquivo 'cloudstack-creds.json':"
echo ""
cat << 'EXAMPLE4'
{
  "api_url": "https://cloudstack.example.com/client/api",
  "api_key": "your-api-key",
  "secret_key": "your-secret-key",
  "verify_ssl": true
}
EXAMPLE4

echo ""
echo "2º - Use com curl:"
echo ""
echo 'curl -X POST http://localhost:8000/api/v1/configuration/cloudstack/test \'
echo '  -H "Content-Type: application/json" \'
echo '  -d @cloudstack-creds.json'
echo ""
echo ""

echo "5. VALIDAR CREDENTIAL E CRIAR PROVIDER"
echo "======================================"
echo ""
echo "Script completo:"
echo ""
cat << 'EXAMPLE5'
#!/bin/bash

API="http://localhost:8000/api/v1"
API_URL="https://cloudstack.example.com/client/api"
API_KEY="your-api-key"
SECRET_KEY="your-secret-key"

# 1. Testar conexão
echo "Testing CloudStack connection..."
TEST_RESULT=$(curl -s -X POST "$API/configuration/cloudstack/test" \
  -H "Content-Type: application/json" \
  -d "{
    \"api_url\": \"$API_URL\",
    \"api_key\": \"$API_KEY\",
    \"secret_key\": \"$SECRET_KEY\"
  }")

# Verificar resultado
CONNECTED=$(echo "$TEST_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['connected'])")

if [ "$CONNECTED" = "True" ]; then
    echo "✅ Connection successful!"
    
    # 2. Criar provider
    echo "Creating provider..."
    curl -X POST "$API/providers" \
      -H "Content-Type: application/json" \
      -d "{
        \"name\": \"CloudStack Production\",
        \"type\": \"CLOUDSTACK\",
        \"is_active\": true,
        \"credentials\": {
          \"api_url\": \"$API_URL\",
          \"api_key\": \"$API_KEY\",
          \"secret_key\": \"$SECRET_KEY\"
        }
      }" | python3 -m json.tool
else
    echo "❌ Connection failed!"
    echo "$TEST_RESULT"
fi
EXAMPLE5

echo ""
echo ""
echo "6. RESPOSTA COM SUCESSO (Exemplo)"
echo "================================="
echo ""
cat << 'EXAMPLE6'
{
  "connected": true,
  "api_url": "https://cloudstack.example.com/client/api",
  "zones_found": 2,
  "error_message": null,
  "details": {
    "zones": [
      {
        "id": "zone-1",
        "name": "Zone-1"
      },
      {
        "id": "zone-2",
        "name": "Zone-2"
      }
    ]
  }
}
EXAMPLE6

echo ""
echo "7. RESPOSTA COM ERRO (Exemplo)"
echo "=============================="
echo ""
cat << 'EXAMPLE7'
{
  "connected": false,
  "api_url": "https://cloudstack.example.com/client/api",
  "zones_found": null,
  "error_message": "Failed to connect - no response from API",
  "details": null
}
EXAMPLE7

echo ""
echo "✅ Todos os exemplos ! 🚀"
