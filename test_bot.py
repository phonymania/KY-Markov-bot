import os
import random
import re
import markovify
from janome.tokenizer import Tokenizer

# ── 1. マルコフ連鎖用のテキストを作る関数 ──
def create_markov_model():
    if not os.path.exists("source.txt"):
        print("【エラー】同じフォルダに 'source.txt' が見つかりません！")
        return None

    with open("source.txt", "r", encoding="utf-8") as f:
        text = f.read()

    if len(text.strip()) == 0:
        print("【エラー】'source.txt' の中身が空っぽです！")
        return None

    # ① 数字をすべて消す
    text = re.sub(r"[0-9０-９]", "", text)

    # ② システム系の不要な単語を消し去る
    unwanted_words = [
        "分前", "時間前", "更新順", "非表示", 
        "新着順", "お気に入り", "ログイン", "マイページ"
    ]
    for word in unwanted_words:
        text = text.replace(word, "")

    print("→ Janomeで文章をバラバラに分解中...（高速化モード）")
    t = Tokenizer()
    
    # ── 高速化のための修正 ──
    # 全体を一度に処理せず、空じゃない行だけをリスト化
    raw_lines = [line.strip() for line in text.replace("。", "\n").split("\n") if line.strip()]
    
    # データ量が多すぎる場合のフリーズ対策：最大でも直近の300行に絞る
    if len(raw_lines) > 300:
        raw_lines = random.sample(raw_lines, 300) # ランダムに300行を間引く

    processed_lines = []
    for line in raw_lines:
        # 1行ずつ分解してスペースで繋ぐ（重い処理を小分けにする）
        words = [token.surface for token in t.tokenize(line)]
        processed_lines.append(" ".join(words))

    # 分解した文章を合体
    space_separated_text = "\n".join(processed_lines)

    print("→ マルコフ連鎖のテーブルを作成中...")
    model = markovify.Text(space_separated_text, state_size=2, well_formed=False)
    return model

# ── 2. フォルダ内から動画をランダムに選ぶ関数 ──
def get_random_video():
    video_dir = "./videos"
    if not os.path.exists(video_dir):
        print(f"【エラー】フォルダ '{video_dir}' が見つかりません！")
        return "動画フォルダなし"

    videos = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
    if not videos:
        print("【エラー】videosフォルダの中に .mp4 動画が1つもありません！")
        return "動画ファイルなし"

    return os.path.join(video_dir, random.choice(videos))

# ── 3. テスト実行メイン処理 ──
def test_main():
    print("=== ボットの動作テストを開始します ===")
    
    model = create_markov_model()
    if not model:
        print("テストを中止します。")
        return

    print("\n=== テストリプライを5件、連続で画面に出力します ===\n")

    virtual_user = "test_user_desu"

    for i in range(1, 6):
        print(f"--- テスト生成 #{i} ---")
        
        reply_text = model.make_short_sentence(max_chars=130, tries=100)
        if not reply_text:
            reply_text = model.make_short_sentence(max_chars=80, tries=100)
            
        if not reply_text:
            reply_text = "（文章の自動生成に失敗しました）"
        else:
            reply_text = reply_text.replace(" ", "")

        video_path = get_random_video()

        print(f"【送信予定のアカウント】: @{virtual_user}")
        print(f"【送信予定の怪文書テキスト】:\n{reply_text}")
        print(f"【添付される動画パス】: {video_path}")
        print("-" * 30 + "\n")

    print("=== テスト出力が完了しました ===")

if __name__ == "__main__":
    test_main()
