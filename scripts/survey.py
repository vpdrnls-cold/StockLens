"""Interactive investor-profile questionnaire (Phase L, CURRENT_STATUS item 57).

Asks the six questions in src/recommendation/survey.py, shows the result and
why, and saves it to data/user_profile.json (gitignored -- personal answers
never go into the public repo). Use it with:

    PYTHONPATH=. python scripts/survey.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py --profile saved

Non-interactive (tests / scripting): --answers 3,2,3,2,2,2 (1-based option numbers)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.recommendation.survey import (
    DEFAULT_PROFILE_PATH,
    QUESTIONS,
    RISK_NOTICE,
    WARNING_TEXT,
    evaluate,
    explain,
    needs_warning,
    save,
)


def ask(prompt: str, n: int) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw) - 1
        print(f"  1~{n} 중 번호를 입력하세요.")


def ask_yes_no(prompt: str) -> bool:
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"예", "y", "yes"}:
            return True
        if raw in {"아니오", "아니요", "n", "no"}:
            return False
        print("  '예' 또는 '아니오'로 입력하세요.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", help="쉼표로 구분한 1부터 시작하는 선택 번호 6개 (비대화형)")
    ap.add_argument("--acknowledge-warning", action="store_true", help="비대화형에서 Q3 10%% 경고에 '예'")
    ap.add_argument("--out", default=str(DEFAULT_PROFILE_PATH))
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    print("=" * 78)
    print("StockLens 투자성향 진단 (6문항)")
    print("=" * 78)
    print(RISK_NOTICE + "\n")

    if args.answers:
        picks = [int(x) - 1 for x in args.answers.split(",")]
        if len(picks) != len(QUESTIONS):
            print(f"--answers 에는 {len(QUESTIONS)}개가 필요합니다.", file=sys.stderr)
            return 1
        answers = {q.key: i for q, i in zip(QUESTIONS, picks)}
        ack = True if args.acknowledge_warning else None
        if needs_warning(answers) and not args.acknowledge_warning:
            ack = False
    else:
        answers = {}
        for q in QUESTIONS:
            print(f"{q.key}. {q.text}")
            for i, (label, _) in enumerate(q.options, 1):
                print(f"   {i}) {label}")
            answers[q.key] = ask("  > ", len(q.options))
            print()
        ack = None
        if needs_warning(answers):
            print("⚠ " + WARNING_TEXT)
            ack = ask_yes_no("  (예/아니오) > ")
            print()

    try:
        result = evaluate(answers, warning_acknowledged=ack)
    except ValueError as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 1

    print(explain(result))
    if not args.no_save:
        path = save(result, Path(args.out))
        print(f"\n저장: {path} (git에 올라가지 않음)")
        if result.eligible:
            print("모델 참고 순위 보기: STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py --profile saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
