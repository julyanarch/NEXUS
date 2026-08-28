import base64
import csv
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

import ansible_runner

import config
import inventory_builder

PLAYBOOK_TEST = os.path.join(config.PLAYBOOKS_DIR, "test_connection.yml")
PLAYBOOK_SANITIZE = os.path.join(config.PLAYBOOKS_DIR, "sanitize_users.yml")
PLAYBOOK_HISTORY = os.path.join(config.PLAYBOOKS_DIR, "fetch_bash_history.yml")
PLAYBOOK_DETECT_SUDO = os.path.join(config.PLAYBOOKS_DIR, "detect_sudo.yml")
PLAYBOOK_CHECK_FILE = os.path.join(config.PLAYBOOKS_DIR, "check_home_file.yml")
PLAYBOOK_DISCOVER_USERS = os.path.join(config.PLAYBOOKS_DIR, "discover_existing_users.yml")

LEGACY_SCRIPT_COPY = os.path.join(config.ANSIBLE_DIR, "files", "nexus_sanitize_users.sh")

SECRET_LINE_PATTERN = re.compile(r"(pass(wo?rd)?|senha|secret|token|chave)", re.IGNORECASE)
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _clean_detail(text):
    """Remove codigos de cor ANSI e espacos sobrando, pra nunca mostrar
    saida bruta cheia de */codigos de escape numa mensagem de erro."""
    if not text:
        return ""
    return ANSI_ESCAPE_PATTERN.sub("", str(text)).strip()


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


GENERIC_DETECTION_FAILURE = "Não foi possível conectar ou executar o teste nesse servidor."


def detect_sudo_nopasswd(server_name):
    """Testa via 'sudo -n true' se esse servidor exige senha de sudo.

    Retorna um dict {"status": ..., "detail": ...}. status e "nopasswd"
    (sudo nao pede senha), "needs_password" (pede senha de verdade) ou
    "unknown" (nao foi possivel concluir o teste). O "detail" e sempre uma
    frase curta e limpa (nunca a saida bruta do Ansible, cheia de */codigos
    de escape) - ou a frase generica acima, se nada de util for encontrado.
    Nunca arrisca ficar esperando um prompt de senha: "sudo -n" falha na
    hora em vez de perguntar.
    """
    result = _run(PLAYBOOK_DETECT_SUDO, {"target_host": server_name})

    unreachable_msg = ""
    for event in result["runner"].events:
        event_data = event.get("event_data", {})
        res = event_data.get("res", {})

        if event.get("event") == "runner_on_unreachable" and not unreachable_msg:
            unreachable_msg = _clean_detail(res.get("msg"))

        if event_data.get("task") == "Testar sudo nao-interativo (sudo -n)":
            rc = res.get("rc")
            if rc is not None:
                status = "nopasswd" if rc == 0 else "needs_password"
                return {"status": status, "detail": _clean_detail(res.get("stderr"))}
            task_msg = _clean_detail(res.get("msg") or res.get("stderr"))
            if task_msg:
                return {"status": "unknown", "detail": task_msg}

    return {"status": "unknown", "detail": unreachable_msg or GENERIC_DETECTION_FAILURE}


def summarize_result(result):
    """Mensagem curta pra coluna Detalhe de Execucoes/Painel - nunca o
    stdout bruto do Ansible (que despeja todas as TASKs e o PLAY RECAP
    cheios de codigos de escape ANSI, ilegivel na tela)."""
    if result["success"]:
        return "Executado com sucesso."

    pieces = []
    for event in result["runner"].events:
        if event.get("event") not in ("runner_on_failed", "runner_on_unreachable"):
            continue
        event_data = event.get("event_data", {})
        host = event_data.get("host") or "?"
        task = event_data.get("task") or ""
        res = event_data.get("res", {})
        detail = _clean_detail(res.get("msg") or res.get("stderr") or res.get("module_stderr"))
        label = "servidor inalcancavel" if event.get("event") == "runner_on_unreachable" else "falhou"
        piece = f'"{task}" {label} em {host}' if task else f"{label} em {host}"
        if detail:
            piece += f": {detail}"
        pieces.append(piece)

    if pieces:
        return " | ".join(pieces)

    fallback = _clean_detail(result["stdout"])[-500:]
    return fallback or f"Execucao terminou com status '{result['status']}'."


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


def _read_sanitize_report(target_host):
    """Le o relatorio JSON que o sanitizer gerou nessa execucao (results[0],
    ja que o dashboard sempre manda 1 usuario por vez) - e o que diz se a
    acao realmente aconteceu (status "ok"), foi ignorada porque o usuario
    nao existe/ja existe ("skipped"), foi barrada por ser usuario protegido
    ("blocked") ou falhou de verdade ("failed"). O script sempre termina com
    exit code 0 mesmo quando ignora ou barra uma linha (e um processador de
    CSV em lote, feito pra nao abortar o resto por causa de uma linha) -
    entao o rc/status do Ansible sozinho nao basta pra saber se a acao
    pedida aconteceu de fato."""
    report_path = os.path.join(config.ARTIFACTS_DIR, f"{target_host}_sanitize.json")
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    results = data.get("results") or []
    return results[0] if results else None


