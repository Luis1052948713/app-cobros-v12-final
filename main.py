# ============================================================
# APP-COBROS-V12-FINAL - MAIN.PY PRODUCCIÓN
# Python + Kivy + SQLite
#
# Características:
# - Base SQLite persistente real.
# - En PC guarda la DB junto al proyecto.
# - En Android guarda la DB en user_data_dir.
# - No carga datos demo automáticamente.
# - Interfaz mobile-first.
# - Nuevo cliente por pasos.
# - Cálculo automático de total, cuota y saldo del crédito.
# - CRUD cliente/préstamo.
# - Cobros: Cuota, Aporte, No Pago, Siguiente Día.
# - Estados visuales: verde, amarillo, rojo.
# - Movimientos de caja.
# - Resumen del día.
# ============================================================

from datetime import datetime, timedelta
from pathlib import Path
import os
import sqlite3
import json
import urllib.request
import urllib.error

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform


# ============================================================
# CONFIGURACIÓN VISUAL
# ============================================================

if platform not in ("android", "ios"):
    Window.size = (430, 820)

Window.clearcolor = (0.06, 0.07, 0.10, 1)

BLUE = (0.117, 0.227, 0.541, 1)
BLUE_DARK = (0.08, 0.16, 0.36, 1)
GOLD = (0.93, 0.69, 0.13, 1)
WHITE = (1, 1, 1, 1)
TEXT = (0.10, 0.12, 0.16, 1)
MUTED = (0.43, 0.47, 0.54, 1)
DARK = (0.12, 0.14, 0.18, 1)
SUCCESS = (0.12, 0.62, 0.32, 1)
DANGER = (0.83, 0.18, 0.18, 1)
LIGHT_BG = (0.95, 0.96, 0.98, 1)

STATUS_GREEN = (0.86, 0.98, 0.89, 1)
STATUS_YELLOW = (1.00, 0.96, 0.78, 1)
STATUS_RED = (1.00, 0.88, 0.88, 1)
STATUS_BORDER_GREEN = (0.12, 0.62, 0.32, 1)
STATUS_BORDER_YELLOW = (0.93, 0.69, 0.13, 1)
STATUS_BORDER_RED = (0.83, 0.18, 0.18, 1)


# ============================================================
# CONFIGURACIÓN SUPABASE
# ============================================================
# Pega aquí los datos de tu proyecto Supabase.
# No uses SERVICE_ROLE_KEY dentro de la app móvil.
SUPABASE_URL = "https://frvzniydfdmhltxwyknh.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZydnpuaXlkZmRtaGx0eHd5a25oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1Nzc3NjUsImV4cCI6MjA5NjE1Mzc2NX0.2NFIkalEfGf0P7d9bT_kmNW_DvMU8I9bYTqQxabV_hI"
COBRADOR_ID = "e058ca8f-210f-4c2e-8c7d-33ed239b3f20"

SYNC_ENABLED = True
SYNC_INTERVAL_SECONDS = 60
SYNC_TIMEOUT_SECONDS = 10


# ============================================================
# MEMORIA DE LA APP
# ============================================================

CLIENTES = []
TRANSACCIONES = []
MOVIMIENTOS_CAJA = []


# ============================================================
# UTILIDADES
# ============================================================

def today_text():
    return datetime.now().strftime("%d/%m/%Y")


def now_text():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def iso_today():
    return datetime.now().strftime("%Y-%m-%d")


def display_date_from_iso(value):
    try:
        if not value:
            return "No definido"
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return "No definido"


def next_due_date(cobro):
    """
    Calcula la próxima fecha de cobro.
    Diario: mañana.
    Semanal: dentro de 7 días.
    Quincenal: dentro de 15 días.
    Mensual: dentro de 30 días.
    """
    today = datetime.now().date()
    cobro = (cobro or "Diario").strip().lower()

    if cobro == "semanal":
        delta = 7
    elif cobro == "quincenal":
        delta = 15
    elif cobro == "mensual":
        delta = 30
    else:
        delta = 1

    return (today + timedelta(days=delta)).strftime("%Y-%m-%d")


def detach_widget(widget):
    """
    Evita el cierre de la app cuando se vuelve a la pantalla Nuevo.
    Kivy no permite agregar el mismo TextInput a dos padres distintos.
    Si el campo ya tenía padre, se separa antes de volver a usarlo.
    """
    try:
        if widget is not None and widget.parent is not None:
            widget.parent.remove_widget(widget)
    except Exception:
        pass


def money(value):
    try:
        value = int(float(value or 0))
    except Exception:
        value = 0
    return "$ {:,.0f}".format(value).replace(",", ".")


def format_thousands(value):
    """
    Devuelve números con separador de miles colombiano:
    500000 -> 500.000
    """
    try:
        value = int(float(value or 0))
    except Exception:
        value = 0
    return "{:,.0f}".format(value).replace(",", ".")


def to_int(value, default=0):
    try:
        clean = str(value or "").replace("$", "").replace(".", "").replace(",", "").strip()
        if clean == "":
            return default
        return int(float(clean))
    except Exception:
        return default


def to_float(value, default=0.0):
    try:
        clean = str(value or "").replace("%", "").replace(",", ".").strip()
        if clean == "":
            return default
        return float(clean)
    except Exception:
        return default


def asset_path(filename):
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "assets" / filename,
        Path(os.getcwd()) / "assets" / filename,
        base_dir / filename,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def safe_pdf_text(value):
    text = str(value or "")
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "ñ": "n", "Ñ": "N",
        "–": "-", "—": "-", "“": '"', "”": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def get_exports_dir():
    if platform in ("android", "ios"):
        try:
            app = App.get_running_app()
            if app and getattr(app, "user_data_dir", None):
                path = Path(app.user_data_dir) / "reportes"
                path.mkdir(parents=True, exist_ok=True)
                return path
        except Exception:
            pass

    path = Path(__file__).resolve().parent / "reportes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shorten(value, max_len=34):
    text = str(value or "")
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


class ProfessionalPDF:
    def __init__(self, output_path):
        self.output_path = Path(output_path)
        self.page_width = 595
        self.page_height = 842
        self.margin = 34
        self.pages = []
        self.commands = []
        self.page_no = 0
        self.new_page()

    def color(self, r, g, b):
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def rect(self, x, y, w, h, fill=True):
        self.commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {'f' if fill else 'S'}")

    def line(self, x1, y1, x2, y2):
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def text(self, x, y, text, size=10, bold=False, color=(0.10, 0.12, 0.16)):
        font = "F2" if bold else "F1"
        r, g, b = color
        txt = safe_pdf_text(text)
        self.commands.extend([
            "BT",
            f"{r:.3f} {g:.3f} {b:.3f} rg",
            f"/{font} {size} Tf",
            f"1 0 0 1 {x:.2f} {y:.2f} Tm",
            f"({txt}) Tj",
            "ET",
        ])

    def new_page(self):
        if self.commands:
            self.footer()
            self.pages.append("\n".join(self.commands))
        self.page_no += 1
        self.commands = []
        self.y = 800
        self.header()

    def header(self):
        self.color(0.117, 0.227, 0.541)
        self.rect(0, 774, self.page_width, 68, True)
        self.text(self.margin, 814, "COBROS V12", 20, True, (1, 1, 1))
        self.text(self.margin, 792, "Reporte profesional de cierre de caja", 10, False, (0.90, 0.94, 1))
        self.color(0.93, 0.69, 0.13)
        self.rect(self.page_width - 170, 796, 135, 26, True)
        self.text(self.page_width - 158, 805, today_text(), 10, True, (0.12, 0.14, 0.18))
        self.y = 752

    def footer(self):
        self.color(0.78, 0.81, 0.86)
        self.line(self.margin, 42, self.page_width - self.margin, 42)
        self.text(self.margin, 26, "Cobros V12 Mobile - Reporte de cierre", 8, False, (0.42, 0.46, 0.52))
        self.text(self.page_width - 95, 26, f"Pagina {self.page_no}", 8, False, (0.42, 0.46, 0.52))

    def ensure_space(self, height):
        if self.y - height < 62:
            self.new_page()

    def section(self, title):
        self.ensure_space(38)
        self.color(0.117, 0.227, 0.541)
        self.rect(self.margin, self.y - 22, self.page_width - 2 * self.margin, 24, True)
        self.text(self.margin + 10, self.y - 15, title.upper(), 11, True, (1, 1, 1))
        self.y -= 36

    def key_grid(self, items, columns=2):
        width = self.page_width - 2 * self.margin
        col_w = width / columns
        row_h = 36

        for i in range(0, len(items), columns):
            self.ensure_space(row_h + 4)
            row = items[i:i + columns]
            for j, item in enumerate(row):
                label, value, highlight = item
                x = self.margin + j * col_w
                y = self.y - row_h
                self.color(1.00, 0.95, 0.78) if highlight else self.color(0.96, 0.97, 0.99)
                self.rect(x, y, col_w - 6, row_h - 4, True)
                self.color(0.84, 0.87, 0.91)
                self.rect(x, y, col_w - 6, row_h - 4, False)
                self.text(x + 8, y + 20, label, 8, True, (0.42, 0.46, 0.52))
                self.text(x + 8, y + 7, value, 11, highlight, (0.10, 0.12, 0.16))
            self.y -= row_h
        self.y -= 8

    def table(self, headers, rows, col_widths):
        table_width = sum(col_widths)
        header_h = 22
        row_h = 20
        self.ensure_space(header_h + row_h + 10)

        y = self.y - header_h
        self.color(0.90, 0.93, 0.97)
        self.rect(self.margin, y, table_width, header_h, True)
        self.color(0.78, 0.81, 0.86)
        self.rect(self.margin, y, table_width, header_h, False)

        x = self.margin
        for h, w in zip(headers, col_widths):
            self.text(x + 4, y + 8, h, 8, True, (0.20, 0.24, 0.30))
            x += w
        self.y -= header_h

        if not rows:
            self.ensure_space(row_h)
            self.text(self.margin + 4, self.y - 14, "Sin registros para mostrar.", 9, False, (0.42, 0.46, 0.52))
            self.y -= row_h + 8
            return

        for idx, row in enumerate(rows):
            self.ensure_space(row_h + 4)
            y = self.y - row_h
            self.color(1, 1, 1) if idx % 2 == 0 else self.color(0.98, 0.99, 1)
            self.rect(self.margin, y, table_width, row_h, True)
            self.color(0.88, 0.90, 0.94)
            self.line(self.margin, y, self.margin + table_width, y)
            x = self.margin
            for value, w in zip(row, col_widths):
                self.text(x + 4, y + 7, value, 8, False, (0.10, 0.12, 0.16))
                x += w
            self.y -= row_h
        self.y -= 10

    def paragraph(self, text):
        self.ensure_space(20)
        self.text(self.margin, self.y - 10, text, 9, False, (0.42, 0.46, 0.52))
        self.y -= 20

    def save(self):
        if self.commands:
            self.footer()
            self.pages.append("\n".join(self.commands))
            self.commands = []

        objects = [
            "1 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
            "2 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n",
        ]

        page_refs = []
        next_obj = 3

        for content in self.pages:
            content_id = next_obj
            page_id = next_obj + 1
            next_obj += 2
            page_refs.append(f"{page_id} 0 R")
            content_bytes = content.encode("latin-1", errors="ignore")
            objects.append(f"{content_id} 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n{content}\nendstream\nendobj\n")
            objects.append(
                f"{page_id} 0 obj\n"
                f"<< /Type /Page /Parent 999 0 R /MediaBox [0 0 {self.page_width} {self.page_height}] "
                f"/Resources << /Font << /F1 1 0 R /F2 2 0 R >> >> /Contents {content_id} 0 R >>\n"
                f"endobj\n"
            )

        pages_id = next_obj
        catalog_id = next_obj + 1
        objects = [obj.replace("999 0 R", f"{pages_id} 0 R") for obj in objects]
        objects.append(f"{pages_id} 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>\nendobj\n")
        objects.append(f"{catalog_id} 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj\n")

        pdf = "%PDF-1.4\n"
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf.encode("latin-1", errors="ignore")))
            pdf += obj

        xref_pos = len(pdf.encode("latin-1", errors="ignore"))
        total_objects = len(objects) + 1
        pdf += f"xref\n0 {total_objects}\n"
        pdf += "0000000000 65535 f \n"
        for offset in offsets[1:]:
            pdf += f"{offset:010d} 00000 n \n"
        pdf += f"trailer\n<< /Size {total_objects} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF"

        self.output_path.write_bytes(pdf.encode("latin-1", errors="ignore"))
        return str(self.output_path)


def generate_daily_pdf_report():
    refresh_memory_from_db()

    total_clientes = len(CLIENTES)
    pagos = [t for t in TRANSACCIONES if t.get("tipo") in ("Cuota", "Aporte")]
    no_pagos = [t for t in TRANSACCIONES if t.get("tipo") == "No Pago"]
    aplazados = [t for t in TRANSACCIONES if t.get("tipo") == "Siguiente Día"]

    recaudo_dia = sum(int(t.get("valor", 0)) for t in pagos)
    ingresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Ingreso")
    egresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Egreso")
    recaudo_esperado = sum(int(c.get("cuota", 0)) for c in CLIENTES)
    saldo_caja = current_cash_balance() if "current_cash_balance" in globals() else (recaudo_dia + ingresos - egresos)
    pendientes_sync = count_pending_sync()

    filename = f"cierre_caja_{datetime.now().strftime('%Y_%m_%d_%H_%M')}.pdf"
    output_path = get_exports_dir() / filename
    pdf = ProfessionalPDF(output_path)

    pdf.section("Resumen ejecutivo")
    pdf.key_grid([
        ("Fecha", today_text(), False),
        ("Cobrador", "CORREDOR - USUARIO", False),
        ("Clientes registrados", str(total_clientes), False),
        ("Pagos registrados", str(len(pagos)), False),
        ("Clientes no pago", str(len(no_pagos)), False),
        ("Aplazados", str(len(aplazados)), False),
        ("Recaudo esperado", money(recaudo_esperado), False),
        ("Recaudo del dia", money(recaudo_dia), True),
        ("Ingresos de caja", money(ingresos), False),
        ("Egresos de caja", money(egresos), False),
        ("Saldo final en caja", money(saldo_caja), True),
        ("Pendientes nube", str(pendientes_sync), False),
    ])

    pdf.section("Pagos y aportes registrados")
    pagos_rows = [[
        shorten(t.get("cliente", ""), 28),
        shorten(t.get("tipo", ""), 9),
        money(t.get("valor", 0)),
        t.get("metodo", ""),
        t.get("fecha", ""),
    ] for t in pagos[-80:]]
    pdf.table(["Cliente", "Tipo", "Valor", "Metodo", "Fecha"], pagos_rows, [180, 60, 80, 75, 95])

    pdf.section("Clientes no pago y aplazados")
    especiales = [c for c in CLIENTES if c.get("estado") in ("no_pago", "siguiente")]
    especiales_rows = []
    for c in especiales:
        prox = display_date_from_iso(c.get("proximo_cobro", "")) if "display_date_from_iso" in globals() else c.get("proximo_cobro", "")
        especiales_rows.append([
            shorten(c.get("nombre", ""), 28),
            estado_texto(c.get("estado", "pendiente")),
            money(c.get("saldo", 0)),
            prox,
        ])
    pdf.table(["Cliente", "Estado", "Saldo", "Prox. cobro"], especiales_rows, [210, 90, 90, 100])

    pdf.section("Movimientos de caja")
    mov_rows = [[
        shorten(m.get("tipo", ""), 8),
        shorten(m.get("concepto", ""), 26),
        money(m.get("valor", 0)),
        shorten(m.get("observaciones", ""), 24),
    ] for m in MOVIMIENTOS_CAJA[-80:]]
    pdf.table(["Tipo", "Concepto", "Valor", "Observacion"], mov_rows, [65, 180, 90, 155])

    pdf.section("Clientes activos")
    cliente_rows = [[
        shorten(c.get("nombre", ""), 26),
        money(c.get("cuota", 0)),
        money(c.get("saldo", 0)),
        estado_texto(c.get("estado", "pendiente")),
        c.get("cobro", "Diario"),
    ] for c in CLIENTES[-120:]]
    pdf.table(["Cliente", "Cuota", "Saldo", "Estado", "Cobro"], cliente_rows, [170, 75, 90, 80, 75])

    pdf.section("Observacion")
    pdf.paragraph("Este reporte resume la gestion diaria del cobrador, los recaudos, movimientos de caja y clientes con novedades.")
    pdf.paragraph("El archivo sirve como soporte administrativo del cierre de ruta.")

    return pdf.save()


def show_popup(title, message, height=240):
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))

    label = Label(
        text=message,
        color=WHITE,
        font_size="14sp",
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    btn = Button(
        text="Aceptar",
        background_normal="",
        background_color=BLUE,
        color=WHITE,
        bold=True,
        size_hint_y=None,
        height=dp(46),
    )

    content.add_widget(label)
    content.add_widget(btn)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(height),
        auto_dismiss=False,
    )

    btn.bind(on_release=popup.dismiss)
    popup.open()


def confirm_popup(title, message, on_confirm):
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))

    label = Label(
        text=message,
        color=WHITE,
        font_size="14sp",
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))

    cancel = Button(
        text="Cancelar",
        background_normal="",
        background_color=(0.55, 0.58, 0.63, 1),
        color=WHITE,
        bold=True,
    )

    accept = Button(
        text="Confirmar",
        background_normal="",
        background_color=DANGER,
        color=WHITE,
        bold=True,
    )

    buttons.add_widget(cancel)
    buttons.add_widget(accept)

    content.add_widget(label)
    content.add_widget(buttons)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(245),
        auto_dismiss=False,
    )

    cancel.bind(on_release=popup.dismiss)

    def do_confirm(*_):
        popup.dismiss()
        on_confirm()

    accept.bind(on_release=do_confirm)
    popup.open()


def estado_texto(estado):
    if estado == "pagado":
        return "PAGADO"
    if estado == "aporte":
        return "APORTE"
    if estado == "no_pago":
        return "NO PAGO"
    if estado == "siguiente":
        return "SIG. DIA"
    return "PENDIENTE"


def estado_colores(estado):
    if estado in ("pagado", "aporte"):
        return STATUS_GREEN, STATUS_BORDER_GREEN, estado_texto(estado)
    if estado == "no_pago":
        return STATUS_RED, STATUS_BORDER_RED, "NO PAGO"
    return STATUS_YELLOW, STATUS_BORDER_YELLOW, estado_texto(estado)


# ============================================================
# BASE DE DATOS SQLITE
# ============================================================

def get_db_path():
    """
    Ruta corregida:
    - En Android/iOS: directorio privado de la app.
    - En PC: junto a main.py dentro del proyecto app-cobros-v12-final.
    """
    if platform in ("android", "ios"):
        try:
            app = App.get_running_app()
            if app and getattr(app, "user_data_dir", None):
                db_dir = Path(app.user_data_dir)
                db_dir.mkdir(parents=True, exist_ok=True)
                return str(db_dir / "cobros_v12.db")
        except Exception:
            pass

    return str(Path(__file__).resolve().parent / "cobros_v12.db")


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return column_name in [row[1] for row in cursor.fetchall()]


