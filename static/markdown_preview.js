(() => {
  "use strict";
  window.opener = null;
  const appScript = document.currentScript;
  const nonce = appScript ? appScript.nonce : "";
  const fixedBar = document.querySelector('.bar.md-bar');
  if (fixedBar) {
    const syncHeight = () => {
      const height = Math.ceil(fixedBar.getBoundingClientRect().height) + 'px';
      if (document.documentElement.style.getPropertyValue('--md-bar-height') !== height)
        document.documentElement.style.setProperty('--md-bar-height', height);
    };
    syncHeight();
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(syncHeight).observe(fixedBar);
    else addEventListener('resize', syncHeight);
  }
  const diagramList = (root = document) =>
    Array.from(root.querySelectorAll(".mermaid-diagram")).slice(0, 24);
  const docName = (document.querySelector("[data-doc-name]")?.getAttribute("data-doc-name") || "document")
    .replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "") || "document";
  let pendingRenders = Promise.resolve();
  const yieldUi = () => new Promise((resolve) => setTimeout(resolve, 0));

  function slugifyHeadingText(rawText) {
    return String(rawText || "")
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s_-]/gu, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function stripVietnameseDiacritics(str) {
    return String(str || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");
  }

  function ensureHeadingIds(root = document) {
    const scope = root instanceof Element || root instanceof Document ? root : document;
    const article = scope.matches?.("article.md-preview") ? scope : (scope.querySelector?.("article.md-preview") || scope);
    const headings = Array.from(article.querySelectorAll("h1, h2, h3, h4, h5, h6"));
    const used = new Map();
    for (const h of headings) {
      const text = h.textContent || "";
      const baseSlug = slugifyHeadingText(text) || "section";
      const asciiSlug = slugifyHeadingText(stripVietnameseDiacritics(text)) || baseSlug;
      const count = used.get(baseSlug) || 0;
      used.set(baseSlug, count + 1);
      const finalId = count === 0 ? baseSlug : `${baseSlug}-${count}`;
      if (!h.id) h.id = finalId;
      h.setAttribute("data-slug", finalId);
      h.setAttribute("data-slug-ascii", count === 0 ? asciiSlug : `${asciiSlug}-${count}`);
    }
  }

  function findAnchorTarget(hash) {
    const raw = String(hash || "").replace(/^#/, "");
    if (!raw) return null;
    let decoded = raw;
    try { decoded = decodeURIComponent(raw); } catch (_) {}
    const direct = document.getElementById(decoded) || document.getElementById(raw);
    if (direct) return direct;
    ensureHeadingIds(document);
    const byId = document.getElementById(decoded) || document.getElementById(raw);
    if (byId) return byId;
    const norm = slugifyHeadingText(decoded);
    const normAscii = slugifyHeadingText(stripVietnameseDiacritics(decoded));
    const headings = Array.from(document.querySelectorAll("article.md-preview h1, article.md-preview h2, article.md-preview h3, article.md-preview h4, article.md-preview h5, article.md-preview h6"));
    return headings.find(h =>
      h.getAttribute("data-slug") === norm ||
      h.getAttribute("data-slug-ascii") === normAscii ||
      slugifyHeadingText(h.textContent) === norm ||
      slugifyHeadingText(stripVietnameseDiacritics(h.textContent)) === normAscii
    ) || null;
  }

  function loadMermaid(diagrams) {
    if (!diagrams.length) return Promise.resolve(null);
    if (window.mermaid) return Promise.resolve(window.mermaid);
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/static/vendor/mermaid-11.17.2.min.js";
      script.nonce = nonce;
      script.onload = () => resolve(window.mermaid || null);
      script.onerror = () => reject(new Error("Failed to load local Mermaid bundle"));
      document.head.appendChild(script);
    });
  }

  function initializeMermaid(runtime) {
    runtime.initialize({
      startOnLoad: false, securityLevel: "strict", suppressErrorRendering: true,
      theme: "base", htmlLabels: false, maxTextSize: 60000, maxEdges: 500,
      fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
      themeCSS: ".label{color:#111}.node rect,.node polygon,.node circle,.node ellipse{fill:#fff;stroke:#334155}.edgePath .path{stroke:#334155}",
      themeVariables: {
        background: "#ffffff", primaryColor: "#ffffff", primaryTextColor: "#111111",
        primaryBorderColor: "#334155", lineColor: "#334155", secondaryColor: "#f8fafc",
        tertiaryColor: "#f1f5f9", fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
      },
      flowchart: { htmlLabels: false },
      dompurifyConfig: {
        USE_PROFILES: { svg: true, svgFilters: true },
        FORBID_TAGS: ["foreignObject", "iframe", "script", "style"],
        FORBID_ATTR: ["onerror", "onload", "onclick"]
      },
      secure: ["secure","securityLevel","startOnLoad","suppressErrorRendering","maxTextSize","maxEdges",
        "theme","themeCSS","themeVariables","fontFamily","htmlLabels","dompurifyConfig"]
    });
  }

  async function renderOne(runtime, wrapper, index) {
    const source = wrapper.querySelector(".mermaid-source")?.textContent || "";
    const output = wrapper.querySelector(".mermaid-output");
    const button = wrapper.querySelector('[data-action="png"]');
    if (!output) return;
    if (source.length > 60000) { output.textContent = "Diagram is too large to render."; return; }
    const temp = document.createElement("div");
    temp.style.position = "fixed";
    temp.style.left = "-100000px";
    temp.style.top = "0";
    temp.style.width = "1200px";
    temp.style.visibility = "hidden";
    temp.style.pointerEvents = "none";
    document.body.appendChild(temp);
    try {
      // Warm the parser/diagram registry in its own task so the governed render task stays bounded.
      await runtime.parse(source);
      await yieldUi();
      const result = await runtime.render(`lantern-mermaid-${index}`, source, temp);
      // Keep Mermaid generation and DOM insertion as separate browser tasks.
      await yieldUi();
      output.innerHTML = result.svg;
      result.bindFunctions?.(output);
      wrapper.classList.add("mermaid-ok");
      wrapper.querySelector(".mermaid-source")?.setAttribute("hidden", "");
      if (button) button.hidden = false;
    } catch (error) {
      output.textContent = `Mermaid render failed: ${error instanceof Error ? error.message : String(error)}`;
    } finally { temp.remove(); }
  }

  async function renderAll(root = document) {
    ensureHeadingIds(root);
    const diagrams = diagramList(root);
    if (!diagrams.length) return;
    const runtime = await loadMermaid(diagrams);
    if (!runtime) throw new Error("Local Mermaid runtime unavailable");
    // script.onload resolves in the same task that parses/evaluates the large bundle.
    // Yield before initialize/render so first-load cost is not compounded with rendering.
    await yieldUi();
    initializeMermaid(runtime);
    await yieldUi();
    for (let i = 0; i < diagrams.length; i += 1) {
      await renderOne(runtime, diagrams[i], i + 1);
      await yieldUi();
    }
  }

  function svgDimensions(svg) {
    const viewBox = svg.viewBox?.baseVal;
    let width = viewBox?.width || Number.parseFloat(svg.getAttribute("width") || "");
    let height = viewBox?.height || Number.parseFloat(svg.getAttribute("height") || "");
    if (!(width > 0 && height > 0)) {
      const box = svg.getBoundingClientRect(); width = box.width; height = box.height;
    }
    if (!(width > 0 && height > 0)) throw new Error("SVG has no usable dimensions");
    return { width, height, viewBox };
  }

  async function exportPng(wrapper, index) {
    await pendingRenders;
    const svg = wrapper.querySelector(".mermaid-output svg");
    if (!svg) throw new Error("Diagram has not rendered");
    const { width, height, viewBox } = svgDimensions(svg);
    const scale = Math.min(2, 8192 / width, 8192 / height, Math.sqrt(32000000 / (width * height)));
    if (!(scale > 0)) throw new Error("Invalid export dimensions");
    const pixelWidth = Math.max(1, Math.floor(width * scale));
    const pixelHeight = Math.max(1, Math.floor(height * scale));
    const clone = svg.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(width)); clone.setAttribute("height", String(height));
    if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
      clone.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`);
    }
    const svgBlob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" });
    const svgUrl = URL.createObjectURL(svgBlob);
    try {
      const image = new Image(); image.decoding = "async"; image.src = svgUrl; await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = pixelWidth; canvas.height = pixelHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas unavailable");
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, pixelWidth, pixelHeight);
      ctx.drawImage(image, 0, 0, pixelWidth, pixelHeight);
      const png = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!png) throw new Error("PNG encoding failed");
      const pngUrl = URL.createObjectURL(png);
      try {
        const link = document.createElement("a");
        link.href = pngUrl; link.download = `${docName}-diagram-${index}.png`; link.click();
      } finally { setTimeout(() => URL.revokeObjectURL(pngUrl), 0); }
    } finally { URL.revokeObjectURL(svgUrl); }
  }

  const queueRender = (root = document) => {
    ensureHeadingIds(root);
    pendingRenders = pendingRenders.then(() => renderAll(root)).catch((error) => {
      for (const wrapper of diagramList(root)) {
        const output = wrapper.querySelector(".mermaid-output");
        if (output && !output.textContent) output.textContent =
          `Mermaid unavailable: ${error instanceof Error ? error.message : String(error)}`;
      }
    });
    return pendingRenders;
  };
  pendingRenders = renderAll().catch((error) => {
    for (const wrapper of diagramList(document)) {
      const output = wrapper.querySelector(".mermaid-output");
      if (output && !output.textContent) output.textContent =
        `Mermaid unavailable: ${error instanceof Error ? error.message : String(error)}`;
    }
  });

  function navigateLogicalParent() {
    const chatPath = document.body?.getAttribute("data-lantern-chat-path") || "";
    if (chatPath) {
      const parts = chatPath.replace(/\\/g, "/").split("/").filter(Boolean);
      parts.pop();
      const parentUrl = parts.length ? "/" + parts.map(encodeURIComponent).join("/") + "/" : "/";
      location.href = parentUrl;
      return;
    }
    try {
      const ref = document.referrer ? new URL(document.referrer) : null;
      if (ref && ref.origin === location.origin) {
        history.back();
        return;
      }
    } catch (_) {}
    location.href = "/";
  }

  document.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    // Issue 0: TOC / Anchor & Local Markdown Hyperlinks must NOT open a duplicate tab!
    const link = target.closest("article.md-preview a[href]");
    if (link) {
      const rawHref = (link.getAttribute("href") || "").trim();
      if (rawHref.startsWith("#")) {
        event.preventDefault();
        link.removeAttribute("target");
        const anchorEl = findAnchorTarget(rawHref);
        if (anchorEl) {
          const barH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--md-bar-height")) || 54;
          const startY = window.scrollY;
          const targetY = Math.max(0, anchorEl.getBoundingClientRect().top + startY - barH - 12);
          const dist = targetY - startY;
          if (Math.abs(dist) < 4) {
            window.scrollTo(0, targetY);
          } else {
            const dur = Math.min(160, Math.max(80, Math.abs(dist) * 0.08));
            const t0 = performance.now();
            const step = (now) => {
              const p = Math.min(1, (now - t0) / dur);
              const ease = 1 - Math.pow(1 - p, 3);
              window.scrollTo(0, Math.round(startY + dist * ease));
              if (p < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
          }
          history.replaceState(null, "", rawHref);
        } else {
          location.hash = rawHref;
        }
        return;
      }
      if (rawHref.startsWith("/") && !rawHref.startsWith("//")) {
        // Same-origin local file/markdown link: open in current tab unless Ctrl/Meta/Middle-clicked
        if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
          link.removeAttribute("target");
        }
      }
    }

    const button = target.closest("[data-action]");
    if (!button) return;
    const action = button.getAttribute("data-action");
    if (action === "back") { navigateLogicalParent(); return; }
    if (action === "print") { await pendingRenders; window.print(); return; }
    if (action === "png") {
      const index = Number(button.getAttribute("data-diagram-index"));
      const wrapper = button.closest(".mermaid-diagram");
      if (!wrapper || !Number.isInteger(index)) return;
      button.setAttribute("disabled", "");
      try { await exportPng(wrapper, index); }
      catch (error) { window.alert(`PNG export failed: ${error instanceof Error ? error.message : String(error)}`); }
      finally { button.removeAttribute("disabled"); }
    }
  });
  window.__lanternMarkdownPreview = {
    get pendingRenders() { return pendingRenders; },
    exportPng,
    refresh: queueRender,
    ensureHeadingIds,
  };
})();
