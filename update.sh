#!/bin/bash
#
# VoidCrypt Updater
# Pulls latest version from GitHub without touching your .env and data
#
# Usage: ./update.sh
#

set -e

REPO="https://github.com/nabzclan-reborn/VoidCrypt.git"
BRANCH="main"
BACKUP_DIR=".voidcrypt_backup_$(date +%s)"

# Get current version
get_current_version() {
    if [ -f "VERSION" ]; then
        cat VERSION
    else
        echo "unknown"
    fi
}

# Get latest version from GitHub
get_latest_version() {
    curl -s "https://raw.githubusercontent.com/nabzclan-reborn/VoidCrypt/$BRANCH/VERSION" 2>/dev/null || echo ""
}

echo "========================================"
echo "  VoidCrypt Updater"
echo "========================================"
echo ""

# Check if we're in a voidcrypt directory
if [ ! -f "voidcrypt.py" ]; then
    echo "Error: Run this script from your VoidCrypt directory"
    exit 1
fi

CURRENT_VERSION=$(get_current_version)
LATEST_VERSION=$(get_latest_version)

echo "Current version: v$CURRENT_VERSION"

if [ -n "$LATEST_VERSION" ] && [ "$LATEST_VERSION" != "$CURRENT_VERSION" ]; then
    echo "Update available: v$LATEST_VERSION"
    echo ""
elif [ -n "$LATEST_VERSION" ]; then
    echo "You are on the latest version!"
    echo ""
    read -p "Force re-download anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "No update needed."
        exit 0
    fi
else
    echo "Could not check for updates (offline?)"
    echo ""
fi

# Check for uncommitted changes
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "WARNING: You have uncommitted changes in this directory."
    echo "These will be backed up but NOT automatically restored."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Update cancelled."
        exit 1
    fi
fi

# Check if .env exists and warn
if [ -f ".env" ]; then
    echo "Your .env file will be preserved."
fi

echo ""
echo "Backing up your changes..."
mkdir -p "$BACKUP_DIR"

# Backup everything except .git, update stuff, andvenv
rsync -av --exclude='.git' --exclude='update.sh' --exclude='venv' --exclude='.env' --exclude='*.enc' --exclude='__pycache__' . "$BACKUP_DIR/" 2>/dev/null || cp -r . "$BACKUP_DIR/"

echo "Backup saved to: $BACKUP_DIR"
echo ""

# Pull latest from GitHub
echo "Fetching latest version..."
if git ls-remote --exit-code --heads "$REPO" "$BRANCH" >/dev/null 2>&1; then
    # Configure remote if needed
    if ! git remote | grep -q origin; then
        git remote add origin "$REPO" 2>/dev/null || true
    fi

    # Fetch and reset
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
    echo "Successfully updated to latest version!"
else
    echo "Warning: Could not reach GitHub. Keeping local version."
    echo "Backup is available at: $BACKUP_DIR"
    exit 1
fi

echo ""
echo "========================================"
echo "  Update Complete!"
echo "========================================"
echo ""
echo "Your files were preserved:"
echo "  - .env (your configuration)"
echo "  - Any .enc vault files"
echo "  - Your backup at: $BACKUP_DIR"
echo ""
echo "If you modified core files and want them restored:"
echo "  cp -r $BACKUP_DIR/* ."
echo ""
echo "Reminder: Restart VoidCrypt after updating."
echo "========================================"
