"""4u4free GUI — Store-style interface on top of the SteaMidra (sff) engine.

Sidebar navigation (Home / Store / Downloads / Tools / Logs), a browsable
game Store, and the same Windows download pipeline the original program
uses: fetch Lua -> parse -> write depot keys -> install Lua to stplug-in ->
write ACF -> register library -> Steam downloads natively via LumaCore.

Launch:  4u4free-gui   (or: python -m four_u_four_free.gui)
"""

from __future__ import annotations

import io
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Callable

from . import __version__
from .config import ConfigStore
from .errors import FourUFourFreeError
from .steam import doctor, list_games, list_libraries, require_steam_root

try:
    from sff.dlc_unlockers.base import UnlockerType
    from sff.dlc_unlockers.creamapi import CreamAPIUnlocker
    from sff.dlc_unlockers.smokeapi import SmokeAPIUnlocker
    from sff.dlc_unlockers.uplay_r1 import UplayR1Unlocker
    from sff.dlc_unlockers.uplay_r2 import UplayR2Unlocker
    from sff.dlc_unlockers.downloader import GitHubReleaseDownloader
    from sff.lumacore.lumacore_setup import (
        deactivate_lumacore,
        get_installed_lumacore_version,
        install_lumacore,
    )
    from sff.game.fix_game.steamstub_unpacker import SteamStubUnpacker
    from sff.game.crack_fix import fetch_crack_games, search_crack_games, _badge_summary, _extract_to_game_folder
    from sff.network.pixeldrain import _extract_pixeldrain_id, download_pixeldrain
    from sff.game_list_fallback import browse_games_json, search_games_json, search_name_fallback
    from sff.lua.choices import download_lua_direct
    from sff.lua.manager import parse_lua_contents
    from sff.lua.writer import ACFWriter, ConfigVDFWriter
    from sff.steam_tools_compat import install_lua_to_steam
    from sff.core.storage.vdf import ensure_library_has_app
    from sff.core.structs import LuaEndpoint, Settings
    from sff.core.storage.settings import get_setting
    HAS_SFF = True
except ImportError:
    HAS_SFF = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

UNLOCKER_CACHE_DIR = Path.home() / ".4u4free" / "unlockers"
HEADER_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
CARD_W, CARD_H = 184, 69
PER_PAGE = 24

BG = "#1b1d23"
SIDEBAR_BG = "#232630"
CARD_BG = "#262a34"
FG = "#e8eaf0"
FG_DIM = "#9aa0ae"
ACCENT = "#3b82f6"


def _header_url_for(game: dict) -> str:
    url = game.get("header_image") or ""
    if url.startswith("http"):
        return url
    app_id = game.get("app_id") or 0
    return HEADER_URL.format(app_id=app_id) if app_id else ""


class StoreApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.store = ConfigStore()
        self.q: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._busy = threading.Event()
        self._img_refs: dict[int, Any] = {}
        self._img_failed: set[int] = set()
        self._store_games: list[dict] = []
        self._store_offset = 0
        self._store_total = 0
        self._crack_results: list[dict] = []
        self.downloads: dict[str, dict] = {}

        root.title(f"4u4free {__version__}")
        root.geometry("1100x720")
        root.minsize(940, 600)
        root.configure(bg=BG)
        self._style()

        shell = ttk.Frame(root, style="App.TFrame")
        shell.pack(fill="both", expand=True)

        self._build_sidebar(shell)
        self.pages: dict[str, ttk.Frame] = {}
        self.page_container = ttk.Frame(shell, style="App.TFrame")
        self.page_container.pack(side="left", fill="both", expand=True)
        self._build_home_page()
        self._build_store_page()
        self._build_downloads_page()
        self._build_tools_page()
        self._build_logs_page()

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")

        self.root.after(100, self._poll_queue)
        self.show_page("home")
        self.run_bg(self.task_doctor)
        self.run_bg(self.task_lc_status_quiet)

    # ── theme ─────────────────────────────────────────────────────────

    def _style(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("App.TFrame", background=BG)
        s.configure("Side.TFrame", background=SIDEBAR_BG)
        s.configure("Card.TFrame", background=CARD_BG)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Side.TLabel", background=SIDEBAR_BG, foreground=FG)
        s.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
        s.configure("Card.TLabel", background=CARD_BG, foreground=FG)
        s.configure("CardDim.TLabel", background=CARD_BG, foreground=FG_DIM)
        s.configure("H1.TLabel", background=BG, foreground=FG, font=("", 20, "bold"))
        s.configure("H2.TLabel", background=BG, foreground=FG, font=("", 12, "bold"))
        s.configure("Status.TLabel", background=SIDEBAR_BG, foreground=FG_DIM, padding=(8, 4))
        s.configure("Nav.TButton", background=SIDEBAR_BG, foreground=FG, anchor="w", padding=(14, 8), borderwidth=0, font=("", 11))
        s.configure("NavActive.TButton", background="#31364a", foreground="#ffffff", anchor="w", padding=(14, 8), borderwidth=0, font=("", 11, "bold"))
        s.map("Nav.TButton", background=[("active", "#31364a")])
        s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", borderwidth=0, padding=(12, 6))
        s.map("Accent.TButton", background=[("active", "#2f6fd8")])
        s.configure("TButton", background="#31364a", foreground=FG, borderwidth=0, padding=(10, 6))
        s.map("TButton", background=[("active", "#3d4358")])
        s.configure("TEntry", fieldbackground="#14161c", foreground=FG, insertcolor=FG, borderwidth=0, padding=6)
        s.configure("Treeview", background=CARD_BG, foreground=FG, fieldbackground=CARD_BG, borderwidth=0, rowheight=24)
        s.configure("Treeview.Heading", background="#31364a", foreground=FG, borderwidth=0)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background="#31364a", foreground=FG, padding=(14, 7))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)])

    # ── infrastructure ────────────────────────────────────────────────

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.q.put(("call", lambda m=f"[{stamp}] {message}": self._append_log(m)))

    def status(self, message: str) -> None:
        self.q.put(("call", lambda m=message: self.status_var.set(m)))

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "call":
                    payload()
                elif kind == "photo":
                    app_id, pil_img = payload
                    photo = ImageTk.PhotoImage(pil_img)
                    self._set_card_image(app_id, photo)
                elif kind == "idle":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _set_busy(self, busy: bool) -> None:
        self.root.configure(cursor="watch" if busy else "")
        if not busy:
            self._busy.clear()

    def run_bg(self, fn: Callable[[], Any]) -> None:
        if self._busy.is_set():
            self.status("A task is already running — please wait.")
            return

        def worker() -> None:
            self._busy.set()
            try:
                fn()
            except FourUFourFreeError as exc:
                self.log(f"error: {exc}")
                self.status(f"error: {exc}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"unexpected error: {exc.__class__.__name__}: {exc}")
                self.status(f"unexpected error: {exc}")
            finally:
                self.q.put(("idle", None))

        threading.Thread(target=worker, daemon=True).start()

    def _require_sff(self) -> None:
        if not HAS_SFF:
            raise FourUFourFreeError("SteaMidra engine unavailable — the sff package could not be imported")

    def _steam_root(self) -> Path:
        config = self.store.load()
        try:
            return require_steam_root(None, config.steam_root).path
        except Exception:
            guess = Path(r"C:\Program Files (x86)\Steam")
            if guess.is_dir():
                return guess
            raise FourUFourFreeError("Steam folder not found — set it with: 4u4free config set --steam-root ...")

    # ── sidebar + navigation ──────────────────────────────────────────

    def _build_sidebar(self, shell: ttk.Frame) -> None:
        side = ttk.Frame(shell, style="Side.TFrame", width=190)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ttk.Label(side, text="  4u4free", style="Side.TLabel", font=("", 15, "bold")).pack(anchor="w", pady=(18, 20))

        self._nav_buttons: dict[str, ttk.Button] = {}
        for key, label in (("home", "Home"), ("store", "Store"), ("downloads", "Downloads"), ("tools", "Tools"), ("logs", "Logs")):
            btn = ttk.Button(side, text=f"  {label}", style="Nav.TButton", command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", pady=1)
            self._nav_buttons[key] = btn

        spacer = ttk.Frame(side, style="Side.TFrame")
        spacer.pack(fill="both", expand=True)
        ttk.Button(side, text="  Restart Steam", style="Nav.TButton", command=self.on_restart_steam).pack(fill="x", pady=1, side="bottom")

    def show_page(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.configure(style="NavActive.TButton" if k == key else "Nav.TButton")
        for k, page in self.pages.items():
            page.pack(fill="both", expand=True) if k == key else page.pack_forget()
        if key == "store" and not self._store_games:
            self.run_bg(self.task_store_browse)

    # ── home page ─────────────────────────────────────────────────────

    def _build_home_page(self) -> None:
        page = ttk.Frame(self.page_container, style="App.TFrame", padding=24)
        self.pages["home"] = page
        ttk.Label(page, text="Home", style="H1.TLabel").pack(anchor="w")
        ttk.Label(page, text="Steam toolkit status and quick actions", style="Dim.TLabel").pack(anchor="w", pady=(0, 16))

        self.home_status = tk.StringVar(value="Checking Steam…")
        ttk.Label(page, textvariable=self.home_status, style="TLabel", font=("", 11)).pack(anchor="w")

        self.lc_home_var = tk.StringVar(value="LumaCore: checking…")
        ttk.Label(page, textvariable=self.lc_home_var, style="TLabel").pack(anchor="w", pady=(6, 16))

        row = ttk.Frame(page, style="TFrame")
        row.pack(anchor="w")
        ttk.Button(row, text="Open Store", style="Accent.TButton", command=lambda: self.show_page("store")).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Refresh games", command=lambda: self.run_bg(self.task_games)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Restart Steam", command=self.on_restart_steam).pack(side="left")

        ttk.Label(page, text="Installed games", style="H2.TLabel").pack(anchor="w", pady=(22, 6))
        cols = ("app_id", "name", "build")
        self.home_tree = ttk.Treeview(page, columns=cols, show="headings", height=12)
        for col, title, width in (("app_id", "App ID", 100), ("name", "Name", 460), ("build", "Build", 100)):
            self.home_tree.heading(col, text=title)
            self.home_tree.column(col, width=width, anchor="w")
        self.home_tree.pack(fill="both", expand=True)

    def task_doctor(self) -> None:
        config = self.store.load()
        report = doctor(None, config.steam_root)
        root = report.get("steam_root", "-")
        found = bool(report.get("steam_found"))
        text = f"Steam: {root}  [{'OK' if found else 'NOT FOUND'}]"
        self.q.put(("call", lambda t=text: self.home_status.set(t)))
        self.log(f"doctor: steam_found={found}")

    def task_games(self) -> None:
        config = self.store.load()
        location = require_steam_root(None, config.steam_root)
        games = list_games(list_libraries(location.path))
        rows = [(g.app_id, g.name, g.build_id or "-") for g in games]

        def fill() -> None:
            self.home_tree.delete(*self.home_tree.get_children())
            for row in rows:
                self.home_tree.insert("", "end", values=row)

        self.q.put(("call", fill))
        self.status(f"{len(rows)} installed game(s)")
        self.log(f"games: found {len(rows)}")

    def task_lc_status_quiet(self) -> None:
        self._require_sff()
        version = get_installed_lumacore_version(self._steam_root())
        text = f"LumaCore: {'installed (' + version + ')' if version else 'not installed'}"
        self.q.put(("call", lambda t=text: self.lc_home_var.set(t)))

    def on_restart_steam(self) -> None:
        if sys.platform != "win32":
            messagebox.showinfo("Restart Steam", "Automatic restart is Windows-only. Restart Steam manually.")
            return
        if not messagebox.askyesno("Restart Steam", "Close and relaunch Steam now?"):
            return
        self.run_bg(self.task_restart_steam)

    def task_restart_steam(self) -> None:
        steam = self._steam_root()
        self.log("Restarting Steam…")
        for name in ("steam.exe", "steamwebhelper.exe", "steamservice.exe"):
            subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True, **({"creationflags": 0x08000000} if sys.platform == "win32" else {}))
        time.sleep(2)
        exe = steam / "steam.exe"
        if exe.is_file():
            subprocess.Popen([str(exe)], cwd=str(steam))
            self.log("Steam relaunched.")
            self.status("Steam relaunched")
        else:
            self.log(f"steam.exe not found at {exe} — start Steam manually.")

    # ── store page ────────────────────────────────────────────────────

    def _build_store_page(self) -> None:
        page = ttk.Frame(self.page_container, style="App.TFrame", padding=24)
        self.pages["store"] = page

        ttk.Label(page, text="Store", style="H1.TLabel").pack(anchor="w")
        ttk.Label(page, text="Browse and download games — Steam fetches the files natively via LumaCore", style="Dim.TLabel").pack(anchor="w", pady=(0, 12))

        search_row = ttk.Frame(page, style="TFrame")
        search_row.pack(fill="x")
        self.store_search_var = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self.store_search_var, font=("", 11))
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        entry.bind("<Return>", lambda _e: self.run_bg(self.task_store_search))
        ttk.Button(search_row, text="Search", style="Accent.TButton", command=lambda: self.run_bg(self.task_store_search)).pack(side="left", padx=(8, 0))
        ttk.Button(search_row, text="Clear", command=self.on_store_clear).pack(side="left", padx=(8, 0))

        opts_row = ttk.Frame(page, style="TFrame")
        opts_row.pack(fill="x", pady=(8, 4))
        ttk.Label(opts_row, text="Source:", style="Dim.TLabel").pack(side="left")
        self.store_source_var = tk.StringVar(value="auto")
        ttk.Combobox(
            opts_row, textvariable=self.store_source_var, state="readonly", width=22,
            values=["auto", "oureveryday", "hubcap", "ryuu", "depotbox"],
        ).pack(side="left", padx=(6, 16))
        self.store_nsfw_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_row, text="Hide adult content", variable=self.store_nsfw_var).pack(side="left")

        self.store_info_var = tk.StringVar(value="")
        ttk.Label(page, textvariable=self.store_info_var, style="Dim.TLabel").pack(anchor="w", pady=(2, 6))

        grid_wrap = ttk.Frame(page, style="App.TFrame")
        grid_wrap.pack(fill="both", expand=True)
        self.store_canvas = tk.Canvas(grid_wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(grid_wrap, orient="vertical", command=self.store_canvas.yview)
        self.store_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.store_canvas.pack(side="left", fill="both", expand=True)
        self.store_grid = ttk.Frame(self.store_canvas, style="App.TFrame")
        self.store_grid_window = self.store_canvas.create_window((0, 0), window=self.store_grid, anchor="nw")
        self.store_grid.bind("<Configure>", lambda e: self.store_canvas.configure(scrollregion=self.store_canvas.bbox("all")))
        self.store_canvas.bind("<Configure>", lambda e: self.store_canvas.itemconfigure(self.store_grid_window, width=e.width))
        self.store_canvas.bind_all("<MouseWheel>", lambda e: self.store_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        nav_row = ttk.Frame(page, style="TFrame")
        nav_row.pack(fill="x", pady=(8, 0))
        ttk.Button(nav_row, text="< Prev", command=self.on_store_prev).pack(side="left")
        self.store_page_var = tk.StringVar(value="page 1")
        ttk.Label(nav_row, textvariable=self.store_page_var, style="Dim.TLabel").pack(side="left", padx=12)
        ttk.Button(nav_row, text="Next >", command=self.on_store_next).pack(side="left")

    def on_store_clear(self) -> None:
        self.store_search_var.set("")
        self._store_offset = 0
        self.run_bg(self.task_store_browse)

    def on_store_prev(self) -> None:
        self._store_offset = max(0, self._store_offset - PER_PAGE)
        self.run_bg(self.task_store_browse)

    def on_store_next(self) -> None:
        if self._store_offset + PER_PAGE < self._store_total:
            self._store_offset += PER_PAGE
            self.run_bg(self.task_store_browse)

    def task_store_browse(self) -> None:
        self._require_sff()
        self.status("Loading store…")
        result = browse_games_json(offset=self._store_offset, per_page=PER_PAGE, sort_by="updated", block_nsfw=self.store_nsfw_var.get())
        games = result.get("games", [])
        self._store_total = int(result.get("total", len(games)) or 0)
        self._store_games = games
        self._render_store(f"browsing · {self._store_total} titles in catalog")

    def task_store_search(self) -> None:
        self._require_sff()
        query = self.store_search_var.get().strip()
        if not query:
            self.task_store_browse()
            return
        self.status(f"Searching '{query}'…")
        results = search_games_json(query, limit=60)
        if not results:
            results = [
                {**r, "header_image": ""} for r in search_name_fallback(query, limit=60)
            ]
        self._store_games = results
        self._store_total = len(results)
        self._store_offset = 0
        self._render_store(f"search '{query}' · {len(results)} result(s)")

    def _render_store(self, info: str) -> None:
        games = list(self._store_games)
        page_no = self._store_offset // PER_PAGE + 1

        def render() -> None:
            for child in self.store_grid.winfo_children():
                child.destroy()
            self._img_refs.clear()
            self.store_info_var.set(info)
            self.store_page_var.set(f"page {page_no}")
            if not games:
                ttk.Label(self.store_grid, text="No results. Try another search.", style="Dim.TLabel").grid(row=0, column=0, pady=20)
                return
            for idx, game in enumerate(games):
                self._store_card(self.store_grid, game).grid(
                    row=idx // 3, column=idx % 3, padx=8, pady=8, sticky="n"
                )
            for col in range(3):
                self.store_grid.columnconfigure(col, weight=1)

        self.q.put(("call", render))
        self.status(info)
        self._load_store_images(games)

    def _store_card(self, parent, game: dict) -> ttk.Frame:
        app_id = int(game.get("app_id") or 0)
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        img_label = ttk.Label(card, style="Card.TLabel", text=" ", width=24, anchor="center")
        img_label._4u4_appid = app_id
        img_label.pack()
        if not HAS_PIL:
            img_label.configure(text=game.get("name", "")[:24], wraplength=180)
        else:
            img_label.configure(text="loading…" if app_id else " ")
        ttk.Label(card, text=(game.get("name") or f"App {app_id}")[:40], style="Card.TLabel", wraplength=184, font=("", 10, "bold")).pack(anchor="w", pady=(6, 0))
        ttk.Label(card, text=f"App ID: {app_id}", style="CardDim.TLabel").pack(anchor="w")
        updated = str(game.get("last_updated") or game.get("updated") or "")[:19].replace("T", " ")
        if updated:
            ttk.Label(card, text=f"Updated: {updated}", style="CardDim.TLabel").pack(anchor="w")
        btn = ttk.Button(card, text="Download", style="Accent.TButton", command=lambda a=app_id, n=game.get("name", f"App {app_id}"): self.on_store_download(a, n))
        btn.pack(fill="x", pady=(8, 0))
        if not app_id:
            btn.state(["disabled"])
        return card

    def _load_store_images(self, games: list[dict]) -> None:
        """Decode + resize headers off-thread; PhotoImage is created on the UI thread."""
        if not HAS_PIL:
            return
        for game in games:
            app_id = int(game.get("app_id") or 0)
            if not app_id or app_id in self._img_refs or app_id in self._img_failed:
                continue
            url = _header_url_for(game)
            if not url:
                self._img_failed.add(app_id)
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"4u4free/{__version__}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                pil_img = Image.open(io.BytesIO(data)).convert("RGB").resize((CARD_W, CARD_H))
            except Exception:
                self._img_failed.add(app_id)
                continue
            self.q.put(("photo", (app_id, pil_img)))

    def _set_card_image(self, app_id: int, photo: Any) -> None:
        self._img_refs[app_id] = photo
        for child in self.store_grid.winfo_children():
            labels = [w for w in child.winfo_children() if isinstance(w, ttk.Label)]
            if labels and getattr(labels[0], "_4u4_appid", None) == app_id:
                labels[0].configure(image=photo, text="")
                return

    def on_store_download(self, app_id: int, name: str) -> None:
        if not messagebox.askyesno(
            "Confirm download",
            f"Install {name} (App {app_id})?\n\n"
            "The Lua, depot keys, manifests, and ACF are written to Steam.\n"
            "Steam then downloads the game files natively (LumaCore makes it appear in your library).",
        ):
            return
        self.run_bg(lambda: self.task_download_game(app_id, name))

    def _source_enum(self):
        choice = self.store_source_var.get()
        mapping = {
            "hubcap": LuaEndpoint.HUBCAP,
            "oureveryday": LuaEndpoint.OUREVERYDAY,
            "ryuu": LuaEndpoint.RYUU,
            "depotbox": LuaEndpoint.DEPOTBOX,
        }
        if choice in mapping:
            return mapping[choice]
        try:
            if str(get_setting(Settings.HUBCAP_KEY) or "").strip():
                return LuaEndpoint.HUBCAP
        except Exception:
            pass
        return LuaEndpoint.OUREVERYDAY

    def task_download_game(self, app_id: int, name: str) -> None:
        """The SteaMidra Windows pipeline, bridge-free."""
        self._require_sff()
        steam_path = self._steam_root()
        self._dl_update(app_id, name, "starting", 0)

        def prog(pct: int, msg: str) -> None:
            self._dl_update(app_id, name, msg, pct)

        try:
            prog(5, "downloading lua")
            saved_lua_root = Path.cwd() / "saved_lua"
            saved_lua_root.mkdir(exist_ok=True)
            lua_path = download_lua_direct(
                dest=saved_lua_root,
                app_id=str(app_id),
                source=self._source_enum(),
                steam_path=steam_path,
            )
            if not lua_path:
                raise FourUFourFreeError(
                    "Lua download failed — the source returned nothing. Try a different Source in the Store tab."
                )

            prog(20, "parsing lua")
            parsed = parse_lua_contents(lua_path.read_text(encoding="utf-8", errors="replace"), lua_path)
            if not parsed:
                raise FourUFourFreeError("Failed to parse the Lua file")

            prog(50, "writing depot keys")
            ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)

            prog(60, "installing lua to Steam")
            install_lua_to_steam(steam_path, str(app_id), lua_path)

            prog(75, "writing ACF")
            acf = ACFWriter(steam_path)
            acf.write_acf(parsed)
            if hasattr(acf, "patch_workshop_acf"):
                acf.patch_workshop_acf(parsed)

            prog(85, "registering library entry")
            ensure_library_has_app(steam_path, steam_path, str(app_id))

            prog(100, "complete — restart Steam to download")
            self.log(f"Download setup complete for {name} (App {app_id}). Restart Steam; the game appears in your library and Steam fetches the files.")
            self.status(f"{name}: ready — restart Steam")
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", "unknown")
            self._dl_update(app_id, name, f"missing dependency: {missing}", 0)
            self.log(f"Download failed — Python package '{missing}' is not installed. Fix: pip install {missing}")
        except Exception as exc:
            self._dl_update(app_id, name, f"failed: {exc}", 0)
            self.log(f"download failed for App {app_id}: {exc}")

    def _dl_update(self, app_id: Any, name: str, status: str, pct: int) -> None:
        key = str(app_id)

        def update() -> None:
            self.downloads[key] = {"name": name, "status": status, "pct": pct, "time": time.strftime("%H:%M:%S")}
            self.dl_tree.delete(*self.dl_tree.get_children())
            for k, d in self.downloads.items():
                self.dl_tree.insert("", "end", iid=k, values=(k, d["name"], d["status"], f"{d['pct']}%", d["time"]))

        self.q.put(("call", update))

    # ── downloads page ────────────────────────────────────────────────

    def _build_downloads_page(self) -> None:
        page = ttk.Frame(self.page_container, style="App.TFrame", padding=24)
        self.pages["downloads"] = page
        ttk.Label(page, text="Downloads", style="H1.TLabel").pack(anchor="w")
        ttk.Label(page, text="Games you queued from the Store — restart Steam to fetch the files", style="Dim.TLabel").pack(anchor="w", pady=(0, 12))
        cols = ("app_id", "name", "status", "progress", "time")
        self.dl_tree = ttk.Treeview(page, columns=cols, show="headings", height=16)
        for col, title, width in (
            ("app_id", "App ID", 90),
            ("name", "Name", 320),
            ("status", "Status", 340),
            ("progress", "Progress", 90),
            ("time", "Queued", 90),
        ):
            self.dl_tree.heading(col, text=title)
            self.dl_tree.column(col, width=width, anchor="w")
        self.dl_tree.pack(fill="both", expand=True)

    # ── tools page ────────────────────────────────────────────────────

    def _build_tools_page(self) -> None:
        page = ttk.Frame(self.page_container, style="App.TFrame", padding=24)
        self.pages["tools"] = page
        ttk.Label(page, text="Tools", style="H1.TLabel").pack(anchor="w")
        ttk.Label(page, text="Unlockers, LumaCore, DRM removal, community fixes", style="Dim.TLabel").pack(anchor="w", pady=(0, 12))

        nb = ttk.Notebook(page)
        nb.pack(fill="both", expand=True)
        self._tool_unlockers(nb)
        self._tool_lumacore(nb)
        self._tool_steamstub(nb)
        self._tool_crack(nb)

    def _tool_labeled_row(self, parent, label: str) -> tuple[ttk.Frame, tk.StringVar]:
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="TLabel").pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Browse…", command=lambda: self._pick(var)).pack(side="left")
        return row, var

    def _pick(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory()
        if chosen:
            var.set(chosen)

    def _tool_unlockers(self, nb) -> None:
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="DLC Unlockers")
        _row, self.unl_folder_var = self._tool_labeled_row(frame, "Game folder:")
        row2 = ttk.Frame(frame, style="TFrame")
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="Unlocker:").pack(side="left")
        self.unl_kind_var = tk.StringVar(value="smokeapi")
        ttk.Combobox(row2, textvariable=self.unl_kind_var, values=["creamapi", "smokeapi", "uplay-r1", "uplay-r2"], state="readonly", width=12).pack(side="left", padx=6)
        ttk.Label(row2, text="App ID:").pack(side="left", padx=(12, 0))
        self.unl_appid_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.unl_appid_var, width=10).pack(side="left", padx=6)
        ttk.Label(row2, text="DLC IDs:").pack(side="left", padx=(12, 0))
        self.unl_dlc_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.unl_dlc_var, width=18).pack(side="left", padx=6)
        row3 = ttk.Frame(frame, style="TFrame")
        row3.pack(fill="x", pady=(8, 0))
        ttk.Button(row3, text="List installed", command=lambda: self.run_bg(self.task_unl_list)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Validate folder", command=lambda: self.run_bg(self.task_unl_validate)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Install", style="Accent.TButton", command=lambda: self.run_bg(self.task_unl_install)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Uninstall", command=lambda: self.run_bg(self.task_unl_uninstall)).pack(side="left")

    def _tool_lumacore(self, nb) -> None:
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="LumaCore")
        self.lc_status_var = tk.StringVar(value="Unknown")
        ttk.Label(frame, textvariable=self.lc_status_var, style="TLabel", font=("", 11, "bold")).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(frame, style="TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Check status", command=lambda: self.run_bg(self.task_lc_status)).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Install / Update", style="Accent.TButton", command=lambda: self.run_bg(self.task_lc_install)).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Uninstall", command=lambda: self.run_bg(self.task_lc_uninstall)).pack(side="left")
        ttk.Label(frame, text="Steam is closed automatically during install/uninstall.", style="Dim.TLabel").pack(anchor="w", pady=(10, 0))

    def _tool_steamstub(self, nb) -> None:
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="SteamStub DRM")
        _row, self.stub_path_var = self._tool_labeled_row(frame, "Game folder:")
        row3 = ttk.Frame(frame, style="TFrame")
        row3.pack(fill="x", pady=(8, 0))
        ttk.Button(row3, text="Dry-run scan", command=lambda: self.run_bg(self.task_stub_dryrun)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Unpack", style="Accent.TButton", command=lambda: self.run_bg(self.task_stub_unpack)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Restore backups", command=lambda: self.run_bg(self.task_stub_restore)).pack(side="left")
        ttk.Label(frame, text="Removes SteamStub DRM with Steamless; keeps .steamstub.bak copies.", style="Dim.TLabel").pack(anchor="w", pady=(10, 0))

    def _tool_crack(self, nb) -> None:
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="Fixes & Bypasses")
        row1 = ttk.Frame(frame, style="TFrame")
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="Game name:").pack(side="left")
        self.crack_name_var = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.crack_name_var)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        entry.bind("<Return>", lambda _e: self.run_bg(self.task_crack_search))
        ttk.Button(row1, text="Search CrakFiles", style="Accent.TButton", command=lambda: self.run_bg(self.task_crack_search)).pack(side="left")
        self.crack_list = tk.Listbox(frame, height=9, bg="#14161c", fg=FG, selectbackground=ACCENT, relief="flat")
        self.crack_list.pack(fill="both", expand=True, pady=6)
        _row, self.crack_target_var = self._tool_labeled_row(frame, "Target folder:")
        ttk.Button(frame, text="Apply selected fix", style="Accent.TButton", command=lambda: self.run_bg(self.task_crack_apply)).pack(anchor="w", pady=(8, 0))

    # ── logs page ─────────────────────────────────────────────────────

    def _build_logs_page(self) -> None:
        page = ttk.Frame(self.page_container, style="App.TFrame", padding=24)
        self.pages["logs"] = page
        head = ttk.Frame(page, style="TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Logs", style="H1.TLabel").pack(side="left")
        ttk.Button(head, text="Clear", command=self._clear_log).pack(side="right")
        self.log_text = scrolledtext.ScrolledText(page, height=24, state="disabled", wrap="word", bg="#14161c", fg=FG, relief="flat", insertbackground=FG)
        self.log_text.pack(fill="both", expand=True, pady=(12, 0))

    # ── unlocker tasks ────────────────────────────────────────────────

    def _downloader(self):
        return GitHubReleaseDownloader(UNLOCKER_CACHE_DIR)

    def _dll_dir_for(self, key: str):
        type_map = {
            "creamapi": UnlockerType.CREAMAPI,
            "smokeapi": UnlockerType.SMOKEAPI,
            "uplay-r1": UnlockerType.UPLAY_R1,
            "uplay-r2": UnlockerType.UPLAY_R2,
        }
        dl = self._downloader()
        utype = type_map[key]
        return dl.get_cached_dll(utype) or dl._get_local_resource(utype)

    def _unlocker_instance(self, key: str):
        return {
            "creamapi": CreamAPIUnlocker,
            "smokeapi": SmokeAPIUnlocker,
            "uplay-r1": UplayR1Unlocker,
            "uplay-r2": UplayR2Unlocker,
        }[key]()

    def _unl_inputs(self) -> tuple[Path, str, int, list[int]]:
        folder = Path(self.unl_folder_var.get().strip().strip('"'))
        if not folder.is_dir():
            raise FourUFourFreeError(f"Game folder not found: {folder or '(empty)'}")
        kind = self.unl_kind_var.get()
        raw = self.unl_appid_var.get().strip()
        app_id = int(raw) if raw else 0
        dlc_ids = [int(x.strip()) for x in self.unl_dlc_var.get().split(",") if x.strip()]
        return folder, kind, app_id, dlc_ids

    def task_unl_list(self) -> None:
        self._require_sff()
        folder = Path(self.unl_folder_var.get().strip().strip('"') or ".")
        for key in ("creamapi", "smokeapi", "uplay-r1", "uplay-r2"):
            inst = self._unlocker_instance(key)
            installed = folder.is_dir() and inst.is_installed(folder)
            self.log(f"{inst.display_name:<20} {'installed' if installed else 'not installed'}")

    def task_unl_validate(self) -> None:
        self._require_sff()
        folder, _k, _a, _d = self._unl_inputs()
        for label, path in {
            "steam_api.dll (32-bit)": folder / "steam_api.dll",
            "steam_api64.dll (64-bit)": folder / "steam_api64.dll",
            "uplay_r1_loader.dll": folder / "uplay_r1_loader.dll",
            "upc_r2_loader.dll": folder / "upc_r2_loader.dll",
        }.items():
            self.log(f"{label:<26} {'found' if path.exists() else 'missing'}")

    def task_unl_install(self) -> None:
        self._require_sff()
        folder, kind, app_id, dlc_ids = self._unl_inputs()
        if not app_id:
            raise FourUFourFreeError("Enter the game's App ID first")
        if not messagebox.askyesno("Confirm", f"Install {kind} into:\n{folder}?\n\nOriginal DLLs are backed up."):
            self.log("Cancelled.")
            return
        if kind == "creamapi":
            ok = CreamAPIUnlocker(self._downloader()).install(folder, dlc_ids, app_id)
        elif kind == "smokeapi":
            ok = SmokeAPIUnlocker().install(folder, dlc_ids, app_id, smokeapi_dir=self._dll_dir_for(kind))
        elif kind == "uplay-r1":
            ok = UplayR1Unlocker().install(folder, dlc_ids, app_id, unlocker_dir=self._dll_dir_for(kind))
        else:
            ok = UplayR2Unlocker().install(folder, dlc_ids, app_id, unlocker_dir=self._dll_dir_for(kind))
        self.log(f"{'Installed' if ok else 'FAILED to install'} {kind} into {folder}")

    def task_unl_uninstall(self) -> None:
        self._require_sff()
        folder, kind, _a, _d = self._unl_inputs()
        if not messagebox.askyesno("Confirm", f"Remove {kind} from:\n{folder}?"):
            self.log("Cancelled.")
            return
        ok = self._unlocker_instance(kind).uninstall(folder)
        self.log(f"{'Removed' if ok else 'FAILED to remove'} {kind} from {folder}")

    # ── lumacore tasks ────────────────────────────────────────────────

    def task_lc_status(self) -> None:
        self._require_sff()
        version = get_installed_lumacore_version(self._steam_root())
        text = f"LumaCore: {'installed (' + version + ')' if version else 'not installed'}"
        self.q.put(("call", lambda t=text: self.lc_status_var.set(t)))
        self.q.put(("call", lambda t=text: self.lc_home_var.set(t)))
        self.log(text)

    def task_lc_install(self) -> None:
        self._require_sff()
        steam = self._steam_root()
        if not messagebox.askyesno("Confirm", "Install/update LumaCore?\n\nSteam will be closed automatically."):
            self.log("Cancelled.")
            return
        ok, message = install_lumacore(steam, progress_callback=self.log)
        self.log(message)
        if ok:
            self.task_lc_status()

    def task_lc_uninstall(self) -> None:
        self._require_sff()
        steam = self._steam_root()
        if not messagebox.askyesno("Confirm", "Remove LumaCore DLLs from Steam?"):
            self.log("Cancelled.")
            return
        ok, message = deactivate_lumacore(steam, progress_callback=self.log)
        self.log(message)
        self.task_lc_status()

    # ── steamstub tasks ───────────────────────────────────────────────

    def _stub_unpacker(self) -> "SteamStubUnpacker":
        unpacker = SteamStubUnpacker()
        if not unpacker.is_available():
            raise FourUFourFreeError("Steamless not found under third_party/")
        return unpacker

    def _stub_target(self) -> Path:
        target = Path(self.stub_path_var.get().strip().strip('"'))
        if not target.is_dir():
            raise FourUFourFreeError(f"Folder not found: {target or '(empty)'}")
        return target

    def task_stub_dryrun(self) -> None:
        self._require_sff()
        unpacker = self._stub_unpacker()
        target = self._stub_target()
        candidates = [f for f in target.rglob("*.exe") if not unpacker._should_skip(f)]
        self.log(f"{len(candidates)} candidate executable(s):")
        for exe in candidates[:25]:
            self.log(f"  {exe.relative_to(target)}")

    def task_stub_unpack(self) -> None:
        self._require_sff()
        unpacker = self._stub_unpacker()
        target = self._stub_target()
        if not messagebox.askyesno("Confirm", f"Unpack SteamStub DRM under:\n{target}?"):
            self.log("Cancelled.")
            return
        count = unpacker.unpack_directory(target, log_func=self.log)
        self.log(f"Unpacked {count} file(s)")

    def task_stub_restore(self) -> None:
        self._require_sff()
        unpacker = self._stub_unpacker()
        target = self._stub_target()
        if not messagebox.askyesno("Confirm", f"Restore all .steamstub.bak backups under:\n{target}?"):
            self.log("Cancelled.")
            return
        restored = unpacker.restore_directory(target, log_func=self.log)
        self.log(f"Restored {restored} backup(s)")

    # ── crack tasks ───────────────────────────────────────────────────

    def task_crack_search(self) -> None:
        self._require_sff()
        query = self.crack_name_var.get().strip()
        if not query:
            raise FourUFourFreeError("Type a game name first")
        games = fetch_crack_games()
        matches = search_crack_games(query, games)
        self._crack_results = matches[:50]
        labels = []
        for g in self._crack_results:
            build, badges = g.get("buildid"), _badge_summary(g)
            parts = [g.get("name", "?")]
            if build:
                parts.append(f"[Build {build}]")
            if badges:
                parts.append(f"[{badges}]")
            labels.append("  ".join(parts))

        def fill() -> None:
            self.crack_list.delete(0, "end")
            for label in labels:
                self.crack_list.insert("end", label)

        self.q.put(("call", fill))
        self.log(f"CrakFiles: {len(matches)} match(es) for '{query}'")

    def task_crack_apply(self) -> None:
        self._require_sff()
        selection = self.crack_list.curselection()
        if not selection:
            raise FourUFourFreeError("Select a game in the results list first")
        game = self._crack_results[selection[0]]
        target = Path(self.crack_target_var.get().strip().strip('"'))
        if not target.is_dir():
            raise FourUFourFreeError(f"Target folder not found: {target or '(empty)'}")
        fixes = game.get("fixes", [])
        if not fixes:
            raise FourUFourFreeError("Selected game has no downloadable fixes")
        name = game.get("name", "game")
        if not messagebox.askyesno("Confirm", f"Download and apply a fix for '{name}'\nto:\n{target}?"):
            self.log("Cancelled.")
            return

        last_error = "no fixes had a valid download link"
        for fix in fixes:
            file_id = _extract_pixeldrain_id(fix.get("href", ""))
            if not file_id:
                continue
            self.log(f"Downloading {fix.get('filename', fix.get('href', ''))}…")
            temp_dir = Path(tempfile.mkdtemp(prefix="4u4free_crack_"))
            try:
                archive = download_pixeldrain(file_id, temp_dir)
                if archive is None or not archive.exists() or archive.stat().st_size == 0:
                    last_error = "download failed or empty"
                    continue
                self.log(f"Downloaded {archive.name} ({archive.stat().st_size // 1024} KB)")
                if _extract_to_game_folder(archive, target, name):
                    self.log(f"Fix applied for {name} → {target}")
                    return
                last_error = "extraction failed"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
        raise FourUFourFreeError(f"Could not apply fix: {last_error}")

    # ── mainloop ──────────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    """Launch the Qt interface, retaining Tk as a dependency fallback."""
    try:
        from .gui_qt import main as qt_main
    except ImportError:
        qt_main = None
    if qt_main is not None:
        return qt_main()

    root = tk.Tk()
    try:
        StoreApp(root).run()
    except FourUFourFreeError as exc:
        root.withdraw()
        messagebox.showerror("4u4free", str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
