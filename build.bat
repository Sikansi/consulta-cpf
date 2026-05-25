@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
title Build - Consulta CPF

echo ================================================
echo   Build - Consulta CPF
echo ================================================
echo.

REM --- Verifica Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo.
    echo Instale em: https://python.org
    echo Na instalacao, marque: "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo Python encontrado: %PY_VER%
echo.

REM --- Instala dependências ---
echo [1/3] Instalando dependencias...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller requests python-dotenv --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo       OK.
echo.

REM --- Limpa builds anteriores ---
echo [2/3] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo       OK.
echo.

REM --- Compila ---
echo [3/3] Compilando executavel...
pyinstaller ConsultaCPF.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilacao. Leia as mensagens acima.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   CONCLUIDO!
echo.
echo   Executavel: dist\ConsultaCPF.exe
echo.
echo   IMPORTANTE: coloque o arquivo .env na mesma
echo   pasta do ConsultaCPF.exe antes de usar.
echo ================================================
echo.
pause
