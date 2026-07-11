$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '..\build_figures.ps1')

$unicodeRoot = Join-Path ([System.IO.Path]::GetTempPath()) '科研-native-path-test'
$unicodeChild = Join-Path $unicodeRoot 'build\figure.pdf'
$nativeChild = ConvertTo-NativeRelativeChildPath -Path $unicodeChild -BaseDirectory $unicodeRoot
if ($nativeChild -ne 'build\figure.pdf') {
    throw "Native child path was not reduced to its ASCII-safe relative form: $nativeChild"
}

function Set-ManagedBaseline {
    param(
        [string[]]$Basenames,
        [string]$PdfDirectory,
        [string]$PngDirectory,
        [string[]]$AbsentPaths = @()
    )

    New-Item -ItemType Directory -Force -Path $PdfDirectory, $PngDirectory | Out-Null
    $snapshot = @{}
    foreach ($basename in $Basenames) {
        foreach ($artifact in @(
            @{ Path = Join-Path $PdfDirectory "${basename}.pdf"; Kind = 'pdf' },
            @{ Path = Join-Path $PngDirectory "${basename}.png"; Kind = 'png' }
        )) {
            Remove-Item -LiteralPath $artifact.Path -Force -ErrorAction SilentlyContinue
            if ($AbsentPaths -contains $artifact.Path) {
                $snapshot[$artifact.Path] = $null
            }
            else {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(
                    "old:$($artifact.Kind):${basename}:$([guid]::NewGuid())"
                )
                [System.IO.File]::WriteAllBytes($artifact.Path, $bytes)
                $snapshot[$artifact.Path] = $bytes
            }
        }
    }
    return $snapshot
}

function Assert-ManagedBaseline {
    param([hashtable]$Snapshot)

    foreach ($entry in $Snapshot.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            if (Test-Path -LiteralPath $entry.Key) {
                throw "Previously absent destination now exists: $($entry.Key)"
            }
        }
        else {
            if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)) {
                throw "Prior managed destination is missing: $($entry.Key)"
            }
            $actual = [System.IO.File]::ReadAllBytes($entry.Key)
            if ([Convert]::ToBase64String($actual) -ne [Convert]::ToBase64String($entry.Value)) {
                throw "Managed destination was not restored byte-for-byte: $($entry.Key)"
            }
        }
    }
}

