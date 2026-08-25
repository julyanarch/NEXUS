import base64
import csv
import os
import re
import shutil
import tempfile
import uuid

import ansible_runner

import config
import inventory_builder

PLAYBOOK_TEST = os.path.join(config.PLAYBOOKS_DIR, "test_connection.yml")
PLAYBOOK_SANITIZE = os.path.join(config.PLAYBOOKS_DIR, "sanitize_users.yml")
PLAYBOOK_HISTORY = os.path.join(config.PLAYBOOKS_DIR, "fetch_bash_history.yml")
PLAYBOOK_DETECT_SUDO = os.path.join(config.PLAYBOOKS_DIR, "detect_sudo.yml")

LEGACY_SCRIPT_COPY = os.path.join(config.ANSIBLE_DIR, "files", "nexus_sanitize_users.sh")

SECRET_LINE_PATTERN = re.compile(r"(pass(wo?rd)?|senha|secret|token|chave)", re.IGNORECASE)


def sync_legacy_script():
    """Garante que a copia usada pelo Ansible reflete o script raiz atual."""
    shutil.copyfile(config.LEGACY_SANITIZER_SCRIPT, LEGACY_SCRIPT_COPY)
    os.chmod(LEGACY_SCRIPT_COPY, 0o755)


def _run(playbook_path, extravars):
    inventory_builder.rebuild_inventory()
    run_id = str(uuid.uuid4())
    private_data_dir = os.path.join(config.ARTIFACTS_DIR, run_id)
    os.makedirs(private_data_dir, exist_ok=True)

    runner = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook=playbook_path,
        inventory=config.INVENTORY_PATH,
        extravars=extravars,
        # Caminhos absolutos via env var, para nao depender de como o cwd e
        # resolvido internamente pelo ansible-runner ao interpretar os
        # caminhos relativos de ansible.cfg.
        envvars={
            "ANSIBLE_CONFIG": config.ANSIBLE_CFG_PATH,
            "ANSIBLE_VAULT_PASSWORD_FILE": config.VAULT_PASS_FILE,
        },
        quiet=True,
    )

    stdout_text = ""
    try:
        runner.stdout.seek(0)
        stdout_text = runner.stdout.read()
    except Exception:
        pass

    return {
        "run_id": run_id,
        "success": runner.status == "successful",
        "status": runner.status,
        "rc": runner.rc,
        "stdout": stdout_text,
        "private_data_dir": private_data_dir,
        "runner": runner,
    }


def test_connection(server_name):
    return _run(PLAYBOOK_TEST, {"target_host": server_name})


def detect_sudo_nopasswd(server_name):
    """Testa via 'sudo -n true' se esse servidor exige senha de sudo.

    Retorna "nopasswd" (sudo nao pede senha), "needs_password" (pede senha
    de verdade) ou "unknown" (nao foi possivel testar - ex.: chave SSH ainda
    nao autorizada, host inacessivel). Nunca arrisca ficar esperando um
    prompt de senha: "sudo -n" falha na hora em vez de perguntar.
    """
    result = _run(PLAYBOOK_DETECT_SUDO, {"target_host": server_name})
    if not result["success"]:
        return "unknown"

    for event in result["runner"].events:
        event_data = event.get("event_data", {})
        if event_data.get("task") == "Testar sudo nao-interativo (sudo -n)":
            res = event_data.get("res", {})
            rc = res.get("rc")
            if rc is None:
                return "unknown"
            return "nopasswd" if rc == 0 else "needs_password"

    return "unknown"


def _write_temp_csv(rows):
    fd, path = tempfile.mkstemp(prefix="nexus_action_", suffix=".csv", dir=config.ARTIFACTS_DIR)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "action", "home", "reason", "ticket", "groups", "shell"])
        for row in rows:
            writer.writerow([
                row.get("username", ""),
                row.get("action", ""),
                row.get("home", "yes"),
                row.get("reason", ""),
                row.get("ticket", ""),
                row.get("groups", ""),
                row.get("shell", ""),
            ])
    return path


def _write_temp_password_hashes(password_hashes):
    if not password_hashes:
        return None
    fd, path = tempfile.mkstemp(prefix="nexus_hashes_", suffix=".txt", dir=config.ARTIFACTS_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for username, hash_value in password_hashes.items():
            f.write(f"{username}:{hash_value}\n")
    os.chmod(path, 0o600)
    return path


def run_sanitize(target_host, mode, rows, password_hashes=None):
    """Executa o nexus_sanitize_users.sh reaproveitado via Ansible.

    target_host: nome do servidor (ou padrao Ansible, ex.: "enabled" para todos)
    mode: "dry-run" ou "apply"
    rows: lista de dicts com username/action/home/reason/ticket/groups/shell
    password_hashes: dict opcional {username: hash_sha512_crypt}
    """
    sync_legacy_script()
    csv_path = _write_temp_csv(rows)
    hashes_path = _write_temp_password_hashes(password_hashes)

    extravars = {
        "target_host": target_host,
        "mode": mode,
        "sanitizer_script_local_path": LEGACY_SCRIPT_COPY,
        "csv_local_path": csv_path,
        "artifacts_local_dir": config.ARTIFACTS_DIR,
    }
    if hashes_path:
        extravars["password_hash_local_path"] = hashes_path

    try:
        return _run(PLAYBOOK_SANITIZE, extravars)
    finally:
        for path in (csv_path, hashes_path):
            if path and os.path.exists(path):
                os.remove(path)


def _redact_history_line(line):
    if SECRET_LINE_PATTERN.search(line):
        return "[linha redigida - parece conter credencial]"
    return line


def fetch_bash_history(target_host, username, max_lines=40):
    result = _run(PLAYBOOK_HISTORY, {"target_host": target_host, "target_username": username})

    if not result["success"]:
        return {"status": "error", "excerpt": ""}

    content_b64 = None
    history_exists = True
    for event in result["runner"].events:
        event_data = event.get("event_data", {})
        task = event_data.get("task", "")
        res = event_data.get("res", {})
        if task == "Verificar se o arquivo de historico existe":
            history_exists = bool(res.get("stat", {}).get("exists"))
        if task == "Ler o arquivo de historico (quando existir)" and "content" in res:
            content_b64 = res["content"]

    if not history_exists:
        return {"status": "no_access", "excerpt": ""}

    if not content_b64:
        return {"status": "empty", "excerpt": ""}

    try:
        raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        return {"status": "error", "excerpt": ""}

    lines = [l for l in raw.splitlines() if l.strip()]
    if not lines:
        return {"status": "empty", "excerpt": ""}

    tail = lines[-max_lines:]
    redacted = [_redact_history_line(l) for l in tail]
    return {"status": "ok", "excerpt": "\n".join(redacted)}
