# ============================================================
# App móvil Python Offline/Online - Gestión de Créditos y Cobros
# Nombre: Cobros V12 Mobile
# Framework: Kivy
#
# Instalación:
#   pip install kivy
#
# Ejecución:
#   python cobros_v12_mobile.py
#
# Nota:
# Esta versión funciona en escritorio como prototipo mobile-first.
# Puede adaptarse a Android con Buildozer.
# ============================================================

from datetime import datetime, timedelta
import sqlite3
from pathlib import Path
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty, ObjectProperty
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.core.window import Window


# ============================================================
# CONFIGURACIÓN VISUAL
# ============================================================

Window.size = (440, 860)  # Vista tipo teléfono para probar en PC

def asset_path(filename):
    """
    Devuelve una ruta segura para cargar imágenes en PC y Android.
    """
    try:
        base_dir = Path(__file__).parent
        return str(base_dir / "assets" / filename)
    except Exception:
        return f"assets/{filename}"


Window.clearcolor = (0.90, 0.93, 0.97, 1)

BLUE = (0.117, 0.227, 0.541, 1)       # #1E3A8A
BLUE_DARK = (0.07, 0.13, 0.30, 1)
BLUE_SOFT = (0.90, 0.94, 1.00, 1)
GOLD = (0.93, 0.69, 0.13, 1)
GOLD_SOFT = (1.00, 0.96, 0.86, 1)
BG = (0.96, 0.97, 0.99, 1)
WHITE = (1, 1, 1, 1)
TEXT = (0.12, 0.15, 0.22, 1)
MUTED = (0.41, 0.47, 0.56, 1)
DARK = (0.12, 0.14, 0.18, 1)
SUCCESS = (0.12, 0.62, 0.32, 1)
DANGER = (0.83, 0.18, 0.18, 1)

# Estados visuales de cobro
STATUS_GREEN = (0.86, 0.98, 0.89, 1)     # Pagado
STATUS_YELLOW = (1.00, 0.96, 0.78, 1)    # Pendiente / siguiente día
STATUS_RED = (1.00, 0.88, 0.88, 1)       # No paga
STATUS_BORDER_GREEN = (0.12, 0.62, 0.32, 1)
STATUS_BORDER_YELLOW = (0.93, 0.69, 0.13, 1)
STATUS_BORDER_RED = (0.83, 0.18, 0.18, 1)


# ============================================================
# DATOS SIMULADOS OFFLINE
# ============================================================

CLIENTES = []


MOVIMIENTOS_CAJA = []
TRANSACCIONES = []


# ============================================================
# BASE DE DATOS SQLITE OFFLINE
# ============================================================

def get_db_path():
    """
    Devuelve la ruta de la base de datos local.
    En escritorio queda junto al archivo.
    En Android/Kivy intenta usar user_data_dir.
    """
    try:
        app = App.get_running_app()
        if app and hasattr(app, "user_data_dir"):
            return str(Path(app.user_data_dir) / "cobros_v12.db")
    except Exception:
        pass

    return "cobros_v12.db"


def get_connection():
    return sqlite3.connect(get_db_path())


def init_database():
    """
    Crea las tablas si no existen.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            cuota INTEGER NOT NULL DEFAULT 0,
            saldo INTEGER NOT NULL DEFAULT 0,
            pagadas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            ultimo_tipo TEXT NOT NULL DEFAULT 'Pendiente',
            documento TEXT,
            direccion TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_finalizacion TEXT,
            cobro TEXT NOT NULL DEFAULT 'Diario',
            fecha_ultimo_pago TEXT,
            proxima_fecha_cobro TEXT,
            created_at TEXT NOT NULL
        )
    """)

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

    # Migraciones simples para bases de datos existentes
    cursor.execute("PRAGMA table_info(clientes)")
    columns = [row[1] for row in cursor.fetchall()]

    if "activo" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")

    if "fecha_finalizacion" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN fecha_finalizacion TEXT")

    if "cobro" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN cobro TEXT NOT NULL DEFAULT 'Diario'")

    if "fecha_ultimo_pago" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN fecha_ultimo_pago TEXT")

    if "proxima_fecha_cobro" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN proxima_fecha_cobro TEXT")

    conn.commit()
    conn.close()


def seed_database_if_empty():
    """
    La app arranca sin clientes de ejemplo.
    Antes se cargaban clientes demo; ahora la base inicia en cero.
    Los clientes se crean desde la pantalla 'Nuevo'.
    """
    return


def load_clients_from_db():
    """
    Carga los clientes desde SQLite a la lista global CLIENTES.
    """
    global CLIENTES

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo,
               documento, direccion, activo, fecha_finalizacion, cobro,
               fecha_ultimo_pago, proxima_fecha_cobro
        FROM clientes
        WHERE activo = 1
        ORDER BY nombre ASC
    """)

    CLIENTES = [dict(row) for row in cursor.fetchall()]

    conn.close()


def load_historial_clientes():
    """
    Devuelve clientes finalizados/inactivos para historial.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo,
               documento, direccion, activo, fecha_finalizacion, cobro,
               fecha_ultimo_pago, proxima_fecha_cobro
        FROM clientes
        WHERE activo = 0
        ORDER BY fecha_finalizacion DESC, nombre ASC
    """)

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def load_transacciones_from_db():
    """
    Carga las transacciones desde SQLite.
    """
    global TRANSACCIONES

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT cliente_id, cliente, tipo, valor, metodo, fecha, synced
        FROM transacciones
        ORDER BY id ASC
    """)

    TRANSACCIONES = [dict(row) for row in cursor.fetchall()]

    conn.close()


def load_movimientos_from_db():
    """
    Carga los movimientos de caja desde SQLite.
    """
    global MOVIMIENTOS_CAJA

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tipo, concepto, valor, observaciones, fecha, synced
        FROM movimientos_caja
        ORDER BY id ASC
    """)

    MOVIMIENTOS_CAJA = [dict(row) for row in cursor.fetchall()]

    conn.close()


def refresh_memory_from_db():
    apply_due_status_updates()
    load_clients_from_db()
    load_transacciones_from_db()
    load_movimientos_from_db()


def update_client_in_db(cliente):
    """
    Guarda los cambios de saldo, estado, cuotas pagadas y pendientes.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET nombre = ?,
            telefono = ?,
            cuota = ?,
            saldo = ?,
            pagadas = ?,
            pendientes = ?,
            estado = ?,
            ultimo_tipo = ?,
            documento = ?,
            direccion = ?,
            activo = ?,
            fecha_finalizacion = ?,
            cobro = ?,
            fecha_ultimo_pago = ?,
            proxima_fecha_cobro = ?
        WHERE id = ?
    """, (
        cliente.get("nombre", ""),
        cliente.get("telefono", ""),
        int(cliente.get("cuota", 0)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente"),
        cliente.get("documento", ""),
        cliente.get("direccion", ""),
        int(cliente.get("activo", 1)),
        cliente.get("fecha_finalizacion", None),
        cliente.get("cobro", "Diario"),
        cliente.get("fecha_ultimo_pago", None),
        cliente.get("proxima_fecha_cobro", today_iso()),
        int(cliente.get("id")),
    ))

    conn.commit()
    conn.close()


def insert_transaction_db(transaccion):
    """
    Guarda una transacción localmente.
    """
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
    """
    Guarda un movimiento de caja localmente.
    """
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


def insert_client_db(cliente):
    """
    Crea un nuevo cliente en SQLite y devuelve su ID.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes
        (nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo,
         documento, direccion, activo, fecha_finalizacion, cobro,
         fecha_ultimo_pago, proxima_fecha_cobro, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cliente.get("nombre", ""),
        cliente.get("telefono", ""),
        int(cliente.get("cuota", 0)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente"),
        cliente.get("documento", ""),
        cliente.get("direccion", ""),
        int(cliente.get("activo", 1)),
        cliente.get("fecha_finalizacion", None),
        cliente.get("cobro", "Diario"),
        cliente.get("fecha_ultimo_pago", None),
        cliente.get("proxima_fecha_cobro", today_iso()),
        today_text(),
    ))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return new_id


