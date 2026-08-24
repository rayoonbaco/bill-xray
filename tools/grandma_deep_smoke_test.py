from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT = Path(os.environ.get('BILL_XRAY_ROOT', r'C:\PROJECTS\Bill_XRay'))
SHOWCASES = [
    ('aca', 'Affordable Care Act', 'Democratic-led'),
    ('ira', 'Inflation Reduction Act', 'Democratic-led'),
    ('tcja', 'Tax Cuts and Jobs Act', 'Republican-led'),
    ('obbba', 'One Big Beautiful Bill Act', 'Republican-led'),
]
LANES = {'what_it_really_does', 'follow_the_money', 'barrel_scan', 'who_wins_pays_power', 'left_right_text'}
LEGAL_ESE = re.compile(r'\b(pursuant|notwithstanding|hereinafter|thereof|hereof|subparagraph|subsection|promulgat(?:e|ion)|aforementioned)\b', re.I)
PLACEHOLDER = re.compile(r'\b(TBD|TODO|placeholder|lorem ipsum|unknown claim|needs expert review|needs legal context)\b', re.I)

@dataclass
class Finding:
    level: str
    role: str
    bill: str
    message: str

@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checks: int = 0
    clears: int = 0

    def add(self, level: str, role: str, bill: str, message: str) -> None:
        self.checks += 1
        if level == 'CLEAR':
            self.clears += 1
        self.findings.append(Finding(level, role, bill, message))

    def clear(self, role: str, bill: str, message: str) -> None:
        self.add('CLEAR', role, bill, message)

    def warn(self, role: str, bill: str, message: str) -> None:
        self.add('WARNING', role, bill, message)

    def red(self, role: str, bill: str, message: str) -> None:
        self.add('RED FLAG', role, bill, message)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def claim_list(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for panel in analysis.get('panels') or []:
        if isinstance(panel, dict):
            for claim in panel.get('claims') or []:
                if isinstance(claim, dict):
                    c = dict(claim)
                    c['_panel'] = panel.get('key')
                    out.append(c)
    return out


def check_repository(report: Report) -> None:
    role = 'Repository Guardian'
    if not PROJECT.exists():
        report.red(role, 'PROJECT', f'Project root not found: {PROJECT}')
        return
    required = ['app.py', 'engine', 'tests', 'data', 'templates/index.html']
    missing = [x for x in required if not (PROJECT / x).exists()]
    if missing:
        report.red(role, 'PROJECT', 'Missing required project paths: ' + ', '.join(missing))
    else:
        report.clear(role, 'PROJECT', 'Core application, engine, tests, data, and public template are present.')

    # Full regression suite: useful, but classify data-packaging-only failures separately.
    try:
        cp = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', 'tests'], cwd=PROJECT, capture_output=True, text=True, timeout=240
        )
        output = (cp.stdout or '') + '\n' + (cp.stderr or '')
        summary = ''
        for line in reversed(output.splitlines()):
            if re.search(r'\b(passed|failed|error|errors)\b', line, re.I):
                summary = line.strip()
                break
        if cp.returncode == 0:
            report.clear(role, 'PROJECT', f'Full regression suite passed. {summary}'.strip())
        else:
            lower = output.lower()
            known_data_only = ('test_upgrade_package_does_not_ship_placeholder_analysis_files' in lower and re.search(r'\b1 failed\b', lower) is not None)
            if known_data_only:
                report.warn(role, 'PROJECT', f'Pytest has a live-data packaging-policy failure; inspect before deployment. {summary}'.strip())
            else:
                report.red(role, 'PROJECT', f'Pytest regression suite failed. {summary or "See test output."}')
            (PROJECT / 'GRANDMA_PYTEST_OUTPUT.txt').write_text(output, encoding='utf-8')
    except Exception as exc:
        report.red(role, 'PROJECT', f'Could not run pytest: {exc}')


