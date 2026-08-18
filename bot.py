import os
import random
import re
import asyncio
import logging
from pathlib import Path

import markovify
from janome.tokenizer import Tokenizer
from dotenv import load_dotenv
from twikit import Client


# ============================================================
# 設定
# ============================================================

load_dotenv()

BOT_USERNAME = os.getenv("X_USERNAME")
AUTH_TOKEN = os.getenv("X_AUTH_TOKEN")
CT0 = os.getenv("X_CT0")

SOURCE_FILE = Path("source.txt")
VIDEO_DIR = Path("videos")
REPLIED_FILE = Path("replied_ids.txt")

# メンション確認間隔
CHECK_INTERVAL = 60

# 返信前の待機時間
MIN_WAIT = 15
MAX_WAIT = 45

# 取得する通知数
NOTIFICATION_COUNT = 40

# マルコフ連鎖の最大文字数
MAX_REPLY_LENGTH = 130

# source.txt 最大使用行数
MAX_SOURCE_LINES = 300


# ============================================================
# ログ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("AirBot")


# ============================================================
# マルコフ連鎖モデル
# ============================================================

def create_markov_model():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"{SOURCE_FILE} がありません。"
        )

    text = SOURCE_FILE.read_text(
        encoding="utf-8"
    )

    # 数字除去
    text = re.sub(
        r"[0-9０-９]",
        "",
        text
    )

    # 不要な文字列を除去
    unwanted_words = [
        "分前",
        "時間前",
        "更新順",
        "非表示",
        "新着順",
    ]

    for word in unwanted_words:
        text = text.replace(word, "")

    tokenizer = Tokenizer()

    raw_lines = [
        line.strip()
        for line in text.replace(
            "。",
            "\n"
        ).split("\n")
        if line.strip()
    ]

    if not raw_lines:
        raise ValueError(
            "source.txt に有効な文章がありません。"
        )

    # データが多すぎる場合
    if len(raw_lines) > MAX_SOURCE_LINES:
        raw_lines = random.sample(
            raw_lines,
            MAX_SOURCE_LINES
        )

    processed_lines = []

    for line in raw_lines:

        words = [
            token.surface
            for token in tokenizer.tokenize(line)
        ]

        if words:
            processed_lines.append(
                " ".join(words)
            )

    if not processed_lines:
        raise ValueError(
            "文章をマルコフ連鎖用に変換できませんでした。"
        )

    model_text = "\n".join(
        processed_lines
    )

    model = markovify.Text(
        model_text,
        state_size=1,
        well_formed=False,
    )

    logger.info(
        "マルコフモデル作成完了: %d行",
        len(processed_lines)
    )

    return model


# ============================================================
# 文章生成
# ============================================================

def generate_reply(model):

    # 長め
    for max_chars in (
        MAX_REPLY_LENGTH,
        100,
        80,
        60,
    ):

        try:

            text = model.make_short_sentence(
                max_chars=max_chars,
                tries=100,
            )

            if text:

                # Janome処理時の空白を除去
                text = text.replace(
                    " ",
                    ""
                )

                if text.strip():
                    return text

        except Exception as e:

            logger.warning(
                "文章生成エラー: %s",
                e
            )

    return "（空気を読まない沈黙）"


# ============================================================
# 動画取得
# ============================================================

def get_random_video():

    if not VIDEO_DIR.exists():

        logger.warning(
            "%s が存在しません。",
            VIDEO_DIR
        )

        return None

    videos = [
        path
        for path in VIDEO_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".mp4"
    ]

    if not videos:

        logger.warning(
            "動画がありません。"
        )

        return None

    return random.choice(videos)


# ============================================================
# 返信済みID
# ============================================================

def load_replied_ids():

    if not REPLIED_FILE.exists():
        return set()

    try:

        return {
            line.strip()
            for line in REPLIED_FILE.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        }

    except Exception as e:

        logger.warning(
            "返信済みIDの読み込み失敗: %s",
            e
        )

        return set()


