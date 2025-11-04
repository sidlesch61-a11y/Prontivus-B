#!/bin/bash
# Render build script for Prontivus Backend
# This script runs during the build phase on Render.com

set -e  # Exit on any error

echo "🚀 Starting Prontivus Backend build..."

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run database migrations (optional - uncomment if you want auto-migrations)
# echo "🔄 Running database migrations..."
# alembic upgrade head

echo "✅ Build complete!"

