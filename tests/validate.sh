#!/bin/bash
set -euo pipefail
python -m py_compile scripts/influx-recovery.py scripts/encrypt-checkpoint.py scripts/restore-standby.py
python -m unittest discover -s tests -p 'test_monitor.py'
ansible-playbook tests/standby.yml -i localhost, --syntax-check
ansible-playbook playbooks/restore-checkpoint.yml -i threadripper, --syntax-check
ansible-playbook tests/render.yml -i localhost,
