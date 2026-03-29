# 🚀 GitHub Setup Guide para anywhere2opus

## Pré-requisitos

✅ Repositório Git local já configurado  
✅ 4 commits ready para push  
✅ Git instalado e configurado

## 📝 Passo 1: Criar Repositório no GitHub

### 1.1 Acesse GitHub
- Abra https://github.com/
- Faça login na sua conta (ou crie uma se não tiver)

### 1.2 Criar Novo Repositório
1. Clique no ícone **"+"** no canto superior direito
2. Selecione **"New repository"**

### 1.3 Preencha os Detalhes
- **Repository name**: `anywhere2opus`
- **Description**: `Cloud Migration API - Connect to AWS, GCP, Azure, OCI, and CloudStack`
- **Visibility**: Escolha **Public** ou **Private**
- **Initialize repository**: ⬜ DEIXE DESMARCADO (já temos repositório local!)

Clique em **"Create repository"**

## 🔗 Passo 2: Conectar Repositório Local ao GitHub

Após criar o repositório, você verá instruções. Execute os comandos abaixo no seu WSL:

```bash
# Entrar no diretório do projeto
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && pwd"

# Adicionar remote (substitua SEU_USERNAME pelo seu username do GitHub)
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git remote add origin https://github.com/SEU_USERNAME/anywhere2opus.git && git remote -v"

# Renomear branch para 'main' (padrão do GitHub)
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git branch -M main"

# Fazer push do código
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git push -u origin main"
```

## 🔑 Passo 3: Autenticação (Se Necessário)

Se o git pedir autenticação, você tem duas opções:

### Opção A: Personal Access Token (Recomendado)
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Clique em "Generate new token (classic)"
3. Marque: `repo`, `write:packages`, `read:packages`
4. Clique em "Generate token" e **copie o token**
5. Na linha de comando, cole o token quando pedir a senha

### Opção B: SSH Key (Mais Seguro)
Se você já tem SSH configurado:
```bash
# Usar URL SSH em vez de HTTPS
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git remote set-url origin git@github.com:SEU_USERNAME/anywhere2opus.git"
```

## 📤 Passo 4: Fazer Push Inicial

Após adicionar o remote, execute:

```bash
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git push -u origin main"
```

Você deve ver algo como:
```
Enumerating objects: 46, done.
Counting objects: 100% (46/46), done.
Delta compression using up to 8 threads
Compressing objects: 100% (40/40), done.
Writing objects: 100% (46/46), 3.88 KiB | 1.94 MiB/s, done.
Total 46 (delta 0), reused 0 (delta 0), reused pack 0
To https://github.com/SEU_USERNAME/anywhere2opus.git
 * [new branch]      main -> main
branch 'main' set to track 'origin/main'.
```

## ✅ Passo 5: Verificar no GitHub

1. Recarregue a página do seu repositório no GitHub
2. Você deve ver todos os arquivos:
   - README.md
   - CONTRIBUTING.md
   - LICENSE
   - app/
   - requirements.txt
   - docker-compose.yml
   - etc...

3. Deve haver 4 commits visíveis:
   - Initial commit: anywhere2opus cloud migration API
   - docs: add comprehensive README with setup instructions
   - chore: improve .gitignore with comprehensive patterns
   - docs: add CONTRIBUTING guidelines and MIT LICENSE

## 🔄 Passo 6: Configurar Sincronização Local

Agora você pode sincronizar alterações facilmente:

### Após fazer mudanças locais:
```bash
# Ver arquivos modificados
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git status"

# Adicionar arquivos
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git add ."

# Fazer commit
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git commit -m 'feat: sua descrição aqui'"

# Fazer push para GitHub
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git push"
```

### Para puxar mudanças do GitHub:
```bash
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git pull origin main"
```

## 🌿 Passo 7: Criar Branch de Desenvolvimento (Opcional)

Para melhor organização:

```bash
# Criar branch dev
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git checkout -b develop && git push -u origin develop"

# Voltar para main
wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git checkout main"
```

## 🎯 Próximos Passos

1. ✅ Repositório criado e sincronizado
2. ⏭️ Adicione colaboradores (Settings → Collaborators)
3. ⏭️ Configure branch protection rules
4. ⏭️ Setup CI/CD (GitHub Actions)
5. ⏭️ Comece a desenvolver com commits bem descritos!

## 📚 Referências Úteis

- Conventional Commits: https://www.conventionalcommits.org/
- GitHub CLI: https://cli.github.com/
- Git Documentation: https://git-scm.com/doc

---

**Substituições Necessárias:**
- `SEU_USERNAME` → Seu username no GitHub
- `anywhere2opus` → Nome do repositório (se diferente)

**Dúvidas?**
Consulte o arquivo CONTRIBUTING.md no repositório para mais detalhes!
