"""
Excalibur — Monitor Manager (arquivo único)

Menu radial (botão X2 do mouse) com TRÊS opções:
    1. Mover Janela      -> mover a janela ativa para outro monitor
    2. Perfis de Monitor -> aplicar um perfil pré-configurado (liga/desliga telas)
    3. Configuração      -> criar / editar / excluir perfis

Dependências: pip install PySide6 pynput pygetwindow screeninfo
Rodar:        python Excalibur_Monitor.py

Perfis salvos em: excalibur_perfis.json (mesma pasta do script)
"""

import os
import sys
import json
import math
import time
import ctypes
from ctypes import wintypes, Structure, Union, byref, sizeof, memmove, POINTER

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Slot, QMetaObject, Q_ARG, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QFrame, QLineEdit, QCheckBox, QScrollArea, QKeySequenceEdit
)

from pynput import mouse, keyboard

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_PATH = os.path.join(SCRIPT_DIR, "excalibur_perfis.json")

# ----- controle de janela -----
try:
    import pygetwindow as gw
    from screeninfo import get_monitors
    WINDOW_CONTROL_AVAILABLE = True
except ImportError:
    WINDOW_CONTROL_AVAILABLE = False
    print("AVISO: instale -> pip install pygetwindow screeninfo")


# =====================================================================
#  DISPLAY MANAGER (Windows CCD API)
# =====================================================================

QDC_ALL_PATHS = 0x00000001
SDC_APPLY = 0x00000080
SDC_USE_SUPPLIED_DISPLAY_CONFIG = 0x00000020
SDC_SAVE_TO_DATABASE = 0x00000200
SDC_ALLOW_CHANGES = 0x00000400
SDC_VALIDATE = 0x00000040
SDC_TOPOLOGY_EXTEND = 0x00000004

DISPLAYCONFIG_PATH_ACTIVE = 0x00000001
DISPLAYCONFIG_PATH_MODE_IDX_INVALID = 0xFFFFFFFF
DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME = 2
ERROR_SUCCESS = 0


