from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SVG_PATH = PROJECT_ROOT / "assets" / "fin_alert_logo.svg"
ICON_PATH = PROJECT_ROOT / "assets" / "FinAlert.ico"
RENDER_SIZE = 512
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    if not SVG_PATH.is_file():
        raise FileNotFoundError(f"FinAlert SVG logo not found: {SVG_PATH}")

    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        raise ValueError(f"Could not read the SVG logo: {SVG_PATH}")

    image = QImage(
        QSize(RENDER_SIZE, RENDER_SIZE),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not create the temporary PNG image.")

    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Could not render the SVG logo as PNG.")
        png_bytes = bytes(buffer.data())
    finally:
        buffer.close()

    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(png_bytes)) as rendered_logo:
        rendered_logo.save(
            ICON_PATH,
            format="ICO",
            sizes=ICON_SIZES,
        )

    print(f"Created Windows icon: {ICON_PATH}")


if __name__ == "__main__":
    main()
