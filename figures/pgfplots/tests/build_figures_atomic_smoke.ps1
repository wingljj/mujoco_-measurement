$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '..\build_figures.ps1')

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jmechplots-atomic-{0}" -f [guid]::NewGuid().ToString('N'))
$stagingDir = Join-Path $testRoot 'staging'
$outputDir = Join-Path $testRoot 'word-output'
$basenames = @(Get-FigureBasenames)

try {
    New-Item -ItemType Directory -Force -Path $stagingDir, $outputDir | Out-Null

    $sentinelPath = Join-Path $outputDir "$($basenames[0]).png"
    Set-Content -LiteralPath $sentinelPath -Value 'sentinel' -NoNewline
    Set-Content -LiteralPath (Join-Path $stagingDir "$($basenames[-1]).png") -Value 'stale' -NoNewline

    $failedAsExpected = $false
    try {
        Invoke-AtomicFigureBatch `
            -Basenames $basenames `
            -StagingDirectory $stagingDir `
            -StagingParentDirectory $testRoot `
            -OutputDirectory $outputDir `
            -BuildAction {
                param($basename, $batchStagingDirectory)
                if ($basename -ne $basenames[-1]) {
                    Set-Content `
                        -LiteralPath (Join-Path $batchStagingDirectory "${basename}.png") `
                        -Value "new:${basename}" `
                        -NoNewline
                }
            }
    }
    catch {
        $failedAsExpected = $true
    }

    if (-not $failedAsExpected) { throw 'Incomplete batch unexpectedly published.' }
    if ((Get-Content -Raw -LiteralPath $sentinelPath) -ne 'sentinel') {
        throw 'Failed batch changed the existing Word PNG.'
    }
    if (Test-Path -LiteralPath (Join-Path $outputDir "$($basenames[1]).png")) {
        throw 'Failed batch published a partial Word PNG set.'
    }

    Invoke-AtomicFigureBatch `
        -Basenames $basenames `
        -StagingDirectory $stagingDir `
        -StagingParentDirectory $testRoot `
        -OutputDirectory $outputDir `
        -BuildAction {
            param($basename, $batchStagingDirectory)
            Set-Content `
                -LiteralPath (Join-Path $batchStagingDirectory "${basename}.png") `
                -Value "new:${basename}" `
                -NoNewline
        }

    foreach ($basename in $basenames) {
        $publishedPath = Join-Path $outputDir "${basename}.png"
        if ((Get-Content -Raw -LiteralPath $publishedPath) -ne "new:${basename}") {
            throw "Successful batch did not publish current output: $basename"
        }
    }

    'Atomic figure publication smoke test passed.'
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
