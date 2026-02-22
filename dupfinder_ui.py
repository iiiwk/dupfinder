import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import re
import threading
from pathlib import Path
from dataclasses import dataclass, field

import sys
import os
import ctypes
import json
import sv_ttk
from send2trash import send2trash
from ttkthemes import ThemedStyle

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    BUNDLE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
    if IS_MAC:
        USER_DIR = Path(sys.executable).resolve().parents[3]
    else:
        USER_DIR = APP_DIR
else:
    BUNDLE_DIR = Path(__file__).parent.resolve()
    APP_DIR = BUNDLE_DIR
    USER_DIR = APP_DIR

if IS_WIN:
    DUPFINDER_EXE = APP_DIR / "dupfinder_engine.exe"
    if not FROZEN and not DUPFINDER_EXE.exists():
        DUPFINDER_EXE = APP_DIR / "build" / "Release" / "dupfinder_engine.exe"
else:
    DUPFINDER_EXE = APP_DIR / "dupfinder_engine"
    if not FROZEN and not DUPFINDER_EXE.exists():
        DUPFINDER_EXE = APP_DIR / "build" / "dupfinder_engine"

FONT_FILE = BUNDLE_DIR / "font" / "HarmonyOS_SansSC_Regular.ttf"
FONT_FAMILY = "HarmonyOS Sans SC"
CONFIG_FILE = APP_DIR / "dupfinder_config.json"
DEFAULT_THEME = "aquativo" if IS_MAC else "xpnative"
DEFAULT_LANG = "zh"

# ============================================================
# i18n -- loaded from external JSON
# ============================================================

STRINGS_FILE = BUNDLE_DIR / "dupfinder_strings.json"

def _load_strings() -> dict:
    raw = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))
    return raw

_I18N = _load_strings()

STRINGS            = _I18N["strings"]
LANG_DISPLAY       = _I18N["lang_display"]
SORT_KEY_DISPLAY   = _I18N["sort_key_display"]
SORT_MODE_TRANSLATE = _I18N["sort_mode_translate"]

LANG_FROM_DISPLAY = {v: k for k, v in LANG_DISPLAY.items()}

SORT_FROM_DISPLAY = {}
for _lang, _m in SORT_KEY_DISPLAY.items():
    for _key, _disp in _m.items():
        SORT_FROM_DISPLAY[_disp] = _key

# ============================================================
# Config & utilities
# ============================================================

def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def _load_custom_font():
    if not FONT_FILE.exists():
        return False
    if IS_WIN:
        FR_PRIVATE = 0x10
        added = ctypes.windll.gdi32.AddFontResourceExW(str(FONT_FILE), FR_PRIVATE, 0)
        return added > 0
    if IS_MAC:
        try:
            from ctypes import c_void_p, c_int32, c_uint32, c_bool, c_char_p
            ct = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreText.framework/CoreText")
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

            cf.CFStringCreateWithCString.restype = c_void_p
            cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
            cf.CFURLCreateWithFileSystemPath.restype = c_void_p
            cf.CFURLCreateWithFileSystemPath.argtypes = [c_void_p, c_void_p, c_int32, c_bool]
            cf.CFRelease.argtypes = [c_void_p]
            ct.CTFontManagerRegisterFontsForURL.restype = c_bool
            ct.CTFontManagerRegisterFontsForURL.argtypes = [c_void_p, c_uint32, c_void_p]

            kCFStringEncodingUTF8 = 0x08000100
            kCTFontManagerScopeProcess = 1

            cf_str = cf.CFStringCreateWithCString(
                None, str(FONT_FILE).encode("utf-8"), kCFStringEncodingUTF8)
            if not cf_str:
                return False
            cf_url = cf.CFURLCreateWithFileSystemPath(None, cf_str, 0, False)
            cf.CFRelease(cf_str)
            if not cf_url:
                return False
            ok = ct.CTFontManagerRegisterFontsForURL(
                cf_url, kCTFontManagerScopeProcess, None)
            cf.CFRelease(cf_url)
            return bool(ok)
        except Exception:
            return False
    return False


# ============================================================
# Data structures & parsing
# ============================================================

@dataclass
class DupGroup:
    index: int
    size_text: str
    count: int
    hash_hex: str
    sampled: bool
    rel_paths: list = field(default_factory=list)