function Assert-TransientDirectoriesAbsent {
    param([string]$BuildWorkDirectory, [string]$BackupDirectory)

    if ((Test-Path -LiteralPath $BuildWorkDirectory) -or (Test-Path -LiteralPath $BackupDirectory)) {
        throw 'Batch left build-work or backup artifacts.'
    }
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jmechplots-atomic-{0}" -f [guid]::NewGuid().ToString('N'))
$buildDirectory = Join-Path $testRoot 'build'
$buildWorkDirectory = Join-Path $buildDirectory 'build-work'
$backupDirectory = Join-Path $buildDirectory 'publication-backup'
$wordDirectory = Join-Path $testRoot 'word-output'
$basenames = @(Get-FigureBasenames)

$successfulBuildAction = {
    param($basename, $batchWorkDirectory)
    Set-Content -LiteralPath (Join-Path $batchWorkDirectory "${basename}.pdf") -Value "new:pdf:${basename}" -NoNewline
    Set-Content -LiteralPath (Join-Path $batchWorkDirectory "${basename}.png") -Value "new:png:${basename}" -NoNewline
}

try {
    $compileBaseline = Set-ManagedBaseline `
        -Basenames $basenames `
        -PdfDirectory $buildDirectory `
        -PngDirectory $wordDirectory
    $compileFailed = $false
    try {
        Invoke-AtomicFigureBatch `
            -Basenames $basenames `
            -BuildWorkDirectory $buildWorkDirectory `
            -BuildParentDirectory $buildDirectory `
            -PdfOutputDirectory $buildDirectory `
            -PngOutputDirectory $wordDirectory `
            -BuildAction {
                param($basename, $batchWorkDirectory)
                Set-Content -LiteralPath (Join-Path $batchWorkDirectory "${basename}.pdf") -Value "new:pdf:${basename}" -NoNewline
                Set-Content -LiteralPath (Join-Path $batchWorkDirectory "${basename}.png") -Value "new:png:${basename}" -NoNewline
                if ($basename -eq $basenames[1]) { throw 'Injected compile/staging failure.' }
            }
    }
    catch { $compileFailed = $true }
    if (-not $compileFailed) { throw 'Compile/staging failure did not propagate.' }
    Assert-ManagedBaseline -Snapshot $compileBaseline
    Assert-TransientDirectoriesAbsent -BuildWorkDirectory $buildWorkDirectory -BackupDirectory $backupDirectory

    $missingPdf = Join-Path $buildDirectory "$($basenames[0]).pdf"
    $missingPng = Join-Path $wordDirectory "$($basenames[0]).png"
    $pdfFailureBaseline = Set-ManagedBaseline `
        -Basenames $basenames `
        -PdfDirectory $buildDirectory `
        -PngDirectory $wordDirectory `
        -AbsentPaths @($missingPdf, $missingPng)
    $pdfReplacementState = [pscustomobject]@{ Attempts = 0 }
    $pdfPublishFailed = $false
    try {
        Invoke-AtomicFigureBatch `
            -Basenames $basenames `
            -BuildWorkDirectory $buildWorkDirectory `
            -BuildParentDirectory $buildDirectory `
            -PdfOutputDirectory $buildDirectory `
            -PngOutputDirectory $wordDirectory `
            -BuildAction $successfulBuildAction `
            -ReplaceAction {
                param($temporaryPath, $finalPath, $replacementIndex)
                $pdfReplacementState.Attempts++
                if ($replacementIndex -eq 1) { throw 'Injected second-PDF publication failure.' }
                Move-Item -LiteralPath $temporaryPath -Destination $finalPath -Force
            }
    }
    catch { $pdfPublishFailed = $true }
    if (-not $pdfPublishFailed -or $pdfReplacementState.Attempts -ne 2) {
        throw 'Second-PDF publication failure was not exercised.'
    }
    Assert-ManagedBaseline -Snapshot $pdfFailureBaseline
    Assert-TransientDirectoriesAbsent -BuildWorkDirectory $buildWorkDirectory -BackupDirectory $backupDirectory

    $pngFailureBaseline = Set-ManagedBaseline `
        -Basenames $basenames `
        -PdfDirectory $buildDirectory `
        -PngDirectory $wordDirectory `
        -AbsentPaths @($missingPdf, $missingPng)
    $pngReplacementState = [pscustomobject]@{ Attempts = 0 }
    $pngPublishFailed = $false
    try {
        Invoke-AtomicFigureBatch `
            -Basenames $basenames `
            -BuildWorkDirectory $buildWorkDirectory `
            -BuildParentDirectory $buildDirectory `
            -PdfOutputDirectory $buildDirectory `
            -PngOutputDirectory $wordDirectory `
            -BuildAction $successfulBuildAction `
            -ReplaceAction {
                param($temporaryPath, $finalPath, $replacementIndex)
                $pngReplacementState.Attempts++
                if ($replacementIndex -eq 9) { throw 'Injected second-PNG publication failure.' }
                Move-Item -LiteralPath $temporaryPath -Destination $finalPath -Force
            }
    }
    catch { $pngPublishFailed = $true }
    if (-not $pngPublishFailed -or $pngReplacementState.Attempts -ne 10) {
        throw 'Second-PNG publication failure was not exercised after all PDF replacements.'
    }
    Assert-ManagedBaseline -Snapshot $pngFailureBaseline
    Assert-TransientDirectoriesAbsent -BuildWorkDirectory $buildWorkDirectory -BackupDirectory $backupDirectory

    Invoke-AtomicFigureBatch `
        -Basenames $basenames `
        -BuildWorkDirectory $buildWorkDirectory `
        -BuildParentDirectory $buildDirectory `
        -PdfOutputDirectory $buildDirectory `
        -PngOutputDirectory $wordDirectory `
        -BuildAction $successfulBuildAction

    foreach ($basename in $basenames) {
        if ((Get-Content -Raw -LiteralPath (Join-Path $buildDirectory "${basename}.pdf")) -ne "new:pdf:${basename}") {
            throw "Successful batch did not publish PDF: $basename"
        }
        if ((Get-Content -Raw -LiteralPath (Join-Path $wordDirectory "${basename}.png")) -ne "new:png:${basename}") {
            throw "Successful batch did not publish PNG: $basename"
        }
    }
    $buildChildren = @(Get-ChildItem -LiteralPath $buildDirectory -Force)
    $wordChildren = @(Get-ChildItem -LiteralPath $wordDirectory -Force)
    if ($buildChildren.Count -ne 8 -or @($buildChildren | Where-Object Extension -ne '.pdf').Count -ne 0) {
        throw 'Successful build directory is not exactly the eight final PDFs.'
    }
    if ($wordChildren.Count -ne 8 -or @($wordChildren | Where-Object Extension -ne '.png').Count -ne 0) {
        throw 'Successful Word directory is not exactly the eight final PNGs.'
    }
    Assert-TransientDirectoriesAbsent -BuildWorkDirectory $buildWorkDirectory -BackupDirectory $backupDirectory

    $outside = Join-Path $testRoot 'outside'
    New-Item -ItemType Directory -Force -Path $outside | Out-Null
    Set-Content -LiteralPath (Join-Path $outside 'sentinel') -Value 'keep'
    $unsafeRejected = $false
    try { Remove-SafeChildDirectory -Directory $outside -ExpectedParentDirectory $buildDirectory }
    catch { $unsafeRejected = $true }
    if (-not $unsafeRejected -or -not (Test-Path -LiteralPath (Join-Path $outside 'sentinel'))) {
        throw 'Safe path containment did not reject an outside directory.'
    }

    'Atomic PDF and PNG publication smoke test passed.'
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
