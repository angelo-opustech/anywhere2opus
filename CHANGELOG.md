# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto segue [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-alpha] - 2026-03-29

### Added
- Initial project setup with FastAPI framework
- PostgreSQL database integration with SQLAlchemy ORM
- Alembic database migrations support
- Multi-cloud provider support (AWS, GCP, Azure, OCI, CloudStack)
- Cloud resource discovery and inventory management
- REST API with OpenAPI/Swagger documentation
- Docker and Docker Compose configuration
- Structured logging with structlog
- Comprehensive README and documentation
- Contributing guidelines
- MIT License

### Features
- **Providers API**: Create, read, update, delete cloud providers
- **Resources API**: Manage discovered cloud resources
- **Migrations API**: Plan and track cloud migrations
- **Health Check**: Application health monitoring endpoint
- **Multi-environment support**: Development, staging, production configurations

### Infrastructure
- Python 3.12 support
- Docker containerization
- PostgreSQL 16 database
- Uvicorn ASGI server with auto-reload in development
- Connection pooling with SQLAlchemy
- Security headers and CORS middleware

## [Unreleased]

### Planned Features
- JWT authentication and authorization
- Rate limiting and request throttling
- Webhook support for migration events
- WebSocket real-time updates
- GraphQL API
- CLI tool for local management
- Web dashboard
- Encryption for stored credentials
- Database backup automation
- Enhanced monitoring and alerting

### Security Improvements
- Implement OAuth2/JWT authentication
- Encrypt sensitive data in database
- Add request signing for API calls
- Implement rate limiting
- Add security headers middleware
- Setup API key rotation

### Testing
- Unit tests for all services
- Integration tests for API endpoints
- Provider mocking for tests
- End-to-end test suite
- Performance and load testing

### Documentation
- API endpoint documentation
- Provider setup guides
- Deployment guide for production
- Architecture decision records (ADRs)
- Troubleshooting guide

## Version History

### [0.9.0] - Pre-alpha
- Project initialization
- Base architecture setup
- Initial database schema

---

## Guidelines for Updates

### For Features
```markdown
### Added
- Description of new feature
- Description of another feature
```

### For Bug Fixes
```markdown
### Fixed
- Description of bug fix
```

### For Breaking Changes
```markdown
### Changed
- Description of breaking change

### Deprecated
- Feature that will be removed soon
```

When creating a commit, reference the changelog item:
```bash
git commit -m "feat: implement JWT authentication

- Add /auth/login endpoint
- Add /auth/refresh endpoint
- Protect routes with JWT validation

Relates to: Feature Authentication in CHANGELOG"
```
