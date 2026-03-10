#!/bin/bash
# Deploy FEC 2024 Dashboard to GitHub Pages
# Run this script from the fec-2024-dashboard directory

set -e

REPO_NAME="fec-2024-dashboard"

echo "=== FEC 2024 Campaign Tech Spending Dashboard ==="
echo "This script will create a GitHub repo and deploy to GitHub Pages."
echo ""

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) not found. Install it: https://cli.github.com/"
    echo ""
    echo "Alternative manual steps:"
    echo "1. Go to https://github.com/new"
    echo "2. Create a repo named '$REPO_NAME'"
    echo "3. Run these commands:"
    echo "   git init"
    echo "   git add -A"
    echo "   git commit -m 'Initial commit: FEC 2024 campaign tech spending dashboard'"
    echo "   git branch -M main"
    echo "   git remote add origin https://github.com/YOUR_USERNAME/$REPO_NAME.git"
    echo "   git push -u origin main"
    echo "4. Go to repo Settings > Pages > Source: Deploy from branch > main > / (root)"
    echo "5. Your site will be live at https://YOUR_USERNAME.github.io/$REPO_NAME/"
    exit 1
fi

# Create repo
echo "Creating GitHub repository..."
gh repo create "$REPO_NAME" --public --description "2024 FEC Campaign Tech & Digital Spending Dashboard - Interactive analysis of $2B+ in political tech vendor spending"

# Init and push
git init
git add -A
git commit -m "Initial commit: FEC 2024 campaign tech spending dashboard

Interactive dashboard analyzing $2B+ in political tech vendor spending across
20 vendors, 6 categories, covering the 2024 federal election cycle.

Data sources: FEC OpenFEC API, OpenSecrets, Brennan Center/Wesleyan Media Project."

git branch -M main
git remote add origin "$(gh repo view "$REPO_NAME" --json sshUrl -q .sshUrl)"
git push -u origin main

# Enable GitHub Pages
echo "Enabling GitHub Pages..."
gh api repos/{owner}/$REPO_NAME/pages -X POST -f source='{"branch":"main","path":"/"}' 2>/dev/null || \
gh api repos/{owner}/$REPO_NAME/pages -X PUT -f source='{"branch":"main","path":"/"}'

echo ""
echo "=== DONE ==="
OWNER=$(gh api user -q .login)
echo "Repository: https://github.com/$OWNER/$REPO_NAME"
echo "Dashboard:  https://$OWNER.github.io/$REPO_NAME/"
echo ""
echo "Note: GitHub Pages may take 1-2 minutes to deploy."
