#!/usr/bin/env bash
# Empacota os fontes para build no Windows.
# Uso: bash package.sh
# Resultado: ConsultaCPF_build.zip  →  envie para o Windows e rode build.bat

set -euo pipefail

DIST="ConsultaCPF_build"
ZIP="${DIST}.zip"

echo "Criando pacote de build para Windows..."

rm -rf "/tmp/${DIST}"
mkdir -p "/tmp/${DIST}"

# Arquivos do app
cp main.py app_gui.py api_client.py cpf_utils.py ConsultaCPF.spec build.bat \
   .env.example requirements.txt "/tmp/${DIST}/"

# Cria um .env vazio se não existir (para não esquecer)
if [ ! -f ".env" ]; then
    cp .env.example "/tmp/${DIST}/.env"
else
    cp .env "/tmp/${DIST}/.env"
fi

cd /tmp
zip -r "${ZIP}" "${DIST}/" > /dev/null
mv "${ZIP}" "${OLDPWD}/"

echo ""
echo "Pacote criado: ${ZIP}"
echo ""
echo "No Windows:"
echo "  1. Extraia o zip"
echo "  2. Execute build.bat  (Python 3.10+ deve estar instalado)"
echo "  3. O executável estará em dist\\ConsultaCPF.exe"
echo "  4. Coloque o .env preenchido na mesma pasta do .exe"
echo ""
