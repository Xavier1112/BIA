"""Sequential background work, with cancellation between images."""
import json
from pathlib import Path
from threading import Event
from PySide6.QtCore import QThread, Signal
from .core import read_image, analyze_image
from .export import export_result, write_csv

class AnalysisWorker(QThread):
    result_ready = Signal(str, object)
    progress = Signal(int, int)
    completed = Signal(object)

    def __init__(self, paths, config, output=None, parent=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.config = config
        self.output = Path(output) if output else None
        self.cancel_event = Event()

    def run(self):
        report = dict(success=[], failures=[], cancelled=False, output=str(self.output or ''))
        for index,path in enumerate(self.paths):
            if self.cancel_event.is_set():
                report['cancelled'] = True
                break
            try:
                result = analyze_image(read_image(path), self.config)
                folder = export_result(result, path, self.output) if self.output else None
                report['success'].append(dict(source=str(path), output=str(folder or ''), **result.summary))
                if self.output is None:
                    self.result_ready.emit(str(path), result)
            except Exception as exc:
                report['failures'].append(dict(source=str(path), error=f'{type(exc).__name__}: {exc}'))
            self.progress.emit(index + 1, len(self.paths))
        if self.output:
            try:
                if report['success']:
                    write_csv(self.output/'batch_summary.csv', report['success'])
                write_csv(self.output/'failures.csv',report['failures'],['source','error'])
                (self.output/'batch_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            except Exception as exc:
                report['failures'].append(dict(source='Batch report',error=str(exc)))
        self.completed.emit(report)
