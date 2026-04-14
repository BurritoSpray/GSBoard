#!/usr/bin/env bash
set -euo pipefail

APP_NAME="GSBoard"
APP_DIR="AppDir"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

# Check for required tools
for cmd in python3 pip appimagetool; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: '$cmd' is not installed."
        if [ "$cmd" = "appimagetool" ]; then
            echo "Download it from: https://github.com/AppImage/appimagetool/releases"
            echo "  chmod +x appimagetool-*.AppImage && sudo mv appimagetool-*.AppImage /usr/local/bin/appimagetool"
        fi
        exit 1
    fi
done

echo "==> Cleaning previous build..."
rm -rf "$APP_DIR" dist build *.egg-info

echo "==> Installing PyInstaller..."
pip install --quiet pyinstaller

echo "==> Freezing application with PyInstaller..."
pyinstaller \
    --noconfirm \
    --name gsboard \
    --collect-all gsboard \
    --hidden-import pynput.keyboard._xorg \
    --hidden-import pynput.mouse._xorg \
    gsboard/main.py

echo "==> Building AppDir structure..."
mkdir -p "$APP_DIR/usr/bin" \
         "$APP_DIR/usr/share/applications" \
         "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

# Move PyInstaller output into AppDir
cp -a dist/gsboard/* "$APP_DIR/usr/bin/"

# Desktop file and icon
cp gsboard.desktop "$APP_DIR/"
cp gsboard.desktop "$APP_DIR/usr/share/applications/"

cp gsboard/resources/gsboard.png "$APP_DIR/gsboard.png"
cp gsboard/resources/gsboard.png "$APP_DIR/usr/share/icons/hicolor/256x256/apps/gsboard.png"
ln -sf gsboard.png "$APP_DIR/.DirIcon"

# AppRun launcher
cat > "$APP_DIR/AppRun" << 'APPRUN'
#!/usr/bin/env bash
SELF="$(readlink -f "$0")"
HERE="${SELF%/*}"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH:-}"
exec "${HERE}/usr/bin/gsboard" "$@"
APPRUN
chmod +x "$APP_DIR/AppRun"

echo "==> Creating AppImage..."
ARCH="$(uname -m)" appimagetool "$APP_DIR" "${APP_NAME}-$(uname -m).AppImage"

echo "==> Done! Output: ${APP_NAME}-$(uname -m).AppImage"
