"""Prepara os dados dos graficos do Painel - toda a conta (px, %, ordem fixa
de cores) e feita aqui, em Python; os templates so desenham o que recebem."""

import config
import models


def build_status_chart(counts):
    """Distribuicao ativos/bloqueados/removidos para a barra empilhada do
    Painel. Ordem fixa (nunca alternada) e cores de status reservadas."""
    segments = [
        {"key": "active", "label": "Ativos", "count": counts["active"], "color": config.CHART_COLOR_GOOD},
        {"key": "locked", "label": "Bloqueados", "count": counts["locked"], "color": config.CHART_COLOR_WARNING},
        {"key": "removed", "label": "Removidos", "count": counts["removed"], "color": config.CHART_COLOR_NEUTRAL},
    ]
    total = sum(s["count"] for s in segments)
    return {"segments": [s for s in segments if s["count"] > 0], "total": total}


def build_timeline_chart():
    """Execucoes por dia (sucesso/falha), com alturas em px ja calculadas -
    o template so desenha, sem fazer conta."""
    days = models.daily_execution_counts(config.TIMELINE_DAYS)
    max_total = max((d["ok"] + d["failed"] for d in days), default=0) or 1
    max_h = config.TIMELINE_CHART_HEIGHT_PX

    columns = []
    for d in days:
        ok_px = round(d["ok"] / max_total * max_h) if d["ok"] else 0
        failed_px = round(d["failed"] / max_total * max_h) if d["failed"] else 0
        columns.append({
            "label": d["label"],
            "ok": d["ok"],
            "failed": d["failed"],
            "ok_px": ok_px,
            "failed_px": failed_px,
            "title": f"{d['label']}: {d['ok']} com sucesso, {d['failed']} com falha",
        })
    return {
        "columns": columns,
        "max_total": max_total if any(d["ok"] or d["failed"] for d in days) else 0,
        "chart_height": max_h,
    }


def build_server_chart():
    """Total de execucoes por servidor (ultimos N dias) - barras de
    magnitude, uma so cor (nao e status)."""
    rows = models.executions_per_server(config.SERVER_CHART_WINDOW_DAYS)
    max_total = max((r["total"] for r in rows), default=0) or 1
    bars = []
    for r in rows:
        width_pct = round(r["total"] / max_total * 100, 1) if r["total"] else 0
        bars.append({"name": r["server_name"], "total": r["total"], "width_pct": width_pct})
    return {"bars": bars, "window_days": config.SERVER_CHART_WINDOW_DAYS}
