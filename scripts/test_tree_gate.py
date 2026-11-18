#!/usr/bin/env python3
"""r27 트리 소유 게이트 단위테스트 — 임시 git 저장소 fixture로 분기 전수(T1~T18+T8b).

테스트는 subprocess로 CLI를 실행한다(test_worktree_gate 관습) — import 방식이면
수집 단계 ImportError로 RED가 성립하지 않는다. RED 단계(tree_gate.py 부재)에서는
해당 테스트가 실패한다. r28에서 훅 케이스(T19·T20·T21~T31b)는
scripts/test_tree_claim_hook.py로 분할 이전했다(r25 worktree_gate/hardening
2파일 선례 준용 — 본 파일은 게이트 본체 분기만 담당).
claims 대응(r27): T1=C5, T3=C6, T5=C7·C8, T6=C7, T7·T10=C9, T13=C10, T11=C11,
T15=§4.3 64자 패턴, 나머지는 분기 전수 결정론 검증.
fixture 계약: test_worktree_gate 준용 — /tmp ext4 기본(tmp.mkdtemp, DrvFs chmod
유도 금지 r25 H1)·clean_env 전역 config 격리·setUp 저장소 내부 가드.
TREE_GATE_TEST_ROOT env로 fixture 루트 지정 가능(r25 M-g 관례).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/tree_gate.py'

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
    """게이트 subprocess 호출 — env_extra는 clean_env 위에 합성(T18 폴백 판정용)."""
    env = clean_env()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(GATE), *args],
                          cwd=str(cwd), capture_output=True, text=True, env=env)


class TreeGateTests(unittest.TestCase):
    """T1~T20+T8b — claims 대응표(번들 §7) 그대로."""

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

    def read_claim(self, repo, session):
        return json.loads(self.claim_file(repo, session).read_text(encoding='utf-8'))

    def backdate(self, repo, session, hours):
        """updated_utc를 과거로 되돌린다(TTL 초과 유도 — §4.2 판정 기준 필드만 조작)."""
        record = self.read_claim(repo, session)
        old = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        self.claim_file(repo, session).write_text(
            json.dumps({**record, 'updated_utc': old}), encoding='utf-8')

    def set_hostname(self, repo, session, hostname):
        record = self.read_claim(repo, session)
        self.claim_file(repo, session).write_text(
            json.dumps({**record, 'hostname': hostname}), encoding='utf-8')

    # --- claim (T1·T2·T4·T18) -------------------------------------------------

    def test_t1_claim_basics(self):
        # C5 — claim → exit 0 ∧ 파일 생성 ∧ 레코드 필드 정합 ∧ flags []
        repo = self.make_repo()
        result = run_gate(repo, 'claim', '--session', 's-a',
                          '--scope', 'r27 구현 스코프')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], [])
        self.assertEqual(output['subcommand'], 'claim')
        record = self.read_claim(repo, 's-a')
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['gate'], 'tree-gate')
        self.assertEqual(record['session_id'], 's-a')
        self.assertEqual(record['tree'], str(Path(repo).resolve()))
        self.assertEqual(len(record['tree_hash']), 16)
        self.assertEqual(record['scope'], 'r27 구현 스코프')
        self.assertEqual(record['hostname'], os.uname().nodename)
        self.assertIsNone(record['pid'])
        self.assertEqual(record['claimed_utc'], record['updated_utc'])

    def test_t2_reclaim_heartbeat_idempotent(self):
        # 재claim — updated_utc만 갱신 멱등 ∧ claimed_utc 최초 고정 ∧ 파일 1건 유지
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        first = self.read_claim(repo, 's-a')
        import time
        time.sleep(0.05)
        again = run_gate(repo, 'claim', '--session', 's-a')
        self.assertEqual(again.returncode, 0, again.stderr)
        second = self.read_claim(repo, 's-a')
        self.assertEqual(second['claimed_utc'], first['claimed_utc'])
        self.assertGreater(second['updated_utc'], first['updated_utc'])
        self.assertEqual(len(list(self.registry(repo).glob('*.json'))), 1)

    def test_t4_claim_with_foreign_alive_claim(self):
        # 타 alive claim 존재 시 claim — 기록은 수행 ∧ exit 1 ∧ 플래그
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        result = run_gate(repo, 'claim', '--session', 's-b')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('foreign_claim_present', output['flags'])
        self.assertTrue(self.claim_file(repo, 's-b').exists())
        self.assertEqual(output['foreign_claims'][0]['session_id'], 's-a')

    def test_t18_session_env_fallback(self):
        # CLAUDE_SESSION_ID env 폴백 — 인자 생략 시 자동 채움 ∧ 인자가 env에 우선
        repo = self.make_repo()
        result = run_gate(repo, 'claim', env_extra={'CLAUDE_SESSION_ID': 'env-sess'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_claim(repo, 'env-sess')['session_id'], 'env-sess')
        result = run_gate(repo, 'claim', '--session', 'explicit-s',
                          env_extra={'CLAUDE_SESSION_ID': 'env-sess'})
        # env-sess claim이 살아있어 foreign 플래그와 함께 exit 1 — 인자 우선은 기록으로 확인
        self.assertEqual(result.returncode, 1)
        self.assertIn('foreign_claim_present', json.loads(result.stdout)['flags'])
        self.assertEqual(self.read_claim(repo, 'explicit-s')['session_id'],
                         'explicit-s')

    # --- check (T3·T7·T8·T8b·T9·T16) -----------------------------------------

    def test_t3_check_foreign_alive_claim(self):
        # C6 — 타 alive claim 존재 시 check → exit 1 ∧ 플래그 ∧ 상대 정보 보고
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a',
                                  '--scope', 'r27 work').returncode, 0)
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['flags'], ['foreign_claim_present'])
        entry = output['foreign_claims'][0]
        self.assertEqual(entry['session_id'], 's-a')
        self.assertEqual(entry['scope'], 'r27 work')
        self.assertTrue(entry['claimed_utc'])
        self.assertEqual(entry['alive_reason'], 'ttl')
        self.assertEqual(entry['pid_check'], 'unsupported')  # pid 미전달
        # --session 미지정(전수 탐색)도 동일
        result = run_gate(repo, 'check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('foreign_claim_present', json.loads(result.stdout)['flags'])

    def test_t7_stale_ttl_ignored_by_check_flagged_by_status(self):
        # C9 — TTL 초과 claim은 check 무시(exit 0) ∧ status 플래그(exit 1)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        self.assertEqual(run_gate(repo, 'check', '--session', 's-b').returncode, 1)
        self.backdate(repo, 's-a', hours=48)
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['foreign_claims'], [])
        result = run_gate(repo, 'status')
        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertIn('stale_claims_present', output['flags'])
        self.assertEqual(output['stale_claims'][0]['session_id'], 's-a')
        self.assertEqual(output['claims'][0]['state'], 'stale')

    def test_t8_pid_liveness_dead_and_alive(self):
        # 죽은 pid(spawn→terminate→wait 회수 완료 확인)는 stale·생존 pid는 alive
        repo = self.make_repo()
        proc = subprocess.Popen(['sleep', '30'])
        proc.terminate()
        proc.wait()
        with self.assertRaises(ProcessLookupError):  # 회수 완료 전제 — 재사용 오염 차단
            os.kill(proc.pid, 0)
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-dead',
                                  '--pid', str(proc.pid)).returncode, 0)
        self.backdate(repo, 's-dead', hours=48)
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 0, result.stderr)  # 사망 확인 → stale 무시
        repo2 = self.make_repo()
        self.assertEqual(run_gate(repo2, 'claim', '--session', 's-live',
                                  '--pid', str(os.getpid())).returncode, 0)
        self.backdate(repo2, 's-live', hours=48)
        result = run_gate(repo2, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1, result.stderr)  # pid 생존 → alive
        entry = json.loads(result.stdout)['foreign_claims'][0]
        self.assertEqual(entry['alive_reason'], 'pid')
        self.assertEqual(entry['pid_check'], 'alive')

    def test_t8b_foreign_owned_pid_is_alive(self):
        # PermissionError=생존 분기 — 타 사용자 소유 pid(root 소유 pid 1)로 생존 판정
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-root',
                                  '--pid', '1').returncode, 0)
        self.backdate(repo, 's-root', hours=48)  # TTL 초과 — 생존 근거는 pid뿐
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1, result.stderr)
        entry = json.loads(result.stdout)['foreign_claims'][0]
        self.assertEqual(entry['pid_check'], 'alive')
        self.assertEqual(entry['alive_reason'], 'pid')

    def test_t9_foreign_hostname_pid_unsupported(self):
        # 호스트 상이 — pid 판정 스킵 표기 ∧ TTL 의존 보수 alive
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-remote',
                                  '--pid', str(os.getpid())).returncode, 0)
        self.set_hostname(repo, 's-remote', 'other-machine')
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1, result.stderr)
        entry = json.loads(result.stdout)['foreign_claims'][0]
        self.assertEqual(entry['pid_check'], 'unsupported')
        self.assertEqual(entry['alive_reason'], 'ttl')

    def test_t16_corrupt_claim_reported_not_paralyzing(self):
        # 파손 claim — status corrupt 보고·마비 없음 ∧ check 보수 alive 취급
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        self.claim_file(repo, 's-a').write_text('{not json', encoding='utf-8')
        result = run_gate(repo, 'status')
        self.assertEqual(result.returncode, 0, result.stderr)  # corrupt는 stale 아님
        output = json.loads(result.stdout)
        self.assertEqual(len(output['corrupt']), 1)
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1)  # 판독 불가 = 판단 보류 → 보수 alive
        output = json.loads(result.stdout)
        self.assertIn('foreign_claim_present', output['flags'])
        self.assertEqual(len(output['corrupt']), 1)

    # --- release (T5·T6) -------------------------------------------------------

    def test_t5_release_and_idempotent_and_refusal(self):
        # C7·C8 — release 파일 제거·exit 0 ∧ 재release 멱등 already_released ∧
        # 레코드 session_id 불일치 제거 거부 exit 2(파일명 충돌 방어)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        result = run_gate(repo, 'release', '--session', 's-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['already_released'])
        self.assertEqual(self.claim_files(repo, 's-a'), [])
        result = run_gate(repo, 'release', '--session', 's-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['already_released'])
        # 방어 계층 — s-b 경로의 레코드에 타 session_id를 기록한 조작 파일
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-b').returncode, 0)
        tampered = self.claim_file(repo, 's-b')
        tampered.write_text(json.dumps({'session_id': 's-a'}), encoding='utf-8')
        result = run_gate(repo, 'release', '--session', 's-b')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL tree gate', result.stderr)
        self.assertTrue(tampered.exists())

    def test_t6_check_after_release_clean(self):
        # C7 — release 후 check → exit 0(간섭 없음)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        self.assertEqual(run_gate(repo, 'release', '--session', 's-a').returncode, 0)
        result = run_gate(repo, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['flags'], [])

    # --- prune (T10) ------------------------------------------------------------

    def test_t10_prune_stale_only(self):
        # C9 — prune --dry-run 무변경 ∧ prune은 stale만 제거(alive pid claim 보존)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-stale').returncode, 0)
        # s-stale이 살아있어 두 번째 claim은 exit 1(기록은 수행 — T4 계약)
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-alive',
                                  '--pid', str(os.getpid())).returncode, 1)
        self.backdate(repo, 's-stale', hours=48)
        self.backdate(repo, 's-alive', hours=48)  # TTL 초과여도 pid 생존 = alive
        result = run_gate(repo, 'prune', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output['dry_run'])
        self.assertEqual(output['removed'], 0)
        self.assertEqual([c['session_id'] for c in output['stale_claims']], ['s-stale'])
        self.assertTrue(self.claim_file(repo, 's-stale').exists())
        result = run_gate(repo, 'prune')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['removed'], 1)
        self.assertEqual(self.claim_files(repo, 's-stale'), [])
        self.assertTrue(self.claim_file(repo, 's-alive').exists())  # alive 불가침

    # --- 폴백·환경 (T11·T12·T15·T17) -------------------------------------------

    def test_t11_non_git_directory_all_subcommands(self):
        # C11 — 비 git 디렉터리에서 5 서브커맨드 전부 → exit 2 ∧ stderr FAIL 접두
        plain = self.root / 'plain'
        plain.mkdir()
        cases = (
            run_gate(plain, 'claim', '--session', 'x'),
            run_gate(plain, 'release', '--session', 'x'),
            run_gate(plain, 'check'),
            run_gate(plain, 'status'),
            run_gate(plain, 'prune'),
        )
        for index, result in enumerate(cases):
            self.assertEqual(result.returncode, 2, f'subcommand #{index}')
            self.assertIn('FAIL tree gate', result.stderr, f'subcommand #{index}')
            self.assertEqual(result.stdout, '', f'subcommand #{index}')

    def test_t12_registry_write_protected_fail_closed(self):
        # common-dir 쓰기 불가 → exit 2 fail-closed(chmod 0500 — ext4 /tmp 전제, r25 H1)
        repo = self.make_repo()
        self.assertEqual(run_gate(repo, 'claim', '--session', 's-a').returncode, 0)
        reg = self.registry(repo)
        reg.chmod(0o500)
        self.addCleanup(reg.chmod, 0o700)
        result = run_gate(repo, 'claim', '--session', 's-b')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL tree gate', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_t15_invalid_inputs_exit2(self):
        # 무효 session-id(65자·허용 외 문자·빈 문자열)·무효 pid → exit 2
        repo = self.make_repo()
        for bad in ('a' * 65, 'bad id', 'bad@id!', ''):
            result = run_gate(repo, 'claim', '--session', bad)
            self.assertEqual(result.returncode, 2, repr(bad))
            self.assertIn('FAIL tree gate', result.stderr, repr(bad))
        result = run_gate(repo, 'claim', '--session', 'ok', '--pid', '0')
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL tree gate', result.stderr)

    def test_t17_bare_repository_exit2(self):
        # bare 저장소 — 작업 트리 부재 → exit 2
        bare = self.root / 'bare.git'
        self.assertEqual(git(self.root, 'init', '--bare',
                             str(bare)).returncode, 0)
        for args in (('claim', '--session', 's-a'), ('check',)):
            result = run_gate(bare, *args)
            self.assertEqual(result.returncode, 2, args)
            self.assertIn('FAIL tree gate', result.stderr, args)

    # --- 가시성·감사 (T13·T14) ---------------------------------------------------

    def test_t13_worktree_common_dir_visibility(self):
        # C10 — common-dir 공유 가시성: worktree 내부에서 claim한 기록을 다른 cwd의
        # check도 동일 레지스트리에서 탐색한다(트리가 같으면)
        repo = self.make_repo()
        wt = self.root / f'wt-{uuid.uuid4().hex[:8]}'
        self.assertEqual(git(repo, 'worktree', 'add', str(wt),
                             '-b', 'wt-x').returncode, 0)
        self.assertEqual(run_gate(wt, 'claim', '--session', 's-wt').returncode, 0)
        self.assertTrue(self.claim_file(repo, 's-wt').exists())  # 본체 .git에 기록
        result = run_gate(wt, 'check', '--session', 's-b')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('foreign_claim_present', json.loads(result.stdout)['flags'])
        result = run_gate(repo, 'check', '--session', 's-b', '--tree', str(wt))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['foreign_claims'][0]['session_id'],
                         's-wt')

    def test_t14_save_audit_and_save_failure(self):
        # --save 감사 JSON 기록 ∧ 저장 실패 시 stdout 보존 후 exit 2(r23/r24 예외)
        repo = self.make_repo()
        audit = self.root / 'audit'
        result = run_gate(repo, 'claim', '--session', 's-a', '--save', str(audit))
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)['saved_to']
        self.assertTrue(saved and Path(saved).is_file())
        self.assertEqual(len(list(audit.glob('tree-gate-*.json'))), 1)
        blocker = self.root / 'blocker.txt'
        blocker.write_text('not a directory\n', encoding='utf-8')
        result = run_gate(repo, 'status', '--save', str(blocker))
        self.assertEqual(result.returncode, 2)
        self.assertIn('FAIL tree gate', result.stderr)
        output = json.loads(result.stdout)  # 검사 결과 stdout 보존
        self.assertIsNone(output['saved_to'])


# r60 문서(GATES.md '경로 claim') 수록 pre-commit 스니펫과 같은 본문 — 게이트 경로만 치환.
PRE_COMMIT_SNIPPET = '''#!/bin/sh
# effort-router r60 경로 claim 대조 — exit 1(범위 밖·타 claim)만 커밋 차단, 2(게이트 오류)는 통과
python3 "{gate}" path-check --staged 1>&2
[ $? -eq 1 ] && {{ echo "pre-commit: 경로 claim 위반 — 위 JSON의 out_of_scope·conflicts 확인" >&2; exit 1; }}
exit 0
'''


class PathClaimTests(TreeGateTests):
    """r60 경로 claim T21~T31 — 기존 fixture 재사용(상속 테스트 중복 실행 방지는 아래 삭제)."""

    def path_registry(self, repo):
        return Path(repo) / '.git' / 'effort-router-path-claims'

    def path_records(self, repo):
        return {p.name: json.loads(p.read_text(encoding='utf-8'))
                for p in self.path_registry(repo).glob('*.json')}

    def add_worktree(self, repo, name):
        path = self.root / name
        result = git(repo, 'worktree', 'add', '-q', str(path), '-b', name)
        self.assertEqual(result.returncode, 0, result.stderr)
        return path

    def pclaim(self, cwd, owner, *paths, extra=()):
        result = run_gate(cwd, 'path-claim', '--owner', owner, '--paths', *paths, *extra)
        output = json.loads(result.stdout) if result.stdout.strip() else None
        return result, output

    def test_t21_path_claim_basics(self):
        repo = self.make_repo()
        result, out = self.pclaim(repo, 't-a', './src/', 'docs', 'src', extra=('--scope', 'r60'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out['granted'])
        self.assertEqual(out['paths'], ['src', 'docs'])  # 정규화·중복 제거
        (record,) = self.path_records(repo).values()
        self.assertEqual((record['kind'], record['owner'], record['scope']),
                         ('path-claim', 't-a', 'r60'))
        # 절대경로(트리 내부)는 루트 기준 상대경로로 저장된다
        result, out = self.pclaim(repo, 't-a', str(Path(repo) / 'README2.md'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out['added'], ['README2.md'])

    def test_t22_cross_worktree_overlap_denied_all_or_nothing(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, 'wt-b')
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        for paths in (['SRC/main.py'], ['.'], ['src/deep/x.py']):
            result, out = self.pclaim(wt, 't-b', *paths)
            self.assertEqual(result.returncode, 1, paths)
            self.assertEqual(out['flags'], ['path_claim_denied'])
            self.assertFalse(out['granted'])
        # 충돌 1건 + 무관 1건 → 아무것도 기록되지 않는다
        result, out = self.pclaim(wt, 't-b', 'docs', 'src/main.py')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.path_records(repo)), 1)
        # 하위 먼저 보유 → 상위 요청도 거부(양방향)
        self.assertEqual(self.pclaim(wt, 't-b', 'docs/readme.md')[0].returncode, 0)
        self.assertEqual(self.pclaim(repo, 't-c', 'docs')[0].returncode, 1)
        # 접두 문자열만 같은 형제 경로는 겹침 아님
        self.assertEqual(self.pclaim(repo, 't-c', 'src2')[0].returncode, 0)

    def test_t23_incremental_add_checks_only_added(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, 'wt-b')
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        self.assertEqual(self.pclaim(wt, 't-b', 'docs')[0].returncode, 0)
        result, out = self.pclaim(repo, 't-a', 'src', 'docs/readme.md')
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c['requested'] for c in out['conflicts']], ['docs/readme.md'])
        self.assertEqual(out['paths'], ['src'])  # 기존 배정 유지
        result, out = self.pclaim(repo, 't-a', 'scripts')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(out['paths'], ['src', 'scripts'])

    def test_t24_stale_does_not_block_and_prune(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, 'wt-b')
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        (name, record) = next(iter(self.path_records(repo).items()))
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        (self.path_registry(repo) / name).write_text(
            json.dumps({**record, 'updated_utc': old}), encoding='utf-8')
        result = run_gate(repo, 'path-status')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['flags'], ['stale_claims_present'])
        result, out = self.pclaim(wt, 't-b', 'src/main.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out['stale_overlaps'][0]['owner'], 't-a')
        result = run_gate(repo, 'path-status', '--prune')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['removed'], 1)
        owners = {r['owner'] for r in self.path_records(repo).values()}
        self.assertEqual(owners, {'t-b'})  # alive 불가침

    def test_t25_staged_out_of_scope_conflict_and_rename(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, 'wt-b')
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        self.assertEqual(self.pclaim(wt, 't-b', 'docs')[0].returncode, 0)
        write_file(wt, 'src/main.py', 'changed\n')
        self.assertEqual(git(wt, 'add', 'src/main.py').returncode, 0)
        result = run_gate(wt, 'path-check', '--staged')
        self.assertEqual(result.returncode, 1)
        out = json.loads(result.stdout)
        self.assertEqual(out['flags'], ['out_of_scope_paths', 'foreign_path_conflict'])
        self.assertEqual(out['out_of_scope'], ['src/main.py'])
        self.assertEqual(git(wt, 'reset', '-q').returncode, 0)
        # 범위 밖으로의 이동 — 새 경로가 잡힌다
        self.assertEqual(git(wt, 'checkout', '--', 'src/main.py').returncode, 0)
        self.assertEqual(git(wt, 'mv', 'docs/readme.md', 'notes.md').returncode, 0)
        out = json.loads(run_gate(wt, 'path-check', '--staged').stdout)
        self.assertIn('docs/readme.md', out['targets'])
        self.assertEqual(out['out_of_scope'], ['notes.md'])
        # 범위 안 이동은 통과
        self.assertEqual(git(wt, 'mv', 'notes.md', 'docs/notes.md').returncode, 0)
        result = run_gate(wt, 'path-check', '--staged')
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_t26_solo_without_path_claims_passes(self):
        repo = self.make_repo()
        write_file(repo, 'src/main.py', 'changed\n')
        self.assertEqual(git(repo, 'add', '-A').returncode, 0)
        result = run_gate(repo, 'path-check', '--staged')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['flags'], [])
        self.assertFalse(self.path_registry(repo).exists())  # 읽기 전용 — 레지스트리 미생성

    def test_t27_invalid_paths_and_owner_exit2(self):
        repo = self.make_repo()
        for bad in ('../x', 'src/*', '.git/config', '   ', str(self.root / 'outside')):
            result, _ = self.pclaim(repo, 't-a', bad)
            self.assertEqual(result.returncode, 2, bad)
            self.assertIn('FAIL tree gate', result.stderr)
            self.assertEqual(result.stdout, '')
        result = run_gate(repo, 'path-claim', '--paths', 'src')  # owner·env 부재
        self.assertEqual(result.returncode, 2)
        result = run_gate(repo, 'path-claim', '--paths', 'src', env_extra={'CLAUDE_SESSION_ID': 'env-s'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['owner'], 'env-s')
        self.assertEqual(run_gate(repo, 'path-check').returncode, 2)  # --staged|--paths 필수

    def test_t28_release_partial_full_idempotent_refusal(self):
        repo = self.make_repo()
        self.assertEqual(self.pclaim(repo, 't-a', 'src', 'docs')[0].returncode, 0)
        result = run_gate(repo, 'path-release', '--owner', 't-a', '--paths', 'DOCS')
        self.assertEqual(json.loads(result.stdout)['paths'], ['src'])
        result = run_gate(repo, 'path-release', '--owner', 't-a')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.path_records(repo), {})
        result = run_gate(repo, 'path-release', '--owner', 't-a')
        self.assertTrue(json.loads(result.stdout)['already_released'])
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        (name, record) = next(iter(self.path_records(repo).items()))
        (self.path_registry(repo) / name).write_text(
            json.dumps({**record, 'owner': 'someone-else'}), encoding='utf-8')
        result = run_gate(repo, 'path-release', '--owner', 't-a')
        self.assertEqual(result.returncode, 2)
        self.assertTrue((self.path_registry(repo) / name).exists())

    def test_t29_concurrent_claims_single_grant(self):
        repo = self.make_repo()
        procs = [subprocess.Popen(
            [sys.executable, str(GATE), 'path-claim', '--owner', f'c{i}', '--paths', 'src'],
            cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=clean_env()) for i in range(8)]
        codes = sorted(p.wait(timeout=60) for p in procs)
        for proc in procs:
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(codes, [0] + [1] * 7)
        self.assertEqual(len(self.path_records(repo)), 1)

    def test_t30_pre_commit_snippet_blocks_out_of_scope(self):
        repo = self.make_repo()
        hook = Path(repo) / '.git' / 'hooks' / 'pre-commit'
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(PRE_COMMIT_SNIPPET.format(gate=GATE), encoding='utf-8')
        hook.chmod(0o755)
        self.assertEqual(self.pclaim(repo, 't-a', 'src')[0].returncode, 0)
        write_file(repo, 'src/main.py', 'in scope\n')
        self.assertEqual(git(repo, 'commit', '-qam', 'in').returncode, 0)
        write_file(repo, 'docs/readme.md', 'out of scope\n')
        result = git(repo, 'commit', '-qam', 'out')  # -a 임시 index도 대조
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('out_of_scope_paths', result.stderr)
        # 게이트 오류(exit 2)는 커밋을 막지 않는다 — 부재 게이트 경로로 재현
        hook.write_text(PRE_COMMIT_SNIPPET.format(gate=self.root / 'missing.py'),
                        encoding='utf-8')
        self.assertEqual(git(repo, 'commit', '-qam', 'bypass').returncode, 0)

    def test_t31_corrupt_records(self):
        repo = self.make_repo()
        reg = self.path_registry(repo)
        reg.mkdir(parents=True)
        (reg / 'garbage.json').write_text('{not json', encoding='utf-8')
        result, out = self.pclaim(repo, 't-a', 'src')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(out['granted'])
        self.assertEqual(out['flags'], ['path_registry_corrupt'])
        # path-check는 파손을 보고만 한다 — 무관한 파손 파일이 커밋을 막지 않는다
        result = run_gate(repo, 'path-check', '--paths', 'src/main.py')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['corrupt'], ['garbage.json'])
        (name,) = [n for n in self.path_records_safe(repo) if n != 'garbage.json']
        (reg / name).write_text(json.dumps({'owner': 't-a', 'paths': 'src'}), encoding='utf-8')
        result, _ = self.pclaim(repo, 't-a', 'docs')
        self.assertEqual(result.returncode, 2)  # 자기 레코드 파손 = 판단 보류

    def test_t32_tree_spelling_variants_are_same_tree(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, 'wt-b')
        # 메인이 표기가 다른 --tree(하위 디렉터리·..)로 위임 전 배정
        result, out = self.pclaim(repo, 't-b', 'docs', extra=('--tree', str(wt / 'src' / '..' / 'docs')))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out['tree'], str(wt.resolve()))
        write_file(wt, 'docs/readme.md', 'changed\n')
        self.assertEqual(git(wt, 'add', 'docs/readme.md').returncode, 0)
        result = run_gate(wt, 'path-check', '--staged')  # 자기 claim을 타 claim으로 오인하지 않는다
        self.assertEqual(result.returncode, 0, result.stdout)
        result = run_gate(repo, 'path-release', '--owner', 't-b', '--tree', str(wt))
        self.assertFalse(json.loads(result.stdout)['already_released'])
        self.assertEqual(self.path_records(repo), {})
        # 다른 저장소·비저장소 트리는 거부
        other = self.make_repo()
        for bad in (str(other), str(self.root)):
            result, _ = self.pclaim(repo, 't-x', 'src', extra=('--tree', bad))
            self.assertEqual(result.returncode, 2, bad)

    def path_records_safe(self, repo):
        return [p.name for p in self.path_registry(repo).glob('*.json')]


# 상속한 T1~T20을 PathClaimTests에서 재실행하지 않는다(fixture만 재사용).
for _name in [n for n in vars(TreeGateTests) if n.startswith('test_')]:
    setattr(PathClaimTests, _name, None)


if __name__ == '__main__':
    unittest.main()
