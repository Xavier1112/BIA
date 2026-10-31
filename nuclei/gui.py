"""Desktop presentation only; image analysis is implemented independently in core.py."""
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QPainter, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QListWidget, QSplitter, QFormLayout, QSpinBox,
    QDoubleSpinBox, QCheckBox, QGroupBox, QComboBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QProgressBar, QPlainTextEdit, QMessageBox, QGraphicsView,
    QGraphicsScene, QAbstractItemView, QHeaderView)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from skimage.color import label2rgb
from .core import AnalysisConfig, read_image, discover_images
from .export import export_result, new_run
from .synthetic import generate_samples
from .worker import AnalysisWorker

ROOT = Path(__file__).resolve().parents[1]

class ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setMinimumSize(200,180)

    def set_image(self, array):
        self.scene().clear()
        if array is None: return
        a = np.asarray(array)
        if a.ndim == 2: a = np.repeat(a[...,None],3,axis=2)
        a = np.ascontiguousarray(a,dtype=np.uint8)
        image = QImage(a.data,a.shape[1],a.shape[0],a.strides[0],QImage.Format.Format_RGB888).copy()
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(0,0,a.shape[1],a.shape[0])
        self.fit_image()

    def fit_image(self):
        self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self,event):
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        if 0.02 < self.transform().m11()*factor < 40: self.scale(factor,factor)
        event.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('BreaKHis Nuclei Explorer')
        self.resize(1350,880)
        self.paths=[]; self.current=None; self.result=None; self.worker=None; self.last_output=None
        central=QWidget(); self.setCentralWidget(central)
        layout=QVBoxLayout(central)
        title=QLabel('BreaKHis Nuclei Explorer'); title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(QLabel('H&E image analysis  |  CPU baseline  |  Candidate regions, not verified nuclei'))
        toolbar=QHBoxLayout(); layout.addLayout(toolbar)
        self.open_button=self.button('Open image',self.open_image,toolbar)
        self.folder_button=self.button('Open folder',self.open_folder,toolbar)
        self.sample_button=self.button('Synthetic examples',self.load_samples,toolbar)
        self.real_button=self.button('BreaKHis samples',self.load_real,toolbar)
        self.button('Quick guide',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'QUICKSTART_ZH.md'))),toolbar)
        toolbar.addStretch()
        split=QSplitter(); layout.addWidget(split,1)
        sidebar=QWidget(); side=QVBoxLayout(sidebar); side.setContentsMargins(0,0,8,0)
        side.addWidget(QLabel('IMAGES'))
        self.file_list=QListWidget(); self.file_list.currentRowChanged.connect(self.select_image)
        side.addWidget(self.file_list,1)
        self.parameters=QGroupBox('Segmentation parameters'); form=QFormLayout(self.parameters)
        self.offset=QDoubleSpinBox(); self.offset.setRange(-.3,.3); self.offset.setSingleStep(.01); self.offset.setDecimals(2)
        self.offset.setToolTip('Added to Otsu threshold (0-1 channel). Increase to retain darker regions only.')
        self.min_area=QSpinBox(); self.min_area.setRange(1,100000); self.min_area.setValue(40)
        self.min_area.setToolTip('Remove components and final instances smaller than this pixel area.')
        self.max_area=QSpinBox(); self.max_area.setRange(1,16000000); self.max_area.setValue(3000)
        self.max_area.setToolTip('Reject final regions larger than this area; may remove merged nuclei.')
        self.distance=QSpinBox(); self.distance.setRange(1,100); self.distance.setValue(8)
        self.distance.setToolTip('Minimum spacing between watershed seeds; smaller can split more regions.')
        self.border=QCheckBox('Exclude image-edge regions')
        self.scale=QDoubleSpinBox(); self.scale.setRange(0,1000); self.scale.setDecimals(6)
        self.scale.setSpecialValueText('Unknown (pixel units)'); self.scale.setSingleStep(.01)
        self.scale.setToolTip('Known micrometres per pixel only. Magnification alone is not calibration.')
        for label,control in [('Threshold offset',self.offset),('Min area (px2)',self.min_area),
                              ('Max area (px2)',self.max_area),('Separation (px)',self.distance),
                              ('Calibration (um/px)',self.scale)]:
            form.addRow(label,control); control.valueChanged.connect(self.mark_stale)
        form.addRow(self.border); self.border.toggled.connect(self.mark_stale)
        reset=QPushButton('Restore defaults'); reset.clicked.connect(self.reset_parameters); form.addRow(reset)
        side.addWidget(self.parameters)
        self.run_button=QPushButton('Analyze selected image'); self.run_button.clicked.connect(self.analyze)
        self.run_button.setObjectName('primary'); side.addWidget(self.run_button)
        self.batch_button=QPushButton('Analyze & export all listed images'); self.batch_button.clicked.connect(self.batch)
        side.addWidget(self.batch_button)
        split.addWidget(sidebar)
        main=QWidget(); right=QVBoxLayout(main); right.setContentsMargins(8,0,0,0)
        self.filename=QLabel('Choose an image or start with synthetic examples.'); self.filename.setWordWrap(True)
        right.addWidget(self.filename)
        viewbar=QHBoxLayout(); right.addLayout(viewbar)
        viewbar.addWidget(QLabel('Result view'))
        self.mode=QComboBox(); self.mode.addItems(['Outline overlay','Hematoxylin channel','Binary mask','Instance labels'])
        self.mode.currentIndexChanged.connect(self.update_result_view); viewbar.addWidget(self.mode)
        self.button('Fit both images',self.fit_views,viewbar); viewbar.addStretch()
        views=QSplitter(); right.addWidget(views,3)
        self.original=ImageView(); self.processed=ImageView()
        for label,view in [('ORIGINAL — wheel to zoom, drag to pan',self.original),('ANALYSIS RESULT',self.processed)]:
            box=QWidget(); box_layout=QVBoxLayout(box); box_layout.setContentsMargins(0,0,0,0)
            box_layout.addWidget(QLabel(label)); box_layout.addWidget(view); views.addWidget(box)
        self.metrics=QLabel('No analysis yet.'); self.metrics.setObjectName('metrics'); self.metrics.setWordWrap(True)
        right.addWidget(self.metrics)
        self.status=QLabel('Ready. Recommended input: BreaKHis 400x RGB images.'); self.status.setWordWrap(True)
        right.addWidget(self.status)
        self.tabs=QTabWidget(); right.addWidget(self.tabs,2)
        self.table=QTableWidget(); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.table,'Per-candidate measurements')
        self.figure=Figure(figsize=(7,2.2),layout='constrained'); self.canvas=FigureCanvasQTAgg(self.figure)
        self.tabs.addTab(self.canvas,'Area distribution')
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.tabs.addTab(self.log,'Run log / failures')
        split.addWidget(main); split.setSizes([330,1000])
        bottom=QHBoxLayout(); layout.addLayout(bottom)
        self.progress=QProgressBar(); self.progress.setValue(0); bottom.addWidget(self.progress,1)
        self.cancel_button=self.button('Cancel after current image',self.cancel,bottom); self.cancel_button.setEnabled(False)
        self.export_button=self.button('Export selected result',self.export_current,bottom); self.export_button.setEnabled(False)
        self.output_button=self.button('Open output folder',self.open_output,bottom); self.output_button.setEnabled(False)
        self.setStyleSheet('''
            QMainWindow {background:#f3f6fa;} QWidget {font-family:"Segoe UI";font-size:12px;color:#21344b;}
            QLabel#title {font-size:24px;font-weight:600;color:#123b53;}
            QLabel#metrics {background:#e1f0ee;padding:12px;font-size:15px;font-weight:600;border-radius:6px;}
            QPushButton {padding:7px 10px;background:white;border:1px solid #c3ced8;border-radius:4px;}
            QPushButton:hover {background:#e7f0f5;} QPushButton:disabled {color:#98a2aa;}
            QPushButton#primary {background:#126d78;color:white;font-weight:600;}
            QGroupBox {font-weight:600;border:1px solid #c3ced8;border-radius:5px;margin-top:12px;padding-top:16px;}
            QListWidget,QTableWidget,QPlainTextEdit,QGraphicsView {background:white;border:1px solid #cdd7df;}
            QHeaderView::section {background:#e5edf3;color:#21344b;padding:5px;border:1px solid #cdd7df;}
            QTableCornerButton::section {background:#e5edf3;border:1px solid #cdd7df;}
            QSplitter::handle {background:#d8e2e9;}
            QSpinBox,QDoubleSpinBox,QComboBox {padding:4px;background:white;border:1px solid #bdcbd6;}
        ''')

    def button(self,text,callback,layout):
        button=QPushButton(text); button.clicked.connect(callback); layout.addWidget(button); return button

    def config(self):
        config=AnalysisConfig(self.offset.value(),self.min_area.value(),self.max_area.value(),
                              self.distance.value(),self.border.isChecked(),self.scale.value() or None)
        config.validate(); return config

    def reset_parameters(self):
        self.offset.setValue(0); self.min_area.setValue(40); self.max_area.setValue(3000)
        self.distance.setValue(8); self.border.setChecked(False); self.scale.setValue(0)

    def mark_stale(self,*args):
        if self.result:
            self.status.setText('Parameters changed. Re-analyze before exporting; displayed result uses previous parameters.')
            self.export_button.setEnabled(False)

    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Select H&E image',str(ROOT),'Images (*.png *.jpg *.jpeg)')
        if path: self.set_paths([Path(path)])

    def open_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Select input folder',str(ROOT/'data'))
        if path: self.set_paths(discover_images(path))

    def load_samples(self):
        self.set_paths(generate_samples(ROOT/'data'/'synthetic'))

    def load_real(self):
        paths=discover_images(ROOT/'data'/'breakhis_samples')
        if paths: self.set_paths(paths)
        else: QMessageBox.information(self,'BreaKHis images','No local samples found. Download the course dataset, unzip it, then use Open folder. See README.md.')

    def set_paths(self,paths):
        self.paths=list(paths); self.file_list.blockSignals(True); self.file_list.clear()
        for path in paths:
            self.file_list.addItem(path.name)
            self.file_list.item(self.file_list.count()-1).setToolTip(str(path))
        self.file_list.blockSignals(False)
        if paths: self.file_list.setCurrentRow(0)
        else:
            self.current=None; self.result=None; self.original.set_image(None); self.clear_results()
            self.status.setText('No PNG/JPEG images found in that folder.')

    def clear_results(self):
        self.result=None; self.processed.set_image(None); self.table.clear(); self.table.setRowCount(0)
        self.figure.clear(); self.canvas.draw(); self.metrics.setText('No analysis yet.')
        self.export_button.setEnabled(False)

    def select_image(self,index):
        self.clear_results(); self.current=None
        if not 0<=index<len(self.paths): return
        path=self.paths[index]
        try:
            image=read_image(path); self.original.set_image(image); self.current=path
            self.filename.setText(path.name + ('  |  SYNTHETIC TEST FIXTURE' if path.name.startswith('SYNTHETIC') else ''))
            self.status.setText(f'{image.shape[1]} x {image.shape[0]} px. Click Analyze selected image.')
        except Exception as exc:
            self.original.set_image(None); self.status.setText(f'Cannot open image: {exc}')
            self.log.appendPlainText(f'{path}: {exc}')

    def analyze(self):
        if self.current: self.start_worker([self.current])
        else: self.status.setText('Select a readable RGB image first.')

    def batch(self):
        if not self.paths: return
        try: self.config()
        except ValueError as exc: self.status.setText(str(exc)); return
        folder=QFileDialog.getExistingDirectory(self,'Choose output parent folder',str(ROOT/'results'))
        if folder:
            try: self.start_worker(self.paths,new_run(folder))
            except OSError as exc: self.status.setText(f'Cannot create output: {exc}')

    def start_worker(self,paths,output=None):
        if self.worker and self.worker.isRunning(): return
        try: config=self.config()
        except ValueError as exc: self.status.setText(str(exc)); return
        self.clear_results(); self.set_busy(True); self.progress.setMaximum(len(paths)); self.progress.setValue(0)
        self.status.setText('Analyzing... cancellation takes effect between images.')
        self.worker=AnalysisWorker(paths,config,output,self)
        self.worker.result_ready.connect(self.show_result)
        self.worker.progress.connect(lambda done,total:self.progress.setValue(done))
        self.worker.completed.connect(self.show_report)
        self.worker.finished.connect(lambda:self.set_busy(False))
        self.worker.start()

    def set_busy(self,busy):
        for control in [self.open_button,self.folder_button,self.sample_button,self.real_button,self.file_list,
                        self.parameters,self.run_button,self.batch_button]: control.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.export_button.setEnabled(not busy and self.result is not None)

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set(); self.cancel_button.setEnabled(False)
            self.status.setText('Cancellation requested. Finishing the current image safely...')

    def show_result(self,path,result):
        self.result=result; self.update_result_view()
        s=result.summary; median=s['median_area_px2']
        self.metrics.setText(f"Detected nucleus candidates: {s['candidate_count']}    |    Median area: "
            f"{f'{median:.1f}' if median is not None else 'N/A'} px2    |    Image coverage: {s['coverage_percent']:.2f}%")
        self.status.setText(f"Rejected: {s['removed_small_components']} small components, {s['rejected_small']} small instances, "
            f"{s['rejected_large']} large, {s['rejected_border']} edge regions. " + ' '.join(result.warnings))
        fields=list(result.rows[0]) if result.rows else ['label','area_px2']
        self.table.setColumnCount(len(fields)); self.table.setHorizontalHeaderLabels(fields)
        self.table.setRowCount(len(result.rows))
        for i,row in enumerate(result.rows):
            for j,key in enumerate(fields):
                val=row[key]; self.table.setItem(i,j,QTableWidgetItem(str(val) if isinstance(val,int) else f'{val:.3f}'))
        self.figure.clear(); ax=self.figure.add_subplot(111)
        if result.rows: ax.hist([r['area_px2'] for r in result.rows],bins='auto',color='#126d78',edgecolor='white')
        else: ax.text(.5,.5,'No candidates',ha='center',transform=ax.transAxes)
        ax.set(xlabel='Candidate area (px2)',ylabel='Number of candidates',title='Area distribution — retained regions')
        self.canvas.draw()
        self.log.appendPlainText(f'{path}: {s["candidate_count"]} candidates; parameters={result.config}')

    def update_result_view(self,*args):
        if self.result is None: return
        r=self.result; index=self.mode.currentIndex()
        image=[lambda:r.overlay(),lambda:(r.hematoxylin*255).astype(np.uint8),
               lambda:r.mask.astype(np.uint8)*255,
               lambda:(label2rgb(r.labels,bg_label=0)*255).astype(np.uint8)][index]()
        self.processed.set_image(image)

    def show_report(self,report):
        self.log.appendPlainText(f"Completed {len(report['success'])}; failures {len(report['failures'])}; cancelled {report['cancelled']}.")
        for item in report['failures']: self.log.appendPlainText(f"{item['source']}: {item['error']}")
        if report['output']:
            self.last_output=Path(report['output']); self.output_button.setEnabled(True)
            self.status.setText(f"Batch {'cancelled' if report['cancelled'] else 'finished'}: {len(report['success'])} saved, "
                                f"{len(report['failures'])} failed. See Run log / failures.")
        elif report['failures']: self.status.setText(report['failures'][0]['error'])

    def export_current(self):
        if self.result is None: return
        folder=QFileDialog.getExistingDirectory(self,'Choose output parent folder',str(ROOT/'results'))
        if folder:
            try:
                self.last_output=export_result(self.result,self.current,new_run(folder))
                self.output_button.setEnabled(True); self.status.setText(f'Saved: {self.last_output}')
            except Exception as exc: QMessageBox.warning(self,'Export failed',str(exc))

    def open_output(self):
        if self.last_output: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def fit_views(self):
        self.original.fit_image(); self.processed.fit_image()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.cancel(); self.status.setText('Waiting for current image. Close again when processing stops.'); event.ignore()
        else: event.accept()