def save_replied_id(tweet_id):

    try:

        with REPLIED_FILE.open(
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                f"{tweet_id}\n"
            )

    except Exception as e:

        logger.error(
            "返信済みIDの保存失敗: %s",
            e
        )


# ============================================================
# Twifork接続
# ============================================================

async def create_client():

    if not BOT_USERNAME:
        raise RuntimeError(
            "X_USERNAME がありません。"
        )

    if not AUTH_TOKEN:
        raise RuntimeError(
            "X_AUTH_TOKEN がありません。"
        )

    if not CT0:
        raise RuntimeError(
            "X_CT0 がありません。"
        )

    client = Client(
        "ja-JP"
    )

    client.set_cookies({
        "auth_token": AUTH_TOKEN,
        "ct0": CT0,
    })

    return client


# ============================================================
# メンション取得
# ============================================================

async def get_mentions(client):
    """
    通知APIに依存せず、X検索からBotへのメンションTweetを取得する。

    Twifork 2.3.5 の notifications/mentions.json は、現在のXでは
    HTTP 200でも globalObjects が空になることが確認できたため、
    to:ユーザー名 と @ユーザー名 の検索を使用する。
    """

    found = {}

    queries = [
        f"to:{BOT_USERNAME}",
        f"@{BOT_USERNAME}",
        f"@{BOT_USERNAME} -from:{BOT_USERNAME}",
    ]

    for query in queries:
        try:
            logger.info(
                "メンション検索開始: query=%s",
                query
            )

            result = await client.search_tweet(
                query,
                "Latest",
                count=NOTIFICATION_COUNT
            )

            result_count = 0

            for tweet in result:
                result_count += 1

                tweet_id = str(
                    getattr(tweet, "id", "")
                )

                if not tweet_id:
                    continue

                tweet_user = getattr(
                    tweet,
                    "user",
                    None
                )

                screen_name = getattr(
                    tweet_user,
                    "screen_name",
                    ""
                )

                # Bot自身のTweetは除外
                if (
                    screen_name
                    and screen_name.lower()
                    == BOT_USERNAME.lower()
                ):
                    continue

                tweet_text = getattr(
                    tweet,
                    "text",
                    ""
                ) or ""

                mention = f"@{BOT_USERNAME}".lower()

                # 実際のTweet本文にBotへのメンションがあるものだけ採用
                if mention not in tweet_text.lower():
                    continue

                found[tweet_id] = tweet

            logger.info(
                "検索結果: query=%s, 取得=%d件, 累計採用=%d件",
                query,
                result_count,
                len(found)
            )

        except Exception as e:
            logger.warning(
                "メンション検索失敗: query=%s, error=%s",
                query,
                e
            )

    mentions = list(found.values())

    # 古いTweetから処理
    try:
        mentions.sort(
            key=lambda tweet: int(tweet.id)
        )
    except Exception:
        pass

    logger.info(
        "最終的なメンション件数: %d件",
        len(mentions)
    )

    for tweet in mentions:
        user = getattr(
            tweet,
            "user",
            None
        )

        username = getattr(
            user,
            "screen_name",
            "unknown"
        )

        logger.info(
            "メンション採用: Tweet ID=%s @%s",
            tweet.id,
            username
        )

    return mentions


# ============================================================
# 起動時の既存メンションを既読扱い
# ============================================================

async def initialize_replied_ids(
    client,
    replied_ids
):

    logger.info(
        "既存メンションを確認しています..."
    )

    mentions = await get_mentions(
        client
    )

    count = 0

    for tweet in mentions:

        tweet_id = str(
            tweet.id
        )

        if tweet_id not in replied_ids:

            replied_ids.add(
                tweet_id
            )

            count += 1

    logger.info(
        "既存メンション %d件をスキップ対象にしました。",
        count
    )


# ============================================================
# 1件のメンションを処理
# ============================================================


