"""RF-16 long-form scale evaluation on a self-owned, deterministic synthetic novel.

The contract (sample, metrics and pass thresholds) is pre-registered in
docs/LONGFORM_EVALUATION.md. This harness builds the sample in an isolated data root
through the real FastAPI application, talks to a deterministic loopback
OpenAI-compatible fake model (never a paid API), measures, and writes a JSON and a
Markdown report into the explicitly named work root.

Exit codes: 0 every threshold passed, 1 at least one FAIL, 2 invalid arguments or root.
"""

# Synthetic Chinese sample text and report labels use full-width punctuation by design;
# rewriting it would change the deterministic sample, so RUF001 is disabled for this file.
# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "backend" / "alembic.ini"
ORIGIN = "http://127.0.0.1:5173"
PROFILE = "default-local"
REVIEW_PROMPT_PREFIX = "你是小说一致性编辑"
RECALL_ITEM_LIMIT = 24
RECALL_CHARACTER_LIMIT = 10_000
CONTEXT_LIMIT = 60_000
PROMPT_LIMIT = 100_000

# ---------------------------------------------------------------------------
# Deterministic synthetic sample
# ---------------------------------------------------------------------------

CHARACTERS = (
    ("林照", "主角，雾港巡夜人"),
    ("沈砚", "盐仓账房，主角旧友"),
    ("顾青", "灯塔守夜人"),
    ("苏晚", "茶楼说书人"),
    ("陆迟", "南岸船坞工头"),
    ("许棠", "藏书阁抄书人"),
    ("韩烈", "城防营校尉"),
    ("温言", "海神祠祭司"),
    ("秦岳", "铁匠铺掌柜"),
    ("白芷", "渡口药铺医女"),
    ("程墨", "钟楼看守"),
    ("裴昭", "外来商队首领"),
)
PLACES = (
    "雾港",
    "北码头",
    "盐仓",
    "钟楼",
    "旧灯塔",
    "渡口集市",
    "城隍庙",
    "南岸船坞",
    "茶楼",
    "藏书阁",
    "铁匠铺",
    "海神祠",
)
ITEM_PREFIXES = (
    "赤霄",
    "青冥",
    "玄铁",
    "白玉",
    "紫檀",
    "寒星",
    "金缕",
    "碧落",
    "墨羽",
    "银霜",
    "苍梧",
    "流火",
    "素心",
    "雷纹",
    "云纹",
    "鎏金",
)
ITEM_SUFFIXES = ("罗盘", "令牌", "铜铃", "匕首", "卷轴", "玉佩")
WEAPONS = ("短刀", "鱼叉", "碎瓷", "铁钩", "断桨", "竹刺")
FILLER = (
    "{a}沿着{p}的石阶往下走，潮气从脚边漫上来，远处传来零散的船号声。",
    "{p}的灯一盏接一盏亮起，{a}在檐下停住，听见风把旗子吹得猎猎作响。",
    "{a}与{b}并肩走过{p}，谁也没有先开口，只有木屐敲在青石上的回音。",
    "雨势渐小，{p}的积水映出昏黄的灯影，{a}抬手抹去额前的水珠。",
    "{b}把一包干粮递给{a}，说天亮之前最好离开{p}，免得再生枝节。",
    "{a}记下了{p}附近每一条小巷的走向，心里慢慢有了打算。",
    "夜里的{p}格外安静，偶尔有猫从屋脊跃过，碰落几片松动的瓦。",
    "{a}想起{b}白天说过的话，越想越觉得其中另有隐情。",
    "潮水退去后，{p}的滩涂上露出一排旧木桩，像一行看不懂的字。",
    "{b}在{p}的柜台后拨着算盘，眼角余光却一直落在门口。",
    "{a}把斗笠压低，从{p}的人群里穿过，没有回头。",
    "天色将明，{p}的雾气还没散尽，{a}和{b}约好午后再碰头。",
)
CONTINUE_SENTENCES = (
    "雾气从海面缓缓推上岸来，把码头的灯火揉成一团团模糊的光晕。",
    "巡夜人提着灯笼走过长街，脚步声在空荡的巷子里来回撞着。",
    "远处钟楼敲响三更，惊起屋檐下几只栖息的海鸟。",
    "他停在桥头，看潮水一寸寸漫过石阶，心里那点不安越发清晰。",
    "风里带着咸腥和焦木的气味，像是有人在对岸烧掉了什么东西。",
    "他把手伸进怀里，确认那件东西仍在，才重新迈开步子。",
)


@dataclass(frozen=True)
class Scale:
    name: str
    volumes: int
    chapters_per_volume: int
    characters_per_chapter: int
    ai_chapters: tuple[int, ...]
    review_chapters: tuple[int, ...]
    probe_sources: tuple[int, ...]
    probe_gaps: tuple[int, ...]


SCALES = {
    "full": Scale(
        "full",
        volumes=3,
        chapters_per_volume=16,
        characters_per_chapter=2_300,
        ai_chapters=(9, 21, 33, 45),
        review_chapters=(14, 26, 38, 47),
        probe_sources=tuple(range(0, 36, 3)),
        probe_gaps=(6, 10, 14, 18, 22),
    ),
    "small": Scale(
        "small",
        volumes=2,
        chapters_per_volume=4,
        characters_per_chapter=360,
        ai_chapters=(5,),
        review_chapters=(6,),
        probe_sources=(0, 1, 2),
        probe_gaps=(4,),
    ),
}


@dataclass(frozen=True)
class FactSpec:
    key: str
    title: str
    text: str
    quote: str
    disposition: str  # confirmed | pending | rejected


@dataclass(frozen=True)
class ChapterSpec:
    index: int
    volume: int
    position: int
    title: str
    summary: str
    draft: str
    final: str
    facts: tuple[FactSpec, ...]


@dataclass(frozen=True)
class Probe:
    source_chapter: int
    target_chapter: int
    fact_key: str


@dataclass(frozen=True)
class Sample:
    scale: Scale
    title: str
    description: str
    outline: tuple[str, str]
    bible: tuple[str, str]
    volumes: tuple[tuple[str, str], ...]
    chapters: tuple[ChapterSpec, ...]
    probes: tuple[Probe, ...]
    control_chapters: tuple[ChapterSpec, ...]

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


def non_whitespace(text: str) -> int:
    return sum(not character.isspace() for character in text)


def _name(index: int) -> str:
    return CHARACTERS[index % len(CHARACTERS)][0]


