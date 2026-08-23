# Instalador do Prospector.
#
# Instala para o usuário atual, em %LOCALAPPDATA%\Programs\Prospector. Isso é
# de propósito: instalação por usuário não pede UAC, não precisa de senha de
# administrador e não mexe em nada do sistema. Sai tão limpo quanto entrou.
#
# A base de leads NÃO fica aqui — ela mora em %LOCALAPPDATA%\Prospector, para
# que reinstalar ou atualizar o programa nunca apague o seu trabalho.

$ErrorActionPreference = "Stop"

$AppName   = "Prospector"
$Publisher = "Prospector"
$Version   = "1.0.0"

$source  = Join-Path $PSScriptRoot "..\backend\dist\Prospector"
$target  = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
$exe     = Join-Path $target "$AppName.exe"
$dataDir = Join-Path $env:LOCALAPPDATA $AppName

Write-Host ""
Write-Host "  $AppName $Version" -ForegroundColor Cyan
Write-Host "  Instalando para $env:USERNAME (sem administrador)"
Write-Host ""

if (-not (Test-Path (Join-Path $source "$AppName.exe"))) {
    Write-Host "  ERRO: o programa ainda nao foi compilado." -ForegroundColor Red
    Write-Host "  Rode compilar.bat primeiro."
    Write-Host ""
    Read-Host "  Enter para sair"
    exit 1
}

# Uma versão anterior pode estar aberta e segurando o executável.
Get-Process -Name $AppName -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Fechando a versao que esta aberta..."
    $_ | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Write-Host "  [1/4] Copiando arquivos..."
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force

Write-Host "  [2/4] Criando atalhos..."
$shell = New-Object -ComObject WScript.Shell

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$lnk = $shell.CreateShortcut((Join-Path $startMenu "$AppName.lnk"))
$lnk.TargetPath       = $exe
$lnk.WorkingDirectory = $target
$lnk.Description      = "Prospeccao de canais do YouTube"
$lnk.Save()

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk2 = $shell.CreateShortcut((Join-Path $desktop "$AppName.lnk"))
$lnk2.TargetPath       = $exe
$lnk2.WorkingDirectory = $target
$lnk2.Description      = "Prospeccao de canais do YouTube"
$lnk2.Save()

Write-Host "  [3/4] Registrando em Aplicativos Instalados..."
Copy-Item (Join-Path $PSScriptRoot "uninstall.ps1") (Join-Path $target "uninstall.ps1") -Force

# HKCU: registro por usuário, sem privilégio elevado. O programa aparece em
# Configuracoes > Aplicativos com um botao de desinstalar que funciona.
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
New-Item -Path $key -Force | Out-Null
$uninstallCmd = "powershell -ExecutionPolicy Bypass -File `"$(Join-Path $target 'uninstall.ps1')`""
Set-ItemProperty $key DisplayName     $AppName
Set-ItemProperty $key DisplayVersion  $Version
Set-ItemProperty $key Publisher       $Publisher
Set-ItemProperty $key InstallLocation $target
Set-ItemProperty $key DisplayIcon     $exe
Set-ItemProperty $key UninstallString $uninstallCmd
Set-ItemProperty $key NoModify        1 -Type DWord
Set-ItemProperty $key NoRepair        1 -Type DWord
$sizeKb = [int]((Get-ChildItem $target -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
Set-ItemProperty $key EstimatedSize   $sizeKb -Type DWord

Write-Host "  [4/4] Pronto."
Write-Host ""
Write-Host "  Instalado em: $target"
Write-Host "  Seus leads:   $dataDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Atalhos criados no Menu Iniciar e na Area de Trabalho." -ForegroundColor Green
Write-Host ""

$open = Read-Host "  Abrir o Prospector agora? (S/n)"
if ($open -eq "" -or $open -match "^[sSyY]") { Start-Process $exe }
