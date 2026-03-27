"""
SNS動画チェッカー - Vercel Serverless Function
"""
import os
import json
import base64
import tempfile
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler

import cv2
import numpy as np


# ──────────────────────────────────────────────
# チェックリスト定義
# ──────────────────────────────────────────────

CHECKLISTS = {
    "pr": {
        "label": "PR投稿",
        "categories": {
            "editing": {
                "label": "編集に関して",
                "items": [
                    {"id": "pr_edit_01", "text": "1カットの秒数0.6秒〜1.2秒になっているか", "auto": "cut_duration"},
                    {"id": "pr_edit_02", "text": "同一カテゴリのカットが3連続以上続いていないか（離脱ポイントになるため）", "auto": "similar_scenes"},
                    {"id": "pr_edit_03", "text": "料理が画面の8割を占めているか（素材が小さい場合アップに修正を行う）", "auto": False},
                    {"id": "pr_edit_04", "text": "誤字脱字はしていないか", "auto": False},
                    {"id": "pr_edit_05", "text": "テロップが画面の中央〜上1/3以内に収まっているか", "auto": False},
                    {"id": "pr_edit_06", "text": "テロップのフォントはマニュアル通りか", "auto": False},
                    {"id": "pr_edit_07", "text": "肖像権を侵害していないか？（一般人の顔はモザイクをかける）", "auto": "face_detect"},
                    {"id": "pr_edit_08", "text": "音声の読み間違いはないか", "auto": False},
                    {"id": "pr_edit_09", "text": "ナレーション音声の倍率が1.2倍になっているか", "auto": False},
                    {"id": "pr_edit_10", "text": "彩度/明度を調整し白飛びを防ぎ、料理の色が不自然でないか", "auto": "color_check"},
                    {"id": "pr_edit_11", "text": "商用利用可能な音源を使用しているか", "auto": False},
                ]
            },
            "appeal": {
                "label": "訴求に関して",
                "items": [
                    {"id": "pr_appeal_01", "text": "冒頭10秒までに伸びる要素が2つ以上入っているか（意外性・話題性・希少性・権威性の中から2つ）", "auto": False},
                    {"id": "pr_appeal_02", "text": "情報を羅列しただけではなく行動描写の表現が1つ以上含まれているか（個人の感想を含める）", "auto": False},
                    {"id": "pr_appeal_03", "text": "ターゲットを明確に訴求しているか", "auto": False},
                ]
            },
            "script": {
                "label": "台本に関して",
                "items": [
                    {"id": "pr_script_01", "text": "notionを見て今月絶対入れたい項目がある場合、確認し組み込んでいるか", "auto": False},
                    {"id": "pr_script_02", "text": "第3者視点の台本になっているか", "auto": False},
                    {"id": "pr_script_03", "text": "景品表示法のガイドラインを違反していないか？（No.1表記、最大表記、みんな知ってるNG）", "auto": False},
                ]
            },
            "thumbnail": {
                "label": "サムネイルに関して",
                "items": [
                    {"id": "pr_thumb_01", "text": "全てが太文字になっているか", "auto": False},
                    {"id": "pr_thumb_02", "text": "サイズは正方形の中に文字が全て収まるようになっているか", "auto": False},
                    {"id": "pr_thumb_03", "text": "メイン被写体が画面中央の正方形に収まったトリミングができているか", "auto": False},
                    {"id": "pr_thumb_04", "text": "サムネイル文1行目（上部）は12文字以内で記載できているか", "auto": False},
                    {"id": "pr_thumb_05", "text": "サムネイル文2行目（上部）は9文字以内で記載できているか", "auto": False},
                    {"id": "pr_thumb_06", "text": "サムネイル文2行目（上部）は左右最大までサイズ調整できているか", "auto": False},
                ]
            },
            "caption": {
                "label": "キャプションに関して",
                "items": [
                    {"id": "pr_cap_01", "text": "適正なハッシュタグを使用できているか（最大5個で#prは一番上に）", "auto": False},
                    {"id": "pr_cap_02", "text": "行動描写が1つ以上含まれているか", "auto": False},
                    {"id": "pr_cap_03", "text": "AIで作成時の「**」などの不要な記号は削除できているか", "auto": False},
                    {"id": "pr_cap_04", "text": "誤字脱字はしていないか", "auto": False},
                    {"id": "pr_cap_05", "text": "店舗情報に誤りはないか", "auto": False},
                ]
            },
        }
    },
    "normal": {
        "label": "通常投稿",
        "categories": {
            "video": {
                "label": "動画に関して",
                "items": [
                    {"id": "nm_vid_01", "text": "冒頭10秒までに伸びる要素が2つ以上入っているか（意外性・話題性・希少性・権威性の中から2つ）", "auto": False},
                    {"id": "nm_vid_02", "text": "第3者視点の台本になっているか", "auto": False},
                    {"id": "nm_vid_03", "text": "1カットの秒数0.6秒〜1.2秒になっているか", "auto": "cut_duration"},
                    {"id": "nm_vid_04", "text": "情報を羅列しただけではなく個人の感想的な文言が入っているか", "auto": False},
                    {"id": "nm_vid_05", "text": "誤字脱字はしていないか", "auto": False},
                    {"id": "nm_vid_06", "text": "同じような素材が続き離脱ポイントが生じていないか", "auto": "similar_scenes"},
                    {"id": "nm_vid_07", "text": "テロップの入れる位置は最適か", "auto": False},
                    {"id": "nm_vid_08", "text": "テロップのフォントはマニュアル通りか", "auto": False},
                    {"id": "nm_vid_09", "text": "景品表示法のガイドラインを違反していないか？（No.1表記、最大表記、みんな知ってる）", "auto": False},
                    {"id": "nm_vid_10", "text": "肖像権を侵害していないか？（一般人の顔はモザイク）", "auto": "face_detect"},
                    {"id": "nm_vid_11", "text": "彩度/明度を調整できているか", "auto": "color_check"},
                    {"id": "nm_vid_12", "text": "既存素材の場合店舗は営業していて商品は今も販売されているか", "auto": False},
                ]
            },
            "thumbnail": {
                "label": "サムネイルに関して",
                "items": [
                    {"id": "nm_thumb_01", "text": "全てが太文字になっているか", "auto": False},
                    {"id": "nm_thumb_02", "text": "サイズは正方形の中に文字が全て収まるようになっているか", "auto": False},
                    {"id": "nm_thumb_03", "text": "正方形の文字の中に見せたいものが全て写った写真のトリミングができているか", "auto": False},
                    {"id": "nm_thumb_04", "text": "エリアは一般ユーザーが見てわかりやすい場所になっているか", "auto": False},
                ]
            },
            "caption": {
                "label": "キャプションに関して",
                "items": [
                    {"id": "nm_cap_01", "text": "適正なハッシュタグを使用できているか（最大5個）", "auto": False},
                    {"id": "nm_cap_02", "text": "AIで作った文章丸出しではないか", "auto": False},
                    {"id": "nm_cap_03", "text": "誤字脱字はしていないか", "auto": False},
                    {"id": "nm_cap_04", "text": "店舗情報に誤りはないか", "auto": False},
                ]
            },
        }
    }
}


