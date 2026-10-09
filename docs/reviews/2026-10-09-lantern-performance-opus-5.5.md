# Lantern performance review — M365 Opus 5.5

- Date: 2026-10-09 (JST)
- Reviewer: Microsoft 365 Copilot, verified `Opus 5.5`
- Repository: `C:\Users\DuongNH66\Desktop\git\lantern`
- Source HEAD reviewed: `a45971b`
- Conversation: https://m365.cloud.microsoft/chat/conversation/3adee003-351c-4b7b-92ee-51dec0434920
- Durable job: `61686840-m365-20261009-104343-2f8a0876`
- Status: COMPLETED; model verified at completion
- Evidence: 3 source/test bundles (13 files), copied to M365 with checksummed attachment receipts
- Method: independent source review; **Opus did not run benchmarks/tests**

> Review-only document. Findings labelled as code-derived or hypothetical should be independently reproduced before production changes. Non-substantive M365 UI markers were omitted when saving this copy.

---

Lantern a45971b: kiểm toán hiệu năng/độ ổn định độc lập (phân tích trên source đính kèm)
1. Verdict: APPROVE_WITH_REQUIRED_FIXES

a45971b đúng hướng. Commit bỏ được việc dựng lại grid mỗi 4s, file đã tồn tại thì không gửi body, _read_limited_bytes đã có giới hạn, và video ở side pane không còn preload=auto + autoplay. Chỉ có một regression về độ đúng dữ liệu (R1) bắt buộc phải sửa trước khi chấp nhận. Sửa nhỏ, không cần revert. Các vấn đề lớn nhất về hiệu năng có từ trước commit: replay terminal sau mỗi lần chuyển thư mục, Office/PDF preview không giới hạn, và listing quét lại toàn thư mục ở mỗi trang. Đây là ưu tiên tiếp theo, không chặn commit.

Tôi không chạy test, không đo CPU/RSS và không xem runtime. Mọi kết luận dưới đây lấy từ source và evidence đã cung cấp.

Quy ước cột "Trạng thái":

