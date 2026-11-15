[CmdletBinding()]
param(
    [ValidateSet('Configurar','Compilar','Gravar','Monitor','Ponte')]
    [string]$Etapa = 'Compilar',
    [ValidatePattern('^COM[1-9][0-9]*$')][string]$Porta = 'COM3',
    [string]$IdfPath = 'C:\esp\v5.5.5\esp-idf'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($Etapa -eq 'Configurar') {
        & python (Join-Path $PSScriptRoot 'configurar.py')
        if ($LASTEXITCODE -ne 0) { throw 'Preparo privado nao concluido.' }
        return
    }
    if ($Etapa -eq 'Ponte') {
        & python (Join-Path $PSScriptRoot 'ponte.py')
        if ($LASTEXITCODE -ne 0) { throw 'Ponte interrompida; consulte o diagnostico sem compartilhar segredos.' }
        return
    }
    if ($Etapa -eq 'Gravar' -and -not (Test-Path -LiteralPath '.private\private_config.h')) {
        throw 'Execute -Etapa Configurar primeiro. O build de verificacao nao deve ser gravado.'
    }
    $versionFile = Join-Path $IdfPath 'tools\cmake\version.cmake'
    $versionText = Get-Content -LiteralPath $versionFile -Raw
    $versionParts = foreach ($part in @('MAJOR','MINOR','PATCH')) {
        if ($versionText -notmatch "set\(IDF_VERSION_$part\s+(\d+)\)") {
            throw 'Nao foi possivel identificar a versao do SDK.'
        }
        $Matches[1]
    }
    $versionLabel = $versionParts -join '.'
    $buildPath = Join-Path $PSScriptRoot "build-$versionLabel"
    $sdkconfig = Join-Path $buildPath 'sdkconfig'
    $eimPython = "C:\Espressif\tools\python\v$versionLabel\venv"
    if (Test-Path -LiteralPath (Join-Path $eimPython 'Scripts\python.exe')) {
        # EIM stores tools directly under its root, unlike legacy export.ps1.
        $toolsRoot = 'C:\Espressif\tools'
        $env:IDF_TOOLS_PATH = $toolsRoot
        $env:IDF_PYTHON_ENV_PATH = $eimPython
        $env:IDF_PATH = $IdfPath
        $env:ESP_IDF_VERSION = "$($versionParts[0]).$($versionParts[1])"
        $toolDefinitions = (Get-Content (Join-Path $IdfPath 'tools\tools.json') -Raw | ConvertFrom-Json).tools
        $pathEntries = @((Join-Path $eimPython 'Scripts'), (Join-Path $IdfPath 'tools'))
        foreach ($tool in $toolDefinitions) {
            if ($tool.name -notin @('xtensa-esp-elf','xtensa-esp-elf-gdb','esp32ulp-elf','cmake','ninja','esp-rom-elfs')) { continue }
            $recommended = @($tool.versions | Where-Object status -eq 'recommended')[0]
            if (-not $recommended) { continue }
            $toolPath = Join-Path (Join-Path $toolsRoot $tool.name) $recommended.name
            if (-not (Test-Path -LiteralPath $toolPath)) { continue }
            foreach ($parts in $tool.export_paths) {
                $entry = $toolPath
                foreach ($part in $parts) { $entry = Join-Path $entry $part }
                $pathEntries += $entry
            }
            foreach ($property in $tool.export_vars.PSObject.Properties) {
                $value = ([string]$property.Value).Replace('${TOOL_PATH}', $toolPath)
                Set-Item -LiteralPath "Env:$($property.Name)" -Value $value
            }
        }
        $env:PATH = ($pathEntries -join ';') + ';' + $env:PATH
        $python = Join-Path $eimPython 'Scripts\python.exe'
        & $python (Join-Path $IdfPath 'tools\idf_tools.py') check-python-dependencies
        if ($LASTEXITCODE -ne 0) { throw 'Dependencias Python do SDK nao passaram na verificacao.' }
    } else {
        & (Join-Path $IdfPath 'export.ps1')
        $python = Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts\python.exe'
    }
    $idf = Join-Path $IdfPath 'tools\idf.py'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Python do ESP-IDF nao foi ativado.' }
    if ($Etapa -in @('Compilar','Gravar')) {
        & $python $idf -B $buildPath -D "SDKCONFIG=$sdkconfig" -D SDKCONFIG_DEFAULTS=sdkconfig.defaults.example reconfigure build
        if ($LASTEXITCODE -ne 0) { throw 'Build falhou; nenhum flash foi executado.' }
    }
    if ($Etapa -eq 'Gravar') {
        Write-Host "Gravando o firmware de ensaio na $Porta; substitui o programa existente da placa."
        & $python $idf -B $buildPath -p $Porta flash monitor
        if ($LASTEXITCODE -ne 0) { throw 'Flash/monitor terminou com erro; confira o resultado.' }
    } elseif ($Etapa -eq 'Monitor') {
        & $python $idf -B $buildPath -p $Porta monitor
    }
} finally {
    Pop-Location
}
