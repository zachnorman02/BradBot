# BradBot AWS EC2 Deployment Guide

## Prerequisites
- AWS Account
- GitHub repository with your bot code
- Discord bot token

## Step 1: Launch EC2 Instance

1. **Go to AWS EC2 Console**
   - Launch Instance
   - Choose "Ubuntu Server 22.04 LTS"
   - Instance type: t2.micro (free tier)
   - Create new key pair (download .pem file)
   - Security group: Default (no inbound rules needed for Discord bot)
   - Storage: 8GB (default)

2. **Note down:**
   - Instance Public IP address
   - Key pair name and location

## Step 2: Initial Server Setup

1. **Connect to your instance:**
```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
```

2. **Run setup script:**
```bash
curl -o setup.sh https://raw.githubusercontent.com/zachnorman02/BradBot/main/scripts/setup.sh
chmod +x setup.sh
./setup.sh
```

3. **Clone your repository:**
```bash
cd /home/ubuntu/bradbot
git clone https://github.com/zachnorman02/BradBot.git .
```

4. **Create environment file:**
```bash
cp .env.example .env
nano .env
```
Add your Discord token:
```
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

5. **Run deployment script:**
```bash
./scripts/deploy.sh
```

## Step 3: Setup GitHub Actions

1. **Add GitHub Secrets:**
   - Go to your GitHub repository
   - Settings → Secrets and variables → Actions
   - Add these secrets:
     - `EC2_HOST`: Your EC2 instance public IP
     - `EC2_SSH_KEY`: Contents of your .pem file

2. **Add your bot token to EC2:**
```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# Edit environment file
nano /home/ubuntu/bradbot/.env
```

## Step 4: Test Deployment

1. **Push code to main branch** - GitHub Actions will automatically deploy
2. **Check deployment logs** in GitHub Actions tab
3. **Monitor bot status:**
```bash
# SSH into EC2
sudo systemctl status bradbot
sudo journalctl -u bradbot -f  # View live logs
```

## Management Commands

```bash
# Check bot status
sudo systemctl status bradbot

# View logs
sudo journalctl -u bradbot -f

# Restart bot
sudo systemctl restart bradbot

# Stop bot
sudo systemctl stop bradbot

# Start bot
sudo systemctl start bradbot
```

## Troubleshooting

### Bot won't start:
1. Check logs: `sudo journalctl -u bradbot -n 50`
2. Verify token in .env file
3. Check Python dependencies: `cd /home/ubuntu/bradbot && source venv/bin/activate && pip list`

### GitHub Actions fails:
1. Check EC2 security groups allow SSH (port 22)
2. Verify SSH key is correct in GitHub secrets
3. Ensure EC2 instance is running

### Update bot code:
Just push to main branch - GitHub Actions will auto-deploy!

## Cost Estimate
- **Free tier (first 12 months):** $0/month
- **After free tier:** ~$8-10/month for t2.micro
