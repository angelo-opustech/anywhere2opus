# Contributing to anywhere2opus

Thank you for your interest in contributing to the anywhere2opus project! This document provides guidelines and instructions for contributing.

## 📋 Code of Conduct

Please be respectful and constructive in all interactions with other contributors.

## 🚀 Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/anywhere2opus.git
   cd anywhere2opus
   ```

3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Set up development environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # For development
   pip install pytest pytest-cov black flake8 mypy
   ```

## 📝 Development Workflow

### Code Style

- Use **Black** for code formatting: `black app/`
- Use **Flake8** for linting: `flake8 app/`
- Use **mypy** for type checking: `mypy app/`

### Commit Messages

Follow conventional commits format:

```
feat: add new feature description
fix: fix bug description
docs: documentation updates
test: add or update tests
chore: maintenance tasks
refactor: code refactoring
perf: performance improvements
```

Examples:
```bash
git commit -m "feat: add AWS provider discovery"
git commit -m "fix: resolve database connection pooling issue"
git commit -m "docs: update API documentation"
```

### Making Changes

1. **Create tests** for new features or bug fixes
2. **Update documentation** if changing APIs
3. **Keep commits atomic** - one feature per commit where possible
4. **Write clear commit messages** explaining the "why" not just the "what"

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/unit/test_providers.py

# Run tests matching pattern
pytest -k "test_provider"
```

## 📚 Documentation

- Update README.md for user-facing changes
- Add docstrings to all functions and classes
- Update API documentation in docstrings
- Include type hints in function signatures

Example:
```python
def create_provider(
    self,
    data: CloudProviderCreate,
) -> CloudProvider:
    """Create a new cloud provider.
    
    Args:
        data: Provider creation payload
        
    Returns:
        Created CloudProvider instance
        
    Raises:
        ValueError: If provider name already exists
    """
```

## 🔄 Pull Request Process

1. **Update main branch**: `git pull origin main`
2. **Push your branch**: `git push origin feature/your-feature-name`
3. **Create Pull Request** on GitHub with:
   - Clear title describing the change
   - Detailed description of what changed and why
   - Reference to issue if applicable (closes #123)
   - Screenshots or logs if relevant

4. **Address review comments** as needed
5. **Ensure CI/CD passes** (tests, linting, coverage)

### PR Title Format

```
[TYPE] Description

Types: feature, fix, docs, test, refactor, perf
Examples:
- [feature] Add CloudStack provider implementation
- [fix] Fix CORS configuration vulnerability
- [docs] Update deployment guide
```

## 🎯 Priority Areas for Contribution

### High Priority
- [ ] Implement JWT authentication
- [ ] Add comprehensive test suite
- [ ] Complete CloudStackProvider implementation
- [ ] Encrypt credentials in database
- [ ] Fix CORS security issue

### Medium Priority
- [ ] Add rate limiting
- [ ] Implement request logging middleware
- [ ] Add performance monitoring
- [ ] Improve error handling

### Nice to Have
- [ ] Add GraphQL API
- [ ] Implement webhooks
- [ ] Add CLI tool
- [ ] Create web dashboard

## 🐛 Bug Reports

Include when reporting bugs:
- Python version and OS
- Exact error message and stack trace
- Steps to reproduce
- Expected vs actual behavior
- Any relevant configuration

## ✨ Feature Requests

When requesting features:
- Clear description of the use case
- Why this feature is needed
- Suggested implementation approach
- Any examples from other tools

## 📦 Release Process

1. Update version in relevant files
2. Update CHANGELOG
3. Create git tag: `git tag v1.0.0`
4. Push tag: `git push --tags`

## 🤝 Questions?

- Open an issue for discussions
- Join our community discussions
- Email: support@opustech.com.br

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thanks for making anywhere2opus better! 🙌
