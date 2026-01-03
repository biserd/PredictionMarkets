#!/bin/bash
set -e

echo "=========================================="
echo "  Polymarket Arbitrage Bot - Setup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BOT_USER="arbbot"
BOT_DIR="/home/${BOT_USER}/arb-bot"
LOG_DIR="/var/log/arbbot"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Updating system packages...${NC}"
apt update && apt upgrade -y

echo -e "${YELLOW}Step 2: Installing Python and dependencies...${NC}"
apt install -y python3 python3-pip python3-venv git ufw fail2ban htop

echo -e "${YELLOW}Step 3: Creating bot user...${NC}"
if id "$BOT_USER" &>/dev/null; then
    echo "User $BOT_USER already exists"
else
    adduser --disabled-password --gecos "" $BOT_USER
    echo "User $BOT_USER created"
fi

echo -e "${YELLOW}Step 4: Creating directories...${NC}"
mkdir -p $BOT_DIR
mkdir -p $LOG_DIR
chown -R $BOT_USER:$BOT_USER $BOT_DIR
chown -R $BOT_USER:$BOT_USER $LOG_DIR

echo -e "${YELLOW}Step 5: Copying bot files...${NC}"
# Copy all source files (run this from the directory containing src/)
if [ -d "src" ]; then
    cp -r src $BOT_DIR/
    cp -r *.py $BOT_DIR/ 2>/dev/null || true
    cp -r *.yaml $BOT_DIR/ 2>/dev/null || true
    cp requirements.txt $BOT_DIR/ 2>/dev/null || true
    chown -R $BOT_USER:$BOT_USER $BOT_DIR
    echo "Files copied to $BOT_DIR"
else
    echo -e "${RED}Warning: src/ directory not found. Copy files manually.${NC}"
fi

echo -e "${YELLOW}Step 6: Setting up Python virtual environment...${NC}"
sudo -u $BOT_USER bash << EOF
cd $BOT_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF

echo -e "${YELLOW}Step 7: Installing systemd service...${NC}"
cp deploy/arbbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable arbbot

echo -e "${YELLOW}Step 8: Configuring firewall...${NC}"
ufw allow ssh
ufw --force enable
echo "Firewall enabled (SSH allowed)"

echo -e "${YELLOW}Step 9: Configuring fail2ban...${NC}"
systemctl enable fail2ban
systemctl start fail2ban

echo ""
echo -e "${GREEN}=========================================="
echo "  Installation Complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Copy your .env file to $BOT_DIR/.env"
echo "   (Use .env.example as a template)"
echo ""
echo "2. Update config.yaml with your settings:"
echo "   nano $BOT_DIR/config.yaml"
echo ""
echo "3. Start the bot:"
echo "   sudo systemctl start arbbot"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status arbbot"
echo ""
echo "5. View logs:"
echo "   tail -f $LOG_DIR/output.log"
echo ""
echo -e "${YELLOW}Important: The bot starts in PAPER MODE by default.${NC}"
echo "Edit config.yaml to enable live trading."