def item_name(chapter: int) -> str:
    return (
        ITEM_PREFIXES[chapter % len(ITEM_PREFIXES)] + ITEM_SUFFIXES[chapter // len(ITEM_PREFIXES)]
    )


def _anchors(index: int) -> dict[str, tuple[str, str, str]]:
    c1, c2, c3 = _name(index), _name(index * 5 + 3), _name(index * 7 + 5)
    place, place2 = PLACES[index % len(PLACES)], PLACES[(index * 5 + 4) % len(PLACES)]
    item = item_name(index)
    weapon = WEAPONS[index % len(WEAPONS)]
    return {
        "item": (
            f"{item}的去向",
            f"第{index + 1}章：{c1}在{place}得到{item}，此后随身携带，未曾示人。",
            f"{c1}在{place}的灯下接过了{item}，掌心一阵发烫。",
        ),
        "injury": (
            f"{c2}的伤势",
            f"第{index + 1}章起{c2}左臂受伤，行动受限，需要静养。",
            f"{c2}的左臂被{weapon}划开一道口子，血顺着袖口滴落。",
        ),
        "promise": (
            f"{c1}与{c3}的约定",
            f"第{index + 1}章：{c1}与{c3}约定在{place2}再次会面。",
            f"{c1}对{c3}低声说：“{place2}见，不见不散。”",
        ),
        "rumor": (
            f"{c3}的身世传闻",
            f"第{index + 1}章：有人传言{c3}出身{place2}旧族，尚无证据。",
            f"茶客们压低声音议论，说{c3}原是{place2}旧族的后人。",
        ),
        "omen": (
            f"{place}的异象",
            f"第{index + 1}章：{place}夜里出现不明火光，来源未知。",
            f"{place}上空忽然亮起一团青白的火光，转瞬又灭了。",
        ),
    }


def _filler(index: int, step: int) -> str:
    template = FILLER[(index * 7 + step) % len(FILLER)]
    return template.format(
        a=_name(index + step),
        b=_name(index * 3 + step * 5 + 1),
        p=PLACES[(index * 2 + step * 3) % len(PLACES)],
    )


def _chapter_text(index: int, target: int, extra: tuple[str, ...]) -> tuple[str, str]:
    anchors = _anchors(index)
    special = [anchors["item"][2], anchors["injury"][2], anchors["promise"][2]]
    if index % 4 == 3:
        special.append(anchors["rumor"][2])
    if index % 6 == 5:
        special.append(anchors["omen"][2])
    paragraphs: list[str] = []
    sentences: list[str] = []
    step = 0
    total = 0
    slots = len(special)
    while total < target or special:
        if special and total >= (target * (slots - len(special))) // max(slots, 1):
            sentence = special.pop(0)
        else:
            sentence = _filler(index, step)
            step += 1
        sentences.append(sentence)
        total += non_whitespace(sentence)
        if len(sentences) == 5:
            paragraphs.append("　　" + "".join(sentences))
            sentences = []
    if sentences:
        paragraphs.append("　　" + "".join(sentences))
    if extra:
        paragraphs.append("　　" + "".join(extra))
    final = "\n\n".join(paragraphs)
    draft = "\n\n".join(paragraphs[: max(1, (len(paragraphs) * 2) // 3)])
    return draft, final


def generate_sample(scale_name: str) -> Sample:
    scale = SCALES[scale_name]
    total = scale.volumes * scale.chapters_per_volume
    probes: list[Probe] = []
    for number, source in enumerate(scale.probe_sources):
        target = source + scale.probe_gaps[number % len(scale.probe_gaps)]
        if target < total and target not in scale.ai_chapters:
            probes.append(Probe(source, target, f"c{source}-item"))
    reminders: dict[int, list[str]] = {}
    for probe in probes:
        source_place = PLACES[probe.source_chapter % len(PLACES)]
        reminders.setdefault(probe.target_chapter, []).append(
            f"{_name(probe.source_chapter)}又摸了摸怀里的{item_name(probe.source_chapter)}，"
            f"想起当初在{source_place}得到它的那个夜晚，此后一直随身携带。"
        )
    chapters: list[ChapterSpec] = []
    for index in range(total):
        draft, final = _chapter_text(
            index, scale.characters_per_chapter, tuple(reminders.get(index, ()))
        )
        anchors = _anchors(index)
        facts = [
            FactSpec(f"c{index}-{key}", *anchors[key], "confirmed")
            for key in ("item", "injury", "promise")
        ]
        if index % 4 == 3:
            facts.append(FactSpec(f"c{index}-rumor", *anchors["rumor"], "pending"))
        if index % 6 == 5:
            facts.append(FactSpec(f"c{index}-omen", *anchors["omen"], "rejected"))
        for spec in facts:
            assert spec.quote in final, spec.key
        chapters.append(
            ChapterSpec(
                index,
                index // scale.chapters_per_volume,
                (index % scale.chapters_per_volume + 1) * 10,
                f"第{index + 1}章 {PLACES[index % len(PLACES)]}夜话",
                f"{_name(index)}在{PLACES[index % len(PLACES)]}追查{item_name(index)}的线索。",
                draft,
                final,
                tuple(facts),
            )
        )
    control: list[ChapterSpec] = []
    for index in range(3):
        anchors = _anchors(index)
        text = "　　" + anchors["item"][2] + _filler(index, 0) + _filler(index, 1)
        control.append(
            ChapterSpec(
                index,
                0,
                (index + 1) * 10,
                f"对照第{index + 1}章",
                "隔离对照小说",
                text,
                text,
                (FactSpec(f"x{index}-item", *anchors["item"], "confirmed"),),
            )
        )
    return Sample(
        scale=scale,
        title="雾港纪事（合成评测样本）",
        description="RF-16 长篇规模评测用的确定性合成小说，不含真实作者内容。",
        outline=("雾港纪事大纲", "巡夜人林照在雾港追查一系列失落器物，揭开旧族与商队的往事。"),
        bible=(
            "雾港设定",
            "\n".join(f"{place}：雾港的一处地点，常年潮湿多雾。" for place in PLACES),
        ),
        volumes=tuple((f"第{v + 1}卷", f"雾港纪事第{v + 1}卷") for v in range(scale.volumes)),
        chapters=tuple(chapters),
        probes=tuple(probes),
        control_chapters=tuple(control),
    )


# ---------------------------------------------------------------------------
# Deterministic fake OpenAI-compatible model server
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    cjk = sum("\u4e00" <= character <= "\u9fff" for character in text)
    other = sum(
        not character.isspace() and not ("\u4e00" <= character <= "\u9fff") for character in text
    )
    return cjk + math.ceil(other / 4)


def continue_text(sequence: int) -> str:
    text = ""
    step = sequence
    while non_whitespace(text) < 250:
        text += CONTINUE_SENTENCES[step % len(CONTINUE_SENTENCES)]
        step += 1
    return text[:250]


def review_text(messages: list[dict[str, str]]) -> str:
    payload = json.loads(messages[-1]["content"])
    content = payload["content"]
    first = content.strip().split("。")[0].strip() + "。"
    fact_ids = [item["id"] for item in payload["confirmed_facts"][:2]]
    return json.dumps(
        {
            "summary": "受控评测结果：核对前文事实承接。",
            "facts": [{"title": "评测候选事实", "text": "受控模型提取的候选事实", "quote": first}],
            "findings": [
                {
                    "quote": first,
                    "explanation": "受控评测：核对此句与前文事实是否承接。",
                    "instruction": "保持事实一致，补足承接。",
                    "fact_ids": fact_ids,
                }
            ],
        },
        ensure_ascii=False,
    )


@dataclass
class ModelCall:
    kind: str
    prompt_characters: int
    completion_characters: int
    prompt_tokens_estimate: int
    completion_tokens_estimate: int
    max_tokens: int


class FakeModelServer:
    """Loopback-only deterministic `/chat/completions` service that records every call."""

    def __init__(self) -> None:
        self.calls: list[ModelCall] = []
        self._lock = threading.Lock()
        self._continues = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                messages = body["messages"]
                prompt = "".join(item["content"] for item in messages)
                with server._lock:
                    if messages[0]["content"].startswith(REVIEW_PROMPT_PREFIX):
                        kind, text = "review", review_text(messages)
                    else:
                        kind, text = "continue", continue_text(server._continues)
                        server._continues += 1
                    server.calls.append(
                        ModelCall(
                            kind,
                            len(prompt),
                            len(text),
                            estimate_tokens(prompt),
                            estimate_tokens(text),
                            int(body.get("max_tokens", 0)),
                        )
                    )
                data = json.dumps(
                    {
                        "choices": [{"message": {"role": "assistant", "content": text}}],
                        "usage": {
                            "prompt_tokens": estimate_tokens(prompt),
                            "completion_tokens": estimate_tokens(text),
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> FakeModelServer:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


# ---------------------------------------------------------------------------
# Isolation helpers
# ---------------------------------------------------------------------------


class IsolationError(ValueError):
    """The requested work root is not a safe, self-owned evaluation location."""


def validate_work_root(candidate: str) -> Path:
    path = Path(candidate)
    if not path.is_absolute():
        raise IsolationError("--work-root must be an absolute path")
    path = Path(os.path.normpath(path))
    if path == REPOSITORY_ROOT or path.is_relative_to(REPOSITORY_ROOT):
        raise IsolationError("--work-root must not be inside the source repository")
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        formal = Path(os.path.normpath(local)) / "AIWebNovel"
        if path == formal or path.is_relative_to(formal) or formal.is_relative_to(path):
            raise IsolationError("--work-root must not overlap the formal author data root")
    if not path.parent.is_dir():
        raise IsolationError("--work-root parent folder must already exist")
    if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise IsolationError("--work-root must be a new or empty folder")
    return path


@contextmanager
def isolated_environment(data_root: Path) -> Iterator[None]:
    from aiwebnovel.core.config import get_settings

    saved = {
        name: os.environ.get(name) for name in ("AIWEBNOVEL_DATA_ROOT", "AIWEBNOVEL_DATABASE_URL")
    }
    os.environ["AIWEBNOVEL_DATA_ROOT"] = os.fspath(data_root)
    os.environ.pop("AIWEBNOVEL_DATABASE_URL", None)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def migrate(data_root: Path) -> Path:
    from aiwebnovel.storage.initializer import initialize_storage
    from aiwebnovel.storage.paths import StoragePaths

    paths = StoragePaths.from_root(data_root)
    initialize_storage(paths)
    environment = {
        **os.environ,
        "AIWEBNOVEL_DATA_ROOT": os.fspath(data_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.pop("AIWEBNOVEL_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", os.fspath(ALEMBIC_CONFIG), "upgrade", "head"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("alembic upgrade failed for the isolated evaluation root")
    return paths.database_file


@contextmanager
def application(data_root: Path, base_url: str) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from aiwebnovel.core.config import Settings
    from aiwebnovel.main import create_app

    settings = Settings(
        environment="production",
        data_root=data_root,
        ai_base_url=base_url,
        ai_model="longform-eval",
        trusted_hosts=("127.0.0.1", "localhost", "testserver"),
    )
    with TestClient(create_app(settings)) as client:
        yield client


def table_rows(database: Path) -> dict[str, list[tuple[object, ...]]]:
    uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }


def revision_counts(database: Path) -> dict[str, int]:
    uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return dict(
            connection.execute(
                "SELECT chapter_id, COUNT(*) FROM chapter_revisions GROUP BY chapter_id"
            ).fetchall()
        )


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "p50_ms": round(percentile(values, 0.5), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "max_ms": round(max(values) if values else 0.0, 2),
    }


def peak_rss_bytes() -> int | None:
    try:
        # Imported dynamically so type checking passes on both win32 and POSIX targets.
        resource: Any = importlib.import_module("resource")
    except ImportError:  # Windows has no resource module.
        return None
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvaluationError(RuntimeError):
    """An HTTP step of the evaluation did not behave as the product contract states."""


@dataclass
class ChapterState:
    spec: ChapterSpec
    chapter_id: str
    volume_id: str
    position: int
    revision: str
    version: int
    content: str
    revisions: int
    title: str
    summary: str
    author_saves: int = 0


@dataclass
class FactState:
    key: str
    fact_id: str
    chapter: int
    revision_id: str
    version: int
    status: str
    source_revision: str
    title: str
    text: str
    quote: str


@dataclass
class Metric:
    id: str
    name: str
    threshold: str
    measured: Any
    passed: bool | None


@dataclass
class Results:
    metrics: list[Metric] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def add(self, id_: str, name: str, threshold: str, measured: Any, passed: bool | None) -> None:
        self.metrics.append(Metric(id_, name, threshold, measured, passed))


class LongformEvaluation:
    def __init__(self, work_root: Path, scale: str, *, log: Callable[[str], None] = print) -> None:
        self.work_root = work_root
        self.sample = generate_sample(scale)
        self.log = log
        self.results = Results()
        self.chapters: list[ChapterState] = []
        self.facts: dict[str, FactState] = {}
        self.control_facts: set[str] = set()
        self.control_chapters: list[str] = []
        self.control_states: list[ChapterState] = []
        self.server: FakeModelServer  # bound in run() before any HTTP step
        self._previous_impacts: tuple[set[str], set[str]] = (set(), set())
        self.reviews: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.timings: dict[str, list[float]] = {}
        self.actions = {"generate": 0, "review_send": 0, "confirm": 0, "adopt": 0, "discard": 0}
        self.client: Any = None
        self.headers: dict[str, str] = {}
        self.project_id = ""

    # -- HTTP helpers ---------------------------------------------------------
    def _call(
        self,
        method: str,
        path: str,
        *,
        expected: int = 200,
        timing: str | None = None,
        **kwargs: Any,
    ) -> Any:
        started = time.perf_counter()
        response = self.client.request(method, path, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        if timing is not None:
            self.timings.setdefault(timing, []).append(elapsed)
        if response.status_code != expected:
            raise EvaluationError(
                f"{method} {path} returned {response.status_code}: {response.text[:300]}"
            )
        return response

    def _write(self, method: str, path: str, payload: dict[str, Any], **kwargs: Any) -> Any:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        return self._call(method, path, json=payload, headers=headers, **kwargs)

    def _session(self) -> None:
        response = self._call("GET", "/api/v1/security/session", headers={"Origin": ORIGIN})
        self.headers = {"Origin": ORIGIN, "X-CSRF-Token": str(response.json()["csrf_token"])}

    def _order(self) -> dict[str, int]:
        ordered = sorted(self.chapters, key=lambda item: (item.spec.volume, item.position))
        return {item.chapter_id: index for index, item in enumerate(ordered)}

    # -- build ----------------------------------------------------------------
    def _save_content(self, state: ChapterState, content: str) -> None:
        response = self._write(
            "PUT",
            f"/api/v1/chapters/{state.chapter_id}/content",
            {"content": content},
            headers={"If-Match": f'"{state.version}"'},
            timing="content_save",
        )
        body = response.json()
        state.revision = body["current_revision_id"]
        state.version = body["concurrency_version"]
        state.content = content
        state.revisions += 1
        state.author_saves += 1

    def _create_fact(
        self, state: ChapterState, spec: FactSpec, registry: dict[str, FactState]
    ) -> FactState:
        body = self._write(
            "POST",
            f"/api/v1/chapters/{state.chapter_id}/memory/facts",
            {
                "expected_version": 0,
                "source_revision": state.revision,
                "title": spec.title,
                "text": spec.text,
                "quote": spec.quote,
                "status": "pending",
            },
            expected=201,
            timing="fact_write",
        ).json()
        fact = FactState(
            spec.key,
            body["id"],
            state.spec.index,
            body["revision_id"],
            body["version"],
            body["status"],
            body["source_revision"],
            spec.title,
            spec.text,
            spec.quote,
        )
        registry[spec.key] = fact
        if spec.disposition != "pending":
            self._set_fact(state, fact, status=spec.disposition)
        return fact

    def _set_fact(
        self, state: ChapterState, fact: FactState, *, status: str, text: str | None = None
    ) -> None:
        source = fact.source_revision if status == "rejected" else state.revision
        body = self._write(
            "PUT",
            f"/api/v1/chapters/{state.chapter_id}/memory/facts/{fact.fact_id}",
            {
                "expected_version": fact.version,
                "source_revision": source,
                "title": fact.title,
                "text": text or fact.text,
                "quote": fact.quote,
                "status": status,
            },
            timing="fact_write",
        ).json()
        if status == "confirmed":
            self.actions["confirm"] += 1
        fact.revision_id, fact.version = body["revision_id"], body["version"]
        fact.status, fact.source_revision, fact.text = (
            body["status"],
            body["source_revision"],
            body["text"],
        )

    def _create_structure(
        self,
        title: str,
        description: str,
        volumes: tuple[tuple[str, str], ...],
        chapters: tuple[ChapterSpec, ...],
    ) -> tuple[str, list[ChapterState]]:
        project = self._write(
            "POST", "/api/v1/projects", {"title": title, "description": description}, expected=201
        ).json()["project_id"]
        volume_ids = [
            self._write(
                "POST",
                f"/api/v1/projects/{project}/volumes",
                {"title": name, "summary": text, "position": (number + 1) * 10},
                expected=201,
            ).json()["volume_id"]
            for number, (name, text) in enumerate(volumes)
        ]
        states = []
        for spec in chapters:
            response = self._write(
                "POST",
                f"/api/v1/projects/{project}/volumes/{volume_ids[spec.volume]}/chapters",
                {"title": spec.title, "summary": spec.summary, "position": spec.position},
                expected=201,
            )
            body = response.json()
            states.append(
                ChapterState(
                    spec,
                    body["chapter_id"],
                    volume_ids[spec.volume],
                    spec.position,
                    body["current_revision_id"],
                    body["concurrency_version"],
                    "",
                    1,
                    spec.title,
                    spec.summary,
                )
            )
        return project, states

    def build(self) -> None:
        sample = self.sample
        self._session()
        self.project_id, self.chapters = self._create_structure(
            sample.title, sample.description, sample.volumes, sample.chapters
        )
        project = self.project_id
        self._write(
            "POST",
            f"/api/v1/projects/{project}/outline",
            {"title": sample.outline[0], "summary": sample.outline[1]},
            expected=201,
        )
        self._write(
            "POST",
            f"/api/v1/projects/{project}/story-bible",
            {"title": sample.bible[0], "content": sample.bible[1]},
            expected=201,
        )
        for name, role in CHARACTERS:
            self._write(
                "POST",
                f"/api/v1/projects/{project}/characters",
                {"name": name, "role": role, "profile": f"{name}：{role}。"},
                expected=201,
            )
        for state in self.chapters:
            self._save_content(state, state.spec.draft)
            self._save_content(state, state.spec.final)
            for spec in state.spec.facts:
                self._create_fact(state, spec, self.facts)
            if state.spec.index in sample.scale.ai_chapters:
                self._ai_run(state)
            if len(self.chapters) >= 8 and (state.spec.index + 1) % 8 == 0:
                self.log(f"[longform] built {state.spec.index + 1}/{len(self.chapters)} chapters")
        before = len(self._workspace(self.chapters[-1])["facts"])
        for index in sample.scale.review_chapters:
            self._review(self.chapters[index])
        self.results.data["facts_before_review_send"] = before
        self.results.data["facts_after_review_send"] = len(
            self._workspace(self.chapters[-1])["facts"]
        )
        control_project, control = self._create_structure(
            "对照小说（隔离样本）", "跨小说隔离对照", (("对照卷", ""),), sample.control_chapters
        )
        self.results.data["control_project"] = control_project
        registry: dict[str, FactState] = {}
        for state in control:
            self._save_content(state, state.spec.final)
            for spec in state.spec.facts:
                self._create_fact(state, spec, registry)
        self.control_facts = {item.fact_id for item in registry.values()}
        self.control_chapters = [item.chapter_id for item in control]
        self.control_states = control
        confirmed_per_chapter = [
            sum(
                fact.chapter == state.spec.index and fact.status == "confirmed"
                for fact in self.facts.values()
            )
            for state in self.chapters
        ]
        self.results.data["built"] = {
            "chapters": len(self.chapters),
            "non_whitespace_characters": sum(
                non_whitespace(state.content) for state in self.chapters
            ),
            "min_author_versions_per_chapter": min(state.author_saves for state in self.chapters),
            "min_confirmed_facts_per_chapter": min(confirmed_per_chapter),
            "pending_facts": sum(fact.status == "pending" for fact in self.facts.values()),
            "rejected_facts": sum(fact.status == "rejected" for fact in self.facts.values()),
            "control_chapters": len(control),
            "control_confirmed_facts": sum(
                item.status == "confirmed" for item in registry.values()
            ),
        }

    def _ai_run(self, state: ChapterState) -> None:
        base = f"/api/v1/chapters/{state.chapter_id}/ai"
        run = self._write(
            "POST",
            base + "/runs",
            {
                "profile_id": PROFILE,
                "instruction": "继续本章",
                "max_steps": 2,
                "max_output_characters": 600,
            },
            expected=201,
            timing="run_prepare_build",
        ).json()
        self._record_run(state, run)
        for step in range(2):
            before = len(self.server.calls)
            run = self._write(
                "POST", base + f"/runs/{run['run_id']}/generate", {}, timing="generate"
            ).json()
            self.actions["generate"] += 1
            if len(self.server.calls) != before + 1:
                raise EvaluationError("generate did not make exactly one model request")
            candidate = run["candidates"][-1]
            if step == 0:
                run = self._write(
                    "POST",
                    base + f"/candidates/{candidate['candidate_id']}/adopt",
                    {"idempotency_key": f"longform-{state.spec.index}-adopt"},
                    headers={"If-Match": f'"{state.version}"'},
                ).json()
                self.actions["adopt"] += 1
                content = self._call("GET", f"/api/v1/chapters/{state.chapter_id}/content").json()
                expected = state.content + "\n\n" + candidate["text"]
                if content["content"] != expected:
                    raise EvaluationError("adopted content does not equal text plus candidate")
                state.content = expected
                state.revision = content["current_revision_id"]
                state.version = content["concurrency_version"]
                state.revisions += 1
                for fact in self.facts.values():
                    if fact.chapter == state.spec.index and fact.status == "confirmed":
                        self._set_fact(state, fact, status="confirmed")
            else:
                self._write("POST", base + f"/candidates/{candidate['candidate_id']}/discard", {})
                self.actions["discard"] += 1

    def _record_run(self, state: ChapterState, run: dict[str, Any]) -> None:
        references = [
            (fact_id, revision)
            for source in run["context"]["manifest"]["sources"]
            if source["source"] == "story_memory" and source["omitted_reason"] is None
            for fact_id, revision in source["references"]
        ]
        self.runs[run["run_id"]] = {
            "chapter": state.chapter_id,
            "references": references,
            "sha256": run["context"]["sha256"],
            "characters": run["context"]["manifest"]["character_count"],
        }

    def _review(self, state: ChapterState) -> None:
        base = f"/api/v1/chapters/{state.chapter_id}/memory/reviews"
        review = self._write(
            "POST", base, {"source_revision": state.revision, "profile_id": PROFILE}, expected=201
        ).json()
        before = len(self.server.calls)
        sent = self._write(
            "POST",
            base + f"/{review['id']}/send",
            {"expected_version": review["version"]},
            timing="review_send",
        ).json()
        self.actions["review_send"] += 1
        if len(self.server.calls) != before + 1 or sent["status"] != "completed":
            raise EvaluationError("review send did not complete with exactly one model request")
        self.reviews[review["id"]] = {
            "chapter": state.chapter_id,
            "source_revision": review["source_revision"],
            "facts": [
                (item["id"], item["revision_id"], item["chapter_id"]) for item in review["facts"]
            ],
        }

    def _workspace(self, state: ChapterState, timing: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = self._call(
            "GET", f"/api/v1/chapters/{state.chapter_id}/memory", timing=timing
        ).json()
        return body

    # -- ground truth ----------------------------------------------------------
    def _current(self) -> dict[str, str]:
        return {item.chapter_id: item.revision for item in self.chapters}

    def _chapter_id(self, index: int) -> str:
        return self.chapters[index].chapter_id

    def eligible(self, state: ChapterState) -> set[str]:
        order, current = self._order(), self._current()
        return {
            fact.fact_id
            for fact in self.facts.values()
            if fact.status == "confirmed"
            and current[self._chapter_id(fact.chapter)] == fact.source_revision
            and order[self._chapter_id(fact.chapter)] < order[state.chapter_id]
        }

    def expected_impacts(self) -> set[str]:
        order, current = self._order(), self._current()
        by_id = {fact.fact_id: fact for fact in self.facts.values()}

        def invalid(fact_id: str, revision: str, consumer: str) -> bool:
            fact = by_id.get(fact_id)
            if fact is None:
                return True
            chapter = self._chapter_id(fact.chapter)
            return (
                fact.revision_id != revision
                or current[chapter] != fact.source_revision
                or fact.status != "confirmed"
                or order[chapter] >= order[consumer]
            )

        impacted = {
            self._chapter_id(fact.chapter)
            for fact in by_id.values()
            if fact.status != "rejected"
            and current[self._chapter_id(fact.chapter)] != fact.source_revision
        }
        for review in self.reviews.values():
            if current[review["chapter"]] != review["source_revision"] or any(
                invalid(fact_id, revision, review["chapter"])
                for fact_id, revision, _ in review["facts"]
            ):
                impacted.add(review["chapter"])
        for run in self.runs.values():
            if any(
                invalid(fact_id, revision, run["chapter"])
                for fact_id, revision in run["references"]
            ):
                impacted.add(run["chapter"])
        return impacted

    def recall_violations(
        self, *, timing: str | None = None
    ) -> tuple[int, list[dict[str, Any]], dict[str, set[str]]]:
        by_id = {fact.fact_id: fact for fact in self.facts.values()}
        order, current = self._order(), self._current()
        violations = 0
        rows = []
        recalled_sets: dict[str, set[str]] = {}
        for state in self.chapters:
            workspace = self._workspace(state, timing=timing)
            recalled = workspace["recalled_facts"]
            cost = sum(len(json.dumps(item, ensure_ascii=False)) + 2 for item in recalled)
            eligible = self.eligible(state)
            bad = 0
            for item in recalled:
                fact = by_id.get(item["id"])
                if (
                    fact is None
                    or item["id"] in self.control_facts
                    or fact.status != "confirmed"
                    or item["revision_id"] != fact.revision_id
                    or item["source_revision"] != current[self._chapter_id(fact.chapter)]
                    or order[self._chapter_id(fact.chapter)] >= order[state.chapter_id]
                ):
                    bad += 1
            count_ok = len(recalled) + workspace["omitted_facts"] == len(eligible)
            budget_ok = len(recalled) <= RECALL_ITEM_LIMIT and cost <= RECALL_CHARACTER_LIMIT
            violations += bad + (not count_ok) + (not budget_ok)
            recalled_sets[state.chapter_id] = {item["id"] for item in recalled}
            rows.append(
                {
                    "chapter": state.spec.index + 1,
                    "recalled": len(recalled),
                    "omitted": workspace["omitted_facts"],
                    "eligible": len(eligible),
                    "characters": cost,
                }
            )
        for state in self.control_states:
            workspace = self._workspace(state)
            if any(item["id"] not in self.control_facts for item in workspace["recalled_facts"]):
                violations += 1
        return violations, rows, recalled_sets

    def impacts_now(self) -> set[str]:
        return {item["chapter_id"] for item in self._workspace(self.chapters[-1])["impacts"]}

    # -- measurement phases ----------------------------------------------------
    def persistence_check(self, database: Path) -> tuple[int, dict[str, int]]:
        mismatches = 0
        details = {"content": 0, "revisions": 0, "facts": 0, "runs": 0, "reviews": 0}
        counts = revision_counts(database)
        for state in self.chapters:
            body = self._call(
                "GET", f"/api/v1/chapters/{state.chapter_id}/content", timing="content_read"
            ).json()
            if (
                hashlib.sha256(body["content"].encode()).hexdigest()
                != hashlib.sha256(state.content.encode()).hexdigest()
                or body["current_revision_id"] != state.revision
            ):
                details["content"] += 1
            if counts.get(state.chapter_id) != state.revisions:
                details["revisions"] += 1
        stored = {item["id"]: item for item in self._workspace(self.chapters[-1])["facts"]}
        for fact in self.facts.values():
            item = stored.get(fact.fact_id)
            if item is None or (item["revision_id"], item["version"], item["status"]) != (
                fact.revision_id,
                fact.version,
                fact.status,
            ):
                details["facts"] += 1
        if len(stored) != len(self.facts):
            details["facts"] += 1
        for run_id, run in self.runs.items():
            body = self._call("GET", f"/api/v1/chapters/{run['chapter']}/ai/runs/{run_id}").json()
            if body["context"]["sha256"] != run["sha256"]:
                details["runs"] += 1
            statuses = sorted(item["status"] for item in body["candidates"])
            if run.get("generated") and statuses != ["adopted", "discarded"]:
                details["runs"] += 1
        for review_id, review in self.reviews.items():
            state = next(item for item in self.chapters if item.chapter_id == review["chapter"])
            listed = {item["id"]: item for item in self._workspace(state)["reviews"]}
            if listed.get(review_id, {}).get("status") != "completed":
                details["reviews"] += 1
        mismatches = sum(details.values())
        return mismatches, details

    def run(self) -> Results:
        started = time.perf_counter()
        data = self.results.data
        sample = self.sample
        root = self.work_root / "main-root"
        data["environment"] = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "cpu_count": os.cpu_count(),
        }
        data["sample"] = {
            "scale": sample.scale.name,
            "fingerprint": sample.fingerprint(),
            "chapters": len(sample.chapters),
            "volumes": sample.scale.volumes,
            "non_whitespace_characters": sum(
                non_whitespace(item.final) for item in sample.chapters
            ),
            "characters": len(CHARACTERS),
            "confirmed_facts": sum(
                f.disposition == "confirmed" for c in sample.chapters for f in c.facts
            ),
            "pending_facts": sum(
                f.disposition == "pending" for c in sample.chapters for f in c.facts
            ),
            "rejected_facts": sum(
                f.disposition == "rejected" for c in sample.chapters for f in c.facts
            ),
            "probes": len(sample.probes),
        }
        with FakeModelServer() as server, isolated_environment(root):
            self.server = server
            database = migrate(root)
            self.log("[longform] phase 1/6 build sample")
            with application(root, server.base_url) as client:
                self.client = client
                self.build()
            for run in self.runs.values():
                run["generated"] = True
            self.log("[longform] phase 2/6 restart and verify persistence")
            calls_before_measure = len(server.calls)
            with application(root, server.base_url) as client:
                self.client = client
                self._session()
                mismatches, details = self.persistence_check(database)
                self.results.data["persistence_details"] = details
                self._measure(database, calls_before_measure)
        data["elapsed_seconds"] = round(time.perf_counter() - started, 1)
        data["peak_rss_bytes"] = peak_rss_bytes()
        self._score(mismatches)
        return self.results

    def _measure(self, database: Path, calls_before: int) -> None:
        data = self.results.data
        sample = self.sample
        self.log("[longform] phase 3/6 recall and context assembly")
        violations, rows, recalled = self.recall_violations(timing="workspace_read")
        data["recall_violations"] = violations
        data["recall_rows"] = rows
        hits = [
            probe
            for probe in sample.probes
            if self.facts[probe.fact_key].fact_id
            in recalled[self._chapter_id(probe.target_chapter)]
        ]
        data["probe_hits"] = len(hits)
        context_sizes = []
        for state in self.chapters:
            run = self._write(
                "POST",
                f"/api/v1/chapters/{state.chapter_id}/ai/runs",
                {"profile_id": PROFILE, "instruction": "继续本章"},
                expected=201,
                timing="run_prepare",
            ).json()
            self._record_run(state, run)
            context_sizes.append(run["context"]["manifest"]["character_count"])
        data["context_max_characters"] = max(context_sizes)
        data["baseline_impacts"] = sorted(self.impacts_now())
        data["calls_during_measure_reads"] = len(self.server.calls) - calls_before
        self.log("[longform] phase 4/6 backup, verify and restore")
        self._backup(database)
        self.log("[longform] phase 5/6 change impact")
        hit_sources = [probe.source_chapter for probe in hits] or [0]
        self._changes(hit_sources[0], database)

    def _backup(self, database: Path) -> None:
        data = self.results.data
        calls = len(self.server.calls)
        timings: dict[str, float] = {}
        started = time.perf_counter()
        created = self._write("POST", "/api/v1/backups", {}, expected=201).json()
        timings["create_s"] = time.perf_counter() - started
        backup_id = created["backup_id"]
        started = time.perf_counter()
        verified = self._write("POST", f"/api/v1/backups/{backup_id}/verify", {}).json()
        timings["verify_s"] = time.perf_counter() - started
        started = time.perf_counter()
        self._write(
            "POST",
            f"/api/v1/backups/{backup_id}/restore",
            {"target_name": "restored-copy", "confirm_new_copy": True},
        )
        timings["restore_s"] = time.perf_counter() - started
        restored_root = self.work_root / "restored-copy"
        restored_db = restored_root / "data" / "aiwebnovel.sqlite3"
        source_rows, restored_rows = table_rows(database), table_rows(restored_db)
        differing = sorted(
            name
            for name in source_rows.keys() | restored_rows.keys()
            if source_rows.get(name) != restored_rows.get(name)
        )
        readback = 0
        main_client = self.client
        with application(restored_root, self.server.base_url) as client:
            self.client = client
            for state in self.chapters:
                content = self._call("GET", f"/api/v1/chapters/{state.chapter_id}/content").json()[
                    "content"
                ]
                readback += content != state.content
            restored_recall = [
                item["id"] for item in self._workspace(self.chapters[-1])["recalled_facts"]
            ]
        self.client = main_client
        source_recall = [
            item["id"] for item in self._workspace(self.chapters[-1])["recalled_facts"]
        ]
        data["backup"] = {
            "status": verified["status"],
            "zip_bytes": created["file_bytes"],
            "counts": created["summary"]["counts"],
            "differing_tables": differing,
            "tables_compared": len(source_rows),
            "rows_compared": sum(len(rows) for rows in source_rows.values()),
            "readback_mismatches": readback,
            "recall_equal": restored_recall == source_recall,
            **{key: round(value, 2) for key, value in timings.items()},
        }
        data["database_bytes"] = sum(
            Path(f"{database}{suffix}").stat().st_size
            for suffix in ("", "-wal")
            if Path(f"{database}{suffix}").exists()
        )
        data["calls_during_backup"] = len(self.server.calls) - calls

    def _changes(self, edit_index: int, database: Path) -> None:
        data = self.results.data
        calls = len(self.server.calls)
        hashes = {run_id: run["sha256"] for run_id, run in self.runs.items()}
        scenarios: list[dict[str, Any]] = []
        self._previous_impacts = (self.expected_impacts(), self.impacts_now())
        # E1: edit an earlier chapter whose facts later chapters recalled.
        state = self.chapters[edit_index]
        anchor = state.spec.facts[0].quote
        self._save_content(state, state.content.replace(anchor, "（作者删去了这一句）"))
        scenarios.append(self._scenario("edit_earlier_text", edit_index))
        # E2: revise a confirmed fact that a completed review froze.
        frozen = [fact_id for review in self.reviews.values() for fact_id, _, _ in review["facts"]]
        frozen += [fact_id for run in self.runs.values() for fact_id, _ in run["references"]]
        by_id = {fact.fact_id: fact for fact in self.facts.values()}
        target = next(
            by_id[fact_id]
            for fact_id in frozen
            if fact_id in by_id
            and by_id[fact_id].chapter != edit_index
            and by_id[fact_id].status == "confirmed"
        )
        owner = self.chapters[target.chapter]
        self._set_fact(owner, target, status="confirmed", text=target.text + "（作者修订）")
        scenarios.append(self._scenario("revise_confirmed_fact", target.chapter))
        # E3: move the first chapter of volume 2 to the end of that volume.
        moved = self.chapters[self.sample.scale.chapters_per_volume]
        last = max(item.position for item in self.chapters if item.volume_id == moved.volume_id)
        body = self._write(
            "PUT",
            f"/api/v1/chapters/{moved.chapter_id}",
            {"title": moved.title, "summary": moved.summary, "position": last + 5},
            headers={"If-Match": f'"{moved.version}"'},
        ).json()
        moved.position = body["position"]
        moved.revision = body["current_revision_id"]
        moved.version = body["concurrency_version"]
        moved.revisions += 1
        scenarios.append(self._scenario("reorder_chapter", moved.spec.index))
        violations, _, _ = self.recall_violations()
        changed = 0
        for run_id, run in self.runs.items():
            body = self._call("GET", f"/api/v1/chapters/{run['chapter']}/ai/runs/{run_id}").json()
            changed += body["context"]["sha256"] != hashes[run_id]
        # The independent impact derivation relies on the harness's revision model (each
        # content save, adoption and structure edit appends exactly one revision). Verify it
        # against the stored rows after the changes so a drift cannot hide behind equal sets.
        counts = revision_counts(database)
        data["revision_model_mismatches_after_changes"] = sum(
            counts.get(state.chapter_id) != state.revisions for state in self.chapters
        )
        data["change_scenarios"] = scenarios
        data["recall_violations_after_changes"] = violations
        data["frozen_context_changes"] = changed
        data["calls_during_changes"] = len(self.server.calls) - calls

    def _scenario(self, name: str, chapter: int) -> dict[str, Any]:
        expected = self.expected_impacts()
        actual = self.impacts_now()
        found = len(expected & actual)
        previous_expected, previous_actual = self._previous_impacts
        self._previous_impacts = (expected, actual)
        return {
            "newly_expected": len(expected - previous_expected),
            "newly_detected": len(actual - previous_actual),
            "changed_chapter_detected": self._chapter_id(chapter) in actual,
            "name": name,
            "changed_chapter": chapter + 1,
            "expected": len(expected),
            "detected": len(actual),
            "true_positive": found,
            "recall": 1.0 if not expected else round(found / len(expected), 4),
            "precision": 1.0 if not actual else round(found / len(actual), 4),
            "exact": expected == actual,
            "dependents_beyond_changed": len(expected - {self._chapter_id(chapter)}),
        }

    # -- scoring ---------------------------------------------------------------
    def _score(self, mismatches: int) -> None:
        data, add, t = self.results.data, self.results.add, self.timings
        built = data["built"]
        le01 = (
            built["chapters"] >= 40
            and built["non_whitespace_characters"] >= 100_000
            and built["min_author_versions_per_chapter"] >= 2
            and built["min_confirmed_facts_per_chapter"] >= 3
            and built["pending_facts"] > 0
            and built["rejected_facts"] > 0
            and built["control_chapters"] > 0
            and built["control_confirmed_facts"] > 0
        )
        is_full = self.sample.scale.name == "full"
        measured = dict(built)
        if not is_full:
            # The pre-registered scale threshold binds only the full run; a reduced sample
            # cannot meet it by construction, so it is reported N/A rather than PASS.
            measured["note"] = (
                f"N/A：--scale {self.sample.scale.name} 是缩小样本，规模阈值只对 full 判定"
                f"（本样本{'满足' if le01 else '未满足'}规模阈值）"
            )
        add(
            "LE-01",
            "样本规模",
            "主小说 ≥40 章、≥100,000 非空白字符；每章 ≥2 个作者正文版本；确认事实 ≥3/章；含待确认、驳回事实与对照小说",
            measured,
            le01 if is_full else None,
        )
        add("LE-02", "重启后持久化完整性", "0 处不符", data["persistence_details"], mismatches == 0)
        save, facts = summary(t.get("content_save", [])), summary(t.get("fact_write", []))
        add(
            "LE-03",
            "写入延迟",
            "正文保存 p95 ≤1,000 ms 且最大 ≤3,000 ms；事实写入 p95 ≤1,000 ms",
            {"content_save": save, "fact_write": facts},
            save["p95_ms"] <= 1000 and save["max_ms"] <= 3000 and facts["p95_ms"] <= 1000,
        )
        read, workspace = summary(t.get("content_read", [])), summary(t.get("workspace_read", []))
        add(
            "LE-04",
            "读取延迟",
            "正文读取 p95 ≤300 ms；工作台读取 p95 ≤2,000 ms",
            {"content_read": read, "workspace_read": workspace},
            read["p95_ms"] <= 300 and workspace["p95_ms"] <= 2000,
        )
        rows = data["recall_rows"]
        add(
            "LE-05",
            "召回正确性与预算",
            "0 处违例（≤24 项、≤10,000 字符、来源/顺序/状态/小说均有效、计数一致）",
            {
                "violations": data["recall_violations"],
                "max_recalled": max(row["recalled"] for row in rows),
                "max_characters": max(row["characters"] for row in rows),
                "max_omitted": max(row["omitted"] for row in rows),
            },
            data["recall_violations"] == 0,
        )
        probes = len(self.sample.probes)
        rate = data["probe_hits"] / probes if probes else 0.0
        add(
            "LE-06",
            "定向召回探针",
            "命中率 ≥90%",
            {"hits": data["probe_hits"], "probes": probes, "rate": round(rate, 4)},
            rate >= 0.9,
        )
        scenarios = data["change_scenarios"]
        add(
            "LE-07",
            "变更影响",
            "基线无影响；三场景影响集合与独立推算完全相等；变更后召回 0 违例；冻结上下文不变",
            {
                "baseline_impacts": len(data["baseline_impacts"]),
                "scenarios": scenarios,
                "recall_violations_after_changes": data["recall_violations_after_changes"],
                "frozen_context_changes": data["frozen_context_changes"],
                "revision_model_mismatches_after_changes": data[
                    "revision_model_mismatches_after_changes"
                ],
            },
            not data["baseline_impacts"]
            and all(item["exact"] and item["dependents_beyond_changed"] > 0 for item in scenarios)
            and data["recall_violations_after_changes"] == 0
            and data["frozen_context_changes"] == 0
            and data["revision_model_mismatches_after_changes"] == 0,
        )
        backup = data["backup"]
        add(
            "LE-08",
            "备份/校验/恢复",
            "valid；全部业务表逐行一致；HTTP 读回一致；创建/校验/恢复各 ≤60 s",
            backup,
            backup["status"] == "valid"
            and not backup["differing_tables"]
            and backup["readback_mismatches"] == 0
            and backup["recall_equal"]
            and max(backup["create_s"], backup["verify_s"], backup["restore_s"]) <= 60,
        )
        limit = 200 * 1024 * 1024
        add(
            "LE-09",
            "存储占用",
            "数据库 ≤200 MB；备份 ZIP ≤200 MB",
            {"database_bytes": data["database_bytes"], "zip_bytes": backup["zip_bytes"]},
            data["database_bytes"] <= limit and backup["zip_bytes"] <= limit,
        )
        prepare = summary(t.get("run_prepare", []))
        prompt_max = max((call.prompt_characters for call in self.server.calls), default=0)
        add(
            "LE-10",
            "生成上下文组装",
            "准备任务 p95 ≤3,000 ms；冻结上下文 ≤60,000 字符；单次请求消息 ≤100,000 字符",
            {
                "run_prepare": prepare,
                "context_max_characters": data["context_max_characters"],
                "prompt_max_characters": prompt_max,
            },
            prepare["p95_ms"] <= 3000
            and data["context_max_characters"] <= CONTEXT_LIMIT
            and prompt_max <= PROMPT_LIMIT,
        )
        calls = self.server.calls
        explicit = self.actions["generate"] + self.actions["review_send"]
        accounting = {}
        for kind in ("continue", "review"):
            subset = [call for call in calls if call.kind == kind]
            accounting[kind] = {
                "requests": len(subset),
                "prompt_characters": sum(c.prompt_characters for c in subset),
                "completion_characters": sum(c.completion_characters for c in subset),
                "prompt_tokens_estimate": sum(c.prompt_tokens_estimate for c in subset),
                "completion_tokens_estimate": sum(c.completion_tokens_estimate for c in subset),
            }
        data["cost_accounting"] = accounting
        silent = (
            data["calls_during_measure_reads"]
            + data["calls_during_backup"]
            + data["calls_during_changes"]
        )
        add(
            "LE-11",
            "模型调用计量",
            "请求数 = 显式生成/发送操作数；准备、工作台、刷新、备份恢复期间 0 请求",
            {
                "requests": len(calls),
                "explicit_actions": explicit,
                "requests_outside_explicit_actions": silent,
                "by_kind": accounting,
            },
            len(calls) == explicit and silent == 0,
        )
        adopted = self.actions["adopt"]
        confirmed_now = sum(fact.status == "confirmed" for fact in self.facts.values())
        add(
            "LE-12",
            "作者权限",
            "评审发送前后事实数不变；采用数 = 显式采用操作数；确认事实均来自显式确认",
            {
                "facts_before_review_send": data["facts_before_review_send"],
                "facts_after_review_send": data["facts_after_review_send"],
                "adopt_actions": adopted,
                "confirm_actions": self.actions["confirm"],
                "confirmed_facts": confirmed_now,
            },
            data["facts_before_review_send"] == data["facts_after_review_send"]
            and adopted == len(self.sample.scale.ai_chapters)
            and confirmed_now <= self.actions["confirm"],
        )
        rss = data["peak_rss_bytes"]
        add(
            "LE-13",
            "整体资源",
            "完整运行 ≤30 分钟；峰值常驻内存 ≤1.5 GiB",
            {"elapsed_seconds": data["elapsed_seconds"], "peak_rss_bytes": rss},
            data["elapsed_seconds"] <= 1800 and (rss is None or rss <= 1.5 * 1024**3),
        )


# ---------------------------------------------------------------------------
# Reports and command line
# ---------------------------------------------------------------------------


def write_reports(results: Results, work_root: Path) -> tuple[Path, Path]:
    payload = {
        "contract": "docs/LONGFORM_EVALUATION.md",
        "overall": overall(results),
        "metrics": [asdict(metric) for metric in results.metrics],
        "data": results.data,
    }
    json_path = work_root / "longform-report.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=list), encoding="utf-8"
    )
    lines = [
        "# RF-16 长篇规模评测报告",
        "",
        f"总体：**{payload['overall']}**；样本 `{results.data['sample']['scale']}`，指纹 `{results.data['sample']['fingerprint'][:16]}`。",
        "",
        *(
            [
                "> 缩小样本（非 full）：N/A 项不参与总体判定；契约结论只来自 `--scale full` 完整运行。",
                "",
            ]
            if results.data["sample"]["scale"] != "full"
            else []
        ),
        "| 编号 | 指标 | 阈值 | 实测 | 结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for metric in results.metrics:
        verdict = "N/A" if metric.passed is None else ("PASS" if metric.passed else "FAIL")
        measured = json.dumps(metric.measured, ensure_ascii=False, default=list).replace("|", "/")
        lines.append(
            f"| {metric.id} | {metric.name} | {metric.threshold} | `{measured}` | {verdict} |"
        )
    md_path = work_root / "longform-report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def overall(results: Results) -> str:
    verdicts = [metric.passed for metric in results.metrics if metric.passed is not None]
    return "PASS" if verdicts and all(verdicts) else "FAIL"


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RF-16 long-form scale evaluation (isolated data only)"
    )
    parser.add_argument(
        "--work-root", required=True, help="absolute new or empty folder outside the repository"
    )
    parser.add_argument("--scale", choices=sorted(SCALES), default="full")
    parser.add_argument("--keep-data", action="store_true", help="keep the isolated data roots")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parse_arguments(argv)
        work_root = validate_work_root(arguments.work_root)
    except IsolationError as error:
        print(f"[longform] {error}", file=sys.stderr)
        return 2
    except SystemExit as error:
        return 2 if error.code else 0
    work_root.mkdir(exist_ok=True)
    evaluation = LongformEvaluation(work_root, arguments.scale)
    try:
        results = evaluation.run()
        json_path, md_path = write_reports(results, work_root)
    finally:
        if not arguments.keep_data:
            for name in ("main-root", "restored-copy"):
                target = work_root / name
                if target.exists() and target.is_relative_to(work_root) and not target.is_symlink():
                    shutil.rmtree(target)
    print(
        json.dumps({"overall": overall(results), "json": json_path.name, "markdown": md_path.name})
    )
    return 0 if overall(results) == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