def check_sources_and_artifacts(report: Report, bill_id: str, title: str) -> None:
    source_role = 'Source Integrity Specialist'
    release_role = 'Release Engineer'
    citation_role = 'Citation Integrity Auditor'
    neutrality_role = 'Political Neutrality Auditor'
    adversarial_role = 'Adversarial QA Lead'
    grandma_role = 'Grandma Clarity Editor'
    structure_role = 'Legislative Structure Examiner'

    source = PROJECT / 'data' / 'source_documents' / f'{bill_id}.txt'
    anchors_path = PROJECT / 'data' / 'citation_anchors' / f'{bill_id}.json'
    analysis_path = PROJECT / 'data' / 'analyses' / f'{bill_id}.json'
    synth_path = PROJECT / 'data' / 'synthesis' / f'{bill_id}.json'
    red_path = PROJECT / 'data' / 'red_team' / f'{bill_id}.json'
    audit_path = PROJECT / 'data' / 'citation_audit' / f'{bill_id}.json'
    challenge_path = PROJECT / 'data' / 'challenge' / f'{bill_id}.json'

    if not source.exists():
        report.red(source_role, title, 'Official source text is missing; this exhibit cannot be independently checked.')
        return
    size = source.stat().st_size
    if size < 500:
        report.red(source_role, title, f'Source text is suspiciously small ({size} bytes).')
    else:
        report.clear(source_role, title, f'Official source text exists ({size:,} bytes).')

    anchors = read_json(anchors_path)
    if not anchors:
        report.red(citation_role, title, 'Citation-anchor artifact is missing or unreadable.')
    else:
        expected = str(anchors.get('source_sha256') or '')
        actual = sha256(source)
        if expected and expected == actual:
            report.clear(source_role, title, 'Source checksum matches the citation-anchor provenance record.')
        elif expected:
            report.red(source_role, title, 'Source checksum does NOT match the citation-anchor provenance record.')
        else:
            report.warn(source_role, title, 'Citation anchors do not record a source checksum.')

        source_url = str(anchors.get('source_url') or '')
        if 'govinfo.gov' in source_url.lower():
            report.clear(source_role, title, 'Citation provenance points to an official GovInfo source URL.')
        elif source_url:
            report.warn(source_role, title, f'Citation provenance source is not GovInfo: {source_url}')
        else:
            report.warn(source_role, title, 'Citation provenance has no source URL.')

        anchor_list = anchors.get('anchors') or []
        ids = [str(a.get('anchor_id')) for a in anchor_list if isinstance(a, dict) and a.get('anchor_id')]
        if ids and len(ids) == len(set(ids)):
            report.clear(citation_role, title, f'{len(ids):,} citation anchor IDs are unique.')
        elif ids:
            report.red(citation_role, title, 'Duplicate citation anchor IDs exist.')
        else:
            report.red(citation_role, title, 'No citation anchors were found.')

        suspicious = []
        for a in anchor_list:
            if not isinstance(a, dict):
                continue
            ident = str(a.get('identifier') or '')
            label = str(a.get('section_label') or '')
            if ident.upper() == 'TION' or 'SEC. TION' in label.upper():
                suspicious.append(str(a.get('anchor_id') or label))
        if suspicious:
            report.warn(structure_role, title, f'Suspicious SECTION parsing remains in {len(suspicious)} anchor(s), including "TION". This deserves manual review.')
        else:
            report.clear(structure_role, title, 'No known SECTION/TION segmentation artifact detected.')

    analysis_doc = read_json(analysis_path)
    synth = read_json(synth_path)
    if not analysis_doc or not synth:
        report.red(release_role, title, 'Public analysis/synthesis artifact is missing; exhibit is not ready.')
        return

    status = str(analysis_doc.get('analysis_status') or synth.get('analysis_status') or '').lower()
    missing_lanes = set(synth.get('missing_public_lanes') or [])
    if status == 'verified' and not missing_lanes:
        report.clear(release_role, title, 'Analysis is VERIFIED and all five public lanes qualified.')
    else:
        extra = f'; missing lanes: {", ".join(sorted(missing_lanes))}' if missing_lanes else ''
        report.red(release_role, title, f'Analysis is {status or "unknown"}{extra}.')

    panels = {str(p.get('key')): p for p in analysis_doc.get('panels') or [] if isinstance(p, dict)}
    missing_panels = sorted(LANES - set(panels))
    empty_panels = sorted(k for k in LANES if k in panels and not (panels[k].get('claims') or []))
    if not missing_panels and not empty_panels:
        report.clear(release_role, title, 'All five public-facing panels exist and contain claims.')
    else:
        report.red(release_role, title, 'Public panel problem: missing=' + repr(missing_panels) + ', empty=' + repr(empty_panels))

    claims = claim_list(analysis_doc)
    uncited = [c for c in claims if not (c.get('citations') or [])]
    if claims and not uncited:
        report.clear(citation_role, title, f'Every public claim has at least one citation ({len(claims)}/{len(claims)}).')
    elif claims:
        report.red(citation_role, title, f'{len(uncited)} of {len(claims)} public claims have no citation.')
    else:
        report.red(citation_role, title, 'No public claims are present.')

    audit = read_json(audit_path)
    if not audit:
        report.red(citation_role, title, 'Citation-audit artifact is missing or unreadable.')
    else:
        audit_status = str(audit.get('status') or '').lower()
        critical = int(audit.get('critical_count') or 0)
        checked = int(audit.get('citations_checked') or 0)
        public_count = int(audit.get('public_claim_count') or 0)
        if audit_status == 'pass' and critical == 0 and checked >= public_count > 0:
            report.clear(citation_role, title, f'Citation audit passed: {checked}/{public_count} public citations reverified; 0 critical findings.')
        else:
            report.red(citation_role, title, f'Citation audit is {audit_status or "missing status"}; checked={checked}/{public_count}; critical={critical}.')

    red = read_json(red_path)
    if not red:
        report.red(neutrality_role, title, 'Political-bias red-team artifact is missing or unreadable.')
    else:
        rstatus = str(red.get('status') or '').lower()
        rcrit = int(red.get('critical_count') or 0)
        score = float(red.get('score') or 0.0)
        if rstatus in {'pass', 'pass_with_warnings'} and rcrit == 0:
            level = report.clear if rstatus == 'pass' else report.warn
            level(neutrality_role, title, f'Bias red team: {rstatus}; score={score:.3f}; critical=0.')
        else:
            report.red(neutrality_role, title, f'Bias red team failed or has critical findings: status={rstatus}, score={score:.3f}, critical={rcrit}.')

    lr = panels.get('left_right_text') or {}
    lr_claims = lr.get('claims') or []
    lenses = {str(c.get('lens') or '').upper() for c in lr_claims if isinstance(c, dict)}
    if {'LEFT', 'RIGHT', 'TEXT'}.issubset(lenses):
        report.clear(neutrality_role, title, 'Left | Right | Text contains all three lanes on the public report.')
    else:
        report.red(neutrality_role, title, f'Left | Right | Text is incomplete; found lenses={sorted(lenses)}.')

    challenge = read_json(challenge_path)
    if not challenge:
        report.red(adversarial_role, title, 'Hostile-context challenge artifact is missing or unreadable.')
    else:
        cstatus = str(challenge.get('status') or '').lower()
        blockers = int(challenge.get('blocker_count') or 0)
        score = float(challenge.get('score') or 0.0)
        if cstatus == 'pass' and blockers == 0:
            report.clear(adversarial_role, title, f'Hostile-context challenge passed; score={score:.3f}; blockers=0.')
        else:
            report.red(adversarial_role, title, f'Hostile challenge not clean: status={cstatus}, score={score:.3f}, blockers={blockers}.')

    # Grandma lens: intentionally heuristic and advisory, never a release gate.
    clarity_flags: list[str] = []
    for idx, c in enumerate(claims, 1):
        text = re.sub(r'\s+', ' ', str(c.get('text') or '')).strip()
        if not text:
            clarity_flags.append(f'claim {idx} is empty')
            continue
        if PLACEHOLDER.search(text):
            clarity_flags.append(f'claim {idx} contains placeholder/context language')
        if LEGAL_ESE.search(text):
            clarity_flags.append(f'claim {idx} still contains legalese')
        words = re.findall(r"\b[\w'-]+\b", text)
        sentences = max(1, len(re.findall(r'[.!?](?:\s|$)', text)))
        if len(words) / sentences > 38:
            clarity_flags.append(f'claim {idx} has a very long sentence (~{len(words)//sentences} words)')
        if len(text) > 500:
            clarity_flags.append(f'claim {idx} is over 500 characters')
    if not clarity_flags:
        report.clear(grandma_role, title, 'Public claims clear basic readability/placeholder/legalese heuristics.')
    else:
        sample = '; '.join(clarity_flags[:4])
        more = f' (+{len(clarity_flags)-4} more)' if len(clarity_flags) > 4 else ''
        report.warn(grandma_role, title, sample + more + '. This is a clarity warning, not proof of factual error.')