@dataclass
class ScanSummary:
    total_files: str = ""
    candidates: str = ""
    quick_hash: str = ""
    full_hash: str = ""
    sort_mode: str = ""
    elapsed: str = ""
    dup_groups: str = ""
    reclaimable: str = ""
    threads: str = ""


SUMMARY_KEYS = {
    "Total Files":  "total_files",
    "Candidates":   "candidates",
    "Quick Hash":   "quick_hash",
    "Full Hash":    "full_hash",
    "Sort":         "sort_mode",
    "Elapsed":      "elapsed",
    "Dup Groups":   "dup_groups",
    "Reclaimable":  "reclaimable",
    "Threads":      "threads",
}


def parse_output(text: str) -> tuple:
    lines = text.splitlines()
    scan_root = ""
    groups: list[DupGroup] = []
    current: DupGroup | None = None
    summary = ScanSummary()

    for line in lines:
        if line.startswith("Scan Directory:"):
            scan_root = line.split(":", 1)[1].strip()
            continue

        matched_key = False
        for prefix, attr in SUMMARY_KEYS.items():
            if line.startswith(prefix + ":"):
                setattr(summary, attr, line.split(":", 1)[1].strip())
                matched_key = True
                break
        if matched_key:
            continue

        if m := re.match(r'^\[(\d+)\]\s+(.+?)\s+x(\d+)\s+copies(.*)$', line):
            if current:
                groups.append(current)
            current = DupGroup(
                index=int(m.group(1)),
                size_text=m.group(2).strip(),
                count=int(m.group(3)),
                hash_hex="",
                sampled="sampled" in m.group(4),
            )
        elif current and line.strip().startswith("Hash:"):
            current.hash_hex = line.strip().split(":", 1)[1].strip()
        elif current and "→" in line:
            current.rel_paths.append(line.split("→", 1)[1].strip())

    if current:
        groups.append(current)
    return scan_root, groups, summary


# ============================================================
# Group color schemes
# ============================================================

GROUP_SCHEMES = [
    {"bg": "#eff6ff", "fg": "#1d4ed8"},
    {"bg": "#f5f3ff", "fg": "#7c3aed"},
    {"bg": "#ecfdf5", "fg": "#059669"},
    {"bg": "#fffbeb", "fg": "#d97706"},
    {"bg": "#fef2f2", "fg": "#dc2626"},
    {"bg": "#ecfeff", "fg": "#0891b2"},
    {"bg": "#fdf4ff", "fg": "#c026d3"},
    {"bg": "#f0fdf4", "fg": "#16a34a"},
]

C = {
    "surface":      "#ffffff",
    "surface_dim":  "#f8fafc",
    "border":       "#e2e8f0",
    "text":         "#0f172a",
    "text_sec":     "#64748b",
    "accent":       "#3b82f6",
    "accent_hover": "#2563eb",
    "danger":       "#ef4444",
    "danger_hover": "#dc2626",
    "success":      "#10b981",
    "bar_bg":       "#0f172a",
    "bar_fg":       "#e2e8f0",
}


# ============================================================
# Main GUI
# ============================================================

class DupFinderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DupFinder")
        self.root.geometry("1150x750")
        self.root.minsize(850, 520)

        self.has_custom_font = _load_custom_font()
        if self.has_custom_font:
            self.F = FONT_FAMILY
            self.FM = FONT_FAMILY
        elif IS_MAC:
            self.F = "PingFang SC"
            self.FM = "Menlo"
        else:
            self.F = "Segoe UI"
            self.FM = "Consolas"

        self.config = _load_config()
        saved_theme = self.config.get("theme", DEFAULT_THEME)
        self.lang = self.config.get("lang", DEFAULT_LANG)

        sv_ttk.set_theme("light")
        self.themed_style = ThemedStyle(self.root)
        self.all_themes = sorted(self.themed_style.theme_names())

        if saved_theme not in self.all_themes:
            saved_theme = DEFAULT_THEME
        self._apply_theme(saved_theme)
        self.current_theme = tk.StringVar(value=saved_theme)
        self.current_lang = tk.StringVar(value=LANG_DISPLAY.get(self.lang, "中文"))

        self.scan_root = ""
        self.groups: list[DupGroup] = []
        self.item_map: dict[str, tuple[int, str]] = {}
        self.summary = ScanSummary()

        # Widget references for dynamic text updates
        self.w = {}

        self._setup_styles()
        self._build_header()
        self._build_toolbar()
        self._build_treeview()
        self._build_action_bar()
        self._build_status_bar()
        self.status(self.t("status_ready"))

    def t(self, key: str) -> str:
        return STRINGS.get(self.lang, STRINGS["zh"]).get(key, key)

    # -- Styles --

    def _setup_styles(self):
        s = ttk.Style()
        F, FM = self.F, self.FM
        s.configure("Header.TFrame", background=C["accent"])
        s.configure("Header.TLabel", background=C["accent"], foreground="#ffffff",
                     font=(F, 16, "bold"))
        s.configure("Toolbar.TFrame", background=C["surface"])
        s.configure("Toolbar.TLabel", background=C["surface"], font=(F, 10))
        s.configure("Treeview", rowheight=28, font=(FM, 10), borderwidth=0, relief="flat")
        s.configure("Treeview.Heading", font=(F, 10, "bold"), padding=(8, 6))
        s.map("Treeview",
              background=[("selected", "#dbeafe")],
              foreground=[("selected", "#1e40af")])
        s.configure("TButton", font=(F, 10))
        s.configure("TCheckbutton", font=(F, 10))
        s.configure("TLabel", font=(F, 10))
        s.configure("Accent.TButton", font=(F, 10))

    # -- Header banner --

    def _build_header(self):
        header = tk.Frame(self.root, bg=C["accent"], padx=20, pady=12)
        header.pack(fill=tk.X)

        left = tk.Frame(header, bg=C["accent"])
        left.pack(side=tk.LEFT)

        tk.Label(left, text="DupFinder", bg=C["accent"], fg="#ffffff",
                 font=(self.F, 18, "bold")).pack(side=tk.LEFT)
        self.w["subtitle"] = tk.Label(left, text=self.t("app_subtitle"),
                                       bg=C["accent"], fg="#93c5fd",
                                       font=(self.F, 11))
        self.w["subtitle"].pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        right = tk.Frame(header, bg=C["accent"])
        right.pack(side=tk.RIGHT)

        # Language selector (left of theme)
        self.w["lang_label"] = tk.Label(right, text=self.t("lang_label"),
                                         bg=C["accent"], fg="#bfdbfe",
                                         font=(self.F, 10))
        self.w["lang_label"].pack(side=tk.LEFT, padx=(0, 4))
        lang_combo = ttk.Combobox(right, textvariable=self.current_lang,
                                  values=list(LANG_DISPLAY.values()), state="readonly",
                                  width=7, font=(self.F, 9))
        lang_combo.pack(side=tk.LEFT)
        lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        tk.Frame(right, bg="#60a5fa", width=1).pack(side=tk.LEFT, fill=tk.Y,
                                                      padx=10, pady=2)

        self.w["theme_label"] = tk.Label(right, text=self.t("theme_label"),
                                          bg=C["accent"], fg="#bfdbfe",
                                          font=(self.F, 10))
        self.w["theme_label"].pack(side=tk.LEFT, padx=(0, 4))
        combo = ttk.Combobox(right, textvariable=self.current_theme,
                             values=self.all_themes, state="readonly",
                             width=16, font=(self.F, 9))
        combo.pack(side=tk.LEFT)
        combo.bind("<<ComboboxSelected>>", self._on_theme_change)

    # -- Toolbar --

    def _build_toolbar(self):
        outer = tk.Frame(self.root, bg=C["border"])
        outer.pack(fill=tk.X)

        bar = tk.Frame(outer, bg=C["surface"], padx=16, pady=12)
        bar.pack(fill=tk.X)

        self.w["scan_dir"] = tk.Label(bar, text=self.t("scan_dir"),
                                       bg=C["surface"], fg=C["text"],
                                       font=(self.F, 10))
        self.w["scan_dir"].pack(side=tk.LEFT)

        self.dir_var = tk.StringVar(value=str(USER_DIR))
        ttk.Entry(bar, textvariable=self.dir_var, width=55,
                  font=(self.FM, 10)).pack(side=tk.LEFT, padx=(10, 6),
                                           fill=tk.X, expand=True)

        self.w["browse_btn"] = ttk.Button(bar, text=self.t("browse"),
                                           command=self._browse, style="Accent.TButton")
        self.w["browse_btn"].pack(side=tk.LEFT, padx=3)

        self.w["scan_btn"] = ttk.Button(bar, text=self.t("scan"),
                                         command=self._scan_async, style="Accent.TButton")
        self.w["scan_btn"].pack(side=tk.LEFT, padx=3)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        self.w["import_btn"] = ttk.Button(bar, text=self.t("import_file"),
                                           command=self._load_file)
        self.w["import_btn"].pack(side=tk.LEFT, padx=3)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        self.w["sort_label"] = tk.Label(bar, text=self.t("sort_label"),
                                         bg=C["surface"], fg=C["text"],
                                         font=(self.F, 10))
        self.w["sort_label"].pack(side=tk.LEFT)
        sort_display = SORT_KEY_DISPLAY.get(self.lang, SORT_KEY_DISPLAY["zh"])
        self.sort_var = tk.StringVar(value=sort_display["path"])
        self.sort_combo = ttk.Combobox(bar, textvariable=self.sort_var,
                                       values=list(sort_display.values()), state="readonly",
                                       width=6, font=(self.F, 9))
        self.sort_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.sort_combo.bind("<<ComboboxSelected>>", self._on_sort_change)

        tk.Frame(outer, bg=C["border"], height=1).pack(fill=tk.X)

    # -- Treeview --

    def _build_treeview(self):
        cols = ("group", "idx", "size", "path", "hash")
        container = ttk.Frame(self.root, padding=0)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 0))

        self.tree = ttk.Treeview(
            container, columns=cols, show="headings", selectmode="extended")

        self.tree.heading("group", text=self.t("col_group"), anchor="center")
        self.tree.heading("idx",   text=self.t("col_idx"),   anchor="center")
        self.tree.heading("size",  text=self.t("col_size"),  anchor="center")
        self.tree.heading("path",  text=self.t("col_path"),  anchor="w")
        self.tree.heading("hash",  text=self.t("col_hash"),  anchor="w")

        self.tree.column("group", width=55,  minwidth=45, stretch=False, anchor="center")
        self.tree.column("idx",   width=40,  minwidth=30, stretch=False, anchor="center")
        self.tree.column("size",  width=110, minwidth=80, stretch=False, anchor="center")
        self.tree.column("path",  width=650, minwidth=200, stretch=True,  anchor="w")
        self.tree.column("hash",  width=300, minwidth=200, stretch=False, anchor="w")

        for i, scheme in enumerate(GROUP_SCHEMES):
            self.tree.tag_configure(f"g{i}", background=scheme["bg"],
                                    foreground=scheme["fg"], font=(self.FM, 10))
            self.tree.tag_configure(f"f{i}", background=scheme["bg"],
                                    foreground=C["text"], font=(self.FM, 10))
        self.tree.tag_configure("sep", background=C["surface"], font=(self.FM, 2))

        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.ctx_menu = tk.Menu(self.root, tearoff=0, font=(self.F, 10),
                                bg=C["surface"], fg=C["text"],
                                activebackground=C["accent"],
                                activeforeground="#ffffff")
        self.ctx_menu.add_command(label=self.t("ctx_delete"), command=self._delete_selected)
        self.ctx_menu.add_command(label=self.t("ctx_open_folder"), command=self._open_folder)
        if IS_MAC:
            self.tree.bind("<Button-2>", self._show_context_menu)
            self.tree.bind("<Button-3>", self._show_context_menu)
            self.tree.bind("<Control-Button-1>", self._show_context_menu)
        else:
            self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Delete>", lambda e: self._delete_selected())
        if IS_MAC:
            self.tree.bind("<BackSpace>", lambda e: self._delete_selected())

    # -- Action bar --

    def _build_action_bar(self):
        outer = tk.Frame(self.root, bg=C["border"])
        outer.pack(fill=tk.X, padx=12, pady=(6, 0))

        tk.Frame(outer, bg=C["border"], height=1).pack(fill=tk.X)
        bar = tk.Frame(outer, bg=C["surface_dim"], padx=12, pady=8)
        bar.pack(fill=tk.X)

        if IS_MAC:
            del_btn = tk.Label(
                bar, text=self.t("btn_delete"), font=(self.F, 10, "bold"),
                bg=C["danger"], fg="#ffffff",
                padx=16, pady=4, cursor="hand2")
            del_btn.pack(side=tk.LEFT)
            del_btn.bind("<Button-1>", lambda e: self._delete_selected())
            del_btn.bind("<Enter>", lambda e: del_btn.configure(bg=C["danger_hover"]))
            del_btn.bind("<Leave>", lambda e: del_btn.configure(bg=C["danger"]))
        else:
            del_btn = tk.Button(
                bar, text=self.t("btn_delete"), font=(self.F, 10, "bold"),
                bg=C["danger"], fg="#ffffff",
                activebackground=C["danger_hover"], activeforeground="#ffffff",
                relief="flat", padx=16, pady=4, cursor="hand2",
                command=self._delete_selected)
            del_btn.pack(side=tk.LEFT)
        self.w["del_btn"] = del_btn

        self.skip_confirm = tk.BooleanVar(value=False)
        self.w["chk_skip"] = ttk.Checkbutton(bar, text=self.t("skip_confirm"),
                                               variable=self.skip_confirm)
        self.w["chk_skip"].pack(side=tk.LEFT, padx=(16, 0))

        self.perm_delete = tk.BooleanVar(value=False)
        self.w["chk_perm"] = ttk.Checkbutton(bar, text=self.t("perm_delete"),
                                               variable=self.perm_delete)
        self.w["chk_perm"].pack(side=tk.LEFT, padx=(10, 0))

        self.w["hint"] = tk.Label(bar, text=self.t("shortcut_hint"),
                                   bg=C["surface_dim"], fg=C["text_sec"],
                                   font=(self.F, 9))
        self.w["hint"].pack(side=tk.LEFT, padx=12)

        self.sel_label = tk.Label(bar, text="", bg=C["surface_dim"], fg=C["accent"],
                                   font=(self.F, 10, "bold"))
        self.sel_label.pack(side=tk.RIGHT)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        if IS_MAC:
            self.tree.bind("<Command-a>", self._select_all_files)
        else:
            self.tree.bind("<Control-a>", self._select_all_files)

    # -- Status bar --

    def _build_status_bar(self):
        self.status_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.status_var,
                 bg=C["bar_bg"], fg=C["bar_fg"],
                 anchor="w", padx=16, pady=5,
                 font=(self.F, 9)).pack(fill=tk.X, side=tk.BOTTOM)

        self.info_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.info_var,
                 bg="#1e3a5f", fg="#93c5fd",
                 anchor="w", padx=16, pady=4,
                 font=(self.FM, 9)).pack(fill=tk.X, side=tk.BOTTOM)

    def status(self, msg: str):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _update_info_bar(self):
        s = self.summary
        if not s.total_files:
            self.info_var.set("")
            return
        parts = []
        if s.total_files:  parts.append(f"{self.t('info_files')}: {s.total_files}")
        if s.candidates:   parts.append(f"{self.t('info_candidates')}: {s.candidates}")
        if s.quick_hash:   parts.append(f"{self.t('info_quick_hash')}: {s.quick_hash}")
        if s.full_hash:    parts.append(f"{self.t('info_full_hash')}: {s.full_hash}")
        if s.dup_groups:   parts.append(f"{self.t('info_dup_groups')}: {s.dup_groups}")
        if s.reclaimable:  parts.append(f"{self.t('info_reclaimable')}: {s.reclaimable}")
        if s.threads:      parts.append(f"{self.t('info_threads')}: {s.threads}")
        if s.elapsed:      parts.append(f"{self.t('info_elapsed')}: {s.elapsed}")
        if s.sort_mode:
            sm = SORT_MODE_TRANSLATE.get(s.sort_mode, {}).get(self.lang, s.sort_mode)
            parts.append(f"{self.t('info_sort')}: {sm}")
        self.info_var.set("  |  ".join(parts))

    # -- Language switch --

    def _on_lang_change(self, event=None):
        display = self.current_lang.get()
        self.lang = LANG_FROM_DISPLAY.get(display, "zh")
        self.config["lang"] = self.lang
        _save_config(self.config)
        self._refresh_all_text()
        self.status(self.t("status_lang").format(display))

    def _refresh_all_text(self):
        text_map = {
            "subtitle":    "app_subtitle",
            "lang_label":  "lang_label",
            "theme_label": "theme_label",
            "scan_dir":    "scan_dir",
            "sort_label":  "sort_label",
            "hint":        "shortcut_hint",
        }
        for wkey, skey in text_map.items():
            if wkey in self.w:
                self.w[wkey].configure(text=self.t(skey))

        btn_map = {
            "browse_btn": "browse",
            "scan_btn":   "scan",
            "import_btn": "import_file",
            "del_btn":    "btn_delete",
        }
        for wkey, skey in btn_map.items():
            if wkey in self.w:
                self.w[wkey].configure(text=self.t(skey))

        chk_map = {
            "chk_skip": "skip_confirm",
            "chk_perm": "perm_delete",
        }
        for wkey, skey in chk_map.items():
            if wkey in self.w:
                self.w[wkey].configure(text=self.t(skey))

        self.tree.heading("group", text=self.t("col_group"))
        self.tree.heading("idx",   text=self.t("col_idx"))
        self.tree.heading("size",  text=self.t("col_size"))
        self.tree.heading("path",  text=self.t("col_path"))
        self.tree.heading("hash",  text=self.t("col_hash"))

        self.ctx_menu.entryconfigure(0, label=self.t("ctx_delete"))
        self.ctx_menu.entryconfigure(1, label=self.t("ctx_open_folder"))

        old_key = SORT_FROM_DISPLAY.get(self.sort_var.get(), "path")
        new_display = SORT_KEY_DISPLAY.get(self.lang, SORT_KEY_DISPLAY["zh"])
        self.sort_combo.configure(values=list(new_display.values()))
        self.sort_var.set(new_display[old_key])

        self._update_info_bar()

    # -- Theme switch --

    def _apply_theme(self, theme: str):
        try:
            self.themed_style.set_theme(theme)
        except Exception:
            try:
                ttk.Style().theme_use(theme)
            except Exception:
                self.themed_style.set_theme(DEFAULT_THEME)

    def _on_theme_change(self, event=None):
        theme = self.current_theme.get()
        self._apply_theme(theme)
        self._setup_styles()
        self.config["theme"] = theme
        _save_config(self.config)
        self.status(self.t("status_theme").format(theme))

    def _on_sort_change(self, event=None):
        target = self.dir_var.get().strip()
        if target and Path(target).is_dir() and self.groups:
            self._scan_async()

    # -- Events --

    def _on_select(self, event=None):
        sel = [s for s in self.tree.selection() if s in self.item_map]
        self.sel_label.configure(text=self.t("selected_n").format(len(sel)) if sel else "")

    def _select_all_files(self, event=None):
        self.tree.selection_set(list(self.item_map.keys()))
        return "break"

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid in self.item_map:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.ctx_menu.tk_popup(event.x_root, event.y_root)

    def _open_folder(self):
        sel = self.tree.selection()
        for iid in sel[:1]:
            if iid in self.item_map:
                gi, rel = self.item_map[iid]
                folder = (Path(self.scan_root) / rel).parent
                if folder.exists():
                    if IS_MAC:
                        subprocess.run(["open", str(folder)])
                    elif IS_WIN:
                        os.startfile(str(folder))
                    else:
                        subprocess.run(["xdg-open", str(folder)])
                break

    # -- Scan --

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _scan_async(self):
        target = self.dir_var.get().strip()
        if not target or not Path(target).is_dir():
            messagebox.showerror(self.t("err_title"),
                                 self.t("err_dir_missing").format(target))
            return

        exe = DUPFINDER_EXE
        if not exe.exists():
            ftypes = [("Executable", "*.exe")] if IS_WIN else [("All Files", "*")]
            alt = filedialog.askopenfilename(
                title=self.t("err_exe_title"),
                filetypes=ftypes)
            if not alt:
                return
            exe = Path(alt)

        self.status(self.t("status_scanning"))
        self._clear_tree()

        sort_key = SORT_FROM_DISPLAY.get(self.sort_var.get(), "path")
        sort_arg = f"--sort={sort_key}"

        def worker():
            try:
                kwargs = {}
                if IS_WIN:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                result = subprocess.run(
                    [str(exe), target, sort_arg], capture_output=True, timeout=600,
                    **kwargs)
                text = result.stdout.decode("utf-8", errors="replace")
                self.root.after(0, lambda: self._on_scan_done(text, target))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(self.t("err_title"), str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, text: str, target: str):
        if not text.strip():
            messagebox.showinfo(self.t("info_title"), self.t("err_no_output"))
            self.status(self.t("status_ready"))
            return
        self.scan_root, self.groups, self.summary = parse_output(text)
        if Path(target).is_absolute():
            self.scan_root = target
        elif not Path(self.scan_root).is_absolute():
            self.scan_root = str(Path(target).resolve())
        self.dir_var.set(self.scan_root)
        self._populate()

    def _load_file(self):
        f = filedialog.askopenfilename(
            title=self.t("dlg_select_output"),
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not f:
            return
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        self.scan_root, self.groups, self.summary = parse_output(text)
        if not Path(self.scan_root).is_absolute():
            d = filedialog.askdirectory(title=self.t("dlg_select_root"))
            if d:
                self.scan_root = d
        self.dir_var.set(self.scan_root)
        self._populate()

    # -- Render results --

    def _clear_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.item_map.clear()

    def _populate(self):
        self._clear_tree()
        self._update_info_bar()

        if not self.groups:
            self.status(self.t("status_no_dup"))
            return

        total_files = 0
        fid = 0
        sampled = self.t("sampled_tag")

        for gi, group in enumerate(self.groups):
            ci = gi % len(GROUP_SCHEMES)
            gtag = f"g{ci}"
            ftag = f"f{ci}"
            stag = sampled if group.sampled else ""

            for fi, rel_path in enumerate(group.rel_paths):
                iid = f"f_{fid}"
                fid += 1
                total_files += 1

                if fi == 0:
                    tag = gtag
                    vals = (f"[{group.index}]", fi,
                            group.size_text + stag,
                            rel_path, group.hash_hex)
                else:
                    tag = ftag
                    vals = (f"[{group.index}]", fi, "", rel_path, "")

                self.tree.insert("", "end", iid=iid, tags=(tag,), values=vals)
                self.item_map[iid] = (gi, rel_path)

            if gi < len(self.groups) - 1:
                self.tree.insert("", "end", iid=f"sep_{gi}", tags=("sep",),
                                 values=("", "", "", "", ""))

        self.status(self.t("status_done").format(
            len(self.groups), total_files, self.scan_root))
        self.tree.yview_moveto(0)

    # -- Delete files --

    def _delete_selected(self):
        selected = [s for s in self.tree.selection() if s in self.item_map]
        if not selected:
            messagebox.showinfo(self.t("info_title"), self.t("info_select_first"))
            return

        if not self.skip_confirm.get():
            preview_lines = []
            for iid in selected[:8]:
                _, rel = self.item_map[iid]
                preview_lines.append(f"  • {rel}")
            more = self.t("dlg_more_files").format(len(selected)) if len(selected) > 8 else ""
            preview = "\n".join(preview_lines) + more

            perm = self.perm_delete.get()
            action = self.t("action_perm") if perm else self.t("action_recycle")
            warn = self.t("dlg_irreversible") if perm else ""
            if not messagebox.askyesno(
                self.t("dlg_confirm_title"),
                self.t("dlg_confirm_msg").format(len(selected), action, preview) + warn,
                icon="warning"):
                return

        perm = self.perm_delete.get()
        deleted, errors = 0, []
        for iid in selected:
            gi, rel = self.item_map[iid]
            abs_path = (Path(self.scan_root) / rel).resolve()
            if not abs_path.exists():
                errors.append(f"{rel}: {self.t('file_not_exist')}")
                self.tree.delete(iid)
                del self.item_map[iid]
                if gi < len(self.groups) and rel in self.groups[gi].rel_paths:
                    self.groups[gi].rel_paths.remove(rel)
                continue
            try:
                if perm:
                    abs_path.unlink()
                else:
                    send2trash(str(abs_path))
                deleted += 1
            except Exception as e:
                errors.append(f"{rel}: {e}")
                continue

            self.tree.delete(iid)
            del self.item_map[iid]
            if gi < len(self.groups) and rel in self.groups[gi].rel_paths:
                self.groups[gi].rel_paths.remove(rel)

        for gi, g in enumerate(self.groups):
            if not g.rel_paths:
                sep = f"sep_{gi}"
                if self.tree.exists(sep):
                    self.tree.delete(sep)

        if errors:
            messagebox.showwarning(self.t("err_partial"), "\n".join(errors[:20]))
        action = self.t("action_perm") if perm else self.t("action_recycle")
        msg = self.t("status_deleted").format(action, deleted)
        if errors:
            msg += self.t("status_deleted_err").format(len(errors))
        self.status(msg)

    # -- Run --

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    DupFinderGUI().run()
