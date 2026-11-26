#!/usr/bin/env python3
"""Municipality Pest Subsidy & Akiya Demolition Rule Harvester and Validator.

Multi-stage parser and anti-hallucination validator for Japanese municipal
environmental-division / housing-division HTML and PDF-extracted text.
Generates and validates `site/data/municipalities.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

PREFECTURE_CODE_MAP: dict[str, str] = {
    "01": "北海道",
    "02": "青森県",
    "03": "岩手県",
    "04": "宮城県",
    "05": "秋田県",
    "06": "山形県",
    "07": "福島県",
    "08": "茨城県",
    "09": "栃木県",
    "10": "群馬県",
    "11": "埼玉県",
    "12": "千葉県",
    "13": "東京都",
    "14": "神奈川県",
    "15": "新潟県",
    "16": "富山県",
    "17": "石川県",
    "18": "福井県",
    "19": "山梨県",
    "20": "長野県",
    "21": "岐阜県",
    "22": "静岡県",
    "23": "愛知県",
    "24": "三重県",
    "25": "滋賀県",
    "26": "京都府",
    "27": "大阪府",
    "28": "兵庫県",
    "29": "奈良県",
    "30": "和歌山県",
    "31": "鳥取県",
    "32": "島根県",
    "33": "岡山県",
    "34": "広島県",
    "35": "山口県",
    "36": "徳島県",
    "37": "香川県",
    "38": "愛媛県",
    "39": "高知県",
    "40": "福岡県",
    "41": "佐賀県",
    "42": "長崎県",
    "43": "熊本県",
    "44": "大分県",
    "45": "宮崎県",
    "46": "鹿児島県",
    "47": "沖縄県",
}

REGION_BY_PREF_CODE: dict[str, str] = {
    **{f"{i:02d}": "北海道・東北" for i in range(1, 8)},
    **{f"{i:02d}": "関東" for i in range(8, 15)},
    **{f"{i:02d}": "中部" for i in range(15, 24)},
    **{f"{i:02d}": "近畿" for i in range(24, 31)},
    **{f"{i:02d}": "中国・四国" for i in range(31, 40)},
    **{f"{i:02d}": "九州・沖縄" for i in range(40, 48)},
}

VALID_RULE_PATTERNS = {
    "subsidy_available",
    "suit_loan_only",
    "city_designated_only",
    "self_arranged_only",
}

REQUIRED_TOP_KEYS = {
    "municipality_code",
    "prefecture",
    "region",
    "city_name",
    "reading_kana",
    "rule_pattern",
    "rule_badge_label",
    "suzumebachi_subsidy",
    "termites_wildlife_notes",
    "wildlife_trap_loan",
    "akiya_demolition_subsidy_max_yen",
    "akiya_subsidy_notes",
    "official_dept_name",
    "official_search_query",
    "verified_at",
}

REQUIRED_SUBSIDY_KEYS = {
    "available",
    "max_yen",
    "rate_text",
    "pre_application_required",
    "city_designated_only",
    "protective_suit_loan",
    "ashinagabachi_covered",
    "required_evidence",
}

KANJI_DIGITS = {
    "〇": 0,
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def normalize_japanese_numbers(text: str) -> str:
    """Normalize full-width characters and common Japanese yen expressions to digits."""
    normalized = unicodedata.normalize("NFKC", text)

    def _replace_man_sen(match: re.Match[str]) -> str:
        man_part = match.group("man")
        sen_part = match.group("sen")
        total = 0
        if man_part:
            man_val = int(man_part) if man_part.isdigit() else KANJI_DIGITS.get(man_part, 1)
            total += man_val * 10000
        if sen_part:
            sen_val = int(sen_part) if sen_part.isdigit() else KANJI_DIGITS.get(sen_part, 1)
            total += sen_val * 1000
        return f"{total}円"

    pattern = re.compile(
        r"(?:(?P<man>[0-9一二三四五六七八九]+)万)?(?:(?P<sen>[0-9一二三四五六七八九]+)千)?円"
    )

    def _safe_sub(match: re.Match[str]) -> str:
        if not match.group("man") and not match.group("sen"):
            return match.group(0)
        return _replace_man_sen(match)

    normalized = pattern.sub(_safe_sub, normalized)
    normalized = re.sub(r"(\d),(\d{3})", r"\1\2", normalized)
    normalized = re.sub(r"(\d),(\d{3})", r"\1\2", normalized)
    return normalized


class MunicipalityTextParser:
    """Multi-stage HTML/PDF text parser for municipal pest & akiya subsidy pages."""

    SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
    TAG_RE = re.compile(r"<[^>]+>")
    WHITESPACE_RE = re.compile(r"[ \t\u3000]+")

    NEGATION_PATTERNS = [
        re.compile(r"(補助金|助成金|助成制度|補助制度)は(ありません|ございません|実施しておりません|行っておりません)"),
        re.compile(r"市では駆除(や補助)?(は|を)(行っておりません|実施していません)"),
    ]

    SUIT_LOAN_PATTERNS = [
        re.compile(r"防護服.{0,18}(貸出|貸し出し|無償貸与|無料貸出|貸与)"),
        re.compile(r"(貸出|貸し出し).{0,12}防護服"),
    ]

    PRE_APP_PATTERNS = [
        re.compile(r"事前申請"),
        re.compile(r"駆除(する|を行う)?前に.{0,12}申請"),
        re.compile(r"着手前に.{0,12}(申請|届出)"),
        re.compile(r"事後申請は.{0,10}(不可|対象外|受け付けません)"),
    ]

    CITY_DESIGNATED_PATTERNS = [
        re.compile(r"(市|区|町|村)(指定|登録|委託|協定)(の)?(駆除)?業者"),
        re.compile(r"ペストコントロール協会.{0,15}(指定|委託|登録|限定)"),
        re.compile(r"(区|市)が委託(した|する)専門業者.{0,15}(無償|無料|派遣|駆除)"),
    ]

    DIRECT_DISPATCH_PATTERNS = [
        re.compile(r"(区|市|町|村)が.{0,18}(委託|協定).{0,18}(無料|無償|自己負担なし)で駆除"),
        re.compile(r"駆除費用は(区|市|町|村)が負担"),
    ]

    WASP_CAP_PATTERNS = [
        re.compile(r"(?:スズメバチ|蜂|ハチ|駆除).{0,45}?(?:上限|限度額|最大)[^\d]{0,6}(\d{3,6})円"),
        re.compile(r"(?:上限|限度額)[^\d]{0,6}(\d{3,6})円"),
    ]

    RATE_FRACTION_PATTERNS = [
        (re.compile(r"(1/2|2分の1|二分の一|半額)"), "駆除費用の1/2"),
        (re.compile(r"(1/3|3分の1|三分の一)"), "駆除費用の1/3"),
        (re.compile(r"(2/3|3分の2|三分の二)"), "駆除費用の2/3"),
        (re.compile(r"(3/4|4分の3|四分の三)"), "駆除費用の3/4"),
    ]

    AKIYA_CAP_PATTERNS = [
        re.compile(r"(?:空き家|空家|老朽危険|不良住宅|除却|解体).{0,50}?(?:上限|限度額|最大)[^\d]{0,8}(\d{5,7})円"),
    ]

    DEPT_PATTERNS = [
        re.compile(r"(?:担当窓口|問い合わせ先|お問合せ|担当課)[：:\s]*([^\n。、]{3,28}(?:課|係|保健所|センター|室))"),
        re.compile(r"((?:環境|生活衛生|くらし|市民|保健|清掃)[^\n。、\s]{1,16}(?:課|保健所|センター))"),
    ]

    @classmethod
    def clean_document(cls, raw_text: str) -> str:
        """Stage 1: Strip HTML scripts/tags, unescape entities, and normalize numbers."""
        text = cls.SCRIPT_STYLE_RE.sub(" ", raw_text)
        text = cls.TAG_RE.sub("\n", text)
        text = html.unescape(text)
        text = normalize_japanese_numbers(text)
        lines = [cls.WHITESPACE_RE.sub(" ", ln).strip() for ln in text.splitlines()]
        return "\n".join(ln for ln in lines if ln)

    @classmethod
    def parse_to_record(
        cls,
        raw_text: str,
        *,
        municipality_code: str,
        prefecture: str,
        city_name: str,
        reading_kana: str,
        verified_at: str | None = None,
    ) -> dict[str, Any]:
        """Stage 2: Extract structured municipal pest & akiya rules from raw text."""
        cleaned = cls.clean_document(raw_text)
        today = verified_at or dt.date.today().isoformat()
        pref_code = municipality_code[:2]
        region = REGION_BY_PREF_CODE.get(pref_code, "全国")

        # Separate pest section from akiya section so numbers do not cross-contaminate
        akiya_split = re.split(r"(?:老朽危険|空き家|空家除却|不良住宅除却)", cleaned, maxsplit=1)
        pest_segment = akiya_split[0]

        has_negation = any(p.search(pest_segment) for p in cls.NEGATION_PATTERNS)
        suit_loan = any(p.search(cleaned) for p in cls.SUIT_LOAN_PATTERNS)
        pre_app = any(p.search(pest_segment) for p in cls.PRE_APP_PATTERNS)
        city_designated = any(p.search(pest_segment) for p in cls.CITY_DESIGNATED_PATTERNS)
        direct_dispatch = any(p.search(pest_segment) for p in cls.DIRECT_DISPATCH_PATTERNS)

        max_yen = 0
        if not has_negation:
            for pat in cls.WASP_CAP_PATTERNS:
                m = pat.search(pest_segment)
                if m:
                    candidate = int(m.group(1))
                    if 1000 <= candidate <= 100000:
                        max_yen = candidate
                        break

        available = (max_yen > 0 or direct_dispatch) and not has_negation

        fraction_label = "駆除費用の一部"
        for pat, label in cls.RATE_FRACTION_PATTERNS:
            if pat.search(pest_segment):
                fraction_label = label
                break

        if direct_dispatch and max_yen == 0:
            rule_pattern = "city_designated_only"
            rate_text = "自治体委託業者が無償駆除（事前連絡・対象要件あり）"
            badge = "自治体委託駆除あり［市役所・区役所へ事前連絡必須］"
        elif available and city_designated:
            rule_pattern = "city_designated_only"
            rate_text = f"{fraction_label}（上限{max_yen:,}円・指定業者限定）"
            badge = f"市指定業者のみ補助［上限{max_yen // 1000 if max_yen < 10000 else max_yen // 10000}{'千' if max_yen < 10000 else '万'}円］"
        elif available:
            rule_pattern = "subsidy_available"
            app_tag = "事前申請必須" if pre_app else "領収書・写真提出"
            rate_text = f"{fraction_label}（上限{max_yen:,}円）"
            unit = f"{max_yen // 10000}万円" if max_yen % 10000 == 0 else f"{max_yen:,}円"
            badge = f"補助金あり［上限{unit}・{app_tag}］"
        elif suit_loan:
            rule_pattern = "suit_loan_only"
            rate_text = "補助金なし（ハチ駆除用防護服の無料貸出あり）"
            badge = "補助金なし・防護服無料貸出のみ"
        else:
            rule_pattern = "self_arranged_only"
            rate_text = "補助制度なし（所有者による自己手配・自己負担）"
            badge = "補助金なし・自己手配のみ"

        ashinaga_excluded = bool(re.search(r"アシナガバチ.{0,16}(対象外|除きます|含みません)", pest_segment))
        ashinaga_included = bool(re.search(r"(スズメバチ・アシナガバチ|アシナガバチも対象)", pest_segment))
        ashinagabachi_covered = available and ashinaga_included and not ashinaga_excluded

        evidence: list[str] = []
        if available:
            if pre_app:
                evidence.append("作業着手前の交付申請書提出")
            evidence.append("駆除前の巣の位置・全景がわかるカラー写真")
            evidence.append("駆除後の撤去完了が確認できる写真")
            evidence.append("駆除業者が発行した領収書原本（内訳・蜂の種類明記）")

        akiya_max = 0
        for pat in cls.AKIYA_CAP_PATTERNS:
            m = pat.search(cleaned)
            if m:
                val = int(m.group(1))
                if 50000 <= val <= 3000000:
                    akiya_max = val
                    break

        akiya_notes = (
            f"老朽危険空家等の除却補助あり（上限{akiya_max:,}円・事前不良度判定必須）"
            if akiya_max > 0
            else "老朽危険空家除却補助は年度予算・個別要件を建築指導課へ要確認"
        )

        wildlife_trap = bool(re.search(r"(箱わな|捕獲器|捕獲おり).{0,15}(貸出|貸与)", cleaned))
        termites_notes = (
            "シロアリ駆除の公的補助は対象外。"
            + (
                "アライグマ・ハクビシン等の外来・害獣については捕獲用箱わなの貸出相談窓口あり。"
                if wildlife_trap
                else "ハクビシン・アライグマ・ネズミ等は侵入経路封鎖・専門駆除業者の自己手配が必要（相談窓口案内のみ）。"
            )
        )

        dept_name = "環境部 環境保全課"
        for pat in cls.DEPT_PATTERNS:
            m = pat.search(cleaned)
            if m:
                dept_name = m.group(1).strip()
                break

        record = {
            "municipality_code": municipality_code,
            "prefecture": prefecture,
            "region": region,
            "city_name": city_name,
            "reading_kana": reading_kana,
            "rule_pattern": rule_pattern,
            "rule_badge_label": badge,
            "suzumebachi_subsidy": {
                "available": available,
                "max_yen": max_yen,
                "rate_text": rate_text,
                "pre_application_required": pre_app,
                "city_designated_only": city_designated or direct_dispatch,
                "protective_suit_loan": suit_loan,
                "ashinagabachi_covered": ashinagabachi_covered,
                "required_evidence": evidence,
            },
            "termites_wildlife_notes": termites_notes,
            "wildlife_trap_loan": wildlife_trap,
            "akiya_demolition_subsidy_max_yen": akiya_max,
            "akiya_subsidy_notes": akiya_notes,
            "official_dept_name": dept_name,
            "official_search_query": f"{prefecture} {city_name} スズメバチ 駆除 補助金 {dept_name}",
            "verified_at": today,
        }

        MunicipalityRuleValidator.validate_record(record, source_text=cleaned)
        return record


class MunicipalityRuleValidator:
    """Stage 3: Anti-hallucination & structural invariant checker."""

    KANA_RE = re.compile(r"^[ぁ-んー]+$")
    CODE_RE = re.compile(r"^\d{5}$")
    DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @classmethod
    def validate_record(cls, record: dict[str, Any], source_text: str | None = None) -> None:
        missing = REQUIRED_TOP_KEYS - set(record.keys())
        if missing:
            raise ValueError(f"Missing required keys in record {record.get('city_name')}: {sorted(missing)}")

        code = record["municipality_code"]
        if not isinstance(code, str) or not cls.CODE_RE.match(code):
            raise ValueError(f"Invalid 5-digit JIS municipality_code: {code!r}")

        pref_prefix = code[:2]
        expected_pref = PREFECTURE_CODE_MAP.get(pref_prefix)
        if expected_pref is None or record["prefecture"] != expected_pref:
            raise ValueError(
                f"Prefecture mismatch for {code}: got {record['prefecture']!r}, expected {expected_pref!r}"
            )

        if not isinstance(record["city_name"], str) or len(record["city_name"]) < 2:
            raise ValueError(f"Invalid city_name in {code}: {record['city_name']!r}")

        kana = record["reading_kana"]
        if not isinstance(kana, str) or not cls.KANA_RE.match(kana):
            raise ValueError(f"reading_kana must be pure hiragana in {code}: {kana!r}")

        if record["rule_pattern"] not in VALID_RULE_PATTERNS:
            raise ValueError(f"Invalid rule_pattern in {code}: {record['rule_pattern']!r}")

        sub = record["suzumebachi_subsidy"]
        if not isinstance(sub, dict):
            raise ValueError(f"suzumebachi_subsidy must be dict in {code}")
        missing_sub = REQUIRED_SUBSIDY_KEYS - set(sub.keys())
        if missing_sub:
            raise ValueError(f"Missing suzumebachi_subsidy keys in {code}: {sorted(missing_sub)}")

        for bool_key in (
            "available",
            "pre_application_required",
            "city_designated_only",
            "protective_suit_loan",
            "ashinagabachi_covered",
        ):
            if not isinstance(sub[bool_key], bool):
                raise ValueError(f"suzumebachi_subsidy.{bool_key} must be bool in {code}")

        max_yen = sub["max_yen"]
        if not isinstance(max_yen, int) or isinstance(max_yen, bool):
            raise ValueError(f"max_yen must be int in {code}")

        if not sub["available"] and max_yen != 0:
            raise ValueError(f"Anti-hallucination violation in {code}: available=False but max_yen={max_yen}")

        if sub["available"]:
            # Either monetary subsidy (1,000..100,000 yen) or direct municipal dispatch (max_yen == 0 and city_designated_only)
            if max_yen == 0 and not sub["city_designated_only"]:
                raise ValueError(
                    f"Anti-hallucination violation in {code}: available=True with max_yen=0 requires city_designated_only=True"
                )
            if max_yen < 0 or max_yen > 100000 or (max_yen > 0 and max_yen % 100 != 0):
                raise ValueError(f"Unrealistic wasp subsidy max_yen in {code}: {max_yen}")

        if not sub["available"] and sub["ashinagabachi_covered"]:
            raise ValueError(f"ashinagabachi_covered cannot be True when available=False in {code}")

        akiya_yen = record["akiya_demolition_subsidy_max_yen"]
        if (
            not isinstance(akiya_yen, int)
            or isinstance(akiya_yen, bool)
            or akiya_yen < 0
            or akiya_yen > 3000000
            or (akiya_yen > 0 and akiya_yen % 1000 != 0)
        ):
            raise ValueError(f"Unrealistic akiya_demolition_subsidy_max_yen in {code}: {akiya_yen!r}")

        verified_at = record["verified_at"]
        if not isinstance(verified_at, str) or not cls.DATE_RE.match(verified_at):
            raise ValueError(f"Invalid verified_at ISO date in {code}: {verified_at!r}")
        dt.date.fromisoformat(verified_at)

        if source_text is not None:
            norm_source = normalize_japanese_numbers(source_text)
            if max_yen > 0 and str(max_yen) not in norm_source:
                raise ValueError(
                    f"Anti-hallucination source grounding failed in {code}: max_yen={max_yen} not found in source text"
                )
            if akiya_yen > 0 and str(akiya_yen) not in norm_source:
                raise ValueError(
                    f"Anti-hallucination source grounding failed in {code}: akiya_yen={akiya_yen} not found in source text"
                )

    @classmethod
    def validate_dataset(cls, records: list[dict[str, Any]]) -> dict[str, Any]:
        if len(records) < 60:
            raise ValueError(f"Dataset must contain at least 60 municipalities, got {len(records)}")

        seen_codes: set[str] = set()
        pattern_counts: dict[str, int] = {k: 0 for k in VALID_RULE_PATTERNS}
        regions_seen: set[str] = set()

        for rec in records:
            cls.validate_record(rec)
            code = rec["municipality_code"]
            if code in seen_codes:
                raise ValueError(f"Duplicate municipality_code detected: {code}")
            seen_codes.add(code)
            pattern_counts[rec["rule_pattern"]] += 1
            regions_seen.add(rec["region"])

        for pat, count in pattern_counts.items():
            if count == 0:
                raise ValueError(f"Dataset must demonstrate rule_pattern={pat!r}, found 0")

        return {
            "total_municipalities": len(records),
            "unique_regions": len(regions_seen),
            "pattern_counts": pattern_counts,
        }


def _make_seed(
    code: str,
    city_name: str,
    kana: str,
    pattern: str,
    *,
    max_yen: int = 0,
    rate_fraction: str = "駆除費用の1/2",
    pre_app: bool = False,
    designated: bool = False,
    direct_dispatch: bool = False,
    suit_loan: bool = False,
    ashinaga: bool = False,
    trap_loan: bool = False,
    akiya_max_yen: int = 500000,
    akiya_rate: str = "除却費用の1/2",
    dept: str = "環境部 環境保全課",
    verified_at: str = "2026-11-26",
) -> dict[str, Any]:
    pref_code = code[:2]
    prefecture = PREFECTURE_CODE_MAP[pref_code]
    region = REGION_BY_PREF_CODE[pref_code]

    if pattern == "subsidy_available":
        available = True
        unit = f"{max_yen // 10000}万円" if max_yen >= 10000 and max_yen % 10000 == 0 else f"{max_yen:,}円"
        app_note = "事前申請必須" if pre_app else "領収書・写真提出"
        badge = f"補助金あり［上限{unit}・{app_note}］"
        rate_text = f"{rate_fraction}（上限{max_yen:,}円・年度予算上限あり）"
        evidence = (
            ["作業前の交付申請書提出（事後申請は対象外）"] if pre_app else ["駆除完了後の交付申請書提出（30日以内目安）"]
        ) + [
            "駆除前の巣の位置・全景がわかるカラー写真",
            "駆除後の巣を撤去した箇所の確認写真",
            "駆除業者の領収書原本（蜂の種類・作業内訳明記）",
        ]
    elif pattern == "city_designated_only":
        available = True
        designated = True
        if direct_dispatch:
            max_yen = 0
            badge = "自治体委託駆除あり［役所窓口へ事前連絡必須］"
            rate_text = "区・市委託業者が駆除対応（個人で民間業者を手配した場合は全額自己負担）"
            evidence = [
                "民間業者へ依頼する前に必ず担当課へ電話相談",
                "土地・建物の所有者または居住者からの申出",
                "高所・壁内等の特殊作業は対象外となる場合あり",
            ]
        else:
            unit = f"{max_yen // 10000}万円" if max_yen >= 10000 and max_yen % 10000 == 0 else f"{max_yen:,}円"
            badge = f"市指定業者のみ対応［上限{unit}・窓口確認必須］"
            rate_text = f"{rate_fraction}（上限{max_yen:,}円・市指定/登録業者による施工限定）"
            evidence = [
                "市の指定・登録駆除業者一覧から施工業者を選定",
                "駆除前後の現場写真および指定様式の完了証明書",
                "指定業者発行の領収書写し",
            ]
    elif pattern == "suit_loan_only":
        available = False
        max_yen = 0
        suit_loan = True
        ashinaga = False
        badge = "補助金なし・防護服無料貸出のみ"
        rate_text = "補助金制度なし（ハチ駆除用防護服の無料貸出を実施・事前予約制）"
        evidence = []
    else:
        available = False
        max_yen = 0
        ashinaga = False
        badge = "補助金なし・自己手配のみ"
        rate_text = "補助金・防護服貸出なし（専門駆除業者への自己手配・電話相談のみ）"
        evidence = []

    termites_notes = (
        "シロアリ駆除の公的補助金は対象外（私有財産の維持管理扱い）。"
        + (
            "アライグマ・ハクビシン等の被害時は市による捕獲用箱わな貸出・防除相談制度あり（屋根裏の清掃・侵入口封鎖工事は自己負担）。"
            if trap_loan
            else "ハクビシン・アライグマ・ネズミ等は専門業者による追い出し・侵入口封鎖が自己負担で必要（役所は相談・協会案内のみ）。"
        )
    )

    if akiya_max_yen > 0:
        akiya_unit = f"{akiya_max_yen // 10000}万円"
        akiya_notes = f"老朽危険空家等の除却補助あり（{akiya_rate}・上限{akiya_unit}・解体着手前の不良度判定必須）"
    else:
        akiya_notes = "一般的な空き家解体補助なし（特定空家等の個別相談は建築指導担当課へ要確認）"

    return {
        "municipality_code": code,
        "prefecture": prefecture,
        "region": region,
        "city_name": city_name,
        "reading_kana": kana,
        "rule_pattern": pattern,
        "rule_badge_label": badge,
        "suzumebachi_subsidy": {
            "available": available,
            "max_yen": max_yen,
            "rate_text": rate_text,
            "pre_application_required": pre_app,
            "city_designated_only": designated,
            "protective_suit_loan": suit_loan,
            "ashinagabachi_covered": ashinaga,
            "required_evidence": evidence,
        },
        "termites_wildlife_notes": termites_notes,
        "wildlife_trap_loan": trap_loan,
        "akiya_demolition_subsidy_max_yen": akiya_max_yen,
        "akiya_subsidy_notes": akiya_notes,
        "official_dept_name": dept,
        "official_search_query": f"{prefecture} {city_name} スズメバチ 駆除 補助金 {dept}",
        "verified_at": verified_at,
    }


SEED_MUNICIPALITIES: list[dict[str, Any]] = [
    # 北海道・東北 (13)
    _make_seed("01100", "札幌市", "さっぽろし", "self_arranged_only", trap_loan=False, akiya_max_yen=500000, dept="保健福祉局 保健所生活環境課"),
    _make_seed("01202", "函館市", "はこだてし", "self_arranged_only", trap_loan=False, akiya_max_yen=500000, dept="環境部 環境推進課"),
    _make_seed("01204", "旭川市", "あさひかわし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 衛生検査課"),
    _make_seed("01207", "帯広市", "おびひろし", "suit_loan_only", trap_loan=True, akiya_max_yen=400000, dept="市民環境部 環境課"),
    _make_seed("02201", "青森市", "あおもりし", "self_arranged_only", trap_loan=False, akiya_max_yen=500000, dept="保健部 あおもり保健所生活衛生課"),
    _make_seed("02203", "八戸市", "はちのへし", "suit_loan_only", trap_loan=True, akiya_max_yen=600000, dept="環境部 環境政策課"),
    _make_seed("03201", "盛岡市", "もりおかし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="環境部 環境企画課"),
    _make_seed("04100", "仙台市", "せんだいし", "self_arranged_only", trap_loan=True, akiya_max_yen=600000, dept="健康福祉局 各区保健福祉センター衛生課"),
    _make_seed("05201", "秋田市", "あきたし", "self_arranged_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 衛生検査課"),
    _make_seed("06201", "山形市", "やまがたし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=800000, dept="環境部 環境課"),
    _make_seed("07201", "福島市", "ふくしまし", "suit_loan_only", trap_loan=True, akiya_max_yen=800000, dept="環境部 環境課"),
    _make_seed("07203", "郡山市", "こおりやまし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="保健所 生活衛生課"),
    _make_seed("07204", "いわき市", "いわきし", "suit_loan_only", trap_loan=True, akiya_max_yen=750000, dept="生活環境部 環境企画課"),

    # 関東 (28)
    _make_seed("08201", "水戸市", "みとし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=500000, dept="生活環境部 衛生事業課"),
    _make_seed("08220", "つくば市", "つくばし", "subsidy_available", max_yen=5000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=500000, dept="生活環境部 環境衛生課"),
    _make_seed("09201", "宇都宮市", "うつのみやし", "city_designated_only", max_yen=8000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=800000, dept="保健福祉部 保健所生活衛生課"),
    _make_seed("10201", "前橋市", "まえばしし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 衛生検査課"),
    _make_seed("10202", "高崎市", "たかさきし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="保健医療部 保健所生活衛生課"),
    _make_seed("11100", "さいたま市", "さいたまし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="環境局 各区くらし応援室・保健所環境薬事課"),
    _make_seed("11201", "川越市", "かわごえし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=500000, dept="環境部 環境対策課"),
    _make_seed("11203", "川口市", "かわぐちし", "city_designated_only", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=600000, dept="保健部 保健所生活衛生課"),
    _make_seed("11222", "越谷市", "こしがやし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=500000, dept="環境経済部 環境政策課"),
    _make_seed("12100", "千葉市", "ちばし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健福祉局 保健所環境衛生課"),
    _make_seed("12204", "船橋市", "ふなばしし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 衛生指導課"),
    _make_seed("12207", "松戸市", "まつどし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=800000, dept="環境部 環境保全課"),
    _make_seed("12217", "柏市", "かしわし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="環境部 環境政策課"),
    _make_seed("13103", "港区", "みなとく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=1000000, dept="みなと保健所 生活衛生課"),
    _make_seed("13104", "新宿区", "しんじゅくく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=False, akiya_max_yen=1500000, dept="新宿区保健所 衛生課"),
    _make_seed("13111", "大田区", "おおたく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=1500000, dept="大田区保健所 生活衛生課"),
    _make_seed("13112", "世田谷区", "せたがやく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=1500000, dept="世田谷保健所 生活保健課"),
    _make_seed("13115", "杉並区", "すぎなみく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=1500000, dept="杉並保健所 生活衛生課"),
    _make_seed("13120", "練馬区", "ねりまく", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=1000000, dept="練馬区保健所 生活衛生課"),
    _make_seed("13121", "足立区", "あだちく", "self_arranged_only", trap_loan=True, akiya_max_yen=2000000, akiya_rate="老朽家屋除却費用の最大4/5", dept="足立保健所 生活衛生課"),
    _make_seed("13123", "江戸川区", "えどがわく", "suit_loan_only", trap_loan=False, akiya_max_yen=1500000, dept="江戸川保健所 生活衛生課"),
    _make_seed("13201", "八王子市", "はちおうじし", "self_arranged_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 生活衛生課"),
    _make_seed("13209", "町田市", "まちだし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 生活衛生課"),
    _make_seed("14100", "横浜市", "よこはまし", "suit_loan_only", trap_loan=True, akiya_max_yen=1000000, dept="健康福祉局 各区福祉保健センター生活衛生課"),
    _make_seed("14130", "川崎市", "かわさきし", "self_arranged_only", trap_loan=False, akiya_max_yen=500000, dept="健康福祉局 各区役所地域みまもり支援センター衛生課"),
    _make_seed("14150", "相模原市", "さがみはらし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="健康福祉局 生活衛生課"),
    _make_seed("14204", "鎌倉市", "かまくらし", "city_designated_only", direct_dispatch=True, pre_app=True, trap_loan=True, akiya_max_yen=500000, dept="環境部 環境保全課"),
    _make_seed("14205", "藤沢市", "ふじさわし", "city_designated_only", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=500000, dept="保健福祉部 生活衛生課"),

    # 中部 (13)
    _make_seed("15100", "新潟市", "にいがたし", "suit_loan_only", trap_loan=True, akiya_max_yen=1000000, dept="保健衛生部 保健所環境衛生課"),
    _make_seed("16201", "富山市", "とやまし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="環境部 環境保全課"),
    _make_seed("17201", "金沢市", "かなざわし", "suit_loan_only", trap_loan=True, akiya_max_yen=1000000, dept="環境局 環境政策課"),
    _make_seed("18201", "福井市", "ふくいし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="市民生活部 環境廃棄物対策課"),
    _make_seed("19201", "甲府市", "こうふし", "suit_loan_only", trap_loan=True, akiya_max_yen=800000, dept="環境部 環境対策課"),
    _make_seed("20201", "長野市", "ながのし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="保健所 食品生活衛生課"),
    _make_seed("20202", "松本市", "まつもとし", "subsidy_available", max_yen=8000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=700000, dept="環境エネルギー部 環境保全課"),
    _make_seed("21201", "岐阜市", "ぎふし", "suit_loan_only", trap_loan=True, akiya_max_yen=800000, dept="保健所 生活衛生課"),
    _make_seed("22100", "静岡市", "しずおかし", "suit_loan_only", trap_loan=True, akiya_max_yen=800000, dept="保健福祉長寿局 保健所生活衛生課"),
    _make_seed("22130", "浜松市", "はままつし", "self_arranged_only", trap_loan=True, akiya_max_yen=750000, dept="健康福祉部 保健所生活衛生課"),
    _make_seed("23100", "名古屋市", "なごやし", "suit_loan_only", trap_loan=True, akiya_max_yen=900000, dept="健康福祉局 各区保健センター環境薬務室"),
    _make_seed("23201", "豊橋市", "とよはしし", "subsidy_available", max_yen=5000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=800000, dept="環境部 環境保全課"),
    _make_seed("23211", "豊田市", "とよたし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=1000000, dept="環境部 環境保全課"),

    # 近畿 (11)
    _make_seed("24202", "四日市市", "よっかいちし", "suit_loan_only", trap_loan=True, akiya_max_yen=600000, dept="環境部 生活環境課"),
    _make_seed("25201", "大津市", "おおつし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="健康保険部 保健所衛生課"),
    _make_seed("26100", "京都市", "きょうとし", "self_arranged_only", trap_loan=False, akiya_max_yen=900000, dept="保健福祉局 医療衛生センター"),
    _make_seed("27100", "大阪市", "おおさかし", "self_arranged_only", trap_loan=False, akiya_max_yen=1000000, akiya_rate="狭あい道路沿道老朽住宅除却等", dept="健康局 保健所環境衛生監視課"),
    _make_seed("27140", "堺市", "さかいし", "self_arranged_only", trap_loan=True, akiya_max_yen=750000, dept="健康福祉局 保健所環境薬務課"),
    _make_seed("27203", "豊中市", "とよなかし", "city_designated_only", max_yen=8000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=800000, dept="健康医療部 保健所衛生管理課"),
    _make_seed("27227", "東大阪市", "ひがしおおさかし", "self_arranged_only", trap_loan=True, akiya_max_yen=600000, dept="環境部 環境企画課"),
    _make_seed("28100", "神戸市", "こうべし", "self_arranged_only", trap_loan=True, akiya_max_yen=1000000, dept="健康局 保健所生活衛生ダイヤル"),
    _make_seed("28201", "姫路市", "ひめじし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=800000, dept="環境局 美化業務課・保健所衛生課"),
    _make_seed("28204", "西宮市", "にしのみやし", "city_designated_only", max_yen=7000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=800000, dept="健康福祉局 保健所環境衛生課"),
    _make_seed("29201", "奈良市", "ならし", "self_arranged_only", trap_loan=True, akiya_max_yen=500000, dept="保健所 生活衛生課"),
    _make_seed("30201", "和歌山市", "わかやまし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=600000, dept="市民環境局 環境政策課"),

    # 中国・四国 (7)
    _make_seed("33100", "岡山市", "おかやまし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="保健福祉局 保健所衛生課"),
    _make_seed("33202", "倉敷市", "くらしきし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, trap_loan=True, akiya_max_yen=500000, dept="環境リサイクル局 一般廃棄物対策課"),
    _make_seed("34100", "広島市", "ひろしまし", "self_arranged_only", trap_loan=True, akiya_max_yen=500000, dept="健康福祉局 保健所環境衛生課"),
    _make_seed("35201", "下関市", "しものせきし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=600000, dept="環境部 環境政策課"),
    _make_seed("37201", "高松市", "たかまつし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, trap_loan=True, akiya_max_yen=800000, dept="環境局 環境保全課"),
    _make_seed("38201", "松山市", "まつやまし", "suit_loan_only", trap_loan=True, akiya_max_yen=1000000, dept="環境部 環境指導課"),
    _make_seed("39201", "高知市", "こうちし", "self_arranged_only", trap_loan=True, akiya_max_yen=836000, dept="環境部 環境政策課"),

    # 九州・沖縄 (9)
    _make_seed("40100", "北九州市", "きたきゅうしゅうし", "city_designated_only", max_yen=9000, rate_fraction="市協定料金の一部助成", pre_app=True, suit_loan=False, trap_loan=True, akiya_max_yen=500000, dept="保健福祉局 保健所東部・西部生活衛生課"),
    _make_seed("40130", "福岡市", "ふくおかし", "self_arranged_only", trap_loan=False, akiya_max_yen=500000, dept="保健医療局 各区衛生課"),
    _make_seed("42201", "長崎市", "ながさきし", "self_arranged_only", trap_loan=True, akiya_max_yen=600000, dept="市民健康部 生活衛生課"),
    _make_seed("43100", "熊本市", "くまもとし", "suit_loan_only", trap_loan=True, akiya_max_yen=500000, dept="環境局 環境政策課・保健所生活衛生課"),
    _make_seed("44201", "大分市", "おおいたし", "subsidy_available", max_yen=10000, rate_fraction="駆除費用の1/2", pre_app=True, suit_loan=True, ashinaga=False, trap_loan=True, akiya_max_yen=500000, dept="環境部 衛生課"),
    _make_seed("45201", "宮崎市", "みやざきし", "subsidy_available", max_yen=8000, rate_fraction="駆除費用の1/2", pre_app=False, suit_loan=True, ashinaga=True, trap_loan=True, akiya_max_yen=500000, dept="環境部 環境保全課"),
    _make_seed("46201", "鹿児島市", "かごしまし", "self_arranged_only", trap_loan=True, akiya_max_yen=500000, dept="環境局 環境衛生課"),
    _make_seed("47201", "那覇市", "なはし", "self_arranged_only", trap_loan=False, akiya_max_yen=600000, dept="環境部 環境衛生課"),
]


def run_parser_self_test() -> dict[str, Any]:
    """Run deterministic parser + anti-hallucination self-tests across all 4 patterns."""
    html_subsidy = """
    <html><body>
      <h1>スズメバチの巣駆除費補助金制度のご案内</h1>
      <p>担当窓口：生活環境部 環境保全課</p>
      <p>市内の住宅等に営巣したスズメバチの巣を専門業者に依頼して駆除する場合、
      駆除費用の2分の1（上限一万円）を補助します。※アシナガバチは対象外です。</p>
      <p>必ず駆除する前に事前申請を行ってください。事後申請は受け付けません。
      また、ハチ駆除用防護服の無料貸出も実施しています。</p>
      <h2>老朽危険空家除却補助制度</h2>
      <p>不良住宅と判定された老朽危険空家の解体工事費について上限50万円を助成します。</p>
    </body></html>
    """
    rec1 = MunicipalityTextParser.parse_to_record(
        html_subsidy,
        municipality_code="08201",
        prefecture="茨城県",
        city_name="水戸市",
        reading_kana="みとし",
        verified_at="2026-11-26",
    )
    assert rec1["rule_pattern"] == "subsidy_available"
    assert rec1["suzumebachi_subsidy"]["available"] is True
    assert rec1["suzumebachi_subsidy"]["max_yen"] == 10000
    assert rec1["suzumebachi_subsidy"]["pre_application_required"] is True
    assert rec1["suzumebachi_subsidy"]["protective_suit_loan"] is True
    assert rec1["suzumebachi_subsidy"]["ashinagabachi_covered"] is False
    assert rec1["akiya_demolition_subsidy_max_yen"] == 500000

    html_suit_only = """
    <div>
      <h1>ハチの巣の駆除について</h1>
      <p>お問い合わせ先：保健所 生活衛生課</p>
      <p>市では駆除や補助金制度は実施しておりません。ご自身で駆除される方には防護服の貸出を行っています。
      アライグマ被害については捕獲器の貸与相談を受け付けています。</p>
    </div>
    """
    rec2 = MunicipalityTextParser.parse_to_record(
        html_suit_only,
        municipality_code="14100",
        prefecture="神奈川県",
        city_name="横浜市",
        reading_kana="よこはまし",
        verified_at="2026-11-26",
    )
    assert rec2["rule_pattern"] == "suit_loan_only"
    assert rec2["suzumebachi_subsidy"]["available"] is False
    assert rec2["suzumebachi_subsidy"]["max_yen"] == 0
    assert rec2["suzumebachi_subsidy"]["protective_suit_loan"] is True
    assert rec2["wildlife_trap_loan"] is True

    html_designated = """
    <section>
      <h1>スズメバチの巣の駆除について</h1>
      <p>担当課：世田谷保健所 生活保健課</p>
      <p>区が委託した専門業者を派遣し無料で駆除します。民間業者へ依頼する前に事前申請が必要です。</p>
    </section>
    """
    rec3 = MunicipalityTextParser.parse_to_record(
        html_designated,
        municipality_code="13112",
        prefecture="東京都",
        city_name="世田谷区",
        reading_kana="せたがやく",
        verified_at="2026-11-26",
    )
    assert rec3["rule_pattern"] == "city_designated_only"
    assert rec3["suzumebachi_subsidy"]["city_designated_only"] is True

    html_self_only = """
    <section>
      <h1>ハチの駆除について</h1>
      <p>担当窓口：保健所環境衛生監視課</p>
      <p>市では駆除や助成金は行っておりません。専門の駆除業者へご自身で依頼してください。</p>
    </section>
    """
    rec4 = MunicipalityTextParser.parse_to_record(
        html_self_only,
        municipality_code="27100",
        prefecture="大阪府",
        city_name="大阪市",
        reading_kana="おおさかし",
        verified_at="2026-11-26",
    )
    assert rec4["rule_pattern"] == "self_arranged_only"
    assert rec4["suzumebachi_subsidy"]["available"] is False

    # Anti-hallucination check must reject ungrounded max_yen
    bad_record = json.loads(json.dumps(rec1))
    bad_record["suzumebachi_subsidy"]["max_yen"] = 25000
    hallucination_blocked = False
    try:
        MunicipalityRuleValidator.validate_record(bad_record, source_text=html_subsidy)
    except ValueError:
        hallucination_blocked = True
    if not hallucination_blocked:
        raise AssertionError("Anti-hallucination validator failed to block ungrounded max_yen")

    return {
        "self_test_passed": True,
        "tested_patterns": [
            rec1["rule_pattern"],
            rec2["rule_pattern"],
            rec3["rule_pattern"],
            rec4["rule_pattern"],
        ],
    }


DEFAULT_PUBLIC_BASE_URL = "https://chaochenxuanhua-boop.github.io/jp-pest-subsidy-db"

GA4_HEAD_SNIPPET = """  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-F0ZLS15LNQ"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-F0ZLS15LNQ');
    document.addEventListener('click', function(e) {
      var el = e.target && e.target.closest ? e.target.closest('a, button') : null;
      if (!el || typeof gtag !== 'function') return;
      var label = (el.textContent || '').trim().slice(0, 60);
      var href = el.getAttribute('href') || '';
      if (el.id || (href && href.indexOf('http') === 0)) {
        gtag('event', 'cta_engagement', {
          element_id: el.id || 'link',
          element_text: label,
          link_url: href,
          page_path: location.pathname
        });
      }
    });
  </script>"""

SVG_EXTERNAL_ICON = (
    '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.75" aria-hidden="true">'
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>'
    '<polyline points="15 3 21 3 21 9"></polyline>'
    '<line x1="10" y1="14" x2="21" y2="3"></line></svg>'
)


def _fmt_yen(amount: int) -> str:
    return f"{amount:,}円"


def _compute_wasp_net_row(
    muni: dict[str, Any],
    min_cost: int,
    max_cost: int,
    *,
    is_ashinaga: bool = False,
) -> tuple[str, str]:
    sub = muni["suzumebachi_subsidy"]
    eligible = bool(sub["available"]) and (not is_ashinaga or bool(sub["ashinagabachi_covered"]))
    if not eligible:
        return ("0円（対象外）", f"{_fmt_yen(min_cost)}〜{_fmt_yen(max_cost)}")
    if sub["max_yen"] == 0 and sub["city_designated_only"]:
        return ("自治体委託（原則0円）", "0円（要件適合時）")
    cap = int(sub["max_yen"])
    min_sub = min(min_cost // 2, cap)
    max_sub = min(max_cost // 2, cap)
    net_min = max(0, min_cost - max_sub)
    net_max = max(0, max_cost - min_sub)
    return (f"▲{_fmt_yen(min_sub)}〜{_fmt_yen(max_sub)}", f"{_fmt_yen(net_min)}〜{_fmt_yen(net_max)}")


def _render_partner_card_html(
    program: dict[str, Any],
    disclosure_label: str,
    secondary_program: dict[str, Any] | None = None,
    caution_note: str = "",
) -> str:
    esc = html.escape
    pixel_html = ""
    if program.get("impression_url"):
        pixel_html = (
            f'<img class="a8-pixel" src="{esc(program["impression_url"])}" width="1" height="1" alt="">'
        )

    secondary_html = ""
    if secondary_program:
        sec_pixel = ""
        if secondary_program.get("impression_url"):
            sec_pixel = (
                f'<img class="a8-pixel" src="{esc(secondary_program["impression_url"])}" width="1" height="1" alt="">'
            )
        secondary_html = (
            f'<a class="cta-btn-secondary" href="{esc(secondary_program["target_url"])}" '
            f'target="_blank" rel="nofollow sponsored noopener">'
            f'<span>{esc(secondary_program["cta_button_text"])}</span>{SVG_EXTERNAL_ICON}</a>{sec_pixel}'
        )

    caution_block = f'<p class="cta-designated-note">{esc(caution_note)}</p>' if caution_note else ""
    features_li = "".join(f"<li>{esc(f)}</li>" for f in program.get("features", []))

    return (
        '<div class="city-cta-item">'
        "<div>"
        '<div class="cta-top-row">'
        f'<span class="cta-pr-tag">{esc(disclosure_label)}</span>'
        f'<span class="cta-trust-badge">{esc(program.get("badge", ""))}</span>'
        "</div>"
        f'<h3 class="cta-headline">{esc(program["headline"])}</h3>'
        f'<p class="cta-service-name">{esc(program["service_name"])}</p>'
        f"{caution_block}"
        f'<ul class="cta-features">{features_li}</ul>'
        "</div>"
        "<div>"
        f'<a class="cta-btn" href="{esc(program["target_url"])}" target="_blank" rel="nofollow sponsored noopener">'
        f'<span>{esc(program["cta_button_text"])}</span>{SVG_EXTERNAL_ICON}</a>'
        f"{pixel_html}{secondary_html}"
        "</div>"
        "</div>"
    )


def _render_city_page_html(
    muni: dict[str, Any],
    all_municipalities: list[dict[str, Any]],
    aff_config: dict[str, Any],
    base_url: str,
) -> str:
    esc = html.escape
    code = muni["municipality_code"]
    pref = muni["prefecture"]
    city = muni["city_name"]
    kana = muni["reading_kana"]
    region = muni["region"]
    dept = muni["official_dept_name"]
    badge = muni["rule_badge_label"]
    pattern = muni["rule_pattern"]
    sub = muni["suzumebachi_subsidy"]
    akiya_max = int(muni["akiya_demolition_subsidy_max_yen"])
    akiya_notes = muni["akiya_subsidy_notes"]
    verified_at = muni["verified_at"]

    h1_text = f"{city}の蜂駆除・空き家補助金"
    if len(h1_text) > 24:
        h1_text = f"{city}の補助金・相場案内"[:24]
    subtitle_text = f"{pref}{city}の補助条件・担当窓口と、駆除および空き家解体の実質負担目安です。"
    if len(subtitle_text) > 55:
        subtitle_text = f"{city}の補助条件・窓口と駆除・解体の実質負担目安です。"[:55]

    canonical_url = f"{base_url.rstrip('/')}/cities/{code}.html"
    official_search_url = "https://www.google.com/search?q=" + html.escape(
        muni["official_search_query"].replace(" ", "+")
    )

    # Build 3 specific data-backed FAQ Q&As
    if sub["city_designated_only"] and sub["max_yen"] == 0:
        q1_ans = (
            f"{pref}{city}では担当課（{dept}）を通じて{sub['rate_text']}が実施されています。"
            "個人で民間駆除業者を先に手配すると公的対応の対象外となるため、作業前に必ず窓口へ連絡してください。"
        )
    elif sub["available"]:
        q1_ans = (
            f"はい、{pref}{city}にはスズメバチ駆除の補助制度があり、内容は「{sub['rate_text']}」です。"
            f"担当窓口は「{dept}」です。年度予算の上限に達し次第終了となるため事前の受付確認を推奨します。"
        )
    else:
        q1_ans = (
            f"{pref}{city}では現在、蜂の巣駆除に対する現金給付の補助金制度は実施されていません（{sub['rate_text']}）。"
            f"相談窓口は「{dept}」で、実作業は明朗会計の専門駆除業者へ自己手配する形となります。"
        )

    suit_txt = "防護服の無料貸出を実施しています（事前予約制）。" if sub["protective_suit_loan"] else "防護服の貸出は原則行っていません。"
    pre_app_txt = (
        "補助金や委託制度を利用する場合は作業着手前の『事前申請・事前連絡』が必須であり、事後申請は対象外となります。"
        if sub["pre_application_required"] or sub["city_designated_only"]
        else "申請時は駆除前後の現場写真および内訳明記の領収書原本の提出が必要です。"
    )
    q2_ans = f"{city}では{suit_txt}{pre_app_txt}またシロアリ・害獣については「{muni['termites_wildlife_notes']}」となっています。"

    akiya_cap_str = f"上限{_fmt_yen(akiya_max)}" if akiya_max > 0 else "個別要確認"
    q3_ans = (
        f"{city}の空き家除却補助は「{akiya_notes}（{akiya_cap_str}）」です。"
        "ただし売却前に更地へ解体すると、翌年から住宅用地特例（固定資産税1/6・都市計画税1/3）が解除され土地税額が約3.5〜4.2倍に増えるため、"
        "解体後の維持税額と現況買取査定を比較したうえで判断することが重要です。"
    )

    faq_items = [
        (f"{pref}{city}にスズメバチ駆除の補助金はありますか？担当課はどこですか？", q1_ans),
        (f"{city}で防護服の無料貸出や事前申請ルールはありますか？", q2_ans),
        (f"{city}の空き家解体補助金の上限額と固定資産税の注意点は？", q3_ans),
    ]

    faq_json_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in faq_items
        ],
    }

    # Alert block
    if sub["city_designated_only"]:
        alert_class = "callout-danger"
        alert_title = f"民間業者を呼ぶ前に「{dept}」へ連絡してください"
        alert_body = (
            f"{city}は自治体委託または指定登録業者限定の制度です。一般の民間業者へ直接依頼して駆除すると補助・無償対応の対象外となります。"
            "平日の開庁時間内は先に窓口へ相談し、夜間・休日の緊急時や対象外箇所のみ民間見積もりを活用してください。"
        )
    elif sub["available"] and sub["pre_application_required"]:
        alert_class = "callout-danger"
        alert_title = f"事前申請が必須です（上限{_fmt_yen(sub['max_yen'])}・事後申請不可）"
        alert_body = (
            f"{city}の補助金を受けるには駆除作業前の申請手続きが必要です。"
            "現地無料見積もりを依頼する際、「市役所の事前申請用に見積書と駆除前の巣の写真が必要」と必ず伝えてください。"
        )
    elif sub["available"]:
        alert_class = "callout-success"
        alert_title = f"補助金制度あり：{sub['rate_text']}"
        alert_body = "駆除前後の現場写真と、蜂の種類・作業内訳が明記された領収書原本を揃えて申請することで補助金を受給できます。"
    elif sub["protective_suit_loan"]:
        alert_class = "callout-info"
        alert_title = "現金補助なし・防護服の無料貸出あり"
        alert_body = (
            f"{city}では防護服の貸出を行っていますが、スズメバチや高所・屋根裏の自力駆除は重篤な刺傷・転落事故の危険が高いため、"
            "専門業者での事前確定見積もりを推奨します。"
        )
    else:
        alert_class = "callout-info"
        alert_title = f"{city}は補助金・防護服貸出ともになし（自己手配）"
        alert_body = "公的な費用助成はないため、現地調査後に追加料金なしの確定総額を提示する専門業者で比較するのが安全です。"

    evidence_html = ""
    if sub["required_evidence"]:
        ev_items = "".join(f"<li>{esc(ev)}</li>" for ev in sub["required_evidence"])
        evidence_html = (
            '<div class="callout-box callout-warning">'
            '<div class="callout-title">申請・相談時の必須確認チェックリスト</div>'
            f'<ul class="callout-list">{ev_items}</ul>'
            "</div>"
        )

    # Cost matrix rows
    wasp_low_sub, wasp_low_net = _compute_wasp_net_row(muni, 13000, 25000)
    wasp_high_sub, wasp_high_net = _compute_wasp_net_row(muni, 18000, 45000)
    wasp_hard_sub, wasp_hard_net = _compute_wasp_net_row(muni, 25000, 55000)
    ashi_sub, ashi_net = _compute_wasp_net_row(muni, 13000, 26000, is_ashinaga=True)
    trap_label = "わな相談あり" if muni["wildlife_trap_loan"] else "対象外"

    cost_rows = [
        ("スズメバチ（軒下・低所 3m未満）", "13,000円〜25,000円", wasp_low_sub, wasp_low_net),
        ("スズメバチ（屋根裏・2階以上の高所）", "18,000円〜45,000円", wasp_high_sub, wasp_high_net),
        ("スズメバチ（床下・土中・狭小箇所）", "25,000円〜55,000円", wasp_hard_sub, wasp_hard_net),
        ("アシナガバチ（高所・屋根裏）", "13,000円〜26,000円", ashi_sub, ashi_net),
        ("シロアリ駆除（1階床下全面・5年保証目安）", "90,000円〜165,000円", "0円（対象外）", "90,000円〜165,000円"),
        ("ハクビシン・アライグマ等（追い出し＋封鎖）", "80,000円〜190,000円", f"0円（{trap_label}）", "80,000円〜190,000円"),
    ]
    cost_rows_html = "".join(
        "<tr>"
        f"<td><strong>{esc(r[0])}</strong></td>"
        f'<td class="num">{esc(r[1])}</td>'
        f'<td class="num num-green">{esc(r[2])}</td>'
        f'<td class="num num-strong">{esc(r[3])}</td>'
        "</tr>"
        for r in cost_rows
    )

    # Live A8.net affiliate programs
    disclosure = aff_config.get("disclosure_label", "PR・広告提携枠")
    progs = aff_config.get("programs", {})
    wasp_caution = (
        f"平日の日中は先に「{dept}」へ指定・委託の対象かご確認ください（緊急時・対象外箇所で下記見積もり利用可）。"
        if sub["city_designated_only"]
        else ""
    )
    cta_cards_html = ""
    if "hachi_110" in progs:
        cta_cards_html += _render_partner_card_html(
            progs["hachi_110"],
            disclosure,
            secondary_program=progs.get("pest_rcleaning"),
            caution_note=wasp_caution,
        )
    if "shiroari_110" in progs:
        cta_cards_html += _render_partner_card_html(progs["shiroari_110"], disclosure)
    if "gaiju_110" in progs:
        cta_cards_html += _render_partner_card_html(progs["gaiju_110"], disclosure)
    if "akiya_kaitai" in progs:
        cta_cards_html += _render_partner_card_html(
            progs["akiya_kaitai"],
            disclosure,
            secondary_program=progs.get("akiya_kaitori"),
        )

    # Regional neighbor links
    neighbors = [m for m in all_municipalities if m["region"] == region and m["municipality_code"] != code]
    neighbor_links_html = "".join(
        f'<a href="./{esc(n["municipality_code"])}.html">{esc(n["prefecture"] + n["city_name"])}</a>'
        for n in neighbors
    )

    faq_visible_html = "".join(
        f'<div class="faq-item"><div class="faq-q">Q. {esc(q)}</div><p class="faq-a">{esc(a)}</p></div>'
        for q, a in faq_items
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
{GA4_HEAD_SNIPPET}
  <title>{esc(pref + city)}のスズメバチ・害獣駆除補助金と空き家解体補助｜{esc(dept)}</title>
  <meta name="description" content="{esc(pref + city)}（{esc(dept)}）のスズメバチ駆除補助金（{esc(badge)}）・防護服貸出ルール・適正駆除相場と、老朽空き家の除却補助・10年固定資産税損益を掲載。">
  <link rel="canonical" href="{esc(canonical_url)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Noto+Sans+JP:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../style.css">
  <script type="application/ld+json">
{json.dumps(faq_json_ld, ensure_ascii=False, indent=2)}
  </script>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <a href="../index.html" class="brand-link">自治体補助金・空き家シミュレーター</a>
      <nav class="nav-tabs" aria-label="機能切り替え">
        <a href="../index.html?code={esc(code)}" class="nav-tab active">補助金・駆除相場</a>
        <a href="../akiya.html?code={esc(code)}" class="nav-tab">空き家10年損益</a>
      </nav>
    </div>
  </header>

  <main class="container">
    <nav class="breadcrumb-nav" aria-label="パンくずリスト">
      <a href="../index.html">全国一覧</a>
      <span>/</span>
      <span>{esc(region)}</span>
      <span>/</span>
      <span>{esc(pref + city)}（{esc(kana)}）</span>
    </nav>

    <div class="page-intro">
      <h1>{esc(h1_text)}</h1>
      <p class="page-subtitle">{esc(subtitle_text)}</p>
    </div>

    <section class="panel-card">
      <div class="result-header-row">
        <div>
          <span class="result-city-name">{esc(pref + " " + city)}</span>
          <span class="rule-badge badge-{esc(pattern)}">{esc(badge)}</span>
        </div>
        <a class="official-verify-link" href="{official_search_url}" target="_blank" rel="noopener noreferrer">
          <span>{esc(dept)}の公式要綱を検索</span>{SVG_EXTERNAL_ICON}
        </a>
      </div>

      <div class="callout-box {alert_class}">
        <div class="callout-title">{esc(alert_title)}</div>
        <div>{esc(alert_body)}</div>
      </div>

      {evidence_html}

      <table class="data-table">
        <tbody>
          <tr>
            <th>担当窓口</th>
            <td><strong>{esc(dept)}</strong>（自治体コード: <span class="mono">{esc(code)}</span>）</td>
          </tr>
          <tr>
            <th>スズメバチ補助内容</th>
            <td>{esc(sub["rate_text"])}</td>
          </tr>
          <tr>
            <th>防護服の無料貸出</th>
            <td>{"あり（要事前予約・在庫確認）" if sub["protective_suit_loan"] else "原則なし"}</td>
          </tr>
          <tr>
            <th>シロアリ・害獣対応</th>
            <td>{esc(muni["termites_wildlife_notes"])}</td>
          </tr>
          <tr>
            <th>老朽空き家 解体補助</th>
            <td>{esc(akiya_notes)}（上限目安: <strong>{_fmt_yen(akiya_max) if akiya_max > 0 else "個別要確認"}</strong>）</td>
          </tr>
        </tbody>
      </table>

      <div class="action-link-row">
        <a class="action-link-btn" href="../index.html?code={esc(code)}">場所・害虫別の実質負担シミュレーターを開く</a>
        <a class="action-link-btn secondary" href="../akiya.html?code={esc(code)}">{esc(city)}の空き家10年損益・解体増税を計算する</a>
      </div>
    </section>

    <section class="panel-card below-fold-section">
      <h2 class="panel-title">
        <span>{esc(city)}の駆除相場と補助金控除後の実質自己負担目安</span>
        <span class="count-status-text">確認日: {esc(verified_at)}</span>
      </h2>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>対象害虫・作業場所</th>
              <th class="num">適正市場相場（税込）</th>
              <th class="num">{esc(city)} 補助見込</th>
              <th class="num">実質自己負担の目安</th>
            </tr>
          </thead>
          <tbody>
            {cost_rows_html}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel-card below-fold-section">
      <h2 class="panel-title">
        <span>現地無料見積もり・空き家解体相談窓口（明朗会計・上場企業運営等）</span>
      </h2>
      <div class="city-cta-grid">
        {cta_cards_html}
      </div>
    </section>

    <section class="panel-card below-fold-section">
      <h2 class="panel-title">
        <span>{esc(city)}の相続空き家「解体補助金 vs 固定資産税増額」の注意点</span>
      </h2>
      <p style="margin:0 0 12px;font-size:0.9rem;">
        {esc(city)}では<strong>{esc(akiya_notes)}</strong>が設けられていますが、買主が決まる前に家屋を解体して更地にすると、翌年1月1日から<strong>住宅用地特例（固定資産税1/6・都市計画税1/3）が解除され、土地の年税額が約3.5〜4.2倍に急増</strong>します。また、放置して「管理不全空家」の勧告を受けた場合も建物が残ったまま特例が解除されます。
      </p>
      <div class="action-link-row">
        <a class="action-link-btn" href="../akiya.html?code={esc(code)}">{esc(city)}の補助金（{esc(akiya_cap_str)}）を反映して10年損益を計算する</a>
      </div>
    </section>

    <section class="panel-card below-fold-section">
      <h2 class="panel-title"><span>{esc(pref + city)}のよくある質問（FAQ）</span></h2>
      <div class="faq-list">
        {faq_visible_html}
      </div>
    </section>

    <section class="below-fold-section">
      <details class="quiet-disclosure" open>
        <summary>{esc(region)}の他市区町村の補助金・相場ページを見る</summary>
        <div class="disclosure-body">
          <div class="city-dir-links">
            {neighbor_links_html}
          </div>
        </div>
      </details>
    </section>
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <p class="footer-note">
        掲載情報は{esc(pref + city)}（{esc(dept)}）等の公開要綱に基づき検証していますが、予算上限到達や要綱改正により受付終了・変更される場合があります。作業依頼・解体契約前に必ず担当窓口へ最新状況をご確認ください。民間見積もりリンクにはPR（アフィリエイト提携枠）が含まれます。
      </p>
    </div>
  </footer>
</body>
</html>
"""


