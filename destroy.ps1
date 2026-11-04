<#
.SYNOPSIS
    Script rápido para destruir todos los recursos en AWS y evitar cobros ($0.00).

.EXAMPLE
    .\destroy.ps1
#>

& "$PSScriptRoot\deploy.ps1" -Destroy
