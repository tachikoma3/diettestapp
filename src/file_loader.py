"""アップロードされたファイルを、拡張子ではなく内容から判別して読み込む.

.txt に保存された JSON / XML / CSV も、拡張子に関係なく同じように扱える。
src/file_loader.py として配置する想定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# BOM付きUTF-8 → UTF-8 → Shift_JIS系(Excel等で保存した日本語CSV)の順に試す
_ENCODINGS = ("utf-8-sig", "utf-8", "cp932")

# 形式判定に使う先頭部分の長さ
_HEAD_CHARS = 2000


@dataclass(frozen=True)
class LoadedFile:
    """読み込み結果.

    kind:    "json" | "xml" | "csv"
    raw:     元のバイト列(XMLパーサーなど、bytesを受け取る処理向け)
    text:    デコード済みテキスト
    payload: json の場合はパース済みオブジェクト、csv は text と同じ、
             xml は None(巨大なため全文デコードしない)
    """

    kind: str
    raw: bytes
    text: str
    payload: Any


def decode_text(raw: bytes) -> str:
    """文字コードを順に試してデコードする."""
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "文字コードを判別できませんでした。"
        "UTF-8 または Shift_JIS で保存し直してください。"
    )


def detect_format(text: str) -> str:
    """テキスト(先頭部分だけでも可)の内容から json / xml / csv を判定する."""
    head = text.lstrip("\ufeff \t\r\n")[:_HEAD_CHARS]
    if not head:
        raise ValueError("ファイルが空です。")

    if head.startswith(("{", "[")):
        return "json"
    if head.startswith("<"):
        return "xml"

    first_line = head.splitlines()[0]
    if "," in first_line or "\t" in first_line:
        return "csv"

    raise ValueError(
        "JSON / XML / CSV のいずれの形式としても判別できませんでした。"
    )


def load_upload(uploaded_file) -> LoadedFile:
    """st.file_uploader の戻り値を読み込み、形式を判定して返す.

    read() は再実行時に空になるため getvalue() を使う。
    XMLは巨大になりうる(HealthKitは100MB超)ので、全文をデコードせず
    先頭部分だけで判定する。XMLの text / payload は空(None)になるため、
    XMLは raw をパーサーへ渡すこと。
    """
    raw = uploaded_file.getvalue()

    # 先頭だけで形式を判定(途中で切れたマルチバイト文字は無視)
    head = raw[:4096].decode("utf-8-sig", errors="ignore")
    if not head.strip():
        # UTF-8で読めない場合はShift_JIS系として先頭を判定
        head = raw[:4096].decode("cp932", errors="ignore")
    kind = detect_format(head)

    if kind == "xml":
        return LoadedFile(kind=kind, raw=raw, text="", payload=None)

    text = decode_text(raw)
    if kind == "json":
        # 壊れたJSONはここで json.JSONDecodeError(ValueErrorの子)になる
        payload: Any = json.loads(text)
    else:
        payload = text

    return LoadedFile(kind=kind, raw=raw, text=text, payload=payload)


def require_kind(loaded: LoadedFile, source_name: str, *allowed: str) -> None:
    """データソースが対応しない形式なら、分かりやすいエラーにする."""
    if loaded.kind not in allowed:
        expected = " / ".join(k.upper() for k in allowed)
        raise ValueError(
            f"{source_name} は {expected} 形式に対応しています。"
            f"アップロードされたファイルは {loaded.kind.upper()} 形式でした。"
        )
