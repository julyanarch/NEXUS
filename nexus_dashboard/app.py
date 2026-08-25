import functools
import os
import secrets
import subprocess

from flask import Flask, flash, redirect, render_template, request, session, url_for
from passlib.hash import sha512_crypt

import ai_engine
import ansible_bridge
import config
import inventory_builder
import models
from scheduler import start_scheduler


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    os.makedirs(config.ARTIFACTS_DIR, exist_ok=True)
    models.init_db()
    inventory_builder.rebuild_inventory()

    if not app.config.get("TESTING"):
        start_scheduler()

    register_routes(app)
    return app


def require_operator(view_func):
    @functools.wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("operator_name"):
            flash("Informe seu nome de operador antes de executar acoes.", "warning")
            session["next_url"] = request.url
            return redirect(url_for("set_operator"))
        return view_func(*args, **kwargs)
    return wrapped


def servers_missing_vault():
    return [
        s for s in models.list_servers()
        if s["enabled"] and not config.server_vault_configured(s["name"])
    ]


def register_routes(app):

    @app.context_processor
    def inject_globals():
        missing = servers_missing_vault()
        return {
            "operator_name": session.get("operator_name"),
            "servers_missing_vault": missing,
            "lock_max_days": config.LOCK_MAX_DAYS,
            "lock_warning_days": config.LOCK_WARNING_DAYS,
        }

    # --------------------------------------------------------------- home --

    @app.route("/")
    def dashboard():
        counts = models.summary_counts()
        expiring_users = [
            u for u in models.list_locked_users()
            if (u["days_locked"] or 0) >= config.LOCK_WARNING_DAYS
        ]
        recent_runs = models.list_recent_runs(limit=10)
        return render_template(
            "dashboard.html", counts=counts, expiring_users=expiring_users, recent_runs=recent_runs
        )

    # ---------------------------------------------------------- operador --

    @app.route("/operador", methods=["GET", "POST"])
    def set_operator():
        if request.method == "POST":
            name = request.form.get("operator_name", "").strip()
            if not name:
                flash("Informe um nome valido.", "danger")
                return redirect(url_for("set_operator"))
            session["operator_name"] = name
            next_url = session.pop("next_url", None)
            flash(f"Identificado como {name}.", "success")
            return redirect(next_url or url_for("dashboard"))
        return render_template("setup/operador.html")

    # -------------------------------------------------------------- vault --

    def _ensure_vault_pass_file():
        os.makedirs(os.path.dirname(config.VAULT_PASS_FILE), exist_ok=True)
        if not os.path.exists(config.VAULT_PASS_FILE):
            # Segredo local usado apenas para criptografar/descriptografar os
            # vault.yml de cada servidor (nao e a senha de nenhuma conta),
            # gerado uma unica vez e mantido estavel para todos os servidores.
            with open(config.VAULT_PASS_FILE, "w", encoding="utf-8") as f:
                f.write(secrets.token_urlsafe(48))
            os.chmod(config.VAULT_PASS_FILE, 0o600)

    @app.route("/servers/<int:server_id>/vault", methods=["GET", "POST"])
    @require_operator
    def server_vault(server_id):
        server = models.get_server(server_id)
        if request.method == "POST":
            become_password = request.form.get("become_password", "")
            if not become_password:
                flash("Informe a senha de sudo desse servidor.", "danger")
                return redirect(url_for("server_vault", server_id=server_id))

            _ensure_vault_pass_file()
            vars_dir = config.host_vars_dir(server["name"])
            os.makedirs(vars_dir, exist_ok=True)

            encrypt = subprocess.run(
                [
                    "ansible-vault", "encrypt_string",
                    "--vault-password-file", config.VAULT_PASS_FILE,
                    become_password, "--name", "vault_become_password",
                ],
                cwd=config.ANSIBLE_DIR,
                capture_output=True,
                text=True,
            )
            if encrypt.returncode != 0:
                flash(f"Falha ao gravar o vault de {server['name']}: {encrypt.stderr}", "danger")
                return redirect(url_for("server_vault", server_id=server_id))

            vault_path = config.host_vault_file(server["name"])
            with open(vault_path, "w", encoding="utf-8") as f:
                f.write(encrypt.stdout + "\n")
            os.chmod(vault_path, 0o600)

            vars_path = config.host_vars_file(server["name"])
            if not os.path.exists(vars_path):
                with open(vars_path, "w", encoding="utf-8") as f:
                    f.write('ansible_become_pass: "{{ vault_become_password }}"\n')

            flash(
                f"Senha de sudo de {server['name']} configurada no Ansible Vault. "
                "Nenhum prompt sera exibido nas proximas execucoes nesse servidor.",
                "success",
            )
            return redirect(url_for("list_servers"))

        return render_template(
            "servers/vault.html", server=server,
            already_configured=config.server_vault_configured(server["name"]),
        )

    # ------------------------------------------------------------ servers --

    @app.route("/servers")
    def list_servers():
        servers = models.list_servers()
        vault_status = {s["id"]: config.server_vault_configured(s["name"]) for s in servers}
        return render_template("servers/list.html", servers=servers, vault_status=vault_status)

    @app.route("/servers/new", methods=["GET", "POST"])
    @require_operator
    def new_server():
        if request.method == "POST":
            models.create_server(
                request.form["name"].strip(),
                request.form["ssh_host"].strip(),
                request.form["ssh_user"].strip(),
                int(request.form.get("ssh_port") or 22),
                request.form.get("enabled") == "on",
            )
            inventory_builder.rebuild_inventory()
            flash("Servidor cadastrado.", "success")
            return redirect(url_for("list_servers"))
        return render_template("servers/form.html", server=None)

    @app.route("/servers/<int:server_id>/edit", methods=["GET", "POST"])
    @require_operator
    def edit_server(server_id):
        server = models.get_server(server_id)
        if request.method == "POST":
            models.update_server(
                server_id,
                request.form["name"].strip(),
                request.form["ssh_host"].strip(),
                request.form["ssh_user"].strip(),
                int(request.form.get("ssh_port") or 22),
                request.form.get("enabled") == "on",
            )
            inventory_builder.rebuild_inventory()
            flash("Servidor atualizado.", "success")
            return redirect(url_for("list_servers"))
        return render_template("servers/form.html", server=server)

    @app.route("/servers/<int:server_id>/toggle", methods=["POST"])
    @require_operator
    def toggle_server(server_id):
        models.toggle_server(server_id)
        inventory_builder.rebuild_inventory()
        flash("Status do servidor alterado.", "success")
        return redirect(url_for("list_servers"))

    @app.route("/servers/<int:server_id>/test", methods=["POST"])
    @require_operator
    def test_server(server_id):
        # So testa conectividade SSH (sem sudo), por isso nao depende do
        # Vault estar configurado - pode ser usado antes mesmo de definir a
        # senha de sudo do servidor.
        server = models.get_server(server_id)
        result = ansible_bridge.test_connection(server["name"])
        models.set_server_test_result(server_id, "ok" if result["success"] else "falhou")
        flash(
            f"Teste em {server['name']}: {'sucesso' if result['success'] else 'falhou'}.",
            "success" if result["success"] else "danger",
        )
        return redirect(url_for("list_servers"))

    # ------------------------------------------------------------- actions --

    @app.route("/actions/new")
    @require_operator
    def new_action_form():
        return render_template("actions/new.html", servers=models.list_servers())

    def _collect_action_form():
        return {
            "username": request.form.get("username", "").strip(),
            "action": request.form.get("action", "").strip().lower(),
            "home": request.form.get("home", "yes"),
            "reason": request.form.get("reason", "").strip(),
            "ticket": request.form.get("ticket", "").strip(),
            "groups": request.form.get("groups", "").strip(),
            "shell": request.form.get("shell", "").strip() or "/bin/bash",
        }

    def _selected_server_ids():
        ids = request.form.getlist("server_ids")
        return [int(i) for i in ids]

    def _run_action(mode):
        row = _collect_action_form()
        server_ids = _selected_server_ids()
        if not row["username"] or not row["action"] or not server_ids:
            flash("Preencha usuario, acao e ao menos um servidor.", "danger")
            return redirect(url_for("new_action_form"))

        target_servers = [models.get_server(sid) for sid in server_ids]
        missing = [s["name"] for s in target_servers if not config.server_vault_configured(s["name"])]
        if missing:
            flash(
                "Configure a senha de sudo antes de executar acoes nestes servidores: "
                + ", ".join(missing),
                "warning",
            )
            return redirect(url_for("list_servers"))

        password_hashes = None
        if mode == "apply" and row["action"] in ("create", "add"):
            password = request.form.get("temp_password", "")
            confirmation = request.form.get("temp_password_confirm", "")
            if not password or password != confirmation:
                flash("Senha temporaria vazia ou nao confere com a confirmacao.", "danger")
                return redirect(url_for("new_action_form"))
            password_hashes = {row["username"]: sha512_crypt.hash(password)}

        operator = session["operator_name"]
        overall_ok = True

        for server_id in server_ids:
            server = models.get_server(server_id)
            result = ansible_bridge.run_sanitize(
                target_host=server["name"], mode=mode, rows=[row], password_hashes=password_hashes,
            )
            status = "ok" if result["success"] else "failed"
            overall_ok = overall_ok and result["success"]

            managed_user_id = None
            if mode == "apply" and result["success"]:
                models.upsert_user_after_action(
                    row["username"], server_id, row["action"], row["groups"], row["shell"],
                    row["home"], row["ticket"], row["reason"], operator,
                )
                found = models.find_user_by_server(row["username"], server_id)
                managed_user_id = found["id"] if found else None
            else:
                existing = models.find_user_by_server(row["username"], server_id)
                managed_user_id = existing["id"] if existing else None

            models.log_action(
                managed_user_id=managed_user_id,
                server_id=server_id,
                username=row["username"],
                action=row["action"],
                mode=mode,
                status=status,
                message=result["stdout"][-2000:] if result["stdout"] else ("sucesso" if result["success"] else "falha na execucao"),
                ticket=row["ticket"],
                groups_snapshot=row["groups"],
                shell_snapshot=row["shell"],
                performed_by=operator,
                triggered_by="manual",
                ansible_run_id=result.get("run_id"),
            )

        if mode == "dry-run":
            flash("Simulacao concluida. Veja o resultado em /runs." if overall_ok else "Simulacao encontrou falhas.",
                  "success" if overall_ok else "danger")
        else:
            flash("Acao aplicada com sucesso." if overall_ok else "Acao aplicada com falhas em um ou mais servidores.",
                  "success" if overall_ok else "danger")
        return redirect(url_for("list_users"))

    @app.route("/actions/new/dry-run", methods=["POST"])
    @require_operator
    def action_dry_run():
        return _run_action("dry-run")

    @app.route("/actions/new/apply", methods=["POST"])
    @require_operator
    def action_apply():
        confirmation = request.form.get("bulk_confirmation", "")
        if len(_selected_server_ids()) > 1 and confirmation.strip().upper() != "APLICAR":
            flash('Para aplicar em mais de um servidor, digite "APLICAR" no campo de confirmacao.', "danger")
            return redirect(url_for("new_action_form"))
        return _run_action("apply")

    # --------------------------------------------------------------- users --

    @app.route("/users")
    def list_users():
        status = request.args.get("status") or None
        search = request.args.get("q") or None
        return render_template("users/list.html", users=models.list_users(status, search), status=status, search=search or "")

    @app.route("/users/<int:user_id>")
    def user_detail(user_id):
        user = models.get_user(user_id)
        if user is None:
            flash("Usuario nao encontrado.", "danger")
            return redirect(url_for("list_users"))
        insights = ai_engine.build_user_insights(user)
        timeline = models.list_action_log_for_user(user_id)
        documents = models.list_documents_for_user(user_id)
        return render_template(
            "users/detail.html", user=user, insights=insights, timeline=timeline, documents=documents,
        )

    @app.route("/users/<int:user_id>/documents", methods=["POST"])
    @require_operator
    def add_document(user_id):
        models.add_document(
            user_id,
            request.form.get("doc_type", "note"),
            request.form.get("reference", "").strip(),
            request.form.get("description", "").strip(),
            session["operator_name"],
        )
        flash("Documento vinculado.", "success")
        return redirect(url_for("user_detail", user_id=user_id))

    @app.route("/users/<int:user_id>/history", methods=["POST"])
    @require_operator
    def collect_history(user_id):
        user = models.get_user(user_id)
        if not config.server_vault_configured(user["server_name"]):
            flash(f'Configure a senha de sudo de "{user["server_name"]}" antes de coletar historico.', "warning")
            return redirect(url_for("user_detail", user_id=user_id))
        result = ansible_bridge.fetch_bash_history(user["server_name"], user["username"])
        models.save_collected_facts(user_id, user["server_id"], result["status"], result.get("excerpt", ""))
        flash("Coleta de historico concluida.", "success")
        return redirect(url_for("user_detail", user_id=user_id))

    @app.route("/users/<int:user_id>/force-removal", methods=["POST"])
    @require_operator
    def force_removal(user_id):
        user = models.get_user(user_id)
        if not config.server_vault_configured(user["server_name"]):
            flash(f'Configure a senha de sudo de "{user["server_name"]}" antes de remover.', "warning")
            return redirect(url_for("user_detail", user_id=user_id))
        result = ansible_bridge.run_sanitize(
            target_host=user["server_name"], mode="apply",
            rows=[{"username": user["username"], "action": "remove", "home": "no",
                   "reason": "remocao manual antecipada", "ticket": user["ticket"] or "",
                   "groups": "", "shell": ""}],
        )
        if result["success"]:
            models.upsert_user_after_action(
                user["username"], user["server_id"], "remove", "", "", "no",
                user["ticket"], "remocao manual antecipada", session["operator_name"],
            )
        models.log_action(
            managed_user_id=user_id, server_id=user["server_id"], username=user["username"],
            action="remove", mode="apply", status="ok" if result["success"] else "failed",
            message=result["stdout"][-2000:] if result["stdout"] else "",
            ticket=user["ticket"], groups_snapshot="", shell_snapshot="",
            performed_by=session["operator_name"], triggered_by="manual", ansible_run_id=result.get("run_id"),
        )
        flash("Remocao executada." if result["success"] else "Falha ao remover.", "success" if result["success"] else "danger")
        return redirect(url_for("user_detail", user_id=user_id))

    # ---------------------------------------------------------------- runs --

    @app.route("/runs")
    def list_runs():
        return render_template("runs/list.html", runs=models.list_recent_runs(limit=200))


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
