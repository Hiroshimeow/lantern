
import urllib.parse


class MediaRoutes:
    def api_folder_preview(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_dir():
            self.send_json(404, {"error": "folder not found"}); return
        self.send_bytes(200, self.app.files.json_dumps({"ok": True, "items": self.app.media.folder_preview_items(target)}).encode("utf-8"),
                        "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def api_video_info(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        target = self.app.files.safe_join("/" + rel)
        if not target.is_file() or self.app.files.classify(target) != "video":
            self.send_json(404, {"error": "video not found"}); return
        self.send_json(200, self.app.media.video_info(target))

    def api_subtitle(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        try:
            idx = max(0, min(int(qs.get("i", ["0"])[0] or 0), 50))
        except Exception:
            idx = 0
        video = self.app.files.safe_join("/" + rel)
        if not video.is_file() or self.app.files.classify(video) != "video":
            self.send_error(404, "video not found"); return
        subs = self.app.media.video_subtitle_sidecars(video)
        if idx >= len(subs):
            self.send_error(404, "subtitle not found"); return
        try:
            body = self.app.media.subtitle_to_vtt(subs[idx]).encode("utf-8", "replace")
        except Exception as e:
            self.send_error(500, f"subtitle error: {e}"); return
        self.send_bytes(200, body, "text/vtt; charset=utf-8")

    def api_thumb(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_file():
            self.send_error(404, "thumb target not found"); return
        kind = self.app.files.classify(target)
        dst = self.app.media.thumb_cache_path(target, kind)
        if not dst.exists():
            ok = False
            if kind == "image": ok = self.app.media.make_image_thumb(target, dst)
            elif kind == "video": ok = self.app.media.make_video_thumb(target, dst)
            if not ok:
                self.send_error(404, "thumbnail unavailable"); return
        self.serve_static_file(dst, download=False, ctype="image/jpeg", cache_control="no-cache")
