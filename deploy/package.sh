#!/bin/bash
# Creates a deployment package for uploading to DigitalOcean

PACKAGE_NAME="arbbot-deploy-$(date +%Y%m%d).tar.gz"

echo "Creating deployment package: $PACKAGE_NAME"

tar -czvf $PACKAGE_NAME \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='arb_ledger.db' \
    --exclude='*.log' \
    --exclude='.streamlit' \
    --exclude='attached_assets' \
    --exclude='.replit' \
    --exclude='replit.nix' \
    --exclude='pyproject.toml' \
    --exclude='poetry.lock' \
    --exclude='.pythonlibs' \
    --exclude='.upm' \
    --exclude='.cache' \
    src/ \
    deploy/ \
    app.py \
    config.yaml \
    config_mock.yaml

echo ""
echo "Package created: $PACKAGE_NAME"
echo ""
echo "Upload to your droplet with:"
echo "  scp $PACKAGE_NAME root@YOUR_DROPLET_IP:/root/"
echo ""
echo "Then on the droplet:"
echo "  cd /root"
echo "  tar -xzvf $PACKAGE_NAME"
echo "  chmod +x deploy/install.sh"
echo "  ./deploy/install.sh"
