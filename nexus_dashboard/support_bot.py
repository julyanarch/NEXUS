"""NEXUS AI - balaozinho de suporte do NEXUS (canto inferior direito), pra
perguntas pontuais sobre os usuarios e servidores ja cadastrados (ex.:
"fulano existe no servidor X?", "quais usuarios estao bloqueados?").

100% local - sem IA, sem API externa, sem nenhuma chamada de rede. So
reconhece a pergunta por palavra-chave (nome de servidor ja cadastrado,
status "bloqueado/ativo/removido", ou um username que ja existe no banco) e
monta a resposta direto a partir das mesmas consultas que ja existem em
models.py (list_users, list_servers) - nao e uma fonte de dado nova, e uma
forma diferente de perguntar o que o painel ja mostra em tela. Qualquer
pergunta fora desses formatos recebe uma resposta fixa, explicando o que ele
sabe responder.
"""
import re

import models

STATUS_BY_WORD = {
    "bloqueado": "locked", "bloqueados": "locked", "bloqueada": "locked", "bloqueadas": "locked",
    "ativo": "active", "ativos": "active", "ativa": "active", "ativas": "active",
    "removido": "removed", "removidos": "removed", "removida": "removed", "removidas": "removed",
}
STATUS_LABEL = {"active": "ativo", "locked": "bloqueado", "removed": "removido"}

# Nomes de usuario no NEXUS seguem a convencao nome.sobrenome (ver
# nexus_sanitize_users.sh) - reconhece esse padrao na pergunta mesmo se o
# usuario ainda NAO existir no banco (e exatamente o caso de uso de "fulano
# existe no servidor X?" quando a resposta e "nao").
USERNAME_RE = re.compile(r"\b[a-z0-9]+\.[a-z0-9]+\b")

SCOPE_MESSAGE = (
    "Eu só respondo perguntas sobre os usuários e servidores cadastrados no NEXUS. "
    "Tente algo como \"quais servidores existem?\", \"quais usuários existem no servidor X?\", "
    "\"fulano existe no servidor Y?\" ou \"quais usuários estão bloqueados?\"."
)


def _match_server(question_lower, servers):
    for server in servers:
        if server["name"].lower() in question_lower:
            return server
    return None


def _match_status(question_lower):
    for word, status in STATUS_BY_WORD.items():
        if word in question_lower:
            return status
    return None


def _match_username(question_lower):
    match = USERNAME_RE.search(question_lower)
    return match.group(0) if match else None


def _status_sentence(row):
    label = STATUS_LABEL.get(row["status"], row["status"])
    if row["status"] == "locked" and row["days_locked"] is not None:
        return f"{label} há {row['days_locked']} dia(s)"
    return label


def _answer_server_list(servers):
    if not servers:
        return "Nenhum servidor cadastrado no NEXUS ainda."
    names = ", ".join(s["name"] for s in servers)
    return f"Servidores cadastrados ({len(servers)}): {names}."


def _answer_username_lookup(username, server, rows):
    if not rows:
        where = f" no servidor {server['name']}" if server else ""
        return f'Não encontrei o usuário "{username}"{where}.'
    return " ".join(
        f"Sim, {r['username']} existe em {r['server_name']}: {_status_sentence(r)}." for r in rows
    )


def _answer_user_list(status, server, rows):
    if not rows:
        return "Nenhum usuário encontrado com esses critérios."
    bullets = "\n".join(f"- {r['username']} em {r['server_name']}: {_status_sentence(r)}" for r in rows)
    count = len(rows)
    plural = "usuário" if count == 1 else "usuários"
    return f"{count} {plural} encontrado(s):\n{bullets}"


def answer(question):
    question = (question or "").strip()
    if not question:
        return SCOPE_MESSAGE

    question_lower = question.lower()
    servers = models.list_servers()
    server = _match_server(question_lower, servers)
    status = _match_status(question_lower)
    username = _match_username(question_lower)

    if re.search(r"\bservidor(es)?\b", question_lower) and not (status or username or server):
        return _answer_server_list(servers)

    if not (status or username or server):
        return SCOPE_MESSAGE

    rows = models.list_users(status=status, server_id=server["id"] if server else None)
    if username:
        rows = [r for r in rows if r["username"].lower() == username.lower()]
        return _answer_username_lookup(username, server, rows)
    return _answer_user_list(status, server, rows)
