#!/usr/bin/env bash
# Serverda yangilash: GitHub dan oxirgi kodni olib, kutubxonalarni yangilab, botni qayta ishga tushiradi.
#   ssh azureuser@SERVER 'bash ~/fin-zayavka/deploy/update.sh'
set -euo pipefail
cd /home/azureuser/fin-zayavka
git pull --ff-only origin main
.venv/bin/pip install -q -r requirements.txt
sudo systemctl restart fin-zayavka
sleep 2
systemctl --no-pager --lines=5 status fin-zayavka