class LUID(Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_RATIONAL(Structure):
    _fields_ = [("Numerator", wintypes.DWORD), ("Denominator", wintypes.DWORD)]


class DISPLAYCONFIG_2DREGION(Structure):
    _fields_ = [("cx", wintypes.DWORD), ("cy", wintypes.DWORD)]


class DISPLAYCONFIG_PATH_SOURCE_INFO(Structure):
    _fields_ = [
        ("adapterId", LUID), ("id", wintypes.DWORD),
        ("modeInfoIdx", wintypes.DWORD), ("statusFlags", wintypes.DWORD),
    ]


class DISPLAYCONFIG_PATH_TARGET_INFO(Structure):
    _fields_ = [
        ("adapterId", LUID), ("id", wintypes.DWORD), ("modeInfoIdx", wintypes.DWORD),
        ("outputTechnology", wintypes.DWORD), ("rotation", wintypes.DWORD),
        ("scaling", wintypes.DWORD), ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", wintypes.DWORD), ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.DWORD),
    ]


class DISPLAYCONFIG_PATH_INFO(Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", wintypes.DWORD),
    ]


class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(Structure):
    _fields_ = [
        ("pixelRate", ctypes.c_uint64), ("hSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("vSyncFreq", DISPLAYCONFIG_RATIONAL), ("activeSize", DISPLAYCONFIG_2DREGION),
        ("totalSize", DISPLAYCONFIG_2DREGION), ("videoStandard", wintypes.DWORD),
        ("scanLineOrdering", wintypes.DWORD),
    ]


class DISPLAYCONFIG_TARGET_MODE(Structure):
    _fields_ = [("targetVideoSignalInfo", DISPLAYCONFIG_VIDEO_SIGNAL_INFO)]


class POINTL(Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class DISPLAYCONFIG_SOURCE_MODE(Structure):
    _fields_ = [
        ("width", wintypes.DWORD), ("height", wintypes.DWORD),
        ("pixelFormat", wintypes.DWORD), ("position", POINTL),
    ]


class RECTL(Structure):
    _fields_ = [
        ("left", wintypes.LONG), ("top", wintypes.LONG),
        ("right", wintypes.LONG), ("bottom", wintypes.LONG),
    ]


class DISPLAYCONFIG_DESKTOP_IMAGE_INFO(Structure):
    _fields_ = [
        ("PathSourceSize", POINTL), ("DesktopImageRegion", RECTL),
        ("DesktopImageClip", RECTL),
    ]


class DISPLAYCONFIG_MODE_INFO_UNION(Union):
    _fields_ = [
        ("targetMode", DISPLAYCONFIG_TARGET_MODE),
        ("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
        ("desktopImageInfo", DISPLAYCONFIG_DESKTOP_IMAGE_INFO),
    ]


class DISPLAYCONFIG_MODE_INFO(Structure):
    _fields_ = [
        ("infoType", wintypes.DWORD), ("id", wintypes.DWORD),
        ("adapterId", LUID), ("mode", DISPLAYCONFIG_MODE_INFO_UNION),
    ]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(Structure):
    _fields_ = [
        ("type", wintypes.DWORD), ("size", wintypes.DWORD),
        ("adapterId", LUID), ("id", wintypes.DWORD),
    ]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER), ("flags", wintypes.DWORD),
        ("outputTechnology", wintypes.DWORD), ("edidManufactureId", wintypes.WORD),
        ("edidProductCodeId", wintypes.WORD), ("connectorInstance", wintypes.DWORD),
        ("monitorFriendlyDeviceName", ctypes.c_wchar * 64),
        ("monitorDevicePath", ctypes.c_wchar * 128),
    ]


_IS_WINDOWS = sys.platform.startswith("win")

if _IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _user32.GetDisplayConfigBufferSizes.argtypes = [
        wintypes.DWORD, POINTER(wintypes.DWORD), POINTER(wintypes.DWORD)]
    _user32.GetDisplayConfigBufferSizes.restype = wintypes.LONG
    _user32.QueryDisplayConfig.argtypes = [
        wintypes.DWORD, POINTER(wintypes.DWORD), POINTER(DISPLAYCONFIG_PATH_INFO),
        POINTER(wintypes.DWORD), POINTER(DISPLAYCONFIG_MODE_INFO), ctypes.c_void_p]
    _user32.QueryDisplayConfig.restype = wintypes.LONG
    _user32.SetDisplayConfig.argtypes = [
        wintypes.DWORD, POINTER(DISPLAYCONFIG_PATH_INFO),
        wintypes.DWORD, POINTER(DISPLAYCONFIG_MODE_INFO), wintypes.DWORD]
    _user32.SetDisplayConfig.restype = wintypes.LONG
    _user32.DisplayConfigGetDeviceInfo.argtypes = [POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]
    _user32.DisplayConfigGetDeviceInfo.restype = wintypes.LONG


class DisplayManager:
    def __init__(self):
        self.available = _IS_WINDOWS

    def _query(self, flags):
        n_paths = wintypes.DWORD()
        n_modes = wintypes.DWORD()
        err = _user32.GetDisplayConfigBufferSizes(flags, byref(n_paths), byref(n_modes))
        if err != ERROR_SUCCESS:
            raise OSError(f"GetDisplayConfigBufferSizes falhou: {err}")
        paths = (DISPLAYCONFIG_PATH_INFO * n_paths.value)()
        modes = (DISPLAYCONFIG_MODE_INFO * n_modes.value)()
        err = _user32.QueryDisplayConfig(flags, byref(n_paths), paths, byref(n_modes), modes, None)
        if err != ERROR_SUCCESS:
            raise OSError(f"QueryDisplayConfig falhou: {err}")
        return paths, n_paths.value, modes, n_modes.value

    def _friendly_name(self, adapter_id, target_id):
        """Nome de EDID do monitor. None se não for um monitor real (fantasma)."""
        name = DISPLAYCONFIG_TARGET_DEVICE_NAME()
        name.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
        name.header.size = sizeof(DISPLAYCONFIG_TARGET_DEVICE_NAME)
        name.header.adapterId = adapter_id
        name.header.id = target_id
        err = _user32.DisplayConfigGetDeviceInfo(byref(name.header))
        if err != ERROR_SUCCESS:
            return None
        friendly = name.monitorFriendlyDeviceName.strip()
        return friendly if friendly else None   # sem nome de EDID = fantasma

    def list_monitors(self):
        """Só monitores REAIS (com nome de EDID)."""
        if not self.available:
            return []
        paths, n_paths, _, _ = self._query(QDC_ALL_PATHS)
        seen, order = {}, []
        for i in range(n_paths):
            t = paths[i].targetInfo
            key = (t.adapterId.LowPart, t.adapterId.HighPart, t.id)
            active = bool(paths[i].flags & DISPLAYCONFIG_PATH_ACTIVE)
            if key not in seen:
                nome = self._friendly_name(t.adapterId, t.id)
                if nome is None:
                    continue  # fantasma -> ignora
                seen[key] = {"key": key, "name": nome, "active": active}
                order.append(key)
            elif active:
                seen[key]["active"] = True
        return [seen[k] for k in order]

    def snapshot(self):
        if not self.available:
            return None
        paths, n_paths, modes, n_modes = self._query(QDC_ALL_PATHS)
        paths_copy = (DISPLAYCONFIG_PATH_INFO * n_paths)()
        modes_copy = (DISPLAYCONFIG_MODE_INFO * n_modes)()
        memmove(paths_copy, paths, sizeof(DISPLAYCONFIG_PATH_INFO) * n_paths)
        memmove(modes_copy, modes, sizeof(DISPLAYCONFIG_MODE_INFO) * n_modes)
        return (paths_copy, n_paths, modes_copy, n_modes)

    def restore(self, snap):
        if not self.available or snap is None:
            return False
        paths, n_paths, modes, n_modes = snap
        flags = SDC_APPLY | SDC_USE_SUPPLIED_DISPLAY_CONFIG | SDC_ALLOW_CHANGES
        return _user32.SetDisplayConfig(n_paths, paths, n_modes, modes, flags) == ERROR_SUCCESS

    def apply_states(self, desired):
        """desired: {key -> bool}. Chaves ausentes ficam como estão."""
        if not self.available:
            return False, "Disponível apenas no Windows"
        if desired and not any(desired.values()):
            return False, "Não é possível desligar todos os monitores"

        paths, n_paths, modes, n_modes = self._query(QDC_ALL_PATHS)

        active_targets = set()
        for i in range(n_paths):
            t = paths[i].targetInfo
            key = (t.adapterId.LowPart, t.adapterId.HighPart, t.id)
            if paths[i].flags & DISPLAYCONFIG_PATH_ACTIVE:
                active_targets.add(key)

        activated = set()
        for i in range(n_paths):
            p = paths[i]
            t = p.targetInfo
            key = (t.adapterId.LowPart, t.adapterId.HighPart, t.id)
            if key not in desired:
                continue
            if desired[key]:
                if key in active_targets:
                    continue
                if key not in activated:
                    p.flags |= DISPLAYCONFIG_PATH_ACTIVE
                    p.sourceInfo.modeInfoIdx = DISPLAYCONFIG_PATH_MODE_IDX_INVALID
                    p.targetInfo.modeInfoIdx = DISPLAYCONFIG_PATH_MODE_IDX_INVALID
                    activated.add(key)
                else:
                    p.flags &= ~DISPLAYCONFIG_PATH_ACTIVE
            else:
                p.flags &= ~DISPLAYCONFIG_PATH_ACTIVE

        base = SDC_USE_SUPPLIED_DISPLAY_CONFIG | SDC_ALLOW_CHANGES
        err = _user32.SetDisplayConfig(n_paths, paths, n_modes, modes, base | SDC_VALIDATE)
        if err != ERROR_SUCCESS:
            return False, f"Configuração inválida (código {err})"
        err = _user32.SetDisplayConfig(
            n_paths, paths, n_modes, modes, base | SDC_APPLY | SDC_SAVE_TO_DATABASE)
        if err != ERROR_SUCCESS:
            return False, f"Falha ao aplicar (código {err})"
        return True, "OK"

    def extend_all(self):
        if not self.available:
            return False
        return _user32.SetDisplayConfig(0, None, 0, None,
                                        SDC_APPLY | SDC_TOPOLOGY_EXTEND) == ERROR_SUCCESS


DISPLAY_MANAGER = DisplayManager()
DISPLAY_CONTROL_AVAILABLE = DISPLAY_MANAGER.available


# =====================================================================
#  PERSISTÊNCIA DE PERFIS
# =====================================================================
#  Perfil = {"name": str, "active": [nomes de monitores que ficam LIGADOS]}
#  (guardamos por NOME, não pelo id volátil da placa)

def carregar_perfis():
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("profiles", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def salvar_perfis(profiles):
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump({"profiles": profiles}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[PERFIS] Erro ao salvar: {e}")
        return False


# --- conversão do atalho (formato Qt "Ctrl+Alt+G" -> formato pynput) ---

_NOMES_ESPECIAIS = {
    "escape": "<esc>", "esc": "<esc>", "space": "<space>", "tab": "<tab>",
    "return": "<enter>", "enter": "<enter>", "backspace": "<backspace>",
    "delete": "<delete>", "del": "<delete>", "insert": "<insert>",
    "home": "<home>", "end": "<end>", "pgup": "<page_up>", "pgdown": "<page_down>",
    "up": "<up>", "down": "<down>", "left": "<left>", "right": "<right>",
}


def qkeyseq_to_pynput(seq_str):
    """'Ctrl+Alt+G' -> '<ctrl>+<alt>+g' (formato do pynput GlobalHotKeys)."""
    if not seq_str:
        return None
    seq_str = seq_str.split(",")[0].strip()  # só o primeiro combo
    out = []
    for part in seq_str.split("+"):
        p = part.strip()
        low = p.lower()
        if low in ("ctrl", "control"):
            out.append("<ctrl>")
        elif low == "alt":
            out.append("<alt>")
        elif low == "shift":
            out.append("<shift>")
        elif low in ("meta", "cmd", "win", "super"):
            out.append("<cmd>")
        elif len(p) == 1:
            out.append(low)
        elif low.startswith("f") and low[1:].isdigit():
            out.append(f"<{low}>")
        elif low in _NOMES_ESPECIAIS:
            out.append(_NOMES_ESPECIAIS[low])
        else:
            out.append(low)
    return "+".join(out) if out else None


class HotkeyManager:
    """Registra atalhos globais (funcionam com o app em segundo plano)."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger   # callable(nome_do_perfil)
        self.listener = None

    def rebuild(self):
        self.stop()
        mapping = {}
        for p in carregar_perfis():
            hk = p.get("hotkey")
            if hk:
                mapping[hk] = (lambda nome=p["name"]: self.on_trigger(nome))
        if not mapping:
            return
        try:
            self.listener = keyboard.GlobalHotKeys(mapping)
            self.listener.start()
            print(f"[HOTKEY] {len(mapping)} atalho(s) registrado(s).")
        except Exception as e:
            print(f"[HOTKEY] Erro ao registrar atalhos: {e}")

    def stop(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None


# =====================================================================
#  CONTROLE DE JANELAS
# =====================================================================

class WindowController:
    BLACKLIST = [
        "program manager", "windows input experience", "experiência de entrada",
    ]

    @staticmethod
    def get_monitors_info():
        if not WINDOW_CONTROL_AVAILABLE:
            return []
        return list(get_monitors())

    @staticmethod
    def get_active_windows(max_items=8):
        if not WINDOW_CONTROL_AVAILABLE:
            return []
        windows = []
        for win in gw.getAllWindows():
            if not (win.title and win.title.strip() and win.visible):
                continue
            tl = win.title.lower()
            if any(tl == b or tl.startswith(b) for b in WindowController.BLACKLIST):
                continue
            windows.append({"title": win.title, "window": win})
        return windows[:max_items]

    @staticmethod
    def move_to_monitor(window, monitor_index):
        if not WINDOW_CONTROL_AVAILABLE:
            return False
        try:
            monitors = get_monitors()
            if monitor_index >= len(monitors):
                print(f"[ERRO] Monitor {monitor_index + 1} não encontrado")
                return False
            monitor = monitors[monitor_index]
            print(f"[MOVER] '{window.title}' -> Monitor {monitor_index + 1}")

            if window.isMinimized:
                window.restore(); time.sleep(0.15)
            was_max = window.isMaximized
            if was_max:
                window.restore(); time.sleep(0.15)
            try:
                window.activate(); time.sleep(0.1)
            except Exception:
                pass

            tx = monitor.x + (monitor.width - window.width) // 2
            ty = monitor.y + (monitor.height - window.height) // 2
            window.moveTo(tx, ty); time.sleep(0.1)

            if was_max:
                window.maximize(); time.sleep(0.1)

            try:
                hwnd = window._hWnd
                ctypes.windll.user32.SetWindowPos(hwnd, 0, tx, ty, 0, 0, 0x0040 | 0x0001 | 0x0004)
                time.sleep(0.05)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception as e:
                print(f"[MOVER] Win32 ignorado: {e}")
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao mover janela: {e}")
            return False


# =====================================================================
#  DIÁLOGO DE SEGURANÇA (auto-reverter)
# =====================================================================

class ConfirmRevertDialog(QWidget):
    def __init__(self, dm, snapshot, segundos=12):
        super().__init__()
        self.dm = dm
        self.snapshot = snapshot
        self.restante = segundos

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(360, 150)

        root = QVBoxLayout(self)
        glass = QFrame()
        glass.setStyleSheet("""
            QFrame { background: rgba(20,20,20,235);
                     border: 1px solid rgba(0,255,255,90); border-radius: 16px; }
        """)
        root.addWidget(glass)
        v = QVBoxLayout(glass)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        self.lbl = QLabel()
        self.lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 600;")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)

        row = QHBoxLayout()
        btn_keep = QPushButton("Manter")
        btn_revert = QPushButton("Reverter")
        for b in (btn_keep, btn_revert):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { background: rgba(255,255,255,22);
                    border: 1px solid rgba(255,255,255,40); border-radius: 10px;
                    padding: 8px 16px; color: white; font-weight: 700; }
                QPushButton:hover { background: rgba(0,255,255,60); }
            """)
        btn_keep.clicked.connect(self._keep)
        btn_revert.clicked.connect(self._revert)
        row.addWidget(btn_keep)
        row.addWidget(btn_revert)
        v.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def start(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2,
                  screen.center().y() - self.height() // 2)
        self._atualizar_texto()
        self.show()
        self.raise_()
        self.activateWindow()
        self.timer.start(1000)

    def _atualizar_texto(self):
        self.lbl.setText(
            f"Manter esta configuração de telas?\n"
            f"Revertendo automaticamente em {self.restante}s..."
        )

    def _tick(self):
        self.restante -= 1
        if self.restante <= 0:
            self._revert()
        else:
            self._atualizar_texto()

    def _keep(self):
        self.timer.stop()
        print("[PERFIS] Configuração mantida.")
        self.close()

    def _revert(self):
        self.timer.stop()
        print("[PERFIS] Revertendo para a configuração anterior...")
        self.dm.restore(self.snapshot)
        self.close()


# =====================================================================
#  JANELA DE CONFIGURAÇÃO DE PERFIS
# =====================================================================

class ConfigWindow(QWidget):
    """App simples para criar/editar/excluir perfis de monitor."""

    def __init__(self, on_change=None):
        super().__init__()
        self.on_change = on_change   # chamado quando perfis mudam (re-registrar atalhos)
        self.setWindowTitle("Excalibur — Configuração de Perfis")
        self.setMinimumSize(420, 560)
        self.setStyleSheet("""
            QWidget { background: #141414; color: #eaeaea; font-size: 13px; }
            QLineEdit { background: #1f1f1f; border: 1px solid #333;
                        border-radius: 8px; padding: 8px; color: white; }
            QCheckBox { padding: 4px; }
            QPushButton { background: #2a2a2a; border: 1px solid #3a3a3a;
                          border-radius: 8px; padding: 8px 14px; font-weight: 600; }
            QPushButton:hover { background: #00b3b3; color: black; }
            QLabel#titulo { font-size: 16px; font-weight: 800; }
            QLabel#sub { color: #9a9a9a; font-size: 12px; }
            QKeySequenceEdit QLineEdit { background: #1f1f1f; border: 1px solid #333;
                        border-radius: 8px; padding: 8px; color: white; }
        """)

        self.checkboxes = []  # (checkbox, monitor_name)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._label("Configuração de Perfis", "titulo"))

        # --- perfis existentes ---
        root.addWidget(self._label("Perfis salvos", "sub"))
        self.lista_perfis = QVBoxLayout()
        self.lista_perfis.setSpacing(6)
        cont_perfis = QFrame()
        cont_perfis.setLayout(self.lista_perfis)
        root.addWidget(cont_perfis)

        # --- novo perfil ---
        root.addWidget(self._divisor())
        root.addWidget(self._label("Novo perfil (ou sobrescrever pelo nome)", "sub"))

        self.nome_edit = QLineEdit()
        self.nome_edit.setPlaceholderText("Nome do perfil (ex: Gaming, Trabalho, Filmes)")
        root.addWidget(self.nome_edit)

        # atalho global
        root.addWidget(self._label("Atalho global (opcional — clique e tecle a combinação):", "sub"))
        row_atalho = QHBoxLayout()
        self.atalho_edit = QKeySequenceEdit()
        b_limpar = QPushButton("Limpar")
        b_limpar.clicked.connect(self.atalho_edit.clear)
        row_atalho.addWidget(self.atalho_edit, 1)
        row_atalho.addWidget(b_limpar)
        root.addLayout(row_atalho)

        root.addWidget(self._label("Monitores LIGADOS neste perfil:", "sub"))

        self.area_monitores = QVBoxLayout()
        self.area_monitores.setSpacing(4)
        box = QFrame()
        box.setLayout(self.area_monitores)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(box)
        root.addWidget(scroll, 1)

        btns = QHBoxLayout()
        b_salvar = QPushButton("Salvar perfil")
        b_salvar.clicked.connect(self._salvar_perfil)
        b_atualizar = QPushButton("Recarregar monitores")
        b_atualizar.clicked.connect(self.refresh)
        btns.addWidget(b_salvar)
        btns.addWidget(b_atualizar)
        root.addLayout(btns)

    def _label(self, txt, obj=None):
        lbl = QLabel(txt)
        if obj:
            lbl.setObjectName(obj)
        return lbl

    def _divisor(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #333;")
        return line

    def abrir(self):
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self):
        # monitores detectados -> checkboxes
        while self.area_monitores.count():
            item = self.area_monitores.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checkboxes = []

        monitores = DISPLAY_MANAGER.list_monitors() if DISPLAY_CONTROL_AVAILABLE else []
        if not monitores:
            self.area_monitores.addWidget(self._label("Nenhum monitor detectado.", "sub"))
        for m in monitores:
            cb = QCheckBox(f"{m['name']}  {'(ativo agora)' if m['active'] else ''}")
            cb.setChecked(m["active"])
            self.area_monitores.addWidget(cb)
            self.checkboxes.append((cb, m["name"]))

        # perfis existentes -> lista com excluir
        while self.lista_perfis.count():
            item = self.lista_perfis.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        perfis = carregar_perfis()
        if not perfis:
            self.lista_perfis.addWidget(self._label("Nenhum perfil ainda.", "sub"))
        for p in perfis:
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            ativos = ", ".join(p.get("active", [])) or "nenhum"
            atalho = p.get("hotkey_label")
            extra = f"  [{atalho}]" if atalho else ""
            lbl = QLabel(f"● {p['name']}{extra}  —  {ativos}")
            lbl.setStyleSheet("color: #d6d6d6;")
            h.addWidget(lbl, 1)
            b_edit = QPushButton("Editar")
            b_edit.clicked.connect(lambda _, prof=p: self._carregar_no_form(prof))
            b_del = QPushButton("Excluir")
            b_del.clicked.connect(lambda _, nome=p["name"]: self._excluir_perfil(nome))
            h.addWidget(b_edit)
            h.addWidget(b_del)
            self.lista_perfis.addWidget(row)

    def _carregar_no_form(self, perfil):
        self.nome_edit.setText(perfil["name"])
        self.atalho_edit.setKeySequence(QKeySequence(perfil.get("hotkey_label", "")))
        ativos = set(perfil.get("active", []))
        for cb, nome in self.checkboxes:
            cb.setChecked(nome in ativos)

    def _salvar_perfil(self):
        nome = self.nome_edit.text().strip()
        if not nome:
            print("[PERFIS] Dê um nome ao perfil.")
            return
        ativos = [n for cb, n in self.checkboxes if cb.isChecked()]
        if not ativos:
            print("[PERFIS] Selecione pelo menos 1 monitor ligado.")
            return

        label = self.atalho_edit.keySequence().toString()
        if "," in label:
            label = label.split(",")[0].strip()
        hotkey = qkeyseq_to_pynput(label)

        perfil = {"name": nome, "active": ativos}
        if hotkey:
            perfil["hotkey"] = hotkey
            perfil["hotkey_label"] = label

        perfis = carregar_perfis()
        perfis = [p for p in perfis if p["name"].lower() != nome.lower()]  # sobrescreve
        perfis.append(perfil)
        salvar_perfis(perfis)

        self.nome_edit.clear()
        self.atalho_edit.clear()
        self.refresh()
        if callable(self.on_change):
            self.on_change()
        print(f"[PERFIS] Perfil '{nome}' salvo." + (f" Atalho: {label}" if hotkey else ""))

    def _excluir_perfil(self, nome):
        perfis = [p for p in carregar_perfis() if p["name"] != nome]
        salvar_perfis(perfis)
        self.refresh()
        if callable(self.on_change):
            self.on_change()
        print(f"[PERFIS] Perfil '{nome}' excluído.")


# =====================================================================
#  MENU RADIAL
# =====================================================================

MODO_PRINCIPAL = "principal"
MODO_JANELAS = "janelas"
MODO_MONITOR = "monitor"
MODO_PERFIS = "perfis"

OPCOES_PRINCIPAL = ["Mover Janela", "Perfis de Monitor", "Configuração"]


class ExcaliburMenu(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(600, 600)
        self.setMouseTracking(True)

        self.centro = QPoint(300, 300)
        self.raio_externo = 180
        self.raio_interno = 75
        self.raio_central_tri = 44   # zona central (cancelar) do menu triangular

        self.modo = MODO_PRINCIPAL
        self.opcao_focada = -1
        self.foco_central = False

        self.janelas_ativas = []
        self.janela_selecionada = None
        self.monitores = []

        self.perfis = []
        self._revert_dialog = None
        self.config_window = None
        self.on_perfis_changed = None   # setado no main (re-registra atalhos)

        self.hide()

    def _itens_atuais(self):
        if self.modo == MODO_JANELAS:
            itens = [w["title"] for w in self.janelas_ativas]
            return itens if itens else ["Nenhuma janela"]
        if self.modo == MODO_MONITOR:
            return [f"Monitor {i + 1}" for i in range(len(self.monitores))] + ["Voltar"]
        if self.modo == MODO_PERFIS:
            if not DISPLAY_CONTROL_AVAILABLE:
                return ["(indisponível)", "Voltar"]
            if not self.perfis:
                return ["(sem perfis)", "Todos", "Voltar"]
            return [p["name"] for p in self.perfis] + ["Todos", "Voltar"]
        return list(OPCOES_PRINCIPAL)

    def _texto_central(self):
        return {
            MODO_JANELAS: "JANELAS",
            MODO_MONITOR: "MONITOR",
            MODO_PERFIS: "PERFIS",
        }.get(self.modo, "EXCALIBUR")

    # ----- geometria do triângulo (menu principal) -----

    def _tri_vertices(self):
        """Triângulo equilátero invertido (ponta pra baixo)."""
        cx, cy = self.centro.x(), self.centro.y()
        R = self.raio_externo
        vtl = (cx - 0.8660 * R, cy - 0.5 * R)   # topo-esquerda (150°)
        vtr = (cx + 0.8660 * R, cy - 0.5 * R)   # topo-direita  (30°)
        vb = (cx, cy + R)                       # base          (270°)
        return vtl, vtr, vb

    def _escala_tri(self, s):
        cx, cy = self.centro.x(), self.centro.y()
        return [(cx + s * (x - cx), cy + s * (y - cy)) for (x, y) in self._tri_vertices()]

    @staticmethod
    def _sinal(p, a, b):
        return (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])

    def _ponto_no_triangulo(self, p, a, b, c):
        d1 = self._sinal(p, a, b)
        d2 = self._sinal(p, b, c)
        d3 = self._sinal(p, c, a)
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (neg and pos)

    def _regioes_principal(self):
        """3 sub-triângulos (centro + aresta): idx 0=topo, 1=direita, 2=esquerda."""
        vtl, vtr, vb = self._tri_vertices()
        return [(vtr, vtl), (vb, vtr), (vtl, vb)]

    # ----- desenho -----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.modo == MODO_PRINCIPAL:
            self._paint_principal(painter)
        else:
            self._paint_circular(painter)

    def _paint_principal(self, painter):
        centro = (self.centro.x(), self.centro.y())
        regioes = self._regioes_principal()

        # preenche cada região (destaca a focada) — sem borda, pra não desenhar
        # as divisórias que cortavam os ícones
        painter.setPen(Qt.NoPen)
        for i, (a, b) in enumerate(regioes):
            poly = QPolygonF([QPointF(*centro), QPointF(*a), QPointF(*b)])
            if i == self.opcao_focada and not self.foco_central:
                painter.setBrush(QColor(0, 255, 255, 75))
            else:
                painter.setBrush(QColor(16, 16, 20, 235))
            painter.drawPolygon(poly)

        # contorno externo (fino e suave, violeta acinzentado)
        vtl, vtr, vb = self._tri_vertices()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(120, 100, 170, 170), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([QPointF(*vtl), QPointF(*vtr), QPointF(*vb)]))

        # triângulo interno (charme: linha dupla, roxo accent)
        inner = self._escala_tri(0.60)
        painter.setPen(QPen(QColor(138, 43, 226), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([QPointF(*p) for p in inner]))

        # zona central (cancelar)
        cor = QColor(255, 0, 100) if self.foco_central else QColor(138, 43, 226)
        painter.setBrush(QColor(10, 10, 12))
        painter.setPen(QPen(cor, 2.5))
        painter.drawEllipse(self.centro, self.raio_central_tri, self.raio_central_tri)

        # ícones das 3 opções (idx0 topo, idx1 direita, idx2 esquerda)
        tipos = ["mover", "monitor", "config"]
        for i, (a, b) in enumerate(regioes):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ix = 0.24 * centro[0] + 0.76 * mx
            iy = 0.24 * centro[1] + 0.76 * my
            focado = (i == self.opcao_focada and not self.foco_central)
            self._icone(painter, ix, iy, tipos[i], focado)

        painter.setPen(QColor(225, 220, 245))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, "EXCALIBUR")

    def _icone(self, painter, cx, cy, tipo, focado):
        cor = QColor(0, 255, 255) if focado else QColor(210, 204, 232)
        painter.setPen(QPen(cor, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)

        if tipo == "mover":
            # janela + seta (mover janela para outro monitor)
            painter.drawRoundedRect(QRectF(cx - 13, cy - 8, 12, 16), 2, 2)
            painter.drawLine(QPointF(cx - 13, cy - 3), QPointF(cx - 1, cy - 3))
            painter.drawLine(QPointF(cx + 2, cy), QPointF(cx + 13, cy))
            painter.drawLine(QPointF(cx + 8, cy - 4), QPointF(cx + 13, cy))
            painter.drawLine(QPointF(cx + 8, cy + 4), QPointF(cx + 13, cy))

        elif tipo == "monitor":
            # monitor com base (perfis de monitor)
            painter.drawRoundedRect(QRectF(cx - 12, cy - 10, 24, 15), 2, 2)
            painter.drawLine(QPointF(cx, cy + 5), QPointF(cx, cy + 9))
            painter.drawLine(QPointF(cx - 6, cy + 9), QPointF(cx + 6, cy + 9))

        elif tipo == "config":
            # engrenagem (configuração)
            painter.save()
            painter.translate(cx, cy)
            r = 6.5
            for k in range(8):
                painter.save()
                painter.rotate(k * 45)
                painter.drawLine(QPointF(0, -r - 4), QPointF(0, -r - 1))
                painter.restore()
            painter.drawEllipse(QPointF(0, 0), r, r)
            painter.drawEllipse(QPointF(0, 0), 2.2, 2.2)
            painter.restore()

    def _paint_circular(self, painter):
        itens = self._itens_atuais() or ["Vazio"]
        angulo_fatia = 360 / len(itens)
        rect = QRectF(
            self.centro.x() - self.raio_externo,
            self.centro.y() - self.raio_externo,
            self.raio_externo * 2, self.raio_externo * 2,
        )

        for i, nome in enumerate(itens):
            start_angle = int(i * angulo_fatia * 16)
            span_angle = int(angulo_fatia * 16)
            if i == self.opcao_focada and not self.foco_central:
                painter.setBrush(QColor(0, 255, 255, 120))
                painter.setPen(QPen(QColor(0, 255, 255), 2))
            else:
                painter.setBrush(QColor(15, 15, 15, 230))
                painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawPie(rect, start_angle, span_angle)

            rad = math.radians(i * angulo_fatia + angulo_fatia / 2)
            tx = self.centro.x() + (self.raio_externo * 0.75) * math.cos(rad)
            ty = self.centro.y() - (self.raio_externo * 0.75) * math.sin(rad)
            painter.setPen(Qt.white)
            texto = nome if len(nome) <= 20 else nome[:17] + "..."
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(int(tx - 70), int(ty - 15), 140, 30, Qt.AlignCenter, texto)

        cor = QColor(255, 0, 100) if self.foco_central else QColor(138, 43, 226)
        painter.setBrush(QColor(10, 10, 10))
        painter.setPen(QPen(cor, 3))
        painter.drawEllipse(self.centro, self.raio_interno, self.raio_interno)

        painter.setPen(Qt.white)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, self._texto_central())

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self.modo == MODO_PRINCIPAL:
            self._move_principal(pos)
        else:
            self._move_circular(pos)
        self.update()

    def _move_principal(self, pos):
        cx, cy = self.centro.x(), self.centro.y()
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.hypot(dx, dy)

        if dist <= self.raio_central_tri:
            self.foco_central = True
            self.opcao_focada = -1
            return

        vtl, vtr, vb = self._tri_vertices()
        if not self._ponto_no_triangulo((pos.x(), pos.y()), vtl, vtr, vb):
            self.foco_central = False
            self.opcao_focada = -1
            return

        self.foco_central = False
        ang = math.degrees(math.atan2(-dy, dx))
        if ang < 0:
            ang += 360
        if 30 <= ang < 150:
            self.opcao_focada = 0   # topo -> Mover Janela
        elif 150 <= ang < 270:
            self.opcao_focada = 2   # esquerda -> Configuração
        else:
            self.opcao_focada = 1   # direita -> Perfis de Monitor

    def _move_circular(self, pos):
        diff = pos - self.centro
        dist = math.hypot(diff.x(), diff.y())
        if dist <= self.raio_interno:
            self.foco_central = True
            self.opcao_focada = -1
        elif self.raio_interno < dist < self.raio_externo:
            self.foco_central = False
            ang = math.degrees(math.atan2(-diff.y(), diff.x()))
            if ang < 0:
                ang += 360
            n = len(self._itens_atuais()) or 1
            self.opcao_focada = int(ang // (360 / n))
        else:
            self.foco_central = False
            self.opcao_focada = -1

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.foco_central:
            self.desaparecer()
            return
        if self.opcao_focada == -1:
            return
        if self.modo == MODO_PRINCIPAL:
            self._selecionar_principal(self.opcao_focada)
        elif self.modo == MODO_JANELAS:
            self._selecionar_janela(self.opcao_focada)
        elif self.modo == MODO_MONITOR:
            self._selecionar_monitor(self.opcao_focada)
        elif self.modo == MODO_PERFIS:
            self._selecionar_perfil(self.opcao_focada)

    def _selecionar_principal(self, idx):
        if idx == 0:
            self.iniciar_mover_janela()
        elif idx == 1:
            self.iniciar_perfis()
        elif idx == 2:
            self.abrir_config()

    # ---- mover janela ----
    def iniciar_mover_janela(self):
        if not WINDOW_CONTROL_AVAILABLE:
            print("Controle de janela indisponível (pip install pygetwindow screeninfo)")
            self.desaparecer()
            return
        self.modo = MODO_JANELAS
        self.janelas_ativas = WindowController.get_active_windows()
        self.janela_selecionada = None
        self.opcao_focada = -1
        self.update()

    def _selecionar_janela(self, idx):
        if not self.janelas_ativas or idx >= len(self.janelas_ativas):
            return
        self.janela_selecionada = self.janelas_ativas[idx]
        self.monitores = WindowController.get_monitors_info()
        self.modo = MODO_MONITOR
        self.opcao_focada = -1
        self.update()

    def _selecionar_monitor(self, idx):
        opcoes = self._itens_atuais()
        if idx >= len(opcoes):
            return
        if opcoes[idx] == "Voltar":
            self.modo = MODO_JANELAS
            self.janela_selecionada = None
            self.opcao_focada = -1
            self.update()
            return
        WindowController.move_to_monitor(self.janela_selecionada["window"], idx)
        self.desaparecer()

    # ---- perfis ----
    def iniciar_perfis(self):
        self.modo = MODO_PERFIS
        self.perfis = carregar_perfis() if DISPLAY_CONTROL_AVAILABLE else []
        self.opcao_focada = -1
        self.update()

    def _selecionar_perfil(self, idx):
        opcoes = self._itens_atuais()
        if idx >= len(opcoes):
            return
        escolha = opcoes[idx]

        if escolha == "Voltar":
            self.modo = MODO_PRINCIPAL
            self.opcao_focada = -1
            self.update()
            return
        if not DISPLAY_CONTROL_AVAILABLE or escolha == "(sem perfis)":
            return

        if escolha == "Todos":
            self.desaparecer()
            snap = DISPLAY_MANAGER.snapshot()
            if DISPLAY_MANAGER.extend_all():
                self._mostrar_confirmacao(snap)
            return

        # aplicar perfil nomeado
        perfil = next((p for p in self.perfis if p["name"] == escolha), None)
        if perfil is None:
            return
        self.desaparecer()
        self._aplicar_perfil(perfil)

    def _aplicar_perfil(self, perfil):
        monitores = DISPLAY_MANAGER.list_monitors()
        ativos = set(perfil.get("active", []))
        desired = {}
        algum = False
        for m in monitores:
            on = m["name"] in ativos
            desired[m["key"]] = on
            algum = algum or on
        if not algum:
            print(f"[PERFIS] Perfil '{perfil['name']}' não tem monitor válido conectado.")
            return
        snap = DISPLAY_MANAGER.snapshot()
        ok, msg = DISPLAY_MANAGER.apply_states(desired)
        if ok:
            print(f"[PERFIS] Perfil '{perfil['name']}' aplicado.")
            self._mostrar_confirmacao(snap)
        else:
            print(f"[PERFIS] {msg}")

    def _mostrar_confirmacao(self, snap):
        self._revert_dialog = ConfirmRevertDialog(DISPLAY_MANAGER, snap)
        self._revert_dialog.start()

    # ---- configuração ----
    def abrir_config(self):
        self.desaparecer()
        if self.config_window is None:
            self.config_window = ConfigWindow(on_change=self.on_perfis_changed)
        self.config_window.abrir()

    @Slot(str)
    def aplicar_perfil_por_nome(self, nome):
        """Chamado por atalho global (via QMetaObject, na thread da GUI)."""
        perfil = next((p for p in carregar_perfis() if p["name"] == nome), None)
        if perfil is None:
            return
        self.desaparecer()
        self._aplicar_perfil(perfil)

    # ---- janela ----
    @Slot(int, int)
    def aparecer(self, x, y):
        self.move(x - self.width() // 2, y - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def desaparecer(self):
        self.hide()
        self.modo = MODO_PRINCIPAL
        self.opcao_focada = -1
        self.foco_central = False
        self.janelas_ativas = []
        self.janela_selecionada = None
        self.monitores = []


# =====================================================================
#  TRIGGER (X2) + MAIN
# =====================================================================

def ao_clicar(x, y, button, pressed):
    if button == mouse.Button.x2 and pressed:
        QMetaObject.invokeMethod(
            window, "aparecer", Qt.QueuedConnection, Q_ARG(int, x), Q_ARG(int, y))


def disparar_perfil(nome):
    """Callback dos atalhos globais -> marshalla para a thread da GUI."""
    QMetaObject.invokeMethod(
        window, "aplicar_perfil_por_nome", Qt.QueuedConnection, Q_ARG(str, nome))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # roda em segundo plano; fechar janela não encerra
    window = ExcaliburMenu()

    listener = mouse.Listener(on_click=ao_clicar)
    listener.start()

    hotkeys = HotkeyManager(disparar_perfil)
    window.on_perfis_changed = hotkeys.rebuild
    hotkeys.rebuild()

    print("EXCALIBUR (Monitor) iniciado!")
    print("  X2 (botão lateral do mouse) => abre o menu radial")
    print("  Mover Janela      :", "ATIVO" if WINDOW_CONTROL_AVAILABLE else "INATIVO")
    print("  Perfis de Monitor :", "ATIVO" if DISPLAY_CONTROL_AVAILABLE else "INATIVO")
    print("  Configuração      : crie perfis e atalhos pela 3ª opção do menu")

    sys.exit(app.exec())