def mark_all_as_synced():
    """
    Simula sincronización online marcando datos como enviados.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE transacciones SET synced = 1")
    cursor.execute("UPDATE movimientos_caja SET synced = 1")

    conn.commit()
    conn.close()


def count_pending_sync():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM transacciones WHERE synced = 0")
    tx = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM movimientos_caja WHERE synced = 0")
    mv = cursor.fetchone()[0]

    conn.close()

    return tx + mv


# ============================================================
# UTILIDADES
# ============================================================

def money(value):
    return "$ {:,.0f}".format(value).replace(",", ".")


def only_digits(value):
    return "".join(ch for ch in str(value) if ch.isdigit())


def parse_money(value):
    digits = only_digits(value)
    if not digits:
        return 0
    return int(digits)


def format_thousands(value):
    try:
        n = int(value)
    except Exception:
        n = parse_money(value)
    return "{:,.0f}".format(n).replace(",", ".")


def today_text():
    return datetime.now().strftime("%d/%m/%Y")


def today_iso():
    return datetime.now().strftime("%Y-%m-%d")


def iso_to_display(value):
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(value)


def next_due_date(cobro):
    """
    Calcula la próxima fecha de cobro según la frecuencia.
    Diario: mañana.
    Semanal: dentro de 7 días.
    Quincenal: dentro de 15 días.
    Mensual: dentro de 30 días.
    """
    days = 1

    if cobro == "Semanal":
        days = 7
    elif cobro == "Quincenal":
        days = 15
    elif cobro == "Mensual":
        days = 30
    else:
        days = 1

    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def is_due_today_or_before(value):
    if not value:
        return True

    try:
        due = datetime.strptime(value, "%Y-%m-%d").date()
        today = datetime.now().date()
        return due <= today
    except Exception:
        return True


def get_estado_cliente(cliente):
    return cliente.get("estado", "pendiente")


def estado_texto(cliente):
    estado = get_estado_cliente(cliente)
    if estado == "pagado":
        return "PAGADO"
    if estado == "no_pago":
        return "NO PAGÓ"
    if estado == "siguiente":
        return "SIGUIENTE DÍA"
    if estado == "aporte":
        return "APORTE"
    return "PENDIENTE"


def estado_colores(cliente):
    estado = get_estado_cliente(cliente)

    if estado in ["pagado", "aporte"]:
        return STATUS_GREEN, STATUS_BORDER_GREEN, "PAGADO" if estado == "pagado" else "APORTE"

    if estado == "no_pago":
        return STATUS_RED, STATUS_BORDER_RED, "NO PAGÓ"

    if estado == "siguiente":
        return STATUS_YELLOW, STATUS_BORDER_YELLOW, "SIG. DÍA"

    return STATUS_YELLOW, STATUS_BORDER_YELLOW, "PENDIENTE"



def cliente_filter_key(cliente):
    """
    Orden inteligente para la ruta:
    1. Pendientes
    2. No pagó
    3. Siguiente día
    4. Aporte
    5. Pagados
    """
    estado = get_estado_cliente(cliente)
    order = {
        "pendiente": 1,
        "no_pago": 2,
        "siguiente": 3,
        "aporte": 4,
        "pagado": 5,
    }
    return (order.get(estado, 9), cliente.get("nombre", ""))


def cliente_matches_filter(cliente, filtro):
    estado = get_estado_cliente(cliente)

    if filtro == "Todos":
        return True

    if filtro == "Pendientes":
        return estado == "pendiente"

    if filtro == "Pagados":
        return estado in ["pagado", "aporte"]

    if filtro == "No Pago":
        return estado == "no_pago"

    if filtro == "Siguiente":
        return estado == "siguiente"

    return True


def make_popup(title, message):
    content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
    lbl = Label(
        text=message,
        color=TEXT,
        font_size="15sp",
        halign="center",
        valign="middle",
    )
    lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    btn = Button(
        text="Aceptar",
        size_hint_y=None,
        height=dp(46),
        background_normal="",
        background_color=BLUE,
        color=WHITE,
        bold=True,
    )

    content.add_widget(lbl)
    content.add_widget(btn)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.86, None),
        height=dp(230),
        auto_dismiss=False,
    )
    btn.bind(on_release=popup.dismiss)
    popup.open()



def make_confirm_popup(title, message, on_confirm):
    content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

    lbl = Label(
        text=message,
        color=TEXT,
        font_size="15sp",
        halign="center",
        valign="middle",
    )
    lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(46))

    cancel = Button(
        text="Cancelar",
        background_normal="",
        background_color=(0.70, 0.72, 0.76, 1),
        color=TEXT,
        bold=True,
    )

    ok = Button(
        text="Confirmar",
        background_normal="",
        background_color=SUCCESS,
        color=WHITE,
        bold=True,
    )

    row.add_widget(cancel)
    row.add_widget(ok)

    content.add_widget(lbl)
    content.add_widget(row)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(250),
        auto_dismiss=False,
    )

    cancel.bind(on_release=popup.dismiss)

    def confirm_action(*_):
        popup.dismiss()
        on_confirm()

    ok.bind(on_release=confirm_action)
    popup.open()


# ============================================================
# WIDGETS BASE
# ============================================================

class RoundedBox(BoxLayout):
    bg_color = ObjectProperty(WHITE)
    radius = NumericProperty(14)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.padding = kwargs.get("padding", dp(12))
        self.spacing = kwargs.get("spacing", dp(8))
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius],
            )
        self.bind(pos=self._update_rect, size=self._update_rect, bg_color=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class Header(BoxLayout):
    def __init__(self, title, show_back=False, on_back=None, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(64), **kwargs)

        with self.canvas.before:
            Color(*BLUE)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        row = BoxLayout(orientation="horizontal", padding=[dp(14), dp(8), dp(14), dp(8)], spacing=dp(8))

        if show_back:
            back = Button(
                text="‹",
                size_hint_x=None,
                width=dp(42),
                background_normal="",
                background_color=BLUE_DARK,
                color=WHITE,
                font_size="26sp",
                bold=True,
            )
            if on_back:
                back.bind(on_release=lambda *_: on_back())
            row.add_widget(back)

        label = Label(
            text=title,
            color=WHITE,
            bold=True,
            font_size="18sp",
            halign="left",
            valign="middle",
        )
        label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        row.add_widget(label)

        self.add_widget(row)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


class SmallButton(Button):
    def __init__(self, text, bg_color=BLUE, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=bg_color,
            color=WHITE,
            bold=True,
            font_size="13sp",
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
            font_size="13sp",
            **kwargs
        )


class FieldLabel(Label):
    def __init__(self, text, **kwargs):
        super().__init__(
            text=text,
            color=(0.33, 0.40, 0.52, 1),
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            bold=True,
            halign="left",
            valign="middle",
            **kwargs
        )
        self.bind(size=lambda instance, value: setattr(instance, "text_size", value))


class AppTextInput(TextInput):
    def __init__(self, hint_text="", text="", multiline=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=text,
            multiline=multiline,
            size_hint_y=None,
            height=dp(44) if not multiline else dp(88),
            background_normal="",
            background_color=(0.97, 0.98, 1, 1),
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
            **kwargs
        )



class MoneyInput(AppTextInput):
    """
    Campo monetario con separador de miles usando punto.
    Ejemplo: 500000 -> 500.000
    """
    def __init__(self, hint_text="", text="", **kwargs):
        initial = ""
        if text not in ["", None]:
            initial = format_thousands(text)
        super().__init__(hint_text=hint_text, text=initial, multiline=False, **kwargs)
        self._formatting = False
        self.bind(text=self._on_text)

    def _on_text(self, instance, value):
        if self._formatting:
            return

        digits = only_digits(value)
        formatted = format_thousands(digits) if digits else ""

        if formatted != value:
            self._formatting = True
            self.text = formatted
            self.cursor = (len(self.text), 0)
            self._formatting = False

    def value(self):
        return parse_money(self.text)


class IconNavItem(ButtonBehavior, BoxLayout):
    def __init__(self, icon_file, label, active=False, on_press_callback=None, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=[dp(6), dp(5), dp(6), dp(5)],
            spacing=dp(2),
            **kwargs
        )
        self.size_hint_y = None
        self.height = dp(56)
        self.on_press_callback = on_press_callback

        self.bg_color = BLUE if active else (0.94, 0.95, 0.98, 1)
        self.txt_color = WHITE if active else TEXT

        with self.canvas.before:
            Color(*self.bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.icon = Image(
            source=asset_path(icon_file),
            size_hint_y=None,
            height=dp(25),
            allow_stretch=True,
            keep_ratio=True,
        )

        self.lbl = Label(
            text=label,
            color=self.txt_color,
            font_size="11sp",
            bold=active,
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        self.lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(self.icon)
        self.add_widget(self.lbl)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def on_release(self):
        if self.on_press_callback:
            self.on_press_callback()


class BottomNav(BoxLayout):
    def __init__(self, app, active="clientes", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(72),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(10),
            **kwargs
        )
        self.app = app

        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        items = [
            ("clientes", "clientes.png", "Clientes", "clientes"),
            ("nuevo", "nuevo.png", "Nuevo", "nuevo_cliente"),
            ("caja", "caja.png", "Caja", "movimientos"),
        ]

        for key, icon_file, label, screen in items:
            item = IconNavItem(
                icon_file=icon_file,
                label=label,
                active=(key == active),
                on_press_callback=lambda s=screen: self.app.go(s),
            )
            self.add_widget(item)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


# ============================================================
# INTERFAZ 1: LISTA DE CLIENTES
# ============================================================

class ClienteCard(RoundedBox):
    def __init__(self, cliente, on_click, **kwargs):
        bg_status, border_color, badge_text = estado_colores(cliente)

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(112),
            padding=[dp(0), dp(0), dp(12), dp(0)],
            spacing=dp(0),
            **kwargs
        )

        self.bg_color = bg_status
        self.cliente = cliente

        # Barra lateral de estado
        side = BoxLayout(size_hint_x=None, width=dp(8))
        with side.canvas.before:
            Color(*border_color)
            side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
        side.bind(pos=lambda w, *_: setattr(w.rect, "pos", w.pos))
        side.bind(size=lambda w, *_: setattr(w.rect, "size", w.size))

        body = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(9), dp(0), dp(9)],
            spacing=dp(5),
        )

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(8))

        initial = cliente["nombre"][0].upper()
        avatar = Label(
            text=initial,
            size_hint_x=None,
            width=dp(34),
            color=WHITE,
            bold=True,
            font_size="16sp",
            halign="center",
            valign="middle",
        )
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(17)])
        avatar.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        avatar.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name = Label(
            text=cliente["nombre"],
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
        )
        name.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        badge = Label(
            text=badge_text,
            size_hint_x=None,
            width=dp(86),
            color=WHITE if badge_text != "PENDIENTE" else DARK,
            bold=True,
            font_size="10sp",
            halign="center",
            valign="middle",
        )
        badge_bg = border_color
        if badge_text == "PENDIENTE":
            badge_bg = GOLD

        with badge.canvas.before:
            Color(*badge_bg)
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        badge.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        top.add_widget(avatar)
        top.add_widget(name)
        top.add_widget(badge)

        amounts = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(28))

        cuota = Label(
            text=f"Cuota: [b]{money(cliente['cuota'])}[/b]",
            markup=True,
            color=TEXT,
            font_size="13sp",
            halign="left",
        )
        cuota.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        saldo = Label(
            text=f"Saldo: [b]{money(cliente['saldo'])}[/b]",
            markup=True,
            color=TEXT,
            font_size="13sp",
            halign="right",
        )
        saldo.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        amounts.add_widget(cuota)
        amounts.add_widget(saldo)

        frecuencia = cliente.get("cobro", "Diario")
        proxima = iso_to_display(cliente.get("proxima_fecha_cobro"))

        if get_estado_cliente(cliente) == "siguiente":
            frecuencia_txt = f"Siguiente {frecuencia}"
        else:
            frecuencia_txt = frecuencia

        extra = Label(
            text=f"Cobro: {frecuencia_txt} | Próx: {proxima} | Pend: {cliente['pendientes']} | Último: {cliente.get('ultimo_tipo', 'Pendiente')}",
            color=MUTED,
            font_size="10sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        )
        extra.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        body.add_widget(top)
        body.add_widget(amounts)
        body.add_widget(extra)

        self.add_widget(side)
        self.add_widget(body)

        self.bind(on_touch_down=lambda widget, touch: self._pressed(touch, on_click))

    def _pressed(self, touch, on_click):
        if self.collide_point(*touch.pos):
            on_click(self.cliente)
            return True
        return False


class ClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="clientes", **kwargs)
        self.app_ref = None
        self.active_filter = "Todos"
        self.filter_buttons = {}

        root = BoxLayout(orientation="vertical", spacing=0)

        # Header compacto
        header_area = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(226))
        header_area.add_widget(Header("::V12:: Lista de Clientes"))

        # Herramientas superiores
        tools = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(154),
        )

        top_tools = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(44))

        self.search = TextInput(
            hint_text="Buscar cliente...",
            multiline=False,
            background_normal="",
            background_color=(0.97, 0.98, 1, 1),
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
        )
        self.search.bind(text=lambda *_: self.render_clients())

        self.summary_btn = Button(
            text="RES",
            size_hint_x=None,
            width=dp(52),
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
            font_size="12sp",
        )
        self.summary_btn.bind(on_release=lambda *_: self.app_ref.go("resumen"))

        self.history_btn = Button(
            text="HIS",
            size_hint_x=None,
            width=dp(52),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        self.history_btn.bind(on_release=lambda *_: self.app_ref.go("historial"))

        top_tools.add_widget(self.search)
        top_tools.add_widget(self.summary_btn)
        top_tools.add_widget(self.history_btn)
        tools.add_widget(top_tools)

        # Contadores rápidos
        self.counters_row = GridLayout(
            cols=4,
            spacing=dp(6),
            size_hint_y=None,
            height=dp(56),
        )
        tools.add_widget(self.counters_row)

        # Filtros rápidos
        self.filters_row = GridLayout(
            cols=5,
            spacing=dp(5),
            size_hint_y=None,
            height=dp(38),
        )

        for filtro in ["Todos", "Pendientes", "Pagados", "No Pago", "Siguiente"]:
            btn = Button(
                text=filtro,
                background_normal="",
                background_color=BLUE if filtro == self.active_filter else (0.90, 0.92, 0.96, 1),
                color=WHITE if filtro == self.active_filter else TEXT,
                bold=True,
                font_size="9sp",
            )
            btn.bind(on_release=lambda _, f=filtro: self.set_filter(f))
            self.filter_buttons[filtro] = btn
            self.filters_row.add_widget(btn)

        tools.add_widget(self.filters_row)

        header_area.add_widget(tools)
        root.add_widget(header_area)

        # Lista
        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(10), dp(12), dp(86)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))
        self.scroll.add_widget(self.client_list)
        root.add_widget(self.scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(72))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="clientes"))
        self.render_clients()

    def set_filter(self, filtro):
        self.active_filter = filtro

        for key, btn in self.filter_buttons.items():
            is_active = key == filtro
            btn.background_color = BLUE if is_active else (0.90, 0.92, 0.96, 1)
            btn.color = WHITE if is_active else TEXT

        self.render_clients()

    def make_counter_card(self, title, value, color):
        box = BoxLayout(orientation="vertical", padding=[dp(6), dp(4), dp(6), dp(4)])

        with box.canvas.before:
            Color(*color)
            box.bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(10)])
        box.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        box.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        lbl_value = Label(
            text=str(value),
            color=WHITE,
            bold=True,
            font_size="16sp",
            halign="center",
            valign="bottom",
        )
        lbl_title = Label(
            text=title,
            color=WHITE,
            font_size="9sp",
            halign="center",
            valign="top",
        )

        box.add_widget(lbl_value)
        box.add_widget(lbl_title)
        return box

    def update_counters(self):
        total = len(CLIENTES)
        pendientes = len([c for c in CLIENTES if get_estado_cliente(c) == "pendiente"])
        pagados = len([c for c in CLIENTES if get_estado_cliente(c) in ["pagado", "aporte"]])
        no_pago = len([c for c in CLIENTES if get_estado_cliente(c) == "no_pago"])
        siguiente = len([c for c in CLIENTES if get_estado_cliente(c) == "siguiente"])

        self.counters_row.clear_widgets()
        self.counters_row.add_widget(self.make_counter_card("Total", total, BLUE))
        self.counters_row.add_widget(self.make_counter_card("Pend.", pendientes, STATUS_BORDER_YELLOW))
        self.counters_row.add_widget(self.make_counter_card("Pag.", pagados, STATUS_BORDER_GREEN))
        self.counters_row.add_widget(self.make_counter_card("No Pago", no_pago + siguiente, STATUS_BORDER_RED))

    def render_clients(self):
        if not self.app_ref:
            return

        self.update_counters()

        query = self.search.text.strip().lower() if hasattr(self, "search") else ""

        self.client_list.clear_widgets()

        filtered = []
        for c in CLIENTES:
            text_match = (
                query in c.get("nombre", "").lower()
                or query in c.get("telefono", "").lower()
                or query in str(c.get("documento", "")).lower()
                or query in c.get("direccion", "").lower()
            )

            if not text_match:
                continue

            if not cliente_matches_filter(c, self.active_filter):
                continue

            filtered.append(c)

        filtered.sort(key=cliente_filter_key)

        if not filtered:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(116),
                padding=dp(14),
            )
            empty.bg_color = WHITE
            empty.add_widget(Label(
                text="No hay clientes para este filtro.\nPrueba con otro estado o búsqueda.",
                color=MUTED,
                font_size="13sp",
                halign="center",
                valign="middle",
            ))
            self.client_list.add_widget(empty)
            return

        # Texto guía
        guide = Label(
            text=f"Mostrando {len(filtered)} cliente(s) - filtro: {self.active_filter}",
            color=MUTED,
            font_size="12sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        )
        guide.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.client_list.add_widget(guide)

        for cliente in filtered:
            self.client_list.add_widget(ClienteCard(cliente, self.open_client))

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("cuota")


# ============================================================
# INTERFAZ 2: INGRESO DE CUOTA
# ============================================================

class CuotaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="cuota", **kwargs)
        self.cliente = None
        self.selected_tipo = "Cuota"

        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = self.app_ref.selected_client
        self.selected_tipo = "Cuota"
        self.build()

    def build(self):
        self.root.clear_widgets()

        self.root.add_widget(Header(
            "Ingreso de Cuota",
            show_back=True,
            on_back=lambda: self.app_ref.go("clientes"),
        ))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(22)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ========================================================
        # TARJETA DE ESTADO DEL CLIENTE
        # ========================================================
        bg_status, border_color, badge_text = estado_colores(self.cliente)

        status_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(150),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(7),
        )
        status_card.bg_color = bg_status

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))

        avatar = Label(
            text=self.cliente["nombre"][0].upper(),
            size_hint_x=None,
            width=dp(40),
            color=WHITE,
            bold=True,
            font_size="18sp",
            halign="center",
            valign="middle",
        )
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(20)])
        avatar.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        avatar.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name_box = BoxLayout(orientation="vertical", spacing=dp(0))
        name = Label(
            text=self.cliente["nombre"].lower(),
            color=TEXT,
            bold=True,
            font_size="16sp",
            halign="left",
            valign="bottom",
        )
        name.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        phone = Label(
            text=self.cliente["telefono"],
            color=MUTED,
            font_size="12sp",
            halign="left",
            valign="top",
        )
        phone.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        name_box.add_widget(name)
        name_box.add_widget(phone)

        badge = Label(
            text=badge_text,
            size_hint_x=None,
            width=dp(92),
            color=WHITE if badge_text != "PENDIENTE" else DARK,
            bold=True,
            font_size="10sp",
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
        top.add_widget(name_box)
        top.add_widget(badge)

        status_card.add_widget(top)

        nums = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(68))

        nums.add_widget(self.small_metric("Cuota", money(self.cliente["cuota"])))
        nums.add_widget(self.small_metric("Saldo", money(self.cliente["saldo"])))
        nums.add_widget(self.small_metric("Pagadas", str(self.cliente["pagadas"])))
        nums.add_widget(self.small_metric("Pendientes", str(self.cliente["pendientes"])))

        status_card.add_widget(nums)
        content.add_widget(status_card)

        # ========================================================
        # ACCIONES RÁPIDAS
        # ========================================================
        action_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(134),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(8),
        )
        action_card.bg_color = WHITE

        action_card.add_widget(Label(
            text="Seleccione resultado del cobro",
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))

        row = GridLayout(cols=4, spacing=dp(6), size_hint_y=None, height=dp(46))
        self.tipo_buttons = {}

        for tipo in ["Cuota", "Aporte", "No Pago", "Siguiente Día"]:
            btn = ToggleButton(
                text=tipo,
                group="tipo_cuota",
                state="down" if tipo == "Cuota" else "normal",
                background_normal="",
                background_color=GOLD if tipo == "Cuota" else (0.88, 0.90, 0.94, 1),
                color=DARK,
                font_size="10sp",
                bold=True,
            )
            btn.bind(on_release=lambda b, t=tipo: self.select_tipo(t))
            self.tipo_buttons[tipo] = btn
            row.add_widget(btn)

        action_card.add_widget(row)

        self.warning_label = Label(
            text="Seleccione una opción para registrar el resultado de la visita.",
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(32),
        )
        self.warning_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        action_card.add_widget(self.warning_label)

        content.add_widget(action_card)

        # ========================================================
        # FORMULARIO DE PAGO
        # ========================================================
        form = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(362),
            padding=[dp(12), dp(10), dp(12), dp(12)],
            spacing=dp(8),
        )
        form.bg_color = WHITE

        form.add_widget(Label(
            text="Datos de la transacción",
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))

        quick_row = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(42))

        q1 = Button(
            text="Cuota completa",
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            font_size="10sp",
        )
        q1.bind(on_release=lambda *_: self.set_quick_amount(self.cliente["cuota"]))

        q2 = Button(
            text="Media cuota",
            background_normal="",
            background_color=(0.25, 0.37, 0.62, 1),
            color=WHITE,
            bold=True,
            font_size="10sp",
        )
        q2.bind(on_release=lambda *_: self.set_quick_amount(round(self.cliente["cuota"] / 2)))

        q3 = Button(
            text="Solo marcar",
            background_normal="",
            background_color=(0.70, 0.72, 0.76, 1),
            color=TEXT,
            bold=True,
            font_size="10sp",
        )
        q3.bind(on_release=lambda *_: self.set_quick_amount(0))

        quick_row.add_widget(q1)
        quick_row.add_widget(q2)
        quick_row.add_widget(q3)

        form.add_widget(quick_row)

        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(198))

        self.valor_cuota = AppTextInput(text=str(self.cliente["cuota"]))
        self.saldo_actual = AppTextInput(text=str(self.cliente["saldo"]))
        self.valor_pagar = AppTextInput(text=str(self.cliente["cuota"]))
        self.numero_cuotas = AppTextInput(text="1")
        self.nuevo_saldo = AppTextInput(text=str(max(self.cliente["saldo"] - self.cliente["cuota"], 0)))
        self.metodo_pago = Spinner(
            text="Efectivo",
            values=["Efectivo", "Transferencia"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )

        fields = [
            ("Valor Cuota", self.valor_cuota),
            ("Saldo Actual", self.saldo_actual),
            ("Valor a Pagar", self.valor_pagar),
            ("N° cuotas a pagar", self.numero_cuotas),
            ("Nuevo Saldo", self.nuevo_saldo),
            ("Método Pago", self.metodo_pago),
        ]

        for label, widget in fields:
            box = BoxLayout(orientation="vertical", spacing=dp(3))
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            grid.add_widget(box)

        self.valor_pagar.bind(text=lambda *_: self.recalculate_balance())
        self.numero_cuotas.bind(text=lambda *_: self.recalculate_balance())

        form.add_widget(grid)

        self.summary_label = Label(
            text="Resumen: registrará una cuota por " + money(self.cliente["cuota"]),
            color=TEXT,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(32),
        )
        self.summary_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        form.add_widget(self.summary_label)

        btn = SmallButton("Confirmar y Registrar", bg_color=SUCCESS)
        btn.bind(on_release=lambda *_: self.confirm_transaction())
        form.add_widget(btn)

        content.add_widget(form)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

        self.apply_payment_rules()
        self.select_tipo(self.selected_tipo)
        self.recalculate_balance()

    def small_metric(self, title, value):
        box = BoxLayout(orientation="vertical", padding=[dp(6), dp(3), dp(6), dp(3)])
        with box.canvas.before:
            Color(1, 1, 1, 0.78)
            box.bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(8)])
        box.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        box.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        t = Label(
            text=title,
            color=MUTED,
            font_size="11sp",
            halign="center",
            valign="bottom",
        )
        v = Label(
            text=value,
            color=TEXT,
            bold=True,
            font_size="13sp",
            halign="center",
            valign="top",
        )
        box.add_widget(t)
        box.add_widget(v)
        return box

    def set_quick_amount(self, amount):
        self.valor_pagar.text = str(int(amount))

        try:
            cuota_base = int(float(self.valor_cuota.text or 0))
        except Exception:
            cuota_base = self.cliente.get("cuota", 0)

        if cuota_base > 0 and amount > 0:
            cuotas = max(round(amount / cuota_base), 1)
            self.numero_cuotas.text = str(cuotas)

        self.recalculate_balance()

    def select_tipo(self, tipo):
        self.selected_tipo = tipo

        for key, btn in self.tipo_buttons.items():
            if btn.disabled:
                continue
            btn.state = "down" if key == tipo else "normal"
            btn.background_color = GOLD if key == tipo else (0.88, 0.90, 0.94, 1)
            btn.color = DARK

        if tipo in ["No Pago", "Siguiente Día"]:
            self.valor_pagar.text = "0"

        if tipo == "Cuota":
            self.valor_pagar.text = str(self.cliente["cuota"])

        if tipo == "Aporte" and int(float(self.valor_pagar.text or 0)) == 0:
            self.valor_pagar.text = str(round(self.cliente["cuota"] / 2))

        self.recalculate_balance()

    def apply_payment_rules(self):
        estado = get_estado_cliente(self.cliente)

        if estado in ["pagado", "aporte"]:
            self.selected_tipo = "Aporte"
            self.warning_label.text = "Cliente ya está en verde. No se permite cobrar otra cuota; solo Aporte."
            self.warning_label.color = DANGER

            for key, btn in self.tipo_buttons.items():
                if key == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = GOLD
                    btn.color = DARK
                else:
                    btn.disabled = True
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.38, 0.38, 0.38, 1)

        elif estado == "no_pago":
            self.selected_tipo = "Aporte"
            self.warning_label.text = "Cliente está en rojo por No Pago. Si entrega dinero, regístrelo como Aporte."
            self.warning_label.color = DANGER

            for key, btn in self.tipo_buttons.items():
                if key == "Cuota":
                    btn.disabled = True
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.38, 0.38, 0.38, 1)
                else:
                    btn.disabled = False

        else:
            self.warning_label.text = "Cliente pendiente. Puede registrar Cuota, Aporte, No Pago o Siguiente Día."
            self.warning_label.color = MUTED

    def recalculate_balance(self):
        """
        Calcula el valor a pagar según el número de cuotas.

        Regla:
        Valor a pagar = Valor Cuota base × N° cuotas a pagar

        Ejemplo:
        Valor cuota base: 20.000
        N° cuotas a pagar: 2
        Valor a pagar: 40.000
        """
        try:
            saldo = int(float(self.saldo_actual.text or 0))
        except Exception:
            saldo = self.cliente.get("saldo", 0)

        try:
            cuota_base = int(float(self.valor_cuota.text or 0))
        except Exception:
            cuota_base = self.cliente.get("cuota", 0)

        try:
            numero_cuotas = int(float(self.numero_cuotas.text or 1))
        except Exception:
            numero_cuotas = 1

        if numero_cuotas <= 0:
            numero_cuotas = 1
            self.numero_cuotas.text = "1"

        tipo = self.selected_tipo

        if tipo == "Cuota":
            pago = cuota_base * numero_cuotas
            if pago > saldo:
                pago = saldo
            self.valor_pagar.text = str(pago)

        elif tipo == "Aporte":
            try:
                pago = int(float(self.valor_pagar.text or 0))
            except Exception:
                pago = 0

            if pago > saldo:
                pago = saldo
                self.valor_pagar.text = str(pago)

        else:
            pago = 0
            self.valor_pagar.text = "0"

        nuevo = max(saldo - pago, 0)
        self.nuevo_saldo.text = str(nuevo)

        if tipo in ["No Pago", "Siguiente Día"]:
            self.summary_label.text = f"Resumen: se marcará como {tipo}, sin dinero recibido."
        elif tipo == "Cuota":
            self.summary_label.text = (
                f"Resumen: registrará {numero_cuotas} cuota(s) por {money(pago)}. "
                f"Nuevo saldo: {money(nuevo)}."
            )
        else:
            self.summary_label.text = f"Resumen: registrará Aporte por {money(pago)}. Nuevo saldo: {money(nuevo)}."



    def confirm_transaction(self):
        try:
            pago = int(float(self.valor_pagar.text or 0))
        except Exception:
            pago = 0

        try:
            numero_cuotas = int(float(self.numero_cuotas.text or 1))
        except Exception:
            numero_cuotas = 1

        tipo = self.selected_tipo

        if tipo in ["Cuota", "Aporte"] and pago <= 0:
            make_popup("Valor inválido", "Para registrar Cuota o Aporte debe ingresar un valor mayor a cero.")
            return

        if tipo == "Cuota" and numero_cuotas <= 0:
            make_popup("Número inválido", "Debe indicar cuántas cuotas va a pagar el cliente.")
            return

        msg = (
            f"Cliente: {self.cliente['nombre']}\n"
            f"Tipo: {tipo}\n"
            f"Número de cuotas: {numero_cuotas if tipo == 'Cuota' else '-'}\n"
            f"Valor: {money(pago)}\n"
            f"Método: {self.metodo_pago.text}\n\n"
            f"¿Desea guardar esta transacción?"
        )

        make_confirm_popup("Confirmar transacción", msg, self.register_transaction)


    def register_transaction(self):
        try:
            pago = int(float(self.valor_pagar.text or 0))
        except Exception:
            pago = 0

        tipo = self.selected_tipo

        estado_actual = get_estado_cliente(self.cliente)

        if estado_actual in ["pagado", "aporte"] and tipo != "Aporte":
            make_popup(
                "Cobro bloqueado",
                "Este cliente ya aparece en verde porque pagó.\n"
                "No se puede cobrar otra cuota.\n"
                "Solo se permite registrar un Aporte."
            )
            return

        if estado_actual == "no_pago" and tipo == "Cuota":
            make_popup(
                "Cobro bloqueado",
                "Este cliente está marcado en rojo como No Pago.\n"
                "Si entrega dinero, regístrelo como Aporte."
            )
            return

        nuevo_saldo = max(self.cliente["saldo"] - pago, 0)

        try:
            numero_cuotas_pagadas = int(float(self.numero_cuotas.text or 1))
        except Exception:
            numero_cuotas_pagadas = 1

        if numero_cuotas_pagadas <= 0:
            numero_cuotas_pagadas = 1

        if tipo == "Cuota":
            self.cliente["saldo"] = nuevo_saldo
            self.cliente["pagadas"] += numero_cuotas_pagadas
            self.cliente["pendientes"] = max(self.cliente["pendientes"] - numero_cuotas_pagadas, 0)
            self.cliente["estado"] = "pagado"
            self.cliente["ultimo_tipo"] = f"{numero_cuotas_pagadas} cuota(s) pagada(s)"
            self.cliente["fecha_ultimo_pago"] = today_iso()
            self.cliente["proxima_fecha_cobro"] = next_due_date(self.cliente.get("cobro", "Diario"))

        elif tipo == "Aporte":
            self.cliente["saldo"] = nuevo_saldo
            self.cliente["estado"] = "aporte"
            self.cliente["ultimo_tipo"] = "Aporte"
            self.cliente["fecha_ultimo_pago"] = today_iso()
            self.cliente["proxima_fecha_cobro"] = next_due_date(self.cliente.get("cobro", "Diario"))

        elif tipo == "No Pago":
            self.cliente["estado"] = "no_pago"
            self.cliente["ultimo_tipo"] = "No pagó"
            self.cliente["fecha_ultimo_pago"] = today_iso()
            self.cliente["proxima_fecha_cobro"] = next_due_date("Diario")
            pago = 0

        elif tipo == "Siguiente Día":
            self.cliente["estado"] = "siguiente"
            self.cliente["ultimo_tipo"] = "Siguiente día"
            self.cliente["fecha_ultimo_pago"] = today_iso()
            self.cliente["proxima_fecha_cobro"] = next_due_date("Diario")
            pago = 0

        # Si el saldo queda en 0, el crédito se finaliza:
        # sale de la lista activa, pero queda en el historial.
        if self.cliente.get("saldo", 0) <= 0:
            self.cliente["saldo"] = 0
            self.cliente["pendientes"] = 0
            self.cliente["activo"] = 0
            self.cliente["estado"] = "finalizado"
            self.cliente["ultimo_tipo"] = "Crédito finalizado"
            self.cliente["fecha_finalizacion"] = today_text()
            self.cliente["proxima_fecha_cobro"] = None

        transaccion = {
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente["nombre"],
            "tipo": tipo,
            "valor": pago,
            "metodo": self.metodo_pago.text,
            "fecha": today_text(),
            "synced": 0,
        }

        TRANSACCIONES.append(transaccion)

        update_client_in_db(self.cliente)
        insert_transaction_db(transaccion)
        refresh_memory_from_db()

        if self.cliente.get("activo", 1) == 0:
            message = f"{tipo} registrado por {money(pago)}. Saldo en cero. El cliente pasa al historial."
        elif tipo in ["Cuota", "Aporte"]:
            message = f"{tipo} registrado por {money(pago)}. El cliente queda en verde."
        elif tipo == "No Pago":
            message = "Cliente marcado en rojo como No Pago."
        else:
            message = "Cliente marcado en amarillo para Siguiente Día."

        make_popup("Transacción registrada", message)
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)


# ============================================================
# BLOQUES COLAPSABLES
# ============================================================

class CollapsibleBlock(BoxLayout):
    def __init__(self, title, content_widgets, opened=True, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(6), **kwargs)
        self.title = title
        self.content_widgets = content_widgets
        self.opened = opened
        self.header_btn = Button(
            text=f"  -  {title}" if opened else f"  +  {title}",
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            halign="left",
        )
        self.header_btn.bind(on_release=lambda *_: self.toggle())
        self.add_widget(self.header_btn)

        self.content_box = RoundedBox(orientation="vertical", spacing=dp(8), padding=dp(10), size_hint_y=None)
        for w in self.content_widgets:
            self.content_box.add_widget(w)

        self.add_widget(self.content_box)
        self.update_height()

    def toggle(self):
        self.opened = not self.opened
        self.header_btn.text = f"  -  {self.title}" if self.opened else f"  +  {self.title}"

        if self.opened:
            if self.content_box.parent is None:
                self.add_widget(self.content_box)
        else:
            if self.content_box.parent:
                self.remove_widget(self.content_box)

        self.update_height()

    def update_height(self):
        if self.opened:
            self.content_box.height = sum([child.height for child in self.content_box.children]) + dp(26) + (len(self.content_widgets) * dp(4))
            self.height = dp(42) + self.content_box.height + dp(8)
        else:
            self.height = dp(46)


def labeled_input(label, hint="", text="", multiline=False):
    box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(68) if not multiline else dp(114))
    box.add_widget(FieldLabel(label))
    box.add_widget(AppTextInput(hint_text=hint, text=text, multiline=multiline))
    return box


# ============================================================
# INTERFAZ 3: NUEVO CLIENTE Y PRÉSTAMO
# ============================================================

class NuevoClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="nuevo_cliente", **kwargs)

        root = BoxLayout(orientation="vertical", spacing=0)
        root.add_widget(Header("Nuevo Cliente y Crédito"))

        scroll = ScrollView()
        self.content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(96)],
            spacing=dp(12),
            size_hint_y=None,
        )
        self.content.bind(minimum_height=self.content.setter("height"))

        # Tarjeta bienvenida
        hero = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(138),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(8),
        )
        hero.bg_color = BLUE_SOFT

        hero_title = Label(
            text="Registro rápido para cobrador",
            color=BLUE,
            bold=True,
            font_size="18sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        hero_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        hero_desc = Label(
            text="Ingresa los datos principales. Los valores se formatean con puntos de mil automáticamente.",
            color=MUTED,
            font_size="12sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(46),
        )
        hero_desc.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        hero_tip = Label(
            text="Tip: usa los montos rápidos para llenar el crédito más rápido.",
            color=BLUE_DARK,
            font_size="11sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        hero_tip.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        hero.add_widget(hero_title)
        hero.add_widget(hero_desc)
        hero.add_widget(hero_tip)
        self.content.add_widget(hero)

        # Campos
        self.documento = AppTextInput(hint_text="Ej: 1045000000")
        self.nombre = AppTextInput(hint_text="Nombre completo")
        self.movil = AppTextInput(hint_text="3000000000")
        self.direccion = AppTextInput(hint_text="Barrio, calle, referencia")

        self.producto = AppTextInput(text="5 - CRÉDITO EN EFECTIVO")
        self.valor_producto = MoneyInput(hint_text="Ej: 500.000")
        self.numero_cuotas = AppTextInput(hint_text="Ej: 25")
        self.valor_cuota = MoneyInput(hint_text="Automático")
        self.valor_cuota.readonly = True
        self.interes = AppTextInput(hint_text="Ej: 20")
        self.cobro = Spinner(
            text="Diario",
            values=["Diario", "Semanal", "Quincenal", "Mensual"],
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=(0.97, 0.98, 1, 1),
            color=TEXT,
        )
        self.cobro.bind(text=lambda *_: self.on_cobro_change())

        self.nombre_codeudor = AppTextInput(hint_text="Opcional")
        self.movil_codeudor = AppTextInput(hint_text="Opcional")
        self.valor_seguro = MoneyInput(hint_text="Ej: 10.000")
        self.beneficiario = AppTextInput(hint_text="Opcional")

        # Secciones
        self.content.add_widget(self.create_section(
            title="1. Datos del cliente",
            subtitle="Información básica para identificar al cliente en ruta",
            fields=[
                ("Documento", self.documento),
                ("Nombre", self.nombre),
                ("Móvil +57", self.movil),
                ("Dirección", self.direccion),
            ],
            accent_color=BLUE
        ))

        self.content.add_widget(self.create_section(
            title="2. Datos del crédito",
            subtitle="Define el valor del préstamo, cuota e interés",
            fields=[
                ("Producto", self.producto),
                ("Valor Producto", self.valor_producto),
                ("Número de cuotas/días", self.numero_cuotas),
                ("Valor Cuota automático", self.valor_cuota),
                ("Interés %", self.interes),
                ("Cobro", self.cobro),
            ],
            accent_color=(0.15, 0.45, 0.78, 1)
        ))

        self.valor_producto.bind(text=lambda *_: self.recalculate_auto_cuota())
        self.numero_cuotas.bind(text=lambda *_: self.recalculate_auto_cuota())
        self.interes.bind(text=lambda *_: self.recalculate_auto_cuota())

        # Resumen dinámico del crédito
        self.summary_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(160),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(7),
        )
        self.summary_card.bg_color = GOLD_SOFT

        self.summary_card.add_widget(Label(
            text="Resumen del crédito",
            color=DARK,
            bold=True,
            font_size="16sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))

        self.summary_label = Label(
            text="Ingrese valor del producto y cuota para calcular el crédito.",
            color=TEXT,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(90),
        )
        self.summary_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.summary_card.add_widget(self.summary_label)

        self.content.add_widget(self.summary_card)

        self.content.add_widget(self.create_section(
            title="3. Datos opcionales",
            subtitle="Codeudor y seguro",
            fields=[
                ("Nombre Codeudor", self.nombre_codeudor),
                ("Móvil Codeudor", self.movil_codeudor),
                ("Valor Seguro", self.valor_seguro),
                ("Beneficiario", self.beneficiario),
            ],
            accent_color=(0.31, 0.31, 0.62, 1)
        ))

        # Montos rápidos
        quick = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(122),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
        )
        quick.bg_color = WHITE

        quick.add_widget(Label(
            text="Montos rápidos",
            color=TEXT,
            bold=True,
            font_size="15sp",
            halign="left",
            size_hint_y=None,
            height=dp(22),
        ))

        quick_row = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(48))
        for label, amount in [("300.000", 300000), ("500.000", 500000), ("1.000.000", 1000000)]:
            btn = Button(
                text=label,
                background_normal="",
                background_color=BLUE,
                color=WHITE,
                bold=True,
                font_size="12sp",
            )
            btn.bind(on_release=lambda _, a=amount: self.set_quick_credit(a))
            quick_row.add_widget(btn)

        quick.add_widget(quick_row)
        self.content.add_widget(quick)

        btn = SmallButton("Crear Cliente y Activar Crédito", bg_color=SUCCESS)
        btn.height = dp(50)
        btn.font_size = "14sp"
        btn.bind(on_release=lambda *_: self.create_client())
        self.content.add_widget(btn)

        scroll.add_widget(self.content)
        root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(72))
        root.add_widget(self.nav_container)

        self.add_widget(root)

        self.update_credit_summary()

    def create_section(self, title, subtitle, fields, accent_color=BLUE):
        section_height = dp(86)
        for _, widget in fields:
            section_height += dp(72)

        section = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=section_height,
            padding=[dp(0), dp(0), dp(0), dp(12)],
            spacing=dp(0),
        )
        section.bg_color = WHITE

        # Encabezado interno de la tarjeta
        head = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(68),
            padding=[dp(14), dp(10), dp(14), dp(8)],
            spacing=dp(2),
        )
        with head.canvas.before:
            Color(*accent_color)
            head.bg = RoundedRectangle(pos=head.pos, size=head.size, radius=[dp(16), dp(16), 0, 0])
        head.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        head.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        title_lbl = Label(
            text=title,
            color=WHITE,
            bold=True,
            font_size="15sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        )
        title_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        subtitle_lbl = Label(
            text=subtitle,
            color=(0.90, 0.94, 1, 1),
            font_size="11sp",
            halign="left",
            size_hint_y=None,
            height=dp(18),
        )
        subtitle_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        head.add_widget(title_lbl)
        head.add_widget(subtitle_lbl)
        section.add_widget(head)

        body = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=section_height - dp(74),
            padding=[dp(14), dp(12), dp(14), dp(0)],
            spacing=dp(8),
        )

        for label, widget in fields:
            box = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(68),
                spacing=dp(4),
            )
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            body.add_widget(box)

        section.add_widget(body)
        return section

    def on_cobro_change(self):
        """
        Cuando cambia la frecuencia, si el usuario no ha definido número de cuotas,
        se sugiere un número. Si ya escribió uno, se respeta.
        """
        if not self.numero_cuotas.text.strip():
            if self.cobro.text == "Diario":
                self.numero_cuotas.text = "25"
            elif self.cobro.text == "Semanal":
                self.numero_cuotas.text = "6"
            elif self.cobro.text == "Quincenal":
                self.numero_cuotas.text = "4"
            else:
                self.numero_cuotas.text = "2"

        self.recalculate_auto_cuota()

    def set_quick_credit(self, amount):
        self.valor_producto.text = format_thousands(amount)

        # Sugerencia de número de cuotas según frecuencia.
        # El cobrador puede cambiar este número manualmente.
        if self.cobro.text == "Diario":
            cuotas = 25
        elif self.cobro.text == "Semanal":
            cuotas = 6
        elif self.cobro.text == "Quincenal":
            cuotas = 4
        else:
            cuotas = 2

        self.numero_cuotas.text = str(cuotas)
        self.recalculate_auto_cuota()

    def recalculate_auto_cuota(self):
        """
        Calcula automáticamente la cuota incluyendo intereses.

        Fórmula:
        Interés = Valor Producto * (Interés % / 100)
        Total a recaudar = Valor Producto + Interés
        Valor Cuota = Total a recaudar / Número de cuotas o días

        Ejemplo:
        Valor Producto: 600.000
        Interés: 20%
        Total a recaudar: 720.000
        Número de cuotas: 6
        Cuota automática: 120.000
        """
        capital = parse_money(self.valor_producto.text)

        try:
            cuotas = int(float(self.numero_cuotas.text or 0))
        except Exception:
            cuotas = 0

        try:
            interes_pct = float((self.interes.text or "0").replace(",", "."))
        except Exception:
            interes_pct = 0

        interes_valor = round(capital * (interes_pct / 100))
        total_recaudar = capital + interes_valor

        if total_recaudar > 0 and cuotas > 0:
            cuota = round(total_recaudar / cuotas)
            self.valor_cuota.text = format_thousands(cuota)
        else:
            self.valor_cuota.text = ""

        self.update_credit_summary()

    def update_credit_summary(self):
        if not hasattr(self, "summary_label"):
            return

        saldo = parse_money(self.valor_producto.text)
        cuota = parse_money(self.valor_cuota.text)
        cobro = self.cobro.text if hasattr(self, "cobro") else "Diario"

        try:
            cuotas = int(float(self.numero_cuotas.text or 0))
        except Exception:
            cuotas = 0

        if saldo <= 0 or cuotas <= 0 or cuota <= 0:
            self.summary_label.text = (
                "Ingrese el valor del crédito y el número de cuotas/días.\n"
                "Ejemplo: crédito 600.000, 6 cuotas y cobro Semanal."
            )
            return

        try:
            interes_pct = float((self.interes.text or "0").replace(",", "."))
        except Exception:
            interes_pct = 0

        interes_valor = round(saldo * (interes_pct / 100))
        total_estimado = saldo + interes_valor
        total_por_cuotas = cuota * cuotas

        self.summary_label.text = (
            f"• Valor prestado: {money(saldo)}\n"
            f"• Interés: {interes_pct:.2f}% = {money(interes_valor)}\n"
            f"• Total a recaudar: {money(total_estimado)}\n"
            f"• Número de cuotas/días: {cuotas}\n"
            f"• Cuota automática: {money(cuota)}  |  Cobro: {cobro}"
        )

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="nuevo"))

    def create_client(self):
        nombre = self.nombre.text.strip().upper()
        movil = self.movil.text.strip()

        if not nombre:
            make_popup("Falta nombre", "Debe ingresar el nombre del cliente.")
            return

        if not movil:
            make_popup("Falta móvil", "Debe ingresar el número móvil del cliente.")
            return

        capital = parse_money(self.valor_producto.text)

        try:
            pendientes = int(float(self.numero_cuotas.text or 0))
        except Exception:
            pendientes = 0

        try:
            interes_pct = float((self.interes.text or "0").replace(",", "."))
        except Exception:
            interes_pct = 0

        interes_valor = round(capital * (interes_pct / 100))
        saldo = capital + interes_valor

        # Recalcular cuota antes de guardar, por seguridad.
        if pendientes > 0:
            cuota = round(saldo / pendientes)
            self.valor_cuota.text = format_thousands(cuota)
        else:
            cuota = 0

        if capital <= 0:
            make_popup("Valor inválido", "Debe ingresar el valor del crédito.")
            return

        if pendientes <= 0:
            make_popup("Número inválido", "Debe ingresar el número de cuotas o días.")
            return

        if cuota <= 0:
            make_popup("Cuota inválida", "El valor de cuota no se pudo calcular. Revise valor del crédito y número de cuotas.")
            return

        nuevo = {
            "id": None,
            "nombre": nombre,
            "telefono": f"+57 {movil}",
            "cuota": cuota,
            "saldo": saldo,
            "pagadas": 0,
            "pendientes": pendientes,
            "estado": "pendiente",
            "ultimo_tipo": "Pendiente",
            "documento": self.documento.text.strip(),
            "direccion": self.direccion.text.strip(),
            "activo": 1,
            "fecha_finalizacion": None,
            "cobro": self.cobro.text,
            "fecha_ultimo_pago": None,
            "proxima_fecha_cobro": today_iso(),
        }

        nuevo["id"] = insert_client_db(nuevo)
        CLIENTES.append(nuevo)
        refresh_memory_from_db()

        make_popup(
            "Cliente creado",
            f"Cliente creado correctamente.\n"
            f"Cobro: {self.cobro.text}\n"
            f"Valor prestado: {money(capital)}\n"
            f"Interés: {interes_pct:.2f}% = {money(interes_valor)}\n"
            f"Total a recaudar: {money(saldo)}\n"
            f"Número de cuotas/días: {pendientes}\n"
            f"Cuota automática: {money(cuota)}"
        )
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.8)


# ============================================================
# INTERFAZ 4: MOVIMIENTOS DE CAJA
# ============================================================

class MovimientosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="movimientos", **kwargs)

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Movimientos de Caja"))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(80)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        type_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(104))
        type_card.add_widget(FieldLabel("Tipo de movimiento"))

        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        self.egreso = ToggleButton(
            text="(*) Egreso",
            group="mov",
            state="down",
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
        )
        self.ingreso = ToggleButton(
            text="Ingreso",
            group="mov",
            background_normal="",
            background_color=(0.88, 0.90, 0.94, 1),
            color=TEXT,
            bold=True,
        )

        self.egreso.bind(on_release=self.update_type)
        self.ingreso.bind(on_release=self.update_type)

        row.add_widget(self.egreso)
        row.add_widget(self.ingreso)
        type_card.add_widget(row)
        content.add_widget(type_card)

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(330))

        form.add_widget(FieldLabel("Concepto ()"))
        self.concepto = Spinner(
            text="Seleccione concepto",
            values=[
                "Transporte",
                "Alimentación",
                "Papelería",
                "Recaudo adicional",
                "Ajuste de caja",
                "Otro",
            ],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        form.add_widget(self.concepto)

        form.add_widget(FieldLabel("Valor a pagar ()"))
        self.valor = AppTextInput(hint_text="Ej: 50000")
        form.add_widget(self.valor)

        form.add_widget(FieldLabel("Observaciones"))
        self.obs = AppTextInput(hint_text="Escriba observaciones", multiline=True)
        form.add_widget(self.obs)

        save = PillButton("[OK] Guardar", bg_color=DARK)
        save.bind(on_release=lambda *_: self.save_movement())
        form.add_widget(save)

        content.add_widget(form)

        scroll.add_widget(content)
        root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(62))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="caja"))

    def update_type(self, *_):
        self.egreso.background_color = GOLD if self.egreso.state == "down" else (0.88, 0.90, 0.94, 1)
        self.ingreso.background_color = GOLD if self.ingreso.state == "down" else (0.88, 0.90, 0.94, 1)
        self.egreso.text = "(*) Egreso" if self.egreso.state == "down" else "( ) Egreso"
        self.ingreso.text = "(*) Ingreso" if self.ingreso.state == "down" else "( ) Ingreso"

    def save_movement(self):
        tipo = "Egreso" if self.egreso.state == "down" else "Ingreso"

        try:
            valor = int(float(self.valor.text or 0))
        except Exception:
            valor = 0

        movimiento = {
            "tipo": tipo,
            "concepto": self.concepto.text,
            "valor": valor,
            "observaciones": self.obs.text,
            "fecha": today_text(),
            "synced": 0,
        }

        MOVIMIENTOS_CAJA.append(movimiento)

        # Guardado offline real en SQLite
        insert_movement_db(movimiento)
        refresh_memory_from_db()

        make_popup("Movimiento guardado", f"{tipo} registrado por {money(valor)}.")
        self.valor.text = ""
        self.obs.text = ""
        self.concepto.text = "Seleccione concepto"


# ============================================================
# INTERFAZ 5: RESUMEN DEL DÍA
# ============================================================

class MetricRow(BoxLayout):
    def __init__(self, left, right, highlight=False, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(38) if not highlight else dp(46),
            padding=[dp(10), 0, dp(10), 0],
            **kwargs
        )

        bg_color = (0.98, 0.98, 1, 1) if not highlight else (1.0, 0.95, 0.78, 1)
        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        l = Label(
            text=left,
            color=TEXT if highlight else MUTED,
            bold=highlight,
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        l.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        r = Label(
            text=right,
            color=TEXT,
            bold=highlight,
            font_size="13sp",
            halign="right",
            valign="middle",
        )
        r.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(l)
        self.add_widget(r)

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

        self.root.add_widget(Header(
            "::V12:: Resumen del Día",
            show_back=True,
            on_back=lambda: self.app_ref.go("clientes"),
        ))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        report = RoundedBox(orientation="vertical", spacing=dp(7), padding=dp(10), size_hint_y=None)
        report.bind(minimum_height=report.setter("height"))

        total_clientes = len(CLIENTES)
        clientes_finalizados = len(load_historial_clientes())
        clientes_nuevos = total_clientes
        pagos = len([t for t in TRANSACCIONES if t["tipo"] in ["Cuota", "Aporte"]])
        no_pagos = len([t for t in TRANSACCIONES if t["tipo"] == "No Pago"])
        aplazados = len([t for t in TRANSACCIONES if t["tipo"] == "Siguiente Día"])

        recaudo_dia = sum(t["valor"] for t in TRANSACCIONES if t["tipo"] in ["Cuota", "Aporte"])
        ingresos = sum(m["valor"] for m in MOVIMIENTOS_CAJA if m["tipo"] == "Ingreso")
        egresos = sum(m["valor"] for m in MOVIMIENTOS_CAJA if m["tipo"] == "Egreso")

        caja_inicial = 350000
        recaudo_esperado = sum(c["cuota"] for c in CLIENTES)
        total_ventas = recaudo_dia + ingresos
        retiros_caja = 80000
        retiro_seguro = 15000
        ingresos_seguro = 30000
        caja_seguro = ingresos_seguro - retiro_seguro
        efectivo_transferencia = recaudo_dia
        saldo_caja = caja_inicial + recaudo_dia + ingresos + ingresos_seguro - egresos - retiros_caja - retiro_seguro
        pendientes_sync = count_pending_sync()

        rows = [
            ("Vendedor", "CORREDOR - LUIS"),
            ("Fecha de Ruta", today_text()),
            ("Clientes Ausentes", str(no_pagos)),
            ("Aplazados Siguiente Día", str(aplazados)),
            ("Número Clientes", str(total_clientes)),
            ("Clientes Nuevos", str(clientes_nuevos)),
            ("Clientes Finalizados", str(clientes_finalizados)),
            ("Pagos Registrados", f"{pagos} / {total_clientes} Adicionales: 0"),
            ("Caja Inicial", money(caja_inicial)),
            ("Recaudo Esperado", money(recaudo_esperado)),
            ("Recaudo del día", money(recaudo_dia)),
            ("Efectivo/Transferencia", money(efectivo_transferencia)),
            ("Total Ventas", money(total_ventas)),
            ("Retiros Caja", money(retiros_caja)),
            ("Egresos", money(egresos)),
            ("Ingresos", money(ingresos)),
            ("Retiro de Caja Seguros", money(retiro_seguro)),
            ("Ingresos de Seguros", money(ingresos_seguro)),
            ("Caja Seguros", money(caja_seguro)),
            ("Registros pendientes de nube", str(pendientes_sync)),
            ("Sincronización Automática", self.sync_status),
        ]

        for left, right in rows:
            report.add_widget(MetricRow(left, right))

        report.add_widget(MetricRow("Saldo en Caja", money(saldo_caja), highlight=True))

        content.add_widget(report)

        actions = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(122), spacing=dp(8))

        row1 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row1.add_widget(PillButton("X  No Pagos", bg_color=DARK))
        row1.add_widget(PillButton("CFG Config.", bg_color=DARK))

        row2 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row2.add_widget(PillButton("RE  Reaj...", bg_color=DARK))
        cloud = PillButton("NUBE Carga", bg_color=BLUE)
        cloud.bind(on_release=lambda *_: self.simulate_cloud_upload())
        row2.add_widget(cloud)

        actions.add_widget(row1)
        actions.add_widget(row2)

        content.add_widget(actions)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def simulate_cloud_upload(self):
        self.sync_status = "Enviando datos a la nube..."
        self.build()

        def complete_sync(*_):
            mark_all_as_synced()
            refresh_memory_from_db()
            self.sync_status = "Sincronizado correctamente"
            self.build()
            make_popup(
                "Carga completa",
                "Los datos fueron enviados a la nube correctamente.\nModo online simulado."
            )

        Clock.schedule_once(complete_sync, 1.4)



# ============================================================
# INTERFAZ 6: HISTORIAL DE CLIENTES FINALIZADOS
# ============================================================

class HistorialCard(RoundedBox):
    def __init__(self, cliente, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(112),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(5),
            **kwargs
        )
        self.bg_color = (0.92, 0.98, 0.94, 1)

        title = Label(
            text=cliente.get("nombre", ""),
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        info1 = Label(
            text=f"Tel: {cliente.get('telefono', '')}  |  Documento: {cliente.get('documento', '')}",
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        info1.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        info2 = Label(
            text=f"Cobro: {cliente.get('cobro', 'Diario')}  |  Cuotas pagadas: {cliente.get('pagadas', 0)}  |  Saldo final: {money(cliente.get('saldo', 0))}",
            color=TEXT,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        info2.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        info3 = Label(
            text=f"Finalizado: {cliente.get('fecha_finalizacion') or 'Sin fecha'}",
            color=STATUS_BORDER_GREEN,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        info3.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(title)
        self.add_widget(info1)
        self.add_widget(info2)
        self.add_widget(info3)


class HistorialScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="historial", **kwargs)

        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.build()

    def build(self):
        self.root.clear_widgets()

        self.root.add_widget(Header(
            "Historial de Créditos",
            show_back=True,
            on_back=lambda: self.app_ref.go("clientes"),
        ))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        historial = load_historial_clientes()

        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(4),
        )
        summary.bg_color = WHITE

        summary.add_widget(Label(
            text="Clientes con saldo en cero",
            color=TEXT,
            bold=True,
            font_size="15sp",
            halign="left",
            size_hint_y=None,
            height=dp(28),
        ))

        summary.add_widget(Label(
            text=f"Total finalizados: {len(historial)}",
            color=MUTED,
            font_size="13sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))

        content.add_widget(summary)

        if not historial:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(110),
                padding=dp(12),
            )
            empty.bg_color = WHITE
            empty.add_widget(Label(
                text="Todavía no hay clientes finalizados.\nCuando un saldo llegue a 0, aparecerá aquí.",
                color=MUTED,
                font_size="13sp",
                halign="center",
                valign="middle",
            ))
            content.add_widget(empty)
        else:
            for cliente in historial:
                content.add_widget(HistorialCard(cliente))

        scroll.add_widget(content)
        self.root.add_widget(scroll)


# ============================================================
# APP PRINCIPAL
# ============================================================

class CobrosV12App(App):
    selected_client = None

    def build(self):
        self.title = "Cobros V12 Mobile"
        self.icon = asset_path("icon.png")

        # Base de datos local offline
        init_database()
        seed_database_if_empty()
        refresh_memory_from_db()

        # Marco móvil centrado:
        # En computador evita que la app se estire demasiado.
        # En celular ocupa el ancho disponible.
        self.shell = AnchorLayout(anchor_x="center", anchor_y="top")

        self.sm = ScreenManager(
            transition=NoTransition(),
            size_hint=(None, 1),
            width=min(Window.width, dp(430)),
        )

        self.sm.add_widget(ClientesScreen())
        self.sm.add_widget(CuotaScreen())
        self.sm.add_widget(NuevoClienteScreen())
        self.sm.add_widget(MovimientosScreen())
        self.sm.add_widget(ResumenScreen())
        self.sm.add_widget(HistorialScreen())

        self.shell.add_widget(self.sm)

        Window.bind(size=self.update_mobile_width)

        return self.shell

    def update_mobile_width(self, *_):
        if hasattr(self, "sm"):
            self.sm.width = min(Window.width, dp(430))

    def go(self, screen_name):
        self.sm.current = screen_name


if __name__ == "__main__":
    CobrosV12App().run()
