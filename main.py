"""
LocalizeIt - Professional Localization Automation Tool
======================================================
A fully GUI-based desktop application for automating localization.
No CLI interaction required. Double-click to run.

Convert to .exe:  pyinstaller --noconsole --onefile --name LocalizeIt main.py
"""

import sys
import os
import re
import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QCheckBox, QScrollArea,
    QProgressBar, QRadioButton, QButtonGroup, QFrame, QGridLayout,
    QMessageBox, QStackedWidget, QGroupBox, QSizePolicy, QSpacerItem,
    QTextEdit, QComboBox, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LANGUAGES = [
    "en","af","sq","am","ar","hy","az","bn","eu","be","bg","my","ca",
    "zh-CN","zh-TW","hr","cs","da","nl","et","fil","fi","fr","gl","ka",
    "de","el","gu","iw","hi","hu","is","id","ja","kn","kk","km","ko",
    "ky","lo","lv","lt","mk","ms","ml","mr","mn","ne","no","fa","pl",
    "pt","pa","ro","rm","ru","sr","si","sk","sl","es","sw","sv","ta",
    "te","th","tr","uk","ur","vi","zu"
]

LANG_NAMES = {
    "en":"English","af":"Afrikaans","sq":"Albanian","am":"Amharic",
    "ar":"Arabic","hy":"Armenian","az":"Azerbaijani","bn":"Bengali",
    "eu":"Basque","be":"Belarusian","bg":"Bulgarian","my":"Burmese",
    "ca":"Catalan","zh-CN":"Chinese (Simplified)","zh-TW":"Chinese (Traditional)",
    "hr":"Croatian","cs":"Czech","da":"Danish","nl":"Dutch","et":"Estonian",
    "fil":"Filipino","fi":"Finnish","fr":"French","gl":"Galician",
    "ka":"Georgian","de":"German","el":"Greek","gu":"Gujarati",
    "iw":"Hebrew","hi":"Hindi","hu":"Hungarian","is":"Icelandic",
    "id":"Indonesian","ja":"Japanese","kn":"Kannada","kk":"Kazakh",
    "km":"Khmer","ko":"Korean","ky":"Kyrgyz","lo":"Lao","lv":"Latvian",
    "lt":"Lithuanian","mk":"Macedonian","ms":"Malay","ml":"Malayalam",
    "mr":"Marathi","mn":"Mongolian","ne":"Nepali","no":"Norwegian",
    "fa":"Persian","pl":"Polish","pt":"Portuguese","pa":"Punjabi",
    "ro":"Romanian","rm":"Romansh","ru":"Russian","sr":"Serbian",
    "si":"Sinhala","sk":"Slovak","sl":"Slovenian","es":"Spanish",
    "sw":"Swahili","sv":"Swedish","ta":"Tamil","te":"Telugu","th":"Thai",
    "tr":"Turkish","uk":"Ukrainian","ur":"Urdu","vi":"Vietnamese","zu":"Zulu"
}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging(directory: str | None = None):
    log_dir = directory or os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, "localize_log.txt")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.info("=" * 60)
    logging.info("LocalizeIt session started")
    return log_path

# ---------------------------------------------------------------------------
# File parsing helpers
# ---------------------------------------------------------------------------
def detect_format(filepath: str) -> str:
    """Return 'json' or 'dart' based on file content/extension."""
    ext = Path(filepath).suffix.lower()
    if ext == ".json":
        return "json"
    if ext == ".dart":
        return "dart"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read(2048)
    if content.strip().startswith("{"):
        try:
            json.loads(content + ("}" if not content.rstrip().endswith("}") else ""))
            return "json"
        except Exception:
            pass
    if re.search(r"(final\s+)?Map<String\s*,\s*String>", content):
        return "dart"
    if ext in (".txt", ""):
        try:
            json.loads(open(filepath, encoding="utf-8").read())
            return "json"
        except Exception:
            pass
    return "unknown"


