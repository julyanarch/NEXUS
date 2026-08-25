import csv
import sqlite3
from datetime import datetime, timezone

import config


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    _seed_servers_from_legacy_conf()


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

def list_servers(conn=None):
    own = conn is None
    conn = conn or get_db()
    rows = conn.execute("SELECT * FROM servers ORDER BY name").fetchall()
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


def create_server(name, ssh_host, ssh_user, ssh_port, enabled, conn=None):
    own = conn is None
    conn = conn or get_db()
    ts = now_iso()
    conn.execute(
        """INSERT INTO servers (name, ssh_host, ssh_user, ssh_port, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, ssh_host, ssh_user, ssh_port, 1 if enabled else 0, ts, ts),
    )
    conn.commit()
    if own:
        conn.close()


def update_server(server_id, name, ssh_host, ssh_user, ssh_port, enabled):
    conn = get_db()
    conn.execute(
        """UPDATE servers SET name=?, ssh_host=?, ssh_user=?, ssh_port=?, enabled=?, updated_at=?
           WHERE id=?""",
        (name, ssh_host, ssh_user, ssh_port, 1 if enabled else 0, now_iso(), server_id),
    )
    conn.commit()
    conn.close()


def set_server_test_result(server_id, status):
    conn = get_db()
    conn.execute(
        "UPDATE servers SET last_test_status=?, last_test_at=?, updated_at=? WHERE id=?",
        (status, now_iso(), now_iso(), server_id),
    )
    conn.commit()
    conn.close()


def toggle_server(server_id):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM servers WHERE id=?", (server_id,)).fetchone()
    if row is None:
        conn.close()
        return
    new_value = 0 if row["enabled"] else 1
    conn.execute(
        "UPDATE servers SET enabled=?, updated_at=? WHERE id=?",
        (new_value, now_iso(), server_id),
    )
    conn.commit()
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
    conn = get_db()
    conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    conn.commit()
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
    existing = conn.execute(
        "SELECT * FROM managed_users WHERE username=? AND server_id=?",
        (username, server_id),
    ).fetchone()
    ts = now_iso()

    if action in ("create", "add"):
        if existing:
            status = "active"
        else:
            conn.execute(
                """INSERT INTO managed_users
                   (username, server_id, status, groups_csv, shell, home_policy, ticket, reason,
                    created_ticket, created_reason, created_at, created_by, updated_at)
                   VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (username, server_id, groups_csv, shell, home_policy, ticket, reason, ticket, reason,
                 ts, performed_by, ts),
            )
            conn.commit()
            conn.close()
            return
        conn.execute(
            "UPDATE managed_users SET status='active', groups_csv=?, shell=?, ticket=?, reason=?, updated_at=? WHERE id=?",
            (groups_csv, shell, ticket, reason, ts, existing["id"]),
        )
    elif action == "lock":
        conn.execute(
            "UPDATE managed_users SET status='locked', locked_at=?, ticket=?, reason=?, updated_at=? WHERE username=? AND server_id=?",
            (ts, ticket, reason, ts, username, server_id),
        )
    elif action in ("remove", "delete", "purge"):
        conn.execute(
            """UPDATE managed_users SET status='removed', removed_at=?, removed_by=?, removal_type='manual',
               updated_at=? WHERE username=? AND server_id=?""",
            (ts, performed_by, ts, username, server_id),
        )
    conn.commit()
    conn.close()


def mark_removed_automatically(user_id):
    conn = get_db()
    ts = now_iso()
    conn.execute(
        """UPDATE managed_users SET status='removed', removed_at=?, removed_by='system/scheduler',
           removal_type='automatic', updated_at=? WHERE id=?""",
        (ts, ts, user_id),
    )
    conn.commit()
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


# ---------------------------------------------------------------- documents --

def add_document(managed_user_id, doc_type, reference, description, uploaded_by):
    conn = get_db()
    conn.execute(
        """INSERT INTO documents (managed_user_id, doc_type, reference, description, uploaded_by, uploaded_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (managed_user_id, doc_type, reference, description, uploaded_by, now_iso()),
    )
    conn.commit()
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
    conn.execute(
        """INSERT INTO collected_facts (managed_user_id, server_id, collected_at, collection_status, history_excerpt)
           VALUES (?, ?, ?, ?, ?)""",
        (managed_user_id, server_id, now_iso(), collection_status, history_excerpt),
    )
    conn.commit()
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
    conn.execute(
        """UPDATE scheduler_runs SET finished_at=?, users_checked=?, users_removed=?, status=?
           WHERE run_type=? AND run_date=?""",
        (now_iso(), users_checked, users_removed, status, run_type, run_date),
    )
    conn.commit()
    conn.close()


def list_scheduler_runs(limit=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM scheduler_runs ORDER BY run_date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows
