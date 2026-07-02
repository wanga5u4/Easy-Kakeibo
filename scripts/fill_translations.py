# -*- coding: utf-8 -*-
from pathlib import Path

from babel.messages import pofile


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


def list_missing(locale):
    path = Path("translations") / locale / "LC_MESSAGES" / "messages.po"
    with path.open("r", encoding="utf-8") as file:
        catalog = pofile.read_po(file)

    return [message.id for message in catalog if message.id and not message.string]


if __name__ == "__main__":
    fill_zh_cn()
    missing_ja = list_missing("ja")
    if missing_ja:
        print("Missing ja translations:")
        for message_id in missing_ja:
            print(f"- {message_id}")
