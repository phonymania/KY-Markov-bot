import time
import requests
from bs4 import BeautifulSoup

def scrape_website_to_text(url, output_file="source.txt"):
    print(f"ターゲットURL: {url} からテキストを取得中...")
    
    # 相手のサーバーに迷惑をかけないための「人間のブラウザのフリ」をする設定
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        # ウェブページのデータを取得
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding  # 文字化け対策
        
        if response.status_code != 200:
            print(f"【エラー】アクセスできませんでした（ステータスコード: {response.status_code}）")
            return

        # HTMLを解析する
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 一般的なウェブサイトの「段落（<p>タグ）」や「divタグ」から文字を拾う
        paragraphs = soup.find_all(["p", "div"])
        
        extracted_lines = []
        for p in paragraphs:
            text = p.get_text().strip()
            
            # 短すぎる行や、メニューの文字を弾くフィルター
            if len(text) > 15 and not text.startswith("javascript:"):
                extracted_lines.append(text)

        # 重複する文章を削る
        unique_lines = list(set(extracted_lines))

        # 取得した文字をファイルに書き込む
        with open(output_file, "a", encoding="utf-8") as f:
            for line in unique_lines:
                f.write(line + "\n")
                
        print(f"成功！ {len(unique_lines)} 行のテキストを '{output_file}' に追加しました。")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

# ── メイン実行部分 ──
if __name__ == "__main__":
    # ここに集めたいサイトのURLを入力（テスト用の仮URLです）
    target_urls = [
		"https://example.com",
    ]
    
    print("=== スクレイピングを開始します ===")
    
    for url in target_urls:
        scrape_website_to_text(url)
        print("相手のサーバーに配慮して5秒間待機します...")
        time.sleep(5)
        
    print("=== すべてのスクレイピングが完了しました ===")