CM: lỗi chứng minh được từ code, hành vi xảy ra tất định.
RR: rủi ro code độ tin cậy cao (race/thuật toán), chưa tái hiện.
GT: giả thuyết, cần stress/soak.
ĐO: có số đo trong evidence.
2. Bảng phát hiện
ID	Mức	Loại	File:hàm [dòng]	Vấn đề	Tác động	Trạng thái
R1	P1	Regression / stale view	lan_drive.py JS softRefresh [L1320]. Nơi gọi: renameOne/copySel/moveSel/duplicateSel/batchRenameSel/extractSelected [L1476–1481], deleteSel [L1562], refreshFolder [L1321], hydrateCache→softRefresh [L1742]	Khi state.items.length>next.length thì unchanged thành true, nên mọi thay đổi ở trang ≥2 bị bỏ qua. Cache sessionStorage nhiều trang cũng không bao giờ được revalidate ngoài trang 1. Nút ↻ cũng không cứu được.	Card đã xoá/đổi tên vẫn hiện, bấm vào thì 404	CM
W1	P1	Network / RAM / lock	terminal_scm.js connect chạy vô điều kiện [L64], onMessage snapshot→ensure→makeX [L12, L34]. lantern_ws.upgrade [L231–233]. TerminalManager.replay [L551]	Mỗi lần chuyển thư mục là load lại cả trang, mở WS mới và nhận snapshot toàn bộ output của live và history (tối đa 16+32 × 200K ký tự). Client tạo xterm (scrollback 8000) cho từng terminal kể cả khi drawer đóng. json.dumps chạy trong lúc giữ terminal.lock. Ký tự điều khiển (ESC) encode thành \u001b (6 byte). Frame vượt 8 MiB thì _enqueue overflow, dẫn tới reconnect vô hạn.	Mỗi click thư mục tốn hàng trăm KB–MB trên Tailscale; giật khi chuyển thư mục; có thể kẹt "Reconnecting"	Cơ chế: CM. Ngưỡng overflow: GT
D1	P1	RAM / CPU không giới hạn	plugin.py _render_docx [L559], _xlsx_shared_strings [L581], _render_xlsx [L650, L653], _render_pdf pdftotext [L713], _extract_pdf_text_naive zlib.decompress [L689]	Cap 8 MiB không áp dụng cho các nhánh này: z.read + ET.fromstring đọc cả part, findall dựng hết list rồi mới cắt 160 dòng, pdftotext xuất toàn bộ tài liệu, decompress không giới hạn. Side pane mở iframe cho .pdf/.docx/.xlsx [L1585]; giữ phím mũi tên thì nhiều render nặng chạy song song, không huỷ được.	Process chiếm RAM rất lớn hoặc chết, kéo theo toàn bộ PTY	RR
L1	P1	Thuật toán	list_entries_page [L1919–1957]	Mỗi trang đều scandir toàn bộ, sort toàn bộ, rồi slice. Cuộn hết thư mục N mục với limit L tốn O(N²/L). Recursive search "all" quét lại cả cây ở mỗi trang và mỗi lần lazy refresh 30s.	Thư mục lớn chậm dần khi cuộn sâu	Độ phức tạp: CM. Thời gian thực: GT
L2	P2	CPU / I/O mỗi item	entry_to_json [L1824, L1853] → plugin.can_preview → custom_patterns → _load_config [plugin L80–89, L112]	Mỗi item: 1–2 lần resolve() (tốn kém trên Windows), is_file(), đọc và parse JSON config từ đĩa, normalize khoảng 90 pattern	Chi phí tăng tuyến tính theo limit (tối đa 1000)	CM
T1	P1	Băng thông / decode	cardHTML [L1287]	thumb_fit mặc định là contain, nên card ảnh tải file gốc thay vì thumbnail 420px	Grid ảnh nặng gấp nhiều lần trên Tailscale/mobile	CM
S1	P2	Độ trễ gõ phím	lantern_ws.upgrade → dispatch chạy inline [L239, L281–289]	Truy vấn git (5 process, có thể tới 15s) chạy trên thread đọc WS, nên terminal_input của cùng tab phải xếp hàng chờ	Gõ terminal bị khựng khi Git view refresh	Cơ chế: CM. Mức độ: GT
S2	P2	Subprocess	ScmService.status [L127–138] + ensure_watch→git_dir_of [L146, L114]	Mỗi status chạy 5 git process (evidence ghi 4). Không đặt GIT_OPTIONAL_LOCKS=0 [L78], nên status có thể ghi .git/index; watchdog đệ quy trên .git bắt được, phát scm_changed, rồi client refresh tiếp	Vòng tự kích hoạt; tranh chấp index.lock với git chạy trong terminal	5 process: CM. Vòng lặp: GT
S3	P2	Refresh khi pane ẩn	terminal_scm.js onMessage scm_changed [L18], terminal_exit [L15]	Chỉ kiểm S.view==='git', không kiểm drawer có hiện hay document.hidden; mỗi lần còn kèm reloadHistory=true. Interval 60s thì có gate [L62], nên hai đường xử lý không nhất quán	Git status + history chạy khi pane đã đóng	CM
S4	P2	Nhiều client	ensure_watch dùng một _watch_path duy nhất [L336–339]; broadcast tới mọi peer	Hai tab ở hai repo khác nhau giành nhau watcher; event của repo này làm refresh repo kia	Mất event hoặc chạy git thừa	CM
S5	P2	Rò rỉ thread	_start_poll_fallback loop dùng self._poll_stop.wait(30) [L379]; stop_watch thay object event [L407]	Nếu loop đang ở trong _git_signature lúc stop_watch chạy, lần lặp sau nó chờ trên event mới chưa được set, nên thread cũ chạy mãi (join chỉ 0.2s)	Thread poll mồ côi tiếp tục phát scm_changed (chỉ khi không có watchdog)	RR
S6	P2	Repo lớn	history --all --graph [L154]; --untracked-files=all [L127] + renderScm dựng DOM cho tất cả file [js L53]	--graph ép topo-order trên toàn bộ history; cây untracked lớn sinh output tới 16 MB và DOM không giới hạn	Repo lớn chậm (evidence 108 ms là repo nhỏ)	GT
O1	P2	CPU khi output dồn	_append_retained [L430–435], _queue_output [L437–444]; OUTPUT_FLUSH_MS/flush_ms [L18, L346] không được dùng	Mỗi chunk tạo lại chuỗi khoảng 200K (copy O(buffer)); mỗi chunk thành 1 broadcast, mỗi peer json.dumps riêng	CPU/GIL tăng khi build/log chạy nhanh; test truyền flush_ms cho ra tự tin giả	Unused: CM. CPU: GT
U1	P2	Race / mất dữ liệu	api_upload [L2381 kiểm tra → L2413 os.replace]; nhánh rename [L2388–2395]	Conflict chỉ kiểm lúc bắt đầu request. File xuất hiện trong lúc stream sẽ bị ghi đè âm thầm. Hai upload rename cùng tên có thể chọn cùng tên "(1)"	Hiếm nhưng mất dữ liệu; test hiện tạo file trước POST nên không phủ race	RR
R2	P2	Thêm 1 RTT	uploadOneQueued preflight [L1707]	Chế độ ask/skip: mọi file, kể cả file mới, tốn thêm 1 GET trước khi POST	Nhiều file nhỏ qua WAN: tổng thời gian tăng khoảng (số file × RTT)/số worker	CM (đo được tổng thời gian: GT)
U2	P2	O(N²) trên DOM	renderUploadQueue [L1693–1700] được gọi ở mỗi progress event; queue.find [L1727]	Mỗi lần dựng lại 500 dòng innerHTML và chạy 2 lần reduce trên toàn queue	Upload folder hàng nghìn file nhỏ làm UI giật	Độ phức tạp: CM. Mức độ: GT
F1	P2	Timer / layout khi idle	startFolderRotate [L1612–1617]; setupFolderPreviews [L1635–1640]	Mỗi folder có 1 setInterval gọi getBoundingClientRect (ép layout) mỗi 3.5s. Mỗi appendRender xoá toàn bộ timer (rotation ngừng) và đặt folderPreviewActive=0 khi request vẫn đang bay, nên giới hạn concurrency 2 bị phá	Tab mở lâu tốn CPU nền; cap fetch sai	Cơ chế: CM. CPU: GT
F2	P2	Tuần tự hoá O(N)	saveListCache [L1300] gọi ở mỗi append	Mỗi trang lại JSON.stringify toàn bộ state.items; vượt quota sessionStorage thì lỗi bị nuốt	Cuộn sâu bị khựng; cache âm thầm không còn tác dụng	CM
P1x	P2	Băng thông khi chuyển trang	page_shell inline CSS/JS [L1804, L1811]; serve_app_asset no-cache [L2055] dù URL đã có ?v=	Mỗi lần chuyển thư mục tải lại HTML kèm toàn bộ CSS/JS inline, cộng 5 lần revalidate	Chậm trên Tailscale	CM (kích thước byte: GT)
TH1	P2	Race cache	api_thumb [L2341–2347]; make_image_thumb lưu thẳng vào dst [L954]	Ghi không atomic, không khoá: request đồng thời có thể sinh trùng hoặc nhận JPEG ghi dở. Cache không bao giờ bị dọn	Thumbnail hỏng thỉnh thoảng; thư mục cache lớn mãi	RR
FP1	P3	Stale	loadFolderPreview cache:'force-cache' [L1633]	Response không có header cache, force-cache dùng lại bản cũ vô thời hạn	Mosaic folder hiển thị nội dung cũ	CM
E1	P3	Edge case	renderListPreview Range [L1586] + serve_static_file [L2828]	File text rỗng: start(0) >= size(0) trả 416, UI báo "HTTP 416"	Lỗi nhỏ ở nhánh fallback	CM
MD1	P2	Bậc hai	plugin._md_inline vòng restore [L322–329]; bảng cắt ở 160 dòng [L432] làm phần dư thành một paragraph	Mỗi vòng quét O(số token × độ dài chuỗi); với 600K ký tự và hàng chục nghìn token có thể tốn nhiều giây trên thread request	Markdown lớn hoặc bảng dài treo preview	RR
SUB1	P3	Unbounded read	subtitle_to_vtt [L1055]	Cùng pattern read_bytes()[:N] mà commit vừa sửa trong plugin	Nhỏ	CM
X1	P2	Đĩa	extract_archive [L695–733]	Không giới hạn tổng dung lượng giải nén; getmembers() nạp hết danh sách vào RAM	Archive độc hại hoặc quá lớn làm đầy đĩa	RR
H1	P3	Thread	ThreadingHTTPServer không đặt timeout; prefetchMediaAround tạo <video> tách rời [L1359]	Client chậm giữ thread mãi; video prefetch có thể giữ kết nối tới khi GC	Số thread tăng khi nhiều client	GT
3. Chấp nhận P1/P2 của commit
Hạng mục	Chạy đúng	Sai / thiếu	Sửa tối thiểu
Lazy refresh 30s + focus/visibility [L1306–1311]	Bỏ được rebuild 4s; có gate (hidden, modal, drawer, selection); minAge 5s chống spam focus	R1. Ngoài ra lazy refresh 30s chạy lại recursive search (L1)	softRefresh({force:true}) cho mọi mutation và ↻; khi force thì reset về trang 1 và render. Bỏ qua lazy refresh khi đang có query đệ quy
DOM identity khi không đổi	So sánh rẻ, giữ được scroll	Chỉ đúng cho trang 1	Như trên
Upload preflight [L1642–1724, L2349–2367]	Dùng chung resolver giữa preflight và POST; preflight không tạo thư mục (có test); skip = 0 byte body; POST vẫn kiểm tra lại	R2 (thêm RTT); U1 có từ trước; preflight 403 trả HTML nên r.json() ném SyntaxError khó hiểu	Chỉ preflight khi size ≥ ngưỡng (đề xuất 1 MiB, cần đo); U1: commit bằng os.link/O_EXCL (POSIX) hoặc os.rename (Windows, lỗi nếu đích tồn tại) cho ask/skip/rename
Text preview Range 200KB [L1586]	Server trả 206 đúng; có guard listPreview!==rel	Tiền đề yếu: .log/.txt/.md khớp BUILTIN_PATTERNS, nên có preview=1 và vào iframe plugin [L1585] trước. Nhánh Range chỉ chạy với text không có pattern hoặc khi plugin tắt. E1 với file rỗng	Ghi rõ phạm vi; xử lý 416 hoặc size==0
_read_limited_bytes [plugin L197–201]	Đọc có giới hạn, có test chống read_bytes	Mặc định vẫn đọc 8 MiB+1, rồi decode thử tối đa 5 encoding trên cả 8 MiB trước khi cắt còn 600K ký tự. Docx/xlsx/pdf không đi qua hàm này (D1)	Giảm số byte đọc cho text xuống khoảng MAX_TEXT_CHARS×4; làm D1
Video preload=metadata side pane [L1583]	Đúng	Thay đổi UX: không còn autoplay. Modal vẫn auto + autoplay [L1405], hợp lý	Không cần sửa
Git 60s gated [js L62]	Gate theo drawer + hidden	S3: nhánh scm_changed/terminal_exit chưa có gate; S2	Đưa cùng điều kiện gate vào [L15, L18]; đánh dấu dirty, refresh khi mở lại
4. Ưu tiên mở rộng (xếp theo tác động tiềm năng)
W1: không replay terminal sau mỗi lần chuyển thư mục. Chỉ connect() khi mở drawer, hoặc gửi terminal_list trước và chỉ gửi output của tab đang active. Tạo xterm lười. Encode snapshot ngoài lock và chia thành nhiều frame.
Tradeoff: mở drawer lần đầu chậm thêm khoảng 1 RTT.
D1: giới hạn Office/PDF. Kiểm ZipInfo.file_size, dùng iterparse và dừng sau 160 dòng, chạy pdftotext với -l và cắt stdout, dùng decompressobj().decompress(raw, max_length). Thêm semaphore cho preview nặng.
Tradeoff: preview chỉ còn phần đầu tài liệu.
L1 + L2: listing thư mục lớn. Thêm LRU cache cho kết quả đã sort, key là (path, sort, q, depth, mtime thư mục), TTL ngắn. Cache custom_patterns theo mtime của config. Resolve root một lần mỗi request.
Tradeoff: mtime thư mục trên Windows không phản ánh thay đổi nội dung file, nên cần TTL.
T1: luôn dùng it.thumb, onerror thì fallback về ảnh gốc. Sửa 1 dòng.
S1–S3: chạy truy vấn SCM trên executor riêng (giữ FIFO per-peer bằng reqId); đặt GIT_OPTIONAL_LOCKS=0; cache git_dir; gate scm_changed.
O1: ring buffer (deque + compact lười) và gộp output theo flush_ms thật sự; encode 1 lần cho mỗi broadcast.
U2/F1/F2: throttle renderUploadQueue bằng rAF; dùng 1 timer rotate chung + tập folder đang hiển thị; chỉ lưu cache trang đầu hoặc ghi lười.
Lazy-load hay invalidation bằng event/watchdog
	Lazy (30s + focus)	Event (watchdog → push)
Chi phí idle	Gần 0 khi tab ẩn	Thread watcher; event .git dồn dập khi fetch/gc
Độ tươi	Trễ tối đa 30s, hoặc tới lần focus	Khoảng 0.6s (debounce)
Nhiều client	Mỗi tab tự lo	Cần lọc theo repo (S4)
Đề xuất	Giữ cho file list (đủ, rẻ) + force sau mutation	Giữ cho Git, nhưng chỉ làm dấu dirty khi pane ẩn

Không nên đẩy file list qua watcher: watch đệ quy trên root có thể là C:\, rất đắt.

5. Test / benchmark đề xuất
#	Workload	Công cụ	Metric	Tiêu chí pass
B1 (R1)	Thư mục 500 file, limit 100; cuộn 5 trang; xoá/đổi tên mục #450; thêm một trường hợp xoá qua CLI rồi ↻	Playwright / Chrome DevTools	Card còn tồn tại hay không	Card biến mất hoặc đổi tên. Khi idle, DOM identity vẫn được giữ
B2 (W1)	Baseline: 4 terminal × 200K ký tự ANSI, drawer đóng; chuyển 10 thư mục. Ngưỡng: 16 live + 16 history đầy, output tiếng Nhật	DevTools Network (WS frames); psutil đo RSS/thread	Byte WS mỗi lần chuyển; số xterm được tạo; số lần reconnect	Drawer đóng: snapshot 0 byte, 0 xterm. Ngưỡng: kết nối được, không có vòng lặp overflow
B3 (D1)	xlsx 300k dòng; docx 200 MB XML; PDF 2000 trang; zlib bomb	psutil peak RSS + thời gian	ΔRSS, p95 thời gian, process còn sống	ΔRSS nằm trong giới hạn đã khai báo (đo baseline trước rồi đặt ngưỡng); không OOM
B4 (L1/L2)	Thư mục 20k và 100k file trên NTFS; cuộn hết; sort name/mtime/type	Thời gian /api/list theo offset (script urllib)	p50/p95 theo từng trang	Thời gian trang N không tăng theo N (sau khi có cache); limit 1000 không tệ hơn baseline
B5 (T1)	200 ảnh × 5 MB, viewport đầu tiên	DevTools Network + Performance	Tổng byte; LongTask khi cuộn	Byte ≈ số ảnh × kích thước thumbnail
B6 (S1–S3)	Repo idle + Git view mở rồi đóng 5 phút; gõ phím liên tục trong terminal khi scm_changed bắn	Đếm scm_status nhận ở server; đo khoảng thời gian keydown→echo	Số lần status khi đóng; p95 độ trễ echo	Pane đóng: 0 lần status. p95 echo khi refresh ≈ p95 khi không refresh
B7 (S2)	Repo idle, Git view mở	GIT_TRACE2_PERF / Procmon	Số process mỗi status; số scm_changed/phút	4 process (sau khi cache git_dir); 0 scm_changed khi idle
B8 (O1)	seq 1 5000000 trong ConPTY và WSL, 1 và 4 tab	psutil CPU%	CPU giây và thời gian hoàn tất	Sau patch không tệ hơn trước (so A/B)
B9 (U1)	2 POST ask song song, cùng tên, 64 MB; 2 POST rename cùng tên	Script Python	Kết quả cuối	Đúng 1×200 và 1×409; với rename: 2 file khác tên
B10 (R2/U2)	1000 file × 4 KB qua Tailscale thật và qua throttle	Đồng hồ tổng thời gian; LongTask	So với 3f0f798	Không chậm hơn baseline
B11 (soak)	8 giờ: 2 tab, 4 terminal, folder có 200 thư mục con	psutil RSS/thread/handle mỗi 5 phút; CPU tab trình duyệt	Độ dốc tăng	Không tăng đơn điệu sau giờ đầu
6. Kế hoạch patch (không implement)
[Bắt buộc] R1: thêm softRefresh({force}) cho mutation và ↻; xử lý E1.
S3 + gate scm_changed; T1 (1 dòng).
W1: connect lười + snapshot lười + encode ngoài lock.
D1: giới hạn docx/xlsx/pdf + semaphore cho preview.
L1/L2: cache listing + cache pattern.
S1/S2: executor cho SCM, GIT_OPTIONAL_LOCKS=0, cache git_dir; S5 (giữ tham chiếu event cục bộ trong loop).
U1 commit atomic; R2 đặt ngưỡng preflight; U2/F1/F2.
O1 ring buffer + flush gộp thật sự.
Mâu thuẫn và khoảng trống bằng chứng (không đoán thay)
Evidence ghi "4 git subprocesses/status", nhưng code chạy 5 (rev-parse trong ensure_watch).
Bài đo "5 MiB log → 206/200 KB": với plugin bật, .log đi vào iframe plugin, không đi nhánh Range. Cần ghi rõ bài đo đã chạy ở cấu hình nào.
Bài đo "32 MiB → 200 KB, 0.38 MiB" dùng limit=200KB; giá trị mặc định thật là 8 MiB. Peak thực tế của đường mặc định chưa được đo.
Khoảng idle 5.3s ngắn hơn chu kỳ 30s, nên chưa chứng minh được hành vi 30s, focus hay cuộn sâu.
Test truyền flush_ms nhưng code không dùng tham số này: tự tin giả.
LANTERN_SYSTEM_ARCHITECTURE.md mô tả reconnect gửi terminal_sync [L632], trong khi test và code xác nhận server tự gửi snapshot khi upgrade. Tài liệu chưa khớp.
Chưa có soak, chưa có test nhiều client, chưa đo WAN. Chưa thể kết luận không có leak.
7. Ghi chú WSL / tmux (độ tin cậy khi shutdown)

kill_all → kill → close(graceful=True) gửi chuỗi \x03exit\r vào PTY [terminal L214, L296]. Nếu tmux đang attached trong PTY đó, chuỗi phím này đi vào pane của tmux: Ctrl-C rồi exit thoát shell trong pane, và nếu đó là pane cuối thì session mất. Khi tmux đã detach, exit chỉ thoát shell ngoài, nên session tmux còn sống.

Cơ chế này khớp với quan sát đã có (detached thì sống, attached thì mất), nhưng vẫn là giả thuyết cần tái hiện. Hướng kiểm chứng: khi shutdown, đóng PTY hoặc pseudo-console (để tmux client nhận SIGHUP và tự detach) thay vì tiêm phím, rồi kiểm tra session còn sống. Ngoài ra kill_all chạy tuần tự, mỗi terminal chờ tối đa 0.3s, nên 16 terminal mất khoảng 4.8s để shutdown.

8. Ngoài phạm vi

Git dock dọc, terminal nổi, resize preview, mở rộng tính năng, chính sách bảo mật hoặc phát hành, IME/UniKey. Bản review này không đề xuất viết lại hệ thống.

Sources
