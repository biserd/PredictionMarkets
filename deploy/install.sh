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
GITHUB_REPO=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            GITHUB_REPO="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./install.sh [--repo https://github.com/user/repo.git]"
            exit 1
            ;;
    esac
done

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
mkdir -p $LOG_DIR
chown -R $BOT_USER:$BOT_USER $LOG_DIR

echo -e "${YELLOW}Step 5: Setting up bot files...${NC}"

if [ -n "$GITHUB_REPO" ]; then
    # Clone from GitHub
    echo "Cloning from GitHub: $GITHUB_REPO"
    if [ -d "$BOT_DIR" ]; then
        echo "Directory exists, pulling latest..."
        sudo -u $BOT_USER bash -c "cd $BOT_DIR && git pull"
    else
        sudo -u $BOT_USER git clone "$GITHUB_REPO" "$BOT_DIR"
    fi
elif [ -d "src" ]; then
    # Copy from current directory (manual upload)
    echo "Copying from current directory..."
    mkdir -p $BOT_DIR
    cp -r src $BOT_DIR/
    cp -r deploy $BOT_DIR/
    cp *.py $BOT_DIR/ 2>/dev/null || true
    cp *.yaml $BOT_DIR/ 2>/dev/null || true
    cp requirements.txt $BOT_DIR/ 2>/dev/null || true
    chown -R $BOT_USER:$BOT_USER $BOT_DIR
else
    echo -e "${RED}Error: No source files found.${NC}"
    echo "Either:"
    echo "  1. Run with --repo https://github.com/user/repo.git"
    echo "  2. Run from a directory containing src/"
    exit 1
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
cp $BOT_DIR/deploy/arbbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable arbbot

echo -e "${YELLOW}Step 8: Configuring firewall...${NC}"
ufw allow ssh
ufw --force enable
echo "Firewall enabled (SSH allowed)"

echo -e "${YELLOW}Step 9: Configuring fail2ban...${NC}"
systemctl enable fail2ban
systemctl start fail2ban

echo -e "${YELLOW}Step 10: Setting up log rotation...${NC}"
cat > /etc/logrotate.d/arbbot << 'LOGROTATE'
/var/log/arbbot/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 arbbot arbbot
}
LOGROTATE

echo ""
echo -e "${GREEN}=========================================="
echo "  Installation Complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Create your .env file:"
echo "   cp $BOT_DIR/deploy/.env.example $BOT_DIR/.env"
echo "   nano $BOT_DIR/.env"
echo ""
echo "2. Add your Polymarket credentials to .env"
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
echo "See deploy/README.md to enable live trading."
