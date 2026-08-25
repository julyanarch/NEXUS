"""IA NEXUS - motor de regras local.

Nao chama nenhuma API externa: le apenas os dados ja coletados no SQLite
(cadastro do usuario, historico de acoes, documentos vinculados e o ultimo
resultado de coleta de bash_history) e monta fatos estruturados + um
paragrafo em portugues. Toda a logica e determinística (if/elif sobre os
dados), o que a torna auditavel e facil de explicar.
"""

import config
import models

COMMAND_STATUS_LABELS = {
    "ok": "coletado com sucesso (best-effort)",
    "empty": "historico vazio ou desativado no servidor",
    "no_access": "arquivo de historico nao encontrado para este usuario",
    "error": "falha ao coletar o historico",
}


def _format_datetime(value):
    if not value:
        return None
    return value.replace("T", " ")


def build_user_insights(managed_user_row):
    user = managed_user_row
    action_log = models.list_action_log_for_user(user["id"])
    documents = models.list_documents_for_user(user["id"])
    facts_row = models.latest_collected_facts(user["id"])

    groups = [g for g in (user["groups_csv"] or "").split(";") if g]

    days_locked = None
    days_remaining = None
    urgency = False
    if user["status"] == "locked":
        days_locked = int(user["days_locked"]) if user["days_locked"] is not None else 0
        days_remaining = max(config.LOCK_MAX_DAYS - days_locked, 0)
        urgency = days_remaining <= (config.LOCK_MAX_DAYS - config.LOCK_WARNING_DAYS)

    commands = {"status": "no_access", "items": [], "collected_at": None}
    if facts_row is not None:
        commands["status"] = facts_row["collection_status"]
        commands["collected_at"] = _format_datetime(facts_row["collected_at"])
        if facts_row["collection_status"] == "ok" and facts_row["history_excerpt"]:
            commands["items"] = facts_row["history_excerpt"].splitlines()

    doc_list = [
        {
            "type": d["doc_type"],
            "reference": d["reference"],
            "description": d["description"],
            "uploaded_by": d["uploaded_by"],
            "uploaded_at": _format_datetime(d["uploaded_at"]),
        }
        for d in documents
    ]

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
        "documents": doc_list,
        "commands": commands,
        "total_actions_registradas": len(action_log),
    }

    facts["summary_pt_br"] = _build_summary(facts)
    return facts


def _build_summary(facts):
    parts = []

    parts.append(
        f"O usuario {facts['username']} esta cadastrado no servidor {facts['server_name']}, "
        f"criado em {facts['created_at']} por {facts['created_by']}"
        + (f" (chamado {facts['created_ticket']})" if facts["created_ticket"] else "") + "."
    )

    if facts["ticket"] and facts["ticket"] != facts["created_ticket"]:
        parts.append(
            f"Chamado/motivo da acao mais recente: {facts['ticket']}"
            + (f" ({facts['reason']})" if facts["reason"] else "") + "."
        )

    if facts["status"] == "active":
        parts.append("Situacao atual: ATIVO.")
    elif facts["status"] == "locked":
        parts.append(
            f"Situacao atual: BLOQUEADO ha {facts['days_locked']} dia(s), desde {facts['locked_at']}. "
            f"Faltam {facts['days_remaining']} dia(s) para a remocao automatica em "
            f"{config.LOCK_MAX_DAYS} dias."
        )
        if facts["urgency"]:
            parts.append(
                "Atencao: a conta esta proxima do limite de bloqueio e sera removida "
                "automaticamente pelo NEXUS se nao houver acao manual antes disso."
            )
    elif facts["status"] == "removed":
        tipo = "automaticamente (expiracao de 90 dias de bloqueio)" if facts["removal_type"] == "automatic" else "manualmente"
        parts.append(f"Situacao atual: REMOVIDO {tipo} em {facts['removed_at']} por {facts['removed_by']}.")

    if facts["groups"]:
        parts.append(f"Permissoes/grupos: {', '.join(facts['groups'])}.")
    else:
        parts.append("Nenhum grupo adicional registrado (sem privilegios elevados conhecidos).")

    if facts["documents"]:
        parts.append(f"Ha {len(facts['documents'])} documento(s)/chamado(s) vinculado(s) a este usuario.")
    else:
        parts.append("Nenhum documento vinculado a este usuario ate o momento.")

    cmd_status = facts["commands"]["status"]
    if cmd_status == "ok" and facts["commands"]["items"]:
        parts.append(
            f"Ultimos comandos conhecidos (best-effort, coletados em {facts['commands']['collected_at']}): "
            + "; ".join(facts["commands"]["items"][-5:]) + "."
        )
    else:
        parts.append(
            "Comandos executados: " + COMMAND_STATUS_LABELS.get(cmd_status, "sem informacao") + "."
        )

    return " ".join(parts)
