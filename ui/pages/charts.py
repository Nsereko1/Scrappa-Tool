import json
import threading

import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import requests

API = "http://localhost:8000"


class ChartsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._loading = False

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        ctk.CTkLabel(header, text="Market Intelligence Analytics",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        self.days_var = ctk.StringVar(value="30")
        ctk.CTkOptionMenu(header, values=["7", "14", "30", "90"],
                          variable=self.days_var, width=80,
                          command=lambda _: self.fetch_analytics()).pack(side="right", padx=6)

        self.refresh_btn = ctk.CTkButton(header, text="Refresh Charts",
                                         command=self.fetch_analytics)
        self.refresh_btn.pack(side="right")

        self.chart_frame = ctk.CTkFrame(self)
        self.chart_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")

        self.fig = Figure(figsize=(11, 6), dpi=100, layout="constrained")
        gs = self.fig.add_gridspec(2, 2, height_ratios=[1.4, 1])
        self.ax_trend = self.fig.add_subplot(gs[0, :])
        self.ax_bar_plat = self.fig.add_subplot(gs[1, 0])
        self.ax_bar_top = self.fig.add_subplot(gs[1, 1])

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(expand=True, fill="both", padx=10, pady=10)

    def fetch_analytics(self):
        if self._loading:
            return
        self._loading = True
        self.refresh_btn.configure(state="disabled", text="Loading...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            days = int(self.days_var.get())
            analytics = requests.get(f"{API}/analytics", timeout=10).json()
            trends = requests.get(f"{API}/trends?days={days}", timeout=10).json()
            self.app.submit_result(self._render_charts,
                                   {"analytics": analytics, "trends": trends})
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_error(self, msg):
        self._loading = False
        self.refresh_btn.configure(state="normal", text="Refresh Charts")
        for ax in (self.ax_trend, self.ax_bar_plat, self.ax_bar_top):
            ax.clear()
        self.ax_trend.text(0.5, 0.5, f"Error: {msg}", ha="center", va="center", color="red")
        self.canvas.draw_idle()

    def _render_charts(self, payload):
        self._loading = False
        self.refresh_btn.configure(state="normal", text="Refresh Charts")
        analytics = payload["analytics"]
        trends = payload["trends"]
        days = int(self.days_var.get())

        dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if dark else "#ffffff"
        fg = "white" if dark else "black"

        self.fig.patch.set_facecolor(bg)
        for ax in (self.ax_trend, self.ax_bar_plat, self.ax_bar_top):
            ax.clear()
            ax.set_facecolor(bg)
            ax.tick_params(colors=fg)
            for spine in ax.spines.values():
                spine.set_color(fg)

        if trends:
            by_plat = {}
            for row in trends:
                plat = row["platform"].capitalize()
                by_plat.setdefault(plat, {"dates": [], "prices": []})
                by_plat[plat]["dates"].append(row["date"])
                by_plat[plat]["prices"].append(row["avg_price"])
            palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
            for i, (p, d) in enumerate(by_plat.items()):
                self.ax_trend.plot(d["dates"], d["prices"], marker="o",
                                   linewidth=2, markersize=4, label=p,
                                   color=palette[i % len(palette)])
            self.ax_trend.set_title(f"Average Price per Platform (last {days} days)", color=fg)
            self.ax_trend.set_ylabel("Avg Price (USD)", color=fg)
            self.ax_trend.tick_params(axis="x", rotation=30)
            legend = self.ax_trend.legend(loc="upper right", fontsize=8)
            for text in legend.get_texts():
                text.set_color(fg)
        else:
            self.ax_trend.text(0.5, 0.5,
                "No trend data yet — run scans over multiple days.",
                ha="center", va="center", color=fg,
                transform=self.ax_trend.transAxes)

        platforms = [p["platform"].capitalize() for p in analytics.get("platforms", [])]
        counts = [p["count"] for p in analytics.get("platforms", [])]
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        if platforms:
            bars = self.ax_bar_plat.bar(platforms, counts,
                color=[palette[i % len(palette)] for i in range(len(platforms))])
            self.ax_bar_plat.set_title("Items Tracked per Platform", color=fg)
            for b in bars:
                h = b.get_height()
                self.ax_bar_plat.text(b.get_x() + b.get_width() / 2.0, h,
                                      f"{int(h)}", ha="center", va="bottom",
                                      color=fg, fontsize=9)

        items = [(i["title"][:18] + "...") if len(i["title"]) > 18 else i["title"]
                 for i in analytics.get("top_items", [])]
        item_counts = [i["count"] for i in analytics.get("top_items", [])]
        if items:
            items.reverse()
            item_counts.reverse()
            self.ax_bar_top.barh(items, item_counts, color="#9467bd")
            self.ax_bar_top.set_title("Top 5 Most Common Items", color=fg)

        self.canvas.draw_idle()
