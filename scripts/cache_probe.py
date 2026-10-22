#!/usr/bin/env python3
"""r49 — 프롬프트 캐시 프로브. 세션 jsonl(Claude Code 원천)의 assistant usage
숫자 6필드만 집계해 보고한다.

읽기 전용 관측 도구 — 세션 jsonl·프로젝트 디렉터리·프로세스에 쓰기·시그널이 없고
--save 감사 JSON이 유일한 쓰기다(워치독 권한 계약 준용). keepalive 전송·compact
실행·/loop 기동 등 자동화 일절 없음 — 보고만.

파싱: type=='assistant' ∧ message.usage 존재 레코드만. message.id 키 dedup(첫 등장
우선 — 세션 jsonl은 동일 usage 레코드를 중복 기록한다, 실측 138레코드/35 id).
파손 라인은 skip 가산. 추출 필드(숫자 화이트리스트 — 이 외 키 출력 금지, usage_log
계약 승계): input_tokens·cache_read_input_tokens·cache_creation_input_tokens·
output_tokens·ephemeral_1h_input_tokens·ephemeral_5m_input_tokens(후 2종의 원천은
message.usage.cache_creation.* — TTL 계급 관측 신호, 부재 시 0).

종료코드: 0 보고 성공 / 2 bypass(원천 부재·usage 0건·전량 파손 — stderr 사유).
exit 1 없음 — 판정 도구가 아니다. stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATE = 'cache_probe'
USAGE_FIELDS = ('input_tokens', 'cache_read_input_tokens',
                'cache_creation_input_tokens', 'output_tokens')
EPHEMERAL_FIELDS = ('ephemeral_1h_input_tokens', 'ephemeral_5m_input_tokens')
ALL_FIELDS = USAGE_FIELDS + EPHEMERAL_FIELDS


class SourceMissingError(Exception):
    """원천 부재·usage 0건·전량 파손 — exit 2 bypass 근거."""


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) \
        and not isinstance(value, bool) else 0


def _parse_line(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def expand_sources(paths: list[str]) -> tuple[list[Path], list[str]]:
    """경로 확장 — 파일은 그대로, 디렉터리는 *.jsonl 비재귀 수집. 부재 경로 반환."""
    files: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(path.glob('*.jsonl')))
        elif path.is_file():
            files.append(path)
        else:
            missing.append(str(path))
    return files, missing


def collect(paths: list[str]) -> dict[str, Any]:
    """원천 전체에서 dedup usage 레코드를 수집한다(텍스트 필드 미포함)."""
    files, missing = expand_sources(paths)
    if not files:
        raise SourceMissingError(
            '원천 부재: ' + (', '.join(missing) if missing
                             else '지정 경로에 *.jsonl 없음'))
    seen: set[Any] = set()
    records: list[dict[str, Any]] = []
    dropped_duplicates = 0
    skipped_bad_lines = 0
    skipped_bad_files = 0
    for path in files:
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as error:
            skipped_bad_files += 1
            print(f'WARN cache probe: 파일 읽기 실패 {path}: {error}',
                  file=sys.stderr)
            continue
        for raw in text.splitlines():
            line = _parse_line(raw)
            if line is None:
                if raw.strip():
                    skipped_bad_lines += 1
                continue
            if line.get('type') != 'assistant':
                continue
            message = line.get('message') \
                if isinstance(line.get('message'), dict) else {}
            usage = message.get('usage') \
                if isinstance(message.get('usage'), dict) else None
            if usage is None:
                continue
            msg_id = message.get('id')
            if msg_id is not None:
                if msg_id in seen:
                    dropped_duplicates += 1
                    continue
                seen.add(msg_id)
            creation = usage.get('cache_creation') \
                if isinstance(usage.get('cache_creation'), dict) else {}
            records.append({'message_id': msg_id,
                            'timestamp': line.get('timestamp'),
                            **{name: _int(usage.get(name))
                               for name in USAGE_FIELDS},
                            **{name: _int(creation.get(name))
                               for name in EPHEMERAL_FIELDS}})
    if not records:
        raise SourceMissingError(
            f'usage 레코드 0건(파손 {skipped_bad_lines}행·읽기 실패 '
            f'{skipped_bad_files}파일 포함) — '
            '캐시 관측 원천 부재')
    return {'files': len(files), 'records': records,
            'dropped_duplicates': dropped_duplicates,
            'skipped_bad_lines': skipped_bad_lines,
            'skipped_bad_files': skipped_bad_files,
            'missing_files': missing}


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    """집계 — hit_ratio = cache_read / max(1, input+cache_read+cache_creation).

    cache_creation=0 보고 관측(2026-10-22)으로 분모 왜곡 가능성이 있다(§4 한계 2).
    """
    sums = {name: sum(record[name] for record in data['records'])
            for name in ALL_FIELDS}
    denominator = max(1, sums['input_tokens']
                      + sums['cache_read_input_tokens']
                      + sums['cache_creation_input_tokens'])
    stamps = sorted(stamp for stamp in
                    (_timestamp(record['timestamp'])
                     for record in data['records'])
                    if stamp is not None)
    gaps = [(later - earlier).total_seconds()
            for earlier, later in zip(stamps, stamps[1:])]
    return {'ok': True, 'gate': GATE, 'files': data['files'],
            'records': len(data['records']),
            'dropped_duplicates': data['dropped_duplicates'],
            'skipped_bad_lines': data['skipped_bad_lines'],
            'skipped_bad_files': data['skipped_bad_files'],
            'missing_files': data['missing_files'],
            'sums': sums,
            'hit_ratio': sums['cache_read_input_tokens'] / denominator,
            'max_gap_s': max(gaps) if gaps else None,
            'first_ts': stamps[0].isoformat() if stamps else None,
            'last_ts': stamps[-1].isoformat() if stamps else None}


def save_report(report: dict[str, Any], directory: str) -> str | None:
    """감사 JSON 1건 저장 — cache_probe의 유일한 쓰기다."""
    try:
        target = Path(directory).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out = target / f'cache-probe-{stamp}.json'
        out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True)
                       + '\n', encoding='utf-8')
        return str(out)
    except OSError as error:
        print(f'WARN cache probe: 감사 저장 실패: {error}', file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='r49 프롬프트 캐시 프로브(읽기 전용 관측 — 보고만)')
    parser.add_argument('--jsonl', nargs='+', required=True,
                        help='세션 jsonl 경로(디렉터리 지정 시 *.jsonl 비재귀 수집)')
    parser.add_argument('--save',
                        help='감사 JSON 저장 디렉터리(유일한 쓰기)')
    args = parser.parse_args(argv)
    try:
        data = collect(args.jsonl)
    except SourceMissingError as error:
        print(f'FAIL cache probe: {error}', file=sys.stderr)
        return 2
    report = summarize(data)
    if args.save:
        saved = save_report(report, args.save)
        if saved:
            print(f'SAVED {saved}', file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