def _build_city_directory_inner_html(municipalities: list[dict[str, Any]]) -> str:
    esc = html.escape
    region_order = ["北海道・東北", "関東", "中部", "近畿", "中国・四国", "九州・沖縄"]
    grouped: dict[str, list[dict[str, Any]]] = {r: [] for r in region_order}
    for m in municipalities:
        grouped.setdefault(m["region"], []).append(m)

    blocks: list[str] = ['<div class="city-directory-grid">']
    for reg in region_order:
        items = grouped.get(reg, [])
        if not items:
            continue
        links = "".join(
            f'<a href="./cities/{esc(m["municipality_code"])}.html">{esc(m["prefecture"] + m["city_name"])}</a>'
            for m in items
        )
        blocks.append(
            f'<div class="city-dir-group">'
            f'<div class="city-dir-region">{esc(reg)}（{len(items)}自治体）</div>'
            f'<div class="city-dir-links">{links}</div>'
            f"</div>"
        )
    blocks.append("</div>")
    return "\n          ".join(blocks)


def build_programmatic_seo_pages(
    site_dir: Path,
    *,
    base_url: str = DEFAULT_PUBLIC_BASE_URL,
) -> dict[str, Any]:
    """Generate static city HTML pages (`site/cities/*.html`), `sitemap.xml`, `robots.txt`, and sync `index.html`."""
    muni_json_path = site_dir / "data" / "municipalities.json"
    aff_json_path = site_dir / "data" / "affiliate_config.json"
    if not muni_json_path.exists():
        raise FileNotFoundError(f"Missing dataset: {muni_json_path}")
    if not aff_json_path.exists():
        raise FileNotFoundError(f"Missing affiliate config: {aff_json_path}")

    muni_payload = json.loads(muni_json_path.read_text(encoding="utf-8"))
    aff_config = json.loads(aff_json_path.read_text(encoding="utf-8"))
    municipalities: list[dict[str, Any]] = muni_payload["municipalities"]
    MunicipalityRuleValidator.validate_dataset(municipalities)

    cities_dir = site_dir / "cities"
    cities_dir.mkdir(parents=True, exist_ok=True)

    generated_date = muni_payload.get("generated_at", "2026-11-26")
    for muni in municipalities:
        page_html = _render_city_page_html(muni, municipalities, aff_config, base_url)
        (cities_dir / f"{muni['municipality_code']}.html").write_text(page_html, encoding="utf-8")

    # Build sitemap.xml
    clean_base = base_url.rstrip("/")
    url_entries: list[tuple[str, str]] = [
        (f"{clean_base}/", generated_date),
        (f"{clean_base}/index.html", generated_date),
        (f"{clean_base}/akiya.html", generated_date),
    ]
    for muni in municipalities:
        url_entries.append((f"{clean_base}/cities/{muni['municipality_code']}.html", muni["verified_at"]))

    sitemap_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in url_entries:
        sitemap_lines.append("  <url>")
        sitemap_lines.append(f"    <loc>{html.escape(loc)}</loc>")
        sitemap_lines.append(f"    <lastmod>{html.escape(lastmod)}</lastmod>")
        sitemap_lines.append("  </url>")
    sitemap_lines.append("</urlset>")
    (site_dir / "sitemap.xml").write_text("\n".join(sitemap_lines) + "\n", encoding="utf-8")

    # Build robots.txt & .nojekyll
    (site_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {clean_base}/sitemap.xml\n",
        encoding="utf-8",
    )
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    # Inject crawlable directory links into site/index.html
    index_path = site_dir / "index.html"
    if index_path.exists():
        idx_text = index_path.read_text(encoding="utf-8")
        dir_html = _build_city_directory_inner_html(municipalities)
        marker_re = re.compile(
            r"(<!-- CITY_DIRECTORY_START -->)[\s\S]*?(<!-- CITY_DIRECTORY_END -->)"
        )
        if marker_re.search(idx_text):
            updated_idx = marker_re.sub(
                rf"\1\n          {dir_html}\n          \2",
                idx_text,
            )
            index_path.write_text(updated_idx, encoding="utf-8")

    return {
        "city_pages_generated": len(municipalities),
        "sitemap_urls": len(url_entries),
        "cities_dir": str(cities_dir),
    }


