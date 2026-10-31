import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from nuclei.gui import MainWindow

def test_gui_analysis_and_stale_export():
    app=QApplication.instance() or QApplication([])
    window=MainWindow(); window.load_samples(); window.analyze()
    for _ in range(1000):
        app.processEvents(); QTest.qWait(10)
        if window.worker and not window.worker.isRunning(): break
    app.processEvents()
    assert window.result is not None
    assert window.result.summary['candidate_count']==5
    assert window.table.rowCount()==5 and window.export_button.isEnabled()
    window.offset.setValue(.02)
    assert not window.export_button.isEnabled() and 'Re-analyze' in window.status.text()
    for mode in range(4): window.mode.setCurrentIndex(mode)
    window.close()