# ──────────────────────────────────────────────
# OpenCV チェック関数
# ──────────────────────────────────────────────

def detect_scene_changes(cap, fps, total_frames, threshold=30.0):
    scene_changes = [0]
    prev_frame = None
    sample_interval = max(int(fps / 10), 1)
    for i in range(0, total_frames, sample_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        if prev_frame is not None:
            diff = cv2.absdiff(small, prev_frame)
            if np.mean(diff) > threshold:
                scene_changes.append(i)
        prev_frame = small
    scene_changes.append(total_frames)
    return scene_changes


def check_cut_duration(scene_changes, fps):
    if fps <= 0 or len(scene_changes) < 2:
        return {"status": "unknown", "comment": "カット検出ができませんでした"}
    cut_durations = [round((scene_changes[i+1] - scene_changes[i]) / fps, 2) for i in range(len(scene_changes)-1)]
    if not cut_durations:
        return {"status": "unknown", "comment": "カットが検出されませんでした"}
    short = [d for d in cut_durations if d < 0.6]
    long = [d for d in cut_durations if d > 1.2]
    total = len(cut_durations)
    ok = total - len(short) - len(long)
    avg = round(sum(cut_durations)/total, 2)
    if not short and not long:
        return {"status": "pass", "comment": f"全{total}カット OK。平均 {avg}秒（{min(cut_durations)}〜{max(cut_durations)}秒）"}
    issues = []
    if short: issues.append(f"短すぎ {len(short)}カット（{min(short)}秒〜）")
    if long: issues.append(f"長すぎ {len(long)}カット（〜{max(long)}秒）")
    ratio = ok / total
    status = "pass" if ratio >= 0.8 else "warn" if ratio >= 0.5 else "fail"
    return {"status": status, "comment": f"全{total}カット中 {ok}カット適正。{', '.join(issues)}。平均 {avg}秒"}


def check_similar_scenes(cap, scene_changes, fps):
    if len(scene_changes) < 4:
        return {"status": "pass", "comment": "カット数が少ないため問題なし"}
    histograms = []
    for i in range(len(scene_changes)-1):
        mid = (scene_changes[i] + scene_changes[i+1]) // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
        ret, frame = cap.read()
        if ret:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0,1], None, [30,32], [0,180,0,256])
            cv2.normalize(hist, hist)
            histograms.append(hist)
        else:
            histograms.append(None)
    consecutive = []
    streak = 1
    for i in range(1, len(histograms)):
        if histograms[i] is not None and histograms[i-1] is not None:
            sim = cv2.compareHist(histograms[i-1], histograms[i], cv2.HISTCMP_CORREL)
            if sim > 0.85:
                streak += 1
            else:
                if streak >= 3:
                    t = round(scene_changes[i-streak]/fps, 1) if fps > 0 else 0
                    consecutive.append(f"{t}秒付近で{streak}連続")
                streak = 1
        else:
            streak = 1
    if streak >= 3:
        t = round(scene_changes[len(histograms)-streak]/fps, 1) if fps > 0 else 0
        consecutive.append(f"{t}秒付近で{streak}連続")
    if not consecutive:
        return {"status": "pass", "comment": "類似カットの3連続以上はありません"}
    return {"status": "warn" if len(consecutive) <= 2 else "fail", "comment": f"類似シーンが連続: {', '.join(consecutive)}"}


def check_faces(cap, fps, total_frames):
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    face_frames = []
    interval = max(total_frames // 30, 1)
    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(50,50))
        if len(faces) > 0:
            face_frames.append(round(i/fps, 1) if fps > 0 else 0)
    if not face_frames:
        return {"status": "pass", "comment": "顔は検出されませんでした"}
    ts = [f"{t}秒" for t in face_frames[:10]]
    return {"status": "warn", "comment": f"顔が検出: {', '.join(ts)}（計{len(face_frames)}箇所）。モザイク確認が必要"}


def check_color(cap, fps, total_frames):
    overexposed = []
    low_sat = []
    interval = max(total_frames // 20, 1)
    bri_vals, sat_vals = [], []
    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: continue
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        _, s, v = cv2.split(hsv)
        bri_vals.append(np.mean(v))
        sat_vals.append(np.mean(s))
        t = round(i/fps, 1) if fps > 0 else 0
        if np.sum(v > 240) / v.size > 0.3:
            overexposed.append(t)
        if np.mean(s) < 30:
            low_sat.append(t)
    issues = []
    status = "pass"
    if overexposed:
        issues.append(f"白飛び: {', '.join(str(t)+'秒' for t in overexposed[:5])}付近")
        status = "warn"
    if low_sat:
        issues.append(f"低彩度: {', '.join(str(t)+'秒' for t in low_sat[:5])}付近")
        status = "warn"
    if overexposed and len(overexposed) > len(bri_vals) * 0.3:
        status = "fail"
    avg_b = round(np.mean(bri_vals), 1) if bri_vals else 0
    avg_s = round(np.mean(sat_vals), 1) if sat_vals else 0
    if not issues:
        return {"status": "pass", "comment": f"色調は適正（平均明度: {avg_b}/255, 平均彩度: {avg_s}/255）"}
    return {"status": status, "comment": f"{'; '.join(issues)}（平均明度: {avg_b}, 平均彩度: {avg_s}）"}


def extract_preview_frames(cap, fps, total_frames, count=8):
    frames = []
    interval = max(total_frames // count, 1)
    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: continue
        h, w = frame.shape[:2]
        scale = min(400/w, 400/h, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w*scale), int(h*scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        frames.append({"base64": base64.b64encode(buf).decode(), "timestamp": round(i/fps, 2) if fps > 0 else 0})
        if len(frames) >= count: break
    return frames


# ──────────────────────────────────────────────
# multipart/form-data パーサー
# ──────────────────────────────────────────────

def parse_multipart(body_bytes, content_type):
    """multipart/form-data をパースしてフィールドとファイルを返す"""
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):].strip('"')
            break
    if not boundary:
        return {}, {}

    boundary_bytes = ("--" + boundary).encode()
    end_boundary = ("--" + boundary + "--").encode()

    parts = body_bytes.split(boundary_bytes)
    fields = {}
    files = {}

    for part in parts:
        if not part or part.strip() == b"" or part.strip() == b"--":
            continue
        # Remove leading \r\n
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]

        # Split headers and body
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header_data = part[:header_end].decode("utf-8", errors="replace")
        body_data = part[header_end + 4:]

        # Parse Content-Disposition
        name = None
        filename = None
        for line in header_data.split("\r\n"):
            if "Content-Disposition" in line:
                for item in line.split(";"):
                    item = item.strip()
                    if item.startswith("name="):
                        name = item[5:].strip('"')
                    elif item.startswith("filename="):
                        filename = item[9:].strip('"')

        if name:
            if filename:
                files[name] = {"filename": filename, "data": body_data}
            else:
                fields[name] = body_data.decode("utf-8", errors="replace")

    return fields, files


# ──────────────────────────────────────────────
# Vercel Handler
# ──────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)

            fields, files = parse_multipart(body, content_type)

            if "video" not in files:
                self._json_response(400, {"error": "動画ファイルが選択されていません"})
                return

            post_type = fields.get("post_type", "pr")
            if post_type not in CHECKLISTS:
                self._json_response(400, {"error": "無効な投稿タイプです"})
                return

            video_file = files["video"]
            suffix = Path(video_file["filename"]).suffix or ".mp4"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(video_file["data"])
                tmp_path = tmp.name

            try:
                cap = cv2.VideoCapture(tmp_path)
                if not cap.isOpened():
                    self._json_response(400, {"error": "動画の読み込みに失敗しました"})
                    return

                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                duration = total_frames / fps if fps > 0 else 0

                metadata = {
                    "fps": round(fps, 2),
                    "total_frames": total_frames,
                    "width": width,
                    "height": height,
                    "duration": round(duration, 2),
                    "aspect_ratio": f"{width}:{height}",
                }

                scene_changes = detect_scene_changes(cap, fps, total_frames)

                auto_results = {}
                checklist = CHECKLISTS[post_type]
                for cat in checklist["categories"].values():
                    for item in cat["items"]:
                        ck = item.get("auto")
                        if not ck: continue
                        iid = item["id"]
                        if ck == "cut_duration":
                            auto_results[iid] = check_cut_duration(scene_changes, fps)
                        elif ck == "similar_scenes":
                            auto_results[iid] = check_similar_scenes(cap, scene_changes, fps)
                        elif ck == "face_detect":
                            auto_results[iid] = check_faces(cap, fps, total_frames)
                        elif ck == "color_check":
                            auto_results[iid] = check_color(cap, fps, total_frames)

                preview_frames = extract_preview_frames(cap, fps, total_frames)
                cap.release()

                self._json_response(200, {
                    "metadata": metadata,
                    "auto_results": auto_results,
                    "preview_frames": preview_frames,
                    "checklist": checklist,
                })
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            traceback.print_exc()
            self._json_response(500, {"error": f"エラーが発生しました: {str(e)}"})

    def do_GET(self):
        self._json_response(200, {"checklists": CHECKLISTS})

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
