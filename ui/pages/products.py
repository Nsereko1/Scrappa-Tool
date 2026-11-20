import threading
import time
from tkinter import ttk
import customtkinter as ctk
import requests

from ui.pages.compare_dialog import PriceCompareDialog

API = "http://localhost:8000"

SORT_MAP = {
    "Last Scraped": "last",
    "Most Common": "common",
    "Highest Price": "price",
    "New Arrivals": "new",
    "Price Drops": "drops",
}

_DEFAULT = [
    ("platform", "Platform", 110, "center"),
    ("title", "Title", 400, "w"),
    ("price_usd", "Price (USD)", 100, "e"),
    ("previous_price_usd", "Prev Price", 100, "e"),
]


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


class AutoScanDialog(ctk.CTkToplevel):
    def __init__(self, master, callback, current_platform):
        super().__init__(master)
        self.callback = callback
        self.title("Auto Scan")
        self.geometry("460x520")
        self.resizable(False, False)
        self.grab_set()

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() // 2) - 230
        y = master.winfo_rooty() + (master.winfo_height() // 2) - 260
        self.geometry(f"+{x}+{y}")

        ctk.CTkLabel(self, text="Configure Scan", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self, text="Scrape only specific products across selected brands", font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 16))

        ctk.CTkLabel(self, text="Platform", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=30)
        self.platform_var = ctk.StringVar(value=(current_platform or "All").capitalize())
        ctk.CTkOptionMenu(self, values=["All", "Jumia", "Amazon", "Alibaba", "Ebay", "Kibuga"], variable=self.platform_var, width=400).pack(padx=30, pady=(4, 14))

        ctk.CTkLabel(self, text="Category", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=30)
        
        self._cat_labels = [
            "All Categories", "Phones & Tablets", "Laptops & Computers",
            "TVs & Audio", "Headphones & Audio", "Fashion & Clothing",
            "Shoes & Footwear", "Home & Kitchen", "Appliances",
            "Beauty & Health", "Gaming", "Accessories", "Power & Chargers",
        ]
        self._cat_keys = {l: l.lower().replace(" & ", "_").replace(" ", "_") for l in self._cat_labels}
        self._cat_keys["All Categories"] = "all"

        try:
            import requests as _r
            cats = _r.get("http://localhost:8000/categories", timeout=2).json()
            if cats:
                self._cat_labels = [c["label"] for c in cats]
                self._cat_keys = {c["label"]: c["key"] for c in cats}
        except Exception:
            pass

        self.category_var = ctk.StringVar(value="All Categories")
        ctk.CTkOptionMenu(self, values=self._cat_labels, variable=self.category_var, width=400).pack(padx=30, pady=(4, 14))

        ctk.CTkLabel(self, text="Search Filter (optional)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=30)
        ctk.CTkLabel(self, text='e.g. "macbook pro", "iphone 14", "hisense tv", "nike air"', font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=30, pady=(0, 4))

        self.query_entry = ctk.CTkEntry(self, width=400, placeholder_text="leave blank to scrape everything in the category")
        self.query_entry.pack(padx=30, pady=(0, 14))

        ctk.CTkLabel(self, text="Max items", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=30)
        self.limit_entry = ctk.CTkEntry(self, width=400)
        self.limit_entry.insert(0, "500")
        self.limit_entry.pack(padx=30, pady=(4, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        ctk.CTkButton(btn_frame, text="Cancel", width=150, fg_color="gray40", hover_color="gray30", command=self.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Start Scan", width=150, fg_color="#1f538d", hover_color="#14375e", command=self.start).pack(side="left", padx=10)

    def start(self):
        platform = self.platform_var.get().lower() or "all"
        if platform == "ebay": platform = "ebay"
        category = self._cat_keys.get(self.category_var.get(), "all")
        query = self.query_entry.get().strip() or None
        try: limit = int(self.limit_entry.get().strip() or "500")
        except ValueError: limit = 500
        self.destroy()
        self.callback(platform, category, limit, query)


class ProductsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self._req_id = 0
        self._last_hover_item = None
        self.platform_vars = {}
        self.item_titles = {}
        self.item_urls = {}
        self.current_platform_name = "All"
        self.filter_buttons = {}

        # HEADER
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        self.title_label = ctk.CTkLabel(header, text="Scraped Products: All", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(side="left")

        # === INSIGHTS DASHBOARD ===
        self.insights_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.insights_frame.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")
        self.insights_frame.grid_columnconfigure(1, weight=1)

        # 1. Total Box
        self.total_box = ctk.CTkFrame(self.insights_frame, corner_radius=10, fg_color=("gray85", "gray20"))
        self.total_box.grid(row=0, column=0, sticky="ns", padx=(0, 20))
        ctk.CTkLabel(self.total_box, text="TOTAL ITEMS", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(padx=25, pady=(18, 0))
        self.total_label = ctk.CTkLabel(self.total_box, text="0", font=ctk.CTkFont(size=32, weight="bold"))
        self.total_label.pack(padx=25, pady=(0, 18))

        # 2. Shops Row
        self.shops_frame = ctk.CTkFrame(self.insights_frame, fg_color="transparent")
        self.shops_frame.grid(row=0, column=1, sticky="ew")
        
        for i in range(5):
            self.shops_frame.grid_columnconfigure(i, weight=1)

        # CONTROL ROW
        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        self.auto_scan_btn = ctk.CTkButton(ctrl, text="Start Auto-Scan", fg_color="#c62828", hover_color="#b71c1c", command=self.open_scan_dialog, width=120)
        self.auto_scan_btn.pack(side="left", padx=(10, 20), pady=10)

        ctk.CTkLabel(ctrl, text="View:").pack(side="left", padx=(10, 2))
        self.sort_var = ctk.StringVar(value="Last Scraped")
        ctk.CTkOptionMenu(ctrl, values=list(SORT_MAP), variable=self.sort_var, command=lambda _e: self.reset_and_fetch()).pack(side="left", padx=(0, 10))

        # QUICK FILTERS
        adv_filter_frame = ctk.CTkFrame(self)
        adv_filter_frame.grid(row=3, column=0, padx=16, pady=(0, 5), sticky="ew")
        self.active_filter = ctk.StringVar(value="all")
        filters = [("All", "all"), ("In Stock", "instock"), ("Highest", "highest"), ("Higher Than Average", "higher"), ("Average", "average"), ("Lower Than Average", "lower"), ("Lowest", "lowest")]
        for label, val in filters:
            is_active = (val == "all")
            btn = ctk.CTkButton(adv_filter_frame, text=label, width=100, height=28, corner_radius=14, fg_color="#1f538d" if is_active else "transparent", border_width=1, border_color="#1f538d", text_color="white" if is_active else ("gray10", "gray90"), command=lambda v=val: self.apply_quick_filter(v))
            btn.pack(side="left", padx=5, pady=5)
            self.filter_buttons[val] = btn

        # PLATFORM FILTERS
        filter_frame = ctk.CTkFrame(self)
        filter_frame.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(filter_frame, text="Filter by:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 15), pady=10)
        for p in ["jumia", "amazon", "alibaba", "ebay", "kibuga"]:
            var = ctk.BooleanVar(value=True)
            self.platform_vars[p] = var
            ctk.CTkCheckBox(filter_frame, text=p.capitalize(), variable=var, command=self.reset_and_fetch).pack(side="left", padx=5)

        self.search_entry = ctk.CTkEntry(filter_frame, placeholder_text="Search items...", width=200)
        self.search_entry.pack(side="right", padx=15, pady=10)
        self.search_entry.bind("<KeyRelease>", self._on_search_typing)
        self.search_timer = None

        # PRODUCTS TABLE
        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=5, column=0, padx=16, pady=(0, 8), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self._apply_tree_style()
        self.tree = ttk.Treeview(table_frame, style="Scrapa.Treeview", show="headings", selectmode="browse")
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._on_leave)
        self.tree.bind("<Double-1>", self._on_double_click)

        self.scrollbar = ctk.CTkScrollbar(table_frame, command=self._on_scrollbar)
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.tree.bind("<MouseWheel>", self._on_mousewheel)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)

        # BOTTOM STATUS BAR
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=6, column=0, padx=16, pady=(0, 12), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(bottom_frame, width=200, progress_color="#1f538d")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(bottom_frame, text="0% (0/0)", width=120, anchor="w", font=ctk.CTkFont(weight="bold"))

        self.status_label = ctk.CTkLabel(bottom_frame, text="Ready", anchor="w", text_color="gray")
        self.status_label.pack(side="left", fill="x", expand=True)

        self.tree.configure(columns=tuple(c[0] for c in _DEFAULT), displaycolumns=tuple(c[0] for c in _DEFAULT))
        for cid, text, width, anchor in _DEFAULT:
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=width, anchor=anchor, stretch=(cid == "title"))

        # Initial Fetch
        self.build_insights()
        self.reset_and_fetch()

    # ==============================
    # DASHBOARD & INSIGHTS
    # ==============================
    def build_insights(self):
        if not hasattr(self, "_insights_req_id"):
            self._insights_req_id = 0
        self._insights_req_id += 1
        self.update_insights(self._insights_req_id)

    def update_insights(self, req_id):
        threading.Thread(target=self._insights_worker, args=(req_id,), daemon=True).start()

    def _insights_worker(self, req_id):
        try:
            r = requests.get("http://localhost:8000/analytics", timeout=10)
            data = r.json()
            self.app.submit_result(lambda d: self._render_insights(d, req_id), data)
        except Exception:
            pass

    def _render_insights(self, data, req_id):
        if getattr(self, "_insights_req_id", None) != req_id:
            return

        platforms = data.get("platforms", [])
        total = sum(p.get("count", 0) for p in platforms)
        self.total_label.configure(text=f"{total:,}")

        for widget in self.shops_frame.winfo_children():
            widget.destroy()

        brand_colors = {
            "jumia":   "#F57C00", "amazon":  "#FF9900", "alibaba": "#FF6A00", 
            "ebay":    "#1976D2", "kibuga":  "#4CAF50", 
        }

        found_counts = {p.get("platform", "").lower(): p.get("count", 0) for p in platforms}

        for i, plat in enumerate(["jumia", "amazon", "alibaba", "ebay", "kibuga"]):
            count = found_counts.get(plat, 0)
            color = brand_colors.get(plat, "gray50")

            box = ctk.CTkFrame(self.shops_frame, corner_radius=8, fg_color=("gray85", "gray20"))
            box.grid(row=0, column=i, sticky="nsew", padx=5)
            box.grid_columnconfigure(0, weight=1)

            header = ctk.CTkFrame(box, height=4, width=40, fg_color=color, corner_radius=2)
            header.grid(row=0, column=0, pady=(15, 5))
            header.grid_propagate(False)

            ctk.CTkLabel(box, text=plat.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color="gray").grid(row=1, column=0)
            ctk.CTkLabel(box, text=f"{count:,}", font=ctk.CTkFont(size=18, weight="bold")).grid(row=2, column=0, pady=(0, 15))

    # ==============================
    # GENERAL UI
    # ==============================
    def apply_quick_filter(self, filter_val):
        self.active_filter.set(filter_val)
        for val, btn in self.filter_buttons.items():
            if val == filter_val:
                btn.configure(fg_color="#1f538d", text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        self.build_insights()
        self.reset_and_fetch()

    def _on_search_typing(self, event):
        if self.search_timer: self.after_cancel(self.search_timer)
        self.search_timer = self.after(500, self.reset_and_fetch)

    def open_scan_dialog(self):
        current = getattr(self, "_platform_filter", "all")
        AutoScanDialog(self, self._run_auto_scan, current)

    def _run_auto_scan(self, platform, category, target_limit, query=None):
        params = {"platform": platform, "target_limit": target_limit, "category": category, "region": "NG"}
        if query: params["query"] = query
        try:
            resp = requests.post(f"{API}/start_auto_scan", params=params, timeout=10)
            if resp.json().get("status") == "started":
                self.show_progress()
                self.progress_bar.set(0)
                self.progress_label.configure(text="0% (0/0)")
                self.poll_scan_status()
        except Exception as e:
            print(f"[UI] scan failed: {e}", flush=True)

    def show_progress(self):
        if not getattr(self, "_progress_visible", False):
            self._progress_visible = True
            self.progress_bar.pack(fill="x", padx=10, pady=(5, 0))
            self.progress_label.pack(side="bottom", pady=(0, 5))

    def hide_progress(self):
        if getattr(self, "_progress_visible", False):
            self._progress_visible = False
            self.progress_bar.pack_forget()
            self.progress_label.pack_forget()
        
        # THE FIX: Force the dashboard and table to refresh after the scan finishes
        self.build_insights()
        self.reset_and_fetch()

    def poll_scan_status(self):
        try:
            s = requests.get(f"{API}/scan_status", timeout=3).json()
            if s.get("is_running"):
                self.show_progress()
                target = max(1, s.get("target", 1))
                scraped = s.get("total_scraped", 0)
                pct = min(1.0, scraped / target)
                self.progress_bar.set(pct)
                self.progress_label.configure(text=f"{int(pct*100)}% ({scraped}/{target})")
                self.after(1000, self.poll_scan_status)
            else:
                if getattr(self, "_progress_visible", False):
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Done!")
                    # Wait 2 seconds before hiding the progress bar so the DB can finish saving
                    self.after(2000, self.hide_progress)
        except Exception:
            pass

    def reset_and_fetch(self):
        self._req_id += 1
        req_id = self._req_id
        selected = [p for p, var in self.platform_vars.items() if var.get()]
        if not selected:
            self.status_label.configure(text="No platforms selected.", text_color="orange")
            return

        platform_str = ",".join(selected)
        self.current_platform_name = selected[0].capitalize() if len(selected) == 1 else "All"
        self.update_insights(req_id)

        search_term = self.search_entry.get().strip()
        quick_filter = self.active_filter.get()

        threading.Thread(target=self._fetch_worker, args=(req_id, self.sort_var.get(), platform_str, search_term, quick_filter, 0), daemon=True).start()

    def _fetch_worker(self, req_id, sort_label, platform_str, search_term, quick_filter, offset):
        try:
            params = {"platform": platform_str, "sort_by": SORT_MAP[sort_label], "limit": 500, "offset": offset, "quick_filter": quick_filter}
            if search_term: params["search"] = search_term
            resp = requests.get(f"{API}/products", params=params, timeout=15)
            self.app.submit_result(self._render_table, (req_id, sort_label, resp.json()))
        except Exception as e:
            self.app.submit_result(self._render_error, (req_id, str(e)))

    def _render_table(self, payload):
        req_id, sort_label, data = payload
        if req_id != self._req_id: return

        items = data.get("items", [])
        total = data.get("total", 0)
        self.tree.delete(*self.tree.get_children())
        self.item_titles.clear()
        self.item_urls.clear()

        for i, row in enumerate(items):
            original_title = row.get("title", "")
            title = "   " + (original_title[:60] + "..." if len(original_title) > 60 else original_title)
            prev_price = _money(row.get("previous_price_usd")) if row.get("previous_price_usd") and row.get("previous_price_usd") != row.get("price_usd") else "—"
            tag = "odd" if i % 2 else "even"
            item_id = self.tree.insert("", "end", values=(row.get("platform", "").upper(), title, _money(row.get("price_usd")), prev_price), tags=(tag,))
            
            self.item_titles[item_id] = original_title
            self.item_urls[item_id] = row.get("url", "")

        self.status_label.configure(text=f"Found {total:,} items.", text_color="gray")

    def _render_error(self, payload):
        req_id, msg = payload
        if req_id == self._req_id:
            self.status_label.configure(text=f"Error: {msg}", text_color="red")

    def _on_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        
        title = self.item_titles.get(item_id)
        url = self.item_urls.get(item_id, "")
        
        vals = self.tree.item(item_id, "values")
        plat = vals[0].lower() if vals else ""
        
        if not title: return
        
        dlg = PriceCompareDialog(self, title, self.app, url)
        dlg.target_platform = plat

    def _on_scrollbar(self, *args): self.tree.yview(*args)
    def _on_mousewheel(self, event): self.tree.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item != self._last_hover_item:
            if self._last_hover_item and self.tree.exists(self._last_hover_item):
                self.tree.item(self._last_hover_item, tags=("odd" if self.tree.index(self._last_hover_item) % 2 else "even"))
            if item: self.tree.item(item, tags=("hover",))
            self._last_hover_item = item

    def _on_leave(self, event):
        if self._last_hover_item and self.tree.exists(self._last_hover_item):
            self.tree.item(self._last_hover_item, tags=("odd" if self.tree.index(self._last_hover_item) % 2 else "even"))
            self._last_hover_item = None

    def _apply_tree_style(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2b2b2b", "#dce4ee") if dark else ("#ffffff", "#1a1a1a")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Scrapa.Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=32, borderwidth=0, font=("Helvetica", 12))
        style.configure("Scrapa.Treeview.Heading", background="#1f538d", foreground="white", relief="flat", font=("Helvetica", 12, "bold"))
        style.map("Scrapa.Treeview", background=[("selected", "#1f538d")], foreground=[("selected", "white")])
        if hasattr(self, "tree"):
            self.tree.tag_configure("odd", background="#333333" if dark else "#f2f5fa")
            self.tree.tag_configure("even", background=bg)
            self.tree.tag_configure("hover", background="#4a4a4a" if dark else "#e0e8f5")

    def set_platform_filter(self, platform):
        if platform == "All":
            for var in self.platform_vars.values(): var.set(True)
        else:
            for p, var in self.platform_vars.items(): var.set(p == platform.lower())
        self.current_platform_name = platform
        self.reset_and_fetch()