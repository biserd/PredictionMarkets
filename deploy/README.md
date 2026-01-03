# Deployment Guide - DigitalOcean Amsterdam

This guide walks you through deploying the Polymarket arbitrage bot on a DigitalOcean droplet in Amsterdam (or any non-US region).

## Prerequisites

- DigitalOcean account
- SSH key configured
- Polymarket API credentials (for live trading)

---

## Step 1: Create the Droplet

1. Log into DigitalOcean
2. Create a new Droplet with these settings:
   - **Region**: Amsterdam (AMS3) or any EU region
   - **OS**: Ubuntu 24.04 LTS
   - **Plan**: Basic, Shared CPU
   - **Size**: $8/month (1GB RAM, 1 vCPU) - sufficient for the bot
   - **Authentication**: SSH Key (recommended)
   - **Hostname**: `polymarket-arb` or similar

3. Note the droplet's IP address after creation

---

## Step 2: Connect to Your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

---

## Step 3: Upload Bot Files

From your local machine, upload the bot files:

```bash
# Option A: Using scp (from project root)
scp -r src deploy config.yaml config_mock.yaml requirements.txt root@YOUR_DROPLET_IP:/root/arb-bot-files/

# Option B: Using rsync
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'venv' \
  ./ root@YOUR_DROPLET_IP:/root/arb-bot-files/
```

---

## Step 4: Run the Install Script

On the droplet:

```bash
cd /root/arb-bot-files
chmod +x deploy/install.sh
./deploy/install.sh
```

This script will:
- Update system packages
- Install Python 3 and dependencies
- Create a dedicated `arbbot` user
- Set up the virtual environment
- Install the systemd service
- Configure firewall and fail2ban

---

## Step 5: Configure the Bot

1. **Create environment file**:
```bash
cp /home/arbbot/arb-bot/deploy/.env.example /home/arbbot/arb-bot/.env
nano /home/arbbot/arb-bot/.env
```

2. **Fill in your Polymarket credentials** (for live trading):
```
POLYMARKET_API_KEY=your_key
POLYMARKET_API_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

3. **Review config.yaml** (optional):
```bash
nano /home/arbbot/arb-bot/config.yaml
```

---

## Step 6: Start the Bot

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

### Common Commands

```bash
# Start bot
sudo systemctl start arbbot

# Stop bot
sudo systemctl stop arbbot

# Restart bot
sudo systemctl restart arbbot

# Check status
sudo systemctl status arbbot

# View output logs
tail -f /var/log/arbbot/output.log

# View error logs
tail -f /var/log/arbbot/error.log

# View last 100 lines of logs
tail -n 100 /var/log/arbbot/output.log
```

### CLI Commands (Manual)

```bash
# Activate virtual environment
cd /home/arbbot/arb-bot
source venv/bin/activate

# Check bot status
python -m src.cli.commands status

# Generate performance report
python -m src.cli.commands report

# Manually halt trading
python -m src.cli.commands halt

# Resume trading
python -m src.cli.commands resume
```

---

## Updating the Bot

When you have new code:

```bash
# 1. Stop the bot
sudo systemctl stop arbbot

# 2. Upload new files
# (from local machine)
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'venv' \
  ./ root@YOUR_DROPLET_IP:/home/arbbot/arb-bot/

# 3. Fix permissions
sudo chown -R arbbot:arbbot /home/arbbot/arb-bot

# 4. Update dependencies (if needed)
sudo -u arbbot bash -c "cd /home/arbbot/arb-bot && source venv/bin/activate && pip install -r requirements.txt"

# 5. Restart the bot
sudo systemctl start arbbot
```

---

## Switching to Live Trading

By default, the bot runs in **paper mode** (no real orders).

To enable live trading:

1. **Edit the service file**:
```bash
sudo nano /etc/systemd/system/arbbot.service
```

2. **Change the ExecStart line** (remove `--paper`):
```
ExecStart=/home/arbbot/arb-bot/venv/bin/python -m src.cli.commands run -c config.yaml
```

3. **Reload and restart**:
```bash
sudo systemctl daemon-reload
sudo systemctl restart arbbot
```

**WARNING**: Only do this after thorough testing in paper mode!

---

## Monitoring

### Resource Usage
```bash
htop  # Interactive process viewer
```

### Disk Space
```bash
df -h
```

### Bot Process
```bash
ps aux | grep python
```

---

## Log Rotation

Create `/etc/logrotate.d/arbbot`:

```
/var/log/arbbot/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 arbbot arbbot
    sharedscripts
    postrotate
        systemctl reload arbbot > /dev/null 2>&1 || true
    endscript
}
```

---

## Troubleshooting

### Bot won't start
```bash
# Check for errors
sudo journalctl -u arbbot -n 50

# Check permissions
ls -la /home/arbbot/arb-bot/

# Test manually
sudo -u arbbot bash
cd /home/arbbot/arb-bot
source venv/bin/activate
python -m src.cli.commands run --paper -c config.yaml
```

### Connection issues
```bash
# Test Polymarket connectivity
curl -I https://gamma-api.polymarket.com/markets

# Check if firewall is blocking outbound
sudo ufw status
```

### High memory usage
```bash
# Check memory
free -h

# Restart bot to clear memory
sudo systemctl restart arbbot
```

---

## Security Notes

- The bot runs as a non-root user (`arbbot`)
- SSH root login should be disabled in production
- UFW firewall only allows SSH
- fail2ban protects against brute-force attacks
- API keys are stored in `.env` (never commit to git)
- The service runs with security hardening (NoNewPrivileges, ProtectSystem)

---

## Backup

```bash
# Backup the database and config
tar -czvf arbbot-backup-$(date +%Y%m%d).tar.gz \
  /home/arbbot/arb-bot/arb_ledger.db \
  /home/arbbot/arb-bot/config.yaml \
  /home/arbbot/arb-bot/.env
```

---

## Cost Estimate

- **Droplet**: $8/month (1GB RAM)
- **Backups** (optional): +$1.60/month
- **Total**: ~$10/month

---

## Support

Check the logs first:
```bash
tail -f /var/log/arbbot/output.log
tail -f /var/log/arbbot/error.log
```
