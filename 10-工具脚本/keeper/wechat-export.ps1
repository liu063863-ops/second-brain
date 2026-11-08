<#
.SYNOPSIS
    一键导出本机微信聊天记录（chatlog-keeper，纯本地、不联网）。
    流程：probe → 取 key（passive/active/targeted）→ 导出 JSON+HTML。

.DESCRIPTION
    -Method passive   只读内存扫 key，风险最低（微信 4.1.10.31+ 多半失败）
    -Method active    官方 CLI 的调试器流程（自动选 oracle）
    -Method targeted  手工指定 oracle 库 + Weixin.dll 的调试器流程（多账号推荐，最稳）
    -Method auto      passive 失败自动转 active

.EXAMPLE
    .\wechat-export.ps1 -ProbeOnly
    .\wechat-export.ps1 -Method targeted -Days 3650
    .\wechat-export.ps1 -Method passive
#>
[CmdletBinding()]
param(
    [int]$Days = 3650,
    [string]$Out = "",
    [ValidateSet('auto', 'passive', 'active', 'targeted')] [string]$Method = 'auto',
    [string]$DataRoot = "",
    [string]$OracleDb = "",
    [string]$WeixinDll = "",
    [switch]$ProbeOnly
)

$ErrorActionPreference = 'Continue'
$tools = Split-Path $PSScriptRoot -Parent
$py = Join-Path $tools 'keeper-venv\Scripts\python.exe'
if (-not $Out) { $Out = Join-Path (Split-Path $tools -Parent) 'wechat-export' }
if (-not $DataRoot) { $DataRoot = Join-Path $env:USERPROFILE 'Documents\xwechat_files' }

$env:PYTHONIOENCODING = 'utf-8'
$env:PIP_CACHE_DIR = Join-Path $tools 'pip-cache'
$env:TMP = Join-Path $tools 'tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null

function Ok($m) { Write-Host "`n[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "`n[!] $m" -ForegroundColor Yellow }
function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Fail($m) { Write-Host "`n[X] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $py)) { Fail "找不到运行环境：$py" }

# 自动挑 oracle：message_*.db 总量最大的账号目录（多账号时最可能是主号）
function Get-DefaultOracleDb {
    if (-not (Test-Path $DataRoot)) { return "" }
    $best = Get-ChildItem -LiteralPath $DataRoot -Directory -Filter 'wxid_*' -ErrorAction SilentlyContinue |
        ForEach-Object {
            $sum = (Get-ChildItem -LiteralPath (Join-Path $_.FullName 'db_storage\message') -File -Filter 'message_*.db' -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notmatch '_fts|_resource' } | Measure-Object Length -Sum).Sum
            [pscustomobject]@{ Dir = $_.FullName; MB = [math]::Round($sum / 1MB, 2) }
        } | Sort-Object MB -Descending
    if (-not $best) { return "" }
    return (Join-Path $best[0].Dir 'db_storage\message\message_0.db')
}

$arguments = @()
if ($DataRoot) { $arguments += @('--data-root', $DataRoot) }

Step '0. 环境检查'
$wx = Get-Process -Name 'Weixin', 'WeChat' -ErrorAction SilentlyContinue
if ($wx) {
    Write-Host ("  微信进程：PID " + ($wx.Id -join ', '))
} else {
    Write-Host '  微信当前未运行。' -ForegroundColor Yellow
    Write-Host '  passive 需要微信已登录；active / targeted 会自己拉起被调试的微信并等待扫码。'
}
if (-not $OracleDb) { $OracleDb = Get-DefaultOracleDb }
if ($OracleDb) { Write-Host "  oracle 库：$OracleDb" }
if (-not $WeixinDll) {
    $cand = Get-ChildItem 'C:\Program Files\Tencent\Weixin' -Recurse -Filter 'Weixin.dll' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($cand) { $WeixinDll = $cand.FullName }
}
if ($WeixinDll) { Write-Host "  Weixin.dll：$WeixinDll" }

Step '1. 探测数据与 key 状态'
& $py -m chatlog_keeper.cli probe 2>&1
if ($ProbeOnly) { Ok 'probe 完成（-ProbeOnly）'; exit 0 }

# ---------------- 取 key ----------------
Step "2. 取解密 key（method=$Method）"

if ($Method -eq 'targeted') {
    if (-not $OracleDb -or -not (Test-Path $OracleDb)) { Fail 'targeted 模式需要有效的 -OracleDb（目标账号的 message_0.db）' }
    $script = Join-Path $tools 'downloaded\chatlog-keeper\chatlog_keeper\scripts\windows_wechat_get_key.ps1'
    if (-not (Test-Path $script)) { Fail "找不到底层取 key 脚本：$script" }
    Warn '会先关闭当前微信，再启动一个被调试的微信实例；请在那个窗口扫码登录。'
    $psArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script, '-DbPath', $OracleDb)
    if ($WeixinDll) { $psArgs += @('-WeixinDllPath', $WeixinDll) }
    $raw = & powershell.exe @psArgs 2>&1 | Out-String
    Write-Host $raw
    $m = [regex]::Match($raw, 'master key:\s*([0-9a-fA-F]{16,128})')
    if (-not $m.Success) { Fail '未捕获到 master key。把上面的完整输出发我。' }
    $m.Groups[1].Value | & $py -m chatlog_keeper.cli set-key --source wechat --key-stdin 2>&1
    if ($LASTEXITCODE -ne 0) { Fail 'set-key 失败' }
    Ok 'key 已获取并缓存'
}
else {
    $keyArgs = @('-m', 'chatlog_keeper.cli', 'extract-key', '--source', 'wechat', '--method', $Method) + $arguments
    & $py @keyArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Warn '自动取 key 失败。建议改用：.\wechat-export.ps1 -Method targeted'
        Write-Host '  常见原因：微信没登录 / 新版 key 不在明文内存 / 多账号 oracle 选错库'
        exit 1
    }
    Ok 'key 已获取并缓存'
}

# ---------------- 导出 ----------------
Step "3. 导出最近 $Days 天聊天记录"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$expArgs = @('-m', 'chatlog_keeper.cli', 'wechat', '--days', "$Days", '--out', $Out) + $arguments
& $py @expArgs 2>&1
if ($LASTEXITCODE -ne 0) { Fail '导出失败，把上面的报错发我' }

Step '4. 产物'
Get-ChildItem -LiteralPath $Out -File -ErrorAction SilentlyContinue | Sort-Object Name |
    Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 2) } }, LastWriteTime |
    Format-Table -AutoSize

Ok "导出完成：$Out"
Write-Host '  下一步：把这个目录路径发我，我转成蒸馏素材（self-said / fingerprint / jsonl）。'
