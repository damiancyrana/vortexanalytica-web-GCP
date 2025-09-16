#!/bin/bash

# Development startup script for Vortex Analytica
# This script sets up the development environment and starts the server

echo "🚀 Starting Vortex Analytica in Development Mode"
echo "================================================"

# Set development environment variables
export ENVIRONMENT=development
export REDIS_HOST=localhost
export REDIS_PORT=6379
export SESSION_SECRET_KEY=local-dev-secret-key-not-for-production-32-chars
export SMTP_USER=dev@vortexanalytica.com
export SMTP_PASS=dev-password
export PROJECT_ID=vortexanalytica-local

# Optional: Start Redis if not running (uncomment if you have Redis installed)
# redis-server --daemonize yes --port 6379 2>/dev/null || echo "Redis might already be running"

echo "✓ Environment variables set"
echo "  - ENVIRONMENT: $ENVIRONMENT"
echo "  - PROJECT_ID: $PROJECT_ID"
echo "  - REDIS_HOST: $REDIS_HOST"
echo ""

# Check if .env exists and inform user
if [ -f .env ]; then
    echo "✓ Found .env file - will be loaded automatically"
else
    echo "ℹ️  No .env file found (optional)"
fi

echo ""
echo "🌟 Starting FastAPI development server..."
echo "📱 Open: http://127.0.0.1:8080"
echo "🛑 Stop with: Ctrl+C"
echo ""

# Start the server
uvicorn Backend.app:app --reload --host 127.0.0.1 --port 8080