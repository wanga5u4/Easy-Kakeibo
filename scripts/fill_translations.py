# -*- coding: utf-8 -*-
from pathlib import Path

from babel.messages import pofile

JA_TRANSLATIONS = {
    "Bug 报告": "バグ報告",
    "功能建议": "機能のご要望",
    "使用问题": "使い方の質問",
    "新建": "新規",
    "处理中": "確認中",
    "已解决": "解決済み",
    "有效": "有効",
    "已停用": "無効",
    "已过期": "期限切れ",
    "反馈类型无效": "フィードバックの種類が無効です",
    "标题长度需要在 2 到 100 个字符之间": "タイトルは2文字以上100文字以内で入力してください",
    "详细内容不能为空": "詳細内容を入力してください",
    "详细内容长度需要在 5 到 2000 个字符之间": "詳細内容は5文字以上2000文字以内で入力してください",
    "%(month)s 收支概览": "%(month)s 収支概要",
    "请至少选择一项分享内容": "共有内容を少なくとも1つ選択してください",
    "有效期无效": "有効期限が無効です",
    "链接已复制": "リンクをコピーしました",
    "复制失败，请手动复制链接。": "コピーに失敗しました。リンクを手動でコピーしてください。",
    "反馈已提交，感谢你的帮助。": "ご意見を送信しました。ご協力ありがとうございます。",
    "分享链接已创建。": "共有リンクを作成しました。",
    "分享链接已停用。": "共有リンクを無効にしました。",
    "分享链接不存在。": "共有リンクが見つかりません。",
    "分享链接已启用。": "共有リンクを有効にしました。",
    "分享链接已删除。": "共有リンクを削除しました。",
    "这个分享链接不存在或已被删除。": "この共有リンクは存在しないか、削除されています。",
    "链接已停用": "リンクは無効です",
    "这个分享链接已停用。": "この共有リンクは無効になっています。",
    "链接已过期": "リンクの有効期限が切れています",
    "这个分享链接已过期。": "この共有リンクの有効期限が切れています。",
    "分享": "共有",
    "分享链接": "共有リンク",
    "反馈与建议": "ご意見・ご要望",
    "告诉我们哪里可以变得更好，或提交你遇到的问题。": "改善してほしい点や、発生した問題をお知らせください。",
    "标题": "タイトル",
    "详细内容": "詳細内容",
    "当前页面": "現在のページ",
    "仅作为普通文本保存，不会用于跳转。": "通常のテキストとして保存され、リダイレクトには使用されません。",
    "联系方式": "連絡先",
    "可选，仅用于管理员联系你，不会展示给其他用户。": "任意項目です。管理者からの連絡のみに使用され、他のユーザーには表示されません。",
    "最近反馈": "最近のフィードバック",
    "你还没有提交过反馈。": "まだご意見は送信されていません。",
    "暂无数据": "データがありません",
    "收入分类汇总": "収入カテゴリ集計",
    "此页面仅展示用户主动分享的汇总信息，不包含完整交易明细。": "このページには、ユーザーが共有を許可した集計情報のみが表示され、取引の詳細は含まれていません。",
    "创建只包含月度汇总的公开链接，不分享完整交易明细。": "月次集計のみを含む公開リンクを作成します。取引の詳細は共有されません。",
    "创建分享链接": "共有リンクを作成",
    "分享标题": "共有タイトル",
    "分享月份": "共有月",
    "有效期": "有効期限",
    "1 天": "1日",
    "7 天": "7日",
    "30 天": "30日",
    "永久": "無期限",
    "分享说明": "共有説明",
    "分享内容": "共有内容",
    "已创建分享链接": "作成済み共有リンク",
    "创建时间": "作成日時",
    "到期时间": "有効期限",
    "浏览次数": "閲覧数",
    "公开链接": "公開リンク",
    "复制链接": "リンクをコピー",
    "停用": "無効化",
    "启用": "有効化",
    "还没有创建分享链接。": "共有リンクはまだ作成されていません。",
}


def fill_zh_cn():
    path = Path("translations") / "zh_CN" / "LC_MESSAGES" / "messages.po"
    with path.open("r", encoding="utf-8") as file:
        catalog = pofile.read_po(file)

    for message in catalog:
        if message.id and not message.string:
            message.string = message.id
            message.flags.discard("fuzzy")

    with path.open("wb") as file:
        pofile.write_po(file, catalog, width=100)


def fill_ja():
    path = Path("translations") / "ja" / "LC_MESSAGES" / "messages.po"
    with path.open("r", encoding="utf-8") as file:
        catalog = pofile.read_po(file)

    for message in catalog:
        if message.id in JA_TRANSLATIONS:
            message.string = JA_TRANSLATIONS[message.id]
            message.flags.discard("fuzzy")

    with path.open("wb") as file:
        pofile.write_po(file, catalog, width=100)


def list_missing(locale):
    path = Path("translations") / locale / "LC_MESSAGES" / "messages.po"
    with path.open("r", encoding="utf-8") as file:
        catalog = pofile.read_po(file)

    return [message.id for message in catalog if message.id and not message.string]


if __name__ == "__main__":
    fill_zh_cn()
    fill_ja()
    missing_ja = list_missing("ja")
    if missing_ja:
        print("Missing ja translations:")
        for message_id in missing_ja:
            print(f"- {message_id}")
