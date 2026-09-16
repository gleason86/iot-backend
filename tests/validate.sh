#!/bin/bash
set -euo pipefail
python -m py_compile scripts/influx-recovery.py scripts/encrypt-checkpoint.py scripts/restore-standby.py
# Discovers every tests/test_*.py (unit tests only). integration_provision_infra.py
# and *_drill.py deliberately do not match this pattern (they need real Docker/
# host resources) and stay out of this disposable, --network none container run.
python -m unittest discover -s tests -p 'test_*.py'
ansible-playbook tests/standby.yml -i localhost, --syntax-check
ansible-playbook playbooks/restore-checkpoint.yml -i threadripper, --syntax-check
ansible-playbook tests/render.yml -i localhost,
