#!/bin/bash
# setup-pikit-git.sh — Set PiKit Git remote & identity in current directory

# --- Configuration ---
GITHUB_USER="glendon144"
REPO_NAME="PiKit"
GIT_NAME="Glendon Gross"
GIT_EMAIL="glendon144@gmail.com"
REMOTE_URL="https://github.com/$GITHUB_USER/$REPO_NAME.git"

# --- Script ---
echo "Setting Git identity for this repository..."
git config user.name "$GIT_NAME"
git config user.email "$GIT_EMAIL"

echo "Setting Git remote URL to $REMOTE_URL ..."
if git remote | grep -q '^origin$'; then
    git remote set-url origin "$REMOTE_URL"
else
    git remote add origin "$REMOTE_URL"
fi

echo "Verifying settings..."
git remote -v
git config user.name
git config user.email

echo "✅ Git remote & identity set for PiKit in $(pwd)"

