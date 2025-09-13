#!/bin/bash

# BradBot Deployment Script
set -e  # Exit on any error

APP_DIR="/home/ubuntu/bradbot"
SERVICE_NAME="bradbot"

echo "🚀 Starting BradBot deployment..."

# Check if we're in the right directory
if [ ! -d "$APP_DIR" ]; then
    echo "❌ Application directory $APP_DIR not found!"
    echo "Please run the setup script first."
    exit 1
fi

# Navigate to app directory
cd $APP_DIR

# Check if this is a git repository
if [ ! -d ".git" ]; then
    echo "❌ Not a git repository! Please clone your repository first:"
    echo "cd $APP_DIR && git clone https://github.com/zachnorman02/BradBot.git ."
    exit 1
fi

# Pull latest changes (GitHub Actions will handle this)
echo "📦 Pulling latest changes..."
git pull origin main || echo "⚠️  Git pull failed - continuing with local files"

# Determine which Python version to use
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    echo "🐍 Using Python 3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    echo "🐍 Using Python 3.11"
else
    PYTHON_CMD="python3"
    echo "🐍 Using Python 3 ($(python3 --version))"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
else
    echo "✅ Virtual environment exists"
fi

# Activate virtual environment and install dependencies
echo "📋 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found!"
    exit 1
fi

pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found! Creating from template..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "📝 Please edit .env file and add your Discord token:"
        echo "   nano .env"
        echo "   Then run this script again."
        exit 1
    else
        echo "❌ No .env.example found! Please create .env file manually."
        exit 1
    fi
fi

# Stop the service if it's running
if systemctl is-active --quiet $SERVICE_NAME 2>/dev/null; then
    echo "⏹️  Stopping $SERVICE_NAME service..."
    sudo systemctl stop $SERVICE_NAME
else
    echo "ℹ️  Service $SERVICE_NAME not running"
fi

# Copy service file and reload systemd
if [ -f "bradbot.service" ]; then
    echo "🔧 Setting up systemd service..."
    sudo cp bradbot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
else
    echo "❌ bradbot.service file not found!"
    exit 1
fi

# Start the service
echo "▶️  Starting $SERVICE_NAME service..."
sudo systemctl start $SERVICE_NAME

# Wait a moment for service to start
sleep 3

# Check status
echo "📊 Checking service status..."
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ $SERVICE_NAME is running!"
    sudo systemctl status $SERVICE_NAME --no-pager --lines=5
else
    echo "❌ $SERVICE_NAME failed to start!"
    echo "📋 Service logs:"
    sudo journalctl -u $SERVICE_NAME -n 10 --no-pager
    exit 1
fi

echo ""
echo "🎉 Deployment complete!"
echo "📋 Useful commands:"
echo "   - Check status: sudo systemctl status $SERVICE_NAME"
echo "   - View logs: sudo journalctl -u $SERVICE_NAME -f"
echo "   - Restart: sudo systemctl restart $SERVICE_NAME"
echo ""