def ensure_column(cursor, table_name, column_name, column_definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            direccion TEXT,
            producto TEXT NOT NULL DEFAULT '5 - CREDITO EN EFECTIVO',
            valor_credito INTEGER NOT NULL DEFAULT 0,
            interes REAL NOT NULL DEFAULT 0,
            total_credito INTEGER NOT NULL DEFAULT 0,
            cuota INTEGER NOT NULL DEFAULT 0,
            numero_cuotas INTEGER NOT NULL DEFAULT 1,
            saldo INTEGER NOT NULL DEFAULT 0,
            pagadas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0,
            cobro TEXT NOT NULL DEFAULT 'Diario',
            estado TEXT NOT NULL DEFAULT 'pendiente',
            ultimo_tipo TEXT NOT NULL DEFAULT 'Pendiente por cobrar',
            codeudor_documento TEXT,
            codeudor_nombre TEXT,
            codeudor_movil TEXT,
            valor_seguro INTEGER NOT NULL DEFAULT 0,
            beneficiario TEXT,
            obs_seguro TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            proximo_cobro TEXT,
            ultima_fecha_pago TEXT,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Migración automática para bases viejas
    columns = [
        ("documento", "TEXT"),
        ("telefono", "TEXT"),
        ("direccion", "TEXT"),
        ("producto", "TEXT NOT NULL DEFAULT '5 - CREDITO EN EFECTIVO'"),
        ("valor_credito", "INTEGER NOT NULL DEFAULT 0"),
        ("interes", "REAL NOT NULL DEFAULT 0"),
        ("total_credito", "INTEGER NOT NULL DEFAULT 0"),
        ("cuota", "INTEGER NOT NULL DEFAULT 0"),
        ("numero_cuotas", "INTEGER NOT NULL DEFAULT 1"),
        ("saldo", "INTEGER NOT NULL DEFAULT 0"),
        ("pagadas", "INTEGER NOT NULL DEFAULT 0"),
        ("pendientes", "INTEGER NOT NULL DEFAULT 0"),
        ("cobro", "TEXT NOT NULL DEFAULT 'Diario'"),
        ("estado", "TEXT NOT NULL DEFAULT 'pendiente'"),
        ("ultimo_tipo", "TEXT NOT NULL DEFAULT 'Pendiente por cobrar'"),
        ("codeudor_documento", "TEXT"),
        ("codeudor_nombre", "TEXT"),
        ("codeudor_movil", "TEXT"),
        ("valor_seguro", "INTEGER NOT NULL DEFAULT 0"),
        ("beneficiario", "TEXT"),
        ("obs_seguro", "TEXT"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("proximo_cobro", "TEXT"),
        ("ultima_fecha_pago", "TEXT"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
    ]

    for name, definition in columns:
        ensure_column(cursor, "clientes", name, definition)

    # Compatibilidad con versiones viejas que tenían saldo/cuota pero no valor_credito/total_credito
    cursor.execute("""
        UPDATE clientes
        SET valor_credito = saldo
        WHERE (valor_credito IS NULL OR valor_credito = 0) AND saldo > 0
    """)

    cursor.execute("""
        UPDATE clientes
        SET total_credito = saldo
        WHERE (total_credito IS NULL OR total_credito = 0) AND saldo > 0
    """)

    cursor.execute("""
        UPDATE clientes
        SET numero_cuotas = pendientes
        WHERE (numero_cuotas IS NULL OR numero_cuotas = 0) AND pendientes > 0
    """)

    cursor.execute("UPDATE clientes SET created_at = ? WHERE created_at IS NULL OR created_at = ''", (now_text(),))
    cursor.execute("UPDATE clientes SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''", (now_text(),))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            cliente TEXT NOT NULL,
            tipo TEXT NOT NULL,
            valor INTEGER NOT NULL DEFAULT 0,
            metodo TEXT,
            fecha TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    for name, definition in [
        ("cliente_id", "INTEGER"),
        ("cliente", "TEXT NOT NULL DEFAULT ''"),
        ("tipo", "TEXT NOT NULL DEFAULT ''"),
        ("valor", "INTEGER NOT NULL DEFAULT 0"),
        ("metodo", "TEXT"),
        ("fecha", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        ensure_column(cursor, "transacciones", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            concepto TEXT,
            valor INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT,
            fecha TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    for name, definition in [
        ("tipo", "TEXT NOT NULL DEFAULT ''"),
        ("concepto", "TEXT"),
        ("valor", "INTEGER NOT NULL DEFAULT 0"),
        ("observaciones", "TEXT"),
        ("fecha", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        ensure_column(cursor, "movimientos_caja", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eliminados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidad TEXT NOT NULL,
            entidad_id INTEGER NOT NULL,
            cobrador_id TEXT,
            synced INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def load_clients_from_db():
    global CLIENTES
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, synced
        FROM clientes
        ORDER BY nombre ASC
    """)

    CLIENTES = [dict(row) for row in cursor.fetchall()]
    conn.close()


def load_transacciones_from_db():
    global TRANSACCIONES
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, cliente_id, cliente, tipo, valor, metodo, fecha, synced
        FROM transacciones
        ORDER BY id ASC
    """)

    TRANSACCIONES = [dict(row) for row in cursor.fetchall()]
    conn.close()


def load_movimientos_from_db():
    global MOVIMIENTOS_CAJA
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tipo, concepto, valor, observaciones, fecha, synced
        FROM movimientos_caja
        ORDER BY id ASC
    """)

    MOVIMIENTOS_CAJA = [dict(row) for row in cursor.fetchall()]
    conn.close()


def refresh_memory_from_db():
    update_due_statuses()
    load_clients_from_db()
    load_transacciones_from_db()
    load_movimientos_from_db()


def insert_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (
            documento, nombre, telefono, direccion, producto,
            valor_credito, interes, total_credito, cuota, numero_cuotas,
            saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
            codeudor_documento, codeudor_nombre, codeudor_movil,
            valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
            proximo_cobro, ultima_fecha_pago, synced
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
        cliente.get("producto", "5 - CREDITO EN EFECTIVO"),
        int(cliente.get("valor_credito", 0)),
        float(cliente.get("interes", 0)),
        int(cliente.get("total_credito", 0)),
        int(cliente.get("cuota", 0)),
        int(cliente.get("numero_cuotas", 1)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("cobro", "Diario"),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("codeudor_documento", ""),
        cliente.get("codeudor_nombre", ""),
        cliente.get("codeudor_movil", ""),
        int(cliente.get("valor_seguro", 0)),
        cliente.get("beneficiario", ""),
        cliente.get("obs_seguro", ""),
        now_text(),
        now_text(),
        cliente.get("proximo_cobro", iso_today()),
        cliente.get("ultima_fecha_pago", ""),
        int(cliente.get("synced", 0)),
    ))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET documento = ?, nombre = ?, telefono = ?, direccion = ?, producto = ?,
            valor_credito = ?, interes = ?, total_credito = ?, cuota = ?, numero_cuotas = ?,
            saldo = ?, pagadas = ?, pendientes = ?, cobro = ?, estado = ?, ultimo_tipo = ?,
            codeudor_documento = ?, codeudor_nombre = ?, codeudor_movil = ?,
            valor_seguro = ?, beneficiario = ?, obs_seguro = ?, updated_at = ?,
            proximo_cobro = ?, ultima_fecha_pago = ?, synced = ?
        WHERE id = ?
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
        cliente.get("producto", "5 - CREDITO EN EFECTIVO"),
        int(cliente.get("valor_credito", 0)),
        float(cliente.get("interes", 0)),
        int(cliente.get("total_credito", 0)),
        int(cliente.get("cuota", 0)),
        int(cliente.get("numero_cuotas", 1)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("cobro", "Diario"),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("codeudor_documento", ""),
        cliente.get("codeudor_nombre", ""),
        cliente.get("codeudor_movil", ""),
        int(cliente.get("valor_seguro", 0)),
        cliente.get("beneficiario", ""),
        cliente.get("obs_seguro", ""),
        now_text(),
        cliente.get("proximo_cobro", ""),
        cliente.get("ultima_fecha_pago", ""),
        int(cliente.get("synced", 0)),
        int(cliente.get("id")),
    ))

    conn.commit()
    conn.close()


def mark_deleted_local(entidad, entidad_id):
    """
    Guarda una marca local de eliminación para que Supabase no restaure
    registros que el usuario ya borró.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO eliminados (entidad, entidad_id, cobrador_id, synced, deleted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            entidad,
            int(entidad_id),
            COBRADOR_ID if "COBRADOR_ID" in globals() else "",
            0,
            now_text(),
        ))

        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR mark_deleted_local:", error)


def get_deleted_ids(entidad):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT entidad_id FROM eliminados WHERE entidad = ?", (entidad,))
        ids = {int(row[0]) for row in cursor.fetchall()}
        conn.close()
        return ids
    except Exception:
        return set()


def mark_deleted_synced(entidad, entidad_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE eliminados SET synced = 1
            WHERE entidad = ? AND entidad_id = ?
        """, (entidad, int(entidad_id)))
        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR mark_deleted_synced:", error)


def delete_client_db(cliente_id):
    """
    Elimina un cliente/préstamo localmente, corrige caja y marca el registro
    como eliminado para que no vuelva a descargarse desde Supabase.
    """
    cliente = get_client_by_id(cliente_id)

    conn = get_connection()
    cursor = conn.cursor()

    if cliente:
        nombre_cliente = str(cliente.get("nombre", "")).strip()
        valor_credito = int(cliente.get("valor_credito") or 0)

        cursor.execute("""
            DELETE FROM movimientos_caja
            WHERE tipo = 'Egreso'
              AND concepto = 'Desembolso préstamo'
              AND valor = ?
              AND observaciones LIKE ?
        """, (valor_credito, f"%{nombre_cliente}%"))

        if cursor.rowcount == 0:
            cursor.execute("""
                DELETE FROM movimientos_caja
                WHERE tipo = 'Egreso'
                  AND concepto = 'Desembolso préstamo'
                  AND valor = ?
            """, (valor_credito,))

    cursor.execute("DELETE FROM transacciones WHERE cliente_id = ?", (int(cliente_id),))
    cursor.execute("DELETE FROM clientes WHERE id = ?", (int(cliente_id),))

    conn.commit()
    conn.close()

    mark_deleted_local("cliente", int(cliente_id))


def get_client_by_id(cliente_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, synced
        FROM clientes
        WHERE id = ?
    """, (int(cliente_id),))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def reset_client_status_db(cliente_id):
    cliente = get_client_by_id(cliente_id)
    if cliente:
        cliente["estado"] = "pendiente"
        cliente["ultimo_tipo"] = "Pendiente por cobrar"
        update_client_db(cliente)


def insert_transaction_db(transaccion):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO transacciones
        (cliente_id, cliente, tipo, valor, metodo, fecha, synced)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        transaccion.get("cliente_id"),
        transaccion.get("cliente", ""),
        transaccion.get("tipo", ""),
        int(transaccion.get("valor", 0)),
        transaccion.get("metodo", ""),
        transaccion.get("fecha", today_text()),
        int(transaccion.get("synced", 0)),
    ))

    conn.commit()
    conn.close()


def insert_movement_db(movimiento):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movimientos_caja
        (tipo, concepto, valor, observaciones, fecha, synced)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        movimiento.get("tipo", ""),
        movimiento.get("concepto", ""),
        int(movimiento.get("valor", 0)),
        movimiento.get("observaciones", ""),
        movimiento.get("fecha", today_text()),
        int(movimiento.get("synced", 0)),
    ))

    conn.commit()
    conn.close()


def clear_all_data_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacciones")
    cursor.execute("DELETE FROM movimientos_caja")
    cursor.execute("DELETE FROM clientes")
    conn.commit()
    conn.close()
    refresh_memory_from_db()


def mark_all_as_synced():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET synced = 1")
    cursor.execute("UPDATE transacciones SET synced = 1")
    cursor.execute("UPDATE movimientos_caja SET synced = 1")
    conn.commit()
    conn.close()
    refresh_memory_from_db()


def count_pending_sync():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clientes WHERE synced = 0")
    clientes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transacciones WHERE synced = 0")
    tx = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movimientos_caja WHERE synced = 0")
    mv = cursor.fetchone()[0]
    conn.close()
    return clientes + tx + mv



def current_cash_balance():
    """
    Calcula saldo disponible en caja:
    ingresos + recaudos de clientes - egresos.
    """
    try:
        ingresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Ingreso")
        egresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Egreso")
        recaudos = sum(int(t.get("valor", 0)) for t in TRANSACCIONES if t.get("tipo") in ("Cuota", "Aporte"))
        return ingresos + recaudos - egresos
    except Exception:
        return 0


def update_due_statuses():
    """
    Si el cliente pagó y ya llegó su próxima fecha de cobro,
    vuelve automáticamente a pendiente para que aparezca amarillo.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        today = iso_today()

        cursor.execute("""
            UPDATE clientes
            SET estado = 'pendiente',
                ultimo_tipo = 'Pendiente por cobrar',
                updated_at = ?
            WHERE estado IN ('pagado', 'aporte')
              AND proximo_cobro IS NOT NULL
              AND proximo_cobro <> ''
              AND proximo_cobro <= ?
              AND pendientes > 0
        """, (now_text(), today))

        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR update_due_statuses:", error)



def supabase_configured():
    return (
        SYNC_ENABLED
        and SUPABASE_URL.startswith("http")
        and len(SUPABASE_ANON_KEY) > 20
        and "PEGAR_AQUI" not in SUPABASE_URL
        and "PEGAR_AQUI" not in SUPABASE_ANON_KEY
        and "PEGAR_AQUI" not in COBRADOR_ID
    )


def supabase_request(table_name, payload, method="POST"):
    if not supabase_configured():
        return False, "Supabase no configurado"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            return (200 <= status < 300), f"HTTP {status}"
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}"
    except Exception as error:
        return False, str(error)



def supabase_get(table_name):
    """
    Descarga datos desde Supabase filtrando por cobrador_id.
    Sirve para restaurar datos en un celular nuevo.
    """
    if not supabase_configured():
        return False, "Supabase no configurado", []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}?select=*&cobrador_id=eq.{COBRADOR_ID}"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }

    request = urllib.request.Request(url=url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
            if 200 <= status < 300:
                return True, "OK", json.loads(raw or "[]")
            return False, f"HTTP {status}", []
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}", []
    except Exception as error:
        return False, str(error), []


def pull_clients_from_cloud():
    ok, msg, rows = supabase_get("clientes")
    if not ok:
        return False, msg

    if not rows:
        return True, "Sin clientes en nube"

    deleted_client_ids = get_deleted_ids("cliente")
    rows = [r for r in rows if int(r.get("id")) not in deleted_client_ids]

    if not rows:
        return True, "Clientes de nube ya estaban eliminados localmente"

    conn = get_connection()
    cursor = conn.cursor()

    for r in rows:
        cursor.execute("""
            INSERT OR REPLACE INTO clientes (
                id, documento, nombre, telefono, direccion, producto,
                valor_credito, interes, total_credito, cuota, numero_cuotas,
                saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
                codeudor_documento, codeudor_nombre, codeudor_movil,
                valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
                proximo_cobro, ultima_fecha_pago, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r.get("id")),
            r.get("documento", ""),
            r.get("nombre", "SIN NOMBRE"),
            r.get("telefono", ""),
            r.get("direccion", ""),
            r.get("producto", "5 - CREDITO EN EFECTIVO"),
            int(r.get("valor_credito") or 0),
            float(r.get("interes") or 0),
            int(r.get("total_credito") or 0),
            int(r.get("cuota") or 0),
            int(r.get("numero_cuotas") or 1),
            int(r.get("saldo") or 0),
            int(r.get("pagadas") or 0),
            int(r.get("pendientes") or 0),
            r.get("cobro", "Diario"),
            r.get("estado", "pendiente"),
            r.get("ultimo_tipo", "Pendiente por cobrar"),
            r.get("codeudor_documento", ""),
            r.get("codeudor_nombre", ""),
            r.get("codeudor_movil", ""),
            int(r.get("valor_seguro") or 0),
            r.get("beneficiario", ""),
            r.get("obs_seguro", ""),
            r.get("created_at", now_text()),
            r.get("updated_at", now_text()),
            r.get("proximo_cobro", ""),
            r.get("ultima_fecha_pago", ""),
            1,
        ))

    conn.commit()
    conn.close()
    return True, f"Clientes descargados: {len(rows)}"


def pull_transactions_from_cloud():
    ok, msg, rows = supabase_get("transacciones")
    if not ok:
        return False, msg

    if not rows:
        return True, "Sin transacciones en nube"

    deleted_client_ids = get_deleted_ids("cliente")
    rows = [r for r in rows if not r.get("cliente_id") or int(r.get("cliente_id")) not in deleted_client_ids]

    if not rows:
        return True, "Transacciones de clientes eliminados omitidas"

    conn = get_connection()
    cursor = conn.cursor()

    for r in rows:
        cursor.execute("""
            INSERT OR REPLACE INTO transacciones (
                id, cliente_id, cliente, tipo, valor, metodo, fecha, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r.get("id")),
            r.get("cliente_id"),
            r.get("cliente", ""),
            r.get("tipo", ""),
            int(r.get("valor") or 0),
            r.get("metodo", ""),
            r.get("fecha", today_text()),
            1,
        ))

    conn.commit()
    conn.close()
    return True, f"Transacciones descargadas: {len(rows)}"


def pull_movements_from_cloud():
    ok, msg, rows = supabase_get("movimientos_caja")
    if not ok:
        return False, msg

    if not rows:
        return True, "Sin movimientos en nube"

    conn = get_connection()
    cursor = conn.cursor()

    for r in rows:
        cursor.execute("""
            INSERT OR REPLACE INTO movimientos_caja (
                id, tipo, concepto, valor, observaciones, fecha, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r.get("id")),
            r.get("tipo", ""),
            r.get("concepto", ""),
            int(r.get("valor") or 0),
            r.get("observaciones", ""),
            r.get("fecha", today_text()),
            1,
        ))

    conn.commit()
    conn.close()
    return True, f"Movimientos descargados: {len(rows)}"


