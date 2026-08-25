import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "db", "nexus.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")

ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
ANSIBLE_CFG_PATH = os.path.join(ANSIBLE_DIR, "ansible.cfg")
INVENTORY_PATH = os.path.join(ANSIBLE_DIR, "inventory", "hosts.yml")
VAULT_PASS_FILE = os.path.join(ANSIBLE_DIR, ".vault_pass")
VAULT_VARS_FILE = os.path.join(ANSIBLE_DIR, "group_vars", "all", "vault.yml")
PLAYBOOKS_DIR = os.path.join(ANSIBLE_DIR, "playbooks")
ARTIFACTS_DIR = os.path.join(ANSIBLE_DIR, "artifacts")

# Script legado do NEXUS (raiz do projeto), reaproveitado sem alteracoes.
LEGACY_SANITIZER_SCRIPT = os.path.abspath(os.path.join(BASE_DIR, "..", "nexus_sanitize_users.sh"))
LEGACY_SERVERS_CONF = os.path.abspath(os.path.join(BASE_DIR, "..", "servidores.conf"))

# Regras de expiracao de bloqueio.
LOCK_MAX_DAYS = 90
LOCK_WARNING_DAYS = 80

SECRET_KEY = os.environ.get("NEXUS_DASHBOARD_SECRET", "nexus-dashboard-dev-secret")

SCHEDULER_HOUR = 3
SCHEDULER_MINUTE = 0
