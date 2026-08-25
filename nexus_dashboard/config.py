import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "db", "nexus.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")

ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
ANSIBLE_CFG_PATH = os.path.join(ANSIBLE_DIR, "ansible.cfg")
INVENTORY_PATH = os.path.join(ANSIBLE_DIR, "inventory", "hosts.yml")
VAULT_PASS_FILE = os.path.join(ANSIBLE_DIR, ".vault_pass")
HOST_VARS_DIR = os.path.join(ANSIBLE_DIR, "host_vars")
PLAYBOOKS_DIR = os.path.join(ANSIBLE_DIR, "playbooks")
ARTIFACTS_DIR = os.path.join(ANSIBLE_DIR, "artifacts")


def host_vars_dir(server_name):
    return os.path.join(HOST_VARS_DIR, server_name)


def host_vault_file(server_name):
    """Senha de sudo (become) desse servidor, criptografada - uma por servidor,
    porque servidores diferentes podem ter senhas diferentes."""
    return os.path.join(host_vars_dir(server_name), "vault.yml")


def host_vars_file(server_name):
    return os.path.join(host_vars_dir(server_name), "vars.yml")


def server_vault_configured(server_name):
    return os.path.exists(host_vault_file(server_name))

# Script legado do NEXUS (raiz do projeto), reaproveitado sem alteracoes.
LEGACY_SANITIZER_SCRIPT = os.path.abspath(os.path.join(BASE_DIR, "..", "nexus_sanitize_users.sh"))
LEGACY_SERVERS_CONF = os.path.abspath(os.path.join(BASE_DIR, "..", "servidores.conf"))

# Regras de expiracao de bloqueio.
LOCK_MAX_DAYS = 90
LOCK_WARNING_DAYS = 80

# Regras da senha temporaria de criacao de usuario (troca obrigatoria no
# primeiro login, via chage -d 0 no proprio nexus_sanitize_users.sh).
TEMP_PASSWORD_MIN_LENGTH = 10

SECRET_KEY = os.environ.get("NEXUS_DASHBOARD_SECRET", "nexus-dashboard-dev-secret")

SCHEDULER_HOUR = 3
SCHEDULER_MINUTE = 0