async def upload_video_for_reply(client, video_path):
    """
    動画をXへアップロードし、create_tweet() に渡すmedia_idを返す。

    Twiforkのバージョンによって upload_media() の戻り値が
    文字列 / オブジェクト / dict のいずれでも扱えるようにする。
    """
    logger.info(
        "動画アップロード開始: %s",
        video_path
    )

    # 動画は FINALIZE が200でも、X側の動画処理が完了しているとは限らない。
    # Twikitの upload_media() は wait_for_completion=True にすると
    # processing_info が succeeded になるまで待機できる。
    uploaded = await client.upload_media(
        str(video_path),
        wait_for_completion=True,
        status_check_interval=1.0,
    )

    media_id = None

    # 文字列としてmedia_idが返る場合
    if isinstance(uploaded, str):
        media_id = uploaded

    # dictとして返る場合
    elif isinstance(uploaded, dict):
        media_id = (
            uploaded.get("media_id_string")
            or uploaded.get("media_id")
            or uploaded.get("id")
        )

    # オブジェクトとして返る場合
    else:
        media_id = getattr(
            uploaded,
            "media_id_string",
            None
        )

        if media_id is None:
            media_id = getattr(
                uploaded,
                "media_id",
                None
            )

        if media_id is None:
            media_id = getattr(
                uploaded,
                "id",
                None
            )

    # Twifork 2.3.5 の upload_media() は環境によって
    # media_id を int で返すことがある。
    # したがって int / str のどちらも有効なmedia_idとして扱う。
    if isinstance(uploaded, (int, str)):
        media_id = uploaded

    if media_id is None:
        raise RuntimeError(
            "upload_media() の戻り値からmedia_idを取得できませんでした: "
            f"{type(uploaded)!r}"
        )

    media_id = str(media_id)

    logger.info(
        "動画アップロード成功: media_id=%s",
        media_id
    )

    return media_id


async def process_mention(
    client,
    tweet,
    model,
    replied_ids
):

    tweet_id = str(tweet.id)

    if tweet_id in replied_ids:
        logger.info(
            "処理済みTweetのためスキップ: Tweet ID=%s",
            tweet_id
        )
        return

    user = getattr(tweet, "user", None)

    if user is None:
        logger.warning(
            "ユーザー情報を取得できません: %s",
            tweet_id
        )
        return

    username = user.screen_name

    if username.lower() == BOT_USERNAME.lower():
        replied_ids.add(tweet_id)
        return

    logger.info("========================================")
    logger.info("【メンション検知】")
    logger.info("ユーザー: @%s", username)
    logger.info("Tweet ID: %s", tweet_id)
    logger.info("本文: %s", getattr(tweet, "text", ""))

    wait_time = random.randint(MIN_WAIT, MAX_WAIT)
    logger.info("%d秒待機します...", wait_time)
    await asyncio.sleep(wait_time)

    if tweet_id in replied_ids:
        return

    reply_text = generate_reply(model)
    full_text = f"@{username} {reply_text}"

    logger.info("返信文: %s", full_text)

    # --------------------------------------------------------
    # 動画付き返信を試す
    # --------------------------------------------------------
    # 324の原因調査を兼ねて、動画アップロード→media_idsで投稿する。
    # Twifork/X側で動画metadataが不足する場合はテキスト返信へフォールバック。
    # --------------------------------------------------------

    video_path = get_random_video()

    if video_path:
        try:
            media_id = await upload_video_for_reply(
                client,
                video_path
            )

            logger.info(
                "動画付きTweet送信開始: reply_to=%s media_id=%s",
                tweet_id,
                media_id
            )

            result = await client.create_tweet(
                text=full_text,
                media_ids=[str(media_id)],
                reply_to=tweet_id,
            )

            sent_id = getattr(
                result,
                "id",
                "unknown"
            )

            logger.info(
                "【動画付き返信成功】@%s / reply_to=%s / sent_id=%s",
                username,
                tweet_id,
                sent_id
            )

            replied_ids.add(tweet_id)
            save_replied_id(tweet_id)

            logger.info("========================================")
            return

        except Exception as e:
            logger.exception(
                "動画付き返信失敗: %s",
                e
            )

            logger.warning(
                "動画付き返信に失敗したため、テキストのみで再試行します。"
            )

    # --------------------------------------------------------
    # 動画なし / 動画返信失敗時の安全なフォールバック
    # --------------------------------------------------------

    try:
        logger.info(
            "Tweet送信開始（テキストのみ）: reply_to=%s",
            tweet_id
        )

        result = await client.create_tweet(
            text=full_text,
            reply_to=tweet_id,
        )

        sent_id = getattr(
            result,
            "id",
            "unknown"
        )

        logger.info(
            "【返信成功】@%s / reply_to=%s / sent_id=%s",
            username,
            tweet_id,
            sent_id
        )

        replied_ids.add(tweet_id)
        save_replied_id(tweet_id)

        logger.info("========================================")

    except Exception as e:
        logger.exception(
            "Tweet送信失敗: %s",
            e
        )


