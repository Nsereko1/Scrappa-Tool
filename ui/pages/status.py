# ui/pages/status.py
import customtkinter as ctk

class StatusPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Collection Run Status",
                     font=ctk.CTkFont(size=22, weight="bold")
                     ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        self.log = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=12))
        self.log.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="nsew")

        self.status_label = ctk.CTkLabel(self, text="Idle", anchor="w")
        self.status_label.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="ew")

        self.after(200, self._poll_log)

    def _poll_log(self):
        # In production, read from the same queue the orchestrator writes to.
        # Here: placeholder for the wiring point.
        self.after(200, self._poll_log)

    def append_log(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")