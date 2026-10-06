"""Investor-profile questionnaire -> risk profile (Phase L, CURRENT_STATUS item 57).

Maps six answers to one of the item 56 profiles (conservative / neutral /
aggressive) or to "not eligible" (no recommendations shown).

Design (decided 2026-09-30 with 재훈; a design choice, NOT fitted to data --
there is no outcome to validate a questionnaire against yet):

  capacity  = (Q1 + Q2) / 6         objective ability to bear loss
  tolerance = (Q3 + Q4 + Q5) / 9    subjective willingness
  s = min(capacity, tolerance)      the binding side decides (contradictory
                                    answers therefore resolve conservatively)

  s < 0.4                 -> conservative
  0.4 <= s < 0.7          -> neutral
  s >= 0.7 and Q6 >= 2    -> aggressive   (aggressive had the thinnest IC margin in item 56)
  s >= 0.7 and Q6 < 2     -> neutral

  Not eligible: Q1 "may need it within 1 month", Q2 "a loss would affect living
  costs", Q3 "cannot accept any loss", or Q3 "max 10%" without acknowledging
  the warning. Q3 "max 10%" WITH acknowledgement -> capped at conservative.

Every number shown to the user comes from this module; nothing is inferred later.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SURVEY_VERSION = "2026-09-30"
DEFAULT_PROFILE_PATH = Path("data/user_profile.json")

NOT_ELIGIBLE = None  # score value marking a disqualifying option

CONSERVATIVE_MAX = 0.4  # s < 0.4 -> conservative
NEUTRAL_MAX = 0.7  # s < 0.7 -> neutral
AGGRESSIVE_MIN_EXPERIENCE = 2  # Q6 score (1~3 years)
WARN_OPTION = ("Q3", 1)  # "max 10% loss"

# Worst validation drawdowns of the conservative profile (item 56: W1 -24.1%, W3 -40.7%)
CONSERVATIVE_MDD_RANGE = "−24%~−41%"


@dataclass(frozen=True)
class Question:
    key: str
    area: str  # "capacity" | "tolerance" | "experience"
    text: str
    options: tuple[tuple[str, int | None], ...]  # (label, score or NOT_ELIGIBLE)


QUESTIONS: tuple[Question, ...] = (
    Question("Q1", "capacity", "이 투자금이 앞으로 얼마나 오랫동안 필요하지 않은 자금인가요?", (
        ("1개월 이내에 사용할 가능성이 있음", NOT_ELIGIBLE),
        ("1년 이내에 사용할 가능성이 있음", 1),
        ("1~3년 동안 사용할 계획이 없음", 2),
        ("3년 이상 사용할 계획이 없음", 3),
    )),
    Question("Q2", "capacity",
             "이 투자금의 절반 가까이 손실이 나더라도 생활비나 예정된 중요한 지출에 영향이 없나요?", (
        ("생활비·중요 지출에 영향을 줌", NOT_ELIGIBLE),
        ("어느 정도 영향을 줄 수 있음", 1),
        ("거의 영향 없음", 2),
        ("전혀 영향 없음", 3),
    )),
    Question("Q3", "tolerance", "1년 동안 투자금 가치가 최대 어느 정도까지 줄어도 투자를 계속 유지할 수 있나요?", (
        ("원금 손실도 감수하기 어려움", NOT_ELIGIBLE),
        ("최대 10% 손실", 0),
        ("최대 20% 손실", 1),
        ("최대 30% 손실", 2),
        ("40% 이상 손실도 감수 가능", 3),
    )),
    Question("Q4", "tolerance", "보유 종목이 특별한 악재 없이 일주일 만에 약 10% 하락하면 어떻게 하겠습니까?", (
        ("대부분 또는 전부 매도", 0),
        ("일부 매도", 1),
        ("그대로 유지", 2),
        ("추가 매수", 3),
    )),
    Question("Q5", "tolerance", "이 투자를 통해 가장 중요하게 달성하고 싶은 목표는 무엇인가요?", (
        ("원금 보존이 가장 중요", 0),
        ("예·적금보다 조금 높은 수익", 1),
        ("시장 평균 수준의 수익", 2),
        ("시장 평균을 웃도는 높은 수익 추구", 3),
    )),
    Question("Q6", "experience", "주식에 직접 투자한 기간은 얼마나 되나요?", (
        ("경험 없음", 0),
        ("1년 미만", 1),
        ("1~3년", 2),
        ("3년 이상", 3),
    )),
)
QUESTION_BY_KEY = {q.key: q for q in QUESTIONS}

RISK_NOTICE = (
    "이 서비스는 KOSPI 대형주 50종목 중 모델 점수 상위 10종목을 다음 거래일 시가에 사서 "
    "5거래일 보유하는 단기 전략의 모델 참고 순위입니다. 과거 검증 구간에서 최대 낙폭(MDD)은 −20%~−44%였고, "
    "표본 밖 성과는 아직 확인되지 않았으며(1차 확인 2027년 1월), 최근 검증 구간에서는 시장 평균보다 낮았습니다. "
    "투자 권유가 아닙니다."
)
WARNING_TEXT = (
    "선택하신 최대 손실은 10%입니다. 이 서비스의 과거 검증 구간에서 가장 안정적인 성향(안정형)도 "
    f"최대 낙폭이 {CONSERVATIVE_MDD_RANGE}였습니다. 선택하신 수준을 넘는 손실이 생길 수 있습니다. "
    "그래도 진행하시겠습니까?"
)
PROFILE_LABELS = {"conservative": "안정형", "neutral": "중립형", "aggressive": "공격형"}
PROFILE_MEANING = {
    "conservative": "변동성이 작은 종목 쪽으로 기울인 순위입니다. 수익 변동은 줄지만 손실이 작다는 보장은 없습니다.",
    "neutral": "모델 순위를 그대로 따르는 순위입니다.",
    "aggressive": "변동성이 크고 거래량이 이례적으로 많은 종목 쪽으로 기울인 순위입니다. "
                  "검증에서 모델 신호 여유가 가장 작았던 성향입니다.",
}


@dataclass
class SurveyResult:
    eligible: bool
    profile: str | None
    capacity: float | None
    tolerance: float | None
    score: float | None
    binding: str | None  # "capacity" | "tolerance" | "equal"
    reasons: list[str] = field(default_factory=list)
    answers: dict[str, int] = field(default_factory=dict)  # option index per question
    warning_shown: bool = False
    warning_acknowledged: bool | None = None
    version: str = SURVEY_VERSION
    created_at: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def needs_warning(answers: dict[str, int]) -> bool:
    key, idx = WARN_OPTION
    return answers.get(key) == idx


def _validate(answers: dict[str, int]) -> None:
    missing = [q.key for q in QUESTIONS if q.key not in answers]
    if missing:
        raise ValueError(f"missing answers: {missing}")
    for q in QUESTIONS:
        idx = answers[q.key]
        if not isinstance(idx, int) or not 0 <= idx < len(q.options):
            raise ValueError(f"{q.key}: option index {idx!r} out of range 0..{len(q.options) - 1}")


def evaluate(answers: dict[str, int], warning_acknowledged: bool | None = None, *, now: datetime | None = None) -> SurveyResult:
    """Score answers (option indices, 0-based) and decide the profile."""
    _validate(answers)
    stamp = (now or datetime.now(timezone(timedelta(hours=9)))).isoformat(timespec="seconds")
    score = {q.key: q.options[answers[q.key]][1] for q in QUESTIONS}
    warn = needs_warning(answers)
    base = dict(answers=dict(answers), warning_shown=warn,
                warning_acknowledged=warning_acknowledged if warn else None, created_at=stamp)

    reasons = [
        f"{q.key}: '{q.options[answers[q.key]][0]}'" for q in QUESTIONS if score[q.key] is NOT_ELIGIBLE
    ]
    if warn and warning_acknowledged is not True:
        reasons.append("Q3: 최대 10% 손실 선택 후 경고에서 진행하지 않음")
    if reasons:
        return SurveyResult(False, None, None, None, None, None, reasons=reasons, **base)

    capacity = (score["Q1"] + score["Q2"]) / 6
    tolerance = (score["Q3"] + score["Q4"] + score["Q5"]) / 9
    s = min(capacity, tolerance)
    binding = "equal" if capacity == tolerance else ("capacity" if capacity < tolerance else "tolerance")

    if s < CONSERVATIVE_MAX:
        profile = "conservative"
        why = [f"종합 점수 {s:.2f} < {CONSERVATIVE_MAX}"]
    elif s < NEUTRAL_MAX:
        profile = "neutral"
        why = [f"종합 점수 {s:.2f}가 {CONSERVATIVE_MAX}~{NEUTRAL_MAX} 구간"]
    elif score["Q6"] >= AGGRESSIVE_MIN_EXPERIENCE:
        profile = "aggressive"
        why = [f"종합 점수 {s:.2f} ≥ {NEUTRAL_MAX}, 투자 경험 1년 이상"]
    else:
        profile = "neutral"
        why = [f"종합 점수 {s:.2f} ≥ {NEUTRAL_MAX}이지만 투자 경험 1년 미만이라 중립형으로 조정"]

    if warn:  # acknowledged "max 10%" -> capped
        if profile != "conservative":
            why.append("Q3 최대 10% 손실 선택(경고 확인) → 안정형으로 상한 적용")
        profile = "conservative"

    return SurveyResult(True, profile, capacity, tolerance, s, binding, reasons=why, **base)


def explain(result: SurveyResult) -> str:
    if not result.eligible:
        lines = ["진단 결과: 현재 응답 기준으로는 이 서비스의 모델 참고 순위를 제공하지 않습니다.", "이유:"]
        lines += [f"  - {r}" for r in result.reasons]
        lines.append("단기 주식 전략은 짧은 기간에 큰 손실이 날 수 있어, 위 조건에서는 적합하지 않습니다.")
        return "\n".join(lines)
    side = {"capacity": "손실 감당 여력", "tolerance": "위험 성향", "equal": "여력·성향(동일)"}[result.binding]
    lines = [
        f"진단 결과: {PROFILE_LABELS[result.profile]}({result.profile})",
        f"  - 손실 감당 여력 {result.capacity:.2f} · 위험 성향 {result.tolerance:.2f} → 낮은 쪽({side}) 기준 {result.score:.2f}",
    ]
    lines += [f"  - {r}" for r in result.reasons]
    lines.append(f"  - 의미: {PROFILE_MEANING[result.profile]}")
    return "\n".join(lines)


def save(result: SurveyResult, path: Path = DEFAULT_PROFILE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load(path: Path = DEFAULT_PROFILE_PATH) -> SurveyResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != SURVEY_VERSION:
        raise ValueError(f"saved survey version {data.get('version')} != {SURVEY_VERSION}; run scripts/survey.py again")
    return SurveyResult(**data)
