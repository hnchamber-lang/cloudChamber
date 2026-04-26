# run_verify.ps1 — PowerShell wrapper for verify_integrity.py
#
# Use this when running from PowerShell (or piping output into a log
# file) and you need UTF-8 output instead of PowerShell's default
# UTF-16 LE.
#
# Examples:
#   .\run_verify.ps1                                # interactive
#   .\run_verify.ps1 *> verify_20260426.log         # capture stdout+stderr as UTF-8

$ErrorActionPreference = 'Stop'

# Force the .NET / PowerShell / Python pipeline to UTF-8.
[Console]::OutputEncoding         = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding          = [System.Text.UTF8Encoding]::new()
$OutputEncoding                   = [System.Text.UTF8Encoding]::new()
$PSDefaultParameterValues['Out-File:Encoding']  = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
$env:PYTHONIOENCODING             = 'utf-8'
$env:PYTHONUTF8                   = '1'

Set-Location -LiteralPath $PSScriptRoot
& python verify_integrity.py @args
