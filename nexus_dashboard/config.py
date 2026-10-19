import os
import secrets

from werkzeug.security import generate_password_hash

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

# Senha padrao usada informalmente pela equipe - proibida como temporaria
# porque vira senha "de fato" para varios usuarios (nunca e trocada de verdade).
TEMP_PASSWORD_BANNED = "Br@$torag3"

# Shells selecionaveis na criacao de usuario - o primeiro item e o padrao
# (pre-selecionado no formulario e usado se o valor enviado nao for um destes).
AVAILABLE_SHELLS = [
    ("/bin/bash", "/bin/bash (padrao, acesso interativo)"),
    ("/usr/sbin/nologin", "/usr/sbin/nologin (sem acesso interativo - conta de servico)"),
]

# Nome do grupo que da privilegio de administrador num servidor recem-
# cadastrado, se o cadastro nao informar outro (a maioria das distros usa
# "sudo" - Debian/Ubuntu; CentOS/RHEL usa "wheel").
DEFAULT_ADMIN_GROUP = "sudo"

# Placeholder usado no formulario de "Nova acao" no lugar do nome literal do
# grupo administrativo - cada servidor pode ter um nome diferente (sudo x
# wheel), entao a acao guarda esse token e o resolve para o grupo real de
# cada servidor de destino na hora de executar (ver app.py:_run_action).
ADMIN_GROUP_TOKEN = "__ADMIN__"

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

# Em producao, defina NEXUS_DASHBOARD_SECRET num valor fixo (senao a sessao
# de cada operador e invalidada a cada reinicio do processo); sem a variavel
# definida, gera uma chave aleatoria por processo em vez de usar um valor
# fixo conhecido no codigo-fonte.
SECRET_KEY = os.environ.get("NEXUS_DASHBOARD_SECRET") or secrets.token_hex(32)

# Login do painel - uso pessoal (nao e multiusuario), por isso e uma
# credencial fixa em vez de uma tabela de usuarios. Em producao, defina
# NEXUS_DASHBOARD_PASSWORD_HASH (gerado com werkzeug.security.generate_password_hash)
# num valor fixo - sem a variavel definida, gera o hash a partir de
# NEXUS_DASHBOARD_PASSWORD (ou da senha padrao abaixo) a cada start do
# processo; a senha em si nunca fica gravada em texto puro.
DASHBOARD_USERNAME = os.environ.get("NEXUS_DASHBOARD_USERNAME", "julyana.silva")
DASHBOARD_DISPLAY_NAME = os.environ.get("NEXUS_DASHBOARD_DISPLAY_NAME", "Julyana Silva")
DASHBOARD_PASSWORD_HASH = os.environ.get("NEXUS_DASHBOARD_PASSWORD_HASH") or generate_password_hash(
    os.environ.get("NEXUS_DASHBOARD_PASSWORD", "Br@$torag3")
)

# NEXUS AI - balaozinho de suporte do painel (ver support_bot.py). 100% local,
# sem IA nem chamada de rede - so reconhece a pergunta por palavra-chave e
# responde com dados que ja estao no banco.
SUPPORT_BOT_NAME = "NEXUS AI"

SCHEDULER_HOUR = 3
SCHEDULER_MINUTE = 0