def parse_json_file(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object (key-value pairs).")
    return {str(k): str(v) for k, v in data.items()}


def parse_dart_file(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"Map<String\s*,\s*String>\s*\w+\s*=\s*\{(.*?)\}\s*;", content, re.DOTALL)
    if not m:
        m = re.search(r"\{(.*)\}", content, re.DOTALL)
    if not m:
        raise ValueError("Could not find a Dart Map<String, String> block.")
    body = m.group(1)
    pairs = re.findall(r"""['"](.+?)['"]\s*:\s*['"](.+?)['"]""", body)
    if not pairs:
        raise ValueError("No key-value pairs found in Dart map.")
    return {k: v for k, v in pairs}


def parse_file(filepath: str):
    fmt = detect_format(filepath)
    if fmt == "json":
        return parse_json_file(filepath), "json"
    elif fmt == "dart":
        return parse_dart_file(filepath), "dart"
    else:
        try:
            return parse_json_file(filepath), "json"
        except Exception:
            pass
        try:
            return parse_dart_file(filepath), "dart"
        except Exception:
            pass
        raise ValueError("Unrecognized file format. Please use JSON or Dart.")

# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_json(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_dart(filepath: str, data: dict, lang_code: str = "lang"):
    # Extract language name from filename or use provided code
    filename = os.path.basename(filepath)
    lang_name = LANG_NAMES.get(lang_code, lang_code).lower().replace(" ", "_").replace("(", "").replace(")", "")
    var_name = f"{lang_name}_{lang_code}"
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"final Map<String, String> {var_name} = {{\n")
        items = list(data.items())
        for i, (k, v) in enumerate(items):
            escaped_v = v.replace("\\", "\\\\").replace("'", "\\'")
            comma = "," if i < len(items) - 1 else ","
            f.write(f"  '{k}': '{escaped_v}'{comma}\n")
        f.write("};\n")