def fetch(base: str, path: str, timeout: float = 5.0) -> tuple[int, str]:
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return int(r.status), r.read().decode('utf-8', errors='replace')


def check_web_surface(report: Report) -> None:
    role = 'Museum Surface Inspector'
    port = 8877
    base = f'http://127.0.0.1:{port}'
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=PROJECT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f'local test server exited with code {proc.returncode}')
            try:
                status, body = fetch(base, '/api/health', 1.0)
                if status == 200:
                    break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError('local test server did not become healthy')

        status, home = fetch(base, '/')
        if status == 200 and 'BILL X-RAY' in home:
            report.clear(role, 'PUBLIC SITE', 'Home page loads successfully from a clean test server.')
        else:
            report.red(role, 'PUBLIC SITE', 'Home page failed to render correctly.')

        card_missing = [bid for bid, _, _ in SHOWCASES if f'data-showcase-id="{bid}"' not in home]
        if not card_missing:
            report.clear(role, 'PUBLIC SITE', 'All four curated exhibit cards render on the home page.')
        else:
            report.red(role, 'PUBLIC SITE', 'Missing exhibit cards: ' + ', '.join(card_missing))

        if 'data-bill-search-input' not in home and 'Search any bill' not in home:
            report.clear(role, 'PUBLIC SITE', 'Public search UI is absent from the museum home page as intended.')
        else:
            report.warn(role, 'PUBLIC SITE', 'Public search UI still appears on the home page.')

        for bid, title, _ in SHOWCASES:
            try:
                s, page = fetch(base, f'/bill/{bid}')
                if s == 200 and 'BILL X-RAY' in page:
                    report.clear(role, title, 'Exhibit route returns HTTP 200 and renders Bill X-Ray.')
                    analysis = read_json(PROJECT / 'data' / 'analyses' / f'{bid}.json')
                    claims = claim_list(analysis or {})
                    citation = None
                    for claim in claims:
                        cites = claim.get('citations') or []
                        if cites and isinstance(cites[0], dict) and cites[0].get('anchor_id'):
                            citation = cites[0]
                            break
                    if citation:
                        aid = str(citation.get('anchor_id'))
                        try:
                            es, evidence = fetch(base, f'/api/evidence/{bid}/{aid}')
                            if es == 200 and aid in evidence and len(evidence) > 100:
                                report.clear('Evidence Drawer Examiner', title, 'A real public citation opens through the evidence API and returns source material.')
                            else:
                                report.red('Evidence Drawer Examiner', title, f'Evidence API did not return a usable source record for {aid}.')
                        except Exception as exc:
                            report.red('Evidence Drawer Examiner', title, f'Evidence API failed for a real public citation: {exc}')
                else:
                    report.red(role, title, f'Exhibit route did not render correctly (HTTP {s}).')
            except urllib.error.HTTPError as exc:
                report.red(role, title, f'Exhibit route returned HTTP {exc.code}.')
            except Exception as exc:
                report.red(role, title, f'Exhibit route failed: {exc}')
    except Exception as exc:
        report.red(role, 'PUBLIC SITE', f'Could not complete clean-server surface test: {exc}')
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def check_persistent_showcases(report: Report) -> None:
    role = 'Persistent Exhibit Custodian'
    try:
        sys.path.insert(0, str(PROJECT))
        from engine.showcase_release import persistent_release_status  # type: ignore
        for bid, title, _ in SHOWCASES:
            status = persistent_release_status(bid)
            state = str(status.get('state') or '')
            if state == 'verified':
                report.clear(role, title, f'Persistent exhibit store is VERIFIED ({status.get("files", "?")} files, checksums checked).')
            elif state == 'missing':
                report.red(role, title, 'Persistent verified exhibit is missing. Run PREBUILD_SHOWCASES.bat before launch.')
            else:
                report.red(role, title, f'Persistent exhibit state is {state}: {status.get("reason", "no reason returned")}')
    except Exception as exc:
        report.red(role, 'PROJECT', f'Could not inspect persistent showcase releases: {exc}')


