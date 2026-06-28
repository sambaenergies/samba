param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

$pythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

try {
    Get-Command $pythonBin -ErrorAction Stop | Out-Null
}
catch {
    Write-Error "[profiling] ERROR: python interpreter not found."
    exit 127
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$outputRoot = if ($env:PROFILE_OUTPUT_ROOT) { $env:PROFILE_OUTPUT_ROOT } else { "artifacts/test-profiling" }
$runDir = Join-Path $outputRoot $timestamp
$rawDir = Join-Path $runDir "raw"
$reportDir = Join-Path $runDir "reports"

New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

$junitXml = Join-Path $rawDir "junit.xml"
$pytestOutput = Join-Path $rawDir "pytest_output.txt"
$reportJson = Join-Path $reportDir "test_timing_report.json"
$summaryMd = Join-Path $reportDir "test_timing_summary.md"

Write-Host "[profiling] Running full pytest suite (including benchmark tests)."
Write-Host "[profiling] Output directory: $runDir"

$pytestCallArgs = @(
    "-m", "pytest",
    "-o", "addopts=",
    "tests",
    "--junit-xml", $junitXml,
    "--durations=0",
    "--durations-min=0",
    "-ra"
) + $PytestArgs

& $pythonBin @pytestCallArgs 2>&1 | Tee-Object -FilePath $pytestOutput
$pytestExit = $LASTEXITCODE

Write-Host "[profiling] Running timing analyzer."
$analyzerArgs = @(
    "scripts/analyze_test_timings.py",
    "--junit-xml", $junitXml,
    "--pytest-output", $pytestOutput,
    "--output-json", $reportJson,
    "--output-summary", $summaryMd
)
& $pythonBin @analyzerArgs
$analyzerExit = $LASTEXITCODE

Write-Host "[profiling] Artifacts written to: $runDir"
if ($pytestExit -ne 0) {
    Write-Host "[profiling] pytest exited with code $pytestExit"
    exit $pytestExit
}
if ($analyzerExit -ne 0) {
    Write-Host "[profiling] analyzer exited with code $analyzerExit"
    exit $analyzerExit
}
Write-Host "[profiling] Completed successfully."
