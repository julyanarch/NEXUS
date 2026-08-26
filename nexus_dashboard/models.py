import csv
import sqlite3
from datetime import date, datetime, timedelta, timezone

import config


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# managed_users.created_by e NOT NULL - usado quando a primeira acao que o
# NEXUS registra pra um usuario e "lock"/"remove"/"purge" (nao "create"), ou
# seja, o usuario ja existia no servidor antes de ser gerido por aqui. Ver
# upsert_user_after_action().
NOT_CREATED_VIA_NEXUS = "desconhecido (usuário já existia no servidor)"


def get_db():
    # timeout/busy_timeout: o agendador (thread separada, ver scheduler.py)
    # e as requisicoes web podem gravar quase ao mesmo tempo - sem isso, o
    # SQLite falha na hora com "database is locked" em vez de aguardar a
    # outra escrita (rapida) liberar.
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    conn = get_db()
    with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    _migrate_schema()
    _seed_servers_from_legacy_conf()


def _migrate_schema():
    """Adiciona colunas novas em bancos que ja existiam antes delas serem
    criadas no schema.sql. CREATE TABLE IF NOT EXISTS nao adiciona coluna em
    tabela que ja existe, entao isso cobre esse caso sem apagar nada."""
    conn = get_db()
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(servers)").fetchall()}
    if "sudo_nopasswd" not in existing_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN sudo_nopasswd INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    if "decommissioned_at" not in existing_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN decommissioned_at TEXT")
        conn.execute("ALTER TABLE servers ADD COLUMN decommissioned_by TEXT")
        conn.execute("ALTER TABLE servers ADD COLUMN decommission_reason TEXT")
        conn.commit()
    _archive_decommissioned_names(conn)
    conn.close()


def _archive_decommissioned_names(conn):
    """Servidor decomissionado antes do arquivamento de nome existir (ver
    decommission_server) ainda ocupa o nome original na coluna UNIQUE,
    impedindo recadastrar um servidor com o mesmo nome. Arruma isso uma
    unica vez, retroativamente, toda vez que a app sobe."""
    rows = conn.execute(
        "SELECT id, name, decommissioned_at FROM servers WHERE decommissioned_at IS NOT NULL"
    ).fetchall()
    changed = False
    for row in rows:
        if "[excluído " in row["name"]:
            continue
        archived_name = f"{row['name']} [excluído {row['decommissioned_at']}]"
        conn.execute("UPDATE servers SET name=? WHERE id=?", (archived_name, row["id"]))
        changed = True
    if changed:
        conn.commit()


def _seed_servers_from_legacy_conf():
    """Importa servidores.conf uma unica vez, se a tabela servers estiver vazia."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) AS c FROM servers").fetchone()["c"]
    if count > 0:
        conn.close()
        return

    try:
        with open(config.LEGACY_SERVERS_CONF, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or not row[0].strip() or row[0].strip().startswith("#"):
                    continue
                name = row[0].strip()
                ssh_user = row[1].strip() if len(row) > 1 else ""
                ssh_host = row[2].strip() if len(row) > 2 else ""
                ssh_port = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 22
                enabled_raw = row[4].strip().lower() if len(row) > 4 else "yes"
                enabled = 1 if enabled_raw in ("yes", "true", "1") else 0
                if not name or not ssh_user or not ssh_host:
                    continue
                create_server(name, ssh_host, ssh_user, ssh_port, enabled, conn=conn)
    except FileNotFoundError:
        pass
    finally:
        conn.close()


# ---------------------------------------------------------------- servers --

def list_servers(conn=None, include_decommissioned=False):
    """Por padrao, so traz servidores ativos - um servidor excluido/decomissionado
    (que tinha historico e por isso nao pode ser apagado de verdade, ver
    decommission_server) some da lista e de qualquer selecao de destino, mas
    a linha continua no banco pra nao quebrar a auditoria ja registrada."""
    own = conn is None
    conn = conn or get_db()
    if include_decommissioned:
        rows = conn.execute("SELECT * FROM servers ORDER BY name").fetchall()
    else:
        rows = conn.execute("SELECT * FROM servers WHERE decommissioned_at IS NULL ORDER BY name").fetchall()
    if own:
        conn.close()
    return rows


def get_server(server_id, conn=None):
    own = conn is None
    conn = conn or get_db()
    row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if own:
        conn.close()
    return row


def create_server(name, ssh_host, ssh_user, ssh_port, enabled, sudo_nopasswd=False, conn=None):
    own = conn is None
    conn = conn or get_db()
    try:
        ts = now_iso()
        cursor = conn.execute(
            """INSERT INTO servers (name, ssh_host, ssh_user, ssh_port, enabled, sudo_nopasswd, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, ssh_host, ssh_user, ssh_port, 1 if enabled else 0, 1 if sudo_nopasswd else 0, ts, ts),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if own:
            conn.close()