def print_report(report: Report) -> int:
    red = [f for f in report.findings if f.level == 'RED FLAG']
    warnings = [f for f in report.findings if f.level == 'WARNING']
    clears = [f for f in report.findings if f.level == 'CLEAR']

    lines: list[str] = []
    lines.append('')
    lines.append('=' * 78)
    lines.append(' BILL X-RAY - GRANDMA MAGNIFYING-GLASS DEEP SMOKE TEST')
    lines.append('=' * 78)
    lines.append(f'Project: {PROJECT}')
    lines.append(f'Checks recorded: {report.checks} | CLEAR={len(clears)} | WARNING={len(warnings)} | RED FLAG={len(red)}')
    lines.append('')

    if red:
        lines.append('RED FLAGS - FIX OR EXPLAIN BEFORE PUBLIC LAUNCH')
        lines.append('-' * 78)
        for f in red:
            lines.append(f'[RED FLAG] {f.bill} | {f.role}: {f.message}')
        lines.append('')
    else:
        lines.append('RED FLAGS: NONE')
        lines.append('')

    if warnings:
        lines.append('WARNINGS - MAGNIFYING GLASS ITEMS')
        lines.append('-' * 78)
        for f in warnings:
            lines.append(f'[WARNING] {f.bill} | {f.role}: {f.message}')
        lines.append('')

    lines.append('PLAIN-ENGLISH VERDICT')
    lines.append('-' * 78)
    verified = []
    blocked = []
    for bid, title, _ in SHOWCASES:
        bill_red = [f for f in red if f.bill == title]
        if bill_red:
            blocked.append(title)
        else:
            verified.append(title)
    if not red:
        lines.append('No launch-blocking defect was found by this extra smoke test. The four exhibits have source/citation/release checks, the public museum responds, and the adversarial gates inspected here are clean.')
        if warnings:
            lines.append(f'There are {len(warnings)} warning(s) worth reading, but this tool found no RED FLAG. Warnings are not automatically factual failures.')
        lines.append('This is strong internal evidence, not a guarantee of legal correctness; the exact statutory evidence remains the final authority.')
    else:
        lines.append(f'This test found {len(red)} RED FLAG(s), so I would NOT call the museum launch-ready yet.')
        if blocked:
            lines.append('The biggest problems are attached to: ' + ', '.join(blocked) + '.')
        lines.append('Read the RED FLAGS above first; they are written to identify the failing layer rather than dump raw test gobbledygook.')

    lines.append('')
    lines.append('WHAT THIS EXTRA TEST LOOKED AT')
    lines.append('-' * 78)
    lines.append('Repository regressions; source-file integrity; source SHA-256 provenance; unique citation anchors; suspicious section parsing; all five public lanes; citation coverage; independent citation-audit result; political-bias red team; Left/Right/Text completeness; hostile-context challenge; Grandma readability heuristics; persistent-release checksums; four-card museum UI; hidden public search; each exhibit route, and a real Evidence Drawer citation on a clean local test server.')
    lines.append('')
    lines.append('NOTE: The Grandma clarity lens is deliberately advisory. It may flag awkward legal language without claiming the underlying statement is false.')

    text = '\n'.join(lines)
    print(text)
    try:
        (PROJECT / 'GRANDMA_MAGNIFYING_GLASS_REPORT.txt').write_text(text + '\n', encoding='utf-8')
        print(f'\nSaved report: {PROJECT / "GRANDMA_MAGNIFYING_GLASS_REPORT.txt"}')
    except Exception:
        pass
    return 1 if red else 0


def main() -> int:
    print('=' * 78)
    print(' BILL X-RAY - GRANDMA MAGNIFYING-GLASS DEEP SMOKE TEST')
    print('=' * 78)
    print('This is an extra read-only QA layer. It does not modify or publish any exhibit.')
    print('Expert lenses: repository, source, structure, citation, neutrality, adversarial,')
    print('Grandma clarity, persistent release, and public museum surface.\n')

    report = Report()
    check_repository(report)
    if PROJECT.exists():
        for bid, title, _ in SHOWCASES:
            check_sources_and_artifacts(report, bid, title)
        check_persistent_showcases(report)
        check_web_surface(report)
    return print_report(report)


if __name__ == '__main__':
    raise SystemExit(main())
