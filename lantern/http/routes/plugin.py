
import urllib.parse


class PluginRoutes:
    def api_plugin_info(self) -> None:
        if self.app.plugin is None:
            self.send_json(200, {"ok": True, "enabled": False, "error": "plugin.py not loaded"})
            return
        try:
            info = self.app.plugin.info(self.app.files.plugin_config_path())
            info["enabled"] = True
            self.send_json(200, info)
        except Exception as e:
            self.send_json(500, {"error": str(e), "enabled": False})

    def api_plugin_preview(self, query: str) -> None:
        if self.app.plugin is None:
            self.send_error(404, "plugin.py not loaded")
            return
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        # parse_qs has already URL-decoded the query. safe_join expects a
        # URL path and splits literal ?/# before decoding; re-encode to keep
        # file names containing those characters intact (or percent signs).
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_file():
            self.send_error(404, "preview target not found")
            return
        pdf_text = target.suffix.lower() == ".pdf" and qs.get("view", [""])[0] == "text"
        # Native PDF preview only emits a small iframe page. Only explicit text
        # extraction needs a heavy parser slot.
        is_heavy = target.suffix.lower() in {".docx", ".xlsx", ".xlsm"} or pdf_text
        acquired = not is_heavy or self.app.heavy_preview_slots.acquire(blocking=False)
        if not acquired:
            self.send_error(503, "Preview is busy (max 2 concurrent heavy documents); retry shortly")
            return
        try:
            if pdf_text:
                body = self.app.plugin.render_preview_page(target, self.app.config.root, self.app.files.plugin_config_path(), self.app.config.title, pdf_text=True)
            else:
                # Source-line anchors enable normal Preview / Visual / Source navigation.
                # Explicit anchor_spike=0 retains the legacy output for diagnostics.
                include_anchors = (target.suffix.lower() in {".md", ".markdown"}
                                   and qs.get("anchor_spike", ["1"])[0] != "0")
                body = self.app.plugin.render_preview_page(
                    target, self.app.config.root, self.app.files.plugin_config_path(), self.app.config.title,
                    anchor_spike=include_anchors)
        except Exception as e:
            self.send_error(500, f"preview error: {e}")
            return
        finally:
            if is_heavy:
                self.app.heavy_preview_slots.release()
        self.send_bytes(200, body, "text/html; charset=utf-8")

    def api_plugin_extensions(self) -> None:
        if self.app.plugin is None:
            self.send_json(404, {"error": "plugin.py not loaded"})
            return
        data = self.read_json()
        try:
            if "add" in data:
                info = self.app.plugin.add_extension(self.app.files.plugin_config_path(), str(data.get("add") or ""))
            elif "remove" in data:
                info = self.app.plugin.remove_extension(self.app.files.plugin_config_path(), str(data.get("remove") or ""))
            else:
                info = self.app.plugin.info(self.app.files.plugin_config_path())
            info["enabled"] = True
            self.send_json(200, info)
        except Exception as e:
            self.send_json(400, {"error": str(e)})
