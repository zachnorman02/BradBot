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

# Pull latest changes
echo "📦 Pulling latest changes..."
CURRENT_REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
if [ -z "$CURRENT_REMOTE_URL" ]; then
    echo "❌ Git remote 'origin' is not configured."
    echo "Set it to your repository, for example:"
    echo "   git remote add origin git@github.com:zachnorman02/BradBot.git"
    exit 1
fi

echo "🔗 origin -> $CURRENT_REMOTE_URL"
if ! git pull --ff-only origin main; then
    echo ""
    echo "❌ git pull failed. Deployment has been stopped to avoid running stale code."
    echo "If your repo is private, ensure this host can authenticate to GitHub."
    echo "Recommended setup: SSH deploy key with origin using git@github.com:owner/repo.git"
    echo "Current origin: $CURRENT_REMOTE_URL"
    exit 1
fi

# Initialize and update submodules
echo "📦 Updating git submodules..."
git submodule update --init --recursive || echo "⚠️  No submodules found or submodule update failed"

# Determine which Python version to use
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    VENV_PACKAGE="python3.12-venv"
    echo "🐍 Using Python 3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    VENV_PACKAGE="python3.11-venv"
    echo "🐍 Using Python 3.11"
else
    PYTHON_CMD="python3"
    VENV_PACKAGE="python3-venv"
    echo "🐍 Using Python 3 ($(python3 --version))"
fi

# Ensure venv package is installed
echo "🔧 Ensuring virtual environment package is installed..."
if ! dpkg -l | grep -q "$VENV_PACKAGE"; then
    echo "📦 Installing $VENV_PACKAGE..."
    sudo apt update
    sudo apt install "$VENV_PACKAGE" -y
else
    echo "✅ $VENV_PACKAGE already installed"
fi

# Create virtual environment if it doesn't exist or is broken
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
elif [ ! -f "venv/bin/activate" ]; then
    echo "🔧 Virtual environment is broken, recreating..."
    rm -rf venv
    $PYTHON_CMD -m venv venv
else
    echo "✅ Virtual environment exists and is healthy"
fi

# Verify virtual environment was created successfully
if [ ! -f "venv/bin/activate" ]; then
    echo "❌ Failed to create virtual environment!"
    echo "🔧 Trying to install missing packages..."
    sudo apt update
    sudo apt install "$VENV_PACKAGE" -y
    rm -rf venv
    $PYTHON_CMD -m venv venv
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