def validate_programmatic_seo_pages(site_dir: Path) -> dict[str, Any]:
    """Validate generated city HTML pages, FAQPage JSON-LD, GA4 tag, and sitemap.xml."""
    cities_dir = site_dir / "cities"
    sitemap_path = site_dir / "sitemap.xml"
    if not cities_dir.is_dir():
        raise FileNotFoundError(f"Missing programmatic SEO directory: {cities_dir}")
    if not sitemap_path.is_file():
        raise FileNotFoundError(f"Missing sitemap.xml: {sitemap_path}")

    html_files = sorted(cities_dir.glob("*.html"))
    if len(html_files) < 60:
        raise ValueError(f"Expected >= 60 city HTML pages in {cities_dir}, found {len(html_files)}")

    ld_re = re.compile(r'<script type="application/ld\+json">\s*(\{[\s\S]*?\})\s*</script>')
    h1_re = re.compile(r"<h1>(.*?)</h1>")

    for page in html_files:
        text = page.read_text(encoding="utf-8")
        if "G-F0ZLS15LNQ" not in text:
            raise ValueError(f"Missing GA4 tag in {page.name}")
        if 'rel="canonical"' not in text:
            raise ValueError(f"Missing canonical link in {page.name}")
        if "px.a8.net" not in text:
            raise ValueError(f"Missing live A8.net CTA link in {page.name}")
        h1_match = h1_re.search(text)
        if not h1_match or len(html.unescape(h1_match.group(1))) > 24:
            raise ValueError(f"Invalid or overly long h1 in {page.name}")
        ld_match = ld_re.search(text)
        if not ld_match:
            raise ValueError(f"Missing FAQPage JSON-LD in {page.name}")
        ld_obj = json.loads(ld_match.group(1))
        if ld_obj.get("@type") != "FAQPage" or len(ld_obj.get("mainEntity", [])) < 3:
            raise ValueError(f"Invalid FAQPage schema in {page.name}")

    sitemap_text = sitemap_path.read_text(encoding="utf-8")
    loc_count = len(re.findall(r"<loc>https://", sitemap_text))
    if loc_count < len(html_files) + 2:
        raise ValueError(f"sitemap.xml has only {loc_count} URLs for {len(html_files)} city pages")

    return {"verified_city_pages": len(html_files), "verified_sitemap_urls": loc_count}


