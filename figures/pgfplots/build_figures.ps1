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

function ConvertTo-NativeRelativeChildPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$BaseDirectory
    )

    $basePath = [System.IO.Path]::GetFullPath($BaseDirectory).TrimEnd('\', '/')
    $childPath = [System.IO.Path]::GetFullPath($Path)
    $basePrefix = "${basePath}$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $childPath.StartsWith($basePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Native-tool path is outside its working directory: $childPath"
    }
    return $childPath.Substring($basePrefix.Length)
}

function Remove-SafeChildDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$Directory,

        [Parameter(Mandatory)]
        [string]$ExpectedParentDirectory
    )

    $parentPath = [System.IO.Path]::GetFullPath($ExpectedParentDirectory).TrimEnd('\', '/')
    $childPath = [System.IO.Path]::GetFullPath($Directory)
    $parentPrefix = "${parentPath}$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $childPath.StartsWith($parentPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove directory outside its expected parent: $childPath"
    }

    if (Test-Path -LiteralPath $childPath) {
        Remove-Item -LiteralPath $childPath -Recurse -Force
    }
}

function Reset-StagingDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$StagingDirectory,

        [Parameter(Mandatory)]
        [string]$ExpectedParentDirectory
    )

    Remove-SafeChildDirectory `
        -Directory $StagingDirectory `
        -ExpectedParentDirectory $ExpectedParentDirectory
    New-Item -ItemType Directory -Force -Path $StagingDirectory | Out-Null
}

function Publish-StagedFigures {
    param(
        [Parameter(Mandatory)]
        [string[]]$Basenames,

        [Parameter(Mandatory)]
        [string]$StagingDirectory,

        [Parameter(Mandatory)]
        [string]$OutputDirectory,

        [Parameter(Mandatory)]
        [string]$BackupDirectory,

        [Parameter()]
        [scriptblock]$ReplaceAction
    )

    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $publicationToken = [guid]::NewGuid().ToString('N')
    $pendingFiles = @()
    $destinationRecords = @()

    try {
        foreach ($basename in $Basenames) {
            $finalPath = Join-Path $OutputDirectory "${basename}.png"
            if ((Test-Path -LiteralPath $finalPath) -and
                -not (Test-Path -LiteralPath $finalPath -PathType Leaf)) {
                throw "Managed publication destination is not a file: $finalPath"
            }

            $destinationExisted = Test-Path -LiteralPath $finalPath -PathType Leaf
            $backupPath = Join-Path $BackupDirectory "${basename}.png"
            if ($destinationExisted) {
                Copy-Item -LiteralPath $finalPath -Destination $backupPath -Force
            }
            $destinationRecords += [pscustomobject]@{
                FinalPath = $finalPath
                Existed = $destinationExisted
                BackupPath = $backupPath
            }

            $sourcePath = Join-Path $StagingDirectory "${basename}.png"
            $temporaryPath = Join-Path $OutputDirectory ".${basename}.${publicationToken}.tmp.png"
            Copy-Item -LiteralPath $sourcePath -Destination $temporaryPath -Force
            $pendingFiles += [pscustomobject]@{
                TemporaryPath = $temporaryPath
                FinalPath = $finalPath
            }
        }

        for ($index = 0; $index -lt $pendingFiles.Count; $index++) {
            $pendingFile = $pendingFiles[$index]
            if ($ReplaceAction) {
                & $ReplaceAction $pendingFile.TemporaryPath $pendingFile.FinalPath $index
            }
            else {
                Move-Item `
                    -LiteralPath $pendingFile.TemporaryPath `
                    -Destination $pendingFile.FinalPath `
                    -Force
            }
        }
    }
    catch {
        $publicationError = $_
        $rollbackErrors = @()
        foreach ($destinationRecord in $destinationRecords) {
            try {
                if ($destinationRecord.Existed) {
                    Copy-Item `
                        -LiteralPath $destinationRecord.BackupPath `
                        -Destination $destinationRecord.FinalPath `
                        -Force
                }
                else {
                    if (Test-Path -LiteralPath $destinationRecord.FinalPath) {
                        Remove-Item -LiteralPath $destinationRecord.FinalPath -Force
                    }
                }
            }
            catch {
                $rollbackErrors += $_.Exception.Message
            }
        }

        if ($rollbackErrors.Count -gt 0) {
            throw "Publication failed and rollback was incomplete. Original: $publicationError Rollback: $($rollbackErrors -join '; ')"
        }
        throw $publicationError
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
        [scriptblock]$BuildAction,

        [Parameter()]
        [scriptblock]$ReplaceAction
    )

    $backupDirectory = Join-Path $StagingParentDirectory 'word-publication-backup'
    try {
        Reset-StagingDirectory `
            -StagingDirectory $StagingDirectory `
            -ExpectedParentDirectory $StagingParentDirectory
        Reset-StagingDirectory `
            -StagingDirectory $backupDirectory `
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
            -OutputDirectory $OutputDirectory `
            -BackupDirectory $backupDirectory `
            -ReplaceAction $ReplaceAction
    }
    finally {
        try {
            Remove-SafeChildDirectory `
                -Directory $StagingDirectory `
                -ExpectedParentDirectory $StagingParentDirectory
        }
        finally {
            Remove-SafeChildDirectory `
                -Directory $backupDirectory `
                -ExpectedParentDirectory $StagingParentDirectory
        }
    }
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
                $nativePdfPath = ConvertTo-NativeRelativeChildPath `
                    -Path $pdfPath `
                    -BaseDirectory $figureDir
                $nativePngPrefix = ConvertTo-NativeRelativeChildPath `
                    -Path $pngPrefix `
                    -BaseDirectory $figureDir

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
                    '-png', '-r', '600', '-singlefile', $nativePdfPath, $nativePngPrefix
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
