# anywhere2opus - Cloud Migration API

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-312/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.35-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-29.3.1-2496ED.svg)](https://www.docker.com/)

A unified cloud migration API that enables seamless discovery, management, and migration of cloud resources between multiple cloud providers.

## 🌐 Supported Cloud Providers

- ☁️ **AWS** - Amazon Web Services
- 🔷 **GCP** - Google Cloud Platform
- 🔵 **Azure** - Microsoft Azure
- 🟠 **OCI** - Oracle Cloud Infrastructure
- 🟣 **CloudStack / Opus** - On-premises cloud platform

## ✨ Features

- **Multi-Cloud Discovery** - Discover and inventory resources across multiple cloud providers
- **Resource Management** - Create, read, update, and delete cloud resources
- **Migration Planning** - Plan migrations between different cloud providers
- **Credential Management** - Securely store and manage cloud provider credentials
- **REST API** - Comprehensive REST API with OpenAPI/Swagger documentation
- **Database Tracking** - PostgreSQL-backed persistent storage
- **Structured Logging** - Production-ready logging with structlog
- **Docker Support** - Complete Docker and docker-compose setup

## 📋 Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Docker & Docker Compose (optional)
- Git

## 🚀 Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/anywhere2opus.git
cd anywhere2opus

# Start services
docker compose up -d

# API will be available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Manual Setup (WSL/Linux/Mac)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Start PostgreSQL (Docker)
docker compose up -d postgres

# Create database tables
python -c "from app.database import create_tables; create_tables()"

# Run application
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Application
APP_NAME=anywhere2opus
APP_ENV=development
APP_DEBUG=true
APP_PORT=8000

# Database
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/anywhere2opus

# Security
SECRET_KEY=your-secret-key-change-in-production

# Cloud Provider Credentials
AWS_ACCESS_KEY_ID=...
GCP_PROJECT_ID=...
AZURE_SUBSCRIPTION_ID=...
OCI_TENANCY_OCID=...
CLOUDSTACK_URL=...
```

## 📚 API Documentation

Once the application is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Core Endpoints

```
GET  /api/v1/providers              # List all cloud providers
POST /api/v1/providers              # Create a new provider
GET  /api/v1/providers/{id}         # Get provider details
PUT  /api/v1/providers/{id}         # Update provider
DELETE /api/v1/providers/{id}       # Delete provider
POST /api/v1/providers/{id}/sync    # Discover resources

GET  /api/v1/resources              # List all resources
POST /api/v1/resources              # Create new resource
GET  /api/v1/resources/{id}         # Get resource details
PUT  /api/v1/resources/{id}         # Update resource
DELETE /api/v1/resources/{id}       # Delete resource

GET  /api/v1/migrations             # List migrations
POST /api/v1/migrations             # Create migration job
GET  /api/v1/migrations/{id}        # Get migration status
```

## 📁 Project Structure

```
anywhere2opus/
├── app/
│   ├── api/                 # API routers and endpoints
│   │   ├── routes/         # Endpoint implementations
│   │   └── deps.py         # FastAPI dependencies
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic
│   ├── providers/          # Cloud provider implementations
│   ├── config.py           # Configuration
│   ├── database.py         # Database setup
│   └── main.py             # FastAPI app entry point
├── alembic/                # Database migrations
├── docker-compose.yml      # Docker services
├── Dockerfile              # Container image
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
└── README.md              # This file
```

## 🧪 Testing

```bash
# Run unit tests (coming soon)
pytest

# Run with coverage
pytest --cov=app

# Run integration tests
pytest tests/integration/
```

## 🔐 Security Considerations

- ⚠️ **Development Only**: Never use default credentials in production
- 🔒 **Database**: Encrypt credentials_json column in production
- 🛡️ **CORS**: Configure to specific origins only
- 🔑 **Secrets**: Use environment variables or secure secrets manager
- 🔐 **HTTPS**: Always use HTTPS in production
- 👤 **Authentication**: Implement JWT or OAuth2 (coming soon)

## 📈 Production Checklist

- [ ] Implement authentication/authorization
- [ ] Enable HTTPS/TLS
- [ ] Configure proper CORS origins
- [ ] Set up monitoring and alerting
- [ ] Implement request logging
- [ ] Add rate limiting
- [ ] Database backups strategy
- [ ] Error tracking (Sentry, etc.)
- [ ] Performance monitoring
- [ ] Security audit

## 🐛 Known Issues & TODOs

- [ ] CloudStackProvider implementation incomplete
- [ ] No authentication/authorization implemented
- [ ] No automated tests yet
- [ ] CORS is open to all origins (security issue)
- [ ] Credentials not encrypted in database
- [ ] Rate limiting not implemented
- [ ] Async endpoints need refactoring

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/anywhere2opus/issues
- Email: support@opustech.com.br

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit and ORM
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [structlog](https://www.structlog.org/) - Structured logging
- Cloud provider SDKs: boto3, google-cloud, azure-identity, oci

---

**Last Updated**: March 29, 2026  
**Version**: 1.0.0-alpha  
**Status**: 🚀 Development
