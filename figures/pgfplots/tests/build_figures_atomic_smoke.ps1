$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '..\build_figures.ps1')

$unicodeRoot = Join-Path ([System.IO.Path]::GetTempPath()) '科研-native-path-test'
$unicodeChild = Join-Path $unicodeRoot 'build\figure.pdf'
$nativeChild = ConvertTo-NativeRelativeChildPath -Path $unicodeChild -BaseDirectory $unicodeRoot
if ($nativeChild -ne 'build\figure.pdf') {
    throw "Native child path was not reduced to its ASCII-safe relative form: $nativeChild"
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jmechplots-atomic-{0}" -f [guid]::NewGuid().ToString('N'))
$stagingDir = Join-Path $testRoot 'staging'
$backupDir = Join-Path $testRoot 'word-publication-backup'
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

    Remove-Item -LiteralPath $sentinelPath -Force
    $originalBytes = @{}
    foreach ($basename in $basenames[1..($basenames.Count - 1)]) {
        $destinationPath = Join-Path $outputDir "${basename}.png"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("old:${basename}:$([guid]::NewGuid())")
        [System.IO.File]::WriteAllBytes($destinationPath, $bytes)
        $originalBytes[$basename] = $bytes
    }

    $replacementState = [pscustomobject]@{ Attempts = 0 }
    $replacementFailedAsExpected = $false
    try {
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
            } `
            -ReplaceAction {
                param($temporaryPath, $finalPath, $replacementIndex)
                $replacementState.Attempts++
                if ($replacementIndex -eq 1) {
                    throw 'Injected failure during second final replacement.'
                }
                Move-Item -LiteralPath $temporaryPath -Destination $finalPath -Force
            }
    }
    catch {
        $replacementFailedAsExpected = $true
    }

    if (-not $replacementFailedAsExpected) { throw 'Injected replacement failure did not propagate.' }
    if ($replacementState.Attempts -ne 2) { throw 'Failure was not injected during the second replacement.' }
    if (Test-Path -LiteralPath $sentinelPath) {
        throw 'Rollback retained a destination that did not exist before publication.'
    }
    foreach ($basename in $basenames[1..($basenames.Count - 1)]) {
        $restoredBytes = [System.IO.File]::ReadAllBytes((Join-Path $outputDir "${basename}.png"))
        $expectedBase64 = [Convert]::ToBase64String($originalBytes[$basename])
        $actualBase64 = [Convert]::ToBase64String($restoredBytes)
        if ($actualBase64 -ne $expectedBase64) {
            throw "Rollback did not restore exact bytes: $basename"
        }
    }
    if ((Test-Path -LiteralPath $stagingDir) -or (Test-Path -LiteralPath $backupDir)) {
        throw 'Failed publication left staging or backup artifacts.'
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
    if ((Test-Path -LiteralPath $stagingDir) -or (Test-Path -LiteralPath $backupDir)) {
        throw 'Successful publication left staging or backup artifacts.'
    }

    'Atomic figure publication smoke test passed.'
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