# ============================================================
# メイン監視
# ============================================================

async def main():

    logger.info(
        "========================================"
    )

    logger.info(
        " 空気を読まないBot"
    )

    logger.info(
        " Twifork 2.3.x"
    )

    logger.info(
        "========================================"
    )

    # --------------------------------------------------------
    # マルコフモデル
    # --------------------------------------------------------

    try:

        model = create_markov_model()

    except Exception as e:

        logger.critical(
            "モデル作成失敗: %s",
            e
        )

        return

    # --------------------------------------------------------
    # 返信済みID
    # --------------------------------------------------------

    replied_ids = load_replied_ids()

    logger.info(
        "保存済み返信ID: %d件",
        len(replied_ids)
    )

    # --------------------------------------------------------
    # X接続
    # --------------------------------------------------------

    try:

        client = await create_client()

        logger.info(
            "@%s に接続しています...",
            BOT_USERNAME
        )

        user = await client.get_user_by_screen_name(
            BOT_USERNAME
        )

        logger.info(
            "ログイン確認成功"
        )

        logger.info(
            "Bot ID: %s",
            user.id
        )

    except Exception as e:

        logger.critical(
            "X接続失敗: %s",
            e
        )

        return

    # --------------------------------------------------------
    # 起動時の既存メンションを無視する処理は行わない
    # --------------------------------------------------------
    #
    # 注意:
    # get_mentions() は検索APIを使用しているため、起動直後に
    # 見つかったTweetをここで replied_ids に入れてしまうと、
    # そのTweetが process_mention() に届く前に
    # 「処理済み」と判定されてしまう。
    #
    # 返信に成功したTweetだけを replied_ids に保存する。
    #
    logger.info(
        "起動時のメンション事前スキップは無効化しています。"
    )

    # --------------------------------------------------------
    # 監視開始
    # --------------------------------------------------------

    logger.info(
        "メンション監視開始"
    )

    logger.info(
        "確認間隔: %d秒",
        CHECK_INTERVAL
    )

    while True:

        try:

            mentions = await get_mentions(
                client
            )

            if mentions:

                # 古いものから処理
                try:

                    mentions = sorted(
                        mentions,
                        key=lambda x: int(x.id)
                    )

                except Exception:
                    pass

            for tweet in mentions:

                tweet_id = str(
                    tweet.id
                )

                if tweet_id in replied_ids:
                    logger.info(
                        "処理済みTweetのためスキップ: Tweet ID=%s",
                        tweet_id
                    )
                    continue

                await process_mention(
                    client,
                    tweet,
                    model,
                    replied_ids
                )

                # 連続処理防止
                await asyncio.sleep(
                    random.randint(
                        3,
                        8
                    )
                )

        except asyncio.CancelledError:

            logger.info(
                "Botを停止します。"
            )

            raise

        except Exception as e:

            logger.exception(
                "監視ループでエラーが発生しました: %s",
                e
            )

            await asyncio.sleep(
                60
            )

        await asyncio.sleep(
            CHECK_INTERVAL
        )


# ============================================================
# 起動
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "Ctrl+Cで終了しました。"
        )
