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

# Cores dos graficos do Painel. Status (good/warning/critical) sao valores
# fixos, validados para contraste >=3:1 contra o fundo dos cards (#1b1229) -
# nao mudam com o tema. "neutral" e um cinza deliberado (sem carga de status)
# para o estado "removido". "magnitude" e a cor unica (roxo) usada em graficos
# de comparacao de volume (nao e status).
CHART_COLOR_GOOD = "#0ca30c"
CHART_COLOR_WARNING = "#fab219"
CHART_COLOR_CRITICAL = "#d03b3b"
CHART_COLOR_NEUTRAL = "#8a8a95"
CHART_COLOR_MAGNITUDE = "#8b5cf6"

TIMELINE_DAYS = 14
TIMELINE_CHART_HEIGHT_PX = 80
SERVER_CHART_WINDOW_DAYS = 30

# Quantas linhas por pagina na tela Execucoes.
RUNS_PER_PAGE = 25

# Menor UID considerado usuario "de gente" (nao conta de sistema/servico) na
# descoberta de usuarios ja existentes no servidor ("Importar usuarios
# existentes") - convencao usual do useradd/login.defs na maioria das
# distros Linux.
DISCOVER_MIN_UID = 1000

SECRET_KEY = os.environ.get("NEXUS_DASHBOARD_SECRET", "nexus-dashboard-dev-secret")

# Depois de quanto tempo sem trocar a identificacao de operador (tela
# "Identificar operador") a sessao e considerada "velha demais" e a app pede
# pra identificar de novo antes de qualquer acao - existe pra evitar que uma
# acao fique registrada em nome de quem usou o navegador por ultimo, se a
# pessoa seguinte esquecer de clicar em "trocar" (ex.: navegador/VM
# compartilhado, ficou aberto o dia todo).
OPERATOR_SESSION_MINUTES = 30

SCHEDULER_HOUR = 3
SCHEDULER_MINUTE = 0