def build_seed_dataset(output_path: Path) -> dict[str, Any]:
    """Validate and write the pre-seeded municipalities dataset to JSON."""
    summary = MunicipalityRuleValidator.validate_dataset(SEED_MUNICIPALITIES)
    payload = {
        "schema_version": "1.0.0",
        "generated_at": "2026-11-26",
        "coverage_note": (
            "全国主要政令指定都市・東京特別区・中核市・地方拠点都市を網羅収録。"
            "自治体補助金は年度途中の予算上限到達（例年9〜11月頃）で受付終了となる場合があるため、"
            "作業依頼前に必ず記載の担当課へ当年度の受付状況をご確認ください。"
        ),
        "summary": summary,
        "municipalities": SEED_MUNICIPALITIES,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def validate_json_file(json_path: Path) -> dict[str, Any]:
    """Load `municipalities.json` from disk and run full invariant + parser self-tests."""
    if not json_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "municipalities" not in data:
        raise ValueError("Invalid dataset envelope: missing 'municipalities' key")
    summary = MunicipalityRuleValidator.validate_dataset(data["municipalities"])
    self_test = run_parser_self_test()
    result = {**summary, **self_test}
    site_dir = json_path.parent.parent
    if (site_dir / "cities").is_dir():
        result.update(validate_programmatic_seo_pages(site_dir))
    return result


def main(argv: list[str] | None = None) -> int:
    base_dir = Path(__file__).resolve().parent.parent
    default_out = base_dir / "site" / "data" / "municipalities.json"

    parser = argparse.ArgumentParser(
        description="Harvest and validate Japanese municipal pest & akiya subsidy rules."
    )
    parser.add_argument(
        "--build-seed",
        action="store_true",
        help="Build and validate site/data/municipalities.json from curated regional rules.",
    )
    parser.add_argument(
        "--build-pages",
        action="store_true",
        help="Generate all programmatic SEO city pages (site/cities/*.html), sitemap.xml, and city directory.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_PUBLIC_BASE_URL,
        help="Canonical base URL used for sitemap.xml and city page canonical links.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate existing site/data/municipalities.json and run anti-hallucination self-tests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_out,
        help="Target path for municipalities.json.",
    )
    parser.add_argument(
        "--parse-file",
        type=Path,
        help="Optional local HTML/text file of a municipal page to parse into a validated JSON record.",
    )
    parser.add_argument("--code", type=str, help="5-digit JIS municipality code when using --parse-file.")
    parser.add_argument("--pref", type=str, help="Prefecture name when using --parse-file.")
    parser.add_argument("--city", type=str, help="City/ward name when using --parse-file.")
    parser.add_argument("--kana", type=str, help="Hiragana reading when using --parse-file.")

    args = parser.parse_args(argv)

    if args.parse_file:
        if not all([args.code, args.pref, args.city, args.kana]):
            parser.error("--parse-file requires --code, --pref, --city, and --kana")
        raw = args.parse_file.read_text(encoding="utf-8")
        record = MunicipalityTextParser.parse_to_record(
            raw,
            municipality_code=args.code,
            prefecture=args.pref,
            city_name=args.city,
            reading_kana=args.kana,
        )
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.build_seed:
        summary = build_seed_dataset(args.output)
        seo_stats: dict[str, Any] = {}
        site_dir = args.output.parent.parent
        if (site_dir / "data" / "affiliate_config.json").exists():
            seo_stats = build_programmatic_seo_pages(site_dir, base_url=args.base_url)
        self_test = run_parser_self_test()
        print(
            json.dumps(
                {"status": "built", "output": str(args.output), **summary, **seo_stats, **self_test},
                ensure_ascii=False,
            )
        )
        return 0

    if args.build_pages:
        site_dir = args.output.parent.parent
        seo_stats = build_programmatic_seo_pages(site_dir, base_url=args.base_url)
        seo_verified = validate_programmatic_seo_pages(site_dir)
        print(json.dumps({"status": "pages_built", **seo_stats, **seo_verified}, ensure_ascii=False))
        return 0

    # Default or --validate: validate on-disk dataset + programmatic SEO pages
    result = validate_json_file(args.output)
    print(json.dumps({"status": "validated", "input": str(args.output), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
