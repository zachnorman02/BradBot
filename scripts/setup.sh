#!/bin/bash

# BradBot Server Setup Script
# Compatible with Ubuntu 22.04 and 24.04

set -e  # Exit on any error

echo "🚀 Starting BradBot server setup..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential packages
echo "🐍 Installing Python and essential packages..."
sudo apt install python3 python3-pip python3-venv git curl wget -y

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION installed"

# Install additional Python versions if needed (optional)
if [[ "$PYTHON_VERSION" < "3.11" ]]; then
    echo "📋 Installing Python 3.11 from deadsnakes PPA..."
    sudo apt install software-properties-common -y
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install python3.11 python3.11-pip python3.11-venv -y
    echo "✅ Python 3.11 installed as backup"
fi

# Create application directory
echo "📁 Creating application directory..."
sudo mkdir -p /home/ubuntu/bradbot
sudo chown ubuntu:ubuntu /home/ubuntu/bradbot

# Install additional useful packages
echo "🔧 Installing additional tools..."
sudo apt install htop nano unzip -y

echo ""
echo "✅ Setup complete!"
echo "📋 System Information:"
echo "   - OS: $(lsb_release -d | cut -f2)"
echo "   - Python: $(python3 --version)"
echo "   - Pip: $(python3 -m pip --version | cut -d' ' -f1,2)"
echo "   - Git: $(git --version | cut -d' ' -f1,2,3)"
echo ""
echo "🎯 Next steps:"
echo "   1. Clone your repository to /home/ubuntu/bradbot"
echo "   2. Create .env file with your Discord token"
echo "   3. Run the deployment script"
echo ""
