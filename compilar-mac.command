#!/bin/bash
# ============================================================
#  Compila o Prospector no macOS.
#  Resultado: backend/dist/Prospector.app
#
#  Rode ESTE arquivo num Mac. O PyInstaller nao compila para
#  outro sistema: o .app so pode ser gerado num Mac, assim como
#  o .exe so pode ser gerado no Windows.
#
#  Para rodar: de dois cliques neste arquivo, ou no Terminal:
#      chmod +x compilar-mac.command && ./compilar-mac.command
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo "  Compilando o Prospector para macOS"
echo "  ----------------------------------"
echo

if [[ "$(uname)" != "Darwin" ]]; then
    echo "  ERRO: este script precisa rodar num Mac."
    echo "  No Windows use compilar.bat."
    exit 1
fi

# --- Python ---------------------------------------------------------------
if [[ ! -x "backend/.venv/bin/python" ]]; then
    echo "  [1/4] Preparando o Python..."
    if ! command -v python3 >/dev/null; then
        echo "  ERRO: python3 nao encontrado. Instale em python.org."
        exit 1
    fi
    python3 -m venv backend/.venv
    backend/.venv/bin/python -m pip install --quiet --upgrade pip
    backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt pyinstaller
else
    echo "  [1/4] Python ja preparado."
fi

# --- Interface ------------------------------------------------------------
echo "  [2/4] Exportando a interface..."
if ! command -v npm >/dev/null; then
    echo "  ERRO: npm nao encontrado. Instale o Node em nodejs.org."
    exit 1
fi
pushd frontend >/dev/null
[[ -d node_modules ]] || npm install --no-audit --no-fund --silent
PROSPECTOR_DESKTOP=1 npx next build
popd >/dev/null

# --- Aplicativo -----------------------------------------------------------
echo "  [3/4] Empacotando o aplicativo..."
pushd backend >/dev/null
.venv/bin/python -m PyInstaller packaging/Prospector-mac.spec --noconfirm --clean
popd >/dev/null

# --- Assinatura local -----------------------------------------------------
# Sem certificado pago, uma assinatura ad-hoc ainda evita que o Gatekeeper
# recuse o app de cara em Apple Silicon, onde binario sem assinatura nenhuma
# nao executa. Nao remove o aviso de "desenvolvedor nao identificado".
echo "  [4/5] Assinando localmente (ad-hoc)..."
codesign --force --deep --sign - backend/dist/Prospector.app 2>/dev/null || \
    echo "      (codesign indisponivel - o app ainda funciona)"

# --- Imagem de disco ------------------------------------------------------
# O equivalente no Mac ao instalador de arquivo unico do Windows: um .dmg que
# a pessoa baixa, abre, e arrasta o app para Aplicativos. Sem isso a entrega
# seria uma pasta .app, que quebra se for zipada errado.
echo "  [5/5] Montando o .dmg..."
DMG="backend/dist/Prospector.dmg"
STAGE="$(mktemp -d)"
cp -R backend/dist/Prospector.app "$STAGE/"
# O atalho para /Applications e o que torna o "arraste para ca" obvio ao abrir.
ln -s /Applications "$STAGE/Aplicativos"
rm -f "$DMG"
if hdiutil create -volname "Prospector" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null 2>&1; then
    echo "      ok"
else
    echo "      (hdiutil falhou - use o Prospector.app direto)"
    DMG=""
fi
rm -rf "$STAGE"

echo
echo "  Pronto."
echo
if [[ -n "$DMG" ]]; then
    echo "    Para dar a alguem:  $DMG"
    echo "    (arquivo unico - abre e arrasta para Aplicativos)"
    echo
fi
echo "    O aplicativo:       backend/dist/Prospector.app"
echo
echo "  Na primeira vez o macOS vai dizer que o app e de um"
echo "  desenvolvedor nao identificado. Clique com o botao direito"
echo "  no app e escolha Abrir - so precisa fazer isso uma vez."
echo
