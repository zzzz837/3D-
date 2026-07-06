# 3D Layout Editor — Unified build script
# Usage: .\build.ps1
# Always outputs to release\IrregularShapedLayout\

$ErrorActionPreference = "Continue"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

Write-Host "=== 3D拟物Layout编辑器 — 构建 ===" -ForegroundColor Cyan

# Check if old exe is running
$running = Get-Process -Name "IrregularShapedLayout" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "检测到旧版exe正在运行，请先关闭后重试" -ForegroundColor Yellow
    Write-Host "  进程ID: $($running.Id)" -ForegroundColor Yellow
    $answer = Read-Host "是否尝试强制关闭? (y/n)"
    if ($answer -eq 'y') {
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
    } else {
        Write-Host "请手动关闭exe后重新运行此脚本" -ForegroundColor Red
        exit 1
    }
}

# Also check QtWebEngineProcess
$qt = Get-Process -Name "QtWebEngineProcess" -ErrorAction SilentlyContinue
if ($qt) {
    Write-Host "检测到QtWebEngineProcess，关闭中..." -ForegroundColor Yellow
    $qt | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Clean old build artifacts
Remove-Item "$project\release" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$project\build_temp" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "开始PyInstaller打包..." -ForegroundColor Cyan
pyinstaller IrregularShapedLayout.spec --noconfirm --distpath "$project\release" --workpath "$project\build_temp"

if (Test-Path "$project\release\IrregularShapedLayout\IrregularShapedLayout.exe") {
    Remove-Item "$project\build_temp" -Recurse -Force -ErrorAction SilentlyContinue
    $exe = Get-Item "$project\release\IrregularShapedLayout\IrregularShapedLayout.exe"
    Write-Host "构建成功!" -ForegroundColor Green
    Write-Host "  $($exe.FullName)" -ForegroundColor Green
    Write-Host "  大小: $([math]::Round($exe.Length/1MB,1))MB" -ForegroundColor Green
    Write-Host "  时间: $($exe.LastWriteTime)" -ForegroundColor Green
    Write-Host ""
    Write-Host "双击运行: release\IrregularShapedLayout\IrregularShapedLayout.exe" -ForegroundColor White
} else {
    Write-Host "构建失败，请检查上方错误信息" -ForegroundColor Red
}