# ---------------------------------------------------------------------------
# Fast Translation Worker (Parallel with Configurable Rate Limiting)
# ---------------------------------------------------------------------------
class TranslationWorker(QThread):
    progress = pyqtSignal(int, int, str)  # current, total, lang_code
    finished = pyqtSignal(bool, str)      # success, message
    log_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    string_progress = pyqtSignal(int, int)  # current_string, total_strings
    
    def __init__(self, data, selected_langs, output_format, output_dir, overwrite_all, chunk_size, cooldown_seconds):
        super().__init__()
        self.data = data
        self.selected_langs = selected_langs
        self.output_format = output_format
        self.output_dir = output_dir
        self.overwrite_all = overwrite_all
        self.chunk_size = chunk_size
        self.cooldown_seconds = cooldown_seconds
        self.is_running = True
        
    def translate_batch_parallel(self, texts, target_lang, max_workers=15):
        """Translate a batch of texts in parallel for maximum speed."""
        from deep_translator import GoogleTranslator
        
        results = {}
        
        def translate_single(text):
            """Translate a single text with retry."""
            if not text or not text.strip():
                return text, text
                
            for attempt in range(3):
                try:
                    translator = GoogleTranslator(source="auto", target=target_lang)
                    result = translator.translate(text[:4500])  # Limit length
                    if result and result.strip():
                        return text, result
                except Exception:
                    if attempt < 2:
                        time.sleep(0.3)
            return text, text  # Return original on failure
        
        # Use ThreadPoolExecutor for parallel translation
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(translate_single, text): text for text in texts}
            
            completed = 0
            for future in as_completed(futures):
                if not self.is_running:
                    break
                try:
                    original, translated = future.result(timeout=10)
                    results[original] = translated
                    completed += 1
                    if completed % 10 == 0:
                        self.string_progress.emit(completed, len(texts))
                except Exception:
                    original = futures[future]
                    results[original] = original
        
        return results
    
    def translate_single_language(self, lang, writer, ext):
        """Translate all strings for a single language using parallel processing."""
        if not self.is_running:
            return None, None
            
        lang_label = LANG_NAMES.get(lang, lang)
        self.log_message.emit(f"  Starting {lang_label} ({lang})...")
        
        out_path = os.path.join(self.output_dir, f"{lang}{ext}")
        
        # Check overwrite
        if not self.overwrite_all and os.path.exists(out_path):
            self.log_message.emit(f"  ⚠ Skipped (file exists)")
            return lang, "skipped"
        
        # English is source language
        if lang == "en":
            translated = dict(self.data)
            try:
                if self.output_format == "dart":
                    writer(out_path, translated, lang)
                else:
                    writer(out_path, translated)
                self.log_message.emit(f"  ✓ Saved (copied from source)")
            except Exception as e:
                self.log_message.emit(f"  ❌ Failed to save: {str(e)}")
                return lang, "failed"
        
        # Handle special language codes
        if lang == "iw":
            dl_lang = "he"
        elif lang == "fil":
            dl_lang = "tl"
        else:
            dl_lang = lang
            
        # Get unique texts to translate
        unique_texts = list(set(self.data.values()))
        total_unique = len(unique_texts)
        
        # Determine workers based on string count
        if total_unique < 50:
            workers = 20
            batch_size = 50
        elif total_unique < 150:
            workers = 15
            batch_size = 75
        else:
            workers = 10
            batch_size = 100
        
        self.log_message.emit(f"  Translating {total_unique} unique strings ({workers} workers)...")
        
        try:
            translated_values = {}
            
            # Process in batches for better control
            for i in range(0, len(unique_texts), batch_size):
                if not self.is_running:
                    break
                    
                batch = unique_texts[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(unique_texts) + batch_size - 1) // batch_size
                
                self.log_message.emit(f"    Batch {batch_num}/{total_batches}: {len(batch)} strings")
                
                # Translate batch in parallel
                batch_results = self.translate_batch_parallel(batch, dl_lang, workers)
                translated_values.update(batch_results)
                
                # Small delay between batches
                if i + batch_size < len(unique_texts):
                    time.sleep(0.5)
            
            # Build final translated dictionary
            translated = {}
            for key, value in self.data.items():
                translated[key] = translated_values.get(value, value)
            
            # Save the file
            if self.is_running:
                if self.output_format == "dart":
                    writer(out_path, translated, lang)
                else:
                    writer(out_path, translated)
                self.log_message.emit(f"  ✓ Saved ({len(translated)} strings)")
                
            return lang, "success"
            
        except Exception as e:
            self.log_message.emit(f"  ❌ Translation failed: {str(e)}")
            logging.error(f"Failed to translate {lang}: {e}", exc_info=True)
            return lang, "failed"
    
    def run(self):
        """Perform translation in background thread with configurable cooldown."""
        try:
            from deep_translator import GoogleTranslator
        except ImportError as e:
            self.error_occurred.emit("deep-translator is not installed. Please run: pip install deep-translator")
            self.finished.emit(False, "Translation library not installed")
            return
        
        total = len(self.selected_langs)
        writer = write_json if self.output_format == "json" else write_dart
        ext = ".json" if self.output_format == "json" else ".dart"
        
        self.log_message.emit("=" * 60)
        self.log_message.emit(f"🚀 FAST PARALLEL TRANSLATION")
        self.log_message.emit(f"   • {total} languages total")
        self.log_message.emit(f"   • {len(self.data)} strings per file")
        self.log_message.emit(f"   • Chunks of {self.chunk_size} languages")
        self.log_message.emit(f"   • {self.cooldown_seconds}s cooldown between chunks")
        self.log_message.emit(f"   • Up to 20 parallel translations per language")
        self.log_message.emit("=" * 60)
        
        successful = 0
        skipped = 0
        failed = 0
        failed_langs = []
        overall_idx = 0
        
        for chunk_start in range(0, len(self.selected_langs), self.chunk_size):
            if not self.is_running:
                self.log_message.emit("\n⚠ Translation cancelled by user")
                break
                
            chunk_end = min(chunk_start + self.chunk_size, len(self.selected_langs))
            chunk = self.selected_langs[chunk_start:chunk_end]
            chunk_num = chunk_start // self.chunk_size + 1
            total_chunks = (len(self.selected_langs) + self.chunk_size - 1) // self.chunk_size
            
            if chunk_start > 0:
                self.log_message.emit(f"\n⏸ COOLDOWN: {self.cooldown_seconds}s...")
                for i in range(self.cooldown_seconds, 0, -1):
                    if not self.is_running:
                        break
                    if i % 5 == 0 or i <= 3:
                        self.log_message.emit(f"   Resuming in {i}s...")
                    time.sleep(1)
                if self.is_running:
                    self.log_message.emit("▶ Resuming...\n")
            
            self.log_message.emit(f"📦 CHUNK {chunk_num}/{total_chunks}: {len(chunk)} languages")
            self.log_message.emit("-" * 40)
            
            for lang in chunk:
                if not self.is_running:
                    break
                    
                self.progress.emit(overall_idx, total, lang)
                self.log_message.emit(f"\n[{overall_idx+1}/{total}] {LANG_NAMES.get(lang, lang)} ({lang})")
                
                start_time = time.time()
                try:
                    result_lang, status = self.translate_single_language(lang, writer, ext)
                    elapsed = time.time() - start_time
                    
                    if status == "success":
                        successful += 1
                        if elapsed > 0:
                            speed = len(self.data) / elapsed
                            self.log_message.emit(f"  ⏱ Done in {elapsed:.1f}s ({speed:.0f} strings/sec)")
                    elif status == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                        failed_langs.append(f"{LANG_NAMES.get(lang, lang)} ({lang})")
                except Exception as e:
                    failed += 1
                    failed_langs.append(f"{LANG_NAMES.get(lang, lang)} ({lang})")
                    self.log_message.emit(f"  ❌ Error: {str(e)}")
                    logging.error(f"Error processing {lang}: {e}", exc_info=True)
                    
                overall_idx += 1
        
        # Final summary
        self.progress.emit(total, total, "done")
        self.log_message.emit("\n" + "=" * 60)
        self.log_message.emit("✅ TRANSLATION COMPLETE")
        self.log_message.emit(f"   • Successful: {successful}")
        if skipped > 0:
            self.log_message.emit(f"   • Skipped: {skipped}")
        if failed > 0:
            self.log_message.emit(f"   • Failed: {failed}")
            self.log_message.emit(f"   • Failed: {', '.join(failed_langs)}")
        self.log_message.emit("=" * 60)
        
        if failed > 0:
            self.finished.emit(True, f"Done with {failed} failures. {successful} successful.")
        else:
            self.finished.emit(True, f"All {successful} languages translated! 🎉")
    
    def stop(self):
        """Stop the translation process."""
        self.is_running = False

# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------
STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget {
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Arial', sans-serif;
}
QLabel {
    color: #cdd6f4;
}
QLabel#title {
    font-size: 26px;
    font-weight: bold;
    color: #89b4fa;
}
QLabel#subtitle {
    font-size: 13px;
    color: #a6adc8;
}
QLabel#sectionTitle {
    font-size: 16px;
    font-weight: bold;
    color: #cba6f7;
}
QPushButton {
    background-color: #89b4fa;
    color: #000000;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #b4d0fb;
    color: #000000;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#secondary {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QPushButton#secondary:hover {
    background-color: #45475a;
}
QPushButton#success {
    background-color: #a6e3a1;
    color: #000000;
}
QPushButton#success:hover {
    background-color: #c6f0c1;
    color: #000000;
}
QPushButton#danger {
    background-color: #f38ba8;
    color: #000000;
}
QPushButton#danger:hover {
    background-color: #f5b0c4;
    color: #000000;
}
QRadioButton {
    font-size: 14px;
    spacing: 8px;
    color: #cdd6f4;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
}
QCheckBox {
    font-size: 13px;
    spacing: 6px;
    padding: 3px;
    color: #cdd6f4;
    background-color: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator:unchecked {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border: 1px solid #89b4fa;
    border-radius: 3px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 18px;
    font-size: 14px;
    font-weight: bold;
    color: #cba6f7;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #cba6f7;
}
QProgressBar {
    border: none;
    border-radius: 8px;
    background-color: #313244;
    height: 22px;
    text-align: center;
    font-weight: bold;
    color: #000000;
}
QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 8px;
}
QScrollArea {
    border: none;
    background-color: #181825;
}
QScrollArea > QWidget > QWidget {
    background-color: #181825;
}
QScrollBar:vertical {
    background-color: #181825;
    width: 12px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #6c7086;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
QTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #a6adc8;
}
QFrame#card {
    background-color: #313244;
    border-radius: 12px;
    padding: 16px;
}
QComboBox, QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #cdd6f4;
    margin-right: 5px;
}
QSpinBox::up-button {
    background-color: #45475a;
    border-radius: 3px;
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #313244;
}
QSpinBox::up-button:hover {
    background-color: #6c7086;
}
QSpinBox::up-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid #cdd6f4;
}
QSpinBox::down-button {
    background-color: #45475a;
    border-radius: 3px;
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #313244;
}
QSpinBox::down-button:hover {
    background-color: #6c7086;
}
QSpinBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #cdd6f4;
}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {
    background-color: #313244;
}
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled {
    border-bottom-color: #6c7086;
    border-top-color: #6c7086;
}
QLabel#guideLabel {
    color: #f38ba8;
    font-size: 12px;
    font-weight: bold;
}
QLabel#warningLabel {
    color: #fab387;
    font-size: 12px;
    font-weight: bold;
}
QMessageBox {
    background-color: #1e1e2e;
}
QMessageBox QLabel {
    color: #cdd6f4;
    font-size: 14px;
    padding: 10px;
}
QMessageBox QPushButton {
    background-color: #89b4fa;
    color: #000000;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
    min-width: 80px;
}
QMessageBox QPushButton:hover {
    background-color: #b4d0fb;
    color: #000000;
}
"""

# ---------------------------------------------------------------------------
# Main Window (Keep exactly the same as before, just update worker call)
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalizeIt — Localization Automation")
        self.setMinimumSize(900, 750)
        self.resize(950, 800)
        self.setStyleSheet(STYLESHEET)
        self.setPalette(self._create_dark_palette())

        self.input_path: str | None = None
        self.parsed_data: dict = {}
        self.input_format: str = ""
        self.output_format: str = "json"
        self.output_dir: str = ""
        self.lang_checkboxes: dict[str, QCheckBox] = {}
        self.overwrite_all = False
        self.log_path = setup_logging()
        self.worker: TranslationWorker | None = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._build_start_page()
        self._build_language_page()
        self._build_processing_page()
        self._build_done_page()

        self.stack.setCurrentIndex(0)
        self._try_autodetect()
    
    def _create_dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 46))
        palette.setColor(QPalette.WindowText, QColor(205, 214, 244))
        palette.setColor(QPalette.Base, QColor(24, 24, 37))
        palette.setColor(QPalette.AlternateBase, QColor(49, 50, 68))
        palette.setColor(QPalette.ToolTipBase, QColor(30, 30, 46))
        palette.setColor(QPalette.ToolTipText, QColor(205, 214, 244))
        palette.setColor(QPalette.Text, QColor(205, 214, 244))
        palette.setColor(QPalette.Button, QColor(49, 50, 68))
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(137, 180, 250))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        return palette

    def _get_recommended_settings(self):
        string_count = len(self.parsed_data) if self.parsed_data else 0
        if string_count < 100:
            return 10, 5
        elif string_count < 200:
            return 8, 8
        else:
            return 5, 12

    def _build_start_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(12)

        title = QLabel("LocalizeIt")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("Translate your app strings into 72 languages in one click.")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        lay.addSpacing(20)

        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setSpacing(10)

        sec1 = QLabel("📄  Input File")
        sec1.setObjectName("sectionTitle")
        card_lay.addWidget(sec1)

        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        card_lay.addWidget(self.file_label)

        self.format_detected_label = QLabel("")
        self.format_detected_label.setStyleSheet("color: #a6e3a1; font-size: 13px;")
        card_lay.addWidget(self.format_detected_label)

        self.keys_label = QLabel("")
        self.keys_label.setStyleSheet("color: #a6adc8; font-size: 13px;")
        card_lay.addWidget(self.keys_label)

        btn_row = QHBoxLayout()
        btn_select = QPushButton("Select File")
        btn_select.clicked.connect(self._select_file)
        btn_row.addWidget(btn_select)
        btn_row.addStretch()
        card_lay.addLayout(btn_row)

        lay.addWidget(card)
        lay.addSpacing(10)

        card2 = QFrame()
        card2.setObjectName("card")
        card2_lay = QVBoxLayout(card2)
        card2_lay.setSpacing(10)

        sec2 = QLabel("📂  Output Format")
        sec2.setObjectName("sectionTitle")
        card2_lay.addWidget(sec2)

        self.radio_json = QRadioButton("JSON  (.json)")
        self.radio_dart = QRadioButton("Dart  (.dart)")
        self.radio_json.setChecked(True)
        self.fmt_group = QButtonGroup()
        self.fmt_group.addButton(self.radio_json)
        self.fmt_group.addButton(self.radio_dart)
        self.radio_json.toggled.connect(lambda c: self._set_output_format("json") if c else None)
        self.radio_dart.toggled.connect(lambda c: self._set_output_format("dart") if c else None)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(self.radio_json)
        fmt_row.addSpacing(30)
        fmt_row.addWidget(self.radio_dart)
        fmt_row.addStretch()
        card2_lay.addLayout(fmt_row)

        self.chk_overwrite = QCheckBox("Overwrite existing output files without asking")
        self.chk_overwrite.setChecked(False)
        card2_lay.addWidget(self.chk_overwrite)

        lay.addWidget(card2)
        
        card3 = QFrame()
        card3.setObjectName("card")
        card3_lay = QVBoxLayout(card3)
        card3_lay.setSpacing(10)
        
        sec3 = QLabel("⚙️  Rate Limiting Settings")
        sec3.setObjectName("sectionTitle")
        card3_lay.addWidget(sec3)
        
        self.guide_label = QLabel("Load a file to see recommended settings")
        self.guide_label.setObjectName("guideLabel")
        self.guide_label.setWordWrap(True)
        card3_lay.addWidget(self.guide_label)
        
        settings_row = QHBoxLayout()
        settings_row.setSpacing(20)
        
        chunk_layout = QVBoxLayout()
        chunk_label = QLabel("Files per chunk:")
        chunk_label.setStyleSheet("font-size: 12px;")
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, 20)
        self.chunk_spin.setValue(10)
        self.chunk_spin.setFixedWidth(80)
        chunk_layout.addWidget(chunk_label)
        chunk_layout.addWidget(self.chunk_spin)
        settings_row.addLayout(chunk_layout)
        
        cooldown_layout = QVBoxLayout()
        cooldown_label = QLabel("Cooldown (seconds):")
        cooldown_label.setStyleSheet("font-size: 12px;")
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(3, 60)
        self.cooldown_spin.setValue(5)
        self.cooldown_spin.setFixedWidth(80)
        cooldown_layout.addWidget(cooldown_label)
        cooldown_layout.addWidget(self.cooldown_spin)
        settings_row.addLayout(cooldown_layout)
        
        settings_row.addStretch()
        card3_lay.addLayout(settings_row)
        
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        card3_lay.addWidget(self.warning_label)
        
        lay.addWidget(card3)
        lay.addStretch()

        self.btn_next_start = QPushButton("Next →  Select Languages")
        self.btn_next_start.setFixedHeight(44)
        self.btn_next_start.setEnabled(False)
        self.btn_next_start.clicked.connect(self._go_to_languages)
        lay.addWidget(self.btn_next_start)

        self.stack.addWidget(page)

    def _build_language_page(self):
        page = QWidget()
        page.setStyleSheet("QWidget { background-color: #1e1e2e; }")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 20, 40, 20)
        lay.setSpacing(8)

        header = QHBoxLayout()
        btn_back = QPushButton("← Back")
        btn_back.setObjectName("secondary")
        btn_back.setFixedWidth(90)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        header.addWidget(btn_back)
        lbl = QLabel("🌍  Select Target Languages")
        lbl.setObjectName("sectionTitle")
        header.addWidget(lbl)
        header.addStretch()
        lay.addLayout(header)

        ctrl = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setObjectName("secondary")
        self.btn_select_all.setFixedWidth(110)
        self.btn_select_all.clicked.connect(self._toggle_all_langs)
        ctrl.addWidget(self.btn_select_all)

        self.selected_count_label = QLabel("0 selected")
        self.selected_count_label.setStyleSheet("color: #a6adc8; font-size: 13px;")
        ctrl.addWidget(self.selected_count_label)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
            }
        """)
        
        scroll_w = QWidget()
        scroll_w.setStyleSheet("background-color: #181825;")
        grid = QGridLayout(scroll_w)
        grid.setSpacing(4)
        grid.setContentsMargins(10, 10, 10, 10)

        cols = 4
        for i, code in enumerate(LANGUAGES):
            name = LANG_NAMES.get(code, code)
            cb = QCheckBox(f"{name}  [{code}]")
            cb.stateChanged.connect(self._update_lang_count)
            self.lang_checkboxes[code] = cb
            grid.addWidget(cb, i // cols, i % cols)

        scroll.setWidget(scroll_w)
        lay.addWidget(scroll, 1)

        self.btn_start_translate = QPushButton("Start Translation →")
        self.btn_start_translate.setFixedHeight(44)
        self.btn_start_translate.setEnabled(False)
        self.btn_start_translate.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c6f0c1;
                color: #000000;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
        """)
        self.btn_start_translate.clicked.connect(self._go_to_processing)
        lay.addWidget(self.btn_start_translate)

        self.stack.addWidget(page)

    def _build_processing_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(14)

        lbl = QLabel("⏳  Translating…")
        lbl.setObjectName("sectionTitle")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        self.progress_label = QLabel("Preparing…")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 14px;")
        lay.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        lay.addWidget(self.progress_bar)

        self.current_lang_label = QLabel("")
        self.current_lang_label.setAlignment(Qt.AlignCenter)
        self.current_lang_label.setStyleSheet("font-size: 13px; color: #a6adc8;")
        lay.addWidget(self.current_lang_label)

        lay.addSpacing(10)

        log_label = QLabel("Log")
        log_label.setStyleSheet("color: #6c7086; font-size: 12px;")
        lay.addWidget(log_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        lay.addWidget(self.log_box, 1)

        self.btn_cancel = QPushButton("Cancel Translation")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_translation)
        self.btn_cancel.setEnabled(False)
        lay.addWidget(self.btn_cancel)

        self.stack.addWidget(page)

    def _build_done_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 60, 40, 40)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignCenter)

        emoji = QLabel("✅")
        emoji.setStyleSheet("font-size: 60px;")
        emoji.setAlignment(Qt.AlignCenter)
        lay.addWidget(emoji)

        self.done_label = QLabel("All files generated successfully!")
        self.done_label.setObjectName("title")
        self.done_label.setAlignment(Qt.AlignCenter)
        self.done_label.setWordWrap(True)
        lay.addWidget(self.done_label)

        self.done_sub = QLabel("")
        self.done_sub.setObjectName("subtitle")
        self.done_sub.setAlignment(Qt.AlignCenter)
        self.done_sub.setWordWrap(True)
        lay.addWidget(self.done_sub)

        lay.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)

        btn_open = QPushButton("Open Output Folder")
        btn_open.setObjectName("success")
        btn_open.clicked.connect(self._open_output_folder)
        btn_row.addWidget(btn_open)

        btn_restart = QPushButton("Start Over")
        btn_restart.setObjectName("secondary")
        btn_restart.clicked.connect(self._restart)
        btn_row.addWidget(btn_restart)

        lay.addLayout(btn_row)
        lay.addStretch()

        self.stack.addWidget(page)

    def _try_autodetect(self):
        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates = []
        try:
            for f in os.listdir(app_dir):
                fp = os.path.join(app_dir, f)
                if os.path.isfile(fp) and f.lower().endswith((".json", ".dart")):
                    stem = Path(f).stem
                    if stem in LANGUAGES:
                        continue
                    candidates.append(fp)
            if candidates:
                self._load_file(candidates[0])
        except Exception as e:
            logging.error(f"Auto-detect error: {e}")

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Localization File", "",
            "Localization Files (*.json *.dart);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            data, fmt = parse_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to parse file:\n{e}")
            logging.error("Parse error for %s: %s", path, e)
            return
        if not data:
            QMessageBox.warning(self, "Error", "File contains no key-value pairs.")
            return

        self.input_path = path
        self.parsed_data = data
        self.input_format = fmt
        self.output_dir = os.path.dirname(path)

        self.file_label.setText(f"📁  {path}")
        self.format_detected_label.setText(f"Detected format: {fmt.upper()}")
        self.keys_label.setText(f"{len(data)} key-value pairs found")
        self.btn_next_start.setEnabled(True)
        self._update_rate_guide()
        logging.info("Loaded file: %s (%s, %d keys)", path, fmt, len(data))
    
    def _update_rate_guide(self):
        string_count = len(self.parsed_data)
        rec_chunk, rec_cooldown = self._get_recommended_settings()
        
        if string_count < 100:
            guide_text = "📊 Strings: < 100 → Recommended: 10 files/chunk, 5 sec cooldown"
            warning = ""
            self.chunk_spin.setValue(10)
            self.cooldown_spin.setValue(5)
        elif string_count < 200:
            guide_text = "📊 Strings: 100-200 → Recommended: 8 files/chunk, 8 sec cooldown"
            warning = "⚠️ Medium file - 8 files per chunk recommended"
            self.chunk_spin.setValue(8)
            self.cooldown_spin.setValue(8)
        else:
            guide_text = "📊 Strings: > 200 → Recommended: 5 files/chunk, 12 sec cooldown"
            warning = "🔴 LARGE FILE! Use 5 files per chunk!"
            self.chunk_spin.setValue(5)
            self.cooldown_spin.setValue(12)
        
        self.guide_label.setText(guide_text)
        self.warning_label.setText(warning)

    def _set_output_format(self, fmt):
        self.output_format = fmt

    def _go_to_languages(self):
        self.stack.setCurrentIndex(1)

    def _toggle_all_langs(self):
        all_checked = all(cb.isChecked() for cb in self.lang_checkboxes.values())
        for cb in self.lang_checkboxes.values():
            cb.setChecked(not all_checked)
        self.btn_select_all.setText("Deselect All" if not all_checked else "Select All")

    def _update_lang_count(self):
        count = sum(1 for cb in self.lang_checkboxes.values() if cb.isChecked())
        self.selected_count_label.setText(f"{count} selected")
        self.btn_start_translate.setEnabled(count > 0)

    def _go_to_processing(self):
        selected = [code for code, cb in self.lang_checkboxes.items() if cb.isChecked()]
        if not selected:
            QMessageBox.information(self, "Info", "Please select at least one language.")
            return

        self.overwrite_all = self.chk_overwrite.isChecked()

        if not self.overwrite_all:
            ext = ".json" if self.output_format == "json" else ".dart"
            existing = [l for l in selected if os.path.exists(os.path.join(self.output_dir, f"{l}{ext}"))]
            if existing:
                reply = QMessageBox.question(
                    self, "Files Exist",
                    f"{len(existing)} output file(s) already exist.\nOverwrite them?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                if reply == QMessageBox.Cancel:
                    return
                self.overwrite_all = (reply == QMessageBox.Yes)

        self.stack.setCurrentIndex(2)
        self.log_box.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(selected))
        self.btn_cancel.setEnabled(True)

        chunk_size = self.chunk_spin.value()
        cooldown = self.cooldown_spin.value()

        self.worker = TranslationWorker(
            self.parsed_data, selected,
            self.output_format, self.output_dir, self.overwrite_all,
            chunk_size, cooldown
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.log_message.connect(self._on_log)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.string_progress.connect(self._on_string_progress)
        self.worker.start()

    def _cancel_translation(self):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Cancel Translation",
                "Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._on_log("⚠ Cancelling...")
                self.worker.stop()
                self.btn_cancel.setEnabled(False)

    def _on_progress(self, current, total, lang):
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"Translating {current} / {total} languages")
        if lang != "done":
            name = LANG_NAMES.get(lang, lang)
            self.current_lang_label.setText(f"Current: {name} ({lang})")

    def _on_string_progress(self, current, total):
        self.current_lang_label.setText(f"Current: Translating strings ({current}/{total})")

    def _on_log(self, msg):
        self.log_box.append(msg)
        scrollbar = self.log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_error(self, error_msg):
        QMessageBox.critical(self, "Error", error_msg)
        self.btn_cancel.setEnabled(False)
        self.stack.setCurrentIndex(0)

    def _on_finished(self, success, message):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.current_lang_label.setText("")
        self.btn_cancel.setEnabled(False)
        logging.info("Translation finished: %s", message)
        self.done_label.setText("Done!" if success else "Completed with errors")
        self.done_sub.setText(message)
        self.stack.setCurrentIndex(3)

    def _open_output_folder(self):
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(self.output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.output_dir])
            else:
                subprocess.Popen(["xdg-open", self.output_dir])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{e}")

    def _restart(self):
        for cb in self.lang_checkboxes.values():
            cb.setChecked(False)
        self.btn_select_all.setText("Select All")
        self._update_lang_count()
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Translation in Progress",
                "Translation is still running. Quit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.stop()
                self.worker.wait(2000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(MainWindow._create_dark_palette(None))
    
    try:
        import deep_translator
    except ImportError:
        QMessageBox.critical(
            None, "Missing Dependency",
            "deep-translator is not installed.\n\n"
            "pip install deep-translator"
        )
        sys.exit(1)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()