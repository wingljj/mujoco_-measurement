param(
    [string]$OutputDir = "output/pdf"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$out = Join-Path $repo $OutputDir
$tmp = Join-Path $repo "tmp/pdfs/manuscript"
$pdf = Join-Path $out "theodolite_station_transfer_manuscript.pdf"

New-Item -ItemType Directory -Force -Path $out, $tmp | Out-Null

Push-Location (Join-Path $repo "docs")
try {
    pandoc "theory_and_simulation.md" `
        --from=markdown+tex_math_dollars `
        --to=latex `
        --standalone `
        --metadata-file="manuscript-metadata.yaml" `
        --lua-filter="manuscript-filter.lua" `
        --include-in-header="manuscript-header.tex" `
        --resource-path=".;.." `
        --pdf-engine=xelatex `
        --wrap=preserve `
        --output=$pdf
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pdf)) {
        throw "Pandoc/XeLaTeX manuscript build failed."
    }
}
finally {
    Pop-Location
}

Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Built: $pdf"