def supabase_delete_where(table_name, query_filter):
    """
    Ejecuta DELETE en Supabase usando filtros REST.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}?{query_filter}"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    request = urllib.request.Request(
        url=url,
        headers=headers,
        method="DELETE",
    )

    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            if 200 <= status < 300:
                return True, "OK"
            return False, f"HTTP {status}"
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}"
    except Exception as error:
        return False, str(error)


def delete_remote_client_bundle(cliente):
    """
    Elimina en Supabase el cliente, sus transacciones y el egreso de desembolso.
    """
    if not cliente or not supabase_configured():
        return False, "Supabase no configurado o cliente vacío"

    cliente_id = int(cliente.get("id"))
    valor_credito = int(cliente.get("valor_credito") or 0)

    results = []

    results.append(supabase_delete_where(
        "transacciones",
        f"cliente_id=eq.{cliente_id}&cobrador_id=eq.{COBRADOR_ID}"
    ))

    results.append(supabase_delete_where(
        "movimientos_caja",
        f"cobrador_id=eq.{COBRADOR_ID}&tipo=eq.Egreso&valor=eq.{valor_credito}"
    ))

    results.append(supabase_delete_where(
        "clientes",
        f"id=eq.{cliente_id}&cobrador_id=eq.{COBRADOR_ID}"
    ))

    ok = all(item[0] for item in results)
    msg = " | ".join(item[1] for item in results)

    if ok:
        mark_deleted_synced("cliente", cliente_id)

    return ok, msg



def pull_all_from_cloud():
    """
    Descarga toda la informacion de Supabase hacia SQLite local.
    Ideal para celular nuevo o app recien instalada.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    results = [
        pull_clients_from_cloud(),
        pull_transactions_from_cloud(),
        pull_movements_from_cloud(),
    ]

    refresh_memory_from_db()

    ok = all(item[0] for item in results)
    msg = " | ".join(item[1] for item in results)

    return ok, msg



def sync_clients_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago
        FROM clientes
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin clientes pendientes"
    payload = []
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
        payload.append(row)
    ok, msg = supabase_request("clientes", payload)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE clientes SET synced = 1 WHERE id IN ({placeholders})", ids)
        conn.commit()
    conn.close()
    return ok, msg


