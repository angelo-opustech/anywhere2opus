#!/bin/bash

echo "🧪 Testing CloudStack Configuration & Connection Endpoints"
echo "============================================================"
echo ""

API_URL="http://localhost:8000/api/v1"

# Test 1: List available configuration endpoints
echo "📋 Available Configuration Endpoints:"
echo ""
curl -s http://localhost:8000/docs | grep -o '<h2>[^<]*</h2>' | head -5
echo ""
echo ""

# Test 2: Test CloudStack connection with valid URL (but wrong credentials for demo)
echo "🔌 Test 1: CloudStack Connection Test (Demo)"
echo "-------------------------------------------"
echo "Payload:"
cat << 'EOF'
{
  "api_url": "https://cloudstack.example.com/client/api",
  "api_key": "test-api-key-12345",
  "secret_key": "test-secret-key-secret",
  "verify_ssl": false
}
EOF
echo ""
echo "Response:"
curl -s -X POST "$API_URL/configuration/cloudstack/test" \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://cloudstack.example.com/client/api",
    "api_key": "test-api-key-12345",
    "secret_key": "test-secret-key-secret",
    "verify_ssl": false
  }' | python3 -m json.tool
echo ""
echo ""

# Test 3: Test generic configuration endpoint
echo "🔌 Test 2: Generic Provider Test Endpoint"
echo "-------------------------------------------"
echo "Payload:"
cat << 'EOF'
{
  "provider_type": "CLOUDSTACK",
  "config": {
    "api_url": "https://cloudstack.example.com/client/api",
    "api_key": "test-key",
    "secret_key": "test-secret"
  }
}
EOF
echo ""
echo "Response:"
curl -s -X POST "$API_URL/configuration/test" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "CLOUDSTACK",
    "config": {
      "api_url": "https://cloudstack.example.com/client/api",
      "api_key": "test-key",
      "secret_key": "test-secret"
    }
  }' | python3 -m json.tool
echo ""
echo ""

# Test 4: Test list zones
echo "🌐 Test 3: List CloudStack Zones"
echo "-------------------------------------------"
echo "Response:"
curl -s -X POST "$API_URL/configuration/cloudstack/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "api_url": "https://cloudstack.example.com/client/api",
    "api_key": "test-key",
    "secret_key": "test-secret"
  }' | python3 -m json.tool
echo ""
echo ""

# Test 5: Swagger documentation
echo "📚 Available Endpoints (from Swagger):"
echo "-------------------------------------------"
curl -s http://localhost:8000/openapi.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('\\nConfiguration Endpoints:')
for path, methods in data['paths'].items():
    if 'configuration' in path:
        for method in methods:
            if method != 'parameters':
                summary = methods[method].get('summary', 'No description')
                print(f'  {method.upper():6} {path:50} - {summary}')
"
echo ""
echo "✅ Tests completed!"
