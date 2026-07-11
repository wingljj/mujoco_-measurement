[CmdletBinding()]
param(
    [switch]$SkipData
)

$ErrorActionPreference = 'Stop'

function Get-RepositoryRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-FigureBasenames {
    return @(
        'fig01_method_pipeline',
        'fig02_workspace_multiview',
        'fig03_transport_sequence',
        'fig04_case_study',
        'fig05_ablation_comparison',
        'fig06_error_tilt_margin',
        'fig07_dynamic_metrics',
        'fig08_baseline_comparison'
    )
}

function Test-PdfFontsEmbedded {
    param(
        [Parameter(Mandatory)]
        [string]$PdfFontsOutput
    )

    $fontRows = @(
        $PdfFontsOutput -split "`r?`n" |
            Where-Object { $_ -match '^\S' -and $_ -notmatch '^name\s' -and $_ -notmatch '^-+\s' }
    )
    if ($fontRows.Count -eq 0) {
        return $false
    }

    foreach ($row in $fontRows) {
        $columns = @($row -split '\s+' | Where-Object { $_ })
        if ($columns.Count -lt 5 -or $columns[$columns.Count - 5] -ne 'yes') {
            return $false
        }
    }
    return $true
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Reset-StagingDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$StagingDirectory,

        [Parameter(Mandatory)]
        [string]$ExpectedParentDirectory
    )

    $parentPath = [System.IO.Path]::GetFullPath($ExpectedParentDirectory).TrimEnd('\', '/')
    $stagingPath = [System.IO.Path]::GetFullPath($StagingDirectory)
    $parentPrefix = "${parentPath}$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $stagingPath.StartsWith($parentPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to reset staging directory outside its expected parent: $stagingPath"
    }

    if (Test-Path -LiteralPath $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $stagingPath | Out-Null
}

function Publish-StagedFigures {
    param(
        [Parameter(Mandatory)]
        [string[]]$Basenames,

        [Parameter(Mandatory)]
        [string]$StagingDirectory,

        [Parameter(Mandatory)]
        [string]$OutputDirectory
    )

    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $publicationToken = [guid]::NewGuid().ToString('N')
    $pendingFiles = @()

    try {
        foreach ($basename in $Basenames) {
            $sourcePath = Join-Path $StagingDirectory "${basename}.png"
            $temporaryPath = Join-Path $OutputDirectory ".${basename}.${publicationToken}.tmp.png"
            Copy-Item -LiteralPath $sourcePath -Destination $temporaryPath -Force
            $pendingFiles += [pscustomobject]@{
                TemporaryPath = $temporaryPath
                FinalPath = Join-Path $OutputDirectory "${basename}.png"
            }
        }

        foreach ($pendingFile in $pendingFiles) {
            Move-Item `
                -LiteralPath $pendingFile.TemporaryPath `
                -Destination $pendingFile.FinalPath `
                -Force
        }
    }
    finally {
        foreach ($pendingFile in $pendingFiles) {
            Remove-Item -LiteralPath $pendingFile.TemporaryPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-AtomicFigureBatch {
    param(
        [Parameter(Mandatory)]
        [string[]]$Basenames,

        [Parameter(Mandatory)]
        [string]$StagingDirectory,

        [Parameter(Mandatory)]
        [string]$StagingParentDirectory,

        [Parameter(Mandatory)]
        [string]$OutputDirectory,

        [Parameter(Mandatory)]
        [scriptblock]$BuildAction
    )

    Reset-StagingDirectory `
        -StagingDirectory $StagingDirectory `
        -ExpectedParentDirectory $StagingParentDirectory

    foreach ($basename in $Basenames) {
        & $BuildAction $basename $StagingDirectory
    }

    foreach ($basename in $Basenames) {
        $stagedPngPath = Join-Path $StagingDirectory "${basename}.png"
        if (-not (Test-Path -LiteralPath $stagedPngPath -PathType Leaf)) {
            throw "Batch did not produce current staged PNG: $stagedPngPath"
        }
    }

    Publish-StagedFigures `
        -Basenames $Basenames `
        -StagingDirectory $StagingDirectory `
        -OutputDirectory $OutputDirectory
}

function Invoke-FigureBuild {
    param(
        [switch]$SkipDataPreparation
    )

    $repoRoot = Get-RepositoryRoot
    $figureDir = Join-Path $repoRoot 'figures\pgfplots'
    $buildDir = Join-Path $figureDir 'build'
    $stagingDir = Join-Path $buildDir 'word-staging'
    $wordOutputDir = Join-Path $repoRoot 'outputs\word_figures'

    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

    if (-not $SkipDataPreparation) {
        Push-Location $repoRoot
        try {
            Invoke-NativeCommand -Command 'conda' -Arguments @(
                'run', '-n', 'mujoco', 'python', 'scripts/prepare_pgfplots_data.py'
            )
        }
        finally {
            Pop-Location
        }
    }

    Push-Location $figureDir
    try {
        Invoke-AtomicFigureBatch `
            -Basenames @(Get-FigureBasenames) `
            -StagingDirectory $stagingDir `
            -StagingParentDirectory $buildDir `
            -OutputDirectory $wordOutputDir `
            -BuildAction {
                param($basename, $batchStagingDirectory)

                $texPath = Join-Path $figureDir "${basename}.tex"
                $pdfPath = Join-Path $buildDir "${basename}.pdf"
                $pngPrefix = Join-Path $batchStagingDirectory $basename
                $pngPath = "${pngPrefix}.png"

                if (-not (Test-Path -LiteralPath $texPath -PathType Leaf)) {
                    throw "Missing figure source: $texPath"
                }

                Remove-Item -LiteralPath $pdfPath, $pngPath -Force -ErrorAction SilentlyContinue
                Invoke-NativeCommand -Command 'latexmk' -Arguments @(
                    '-xelatex',
                    '-interaction=nonstopmode',
                    '-halt-on-error',
                    '-file-line-error',
                    "-outdir=$buildDir",
                    $texPath
                )
                if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
                    throw "latexmk completed without producing: $pdfPath"
                }

                Invoke-NativeCommand -Command 'pdfinfo' -Arguments @($pdfPath)

                $fontReport = (& pdffonts $pdfPath 2>&1 | Out-String)
                if ($LASTEXITCODE -ne 0) {
                    throw "pdffonts failed with exit code ${LASTEXITCODE}: $pdfPath"
                }
                Write-Host $fontReport
                if (-not (Test-PdfFontsEmbedded -PdfFontsOutput $fontReport)) {
                    throw "PDF contains a non-embedded font or no fonts: $pdfPath"
                }

                Invoke-NativeCommand -Command 'pdftoppm' -Arguments @(
                    '-png', '-r', '600', '-singlefile', $pdfPath, $pngPrefix
                )
                if (-not (Test-Path -LiteralPath $pngPath -PathType Leaf)) {
                    throw "pdftoppm completed without producing: $pngPath"
                }
        }
    }
    finally {
        Pop-Location
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-FigureBuild -SkipDataPreparation:$SkipData
}
