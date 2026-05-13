#!/bin/bash

echo "========================================="
echo "Summer Fest - Push data.csv to GitHub"
echo "========================================="
echo ""
echo "Pushing data.csv to GitHub..."

# Change to the directory where the script is located
cd "$(dirname "$0")"

git add data.csv

if git diff --cached --quiet; then
    echo "No changes in data.csv. Nothing to push."
else
    # Add current date and time to the commit message
    git commit -m "Manual data refresh - $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "Pulling latest changes from GitHub first..."
    git pull origin main --no-rebase
    echo ""
    echo "Pushing to GitHub..."
    git push origin main
    echo ""
    echo "Done! Streamlit Cloud will update shortly."
fi

echo ""
echo "Press any key to close..."
read -n 1 -s