def sync_transactions_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, cliente_id, cliente, tipo, valor, metodo, fecha
        FROM transacciones
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin transacciones pendientes"
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
    ok, msg = supabase_request("transacciones", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE transacciones SET synced = 1 WHERE id IN ({placeholders})", ids)
        conn.commit()
    conn.close()
    return ok, msg


def sync_movements_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, tipo, concepto, valor, observaciones, fecha
        FROM movimientos_caja
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin movimientos pendientes"
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
    ok, msg = supabase_request("movimientos_caja", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE movimientos_caja SET synced = 1 WHERE id IN ({placeholders})", ids)
        conn.commit()
    conn.close()
    return ok, msg


def sync_all_to_cloud(silent=True):
    """
    Sincronizacion bidireccional basica:
    1. Sube pendientes locales a Supabase.
    2. Descarga registros de Supabase al SQLite local.
    3. Si no hay internet, no borra nada y reintenta despues.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    try:
        refresh_memory_from_db()

        push_results = [
            sync_clients_to_cloud(),
            sync_transactions_to_cloud(),
            sync_movements_to_cloud(),
        ]

        pull_result = pull_all_from_cloud()

        refresh_memory_from_db()

        all_ok = all(item[0] for item in push_results) and pull_result[0]
        message = " | ".join(item[1] for item in push_results + [pull_result])

        return all_ok, message
    except Exception as error:
        return False, str(error)




# ============================================================
# WIDGETS BASE
# ============================================================

class RoundedBox(BoxLayout):
    bg_color = ObjectProperty(WHITE)
    radius = NumericProperty(14)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "padding" not in kwargs:
            self.padding = dp(12)
        if "spacing" not in kwargs:
            self.spacing = dp(8)

        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])

        self.bind(pos=self._update_rect, size=self._update_rect, bg_color=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class Header(BoxLayout):
    def __init__(self, title, show_back=False, on_back=None, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(66), **kwargs)
        self.padding = [dp(12), dp(8), dp(12), dp(8)]
        self.spacing = dp(8)

        with self.canvas.before:
            Color(*BLUE)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        if show_back:
            back = Button(
                text="<",
                size_hint_x=None,
                width=dp(42),
                background_normal="",
                background_color=BLUE_DARK,
                color=WHITE,
                bold=True,
                font_size="18sp",
            )
            if on_back:
                back.bind(on_release=lambda *_: on_back())
            self.add_widget(back)

        label = Label(text=title, color=WHITE, bold=True, font_size="17sp", halign="left", valign="middle")
        label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.add_widget(label)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


class FieldLabel(Label):
    def __init__(self, text, **kwargs):
        super().__init__(
            text=text,
            color=MUTED,
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            halign="left",
            valign="middle",
            **kwargs
        )
        self.bind(size=lambda instance, value: setattr(instance, "text_size", value))


class AppTextInput(TextInput):
    def __init__(self, hint_text="", text="", multiline=False, readonly=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=text,
            multiline=multiline,
            readonly=readonly,
            size_hint_y=None,
            height=dp(44) if not multiline else dp(88),
            background_normal="",
            background_color=(0.93, 0.95, 0.98, 1) if readonly else WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
            **kwargs
        )


class MoneyTextInput(AppTextInput):
    """
    Campo para valores monetarios.
    Permite escribir 500000 y lo convierte a 500.000 automáticamente.
    to_int() ya entiende puntos, así que no rompe los cálculos.
    """
    def __init__(self, hint_text="", text="", readonly=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=str(text) if text not in (None, "") else "",
            readonly=readonly,
            **kwargs
        )
        self._formatting = False
        self.bind(text=self._on_money_text)
        if self.text:
            Clock.schedule_once(lambda *_: self._format_current_text(), 0)

    def _on_money_text(self, *_):
        if self._formatting:
            return
        self._format_current_text()

    def _format_current_text(self):
        raw = str(self.text or "")
        digits = "".join(ch for ch in raw if ch.isdigit())

        if digits == "":
            return

        formatted = format_thousands(int(digits))

        if formatted != raw:
            self._formatting = True
            self.text = formatted
            self.cursor = (len(self.text), 0)
            self._formatting = False


class SmallButton(Button):
    def __init__(self, text, bg_color=BLUE, text_color=WHITE, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=bg_color,
            color=text_color,
            bold=True,
            font_size="12sp",
            **kwargs
        )


class PillButton(Button):
    def __init__(self, text, bg_color=DARK, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=bg_color,
            color=WHITE,
            bold=True,
            font_size="12sp",
            **kwargs
        )


class DetailRow(BoxLayout):
    def __init__(self, label, value, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6), **kwargs)

        left = Label(text=label, color=MUTED, bold=True, font_size="12sp", halign="left", valign="middle", size_hint_x=0.42)
        right = Label(text=str(value), color=TEXT, font_size="12sp", halign="right", valign="middle", size_hint_x=0.58)
        left.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        right.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(left)
        self.add_widget(right)


class NavItem(BoxLayout):
    def __init__(self, app, label, screen, icon_name, active=False, **kwargs):
        super().__init__(orientation="vertical", padding=[dp(6), dp(4), dp(6), dp(4)], spacing=dp(2), **kwargs)
        self.app = app
        self.screen = screen
        bg_color = GOLD if active else (0.91, 0.93, 0.96, 1)

        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        source = asset_path(icon_name)
        if source:
            icon = Image(source=source, size_hint_y=None, height=dp(24), allow_stretch=True, keep_ratio=True)
        else:
            icon = Label(text=label[:2].upper(), color=DARK, bold=True, font_size="13sp", size_hint_y=None, height=dp(24))

        text = Label(text=label, color=DARK, bold=active, font_size="11sp", size_hint_y=None, height=dp(22), halign="center")
        text.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(icon)
        self.add_widget(text)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.app.go(self.screen)
            return True
        return super().on_touch_down(touch)


class BottomNav(BoxLayout):
    def __init__(self, app, active="clientes", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(66),
            padding=[dp(8), dp(7), dp(8), dp(7)],
            spacing=dp(8),
            **kwargs
        )
        self.app = app

        with self.canvas.before:
            Color(*WHITE)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        for key, label, screen, icon_name in [
            ("clientes", "Clientes", "clientes", "clientes.png"),
            ("nuevo", "Nuevo", "nuevo_cliente", "nuevo.png"),
            ("caja", "Caja", "movimientos", "caja.png"),
        ]:
            self.add_widget(NavItem(self.app, label, screen, icon_name, active=(key == active)))

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


# ============================================================
# CLIENTES
# ============================================================

class ClienteCard(RoundedBox):
    def __init__(self, cliente, on_click, **kwargs):
        estado = cliente.get("estado", "pendiente")
        bg_status, border_color, badge_text = estado_colores(estado)

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(116),
            padding=[dp(0), dp(0), dp(12), dp(0)],
            spacing=dp(0),
            **kwargs
        )
        self.bg_color = bg_status
        self.cliente = cliente
        self.on_click = on_click

        side = BoxLayout(size_hint_x=None, width=dp(8))
        with side.canvas.before:
            Color(*border_color)
            side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
        side.bind(pos=lambda w, *_: setattr(w.rect, "pos", w.pos))
        side.bind(size=lambda w, *_: setattr(w.rect, "size", w.size))

        body = BoxLayout(orientation="vertical", padding=[dp(12), dp(9), dp(0), dp(9)], spacing=dp(5))

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8))
        initial = cliente.get("nombre", "C")[0].upper()

        avatar = Label(text=initial, size_hint_x=None, width=dp(34), color=WHITE, bold=True, font_size="16sp")
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(17)])
        avatar.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        avatar.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name = Label(text=cliente.get("nombre", "SIN NOMBRE"), color=TEXT, bold=True, font_size="13sp", halign="left", valign="middle")
        name.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        badge = Label(
            text=badge_text,
            size_hint_x=None,
            width=dp(84),
            color=WHITE if badge_text != "PENDIENTE" else DARK,
            bold=True,
            font_size="9sp",
            halign="center",
            valign="middle",
        )
        badge_bg = border_color if badge_text != "PENDIENTE" else GOLD
        with badge.canvas.before:
            Color(*badge_bg)
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        badge.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        top.add_widget(avatar)
        top.add_widget(name)
        top.add_widget(badge)

        amounts = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8))
        cuota = Label(text=f"Cuota: [b]{money(cliente.get('cuota', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="left")
        saldo = Label(text=f"Saldo: [b]{money(cliente.get('saldo', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="right")
        cuota.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        saldo.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        amounts.add_widget(cuota)
        amounts.add_widget(saldo)

        extra = Label(text=f"Tel: {cliente.get('telefono', '')} | Pendientes: {cliente.get('pendientes', 0)}", color=MUTED, font_size="10sp", halign="left", size_hint_y=None, height=dp(18))
        hint = Label(text="Tocar para gestionar", color=BLUE, bold=True, font_size="10sp", halign="left", size_hint_y=None, height=dp(18))
        extra.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        hint.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        body.add_widget(top)
        body.add_widget(amounts)
        body.add_widget(extra)
        body.add_widget(hint)

        self.add_widget(side)
        self.add_widget(body)
        self.bind(on_touch_down=self._pressed)

    def _pressed(self, widget, touch):
        if self.collide_point(*touch.pos):
            self.on_click(self.cliente)
            return True
        return False


class ClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="clientes", **kwargs)
        self.app_ref = None

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("::V12:: Lista de Clientes"))

        tools = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(72), padding=[dp(12), dp(9), dp(12), dp(9)])
        row = BoxLayout(orientation="horizontal", spacing=dp(8))

        self.search = TextInput(
            hint_text="Buscar cliente...",
            multiline=False,
            background_normal="",
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
        )
        self.search.bind(text=lambda *_: self.render_clients())

        summary = Button(text="RES", size_hint_x=None, width=dp(54), background_normal="", background_color=GOLD, color=DARK, bold=True, font_size="12sp")
        summary.bind(on_release=lambda *_: self.app_ref.go("resumen"))

        row.add_widget(self.search)
        row.add_widget(summary)
        tools.add_widget(row)
        root.add_widget(tools)

        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(10), dp(12), dp(80)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))
        self.scroll.add_widget(self.client_list)
        root.add_widget(self.scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()

        # Si el celular esta nuevo y no tiene SQLite local,
        # intenta restaurar automaticamente desde Supabase.
        if not CLIENTES and supabase_configured():
            ok, msg = pull_all_from_cloud()
            print("RESTORE FROM CLOUD:", ok, msg)
            refresh_memory_from_db()

        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="clientes"))
        self.render_clients()

    def confirm_clear(self):
        confirm_popup("Limpiar datos", "Esto borrará clientes, pagos y movimientos.\nLa app quedará vacía para uso personal.", self.clear_all)

    def clear_all(self):
        clear_all_data_db()
        self.search.text = ""
        self.render_clients()
        show_popup("Datos limpiados", "La app quedó vacía para uso personal.")

    def render_clients(self):
        if not self.app_ref:
            return

        query = (self.search.text or "").strip().lower()
        self.client_list.clear_widgets()

        filtered = [
            cliente for cliente in CLIENTES
            if query in cliente.get("nombre", "").lower()
            or query in cliente.get("telefono", "").lower()
            or query in cliente.get("documento", "").lower()
        ]

        if not filtered:
            empty_box = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(160), padding=dp(14), spacing=dp(8))
            title = Label(text="No hay clientes registrados", color=TEXT, bold=True, font_size="15sp", halign="center", size_hint_y=None, height=dp(30))
            msg = Label(text="Presiona NUEVO para crear tu primer cliente real.", color=MUTED, font_size="12sp", halign="center", valign="middle")
            btn = SmallButton("Crear primer cliente", bg_color=BLUE)
            btn.bind(on_release=lambda *_: self.app_ref.go("nuevo_cliente"))
            title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty_box.add_widget(title)
            empty_box.add_widget(msg)
            empty_box.add_widget(btn)
            self.client_list.add_widget(empty_box)
            return

        for cliente in filtered:
            self.client_list.add_widget(ClienteCard(cliente, self.open_client))

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente")


# ============================================================
# GESTIÓN CLIENTE
# ============================================================

class GestionClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="gestion_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Gestión del Cliente", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(14), dp(14), dp(20)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        bg_status, border_color, badge_text = estado_colores(self.cliente.get("estado", "pendiente"))
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(390), padding=[dp(14), dp(12), dp(14), dp(12)], spacing=dp(8))
        card.bg_color = bg_status

        title = Label(text=self.cliente.get("nombre", "SIN NOMBRE"), color=TEXT, bold=True, font_size="17sp", halign="left", size_hint_y=None, height=dp(30))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)
        card.add_widget(DetailRow("Estado", badge_text))
        card.add_widget(DetailRow("Documento", self.cliente.get("documento") or "No registrado"))
        card.add_widget(DetailRow("Teléfono", self.cliente.get("telefono") or "No registrado"))
        card.add_widget(DetailRow("Producto", self.cliente.get("producto") or "Crédito"))
        card.add_widget(DetailRow("Valor Crédito", money(self.cliente.get("valor_credito", 0))))
        card.add_widget(DetailRow("Total Crédito", money(self.cliente.get("total_credito", 0))))
        card.add_widget(DetailRow("Cuota", money(self.cliente.get("cuota", 0))))
        card.add_widget(DetailRow("Tipo Cobro", self.cliente.get("cobro", "Diario")))
        card.add_widget(DetailRow("Saldo", money(self.cliente.get("saldo", 0))))
        card.add_widget(DetailRow("Pendientes", str(self.cliente.get("pendientes", 0))))
        card.add_widget(DetailRow("Próx. cobro", display_date_from_iso(self.cliente.get("proximo_cobro", ""))))

        content.add_widget(card)

        btn_cobrar = SmallButton("COBRAR CUOTA / APORTE", bg_color=BLUE)
        btn_editar = SmallButton("EDITAR CLIENTE Y PRÉSTAMO", bg_color=GOLD, text_color=DARK)
        btn_reset = SmallButton("REINICIAR ESTADO A PENDIENTE", bg_color=(0.45, 0.48, 0.55, 1))
        btn_borrar = SmallButton("ELIMINAR CLIENTE", bg_color=DANGER)

        btn_cobrar.bind(on_release=lambda *_: self.go_cobrar())
        btn_editar.bind(on_release=lambda *_: self.go_editar())
        btn_reset.bind(on_release=lambda *_: self.reset_estado())
        btn_borrar.bind(on_release=lambda *_: self.confirm_delete())

        content.add_widget(btn_cobrar)
        content.add_widget(btn_editar)
        content.add_widget(btn_reset)
        content.add_widget(btn_borrar)

        help_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(154), padding=[dp(14), dp(12), dp(14), dp(12)])
        help_card.add_widget(Label(text="Regla del sistema", color=TEXT, bold=True, font_size="14sp", halign="center", size_hint_y=None, height=dp(24)))
        for label, value in [
            ("Verde", "Pagó cuota o realizó aporte."),
            ("Amarillo", "Pendiente o siguiente día."),
            ("Rojo", "Cliente marcado como no pago."),
            ("Bloqueo", "Si ya está verde, solo permite aporte."),
        ]:
            help_card.add_widget(DetailRow(label, value))

        content.add_widget(help_card)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def go_cobrar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("cuota")

    def go_editar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("editar_cliente")

    def reset_estado(self):
        reset_client_status_db(self.cliente.get("id"))
        refresh_memory_from_db()
        show_popup("Estado reiniciado", "El cliente quedó pendiente por cobrar.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)

    def confirm_delete(self):
        confirm_popup("Eliminar cliente", f"¿Eliminar a {self.cliente.get('nombre', 'este cliente')}?\nTambién se borrarán sus transacciones.", self.delete_client)

    def delete_client(self):
        cliente_eliminado = dict(self.cliente) if self.cliente else None

        # 1. Intentar eliminar primero en Supabase para que no se restaure.
        try:
            if cliente_eliminado and supabase_configured():
                ok, msg = delete_remote_client_bundle(cliente_eliminado)
                print("DELETE REMOTE:", ok, msg)
        except Exception as error:
            print("ERROR DELETE REMOTE:", error)

        # 2. Eliminar en SQLite local y corregir caja.
        delete_client_db(self.cliente.get("id"))
        refresh_memory_from_db()

        # 3. Limpiar selección y volver a la lista.
        self.app_ref.selected_client = None

        show_popup(
            "Cliente eliminado",
            "El cliente, sus transacciones y el egreso del préstamo fueron eliminados correctamente."
        )
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)

# COBRO
# ============================================================

class CuotaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="cuota", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Cuota Cliente / Ingreso Cuota", show_back=True, on_back=lambda: self.app_ref.go("gestion_cliente")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(20)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        summary = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(190), padding=dp(12), spacing=dp(6))
        summary.add_widget(Label(text=self.cliente.get("nombre", "").lower(), color=TEXT, bold=True, font_size="18sp", halign="left", size_hint_y=None, height=dp(30)))
        summary.add_widget(DetailRow("Teléfono", self.cliente.get("telefono", "")))
        summary.add_widget(DetailRow("Pagadas", str(self.cliente.get("pagadas", 0))))
        summary.add_widget(DetailRow("Pendientes", str(self.cliente.get("pendientes", 0))))
        summary.add_widget(DetailRow("Tipo Cobro", self.cliente.get("cobro", "Diario")))
        summary.add_widget(DetailRow("Saldo", money(self.cliente.get("saldo", 0))))
        content.add_widget(summary)

        action = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(132), padding=dp(12), spacing=dp(8))
        action.add_widget(FieldLabel("Tipo de transacción"))
        row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(44))
        self.tipo_buttons = []

        for index, option in enumerate(["Cuota", "Aporte", "No Pago", "Siguiente Día"]):
            btn = ToggleButton(
                text=option,
                group="tipo_cuota",
                state="down" if index == 0 else "normal",
                background_normal="",
                background_color=GOLD if index == 0 else (0.88, 0.90, 0.94, 1),
                color=DARK,
                font_size="10sp",
                bold=True,
            )
            btn.bind(on_release=self.update_tipo_colors)
            self.tipo_buttons.append(btn)
            row.add_widget(btn)

        action.add_widget(row)

        self.warning = Label(text="Seleccione el resultado del cobro.", color=MUTED, font_size="11sp", halign="left", valign="middle", size_hint_y=None, height=dp(28))
        self.warning.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        action.add_widget(self.warning)
        content.add_widget(action)

        self.apply_payment_rules()

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(360), padding=dp(12), spacing=dp(8))

        self.valor_cuota = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)), readonly=True)
        self.saldo_actual = MoneyTextInput(text=format_thousands(self.cliente.get("saldo", 0)), readonly=True)
        self.valor_pagar = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)))
        self.numero_cuotas = AppTextInput(text="1")
        self.nuevo_saldo = MoneyTextInput(text=format_thousands(max(int(self.cliente.get("saldo", 0)) - int(self.cliente.get("cuota", 0)), 0)), readonly=True)
        self.metodo_pago = Spinner(text="Efectivo", values=["Efectivo", "Transferencia"], size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)

        for label, widget in [
            ("Valor Cuota", self.valor_cuota),
            ("Saldo Actual", self.saldo_actual),
            ("Valor a Pagar", self.valor_pagar),
            ("Número de Cuotas", self.numero_cuotas),
            ("Nuevo Saldo", self.nuevo_saldo),
            ("Método de Pago", self.metodo_pago),
        ]:
            box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(48), spacing=dp(3))
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            form.add_widget(box)

        self.valor_pagar.bind(text=lambda *_: self.recalculate_balance())
        self.numero_cuotas.bind(text=lambda *_: self.recalculate_balance())

        register = SmallButton("Registrar Transacción", bg_color=BLUE)
        register.bind(on_release=lambda *_: self.register_transaction())
        form.add_widget(register)

        content.add_widget(form)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def apply_payment_rules(self):
        estado = self.cliente.get("estado", "pendiente")

        # Primero normalizamos todos los botones para evitar que "Cuota"
        # quede seleccionado internamente cuando el sistema escoge Aporte.
        for btn in self.tipo_buttons:
            btn.disabled = False
            btn.state = "normal"
            btn.background_color = (0.88, 0.90, 0.94, 1)
            btn.color = DARK

        if estado in ("pagado", "aporte"):
            self.warning.text = "Cliente en verde. No se permite otra cuota; solo aporte."
            self.warning.color = DANGER

            for btn in self.tipo_buttons:
                if btn.text == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = GOLD
                    btn.color = DARK
                else:
                    btn.disabled = True
                    btn.state = "normal"
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.40, 0.40, 0.40, 1)

        elif estado == "no_pago":
            self.warning.text = "Cliente en rojo. Si entrega dinero, registre Aporte."
            self.warning.color = DANGER

            for btn in self.tipo_buttons:
                if btn.text == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = GOLD
                    btn.color = DARK
                elif btn.text == "Cuota":
                    btn.disabled = True
                    btn.state = "normal"
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.40, 0.40, 0.40, 1)
                else:
                    btn.disabled = False
                    btn.state = "normal"
                    btn.background_color = (0.88, 0.90, 0.94, 1)
                    btn.color = DARK

        else:
            # Cliente pendiente normal: por defecto queda Cuota.
            for btn in self.tipo_buttons:
                if btn.text == "Cuota":
                    btn.state = "down"
                    btn.background_color = GOLD
                else:
                    btn.state = "normal"
                    btn.background_color = (0.88, 0.90, 0.94, 1)

    def update_tipo_colors(self, *_):
        for btn in self.tipo_buttons:
            if btn.disabled:
                continue
            btn.background_color = GOLD if btn.state == "down" else (0.88, 0.90, 0.94, 1)
            btn.color = DARK

    def selected_tipo(self):
        for btn in self.tipo_buttons:
            if not btn.disabled and btn.state == "down":
                return btn.text

        # Seguridad adicional: si por estado visual quedó bloqueado,
        # usar Aporte cuando sea el único permitido.
        estado = self.cliente.get("estado", "pendiente")
        if estado in ("pagado", "aporte", "no_pago"):
            return "Aporte"

        return "Cuota"

    def recalculate_balance(self):
        saldo = to_int(self.saldo_actual.text, 0)
        pago = to_int(self.valor_pagar.text, 0)
        self.nuevo_saldo.text = format_thousands(max(saldo - pago, 0))

    def register_transaction(self):
        tipo = self.selected_tipo()
        pago = to_int(self.valor_pagar.text, 0)
        estado_actual = self.cliente.get("estado", "pendiente")

        if estado_actual in ("pagado", "aporte", "no_pago"):
            tipo = "Aporte"

        if estado_actual in ("pagado", "aporte") and tipo != "Aporte":
            show_popup("Cobro bloqueado", "Este cliente ya está en verde.\nSolo se permite registrar Aporte.")
            return
        if estado_actual == "no_pago" and tipo == "Cuota":
            show_popup("Cobro bloqueado", "Este cliente está en rojo.\nSi entrega dinero, registre Aporte.")
            return
        if tipo in ("Cuota", "Aporte") and pago <= 0:
            show_popup("Valor inválido", "Ingrese un valor mayor a cero.")
            return

        if tipo == "Cuota":
            self.cliente["saldo"] = max(int(self.cliente.get("saldo", 0)) - pago, 0)
            self.cliente["pagadas"] = int(self.cliente.get("pagadas", 0)) + 1
            self.cliente["pendientes"] = max(int(self.cliente.get("pendientes", 0)) - 1, 0)
            self.cliente["estado"] = "pagado"
            self.cliente["ultimo_tipo"] = "Cuota pagada"
            self.cliente["ultima_fecha_pago"] = iso_today()
            self.cliente["proximo_cobro"] = next_due_date(self.cliente.get("cobro", "Diario"))
        elif tipo == "Aporte":
            self.cliente["saldo"] = max(int(self.cliente.get("saldo", 0)) - pago, 0)
            self.cliente["estado"] = "aporte"
            self.cliente["ultimo_tipo"] = "Aporte"
            self.cliente["ultima_fecha_pago"] = iso_today()
            self.cliente["proximo_cobro"] = next_due_date(self.cliente.get("cobro", "Diario"))
        elif tipo == "No Pago":
            pago = 0
            self.cliente["estado"] = "no_pago"
            self.cliente["ultimo_tipo"] = "No pago"
        elif tipo == "Siguiente Día":
            pago = 0
            self.cliente["estado"] = "siguiente"
            self.cliente["ultimo_tipo"] = "Siguiente día"
            self.cliente["proximo_cobro"] = next_due_date("Diario")

        self.cliente["synced"] = 0
        update_client_db(self.cliente)

        insert_transaction_db({
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente.get("nombre", ""),
            "tipo": tipo,
            "valor": pago,
            "metodo": self.metodo_pago.text,
            "fecha": today_text(),
            "synced": 0,
        })

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        show_popup("Transacción registrada", "Registro guardado correctamente.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)


# ============================================================
# NUEVO CLIENTE WIZARD
# ============================================================

class NuevoClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="nuevo_cliente", **kwargs)
        self.step = 1
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

        self.documento = AppTextInput(hint_text="Número de documento")
        self.nombre = AppTextInput(hint_text="Nombre completo")
        self.movil = AppTextInput(hint_text="3000000000")
        self.direccion = AppTextInput(hint_text="Dirección del cliente")

        self.producto = AppTextInput(text="5 - CREDITO EN EFECTIVO")
        self.valor_credito = MoneyTextInput(hint_text="Ej: 500.000")
        self.interes = AppTextInput(hint_text="Ej: 20")
        self.numero_cuotas = AppTextInput(hint_text="Ej: 30")
        self.total_credito = MoneyTextInput(text="0", readonly=True)
        self.valor_cuota = MoneyTextInput(text="0", readonly=True)
        self.cobro = Spinner(text="Diario", values=["Diario", "Semanal", "Quincenal", "Mensual"], size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)

        self.valor_credito.bind(text=lambda *_: self.calculate_credit())
        self.interes.bind(text=lambda *_: self.calculate_credit())
        self.numero_cuotas.bind(text=lambda *_: self.calculate_credit())

        self.documento_codeudor = AppTextInput(hint_text="Opcional")
        self.nombre_codeudor = AppTextInput(hint_text="Opcional")
        self.movil_codeudor = AppTextInput(hint_text="Opcional")

        self.valor_seguro = MoneyTextInput(hint_text="Ej: 10.000")
        self.beneficiario = AppTextInput(hint_text="Nombre beneficiario")
        self.obs_seguro = AppTextInput(hint_text="Observaciones", multiline=True)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.step = 1
        self.build()

    def calculate_credit(self):
        base = to_int(self.valor_credito.text, 0)
        interes = to_float(self.interes.text, 0)
        cuotas = to_int(self.numero_cuotas.text, 0)

        total = int(round(base * (1 + (interes / 100))))
        cuota = int(round(total / cuotas)) if cuotas > 0 else 0

        self.total_credito.text = format_thousands(total)
        self.valor_cuota.text = format_thousands(cuota)

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Nuevo Cliente y Crédito"))

        body = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(8)], spacing=dp(10))

        body.add_widget(self.progress_card())

        scroll = ScrollView(size_hint_y=1)
        card_wrap = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        card_wrap.bind(minimum_height=card_wrap.setter("height"))

        if self.step == 1:
            card_wrap.add_widget(self.form_card("1", "DATOS DEL CLIENTE", [
                ("Documento", self.documento),
                ("Nombre", self.nombre),
                ("Móvil +57", self.movil),
                ("Dirección", self.direccion),
            ], height=dp(382)))
        elif self.step == 2:
            card_wrap.add_widget(self.form_card("2", "DATOS DEL CRÉDITO", [
                ("Producto", self.producto),
                ("Valor Crédito", self.valor_credito),
                ("Interés %", self.interes),
                ("Número de Cuotas", self.numero_cuotas),
                ("Total Crédito", self.total_credito),
                ("Valor Cuota Calculada", self.valor_cuota),
                ("Cobro", self.cobro),
            ], height=dp(536)))
        elif self.step == 3:
            card_wrap.add_widget(self.form_card("3", "CODEUDOR", [
                ("Documento Codeudor", self.documento_codeudor),
                ("Nombre Codeudor", self.nombre_codeudor),
                ("Móvil Codeudor", self.movil_codeudor),
            ], height=dp(322)))
        else:
            card_wrap.add_widget(self.form_card("4", "SEGURO", [
                ("Valor Seguro", self.valor_seguro),
                ("Beneficiario", self.beneficiario),
                ("Observaciones", self.obs_seguro),
            ], height=dp(370)))

        scroll.add_widget(card_wrap)
        body.add_widget(scroll)

        nav = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))

        back = SmallButton("Atrás", bg_color=(0.45, 0.48, 0.55, 1))
        back.disabled = self.step == 1
        back.bind(on_release=lambda *_: self.previous_step())

        if self.step < 4:
            next_btn = SmallButton("Siguiente", bg_color=BLUE)
            next_btn.bind(on_release=lambda *_: self.next_step())
        else:
            next_btn = SmallButton("Crear Cliente", bg_color=SUCCESS)
            next_btn.bind(on_release=lambda *_: self.create_client())

        nav.add_widget(back)
        nav.add_widget(next_btn)
        body.add_widget(nav)

        self.root.add_widget(body)

        nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        nav_container.add_widget(BottomNav(self.app_ref, active="nuevo"))
        self.root.add_widget(nav_container)

    def progress_card(self):
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(72), padding=[dp(12), dp(8), dp(12), dp(8)], spacing=dp(2))
        card.bg_color = (0.94, 0.97, 1, 1)
        title = Label(text=f"Paso {self.step} de 4", color=TEXT, bold=True, font_size="16sp", halign="left", size_hint_y=None, height=dp(26))
        msg = Label(text="Formulario de producción. Los datos se guardan offline.", color=MUTED, font_size="11sp", halign="left", size_hint_y=None, height=dp(24))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)
        card.add_widget(msg)
        return card

    def form_card(self, number, title, fields, height):
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=height, padding=[dp(12), dp(10), dp(12), dp(12)], spacing=dp(7))
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        circle = Label(text=number, color=WHITE, bold=True, font_size="15sp", size_hint_x=None, width=dp(34))
        with circle.canvas.before:
            Color(*BLUE)
            circle.bg = RoundedRectangle(pos=circle.pos, size=circle.size, radius=[dp(17)])
        circle.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        circle.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))
        lbl = Label(text=title, color=TEXT, bold=True, font_size="14sp", halign="left", valign="middle")
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        header.add_widget(circle)
        header.add_widget(lbl)
        card.add_widget(header)

        for label, widget in fields:
            field_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66) if not (isinstance(widget, TextInput) and widget.multiline) else dp(108), spacing=dp(3))
            field_box.add_widget(FieldLabel(label))
            detach_widget(widget)
            field_box.add_widget(widget)
            card.add_widget(field_box)

        return card

    def next_step(self):
        if self.step == 1 and not self.nombre.text.strip():
            show_popup("Falta nombre", "Ingrese el nombre del cliente para continuar.")
            return

        if self.step == 2:
            self.calculate_credit()
            base = to_int(self.valor_credito.text, 0)
            cuotas = to_int(self.numero_cuotas.text, 0)
            cuota = to_int(self.valor_cuota.text, 0)
            if base <= 0:
                show_popup("Valor inválido", "Ingrese el valor del crédito.")
                return
            if cuotas <= 0:
                show_popup("Valor inválido", "Ingrese el número de cuotas.")
                return
            if cuota <= 0:
                show_popup("Valor inválido", "La cuota calculada debe ser mayor a cero.")
                return

        self.step += 1
        self.build()

    def previous_step(self):
        if self.step > 1:
            self.step -= 1
            self.build()

    def create_client(self):
        self.calculate_credit()

        nombre = self.nombre.text.strip().upper()
        if not nombre:
            self.step = 1
            self.build()
            show_popup("Falta nombre", "Ingrese el nombre del cliente.")
            return

        valor_credito = to_int(self.valor_credito.text, 0)
        total_credito = to_int(self.total_credito.text, 0)
        cuota = to_int(self.valor_cuota.text, 0)
        numero_cuotas = to_int(self.numero_cuotas.text, 0)

        if valor_credito <= 0 or total_credito <= 0 or cuota <= 0 or numero_cuotas <= 0:
            self.step = 2
            self.build()
            show_popup("Datos incompletos", "Revise valor crédito, interés y número de cuotas.")
            return

        refresh_memory_from_db()
        saldo_caja = current_cash_balance()

        if valor_credito > saldo_caja:
            show_popup(
                "Saldo insuficiente",
                f"No se puede crear el préstamo.\n"
                f"Valor a prestar: {money(valor_credito)}\n"
                f"Saldo en caja: {money(saldo_caja)}\n\n"
                f"Primero registre un INGRESO o CAJA INICIAL."
            )
            return

        cliente = {
            "documento": self.documento.text.strip(),
            "nombre": nombre,
            "telefono": f"+57 {self.movil.text.strip()}" if self.movil.text.strip() else "",
            "direccion": self.direccion.text.strip(),
            "producto": self.producto.text.strip() or "5 - CREDITO EN EFECTIVO",
            "valor_credito": valor_credito,
            "interes": to_float(self.interes.text, 0),
            "total_credito": total_credito,
            "cuota": cuota,
            "numero_cuotas": numero_cuotas,
            "saldo": total_credito,
            "pagadas": 0,
            "pendientes": numero_cuotas,
            "cobro": self.cobro.text,
            "estado": "pendiente",
            "ultimo_tipo": "Pendiente por cobrar",
            "proximo_cobro": iso_today(),
            "ultima_fecha_pago": "",
            "synced": 0,
            "codeudor_documento": self.documento_codeudor.text.strip(),
            "codeudor_nombre": self.nombre_codeudor.text.strip(),
            "codeudor_movil": self.movil_codeudor.text.strip(),
            "valor_seguro": to_int(self.valor_seguro.text, 0),
            "beneficiario": self.beneficiario.text.strip(),
            "obs_seguro": self.obs_seguro.text.strip(),
        }

        cliente_id = insert_client_db(cliente)

        insert_movement_db({
            "tipo": "Egreso",
            "concepto": "Desembolso préstamo",
            "valor": valor_credito,
            "observaciones": f"Préstamo entregado a {nombre}",
            "fecha": today_text(),
            "synced": 0,
        })

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        show_popup("Cliente creado", "Cliente y crédito activados correctamente.\nEl desembolso fue descontado de caja.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.8)


# ============================================================
# EDITAR CLIENTE
# ============================================================

class EditarClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="editar_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Editar Cliente / Préstamo", show_back=True, on_back=lambda: self.app_ref.go("gestion_cliente")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(24)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(740), padding=[dp(12), dp(12), dp(12), dp(12)], spacing=dp(8))

        self.documento = AppTextInput(text=str(self.cliente.get("documento", "")))
        self.nombre = AppTextInput(text=str(self.cliente.get("nombre", "")))
        telefono = str(self.cliente.get("telefono", "")).replace("+57", "").strip()
        self.movil = AppTextInput(text=telefono)
        self.direccion = AppTextInput(text=str(self.cliente.get("direccion", "")))
        self.valor_credito = MoneyTextInput(text=format_thousands(self.cliente.get("valor_credito", 0)))
        self.interes = AppTextInput(text=str(self.cliente.get("interes", 0)))
        self.numero_cuotas = AppTextInput(text=str(self.cliente.get("numero_cuotas", self.cliente.get("pendientes", 1))))
        self.total_credito = MoneyTextInput(text=format_thousands(self.cliente.get("total_credito", self.cliente.get("saldo", 0))), readonly=True)
        self.valor_cuota = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)), readonly=True)

        self.valor_credito.bind(text=lambda *_: self.calculate_credit())
        self.interes.bind(text=lambda *_: self.calculate_credit())
        self.numero_cuotas.bind(text=lambda *_: self.calculate_credit())

        for label, widget in [
            ("Documento", self.documento),
            ("Nombre", self.nombre),
            ("Móvil +57", self.movil),
            ("Dirección", self.direccion),
            ("Valor Crédito", self.valor_credito),
            ("Interés %", self.interes),
            ("Número de Cuotas", self.numero_cuotas),
            ("Total Crédito", self.total_credito),
            ("Valor Cuota", self.valor_cuota),
        ]:
            field = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(68), spacing=dp(3))
            field.add_widget(FieldLabel(label))
            field.add_widget(widget)
            card.add_widget(field)

        save = SmallButton("Guardar Cambios", bg_color=SUCCESS)
        save.bind(on_release=lambda *_: self.save_changes())
        card.add_widget(save)

        content.add_widget(card)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def calculate_credit(self):
        base = to_int(self.valor_credito.text, 0)
        interes = to_float(self.interes.text, 0)
        cuotas = to_int(self.numero_cuotas.text, 0)
        total = int(round(base * (1 + interes / 100)))
        cuota = int(round(total / cuotas)) if cuotas > 0 else 0
        self.total_credito.text = format_thousands(total)
        self.valor_cuota.text = format_thousands(cuota)

    def save_changes(self):
        self.calculate_credit()
        nombre = self.nombre.text.strip().upper()
        if not nombre:
            show_popup("Falta nombre", "Ingrese el nombre del cliente.")
            return

        valor_credito = to_int(self.valor_credito.text, 0)
        total_credito = to_int(self.total_credito.text, 0)
        cuota = to_int(self.valor_cuota.text, 0)
        numero_cuotas = to_int(self.numero_cuotas.text, 0)

        if valor_credito < 0 or total_credito < 0 or cuota < 0 or numero_cuotas < 0:
            show_popup("Datos inválidos", "Los valores no pueden ser negativos.")
            return

        # Al editar el crédito, el saldo se actualiza al total calculado.
        self.cliente["documento"] = self.documento.text.strip()
        self.cliente["nombre"] = nombre
        self.cliente["telefono"] = f"+57 {self.movil.text.strip()}" if self.movil.text.strip() else ""
        self.cliente["direccion"] = self.direccion.text.strip()
        self.cliente["valor_credito"] = valor_credito
        self.cliente["interes"] = to_float(self.interes.text, 0)
        self.cliente["total_credito"] = total_credito
        self.cliente["cuota"] = cuota
        self.cliente["numero_cuotas"] = numero_cuotas
        self.cliente["saldo"] = total_credito
        self.cliente["pendientes"] = numero_cuotas
        self.cliente["pagadas"] = 0
        self.cliente["estado"] = "pendiente"
        self.cliente["ultimo_tipo"] = "Cliente y crédito actualizado"

        self.cliente["synced"] = 0
        update_client_db(self.cliente)
        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        show_popup("Cambios guardados", "Cliente y préstamo actualizados correctamente.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)


# ============================================================
# MOVIMIENTOS DE CAJA
# ============================================================

class MovimientosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="movimientos", **kwargs)
        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Movimientos de Caja"))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(14), dp(12), dp(80)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        type_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(104))
        type_card.add_widget(FieldLabel("Tipo de movimiento"))

        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        self.egreso = ToggleButton(text="(*) Egreso", group="movimiento", state="down", background_normal="", background_color=GOLD, color=DARK, bold=True)
        self.ingreso = ToggleButton(text="( ) Ingreso", group="movimiento", background_normal="", background_color=(0.88, 0.90, 0.94, 1), color=TEXT, bold=True)
        self.egreso.bind(on_release=self.update_type)
        self.ingreso.bind(on_release=self.update_type)
        row.add_widget(self.egreso)
        row.add_widget(self.ingreso)
        type_card.add_widget(row)
        content.add_widget(type_card)

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(330))
        form.add_widget(FieldLabel("Concepto"))
        self.concepto = Spinner(text="Seleccione concepto", values=["Caja inicial", "Transporte", "Alimentación", "Papelería", "Recaudo adicional", "Ajuste de caja", "Otro"], size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)
        form.add_widget(self.concepto)

        form.add_widget(FieldLabel("Valor"))
        self.valor = MoneyTextInput(hint_text="Ej: 50.000")
        form.add_widget(self.valor)

        form.add_widget(FieldLabel("Observaciones"))
        self.obs = AppTextInput(hint_text="Escriba observaciones", multiline=True)
        form.add_widget(self.obs)

        save = PillButton("Guardar")
        save.bind(on_release=lambda *_: self.save_movement())
        form.add_widget(save)

        content.add_widget(form)
        scroll.add_widget(content)
        root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        root.add_widget(self.nav_container)
        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="caja"))

    def update_type(self, *_):
        if self.egreso.state == "down":
            self.egreso.text = "(*) Egreso"
            self.ingreso.text = "( ) Ingreso"
        else:
            self.egreso.text = "( ) Egreso"
            self.ingreso.text = "(*) Ingreso"
        self.egreso.background_color = GOLD if self.egreso.state == "down" else (0.88, 0.90, 0.94, 1)
        self.ingreso.background_color = GOLD if self.ingreso.state == "down" else (0.88, 0.90, 0.94, 1)

    def save_movement(self):
        tipo = "Egreso" if self.egreso.state == "down" else "Ingreso"
        valor = to_int(self.valor.text, 0)
        if valor <= 0:
            show_popup("Valor inválido", "Ingrese un valor mayor a cero.")
            return

        refresh_memory_from_db()
        saldo_caja = current_cash_balance()

        if tipo == "Egreso" and valor > saldo_caja:
            show_popup(
                "Saldo insuficiente",
                f"No se puede registrar el egreso.\n"
                f"Egreso: {money(valor)}\n"
                f"Saldo en caja: {money(saldo_caja)}"
            )
            return

        insert_movement_db({
            "tipo": tipo,
            "concepto": self.concepto.text,
            "valor": valor,
            "observaciones": self.obs.text,
            "fecha": today_text(),
            "synced": 0,
        })
        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        self.valor.text = ""
        self.obs.text = ""
        self.concepto.text = "Seleccione concepto"
        show_popup("Movimiento guardado", f"{tipo} registrado por {money(valor)}.")


# ============================================================
# RESUMEN
# ============================================================

class MetricRow(BoxLayout):
    def __init__(self, left, right, highlight=False, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(38) if not highlight else dp(46), padding=[dp(10), 0, dp(10), 0], **kwargs)
        bg_color = (0.98, 0.98, 1, 1) if not highlight else (1.0, 0.95, 0.78, 1)
        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        left_label = Label(text=left, color=TEXT if highlight else MUTED, bold=highlight, font_size="12sp", halign="left", valign="middle")
        right_label = Label(text=right, color=TEXT, bold=highlight, font_size="12sp", halign="right", valign="middle")
        left_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        right_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.add_widget(left_label)
        self.add_widget(right_label)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


class ResumenScreen(Screen):
    sync_status = StringProperty("Pendiente")

    def __init__(self, **kwargs):
        super().__init__(name="resumen", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("::V12:: Resumen del Día", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(18)], spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        total_clientes = len(CLIENTES)
        clientes_nuevos = len([c for c in CLIENTES if str(c.get("created_at", "")).startswith(today_text())])
        pagos = len([t for t in TRANSACCIONES if t["tipo"] in ("Cuota", "Aporte")])
        no_pagos = len([t for t in TRANSACCIONES if t["tipo"] == "No Pago"])
        aplazados = len([t for t in TRANSACCIONES if t["tipo"] == "Siguiente Día"])
        recaudo_dia = sum(int(t.get("valor", 0)) for t in TRANSACCIONES if t["tipo"] in ("Cuota", "Aporte"))
        ingresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m["tipo"] == "Ingreso")
        egresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m["tipo"] == "Egreso")
        caja_inicial = 0
        recaudo_esperado = sum(int(c.get("cuota", 0)) for c in CLIENTES)
        saldo_caja = current_cash_balance()
        pendientes_sync = count_pending_sync()

        report = RoundedBox(orientation="vertical", spacing=dp(7), padding=dp(10), size_hint_y=None)
        report.bind(minimum_height=report.setter("height"))

        for left, right in [
            ("Vendedor", "CORREDOR - USUARIO"),
            ("Fecha de Ruta", today_text()),
            ("Clientes Ausentes", str(no_pagos)),
            ("Aplazados Sig. Día", str(aplazados)),
            ("Número Clientes", str(total_clientes)),
            ("Clientes Nuevos", str(clientes_nuevos)),
            ("Pagos Registrados", f"{pagos} / {total_clientes}"),
            ("Caja Inicial", money(caja_inicial)),
            ("Recaudo Esperado", money(recaudo_esperado)),
            ("Recaudo del día", money(recaudo_dia)),
            ("Ingresos", money(ingresos)),
            ("Egresos", money(egresos)),
            ("Pendientes Nube", str(pendientes_sync)),
            ("Sincronización", self.sync_status),
        ]:
            report.add_widget(MetricRow(left, right))

        report.add_widget(MetricRow("Saldo en Caja", money(saldo_caja), highlight=True))
        content.add_widget(report)

        actions = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(176), spacing=dp(8))
        row1 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row1.add_widget(PillButton("No Pagos"))
        row1.add_widget(PillButton("Configuración"))

        row2 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row2.add_widget(PillButton("Reajuste"))
        cloud = PillButton("Carga Completa", bg_color=BLUE)
        cloud.bind(on_release=lambda *_: self.simulate_cloud_upload())
        row2.add_widget(cloud)

        row_pdf = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        pdf_btn = PillButton("Generar PDF", bg_color=SUCCESS)
        pdf_btn.bind(on_release=lambda *_: self.generate_pdf())
        row_pdf.add_widget(pdf_btn)

        actions.add_widget(row1)
        actions.add_widget(row2)
        actions.add_widget(row_pdf)
        content.add_widget(actions)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def confirm_clear(self):
        confirm_popup("Limpiar datos", "Esto borrará clientes, pagos y movimientos.\nLa app quedará vacía para uso personal.", self.clear_all)

    def clear_all(self):
        clear_all_data_db()
        self.sync_status = "Pendiente"
        self.build()
        show_popup("Datos limpiados", "La base local fue limpiada correctamente.")

    def generate_pdf(self):
        try:
            pdf_path = generate_daily_pdf_report()
            show_popup(
                "PDF generado",
                f"Reporte creado correctamente.\n\nRuta:\n{pdf_path}",
                height=300,
            )
        except Exception as error:
            show_popup("Error PDF", f"No se pudo generar el PDF.\n{error}", height=260)

    def simulate_cloud_upload(self):
        self.sync_status = "Sincronizando..."
        self.build()

        def complete_sync(*_):
            if supabase_configured():
                ok, msg = sync_all_to_cloud(silent=False)
                if ok:
                    self.sync_status = "Sincronizado correctamente"
                    self.build()
                    show_popup("Carga completa", "Datos sincronizados con Supabase correctamente.\nSe subieron y descargaron registros.")
                else:
                    self.sync_status = "Pendiente"
                    self.build()
                    show_popup("Sincronización pendiente", f"No se pudo sincronizar ahora.\n{msg}")
            else:
                self.sync_status = "Supabase no configurado"
                self.build()
                show_popup("Supabase no configurado", "Debes pegar SUPABASE_URL, SUPABASE_ANON_KEY y COBRADOR_ID en main.py.")
        Clock.schedule_once(complete_sync, 0.5)


# ============================================================
# APP PRINCIPAL
# ============================================================

class CobrosV12App(App):
    selected_client = None

    def build(self):
        self.title = "Cobros V12 Mobile"
        try:
            init_database()
            refresh_memory_from_db()
        except Exception as error:
            print("ERROR SQLITE:", error)

        self.shell = AnchorLayout(anchor_x="center", anchor_y="top")

        if platform in ("android", "ios"):
            size_hint = (1, 1)
            width = Window.width
        else:
            size_hint = (None, 1)
            width = min(Window.width, dp(430))

        self.sm = ScreenManager(transition=NoTransition(), size_hint=size_hint, width=width)

        self.sm.add_widget(ClientesScreen())
        self.sm.add_widget(GestionClienteScreen())
        self.sm.add_widget(CuotaScreen())
        self.sm.add_widget(NuevoClienteScreen())
        self.sm.add_widget(EditarClienteScreen())
        self.sm.add_widget(MovimientosScreen())
        self.sm.add_widget(ResumenScreen())

        self.shell.add_widget(self.sm)
        Window.bind(size=self.update_mobile_width)

        return self.shell

    def update_mobile_width(self, *_):
        if hasattr(self, "sm") and platform not in ("android", "ios"):
            self.sm.width = min(Window.width, dp(430))

    def on_start(self):
        print("Cobros V12 iniciado correctamente.")
        print("Base de datos:", get_db_path())
        print("Supabase configurado:", supabase_configured())
        Clock.schedule_once(lambda *_: self.request_auto_sync(), 3)
        Clock.schedule_interval(lambda *_: self.request_auto_sync(), SYNC_INTERVAL_SECONDS)

    def request_auto_sync(self):
        if not supabase_configured():
            return
        Clock.schedule_once(lambda *_: self._do_auto_sync(), 0.2)

    def _do_auto_sync(self):
        ok, msg = sync_all_to_cloud(silent=True)
        print("AUTO SYNC:", ok, msg)

    def go(self, screen_name):
        self.sm.current = screen_name


if __name__ == "__main__":
    CobrosV12App().run()
