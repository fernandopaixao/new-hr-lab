@echo off
rem Atalho para o instalador do Windows: roda o install.ps1 sem exigir mudanca
rem na politica de execucao do PowerShell. Aceita as mesmas opcoes, ex.: install.cmd -Sim
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %ERRORLEVEL%