def run_sanitize(target_host, mode, rows, password_hashes=None):
    """Executa o nexus_sanitize_users.sh reaproveitado via Ansible.

    target_host: nome do servidor (ou padrao Ansible, ex.: "enabled" para todos)
    mode: "dry-run" ou "apply"
    rows: lista de dicts com username/action/home/reason/ticket/groups/shell
    password_hashes: dict opcional {username: hash_sha512_crypt}

    O dict retornado inclui "row_status"/"row_message" com o resultado real
    da linha processada (ok/skipped/blocked/failed - ver _read_sanitize_report),
    alem de "success" (se a execucao via Ansible em si rodou sem erro).
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
        "host_vars_root": config.HOST_VARS_DIR,
    }
    if hashes_path:
        extravars["password_hash_local_path"] = hashes_path

    try:
        result = _run(PLAYBOOK_SANITIZE, extravars)
    finally:
        for path in (csv_path, hashes_path):
            if path and os.path.exists(path):
                os.remove(path)

    row = _read_sanitize_report(target_host) if result["success"] else None
    result["row_status"] = row.get("status") if row else None
    result["row_message"] = row.get("message") if row else None
    return result


def _redact_history_line(line):
    if SECRET_LINE_PATTERN.search(line):
        return "[linha redigida - parece conter credencial]"
    return line


def fetch_bash_history(target_host, username, max_lines=40):
    result = _run(PLAYBOOK_HISTORY, {
        "target_host": target_host,
        "target_username": username,
        "host_vars_root": config.HOST_VARS_DIR,
    })

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


def check_home_file(target_host, username, full_path):
    """Confere se um arquivo/pasta especifico existe no servidor - so confirma
    presenca/ausencia (com tamanho e data de modificacao quando existe), nao
    lista nem baixa nada. Sem restricao de caminho (proposital - so leitura,
    quem usa o NEXUS ja tem acesso root nesses servidores via Ansible mesmo).
    """
    result = _run(PLAYBOOK_CHECK_FILE, {
        "target_host": target_host,
        "target_username": username,
        "full_path": full_path,
        "host_vars_root": config.HOST_VARS_DIR,
    })

    if not result["success"]:
        return {"status": "error", "detail": summarize_result(result)}

    # O Ansible emite mais de um evento pra essa task (ex.: "task start" antes
    # de rodar, com res={}, e so depois o evento com o resultado de verdade).
    # Pegar o primeiro evento que bater o nome da task (sem checar se "stat"
    # realmente veio preenchido) pega o evento errado - sempre "nao existe",
    # mesmo quando existe. Por isso: guarda so quando "stat" aparece de
    # verdade no resultado, e so decide depois de varrer todos os eventos.
    stat = None
    for event in result["runner"].events:
        event_data = event.get("event_data", {})
        if event_data.get("task") == "Verificar o arquivo":
            res = event_data.get("res", {})
            if "stat" in res:
                stat = res["stat"]

    if stat is None:
        return {"status": "error", "detail": "Nao foi possivel concluir a verificacao."}

    if not stat.get("exists"):
        return {"status": "not_found"}

    mtime = stat.get("mtime")
    mtime_text = None
    if mtime:
        mtime_text = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "status": "found",
        "is_dir": bool(stat.get("isdir")),
        "size": stat.get("size"),
        "mtime_text": mtime_text,
    }


def discover_existing_users(target_host, min_uid=None):
    """Lista usuarios "de gente" (uid >= min_uid, shell interativo - exclui
    contas de sistema/servico) ja existentes no servidor, com status ativo/
    bloqueado (via `passwd -S`) - pra "Importar usuarios existentes". So
    leitura, nao altera nada no servidor."""
    result = _run(PLAYBOOK_DISCOVER_USERS, {
        "target_host": target_host,
        "min_uid": min_uid if min_uid is not None else config.DISCOVER_MIN_UID,
        "host_vars_root": config.HOST_VARS_DIR,
    })

    if not result["success"]:
        return {"status": "error", "detail": summarize_result(result), "users": []}

    stdout = None
    for event in result["runner"].events:
        event_data = event.get("event_data", {})
        if event_data.get("task") == "Listar usuarios reais do servidor":
            res = event_data.get("res", {})
            if "stdout" in res:
                stdout = res["stdout"]

    if stdout is None:
        return {"status": "error", "detail": "Nao foi possivel concluir a descoberta.", "users": []}

    users = []
    for line in stdout.splitlines():
        parts = line.strip().split(",")
        if len(parts) != 4:
            continue
        username, uid, shell, pw_status = parts
        users.append({
            "username": username,
            "uid": uid,
            "shell": shell,
            "locked": pw_status.strip() == "L",
        })
    return {"status": "ok", "users": users, "detail": None}
