#!/usr/bin/env python3
"""트리 소유 게이트 훅 단위테스트 — SessionStart·PreToolUse 어댑터 전수(T19·T20·T21~T31b).

r27 SessionStart 훅 케이스(T19·T20)와 r28 격리 가드 케이스(T21~T31b)를 담는다 —
r28에서 test_tree_gate.py에서 분할 이전했다(r25 worktree_gate/hardening 2파일 선례
준용 — 게이트 본체 분기는 본 파일과 분리). 테스트는 subprocess로 훅을 실행한다
(import 방식 수집 ImportError 회피 관습 준용). 훅 부재 환경(미러 배포 —
.claude/hooks 경로 없음)에서는 전 케이스가 skipTest 가드로 자동 제외된다
(저장소=실행·미러=skip — 단정 축소가 아니다).
claims 대응: T19·T20=C14(r27), T21~T24=C5, T25=C6, T26~T27=C9, T28=C7,
T29·T29b=C8, T30=C10, T31=C11, T31b=C11b(r28).
fixture 계약: test_worktree_gate 준용 — /tmp ext4 기본(tmp.mkdtemp, DrvFs chmod
유도 금지 r25 H1)·clean_env 전역 config 격리·setUp 저장소 내부 가드.
TREE_GATE_TEST_ROOT env로 fixture 루트 지정 가능(r25 M-g 관례).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/tree_gate.py'
HOOK = ROOT / '.claude/hooks/tree_claim_hook.py'

# 부모 환경 오염 차단 — fixture git과 게이트·훅 subprocess 모두 적용.
FIXTURE_ENV_KEYS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                    'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL',
                    'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL')
GIT_IDENTITY = ('-c', 'user.email=tree-gate-test@example.com',
                '-c', 'user.name=tree-gate-test')

_ISOLATION_TMP = tempfile.TemporaryDirectory()
XDG_ISOLATION_DIR = os.path.join(_ISOLATION_TMP.name, 'xdg')
os.makedirs(XDG_ISOLATION_DIR, exist_ok=True)


def clean_env():
    env = dict(os.environ)
    for key in FIXTURE_ENV_KEYS:
        env.pop(key, None)
    env.pop('CLAUDE_SESSION_ID', None)  # T18 폴백 판정의 전제 — 부모 env 차단
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    env['XDG_CONFIG_HOME'] = XDG_ISOLATION_DIR
    return env


def git(repo, *args):
    return subprocess.run(['git', '-c', 'core.autocrlf=false', *GIT_IDENTITY, *args],
                          cwd=repo, capture_output=True, text=True, env=clean_env())


def write_file(base, name, content):
    path = Path(base) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run_gate(cwd, *args, env_extra=None):
    """게이트 subprocess 호출 — claim 설치 등 fixture 구성용."""
    env = clean_env()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(GATE), *args],
                          cwd=str(cwd), capture_output=True, text=True, env=env)


def run_hook(repo, session, project_dir=None):
    """SessionStart 훅 subprocess — stdin JSON 주입·CLAUDE_PROJECT_DIR로 fixture 지정."""
    env = clean_env()
    env['CLAUDE_PROJECT_DIR'] = str(project_dir if project_dir is not None else repo)
    payload = json.dumps({'session_id': session, 'hook_event_name': 'SessionStart',
                          'source': 'startup'})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(repo),
                          timeout=30)


class TreeClaimHookTests(unittest.TestCase):
    """T19·T20·T21~T31b — 훅 어댑터 케이스(r28 분할 — 저장소 국소, 미러는 skip)."""

    maxDiff = None

    def setUp(self):
        env_root = os.environ.get('TREE_GATE_TEST_ROOT')
        if env_root:
            self.root = Path(env_root) / f'tgate-{uuid.uuid4().hex[:8]}'
            self.root.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
        # 루트가 git 저장소 내부면 fixture가 호스트 본체에서 실행된다 — fail(test_worktree_gate 가드 준용).
        inside = git(self.root, 'rev-parse', '--is-inside-work-tree')
        if inside.returncode == 0 and inside.stdout.strip() == 'true':
            self.fail(f'fixture 루트가 git 저장소 내부다({self.root}) — 호스트 오염 방지: '
                      'TREE_GATE_TEST_ROOT를 저장소 밖으로 옮겨라')

    def make_repo(self):
        repo = self.root / f'repo-{uuid.uuid4().hex[:8]}'
        repo.mkdir()
        write_file(repo, 'docs/readme.md', 'readme\n')
        write_file(repo, 'src/main.py', 'print("main")\n')
        self.assertEqual(git(repo, '-c', 'advice.defaultBranch=false',
                             'init').returncode, 0)
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        self.assertEqual(git(repo, 'commit', '-m', 'init').returncode, 0)
        return repo

    def registry(self, repo):
        return Path(repo) / '.git' / 'effort-router-tree-claims'

    def claim_files(self, repo, session):
        return list(self.registry(repo).glob(f'*-{session}.json'))

    def claim_file(self, repo, session):
        matches = self.claim_files(repo, session)
        self.assertEqual(len(matches), 1, f'{session} claim 파일 탐색: {matches}')
        return matches[0]

    def install_gate(self, repo):
        """훅 계약 형상 구성 — 훅은 $CLAUDE_PROJECT_DIR/scripts/tree_gate.py를
        찾는다(r27 §4.9). fixture를 설치된 프로젝트 레이아웃으로 맞춘다."""
        scripts = Path(repo) / 'scripts'
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy(GATE, scripts / 'tree_gate.py')

    def require_hook(self):
        if not HOOK.is_file():  # 저장소 국소 훅 부재 환경(미러) — skip 가드(번들 §7)
            self.skipTest('훅 부재(미러 배포 환경 — 저장소 국소 훅 케이스 skip)')

    def foreign_repo(self, scope=None):
        """foreign claim(s-a) 설치 fixture — deny·재점검 케이스 공통 전제."""
        repo = self.make_repo()
        self.install_gate(repo)
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a',
                                  *(('--scope', scope) if scope else ())).returncode, 0)
        return repo

    def run_prebash(self, repo, session, command, project_dir=None, env_extra=None,
                    tmpdir=None, cwd=None):
        """PreToolUse(Bash) 훅 subprocess — TMPDIR을 fixture 하위로 지정해 캐시 격리(§7)."""
        base = Path(tmpdir) if tmpdir else self.root / 'hooktmp'  # 메서드 내 호출 간 공유
        base.mkdir(parents=True, exist_ok=True)
        env = clean_env()
        env['CLAUDE_PROJECT_DIR'] = str(project_dir or repo)
        env['TMPDIR'] = str(base)
        env.update(env_extra or {})
        payload = json.dumps({'session_id': session, 'hook_event_name': 'PreToolUse',
                              'tool_input': {'command': command}})
        return subprocess.run([sys.executable, str(HOOK), 'prebash'], input=payload,
                              capture_output=True, text=True, env=env,
                              cwd=str(cwd or repo), timeout=30)

    def cache_path(self, session, tmpdir=None):
        sanitized = re.sub(r'[^A-Za-z0-9._-]', '_', session)[:64]
        base = Path(tmpdir) if tmpdir else self.root / 'hooktmp'
        return base / 'effort-router-tree-gate-hook' / f'{sanitized}.json'

    def read_cache(self, session, tmpdir=None):
        return json.loads(self.cache_path(session, tmpdir).read_text(encoding='utf-8'))

    def assert_silent(self, result, label=''):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '', label)

    def hook_output(self, repo, command, **kwargs):
        """prebash stdout JSON 파싱 — exit 0 단정 포함(출력 기대 케이스 공통)."""
        result = self.run_prebash(repo, 's-b', command, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)['hookSpecificOutput']

    # --- SessionStart 훅 (T19·T20 — r27) -----------------------------------------

    def test_t19_hook_warns_on_foreign_claim(self):
        # C14 — foreign claim 존재 시 경고 additionalContext emit ∧ 훅 exit 0
        self.require_hook()
        repo = self.make_repo()
        self.install_gate(repo)
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a',
                                  '--scope', 'r27 구현').returncode, 0)
        result = run_hook(repo, 's-b')
        self.assertEqual(result.returncode, 0, result.stderr)  # 세션 시작 차단 없음
        payload = json.loads(result.stdout)
        context = payload['hookSpecificOutput']['additionalContext']
        self.assertEqual(payload['hookSpecificOutput']['hookEventName'],
                         'SessionStart')
        self.assertIn('s-a', context)  # 상대 session_id
        self.assertIn('r27 구현', context)  # scope
        self.assertIn('ttl', context)  # alive 근거

    def test_t20_hook_silent_without_conflict_or_gate(self):
        # C14 — 간섭 없음·게이트 부재 모두 무작동·무경고·exit 0·출력 없음
        self.require_hook()
        repo = self.make_repo()
        self.install_gate(repo)
        result = run_hook(repo, 's-b')  # claim 없음 — 간섭 없음
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '')
        result = run_hook(repo, 's-b', project_dir='/nonexistent-tree-gate-path')
        self.assertEqual(result.returncode, 0, result.stderr)  # 게이트 부재 무작동
        self.assertEqual(result.stdout.strip(), '')

    # --- PreToolUse 훅 (T21~T31b — r28 격리 가드) --------------------------------

    def test_t21_prebash_deny_add_A(self):
        # C5 — foreign + git add -A → deny JSON ∧ pathspec·격리·유령 탈출 안내
        self.require_hook()
        output = self.hook_output(self.foreign_repo('r28 가드'), 'git add -A')
        self.assertEqual(output['hookEventName'], 'PreToolUse')
        self.assertEqual(output['permissionDecision'], 'deny')
        for phrase in ('s-a', 'pathspec', 'worktree_gate.py create --task',
                       '수동 삭제', 'prune은 alive 불가침'):
            self.assertIn(phrase, output['permissionDecisionReason'])

    def test_t22_prebash_deny_commit_am(self):
        # C5 — foreign + git commit -am "x" → deny(-am 묶음의 a 분해)
        self.require_hook()
        output = self.hook_output(self.foreign_repo(), 'git commit -am "x"')
        self.assertEqual(output['permissionDecision'], 'deny')

    def test_t23_prebash_deny_u_dot_dot_slash(self):
        # C5 — -u·`.`·`./` deny ∧ pathspec 병존·./src 부분은 허용
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git add -u', 'git add .', 'git add ./'):
            self.assertEqual(self.hook_output(repo, command)['permissionDecision'],
                             'deny', command)
        for command in ('git add -u src/', 'git add -A src/', 'git add ./src'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)

    def test_t24_prebash_partial_staging_silent(self):
        # C5 — 부분 스테이징(pathspec add)·커밋 -m은 무간섭(무출력·exit 0)
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git add src/main.py', 'git commit -m "x"'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)

    def test_t25_prebash_solo_allows_add_A(self):
        # C6 — 단독 세션(foreign_claims 빈)의 add -A 허용 — 오탐 0 원칙 실증
        self.require_hook()
        repo = self.make_repo()
        self.install_gate(repo)  # claim 없음
        self.assert_silent(self.run_prebash(repo, 's-b', 'git add -A'))

    def test_t26_prebash_readonly_nontrigger_no_cache(self):
        # C9 — read-only·비git은 레벨 1 미발화 — 무간섭 ∧ 캐시 파일 미생성
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git status', 'git log', 'ls -la'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)
        self.assertFalse(self.cache_path('s-b').exists())

    def test_t27_prebash_false_positive_blocked(self):
        # C9 — 명령 위치·인용 내부 제어 연산자·-C 귀속 불확실 오탐 봉쇄 — deny 없음
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('echo git add -A', 'echo "git add -A"',
                        'echo "x && git add -A"'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)
        for command in ('git -C ../x add -A', 'cat a && git add src/'):
            result = self.run_prebash(repo, 's-b', command)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = (json.loads(result.stdout)['hookSpecificOutput']
                      if result.stdout.strip() else {})  # 재점검 경고는 가능
            self.assertIsNone(output.get('permissionDecision'), command)

    def test_t28_prebash_cache_ttl(self):
        # C7 — 1회차 캐시 생성(foreign·sessions 기록·foreign=false도 생성)∧ TTL 내
        # epoch 불변 ∧ 만료 후 갱신
        self.require_hook()
        repo = self.foreign_repo()
        self.hook_output(repo, 'git add -A')  # 1회차 — 캐시 생성
        cache = self.read_cache('s-b')
        self.assertEqual(cache['version'], 1)
        self.assertEqual(cache['session_id'], 's-b')
        self.assertTrue(cache['foreign'])
        self.assertEqual(cache['foreign_sessions'], ['s-a'])
        first = cache['last_check_epoch']
        self.hook_output(repo, 'git add -A')  # TTL 내 — check 스킵
        self.assertEqual(self.read_cache('s-b')['last_check_epoch'], first)
        time.sleep(1.1)  # TTL=1 만료 유도 — env는 실행 시점 판정에 쓰인다
        self.hook_output(repo, 'git add -A',
                         env_extra={'TREE_GATE_HOOK_CACHE_TTL_S': '1'})
        self.assertGreater(self.read_cache('s-b')['last_check_epoch'], first)
        solo_repo = self.make_repo()  # foreign=false(단독) 1회차에도 캐시 생성
        self.install_gate(solo_repo)
        self.assert_silent(self.run_prebash(solo_repo, 's-z', 'git add -A'))
        solo = self.read_cache('s-z')
        self.assertFalse(solo['foreign'])
        self.assertEqual(solo['foreign_sessions'], [])

    def test_t29_prebash_new_intruder_warning_once(self):
        # C8 — 기준선(A) 후 C claim → 만료 후 재점검 경고(C 포함)∧ 재실행 무경고
        self.require_hook()
        repo = self.foreign_repo()
        ttl = {'TREE_GATE_HOOK_CACHE_TTL_S': '1'}
        self.assert_silent(self.run_prebash(repo, 's-b', 'git add src/main.py',
                                            env_extra=ttl))  # 첫 캐시 — 기록만
        # s-a 생존으로 s-c claim은 기록 수행 후 exit 1(T4 계약 — 기존 T10 전제 동일)
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-c',
                                  '--scope', 'r28 침입').returncode, 1)
        time.sleep(1.1)  # 캐시 만료 유도
        output = self.hook_output(repo, 'git add src/main.py', env_extra=ttl)
        self.assertIsNone(output.get('permissionDecision'))
        for phrase in ('진행 중 재점검', 's-c', 'r28 침입'):
            self.assertIn(phrase, output['additionalContext'])
        time.sleep(1.1)  # 재실행 — 신규 없음
        self.assert_silent(self.run_prebash(repo, 's-b', 'git add src/main.py',
                                            env_extra=ttl))

    def test_t29b_prebash_corrupt_only_no_deny_notified_once(self):
        # C8 — corrupt-only(foreign_claims 빈) deny 불발행 ∧ corrupt 통보 1회 → 무통보
        self.require_hook()
        repo = self.foreign_repo()
        self.claim_file(repo, 's-a').write_text('{not json', encoding='utf-8')
        ttl = {'TREE_GATE_HOOK_CACHE_TTL_S': '1'}
        output = self.hook_output(repo, 'git add -A', env_extra=ttl)
        self.assertIsNone(output.get('permissionDecision'))  # corrupt-only deny 불발행
        self.assertIn('파손 claim', output['additionalContext'])
        self.assertIn(self.claim_file(repo, 's-a').name, output['additionalContext'])
        self.assertFalse(self.read_cache('s-b')['foreign'])
        time.sleep(1.1)  # 재실행 — corrupt 기준선 합류
        self.assert_silent(self.run_prebash(repo, 's-b', 'git add -A', env_extra=ttl))

    def test_t30_prebash_fallback_and_off_switch(self):
        # C10 — 게이트 부재·비저장소 cwd·TREE_GATE_HOOKS=0(foreign 상태) — 전부 bypass
        self.require_hook()
        repo = self.foreign_repo()
        plain = self.root / 'plain-r28'
        plain.mkdir()
        for kwargs in ({'project_dir': '/nonexistent-tree-gate-path'}, {'cwd': plain},
                       {'env_extra': {'TREE_GATE_HOOKS': '0'}}):
            self.assert_silent(self.run_prebash(repo, 's-b', 'git add -A', **kwargs))

    def test_t31_start_extension_isolation_hint(self):
        # C11 — foreign 상태 무인자 start 경고에 격리 명령 원문(T19 문구 보존)
        self.require_hook()
        repo = self.foreign_repo('r28 격리')
        result = run_hook(repo, 's-b')
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        for phrase in ('s-a', 'r28 격리', 'ttl', 'worktree_gate.py create --task'):
            self.assertIn(phrase, context)

    def test_t31b_prebash_warning_merged_into_single_deny(self):
        # C11b — 신규 침입자 ∧ deny 동시 — stdout JSON 1개(deny 단독)∧ reason 병합∧
        # additionalContext emit 없음
        self.require_hook()
        repo = self.foreign_repo()
        ttl = {'TREE_GATE_HOOK_CACHE_TTL_S': '1'}
        self.assert_silent(self.run_prebash(repo, 's-b', 'git add src/main.py',
                                            env_extra=ttl))  # 기준선 기록
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-c',
                                  '--scope', 'r28 동시').returncode, 1)  # T4 계약
        time.sleep(1.1)
        result = self.run_prebash(repo, 's-b', 'git add -A', env_extra=ttl)
        self.assertEqual(result.returncode, 0, result.stderr)
        objects = [json.loads(line) for line in result.stdout.splitlines()
                   if line.strip()]
        self.assertEqual(len(objects), 1)  # deny 단독 — 2개 JSON 객체 금지
        output = objects[0]['hookSpecificOutput']
        self.assertEqual(output['permissionDecision'], 'deny')
        for phrase in ('s-c', 'r28 동시'):
            self.assertIn(phrase, output['permissionDecisionReason'])
        self.assertNotIn('additionalContext', objects[0])  # 별도 emit 없음

    # --- 갭 수선 (T32~T35 — ④리뷰 D1~D4) -----------------------------------------

    def test_t32_prebash_heredoc_body_no_interference(self):
        # D1 — 히어독 본문 git은 명령이 아니다(스크립트 작성 차단 금지)
        self.require_hook()
        repo = self.foreign_repo()
        command = "cat > s.sh <<'EOF'\ngit add -A\nEOF"
        self.assert_silent(self.run_prebash(repo, 's-b', command))

    def test_t33_prebash_combined_uncertain_option_no_deny(self):
        # D2 — 결합형 귀속 불확실(-C../x·--git-dir=../x) — 트리거는 유효·deny 제외
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git -C../other add -A', 'git --git-dir=../x add -A'):
            result = self.run_prebash(repo, 's-b', command)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = (json.loads(result.stdout)['hookSpecificOutput']
                      if result.stdout.strip() else {})
            self.assertIsNone(output.get('permissionDecision'), command)

    def test_t34_prebash_commit_value_char_not_flag(self):
        # D3 — -ma의 'a'는 -m 결합값(메시지) — -a 플래그로 오인 deny 금지
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git commit -ma', 'git commit -ma "msg"'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)

    def test_t35_prebash_dry_run_no_deny(self):
        # D4 — 실행 안 되는 명령(--dry-run·add -n)은 deny 제외
        self.require_hook()
        repo = self.foreign_repo()
        for command in ('git add --dry-run -A', 'git add -n -A',
                        'git add --dry-run .'):
            self.assert_silent(self.run_prebash(repo, 's-b', command), command)


if __name__ == '__main__':
    unittest.main()
