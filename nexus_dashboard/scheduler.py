"""Job diario de expiracao automatica de contas bloqueadas (90 dias).

Roda dentro do proprio processo Flask via APScheduler (BackgroundScheduler),
processo unico - sem workers multiplos, o que evita o problema classico de
o job rodar em duplicidade. Uma tabela `scheduler_runs` com UNIQUE(run_type,
run_date) e a segunda linha de defesa contra execucao duplicada no mesmo dia.
"""

from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

import ansible_bridge
import config
import models

RUN_TYPE = "lock_expiry_check"


def run_lock_expiry_check():
    run_date = date.today().isoformat()
    if not models.try_start_scheduler_run(RUN_TYPE, run_date):
        return  # ja rodou hoje

    users_checked = 0
    users_removed = 0

    for user in models.list_locked_users():
        users_checked += 1
        if user["lock_review_needed"]:
            # Bloqueio importado de fora do NEXUS (usuario ja existia
            # bloqueado no servidor) - data real desconhecida, nunca conta
            # pra remocao automatica ate revisao manual (confirm_lock_start).
            continue
        days_locked = user["days_locked"] or 0
        if days_locked < config.LOCK_MAX_DAYS:
            continue

        result = ansible_bridge.run_sanitize(
            target_host=user["server_name"],
            mode="apply",
            rows=[{
                "username": user["username"],
                "action": "remove",
                "home": "no",
                "reason": f"expiracao automatica de bloqueio ({config.LOCK_MAX_DAYS} dias)",
                "ticket": user["ticket"] or "",
                "groups": "",
                "shell": "",
            }],
        )

        if result["success"]:
            models.mark_removed_automatically(user["id"])
            users_removed += 1
            status = "ok"
            message = f"Removido automaticamente apos {days_locked} dias de bloqueio."
        else:
            status = "failed"
            message = (
                f"Falha ao tentar remocao automatica apos {days_locked} dias de bloqueio; "
                "usuario permanece bloqueado e sera retentado no proximo ciclo."
            )

        models.log_action(
            managed_user_id=user["id"],
            server_id=user["server_id"],
            username=user["username"],
            action="remove",
            mode="apply",
            status=status,
            message=message,
            ticket=user["ticket"],
            groups_snapshot=user["groups_csv"],
            shell_snapshot=user["shell"],
            performed_by="system/scheduler",
            triggered_by="automatic",
            ansible_run_id=result.get("run_id"),
        )

    models.finish_scheduler_run(RUN_TYPE, run_date, users_checked, users_removed, "completed")


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_lock_expiry_check,
        trigger="cron",
        hour=config.SCHEDULER_HOUR,
        minute=config.SCHEDULER_MINUTE,
        id="lock_expiry_check",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
