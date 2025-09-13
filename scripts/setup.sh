#!/bin/bash

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11 and required packages
sudo apt install python3.11 python3.11-pip python3.11-venv git -y

# Create application directory
sudo mkdir -p /home/ubuntu/bradbot
sudo chown ubuntu:ubuntu /home/ubuntu/bradbot

# Clone repository (this will be replaced by GitHub Actions)
# git clone https://github.com/zachnorman02/BradBot.git /home/ubuntu/bradbot

echo "Setup complete! Now run the deployment script."