def set_server_sudo_nopasswd(server_id, sudo_nopasswd):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE servers SET sudo_nopasswd=?, updated_at=? WHERE id=?",
            (1 if sudo_nopasswd else 0, now_iso(), server_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_server(server_id, name, ssh_host, ssh_user, ssh_port, enabled, sudo_nopasswd=False):
    conn = get_db()
    try:
        conn.execute(
            """UPDATE servers SET name=?, ssh_host=?, ssh_user=?, ssh_port=?, enabled=?, sudo_nopasswd=?,
               updated_at=? WHERE id=?""",
            (name, ssh_host, ssh_user, ssh_port, 1 if enabled else 0, 1 if sudo_nopasswd else 0,
             now_iso(), server_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_server_test_result(server_id, status):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE servers SET last_test_status=?, last_test_at=?, updated_at=? WHERE id=?",
            (status, now_iso(), now_iso(), server_id),
        )
        conn.commit()
    finally:
        conn.close()


def toggle_server(server_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT enabled FROM servers WHERE id=?", (server_id,)).fetchone()
        if row is None:
            return
        new_value = 0 if row["enabled"] else 1
        conn.execute(
            "UPDATE servers SET enabled=?, updated_at=? WHERE id=?",
            (new_value, now_iso(), server_id),
        )
        conn.commit()
    finally:
        conn.close()


def find_servers_by_host(ssh_host, exclude_id=None):
    """Outros servidores cadastrados com o mesmo host/IP (mesma maquina fisica,
    possivelmente com outro usuario SSH) - usado so para avisar, nao bloqueia."""
    conn = get_db()
    if exclude_id is not None:
        rows = conn.execute(
            "SELECT * FROM servers WHERE ssh_host = ? AND id != ?", (ssh_host, exclude_id)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM servers WHERE ssh_host = ?", (ssh_host,)).fetchall()
    conn.close()
    return rows


def server_has_history(server_id):
    """True se ja existe algum usuario gerido ou linha de auditoria presa a esse
    servidor - nesse caso, excluir de verdade apagaria rastro de auditoria."""
    conn = get_db()
    users_count = conn.execute(
        "SELECT COUNT(*) AS c FROM managed_users WHERE server_id = ?", (server_id,)
    ).fetchone()["c"]
    actions_count = conn.execute(
        "SELECT COUNT(*) AS c FROM action_log WHERE server_id = ?", (server_id,)
    ).fetchone()["c"]
    conn.close()
    return (users_count + actions_count) > 0


def delete_server(server_id):
    """Apaga o servidor de verdade - so seguro quando server_has_history() e
    False (senao a FK de managed_users/action_log pra esse servidor quebra)."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        conn.commit()
    finally:
        conn.close()


def decommission_server(server_id, reason, performed_by):
    """'Exclusao' de um servidor que ja tem historico: nao apaga a linha (isso
    quebraria a FK de managed_users/action_log e derrubaria a auditoria ja
    registrada) - marca como decomissionado, com motivo e quem fez, e some da
    lista/telas de selecao (list_servers), mas fica disponivel pra consulta
    futura direto no banco ou via a linha de auditoria em log_action().

    O nome tambem e arquivado (sufixo com a data) - a coluna `name` e UNIQUE,
    entao sem isso o nome original ficaria preso para sempre no servidor
    decomissionado e um novo cadastro com o mesmo nome falharia."""
    conn = get_db()
    try:
        ts = now_iso()
        server = conn.execute("SELECT name FROM servers WHERE id=?", (server_id,)).fetchone()
        if server is None:
            return
        archived_name = f"{server['name']} [excluído {ts}]"
        conn.execute(
            """UPDATE servers SET name=?, decommissioned_at=?, decommissioned_by=?, decommission_reason=?,
               enabled=0, updated_at=? WHERE id=?""",
            (archived_name, ts, performed_by, reason, ts, server_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------- managed_users --

USER_LIST_QUERY = """
    SELECT mu.*, s.name AS server_name,
           CAST((julianday('now') - julianday(mu.locked_at)) AS INTEGER) AS days_locked
    FROM managed_users mu
    JOIN servers s ON s.id = mu.server_id
"""


def list_users(status=None, search=None):
    conn = get_db()
    query = USER_LIST_QUERY
    clauses = []
    params = []
    if status:
        clauses.append("mu.status = ?")
        params.append(status)
    if search:
        clauses.append("(mu.username LIKE ? OR mu.ticket LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY mu.updated_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_user(user_id):
    conn = get_db()
    row = conn.execute(USER_LIST_QUERY + " WHERE mu.id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def find_user_by_server(username, server_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM managed_users WHERE username=? AND server_id=?",
        (username, server_id),
    ).fetchone()
    conn.close()
    return row


def upsert_user_after_action(username, server_id, action, groups_csv, shell, home_policy,
                               ticket, reason, performed_by):
    """Cria ou atualiza o registro local do usuario apos uma acao aplicada com sucesso."""
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM managed_users WHERE username=? AND server_id=?",
            (username, server_id),
        ).fetchone()
        ts = now_iso()

        if action in ("create", "add"):
            if existing:
                conn.execute(
                    "UPDATE managed_users SET status='active', groups_csv=?, shell=?, ticket=?, reason=?, updated_at=? WHERE id=?",
                    (groups_csv, shell, ticket, reason, ts, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO managed_users
                       (username, server_id, status, groups_csv, shell, home_policy, ticket, reason,
                        created_ticket, created_reason, created_at, created_by, updated_at)
                       VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (username, server_id, groups_csv, shell, home_policy, ticket, reason, ticket, reason,
                     ts, performed_by, ts),
                )
        elif action == "lock":
            if existing:
                conn.execute(
                    "UPDATE managed_users SET status='locked', locked_at=?, ticket=?, reason=?, updated_at=? WHERE id=?",
                    (ts, ticket, reason, ts, existing["id"]),
                )
            else:
                # Usuario que o NEXUS nunca tinha "criado" (ja existia no
                # servidor antes de ser gerido por aqui) - sem isso a acao
                # aplicava certinho no servidor mas nao deixava rastro na
                # tabela local, entao nunca aparecia em Usuarios.
                conn.execute(
                    """INSERT INTO managed_users
                       (username, server_id, status, groups_csv, shell, home_policy, ticket, reason,
                        created_at, created_by, locked_at, updated_at)
                       VALUES (?, ?, 'locked', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (username, server_id, groups_csv, shell, home_policy, ticket, reason,
                     ts, NOT_CREATED_VIA_NEXUS, ts, ts),
                )
        elif action in ("remove", "delete", "purge"):
            if existing:
                conn.execute(
                    """UPDATE managed_users SET status='removed', removed_at=?, removed_by=?, removal_type='manual',
                       updated_at=? WHERE id=?""",
                    (ts, performed_by, ts, existing["id"]),
                )
            else:
                # Mesmo caso do "lock" acima - ex.: purgar de primeira um
                # usuario que ja existia no servidor, nunca gerido por aqui.
                conn.execute(
                    """INSERT INTO managed_users
                       (username, server_id, status, groups_csv, shell, home_policy, ticket, reason,
                        created_at, created_by, removed_at, removed_by, removal_type, updated_at)
                       VALUES (?, ?, 'removed', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)""",
                    (username, server_id, groups_csv, shell, home_policy, ticket, reason,
                     ts, NOT_CREATED_VIA_NEXUS, ts, performed_by, ts),
                )
        conn.commit()
    finally:
        conn.close()


def mark_removed_automatically(user_id):
    conn = get_db()
    try:
        ts = now_iso()
        conn.execute(
            """UPDATE managed_users SET status='removed', removed_at=?, removed_by='system/scheduler',
               removal_type='automatic', updated_at=? WHERE id=?""",
            (ts, ts, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_locked_users():
    conn = get_db()
    rows = conn.execute(USER_LIST_QUERY + " WHERE mu.status = 'locked'").fetchall()
    conn.close()
    return rows


def summary_counts():
    conn = get_db()
    rows = conn.execute("SELECT status, COUNT(*) AS c FROM managed_users GROUP BY status").fetchall()
    counts = {"active": 0, "locked": 0, "removed": 0}
    for row in rows:
        counts[row["status"]] = row["c"]

    expiring = conn.execute(
        """SELECT COUNT(*) AS c FROM managed_users
           WHERE status='locked'
             AND CAST((julianday('now') - julianday(locked_at)) AS INTEGER) >= ?""",
        (config.LOCK_WARNING_DAYS,),
    ).fetchone()["c"]
    conn.close()
    counts["expiring_soon"] = expiring
    return counts


# ---------------------------------------------------------------- action_log --

def log_action(managed_user_id, server_id, username, action, mode, status, message,
               ticket, groups_snapshot, shell_snapshot, performed_by, triggered_by,
               ansible_run_id=None, raw_stdout_ref=None):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO action_log
               (managed_user_id, server_id, username, action, mode, status, message, ticket,
                groups_snapshot, shell_snapshot, performed_by, triggered_by, ansible_run_id,
                raw_stdout_ref, performed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (managed_user_id, server_id, username, action, mode, status, message, ticket,
             groups_snapshot, shell_snapshot, performed_by, triggered_by, ansible_run_id,
             raw_stdout_ref, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def list_action_log_for_user(managed_user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM action_log WHERE managed_user_id = ? ORDER BY performed_at DESC",
        (managed_user_id,),
    ).fetchall()
    conn.close()
    return rows


def list_recent_runs(limit=100):
    conn = get_db()
    rows = conn.execute(
        """SELECT al.*, s.name AS server_name
           FROM action_log al
           LEFT JOIN servers s ON s.id = al.server_id
           ORDER BY al.performed_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def daily_execution_counts(days=14):
    """Execucoes (ok vs falha) por dia, para o grafico de linha do tempo do
    Painel. Sempre retorna exatamente `days` dias (do mais antigo ao mais
    recente), preenchendo com zero os dias sem nenhuma execucao."""
    conn = get_db()
    rows = conn.execute(
        """SELECT substr(performed_at, 1, 10) AS day,
                  SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
                  SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS failed_count
           FROM action_log
           GROUP BY day"""
    ).fetchall()
    conn.close()

    by_day = {r["day"]: (r["ok_count"], r["failed_count"]) for r in rows}
    today = date.today()
    result = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        ok_count, failed_count = by_day.get(key, (0, 0))
        result.append({
            "day": key,
            "label": day.strftime("%d/%m"),
            "ok": ok_count,
            "failed": failed_count,
        })
    return result


def executions_per_server(days=30):
    """Total de execucoes por servidor nos ultimos `days` dias, para o
    grafico de magnitude do Painel. Inclui servidores sem nenhuma execucao
    no periodo (aparecem com contagem zero)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT s.name AS server_name, COUNT(al.id) AS total
           FROM servers s
           LEFT JOIN action_log al
             ON al.server_id = s.id AND al.performed_at >= datetime('now', ?)
           GROUP BY s.id
           ORDER BY total DESC, s.name""",
        (f"-{days} days",),
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------- documents --

def add_document(managed_user_id, doc_type, reference, description, uploaded_by):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO documents (managed_user_id, doc_type, reference, description, uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (managed_user_id, doc_type, reference, description, uploaded_by, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def list_documents_for_user(managed_user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM documents WHERE managed_user_id = ? ORDER BY uploaded_at DESC",
        (managed_user_id,),
    ).fetchall()
    conn.close()
    return rows


# --------------------------------------------------------- collected_facts --

def save_collected_facts(managed_user_id, server_id, collection_status, history_excerpt):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO collected_facts (managed_user_id, server_id, collected_at, collection_status, history_excerpt)
               VALUES (?, ?, ?, ?, ?)""",
            (managed_user_id, server_id, now_iso(), collection_status, history_excerpt),
        )
        conn.commit()
    finally:
        conn.close()


def latest_collected_facts(managed_user_id):
    conn = get_db()
    row = conn.execute(
        """SELECT * FROM collected_facts WHERE managed_user_id = ?
           ORDER BY collected_at DESC LIMIT 1""",
        (managed_user_id,),
    ).fetchone()
    conn.close()
    return row


def list_collected_facts_for_user(managed_user_id):
    """Todas as coletas de historico ja feitas pra esse usuario (uma por
    clique em "Coletar historico de comandos"), da mais recente pra mais
    antiga - cada coleta e uma "foto" independente, nao sobrescreve a
    anterior. Usado pra deixar escolher qual data baixar."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM collected_facts WHERE managed_user_id = ? ORDER BY collected_at DESC",
        (managed_user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_collected_facts(fact_id, managed_user_id):
    """Uma coleta especifica, restrita ao usuario informado (evita baixar a
    coleta de outro usuario so trocando o numero na URL)."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM collected_facts WHERE id = ? AND managed_user_id = ?",
        (fact_id, managed_user_id),
    ).fetchone()
    conn.close()
    return row


# --------------------------------------------------------- scheduler_runs --

def try_start_scheduler_run(run_type, run_date):
    """Retorna True se conseguiu registrar o inicio do run (nao havia outro no mesmo dia)."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO scheduler_runs (run_type, run_date, started_at, status) VALUES (?, ?, ?, 'running')",
            (run_type, run_date, now_iso()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def finish_scheduler_run(run_type, run_date, users_checked, users_removed, status):
    conn = get_db()
    try:
        conn.execute(
            """UPDATE scheduler_runs SET finished_at=?, users_checked=?, users_removed=?, status=?
               WHERE run_type=? AND run_date=?""",
            (now_iso(), users_checked, users_removed, status, run_type, run_date),
        )
        conn.commit()
    finally:
        conn.close()


def list_scheduler_runs(limit=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM scheduler_runs ORDER BY run_date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows
