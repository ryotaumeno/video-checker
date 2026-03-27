"""
SNS動画チェッカー - 動画の品質チェックWebアプリ（APIなし版）
OpenCVで技術的なチェックを自動化 + 手動チェックリスト
"""
import os
import json
import base64
import tempfile
import traceback
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

UPLOAD_DIR = tempfile.mkdtemp(prefix="video_checker_")

# チェックリスト定義
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
# OpenCVによる自動チェック関数
# ──────────────────────────────────────────────

def get_video_info(video_path):
    """動画の基本情報を取得"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, None

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

    return cap, metadata


def detect_scene_changes(cap, fps, total_frames, threshold=30.0):
    """シーン変化を検出してカットポイントを返す"""
    scene_changes = [0]  # 最初のフレーム
    prev_frame = None
    sample_interval = max(int(fps / 10), 1)  # FPSの1/10間隔でサンプリング

    for i in range(0, total_frames, sample_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))

        if prev_frame is not None:
            diff = cv2.absdiff(small, prev_frame)
            mean_diff = np.mean(diff)
            if mean_diff > threshold:
                scene_changes.append(i)

        prev_frame = small

    scene_changes.append(total_frames)
    return scene_changes


def check_cut_duration(scene_changes, fps):
    """各カットの秒数が0.6〜1.2秒か確認"""
    if fps <= 0 or len(scene_changes) < 2:
        return {"status": "unknown", "comment": "カット検出ができませんでした"}

    cut_durations = []
    for i in range(len(scene_changes) - 1):
        dur = (scene_changes[i + 1] - scene_changes[i]) / fps
        cut_durations.append(round(dur, 2))

    if not cut_durations:
        return {"status": "unknown", "comment": "カットが検出されませんでした"}

    short_cuts = [d for d in cut_durations if d < 0.6]
    long_cuts = [d for d in cut_durations if d > 1.2]
    total = len(cut_durations)
    ok_cuts = total - len(short_cuts) - len(long_cuts)
    avg = round(sum(cut_durations) / len(cut_durations), 2)

    if len(short_cuts) + len(long_cuts) == 0:
        return {
            "status": "pass",
            "comment": f"全{total}カット OK。平均 {avg}秒（範囲: {min(cut_durations)}〜{max(cut_durations)}秒）"
        }

    issues = []
    if short_cuts:
        issues.append(f"短すぎ {len(short_cuts)}カット（{min(short_cuts)}秒〜）")
    if long_cuts:
        issues.append(f"長すぎ {len(long_cuts)}カット（〜{max(long_cuts)}秒）")

    ratio = ok_cuts / total
    status = "pass" if ratio >= 0.8 else "warn" if ratio >= 0.5 else "fail"

    return {
        "status": status,
        "comment": f"全{total}カット中 {ok_cuts}カット適正。{', '.join(issues)}。平均 {avg}秒",
        "details": {"cut_durations": cut_durations[:50]}  # 最大50カット分
    }


def check_similar_scenes(cap, scene_changes, fps):
    """類似シーンが3連続以上続いていないか確認"""
    if len(scene_changes) < 4:
        return {"status": "pass", "comment": "カット数が少ないため問題なし"}

    # 各カットの代表フレーム（中間フレーム）のヒストグラムを比較
    histograms = []
    for i in range(len(scene_changes) - 1):
        mid_frame = (scene_changes[i] + scene_changes[i + 1]) // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        if ret:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            histograms.append(hist)
        else:
            histograms.append(None)

    # 連続類似カウント
    consecutive_similar = []
    current_streak = 1
    similarity_threshold = 0.85

    for i in range(1, len(histograms)):
        if histograms[i] is not None and histograms[i - 1] is not None:
            similarity = cv2.compareHist(histograms[i - 1], histograms[i], cv2.HISTCMP_CORREL)
            if similarity > similarity_threshold:
                current_streak += 1
            else:
                if current_streak >= 3:
                    t = round(scene_changes[i - current_streak] / fps, 1) if fps > 0 else 0
                    consecutive_similar.append({"start": t, "count": current_streak})
                current_streak = 1
        else:
            current_streak = 1

    if current_streak >= 3:
        t = round(scene_changes[len(histograms) - current_streak] / fps, 1) if fps > 0 else 0
        consecutive_similar.append({"start": t, "count": current_streak})

    if not consecutive_similar:
        return {"status": "pass", "comment": "類似カットの3連続以上はありません"}

    details = [f"{s['start']}秒付近で{s['count']}連続" for s in consecutive_similar]
    return {
        "status": "warn" if len(consecutive_similar) <= 2 else "fail",
        "comment": f"類似シーンが連続している箇所あり: {', '.join(details)}"
    }


def check_faces(cap, fps, total_frames):
    """顔検出（肖像権チェック）"""
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    face_frames = []
    sample_count = min(30, total_frames)
    interval = max(total_frames // sample_count, 1)

    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))

        if len(faces) > 0:
            timestamp = round(i / fps, 1) if fps > 0 else 0
            face_frames.append({"timestamp": timestamp, "count": len(faces)})

    if not face_frames:
        return {"status": "pass", "comment": "顔は検出されませんでした"}

    timestamps = [f"{f['timestamp']}秒" for f in face_frames[:10]]
    return {
        "status": "warn",
        "comment": f"顔が検出されたフレーム: {', '.join(timestamps)}（計{len(face_frames)}箇所）。モザイク処理の確認が必要です"
    }


def check_color(cap, fps, total_frames):
    """彩度/明度・白飛びチェック"""
    overexposed_frames = []
    low_saturation_frames = []
    sample_count = min(20, total_frames)
    interval = max(total_frames // sample_count, 1)

    brightness_values = []
    saturation_values = []

    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        mean_v = np.mean(v)
        mean_s = np.mean(s)
        brightness_values.append(mean_v)
        saturation_values.append(mean_s)

        timestamp = round(i / fps, 1) if fps > 0 else 0

        # 白飛び: 明度が高すぎるピクセルが多い
        overexposed_ratio = np.sum(v > 240) / v.size
        if overexposed_ratio > 0.3:
            overexposed_frames.append(timestamp)

        # 低彩度
        if mean_s < 30:
            low_saturation_frames.append(timestamp)

    issues = []
    status = "pass"

    if overexposed_frames:
        issues.append(f"白飛び: {', '.join([str(t) + '秒' for t in overexposed_frames[:5]])}付近")
        status = "warn"

    if low_saturation_frames:
        issues.append(f"低彩度: {', '.join([str(t) + '秒' for t in low_saturation_frames[:5]])}付近")
        status = "warn"

    if len(overexposed_frames) > len(brightness_values) * 0.3:
        status = "fail"

    avg_brightness = round(np.mean(brightness_values), 1) if brightness_values else 0
    avg_saturation = round(np.mean(saturation_values), 1) if saturation_values else 0

    if not issues:
        return {
            "status": "pass",
            "comment": f"色調は適正です（平均明度: {avg_brightness}/255, 平均彩度: {avg_saturation}/255）"
        }

    return {
        "status": status,
        "comment": f"{'; '.join(issues)}（平均明度: {avg_brightness}, 平均彩度: {avg_saturation}）"
    }


def extract_preview_frames(cap, fps, total_frames, count=8):
    """プレビュー用フレームを抽出してbase64で返す"""
    frames = []
    interval = max(total_frames // count, 1)

    for i in range(0, total_frames, interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        scale = min(400 / w, 400 / h, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        b64 = base64.b64encode(buf).decode("utf-8")
        timestamp = round(i / fps, 2) if fps > 0 else 0
        frames.append({"base64": b64, "timestamp": timestamp})

        if len(frames) >= count:
            break

    return frames


def run_auto_checks(video_path, post_type):
    """全自動チェックを実行"""
    cap, metadata = get_video_info(video_path)
    if cap is None:
        return None, None, None

    fps = metadata["fps"]
    total_frames = metadata["total_frames"]

    # シーン変化検出
    scene_changes = detect_scene_changes(cap, fps, total_frames)

    # 各自動チェック実行
    auto_results = {}

    checklist = CHECKLISTS[post_type]
    for cat in checklist["categories"].values():
        for item in cat["items"]:
            check_type = item.get("auto")
            if not check_type:
                continue

            item_id = item["id"]

            if check_type == "cut_duration":
                auto_results[item_id] = check_cut_duration(scene_changes, fps)
            elif check_type == "similar_scenes":
                auto_results[item_id] = check_similar_scenes(cap, scene_changes, fps)
            elif check_type == "face_detect":
                auto_results[item_id] = check_faces(cap, fps, total_frames)
            elif check_type == "color_check":
                auto_results[item_id] = check_color(cap, fps, total_frames)

    # プレビューフレーム
    preview_frames = extract_preview_frames(cap, fps, total_frames)

    cap.release()
    return metadata, auto_results, preview_frames


# ──────────────────────────────────────────────
# ルーティング
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/checklists")
def get_checklists():
    return jsonify(CHECKLISTS)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        if "video" not in request.files:
            return jsonify({"error": "動画ファイルが選択されていません"}), 400

        video = request.files["video"]
        post_type = request.form.get("post_type", "pr")

        if post_type not in CHECKLISTS:
            return jsonify({"error": "無効な投稿タイプです"}), 400

        # 動画を一時保存
        suffix = Path(video.filename).suffix or ".mp4"
        tmp = tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, suffix=suffix, delete=False)
        video.save(tmp.name)
        tmp.close()

        try:
            metadata, auto_results, preview_frames = run_auto_checks(tmp.name, post_type)

            if metadata is None:
                return jsonify({"error": "動画の読み込みに失敗しました。ファイル形式を確認してください。"}), 400

            return jsonify({
                "metadata": metadata,
                "auto_results": auto_results,
                "preview_frames": preview_frames,
                "checklist": CHECKLISTS[post_type],
            })
        finally:
            os.unlink(tmp.name)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"エラーが発生しました: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5555)
