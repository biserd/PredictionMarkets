# Deployment Guide - DigitalOcean

Deploy the Polymarket arbitrage bot on a DigitalOcean droplet in a non-US region (Amsterdam recommended).

## Prerequisites

- DigitalOcean account
- SSH key configured
- GitHub repository (or manual file upload)
- Polymarket API credentials (for live trading)

---

## Step 1: Create the Droplet

1. Log into DigitalOcean
2. Create a new Droplet:
   - **Region**: Amsterdam (AMS3) or any EU region
   - **OS**: Ubuntu 24.04 LTS
   - **Plan**: Basic, Shared CPU
   - **Size**: $8/month (1GB RAM, 1 vCPU)
   - **Authentication**: SSH Key (recommended)
   - **Hostname**: `polymarket-arb`

3. Note the droplet's IP address

---

## Step 2: Connect to Your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

---

## Step 3: Deploy from GitHub (Recommended)

### One-Command Install

```bash
# Download and run the installer
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/deploy/install.sh -o install.sh
chmod +x install.sh
./install.sh --repo https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

### Or step by step:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

# Run the installer
chmod +x deploy/install.sh
./deploy/install.sh --repo https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

---

## Step 3 (Alternative): Deploy from File Upload

If you prefer not to use GitHub:

```bash
# From your local machine, upload files
scp -r src deploy config.yaml requirements.txt root@YOUR_DROPLET_IP:/root/arb-bot-files/

# On the droplet
cd /root/arb-bot-files
chmod +x deploy/install.sh
./deploy/install.sh
```

---

## Step 4: Configure Credentials

```bash
# Create environment file from template
cp /home/arbbot/arb-bot/deploy/.env.example /home/arbbot/arb-bot/.env

# Edit with your credentials
nano /home/arbbot/arb-bot/.env
```

Add your Polymarket API credentials:
```
POLYMARKET_API_KEY=your_key
POLYMARKET_API_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

---

## Step 5: Start the Bot

```bash
# Start the bot
sudo systemctl start arbbot

# Check status
sudo systemctl status arbbot

# View logs
tail -f /var/log/arbbot/output.log
```

---

## Managing the Bot

### Service Commands

```bash
sudo systemctl start arbbot      # Start
sudo systemctl stop arbbot       # Stop
sudo systemctl restart arbbot    # Restart
sudo systemctl status arbbot     # Status
```

### View Logs

```bash
tail -f /var/log/arbbot/output.log   # Live output
tail -f /var/log/arbbot/error.log    # Errors
tail -n 100 /var/log/arbbot/output.log  # Last 100 lines
```

### CLI Commands

```bash
cd /home/arbbot/arb-bot
source venv/bin/activate

python -m src.cli.commands status   # Bot status
python -m src.cli.commands report   # Performance report
python -m src.cli.commands halt     # Emergency stop
python -m src.cli.commands resume   # Resume trading
```

---

## Updating from GitHub

```bash
# Stop the bot
sudo systemctl stop arbbot

# Pull latest changes
cd /home/arbbot/arb-bot
sudo -u arbbot git pull

# Update dependencies (if needed)
sudo -u arbbot bash -c "source venv/bin/activate && pip install -r requirements.txt"

# Restart
sudo systemctl start arbbot
```

---

## Switching to Live Trading

By default, the bot runs in **paper mode** (no real orders).

To enable live trading:

1. Edit the service file:
```bash
sudo nano /etc/systemd/system/arbbot.service
```

2. Change the ExecStart line (remove `--paper`):
```
ExecStart=/home/arbbot/arb-bot/venv/bin/python -m src.cli.commands run -c config.yaml
```

3. Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart arbbot
```

**WARNING**: Only enable after thorough paper trading testing!

---

## Troubleshooting

### Bot won't start

```bash
# Check service logs
sudo journalctl -u arbbot -n 50

# Test manually
sudo -u arbbot bash
cd /home/arbbot/arb-bot
source venv/bin/activate
python -m src.cli.commands run --paper -c config.yaml
```

### Connection issues

```bash
# Test Polymarket API access
curl -I https://gamma-api.polymarket.com/markets

# Should return HTTP 200 from EU servers
```

### Permission errors

```bash
sudo chown -R arbbot:arbbot /home/arbbot/arb-bot
sudo chown -R arbbot:arbbot /var/log/arbbot
```

---

## Security Checklist

- [x] Bot runs as non-root user (arbbot)
- [x] UFW firewall enabled (SSH only)
- [x] fail2ban protects against brute-force
- [x] API keys in .env (not in git)
- [x] Systemd security hardening enabled
- [ ] Disable SSH root login (recommended)
- [ ] Set up SSH key authentication only

### Disable root login (recommended)

```bash
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no
sudo systemctl restart sshd
```

---

## Backup

```bash
# Backup database and config
tar -czvf arbbot-backup-$(date +%Y%m%d).tar.gz \
  /home/arbbot/arb-bot/arb_ledger.db \
  /home/arbbot/arb-bot/config.yaml \
  /home/arbbot/arb-bot/.env
```

---

## Cost Summary

| Item | Cost |
|------|------|
| Droplet (1GB) | $8/month |
| Backups (optional) | +$1.60/month |
| **Total** | ~$10/month |
