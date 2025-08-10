#!/bin/bash
# save as commit_working_state.sh
# usage: bash commit_working_state.sh

cd "$(dirname "$0")"

# Check Git identity
name=$(git config --get user.name)
email=$(git config --get user.email)

if [[ -z "$name" || -z "$email" ]]; then
    echo "❌ Git identity not set!"
    echo "Please set it with:"
    echo "  git config --global user.name \"Your Name\""
    echo "  git config --global user.email \"you@example.com\""
    exit 1
fi

echo "✅ Git identity is set to: $name <$email>"

# Determine next tag version
base_tag="milestone-hyperscope-working"
last_tag=$(git tag --list "${base_tag}-v*" | sort -V | tail -n 1)

if [[ -z "$last_tag" ]]; then
    next_tag="${base_tag}-v1"
else
    last_num=${last_tag##*-v}
    next_num=$((last_num + 1))
    next_tag="${base_tag}-v${next_num}"
fi

# Stage and commit changes
git add -A
commit_msg="✅ Working state: fixed document rendering, restored BACK button image-clearing behavior, integrated and verified OPML parsing (Hyperscope tutorial working flawlessly). Includes TabNanny clean bill of health."
git commit -m "$commit_msg"

# Tag the commit
git tag -a "$next_tag" -m "Stable Hyperscope tutorial milestone (PyKit fully functional)."
echo "🏷️  Created Git tag: $next_tag"

# Optional: push to remote (uncomment to enable)
# git push
# git push origin "$next_tag"

echo "✅ Commit complete: $commit_msg"
echo "🔹 Use 'git checkout $next_tag' to restore this exact version."

