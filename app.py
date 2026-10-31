"""Start the local desktop GUI. No network calls are made by the application."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from nuclei.gui import MainWindow

def main():
    app=QApplication(sys.argv)
    app.setApplicationName('BreaKHis Nuclei Explorer')
    (Path(__file__).parent/'results').mkdir(exist_ok=True)
    window=MainWindow(); window.show()
    sys.exit(app.exec())

if __name__=='__main__': main()
