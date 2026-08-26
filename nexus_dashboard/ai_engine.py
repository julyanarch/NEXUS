"""IA NEXUS - motor de regras local.

Nao chama nenhuma API externa: le apenas os dados ja coletados no SQLite
(cadastro do usuario, historico de acoes e o ultimo resultado de coleta de
bash_history) e monta fatos estruturados + um paragrafo em portugues. Toda a
logica e determinística (if/elif sobre os dados), o que a torna auditavel e
facil de explicar.
"""

import config
import models


def _format_datetime(value):
    if not value:
        return None
    return value.replace("T", " ")


def build_user_insights(managed_user_row):
    user = managed_user_row
    action_log = models.list_action_log_for_user(user["id"])
    facts_row = models.latest_collected_facts(user["id"])

    groups = [g for g in (user["groups_csv"] or "").split(";") if g]

    days_locked = None
    days_remaining = None
    urgency = False
    if user["status"] == "locked":
        days_locked = int(user["days_locked"]) if user["days_locked"] is not None else 0
        days_remaining = max(config.LOCK_MAX_DAYS - days_locked, 0)
        urgency = days_remaining <= (config.LOCK_MAX_DAYS - config.LOCK_WARNING_DAYS)

    # A chave se chama "lines", nao "items" - "items" colide com o metodo
    # dict.items() e faz o Jinja2 (que tenta getattr antes de __getitem__)
    # pegar o metodo em vez do valor, sem erro nenhum ate tentar iterar de
    # verdade (ex.: `| join`), quando vira "'builtin_function_or_method'
    # object is not iterable".
    commands = {"status": "no_access", "lines": [], "collected_at": None}
    if facts_row is not None:
        commands["status"] = facts_row["collection_status"]
        commands["collected_at"] = _format_datetime(facts_row["collected_at"])
        if facts_row["collection_status"] == "ok" and facts_row["history_excerpt"]:
            commands["lines"] = facts_row["history_excerpt"].splitlines()

    facts = {
        "username": user["username"],
        "server_name": user["server_name"],
        "status": user["status"],
        "groups": groups,
        "shell": user["shell"],
        "ticket": user["ticket"],
        "reason": user["reason"],
        "created_ticket": user["created_ticket"],
        "created_reason": user["created_reason"],
        "created_at": _format_datetime(user["created_at"]),
        "created_by": user["created_by"],
        "locked_at": _format_datetime(user["locked_at"]),
        "days_locked": days_locked,
        "days_remaining": days_remaining,
        "urgency": urgency,
        "removed_at": _format_datetime(user["removed_at"]),
        "removed_by": user["removed_by"],
        "removal_type": user["removal_type"],
        "commands": commands,
        "total_actions_registradas": len(action_log),
    }

    facts["summary_pt_br"] = _build_summary(facts)
    return facts


def _build_summary(facts):
    """So a sintese de situacao, em uma frase - o resto (servidor, criacao,
    permissoes, comandos) ja aparece organizado nos cards "Fatos" e "Ultimos
    comandos executados" logo abaixo, repetir tudo aqui so poluia a tela."""
    if facts["status"] == "active":
        return f"{facts['username']} esta ativo em {facts['server_name']}."

    if facts["status"] == "locked":
        summary = (
            f"{facts['username']} esta bloqueado ha {facts['days_locked']} dia(s) - "
            f"restam {facts['days_remaining']} dia(s) ate a remocao automatica."
        )
        if facts["urgency"]:
            summary += (
                " Proximo do limite: sera removido automaticamente pelo NEXUS "
                "se nao houver acao manual antes disso."
            )
        return summary

    if facts["status"] == "removed":
        tipo = "automaticamente (expiracao de 90 dias de bloqueio)" if facts["removal_type"] == "automatic" else "manualmente"
        return f"{facts['username']} foi removido {tipo} em {facts['removed_at']} por {facts['removed_by']}."

    return f"{facts['username']}."
