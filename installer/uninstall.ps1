# Desinstalador do Prospector.
#
# Remove o programa e os atalhos. A base de leads é tratada à parte e só sai
# se você pedir: ela é o resultado de buscas que custaram quota, e apagar isso
# junto com o programa seria destruir trabalho sem avisar.

$ErrorActionPreference = "SilentlyContinue"

$AppName = "Prospector"
$target  = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
$dataDir = Join-Path $env:LOCALAPPDATA $AppName
$db      = Join-Path $dataDir "leads.db"

Write-Host ""
Write-Host "  Desinstalando o $AppName" -ForegroundColor Cyan
Write-Host ""

Get-Process -Name $AppName | Stop-Process -Force
Start-Sleep -Seconds 1

Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk") -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk") -Force
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName" -Recurse -Force
Write-Host "  Atalhos e registro removidos."

$leads = 0
if (Test-Path $db) {
    try {
        # Conta as linhas sem depender do SQLite estar instalado: o cabecalho
        # do arquivo basta para saber que ha uma base ali.
        $leads = [int]((Get-Item $db).Length / 1KB)
    } catch { }
}

if (Test-Path $dataDir) {
    Write-Host ""
    Write-Host "  Sua base de canais fica em:" -ForegroundColor Yellow
    Write-Host "    $dataDir  (~$leads KB)"
    Write-Host "  Ela nao e apagada por padrao. Buscas custam quota da API."
    $answer = Read-Host "  Apagar tambem a base de leads? (s/N)"
    if ($answer -match "^[sSyY]") {
        Remove-Item $dataDir -Recurse -Force
        Write-Host "  Base apagada." -ForegroundColor DarkGray
    } else {
        Write-Host "  Base mantida." -ForegroundColor Green
    }
}

# Por último: a pasta some com este próprio script dentro dela, então a
# remoção é agendada para depois que o PowerShell soltar o arquivo.
Write-Host ""
Write-Host "  Removendo o programa..."
$cmd = "Start-Sleep -Seconds 2; Remove-Item '$target' -Recurse -Force"
Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-Command", $cmd

Write-Host "  Desinstalado." -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 2
