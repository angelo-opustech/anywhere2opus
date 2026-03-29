#!/bin/bash
# Helper script to make git operations easier in WSL

set -e

echo "📦 Anywhere2opus Git Helper"
echo "================================"
echo ""

# Determine action
ACTION=${1:-help}

case $ACTION in
    status)
        echo "📋 Git Status:"
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git status"
        ;;
    
    log)
        echo "📝 Git Log:"
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git log --oneline -10"
        ;;
    
    add)
        echo "➕ Adding all changes..."
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git add . && echo '✅ Changes staged'"
        ;;
    
    commit)
        if [ -z "$2" ]; then
            echo "❌ Message required: ./git-helper.sh commit 'your message'"
            exit 1
        fi
        echo "💾 Committing changes..."
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git commit -m '$2' && echo '✅ Committed'"
        ;;
    
    push)
        echo "🚀 Pushing to GitHub..."
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git push && echo '✅ Pushed successfully'"
        ;;
    
    pull)
        echo "⬇️ Pulling from GitHub..."
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git pull && echo '✅ Pulled successfully'"
        ;;
    
    sync)
        echo "🔄 Syncing with GitHub..."
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git pull && git push && echo '✅ Synced successfully'"
        ;;
    
    branch)
        if [ -z "$2" ]; then
            echo "🌿 Current branches:"
            wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git branch -a"
        else
            echo "🌿 Creating branch: $2"
            wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git checkout -b $2 && git push -u origin $2 && echo '✅ Branch created and pushed'"
        fi
        ;;
    
    remote)
        echo "🔗 Git Remotes:"
        wsl -d Ubuntu-24.04 -e bash -c "cd /home/projects/anywhere2opus && git remote -v"
        ;;
    
    help)
        cat << 'EOF'
Git Helper for anywhere2opus

Usage:
  ./git-helper.sh [command] [options]

Commands:
  status              Show git status
  log                 Show commit history
  add                 Stage all changes
  commit <message>    Create commit with message
  push                Push to GitHub
  pull                Pull from GitHub
  sync                Pull and push (synchronize)
  branch [name]       List branches or create new one
  remote              Show remote repositories
  help                Show this help message

Examples:
  ./git-helper.sh status
  ./git-helper.sh commit "feat: add new feature"
  ./git-helper.sh push
  ./git-helper.sh branch "feature/new-api"
  ./git-helper.sh sync

EOF
        ;;
    
    *)
        echo "❌ Unknown command: $ACTION"
        echo "Run './git-helper.sh help' for usage"
        exit 1
        ;;
esac
