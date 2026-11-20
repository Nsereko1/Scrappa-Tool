import customtkinter as ctk
import tkinter as tk
import requests
import threading
import webbrowser

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

API = "http://localhost:8000"

SHOP_COLORS = {
    "amazon": ("#ff9900", "#ffffff"),
    "jumia": ("#f68b1e", "#ffffff"),
    "alibaba": ("#ff6a00", "#ffffff"),
    "ebay": ("#0064d2", "#ffffff"),
    "kibuga": ("#4CAF50", "#ffffff"),
    "default": ("#607d8b", "#ffffff")
}

class PriceHistoryDialog(ctk.CTkToplevel):
    def __init__(self, master, sku, title, app):
        super().__init__(master)
        self.app = app
        self.title("Price Movement Graph")
        self.geometry("600x400")
        self.resizable(False, False)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() // 2) - 300
        y = master.winfo_rooty() + (master.winfo_height() // 2) - 200
        self.geometry(f"+{x}+{y}")
        self.grab_set()

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14, weight="bold"), wraplength=550).pack(pady=(15, 5))
        self.chart_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.fig = Figure(figsize=(6, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(expand=True, fill="both")
        self.status = ctk.CTkLabel(self, text="Loading data...", text_color="gray")
        self.status.pack(pady=5)
        self.fetch_data(sku)

    def fetch_data(self, sku):
        threading.Thread(target=self._fetch_worker, args=(sku,), daemon=True).start()

    def _fetch_worker(self, sku):
        try:
            resp = requests.get(f"{API}/price_history", params={"sku": sku}, timeout=10)
            resp.raise_for_status()
            self.app.submit_result(self._render, resp.json())
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_error(self, msg):
        self.status.configure(text=f"Error: {msg}", text_color="red")

    def _render(self, data):
        self.status.pack_forget()
        self.ax.clear()
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2b2b2b", "white") if is_dark else ("#ffffff", "black")
        self.fig.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)

        if not data:
            self.ax.text(0.5, 0.5, "No price history recorded yet.", ha="center", va="center", color=fg, transform=self.ax.transAxes)
        else:
            timestamps = [r["timestamp"][11:16] for r in data]
            prices = [r["price_usd"] for r in data]
            self.ax.plot(timestamps, prices, marker="o", color="#1f77b4", linewidth=2, markersize=6)
            self.ax.set_title("Price Trend (USD)", color=fg)
            self.ax.tick_params(colors=fg)
            for spine in self.ax.spines.values(): spine.set_color(fg)
            self.fig.tight_layout()
        self.canvas.draw()

class PriceCompareDialog(ctk.CTkToplevel):
    def __init__(self, master, title, app, target_url=""):
        super().__init__(master)
        self.app = app
        self.title_text = title
        self.target_url = target_url
        self.target_platform = "" # Set by parent after init
        self._currency = "USD"
        
        self.title("Competitor Price Matrix")
        self.geometry("900x760")
        self.resizable(False, False)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() // 2) - 450
        y = master.winfo_rooty() + (master.winfo_height() // 2) - 380
        self.geometry(f"+{x}+{y}")
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 5))
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=17, weight="bold"), wraplength=850, justify="left").pack(anchor="w")
        ctk.CTkLabel(header, text="Compare market prices, sellers and competing products", font=ctk.CTkFont(size=12), text_color="gray").pack(anchor="w", pady=(4, 0))

        self.controls = ctk.CTkFrame(self, fg_color="transparent")
        self.controls.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(self.controls, text="Group:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.group_var = ctk.StringVar(value="Shop")
        ctk.CTkOptionMenu(self.controls, values=["Shop", "Price Only"], variable=self.group_var, command=lambda _: self._rerender()).pack(side="left", padx=(5, 15))

        ctk.CTkLabel(self.controls, text="Sort:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.sort_var = ctk.StringVar(value="Lowest Price")
        ctk.CTkOptionMenu(self.controls, values=["Lowest Price", "Highest Price", "Shop (A-Z)"], variable=self.sort_var, command=lambda _: self._rerender()).pack(side="left", padx=5)

        self.cur_var = ctk.StringVar(value="USD")
        ctk.CTkOptionMenu(self.controls, values=["USD", "UGX"], variable=self.cur_var, command=self._switch_currency, width=80).pack(side="right")

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=5)

        self.canvas = tk.Canvas(self.container, bg="#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff", highlightthickness=0)
        self.scrollbar = ctk.CTkScrollbar(self.container, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        self.content_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        self.status = ctk.CTkLabel(self, text="Fetching price matrix...", text_color="gray")
        self.status.pack(pady=10)
        self.fetch_data()

    def _on_frame_configure(self, event=None): self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    def _on_canvas_configure(self, event): self.canvas.itemconfig(self.canvas_window, width=event.width)
    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0: self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0: self.canvas.yview_scroll(1, "units")
    def destroy(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")
        super().destroy()

    def fetch_data(self):
        self.status.configure(text="Fetching price matrix...", text_color="gray")
        self.status.pack()
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            resp = requests.get(f"{API}/compare/specific", params={"title": self.title_text}, timeout=20)
            resp.raise_for_status()
            self.app.submit_result(self._render, resp.json())
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_error(self, msg):
        self.status.configure(text=f"Error: {msg}", text_color="red")

    def _rerender(self):
        if hasattr(self, "_cached_data"): self._render(self._cached_data)

    def _switch_currency(self, choice):
        self._currency = choice
        self._rerender()

    def format_price(self, price_usd):
        if price_usd is None: return "N/A"
        cur = getattr(self, "_currency", "USD")
        if cur == "UGX":
            try: rate = requests.get(f"{API}/currency", timeout=2).json()["rates"].get("UGX", 3800)
            except: rate = 3800
            return f"UGX {price_usd * rate:,.0f}"
        return f"${price_usd:,.2f}"

    def clear_content(self):
        for widget in self.content_frame.winfo_children(): widget.destroy()

    def _render(self, data):
        self.status.pack_forget()
        self._cached_data = data
        self.clear_content()

        if not data or "exact_matches" not in data:
            self.status.configure(text="No data found.")
            return

        items = data["exact_matches"]
        summary = data["summary"]

        if not items:
            ctk.CTkLabel(self.content_frame, text="No similar products found.", text_color="gray").pack(pady=30)
            return

        sum_frame = ctk.CTkFrame(self.content_frame, fg_color="#f3e8ff", corner_radius=10)
        sum_frame.pack(fill="x", pady=(5, 15))
        left = ctk.CTkFrame(sum_frame, fg_color="transparent")
        left.pack(side="left", padx=15, pady=15)
        ctk.CTkLabel(left, text="Lowest Price:", text_color="#5b21b6", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(left, text=self.format_price(summary.get('lowest')), text_color="#4c1d95", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=5)
        
        if summary.get("cheapest_url") and summary["cheapest_url"].startswith("http"):
            plat = str(summary.get("cheapest_platform")).upper()
            ctk.CTkButton(sum_frame, text=f"Open {plat} →", width=120, height=28, fg_color="#16a34a", hover_color="#15803d", command=lambda u=summary["cheapest_url"]: webbrowser.open(u)).pack(side="right", padx=15)

        sort_mode = self.sort_var.get()
        group_mode = self.group_var.get()
        
        # Strict match by URL, with fallback to Platform
        target_found = False
        if self.target_url:
            for item in items:
                if item.get("url") == self.target_url:
                    item["_is_target"] = True
                    target_found = True
                    break
        
        if not target_found and self.target_platform:
            for item in items:
                if item.get("platform", "").lower() == self.target_platform.lower():
                    item["_is_target"] = True
                    target_found = True
                    break

        # Ensure all others are False
        for item in items:
            if "_is_target" not in item:
                item["_is_target"] = False

        if sort_mode == "Lowest Price": items.sort(key=lambda x: (not x["_is_target"], x["price_usd"]))
        elif sort_mode == "Highest Price": items.sort(key=lambda x: (not x["_is_target"], -x["price_usd"]))
        elif sort_mode == "Shop (A-Z)": items.sort(key=lambda x: (not x["_is_target"], x["platform"], x["price_usd"]))

        def render_card(it):
            is_dark = ctk.get_appearance_mode() == "Dark"
            default_bg = "#242424" if is_dark else "#ffffff"
            hover_bg = "#333333" if is_dark else "#f0f0f0"

            card = ctk.CTkFrame(self.content_frame, fg_color=default_bg, corner_radius=8)
            card.pack(fill="x", pady=2)
            
            if it.get("_is_target"):
                card.configure(border_width=2, border_color="#8b5cf6")
                ctk.CTkLabel(card, text="[YOUR ITEM]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#8b5cf6").pack(side="left", padx=10)
            
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            
            plat_key = it["platform"].lower()
            bg_c, text_c = SHOP_COLORS.get(plat_key, SHOP_COLORS["default"])
            tag = ctk.CTkLabel(info, text=plat_key.upper(), font=ctk.CTkFont(size=10, weight="bold"), fg_color=bg_c, text_color=text_c, corner_radius=4, height=20)
            tag.pack(side="left", padx=(0, 10))
            
            ctk.CTkLabel(info, text=it["title"], font=ctk.CTkFont(size=12), anchor="w", wraplength=450, justify="left").pack(side="left")

            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=10)
            ctk.CTkLabel(right, text=self.format_price(it["price_usd"]), font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=10)
            
            if it.get("url"):
                ctk.CTkButton(right, text="View", width=60, height=26, command=lambda u=it["url"]: webbrowser.open(u)).pack(side="left", padx=5)
            if it.get("sku"):
                ctk.CTkButton(right, text="History", width=60, height=26, fg_color="#9467bd", hover_color="#7a5299", command=lambda s=it["sku"], t=it["title"]: PriceHistoryDialog(self, s, t, self.app)).pack(side="left", padx=5)

            def on_enter(e): card.configure(fg_color=hover_bg)
            def on_leave(e): card.configure(fg_color=default_bg)
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
            info.bind("<Enter>", on_enter)
            info.bind("<Leave>", on_leave)
            for child in info.winfo_children():
                child.bind("<Enter>", on_enter)
                child.bind("<Leave>", on_leave)
            for child in right.winfo_children():
                child.bind("<Enter>", on_enter)
                child.bind("<Leave>", on_leave)

        if group_mode == "Price Only":
            for it in items: render_card(it)
        else:
            platform_groups = {}
            for it in items:
                plat = it["platform"].upper()
                if plat not in platform_groups: platform_groups[plat] = []
                platform_groups[plat].append(it)

            sorted_groups = sorted(platform_groups.items(), key=lambda x: min(i["price_usd"] for i in x[1]))

            for plat, plat_items in sorted_groups:
                hdr = ctk.CTkFrame(self.content_frame, fg_color=("gray80", "gray25"), corner_radius=6)
                hdr.pack(fill="x", pady=(10, 2))
                avg_p = sum(i["price_usd"] for i in plat_items) / len(plat_items)
                ctk.CTkLabel(hdr, text=f"{plat} ({len(plat_items)} listings) - Avg: {self.format_price(avg_p)}", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=15, pady=8)
                
                for it in plat_items: render_card(it)