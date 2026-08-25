-- NEXUS Dashboard - schema SQLite
-- Fonte unica de verdade para servidores, usuarios gerenciados, auditoria,
-- documentos vinculados e fatos coletados (historico de comandos).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    ssh_host TEXT NOT NULL,
    ssh_user TEXT NOT NULL,
    ssh_port INTEGER NOT NULL DEFAULT 22,
    enabled INTEGER NOT NULL DEFAULT 1,
    sudo_nopasswd INTEGER NOT NULL DEFAULT 0,
    last_test_status TEXT,
    last_test_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS managed_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id),
    status TEXT NOT NULL CHECK (status IN ('active', 'locked', 'removed')),
    groups_csv TEXT DEFAULT '',
    shell TEXT DEFAULT '/bin/bash',
    home_policy TEXT DEFAULT 'yes',
    ticket TEXT,
    reason TEXT,
    created_ticket TEXT,
    created_reason TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    locked_at TEXT,
    removed_at TEXT,
    removed_by TEXT,
    removal_type TEXT CHECK (removal_type IN ('manual', 'automatic')),
    updated_at TEXT NOT NULL,
    UNIQUE (username, server_id)
);

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_user_id INTEGER REFERENCES managed_users(id),
    server_id INTEGER REFERENCES servers(id),
    username TEXT,
    action TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('dry-run', 'apply')),
    status TEXT NOT NULL CHECK (status IN ('ok', 'skipped', 'blocked', 'failed')),
    message TEXT,
    ticket TEXT,
    groups_snapshot TEXT,
    shell_snapshot TEXT,
    performed_by TEXT NOT NULL,
    triggered_by TEXT NOT NULL CHECK (triggered_by IN ('manual', 'automatic')),
    ansible_run_id TEXT,
    raw_stdout_ref TEXT,
    performed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_user_id INTEGER NOT NULL REFERENCES managed_users(id),
    doc_type TEXT NOT NULL CHECK (doc_type IN ('ticket_ref', 'uploaded_file', 'note')),
    reference TEXT NOT NULL,
    description TEXT,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collected_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_user_id INTEGER NOT NULL REFERENCES managed_users(id),
    server_id INTEGER NOT NULL REFERENCES servers(id),
    collected_at TEXT NOT NULL,
    collection_status TEXT NOT NULL CHECK (collection_status IN ('ok', 'empty', 'no_access', 'error')),
    history_excerpt TEXT
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    run_date TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    users_checked INTEGER DEFAULT 0,
    users_removed INTEGER DEFAULT 0,
    status TEXT,
    UNIQUE (run_type, run_date)
);

CREATE INDEX IF NOT EXISTS idx_managed_users_status ON managed_users(status);
CREATE INDEX IF NOT EXISTS idx_managed_users_server ON managed_users(server_id);
CREATE INDEX IF NOT EXISTS idx_action_log_user ON action_log(managed_user_id);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(managed_user_id);
CREATE INDEX IF NOT EXISTS idx_collected_facts_user ON collected_facts(managed_user_id);
