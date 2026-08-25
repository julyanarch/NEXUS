param(
    [int]$IntervalSeconds = 60,
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[NEXUS AUTO-COMMIT] $Message"
}

if (-not (Test-Path ".git")) {
    Write-Error "Esta pasta ainda nao e um repositorio Git. Rode 'git init' antes."
}

Write-Info "Monitorando alteracoes a cada $IntervalSeconds segundos."
Write-Info "Use Ctrl+C para parar."

while ($true) {
    $status = git status --porcelain

    if ($status) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Info "Alteracoes detectadas em $timestamp"

        git add -A
        git commit -m "auto: atualiza projeto em $timestamp"

        $remote = git remote
        if ($remote -contains "origin") {
            git push origin $Branch
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}

