#!/bin/bash

# Rocketlane Clone Tool - Web UI Startup Script

echo "================================================================================"
echo "ROCKETLANE CLONE TOOL - WEB UI LAUNCHER"
echo "================================================================================"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "   Please install Python 3.9 or later"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Check if Flask is installed
if ! python3 -c "import flask" &> /dev/null; then
    echo "⚠️  Flask not found. Installing dependencies..."
    echo ""
    pip3 install -r requirements.txt
    echo ""
fi

echo "✅ Dependencies installed"
echo ""
echo "🚀 Starting web server..."
echo ""
echo "================================================================================"
echo ""
echo "📍 Web UI will be available at: http://localhost:5000"
echo ""
echo "⌨️  Press Ctrl+C to stop the server"
echo ""
echo "================================================================================"
echo ""

# Start the web UI
python3 web_ui.py
